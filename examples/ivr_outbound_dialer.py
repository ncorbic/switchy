# Switchy IVR Outbound Dialer
#
# Author: Nenad Corbic <ncorbic@sangoma.com>
#
# This application is designed to demonstrate Switchy capabilities
# and ease of use.  The application will connect to actively running
# FreeSWITCH or Sangoma NSG application. It will then originate
# a single call and play introductory IVR message. From then
# on application will wait for user input via DTMF.
#
# IVR Menu
#  911 - Play file contact system admin
#  811 - Play file hello
#  111 - Cause a hangup
#  If user times out on DTMF a hello playback will be heard
#
# All user logic should be defined in IVRCallLogic Class.
#
# Variables
#  self.<variables>       are global in nature.
#  call.vars.['var_name'] should be used for per call info and state
#
# Switchy Documentation
#  https://github.com/sangoma/switchy/blob/master/switchy/models.py
#          class: Session Event Call Job
#
#  https://github.com/sangoma/switchy/blob/master/switchy/observe.py
#          class: EventListener Client
#
# Sample Switchy Applications
#  https://switchy.readthedocs.org/en/latest/apps.html
#
# License:
#  BSD License
#  http://opensource.org/licenses/bsd-license.php
#
#  Copyright (c) 2015, Sangoma Technologies Inc
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without modification,
#  are permitted provided that the following conditions are met:
#  1. Developer makes use of Sangoma NetBorder Gateway or Sangoma Session Border Controller
#  2. Redistributions of source code must retain the above copyright notice,
#     this list of conditions and the following disclaimer.
#  3. Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS
#  OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#  IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
#  INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
#  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
#  OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#  ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


import time
import switchy
import threading
from switchy.marks import event_callback
from switchy import get_originator

# Enable logging to stderr
# Debug levels: INFO in production, DEBUG in devel
log = switchy.utils.log_to_stderr(INFO)

# Specify FreeSWITCH or Sangoma NSG IP information
# In this example the sample app is running on
# Sangoma NSG appliance hence the use of local address
host = "127.0.0.1"
port = 8821


# IVR Call Logic
# This is the main IVR logic
# All custom development should be done here.
# Variables
#   self.<variables>       are global in nature.
#   call.vars.['var_name'] should be used for per call info and state
#
class IVRCallLogic(object):

    def prepost(self, client, listener):
        # Get the install directory of FreeSWITCH or Sangoma NSG and append recording to it
        # By default FreeSWITCH resides in /usr/local/freeswitch, NSG resides in /usr/local/nsg
        self.base_dir = client.cmd('global_getvar base_dir')
        self.recdir = self.base_dir + "/recording"
        log.info("Setting recording dir to '{}" . format(self.recdir))

        # Get the install directory of NSG and append sounds to it
        self.sound_dir = self.base_dir +  "/sounds"
        log.info("Setting sounds dir to '{}" . format(self.sound_dir))

        self.stereo = False

        # mod_sndfile module is a must in order to play prompts
        # Example of how to execute FreeSWITCH/NSG commands as from the CLI
        try:
            client.cmd('load mod_sndfile')
        except switchy.utils.CommandError:
            pass

        # Example of how to use a Timer to measure elapsed time
        # This example does not use it, but its use is commented out and
        # left for demonstration purposes
        self.dtmf_timeout = switchy.utils.Timer()
        self.dtmf_timeout_period = 3.0

    @event_callback('CHANNEL_PARK')
    def on_park(self, sess):
        # Example of how to answer an inbound call
        # This application demonstrates outbound dialing
        if sess.is_inbound():
            sess.answer()

    @event_callback("CHANNEL_ANSWER")
    def on_answer(self, sess):
        call = sess.call

        # This application does not deal with inbound calls.
        if sess.is_inbound():
            pass

        # Outbound call hsa just been answered
        # Developer would start the introductory IVR message
        if sess.is_outbound():

            # Start recording a call
            call.vars['record'] = True
            sess.start_record('{}/callee_{}.wav'.format(self.recdir, sess.uuid), stereo=self.stereo)

            # Play IVR initial greeting
            call.vars['play_welcome'] = True
            play_filename = '{}/en/us/callie/ivr/8000/ivr-welcome.wav'.format(self.sound_dir)
            sess.playback(play_filename)

            # At this point we wait for PLAYBACK_STOP event to finish
            # We could trigger a timeout as in DTMF section

    # Timer handler function that implements DTMF timeout
    def dtmf_timeout_action(self, sess):
        call = sess.call

        log.info("'{}': DTMF timeout".  format(sess.uuid))

        if call.vars.get('playing') is True:
            call.vars['playing'] = False
            sess.breakmedia()

        # Reset incoming dtmf queue
        call.vars['incoming_dtmf'] = None

        # Example of playing a prompt urging the user to try again
        play_filename = '{}/en/us/callie/ivr/8000/ivr-hello.wav'.format(self.sound_dir)
        call.vars['playing'] = True
        sess.playback(play_filename)

        # Trigger dtmf timeout again
        call.vars['dtmf_timeout_job'] = threading.Timer(3, self.dtmf_timeout_action, [self, sess])

    @event_callback('DTMF')
    def on_digit(self, sess):
        call = sess.call
        digit = int(sess['DTMF-Digit'])

        # DTMF has just been detected, stop playing any files to the user
        if call.vars.get('playing') is True:
            sess.breakmedia()

        # If DTMF timeout is pending, reset the DTMF timeout
        if call.vars.get('dtmf_timeout_job'):
            log.debug("'{}': Cancel dtmf timeout job" . format(sess.uuid))
            call.vars.get('dtmf_timeout_job').cancel()
            call.vars['dtmf_timeout_job'] = None

        # Restart the DTMF timeout
        call.vars['dtmf_timeout_job'] = threading.Timer(3, self.dtmf_timeout_action, [sess])
        call.vars.get('dtmf_timeout_job').start()

        # Example of how to check elapsed time
        # elapsed=self.dtmf_timeout.elapsed()
        # if elapsed >= self.dtmf_timeout_period:
        #    log.info("'{}': Resetting DTMF queue: timeout" . format(sess.uuid))
        #    call.vars['incoming_dtmf'] = None
        #    self.dtmf_timeout.reset()

        log.info("'{}': DTMF dtmf digit '{}'".  format(sess.uuid, digit))

        # Add incoming digit into the digit queue
        if call.vars.get('incoming_dtmf') is None:
            call.vars['incoming_dtmf'] = str(digit)
        else:
            call.vars['incoming_dtmf'] += str(digit)

        # IVR Menu
        if call.vars.get('incoming_dtmf') == '911':
            log.info("'{}': Playing 911 file STARTED" . format(sess.uuid))
            call.vars['incoming_dtmf'] = None
            play_filename = '{}/en/us/callie/ivr/8000/ivr-contact_system_administrator.wav' . format(self.sound_dir)
            call.vars['playing'] = True
            sess.playback(play_filename)

        if call.vars.get('incoming_dtmf') == '811':
            log.info("'{}': Playing 811 file STARTED" . format(sess.uuid))
            call.vars['incoming_dtmf'] = None
            play_filename = '{}/en/us/callie/ivr/8000/ivr-hello.wav'.format(self.sound_dir)
            call.vars['playing'] = True
            sess.playback(play_filename)

        if call.vars.get('incoming_dtmf') == '111':
            log.info("'{}': User chose to hangup" . format(sess.uuid))
            call.vars['incoming_dtmf'] = None
            sess.hangup()

        # End of IVR menu: If max digits where entered reset the dtmf queue
        # One could restart the menu
        if call.vars.get('incoming_dtmf') is not None and len(call.vars['incoming_dtmf']) >= 3:
            log.debug("'{}': Resetting DTMF queue" . format(sess.uuid))
            call.vars['incoming_dtmf'] = None
            # self.dtmf_timeout.reset()

    @event_callback("PLAYBACK_START")
    def on_playback_start(self, sess):
        call = sess.call
        log.info("'{}': got PLAYBACK_START ".  format(sess.uuid))
        if call.vars.get('play_welcome') is True:
            log.info("'{}': Playing Welcome STARTED" . format(sess.uuid))

    @event_callback("PLAYBACK_STOP")
    def on_playback_stop(self, sess):
        call = sess.call
        log.info("'{}': got PLAYBACK_STOP ".  format(sess.uuid))
        call.vars['playing'] = False
        if call.vars.get('play_welcome') is True:
            call.vars['play_welcome'] = False
            log.info("'{}': Playing Welcome STOPPED, Lets Wait for Digits" . format(sess.uuid))

    @event_callback("RECORD_START")
    def on_record_start(self, sess):
        call = sess.call
        log.info("'{}': got RECORD_START ".  format(sess.uuid))

    @event_callback("RECORD_STOP")
    def on_record_stop(self, sess):
        call = sess.call
        log.info("'{}': got RECORD_STOP ".  format(sess.uuid))

    @event_callback('CHANNEL_HANGUP')
    def on_hangup(self, sess, job):
        call = sess.call
        log.info("'{}': got HANGUP ". format(sess.uuid))
        if call.vars.get('play_welcome') is True:
            call.vars['play_welcome'] = False
            log.info("'{}': Got HANGUP while playing" . format(sess.uuid))


# Make an outbound call
# This function will be called by originator for each call
# User is supposed to provide the outbound DID or SIP URL for each call
#
# SIP Call
#   dest_url='did@domain.com'   #Remote SIP URI
#   dest_profile='internal'     #NSG defined SIP profile name
#   dest_endpoint='sofia'       #For SIP calls one MUST set sofia
#
# FreeTDM Call
#   dest_url='[A,a]/did'        #A=ascending hunt, a=descending hunt, DID number
#   dest_profile='g1'           #profile is used as trunk group definition: g1 == group 1
#   endpoint='freetdm"          #For TDM calls on MUST set freetdm
#
# In this example we are making a FreeTDM Call.
# Change True to False in order to make SIP calls.
def create_url():
    if True:
        # Make a FreeTDM SS7/PRI Call
        # Adding F at the end of the DID disables remote SS7 overlap dialing which can add 5 sec to the incoming call setup time
        # Note: Developer is suppose to supply their own DID. From a list or a DB
        return {'dest_url': 'a/1000F', 'dest_profile': 'g1', 'dest_endpoint': 'freetdm'}
    else:

        # Make a SIP Call
        # Uncoming in order to use it.
        return {'dest_url': '4113@10.10.12.5:6060', 'dest_profile': 'internal', 'dest_endpoint': 'sofia'}


# Create an originator
# Originator is a dialer
# You can tell it how many calls to make and at what frequency
# After the first batch of calls are complete, you can choose to start dialing again.
# There are 3 configurable variables
#    max_calls_per_campaign
#    max_call_attempts_per_sec
#    max_campaigns
# In my example the Dialer will dial out 2 calls as par to first campaign.
# By increasing the max_campaigns, dialer will repeat as many dial campings.

max_calls_per_campaign = 1
max_call_attempts_per_sec = 1
max_campaigns = 1

originator = get_originator([(host, port)], apps=(IVRCallLogic,), auto_duration=False, rep_fields_func=create_url)

# Use place holders in order for switch to trigger create_url() function above
# TODO: Should be hidden in switchy
#       Should iterate over all clients
originator.pool.clients[0].set_orig_cmd(
    dest_url='{dest_url}',
    profile='{dest_profile}',
    endpoint='{dest_endpoint}',
    app_name='park',
)


# Setup calls per sec
originator.rate = max_call_attempts_per_sec

# Setup maximum number of calls to make
originator.limit = max_calls_per_campaign

# Maximum number of calls to dial out
originator.max_offered = max_calls_per_campaign

# Start the initial campaign
# Originator will start making outbound calls
originator.start()

# Keeps a count of campaigns
campaign_cnt = 0

# Example of how to keep an eye on the campaign
# After the campaign is over, check to see if another
# campaign should start
while (True):

    log.info("Originator Stopped='{}' State='{}' Call Count='{}'\n" .  format(originator.stopped(), originator.state, originator.count_calls()))

    if originator.state == "STOPPED" and originator.count_calls() == 0:

        # Check to see if we should run another camapign
        campaign_cnt += 1
        if campaign_cnt >= max_campaigns:
            break

        log.info("Starting new campaign\n")

        # We must increase the max allowed calls in order
        # for dialer to initiate another max_calls_per_campaign
        originator.max_offered += max_calls_per_campaign
        originator.start()

    time.sleep(1)

log.info("All campaigns done: stopping...\n")

originator.shutdown()
