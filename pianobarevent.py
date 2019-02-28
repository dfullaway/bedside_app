#!/usr/bin/env python

"""
Adopted from:
Last.fm scrobbling for Pianobar, the command-line Pandora client.
Copyright (c) 2011
Jon Pierce <jon@jonpierce.com>
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
Dependencies:
1) https://github.com/PromyLOPh/pianobar/
2) http://python.org/

Installation:
1) Copy this script to the Pianobar config directory, ~/.config/pianobar/, and make sure this script is executable
3) Update Pianobar's config file to use this script as its event_command
"""

import sys
import socket
import pickle

def main():

    event = sys.argv[1]
    lines = sys.stdin.readlines()
    fields = dict([line.strip().split("=", 1) for line in lines])

    # fields: title, artist, album, songDuration, songPlayed, rating, stationName, pRet, pRetStr, wRet, wRetStr, rating
    # Add event to dictionary

    # events: songstart, songfinish, songlove, songshelf, songban, songbookmark, artistbookmark

    fields["event"] = event

    #Pickle the dictionary

    pickled_fields = pickle.dumps(fields)

    HOST = 'localhost'
    PORT = 50007
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        s.sendall(pickled_fields)



if __name__ == "__main__":
    main()
