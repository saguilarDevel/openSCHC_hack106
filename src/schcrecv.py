"""OpenSCHC Reception Functionality

"""
#---------------------------------------------------------------------------

from base_import import *  # used for now for differing modules in py/upy

import schcmsg
from schcbitmap import find_missing_tiles, sort_tile_list, find_missing_tiles_no_all_1, find_missing_tiles_mic_ko_yes_all_1, make_bit_list_mic_ko
from schccomp import *

enable_statsct = True
if enable_statsct:
    from stats.statsct import Statsct

#---------------------------------------------------------------------------

"""
.. module:: schcrecv
    :platform: Code Running on MicroPython
    :synopsis: SCHC Reception Module

"""

class ReassembleBase:
    """This class is used as a common base for Reassembling packets

    """

    def __init__(self, protocol, context, rule, dtag, sender_L2addr):
        """
        
        Args :
            protocol : protocol
            context : context
            rule : rule can be either "comp" for compression, "fragSender" for fragmentation from sender and "fragReceiver" for fragmentation from receiver
            dtag : ?
            sender_L2addr : None or 'int' containing the sender's address
     
                
        """
        self.protocol = protocol
        self.context = context
        self.rule = rule
        self.dtag = dtag
        self.sender_L2addr = sender_L2addr
        self.tile_list = []
        self.mic_received = None
        self.inactive_timer = 200 #last value 120
        self.event_id_inactive_timer = None
        # state:
        #   INIT:
        #   DONE: sent ACK success. only accept ACK REQ.
        #   ALL-1: All-1 messages has been received
        #   ABORT: receiver abort send, reject any message with abort
        self.state = "INIT"
        self.schc_ack = None
        self.all1_received = False
        self.mic_missmatched = False

        self.fragment_received = False



    def get_mic(self, mic_target, extra_bits=0):
        """This gets the mic
        
        This function gets the mic and display it in a 4 byte format
        
        """

        assert isinstance(mic_target, bytearray)
        mic = get_mic(mic_target)
        print("Recv MIC {}, base = {}, lenght = {}".format(mic, mic_target, len(mic_target)))
        return mic.to_bytes(4, "big")

    def event_inactive(self):
        """ event_inactive
        
        // TODO : Redaction (here is schcrecv.py)
        
        
        """
        #if the ack-ok was received, no ACK REQ will be received,
        #check for state == "DONE" and return, this means that the ack-ok
        #was send, before the system returns after sending the ack-ok, now it 
        #waits for one inactivity timer before closing session
        if self.state == "DONE":
            return

        # sending sender abort.
        schc_frag = schcmsg.frag_receiver_tx_abort(self.rule, self.dtag)
        """
        Changement à corriger
        args = (schc_frag.packet.get_content(), self.context["devL2Addr"])
        """
        args = (schc_frag.packet.get_content(), '*')
        print("Sent Receiver-Abort.", schc_frag.__dict__)
        print("----------------------- SCHC RECEIVER ABORT SEND  -----------------------")

        if enable_statsct:
            Statsct.set_msg_type("SCHC_RECEIVER_ABORT")
            Statsct.set_header_size(schcmsg.get_sender_header_size(self.rule))
        self.state = "ABORT"
        self.protocol.scheduler.add_event(0,
                                    self.protocol.layer2.send_packet, args)
        # XXX needs to release all resources.
        return

    def cancel_inactive_timer(self):
        """ cancel_inactive_timer
        
        // TODO : Redaction (here is schcrecv.py)
        
        """
        if self.event_id_inactive_timer is None:
            return
        self.protocol.scheduler.cancel_event(self.event_id_inactive_timer)
        self.event_id_inactive_timer = None

#---------------------------------------------------------------------------

class ReassemblerNoAck(ReassembleBase):
    """ ReassemblerNoAck class
    
    // Todo : Redaction
    
    """
    def receive_frag(self, bbuf, dtag):
        print('state: {}, recieved fragment -> {}, rule-> {}'.format(self.state,
                                                                     bbuf, self.rule))

        schc_frag = schcmsg.frag_receiver_rx(self.rule, bbuf)
        print("receiver frag received:", schc_frag.__dict__)
        # XXX how to authenticate the message from the peer. without
        # authentication, any nodes can cancel the invactive timer.
        self.cancel_inactive_timer()
        print(schc_frag)
        #
        if schc_frag.abort == True:
            print("----------------------- Sender-Abort ---------------------------")
            # XXX needs to release all resources.
            return
        self.tile_list.append(schc_frag.payload)
        #
        if schc_frag.fcn == schcmsg.get_fcn_all_1(self.rule):
            print("----------------------- Final Reassembly -----------------------")
            print("ALL1 received")
            # MIC calculation
            print("tile_list")
            for _ in self.tile_list:
                print(_)
            schc_packet = BitBuffer()
            for i in self.tile_list:
                schc_packet += i
            mic_calced = self.get_mic(schc_packet.get_content())
            if schc_frag.mic != mic_calced:
                print("ERROR: MIC mismatched. packet {} != result {}".format(
                        schc_frag.mic, mic_calced))
                self.state = 'ERROR_MIC_NO_ACK'
                return
            else:
                print("SUCCESS: MIC matched. packet {} == result {}".format(
                    schc_frag.mic, mic_calced))
            # decompression
            # print("----------------------- Decompression -----------------------")
            if not self.protocol.config.get("debug-fragment"):
                # XXX
                # XXX in hack105, we have separate databases for C/D and F/R.
                # XXX need to merge them into one.  Then, here searching database will
                # XXX be moved into somewhere.
                # XXX
                #rule = self.protocol.rule_manager.FindRuleFromSCHCpacket(schc=schc_packet)
                #print("debug: no-ack FindRuleFromSCHCpacket", rule)
                self.protocol.process_decompress(schc_packet, self.sender_L2addr, "UP")
            self.state = 'DONE_NO_ACK'
            #print(self.state)
            return
        # set inactive timer.
        self.event_id_inactive_timer = self.protocol.scheduler.add_event(
                self.inactive_timer, self.event_inactive, tuple())
        print("---", schc_frag.fcn)

#---------------------------------------------------------------------------

class ReassemblerAckOnError(ReassembleBase):
    """ ReassemblerAckOnError class
    
    Todo : Redaction
    
    """
    # In ACK-on-Error, a fragment contains tiles belonging to different window.
    # A type of data structure holding tiles in each window is not suitable.  
    # So, here just appends a fragment into the tile_list like No-ACK.

    def receive_frag(self, bbuf, dtag):

<<<<<<< Updated upstream:src/schcrecv.py
        print('state: {}, recieved fragment -> {}, rule-> {}'.format(self.state,
                                                                     bbuf, self.rule))

        schc_frag = schcmsg.frag_receiver_rx(self.rule, bbuf)
        print("receiver frag received:", schc_frag.__dict__)
=======
        dprint('state: {}, received fragment -> {}, rule-> {}'.format(self.state,
                                                                     bbuf, self.rule))
        input("")
        schc_frag = frag_msg.frag_receiver_rx(self.rule, bbuf)
        dprint("receiver frag received:", schc_frag.__dict__)
>>>>>>> Stashed changes:src/frag_recv.py
        # XXX how to authenticate the message from the peer. without
        # authentication, any nodes can cancel the invactive timer.
        self.cancel_inactive_timer()
        if self.state == "ABORT":
            self.send_receiver_abort()
            return
        #
        # input("")
        if schc_frag.abort == True:
            print("----------------------- Sender-Abort ---------------------------")
            # Statsct.set_msg_type("SCHC_SENDER_ABORT")
            # XXX needs to release all resources.
            return

        if schc_frag.ack_request == True:
            print("Received ACK-REQ")
            # if self.state != "DONE":
            #     #this can happen when the ALL-1 is not received, so the state is
            #     #not done and the sender is requesting an ACK.
            #     # sending Receiver abort.
            #     schc_frag = schcmsg.frag_receiver_tx_abort(self.rule, self.dtag)
            #     args = (schc_frag.packet.get_content(), self.context["devL2Addr"])
            #     print("Sent Receiver-Abort.", schc_frag.__dict__)
            #     print("----------------------- SCHC RECEIVER ABORT SEND  -----------------------")

            #     if enable_statsct:
            #         Statsct.set_msg_type("SCHC_RECEIVER_ABORT")
            #         #Statsct.set_header_size(schcmsg.get_sender_header_size(self.rule))
            #     self.protocol.scheduler.add_event(0,
            #                                 self.protocol.layer2.send_packet, args)
            #     # XXX needs to release all resources.
            #     return
            print("XXX need sending ACK back.")
            self.state = 'ACK_REQ'
            # input('')
            self.resend_ack(schc_frag)
            return

        self.fragment_received = True
        # append the payload to the tile list.
        # padding truncation is done later. see below.
        # nb_tiles = schc_frag.payload.count_added_bits()//self.rule["tileSize"]
        tile_size = self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_TILE]
        nb_tiles, last_tile_size = (
            schc_frag.payload.count_added_bits() // tile_size,
            schc_frag.payload.count_added_bits() % tile_size)
        print("---------nb_tiles: ", nb_tiles, " -----last_tile_size ", last_tile_size)
        tiles = [schc_frag.payload.get_bits_as_buffer(tile_size) for _ in range(nb_tiles)]
        print("---------tiles: ", tiles)

        # Note that nb_tiles is the number of tiles which is exact number of the
        # size of the tile.  the tile of which the size is less than the size
        # is not included.
        # The tile that is less than a tile size must be included, so a 1 can be added
        # in the bitmap when there is a tile in the all-1 message

        win = schc_frag.win
        fcn = schc_frag.fcn
        for tile_in_tiles in tiles:
            idx = tiles.index(tile_in_tiles)
            if tile_in_tiles.count_added_bits() % tile_size != 0:
                # tile found that is smaller than a normal tile
                print("tile found that is smaller than a normal tile")
                # nb_tiles = 1
            # tile should only be append if it is not in the list
            tile_in_list = False
            for tile in self.tile_list:
                if tile["w-num"] == win:
                    if tile["t-num"] == fcn - idx:
                        print("tile is already in tile list")
                        tile_in_list = True
            if not tile_in_list:
                self.tile_list.append({
                    "w-num": win,
                    "t-num": fcn - idx,
                    "nb_tiles": 1,
                    "raw_tiles": tile_in_tiles})
                self.tile_list = sort_tile_list(self.tile_list, self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN])
            if (fcn - idx) == 0:
                win += 1
                fcn = self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN] << 1
                tiles = tiles[(idx + 1):]

        # !IMPORTANT: it's neccesary to change this condition for one more exact which consider the last tile size cases
        if last_tile_size > 8:
            last_tile = schc_frag.payload.get_bits_as_buffer(last_tile_size)
            print('---------tile:', last_tile)
            tile_in_list = False
            for tile in self.tile_list:
                if tile["w-num"] == win:
                    if tile["t-num"] == 7:
                        print("tile is already in tile list")
                        tile_in_list = True
            if not tile_in_list:
                self.tile_list.append({
                    "w-num": win,
                    "t-num": 7,
                    "nb_tiles": 1,
                    "raw_tiles": last_tile})
                self.tile_list = sort_tile_list(self.tile_list, self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN])

        # if schc_frag.payload.count_added_bits()%self.rule["tileSize"] != 0:
        #     #tile found that is smaller than a normal tile
        #     print("tile found that is smaller than a normal tile")
        #     #nb_tiles = 1
        # #tile should only be append if it is not in the list
        # tile_in_list = False
        # for tile in self.tile_list:
        #     if tile["w-num"] == schc_frag.win:
        #         if tile["t-num"] == schc_frag.fcn:
        #             print("tile is already in tile list")
        #             tile_in_list = True
        # if not tile_in_list:
        #     self.tile_list.append({
        #             "w-num": schc_frag.win,
        #             "t-num": schc_frag.fcn,
        #             "nb_tiles": nb_tiles,
        #             "raw_tiles":schc_frag.payload})
        #     self.tile_list = sort_tile_list(self.tile_list, self.rule["FCNSize"])
        for tile in self.tile_list:
            print("w-num: {} t-num: {} nb_tiles:{}".format(
                tile['w-num'], tile['t-num'], tile['nb_tiles']))
        print("")
        # print("raw_tiles:{}".format(tile['raw_tiles']))
        # self.tile_list = sort_tile_list(self.tile_list, self.rule["WSize"])

        # self.tile_list.append({
        #         "w-num": schc_frag.win,
        #         "t-num": schc_frag.fcn,
        #         "nb_tiles": nb_tiles,
        #         "raw_tiles":schc_frag.payload})
        # self.tile_list = sort_tile_list(self.tile_list, self.rule["FCNSize"])
        # self.tile_list = sort_tile_list(self.tile_list, self.rule["WSize"])

        if self.mic_received is not None:
            schc_packet, mic_calced = self.get_mic_from_tiles_received()
            if self.mic_received == mic_calced:
                self.finish(schc_packet, schc_frag)
                return
            else:
                # XXX waiting for the fragments requested by ACK.
                # during MAX_ACK_REQUESTS
                print("waiting for more fragments.")
        elif schc_frag.fcn == schcmsg.get_fcn_all_1(self.rule):
            print("----------------------- ALL1 received -----------------------")
            self.all1_received = True
            #Statsct.set_msg_type("SCHC_ALL_1")
            self.mic_received = schc_frag.mic
            schc_packet, mic_calced = self.get_mic_from_tiles_received()
            print("schc_frag.mic: {}, mic_calced: {}".format(schc_frag.mic, mic_calced))
            if schc_frag.mic == mic_calced:
                print("SUCCESS: MIC matched. packet {} == result {}".format(
                    schc_frag.mic, mic_calced))
                self.mic_missmatched = False
                self.finish(schc_packet, schc_frag)
                return
            else:
                self.mic_missmatched = True
                self.state = 'ERROR_MIC'
                print("----------------------- ERROR -----------------------")
                print("ERROR: MIC mismatched. packet {} != result {}".format(
                    schc_frag.mic, mic_calced))
                bit_list = find_missing_tiles(self.tile_list,
                                              self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN],
                                              schcmsg.get_fcn_all_1(self.rule))

                assert bit_list is not None

                schc_ack = self.create_ack_schc_ko(schc_frag)
                """
                Changement à corriger
                args = (schc_ack.packet.get_content(), self.context["devL2Addr"])
                """
                args = (schc_ack.packet.get_content(), '*')
                self.protocol.scheduler.add_event(
                    0, self.protocol.layer2.send_packet, args)
                # XXX need to keep the ack message for the ack request.
        # set inactive timer.
        self.event_id_inactive_timer = self.protocol.scheduler.add_event(
            self.inactive_timer, self.event_inactive, tuple())
        print("---", schc_frag.fcn)

    def resend_ack(self, schc_frag):
        print("resend ack method")
        print(schc_frag.__dict__)
        if self.mic_received is not None:
            schc_packet, mic_calced = self.get_mic_from_tiles_received()
            print("schc_frag.mic: {}, mic_calced: {}".format(self.mic_received,mic_calced))
            if self.mic_received == mic_calced:
                self.state = "DONE"
        if self.state == "DONE":
            # ACK message
            schc_ack = schcmsg.frag_receiver_tx_all1_ack(
                schc_frag.rule,
                schc_frag.dtag,
                schc_frag.win,
                cbit=1)
            print("ACK success sent:", schc_ack.__dict__)
            if enable_statsct:
                Statsct.set_msg_type("SCHC_ACK_OK")
            print("----------------------- SCHC ACK OK SEND  -----------------------")
        else:
            if self.all1_received:
                print("all-1 received, building ACK")
                print('send ack before done {},{},{}'.format(self.tile_list,
                            self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN], schcmsg.get_fcn_all_1(self.rule)))
                schc_ack = self.create_ack_schc_ko(schc_frag)
            else:
                #special case when the ALL-1 message is lost: 2 cases:
                #1) the all-1 carries a tile (bit in bitmap)
                #2) the all-1 only carries the MIC (no bit in bitmap)
                if self.fragment_received is False:
                    print("no fragments received yet, abort")
                    self.send_receiver_abort()
                
                    return
                print("all-1 not received, building ACK")
                print('send ack before done {},{},{}'.format(self.tile_list,
                            self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN], schcmsg.get_fcn_all_1(self.rule)))
                for tile in self.tile_list:
                    print("w-num: {} t-num: {} nb_tiles:{}".format(
                        tile['w-num'],tile['t-num'],tile['nb_tiles']))
                    print("raw_tiles:{}".format(tile['raw_tiles']))
                
                
                bit_list = find_missing_tiles_no_all_1(self.tile_list,
                                                self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN],
                                                schcmsg.get_fcn_all_1(self.rule))
                print('send ack before done {}'.format(bit_list))
                assert bit_list is not None
                if len(bit_list) == 0:
                    bit_list = find_missing_tiles_no_all_1(self.tile_list,
                                                self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN],
                                                schcmsg.get_fcn_all_1(self.rule))
                for bl_index in range(len(bit_list)):
                    print("missing wn={} bitmap={}".format(bit_list[bl_index][0],
                                                            bit_list[bl_index][1]))
                    # XXX compress bitmap if needed.
                    # ACK failure message
                    schc_ack = schcmsg.frag_receiver_tx_all1_ack(
                            schc_frag.rule,
                            schc_frag.dtag,
                            win=bit_list[bl_index][0],
                            cbit=0,
                            bitmap=bit_list[bl_index][1])
                    if enable_statsct:
                        Statsct.set_msg_type("SCHC_ACK_KO")
                    print("----------------------- SCHC ACK KO SEND  -----------------------")
 
                    print("ACK failure sent:", schc_ack.__dict__)
        """
        Changement à corriger
        args = (schc_ack.packet.get_content(), self.context["devL2Addr"])
        """
        args = (schc_ack.packet.get_content(), "*")
        self.protocol.scheduler.add_event(0, self.protocol.layer2.send_packet, args)
        # XXX need to keep the ack message for the ack request.
    def finish(self, schc_packet, schc_frag):
        self.state = "DONE"
        print('state DONE -> {}'.format(self.state))
        #input('DONE')
        # decompression
        self.protocol.process_decompress(schc_packet, self.sender_L2addr, direction="UP")

        # ACK message
        schc_ack = schcmsg.frag_receiver_tx_all1_ack(
                schc_frag.rule,
                schc_frag.dtag,
                schc_frag.win,
                cbit=1)
        print("ACK success sent:", schc_ack.__dict__)
        if enable_statsct:
            Statsct.set_msg_type("SCHC_ACK_OK")
        print("----------------------- SCHC ACK OK SEND  -----------------------")
        """
        Changement à corriger
        args = (schc_ack.packet.get_content(), self.context["devL2Addr"])
        """
        args = (schc_ack.packet.get_content(), '*')
        self.protocol.scheduler.add_event(0, self.protocol.layer2.send_packet, args)
        # XXX need to keep the ack message for the ack request.
        #the ack is build everytime
        self.schc_ack = schc_ack
        # set inactive timer.
        #self.event_id_inactive_timer = self.protocol.scheduler.add_event(
        #        self.inactive_timer, self.event_inactive, tuple())
        #print("DONE, but in case of ACK REQ MUST WAIT ", schc_frag.fcn)

    def get_mic_from_tiles_received(self):
        # MIC calculation.
        # The truncation of the padding should be done here
        # because the padding of the last tile must be included into the
        # MIC calculation.  However, the fact that the last tile is
        # received can be known after the All-1 fragment is received.
        assert len(self.tile_list) > 0
        print("tile_list:")
        for _ in self.tile_list:
            print(_)
        schc_packet = BitBuffer()
        if len(self.tile_list) > 1:
            for i in self.tile_list[:-2]:
                # it needs to copy the buffer as it will be reused later.
                tiles = i["raw_tiles"].copy().get_bits_as_buffer(
                    i["nb_tiles"]*self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_TILE])
                schc_packet += tiles
            # check the size of the padding in the All-1 fragment.
            if (self.tile_list[-1]["raw_tiles"].count_added_bits() <
                self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_L2WORDSIZE]):
                # the last tile exists in the fragment before the All-1
                # fragment and the payload has to add as it is.
                # the All-1 fragment doesn't need to taken into account
                # of the MIC calculation.
                schc_packet += self.tile_list[-2]["raw_tiles"]
            else:
                # the last tile exists in the All-1 fragment.
                # it needs to truncate the padding in the fragment before that.
                i = self.tile_list[-2]
                schc_packet += i["raw_tiles"].copy().get_bits_as_buffer(
                    i["nb_tiles"]*self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_TILE])
                schc_packet += self.tile_list[-1]["raw_tiles"]
        else:
            # len(self.tile_list) == 1
            # add into the packet as it is.
            schc_packet += self.tile_list[0]["raw_tiles"]
        # get the target of MIC from the BitBuffer.
        print("---MIC calculation:")
        mic_calced = self.get_mic(schc_packet.get_content())
        return schc_packet, mic_calced

    def send_receiver_abort(self):
        # sending Receiver abort.
        self.state = "ABORT"
        schc_frag = schcmsg.frag_receiver_tx_abort(self.rule, self.dtag)
        """
        Changement à  corriger
        args = (schc_frag.packet.get_content(), self.context["devL2Addr"])
        """
        args = (schc_frag.packet.get_content(), '*')
        print("Sent Receiver-Abort.", schc_frag.__dict__)
        print("----------------------- SCHC RECEIVER ABORT SEND  -----------------------")

        if enable_statsct:
            Statsct.set_msg_type("SCHC_RECEIVER_ABORT")
            #Statsct.set_header_size(schcmsg.get_sender_header_size(self.rule))
        self.protocol.scheduler.add_event(0,
                                    self.protocol.layer2.send_packet, args)
    
    def create_ack_schc_ko(self, schc_frag):
        """Create schc_ack packet in case of wrong RCS (C=0)
            return schc_ack packet
        """
        bit_list = find_missing_tiles_mic_ko_yes_all_1(self.tile_list,
                                                self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN],
                                                schcmsg.get_fcn_all_1(self.rule))
        for tile in self.tile_list:
            print("w-num: {} t-num: {} nb_tiles:{}".format(
                tile['w-num'],tile['t-num'],tile['nb_tiles']))
            print("raw_tiles:{}".format(tile['raw_tiles']))
        print('send ack before done {}'.format(bit_list))
        assert bit_list is not None

        if bit_list:
            # Some tiles are actually missing, send ACK for first window with missing tiles
            print("missing wn={} bitmap={}".format(bit_list[0][0],
                                                    bit_list[0][1]))
                                                    # XXX compress bitmap if needed.
            # ACK failure message
            schc_ack = schcmsg.frag_receiver_tx_all1_ack(
                    schc_frag.rule,
                    schc_frag.dtag,
                    win=bit_list[0][0],
                    cbit=0,
                    bitmap=bit_list[0][1])
        else:
            window_list = make_bit_list_mic_ko(self.tile_list,
                                        self.rule[T_FRAG][T_FRAG_PROF][T_FRAG_FCN],
                                        schcmsg.get_fcn_all_1(self.rule))
            last_window = max(window_list.keys())

            # No tiles are detected missing, send ACK for last window
            print("No missing tiles, sending last window: wn={} bitmap={}".format(last_window,
                                                    BitBuffer(window_list[last_window])))
                                                    # XXX compress bitmap if needed.
            # ACK failure message
            schc_ack = schcmsg.frag_receiver_tx_all1_ack(
                    schc_frag.rule,
                    schc_frag.dtag,
                    win=last_window,
                    cbit=0,
                    bitmap=BitBuffer(window_list[last_window]))
        if enable_statsct:
            Statsct.set_msg_type("SCHC_ACK_KO")
        print("----------------------- SCHC ACK KO SEND  -----------------------")
        print("ACK failure sent:", schc_ack.__dict__)
        return schc_ack
#---------------------------------------------------------------------------
