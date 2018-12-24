# ---------------------------------------------------------------------------

from base_import import *  # used for now for differing modules in py/upy

import compress

# ---------------------------------------------------------------------------

from schcrecv import ReassemblerAckOnError
from schcrecv import ReassemblerNoAck
from schcsend import FragmentAckOnError
from schcsend import FragmentNoAck
from compress import Compression

class Session:
    """ fragmentation/reassembly session manager
    session = [
        { "ruleID": n, "ruleLength", "dtag": n, "session": session }, ...
        ]
    """
    def __init__(self, protocol):
        self.protocol = protocol
        self.session_list = []

    def add(self, rule_id, rule_id_size, dtag, session):
        if self.get(rule_id, rule_id_size, dtag) is not None:
            print("ERROR: the session rid={}/{} dtag={} exists already".format(
                    rule_id, rule_id_size, dtag))
            return False
        self.session_list.append({"rule_id": rule_id,
                                  "rule_id_size": rule_id_size, "dtag": dtag,
                                  "session": session })
        return True

    def get(self, rule_id, rule_id_size, dtag):
        for i in self.session_list:
            if (rule_id == i["rule_id"] and rule_id_size == i["rule_id_size"]
                and dtag == i["dtag"]):
                return i["session"]
        return None

class SCHCProtocol:
    """This class is the entry point for the openschc
    (in this current form, object composition is used)"""
    #def __init__(self, config, scheduler, schc_layer2, role="sender"):
    def __init__(self, config, system, layer2, layer3):
        self.config = config
        self.system = system
        self.scheduler = system.get_scheduler()
        self.layer2 = layer2
        self.layer3 = layer3
        self.layer2._set_protocol(self)
        self.layer3._set_protocol(self)
        self.default_frag_rule = None # XXX: to be in  rule_manager
        self.compression = compress.Compression(self)
        self.fragment_session = Session(self)
        self.reassemble_session = Session(self)

    def _log(self, message):
        self.log("schc", message)

    def log(self, name, message):
        self.system.log(name, message)

    def set_rulemanager(self, rule_manager):
        self.rule_manager = rule_manager

    def set_dev_L2addr(self, dev_L2addr):
        """ set the L2 address of the SCHC device """
        self.dev_L2addr = dev_L2addr

    def event_receive_from_L3(self, dst_L3addr, raw_packet):
        self._log("recv-from-L3 -> {} {}".format(dst_L3addr, raw_packet))
        context = self.rule_manager.find_context_bydstiid(dst_L3addr)
        if context is None:
            self._log("Looks not for SCHC packet, L3addr={}".format(dst_L3addr))
            args = (raw_packet, self.layer2.mac_id, None, None)
            self.scheduler.add_event(0, self.layer2.send_packet, args)
            return
        # XXX how to know the L2 address of the SCHC device ?
        # for now, dev_L2addr must be set before processing SCHC.
        # Therefore, the node must call set_dev_L2addr() before
        # sending a packet.
        #
        # Compression process
        packet_bbuf = BitBuffer(raw_packet)
        rule = context["comp"]
        self._log("compression rule_id={}".format(rule.ruleID))
        packet_bbuf, meta_info = self.compression.compress(packet_bbuf)
        # check if fragmentation is needed.
        if packet_bbuf.count_added_bits() < self.layer2.get_mtu_size():
            self._log("SCHC fragmentation is not needed. size={}".format(
                    packet_bbuf.count_added_bits()))
            args = (packet_bbuf.get_content(), self.layer2.mac_id, None,
                    None)
            self.scheduler.add_event(0, self.layer2.send_packet, args)
            return
        # fragmentation is required.
        if context.get("fragSender") is None:
            self._log("Rejected the packet due to no fragmenation rule.")
            return
        # Do fragmenation
        rule = context["fragSender"]
        self._log("fragmentation rule_id={}".format(rule.ruleID))
        session = self.new_fragment_session(rule)
        session.set_packet(packet_bbuf)
        self.fragment_session.add(rule.ruleID, rule.ruleLength,
                                    session.dtag, session)
        session.start_sending()
        # self.layer2.send_packet() will be called in the session.

    def new_fragment_session(self, rule):
        mode = rule.get("FRMode")
        if mode == "noAck":
            session = FragmentNoAck(self, rule) # XXX
        elif mode == "ackAlwayw":
            raise NotImplementedError(
                    "{} is not implemented yet.".format(mode))
        elif mode == "ackOnError":
            session = FragmentAckOnError(self, rule) # XXX
        else:
            raise ValueError("invalid FRMode: {}".format(mode))
        return session

    def new_reassemble_session(self, bbuf, rule, dtag, sender_L2addr):
        mode = rule.get("FRMode")
        if mode == "noAck":
            session = ReassemblerNoAck(self, rule, dtag, sender_L2addr)
        elif mode == "ackAlways":
            raise NotImplementedError("FRMode:", mode)
        elif mode == "ackOnError":
            session = ReassemblerAckOnError(self, rule, dtag, sender_L2addr)
        else:
            raise ValueError("FRMode:", mode)
        return session

    def event_receive_from_L2(self, sender_L2addr, raw_packet):
        self._log("recv-from-L2 {}->{} {}".format(
            sender_L2addr, self.layer2.mac_id, raw_packet))
        # find context for the SCHC processing.
        # XXX
        # the receiver never knows if the packet from the device having the L2
        # addrss is encoded in SCHC.  Therefore, it has to search the db with
        # the field value of the packet.
        # XXX for now, dev_L2addr is used.
        context = self.rule_manager.find_context_bydevL2addr(self.dev_L2addr)
        if context is None:
            self._log("Looks not for SCHC packet, sender L2addr={}".format(
                    self.dev_L2addr))
            args = (sender_L2addr, self.layer2.mac_id, raw_packet)
            self.scheduler.add_event(0, self.layer3.receive_packet, args)
            return
        # find a rule in the context for this packet.
        packet_bbuf = BitBuffer(raw_packet)
        key, rule = self.rule_manager.find_rule_bypacket(context, packet_bbuf)
        if key == "fragSender":
            if rule["dtagSize"] > 0:
                dtag = packet_bbuf.get_bits(rule.get("dtagSize"),
                                    position=rule.get("ruleLength"))
            else:
                dtag = None
            # find existing session for fragment or reassembly.
            session = self.fragment_session.get(rule.ruleID,
                                                rule.ruleLength, dtag)
            if session is not None:
                session.cancel_timer()
                print("Fragmentation session found", session)
                session.receive_frag(packet_bbuf, dtag)
            else:
                print("context exists, but no {} session for this packet {}".
                        format(key, self.dev_L2addr))
        elif key == "fragReceiver":
            if rule["dtagSize"] > 0:
                dtag = packet_bbuf.get_bits(rule.get("dtagSize"),
                                    position=rule.get("ruleLength"))
            else:
                dtag = None
            # find existing session for fragment or reassembly.
            session = self.reassemble_session.get(rule.ruleID,
                                                rule.ruleLength, dtag)
            if session is not None:
                session.cancel_timer()
                print("Reassembly session found", session)
            else:
                # no session is found.  create a new reassemble session.
                session = self.new_reassemble_session(packet_bbuf,
                                                      rule, dtag,
                                                      sender_L2addr)
                self.reassemble_session.add(rule.ruleID, rule.ruleLength,
                                            dtag, session)
                print("New reassembly session created", session)
            session.receive_frag(packet_bbuf, dtag)
        elif key == "compression":
            # if there is no reassemble rule, process_decompress() is directly
            # called from here.  Otherwise, it will be called from a reassemble
            # function().
            self.process_decompress(sender_L2addr, packet_bbuf)
        elif key is None:
            raise ValueError(
                    "context exists, but no rule found for L2Addr {}".
                    format(self.dev_L2addr))
        else:
            raise SystemError("should not come here.")

    def process_decompress(self, sender_L2addr, schc_packet):
        raw_packet = self.compression.decompress(schc_packet)
        args = (sender_L2addr, self.layer2.mac_id, raw_packet)
        self.scheduler.add_event(0, self.layer3.receive_packet, args)

