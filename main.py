import random
import os
import sys

from pathlib import Path

from pydub import AudioSegment
from pydub.silence import split_on_silence, detect_silence

root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(root)
os.chdir(root)

from anim import TALK_FRAMES, SILENT_FRAME, ANIM_ONE_FRAMES, OPEN_MOUTH_FRAME, TALK_FRAMES_CHUNKS

FPS = 30
MIN_SILENCE_LEN = 600
SILENCE_THRESH = -30
TALK_EXTRA = 0.5

TALK_FRAMES_COUNT = len(TALK_FRAMES)

SILENCE = 1
TALK = 2

MAX_INLINE_FRAME = 32


class Segment(object):
    def __init__(self, kind, duration=None, voice=None, is_first=False, talk_data=None):
        self.kind = kind
        self.duration = duration  # second!
        self.voice = voice
        self.next_segment = None
        self.is_first = is_first
        self.talk_data = talk_data

        if self.is_silence():
            if not self.duration:
                raise Exception('duration is mandatory for silence')
        elif self.is_talk():
            if not self.voice:
                raise Exception('voice is mandatory for talk')
            if not self.talk_data:
                raise Exception('talk data is mandatory for talk')
            self.duration = voice.duration_seconds

    def is_silence(self):
        return self.kind == SILENCE

    def is_talk(self):
        return self.kind == TALK

    def get_duration(self):
        duration = self.duration

        if self.next_segment:
            if self.is_silence():
                if not self.is_first:
                    have_enough_silence = self.duration > TALK_EXTRA
                    if have_enough_silence:
                        duration -= TALK_EXTRA

            if self.is_talk():
                have_enough_silence = self.next_segment.duration > TALK_EXTRA
                if have_enough_silence:
                    duration += TALK_EXTRA
        #
        # print('----')
        # print(self.duration)
        # print(duration)
        # print(self.kind)

        return duration

    def get_frames_count(self):
        float_frames = self.get_duration() * FPS
        # print('xxx')
        # print(float_frames)
        # print(round(float_frames))
        # print(int(round(float_frames)))
        return int(round(float_frames))

    def get_frames(self):
        count = self.get_frames_count()
        frames = []
        if self.is_silence():
            for _ in range(0, count):
                frames.append(SILENT_FRAME)
        elif self.is_talk():
            talk_chunk = self.talk_data
            while len(talk_chunk) < count:
                talk_chunk.extend(self.talk_data)

            talk_chunk = talk_chunk[:count]

            frames.extend(talk_chunk)

            # # V1 - use line from haystack
            #
            # start_frame = random.randint(0, TALK_FRAMES_COUNT)
            # while len(frames) < count:
            #     for item in TALK_FRAMES[start_frame:]:
            #         if len(frames) == count:
            #             break
            #         frames.append(item)
            #     start_frame = 0

            # # V2 - use fixed
            #
            # for _ in range(0, count):
            #     frames.append(OPEN_MOUTH_FRAME)

        return frames

    def set_next_segment(self, segment):
        self.next_segment = segment


class Manager(object):
    def __init__(self, silence_is_first):
        self.silence_is_first = silence_is_first
        self.silences = []
        self.talks = []
        self.segments = []
        self.last_talk_chunk = len(TALK_FRAMES_CHUNKS) - 1
        self.current_chunk = 0

    def get_next_talk_chunk(self):
        talk_chunk = TALK_FRAMES_CHUNKS[self.current_chunk]
        self.current_chunk += 1
        if self.current_chunk >= self.last_talk_chunk:
            self.current_chunk = 0

        return talk_chunk

    def add_talk(self, chunk, i):
        is_first = (self.silence_is_first is False and i == 0)
        self.talks.append(
            Segment(TALK, voice=chunk, is_first=is_first, talk_data=self.get_next_talk_chunk())
        )

    def add_silence(self, duration, i):
        is_first = (self.silence_is_first is True and i == 0)
        self.silences.append(
            Segment(SILENCE, duration=duration, is_first=is_first)
        )

    def parse_no_silence_chunks(self, no_silence_chunks):
        i = 0
        for chunk in no_silence_chunks:
            self.add_talk(chunk, i)
            i += 1

    def parse_silence_list(self, raw_silence_list):
        i = 0
        for start, stop in raw_silence_list:
            duration = (stop - start) / 1000
            self.add_silence(duration, i)
            i += 1

    def get_segments(self):
        turn_silence = self.silence_is_first
        have_silence = len(self.silences) > 0
        have_talks = len(self.talks) > 0
        next_silence_id = 0
        next_talk_id = 0

        segments = []

        while have_silence or have_talks:
            if turn_silence:
                turn_silence = False

                try:
                    segments.append(self.silences[next_silence_id])
                    next_silence_id += 1
                except IndexError:
                    have_silence = False
            else:
                turn_silence = True

                try:
                    segments.append(self.talks[next_talk_id])
                    next_talk_id += 1
                except IndexError:
                    have_talks = False

        return segments

    def load_segments(self):
        self.segments = self.get_segments()
        i = 0
        for segment in self.segments:
            try:
                segment.set_next_segment(self.segments[i+1])
            except IndexError:
                pass
            i += 1

    def get_total_duration(self):
        return sum([i.diration for i in self.segments])

    def get_frames(self):
        frames = []
        for segment in self.segments:
            frames.extend(segment.get_frames())
        return frames

    def get_frames_formatted(self):
        frames_str = ''

        for segment in self.segments:
            seg_frames = segment.get_frames()
            insert_list = []
            j = 1
            for frame in seg_frames:
                insert_list.append(str(frame))
                j += 1
                if j > MAX_INLINE_FRAME:
                    frames_str += ','.join(insert_list) + ',\n'
                    insert_list = []
                    j = 1
            if len(insert_list) > 0:
                frames_str += ','.join(insert_list) + ',\n'
        return frames_str


song = AudioSegment.from_ogg('rams.ogg')
awaited_frames = len(ANIM_ONE_FRAMES)

chunks = split_on_silence(song, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESH, keep_silence=False)
silence_list = detect_silence(song, min_silence_len=MIN_SILENCE_LEN, silence_thresh=SILENCE_THRESH)

manager = Manager(silence_is_first=silence_list[0][0] == 0)
manager.parse_no_silence_chunks(chunks)
manager.parse_silence_list(silence_list)
manager.load_segments()

frames = manager.get_frames()

inline_frames = ''
j = 1
for frame in frames:
    inline_frames += f'{frame},'
    j += 1
    if j > MAX_INLINE_FRAME:
        inline_frames += '\n'
        j = 1

i = 0
for chunk in chunks:
    chunk.export(f'chunk/{i}.mp3')
    i += 1

out_file = Path().resolve() / 'out.txt'
out_file.write_text(manager.get_frames_formatted())

print('Original frames: %d' % awaited_frames)
print('Generated frames in out.txt: %d' % len(frames))


# import pdb;pdb.set_trace()