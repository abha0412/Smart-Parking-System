"""
SMART PARKING SYSTEM - GUIDED ANIMATED SIMULATION
Operating Systems Case Study 3

WHAT THIS PROGRAM SHOWS
  A parking lot with 5 spaces and 8 cars. Cars compete for spaces the same way
  programs in a computer compete for memory, files or a printer. The operating
  system (OS) must share these resources safely. Each button shows one idea:

  Start Here          - what every picture on the screen means
  1. Normal Parking   - every car is a real OS PROCESS
  2. Race Condition   - THREADS change shared data with no protection -> wrong result
  3. Mutex Lock       - the same thing, protected by a lock -> correct result
  4. Semaphore        - a "ticket machine" with 5 tickets limits the lot to 5 cars
  5A. Deadlock        - two cars wait for each other forever
  5B. Prevention      - one simple rule stops the deadlock

HOW TO RUN (Windows):   py -3 smart_parking_gui.py
Only Python's built-in libraries are used (tkinter comes with Python).

HOW THIS FILE IS ORGANISED
  PART 1  Settings and the message queue
  PART 2  The Operating System logic - one function per scenario
          (this is the important part for the OS case study)
  PART 3  The window: drawing cars, slots, the graph and the explanations
"""

import multiprocessing
import threading
import queue
import time
import os
import math
import tkinter as tk

# ==================================================================
# PART 1 : SETTINGS AND THE MESSAGE QUEUE
# ==================================================================
TOTAL_SLOTS = 5          # parking capacity
NUM_VEHICLES = 8         # vehicles V1 .. V8
ARRIVAL_GAP = 1.0        # a new car arrives every 1 second

# Fixed parking time (seconds) for each car, so every run looks the same
PARK_TIME = {1: 9, 2: 7, 3: 9, 4: 7, 5: 8, 6: 3.5, 7: 3, 8: 3}

# tkinter is NOT thread-safe: only the main thread may draw on the screen.
# So the car threads never draw anything. They put short messages
# ("events") into this queue, and the main thread reads the queue every
# 50 ms and updates the picture.
events = queue.Queue()


def send(*event):
    events.put(event)


def find_free_slot(slots):
    # Return the index of the first free slot (0 means free), or -1 if none
    for i in range(TOTAL_SLOTS):
        if slots[i] == 0:
            return i
    return -1


# ==================================================================
# PART 2 : THE OPERATING SYSTEM LOGIC
# ==================================================================

# ---------------- Scenario 1 : every car is a separate PROCESS ----------------
# Separate processes do NOT share normal variables, so we use multiprocessing
# shared memory (Value, Array) and a multiprocessing Lock / Semaphore.
# Messages go back to the window through a SimpleQueue.

def vehicle_process(vid, parking_sem, slot_lock, slots, available, peak, msg_queue):
    pid = os.getpid()
    msg_queue.put(("arrive", vid, f"V{vid}\nPID {pid}"))
    msg_queue.put(("log", f"V{vid} arrives. The OS creates a new process for it (PID {pid}).", "black"))

    # Try to get a parking permit WITHOUT waiting (block=False)
    if not parking_sem.acquire(block=False):
        msg_queue.put(("wait", vid))
        msg_queue.put(("log", f"V{vid} finds the lot FULL. Its process is BLOCKED (paused) until a space frees up.", "orange"))
        parking_sem.acquire()                      # now wait for a permit

    with slot_lock:                                # critical section: take a slot
        slot = find_free_slot(slots)
        slots[slot] = vid
        available.value -= 1
        peak.value = max(peak.value, TOTAL_SLOTS - available.value)
        msg_queue.put(("park", vid, slot, available.value))
        msg_queue.put(("log", f"V{vid} parks in Slot {slot + 1}. Free slots left: {available.value}.", "green"))

    time.sleep(PARK_TIME[vid])                     # the car stays parked

    with slot_lock:                                # critical section: free the slot
        slots[slot] = 0
        available.value += 1
        msg_queue.put(("leave", vid, slot, available.value))
        msg_queue.put(("log", f"V{vid} leaves Slot {slot + 1}. Free slots now: {available.value}.", "blue"))

    parking_sem.release()                          # permit back: one waiting car may enter


def forward_messages(msg_queue, seconds):
    # Pass messages from the car processes to the window for some seconds
    end_time = time.time() + seconds
    while time.time() < end_time:
        while not msg_queue.empty():
            events.put(msg_queue.get())
        time.sleep(0.05)


def run_scenario_1():
    available = multiprocessing.Value("i", TOTAL_SLOTS)    # shared "free slots" counter
    slots = multiprocessing.Array("i", TOTAL_SLOTS)         # shared slot table (0 = free)
    peak = multiprocessing.Value("i", 0)                    # most cars ever inside at once
    parking_sem = multiprocessing.Semaphore(TOTAL_SLOTS)    # 5 parking permits
    slot_lock = multiprocessing.Lock()                      # protects the slot table
    msg_queue = multiprocessing.SimpleQueue()               # messages back to the window

    send("log", f"The Parking Manager program is running as process PID {os.getpid()}.", "purple")
    processes = []
    for vid in range(1, NUM_VEHICLES + 1):
        p = multiprocessing.Process(
            target=vehicle_process,
            args=(vid, parking_sem, slot_lock, slots, available, peak, msg_queue))
        p.daemon = True
        p.start()                                  # the OS creates a new process here
        processes.append(p)
        forward_messages(msg_queue, ARRIVAL_GAP)

    while any(p.is_alive() for p in processes):    # wait until every car has left
        forward_messages(msg_queue, 0.2)
    forward_messages(msg_queue, 0.3)

    ok = peak.value <= TOTAL_SLOTS and available.value == TOTAL_SLOTS
    send("log", f"CHECK: at most {peak.value} cars were ever inside, and all {available.value} "
                f"slots are free at the end -> {'PASS' if ok else 'FAIL'}", "purple")
    send("result", "DONE: 8 separate processes shared\n5 slots correctly. Cars that found\n"
                   "the lot full waited, then entered.", "green")
    send("done")


# ---------------- Scenario 2 : RACE CONDITION (no lock) ----------------
# Threads live inside ONE process and share its memory, so all of them
# change the same 'parking' dictionary. Nothing stops them doing it at once.

def race_vehicle(vid, parking):
    send("arrive", vid, f"V{vid}")
    time.sleep(1.5)                                # all 5 cars reach the gate together

    count = parking["available"]                   # 1. READ the shared counter
    slot = find_free_slot(parking["slots"])        #    and look for a free slot
    send("row", vid, 1, f"{count} free")
    send("log", f"V{vid} reads the board: '{count} free'. It picks Slot {slot + 1}.", "orange")

    time.sleep(1.0)                                # 2. pause: the other cars read the SAME old value

    parking["slots"][slot] = vid                   # 3. WRITE, based on the old value
    parking["available"] = count - 1
    send("park", vid, slot, parking["available"])
    send("row", vid, 2, f"{count - 1} free")
    send("row", vid, 3, f"Slot {slot + 1}")
    send("log", f"V{vid} writes '{count - 1} free' on the board and parks in Slot {slot + 1}.", "red")


def run_scenario_2():
    parking = {"available": TOTAL_SLOTS, "slots": [0] * TOTAL_SLOTS}
    threads = []
    for vid in range(1, 6):
        t = threading.Thread(target=race_vehicle, args=(vid, parking))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    send("log", f"RACE CONDITION SHOWN: the board should say 0 free but says {parking['available']}. "
                "This mistake is expected without a lock - see Scenario 3 for the fix.", "red")
    send("result", f"RACE CONDITION!\nThe board says {parking['available']} free, but 5 cars\n"
                   "are piled into Slot 1. Every car read\nthe OLD value before anyone wrote.", "red")
    send("done")


# ---------------- Scenario 3 : MUTEX LOCK ----------------

def mutex_vehicle(vid, parking, lock):
    send("arrive", vid, f"V{vid}")
    time.sleep(1.5)
    send("log", f"V{vid} wants to update the board, so it asks for the lock (the key).", "black")

    with lock:                                     # only ONE thread at a time gets past this line
        send("mutex", vid)
        count = parking["available"]
        slot = find_free_slot(parking["slots"])
        send("row", vid, 1, f"{count} free")
        send("log", f"V{vid} has the key. It reads '{count} free' and picks Slot {slot + 1}. Others must wait.", "orange")
        time.sleep(1.0)                            # same pause as Scenario 2
        parking["slots"][slot] = vid
        parking["available"] = count - 1
        send("park", vid, slot, parking["available"])
        send("row", vid, 2, f"{count - 1} free")
        send("row", vid, 3, f"Slot {slot + 1}")
        send("log", f"V{vid} writes '{count - 1} free', parks in Slot {slot + 1} and gives the key back.", "green")
        send("mutex", 0)


def run_scenario_3():
    parking = {"available": TOTAL_SLOTS, "slots": [0] * TOTAL_SLOTS}
    lock = threading.Lock()                        # the mutex
    threads = []
    for vid in range(1, 6):
        t = threading.Thread(target=mutex_vehicle, args=(vid, parking, lock))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    used = [s for s in parking["slots"] if s != 0]
    ok = parking["available"] == 0 and len(set(used)) == 5
    send("log", f"CHECK: the board says {parking['available']} free (correct is 0) and every car "
                f"has its own slot -> {'PASS' if ok else 'FAIL'}", "purple")
    send("result", "CORRECT!\nThe lock let only one car at a\ntime read and change the board.\n"
                   "Board = 0 free, 5 different slots.", "green")
    send("done")


# ---------------- Scenario 4 : SEMAPHORE ----------------
# Semaphore(5) = 5 permits ("tickets") -> controls HOW MANY cars are inside.
# Lock         = 1 key                 -> controls WHO changes the slot table.

def semaphore_vehicle(vid, parking, parking_sem, lock):
    send("arrive", vid, f"V{vid}")
    send("log", f"V{vid} arrives and asks the ticket machine for a ticket (permit).", "black")

    if not parking_sem.acquire(blocking=False):    # try once without waiting
        send("wait", vid)
        send("log", f"No tickets left - all 5 are in use. V{vid} must WAIT.", "orange")
        parking_sem.acquire()                      # wait for a ticket

    with lock:                                     # critical section: take a slot
        slot = find_free_slot(parking["slots"])
        parking["slots"][slot] = vid
        parking["available"] -= 1
        parking["peak"] = max(parking["peak"], TOTAL_SLOTS - parking["available"])
        send("park", vid, slot, parking["available"])
        send("log", f"V{vid} got a ticket and parks in Slot {slot + 1}. Tickets left: {parking['available']}.", "green")

    time.sleep(PARK_TIME[vid])

    with lock:                                     # critical section: free the slot
        parking["slots"][slot] = 0
        parking["available"] += 1
        send("leave", vid, slot, parking["available"])
        send("log", f"V{vid} leaves Slot {slot + 1} and returns its ticket. Tickets left: {parking['available']}.", "blue")

    parking_sem.release()                          # wakes up one waiting car


def run_scenario_4():
    parking = {"available": TOTAL_SLOTS, "slots": [0] * TOTAL_SLOTS, "peak": 0}
    parking_sem = threading.Semaphore(TOTAL_SLOTS)
    lock = threading.Lock()
    threads = []
    for vid in range(1, NUM_VEHICLES + 1):
        t = threading.Thread(target=semaphore_vehicle, args=(vid, parking, parking_sem, lock))
        threads.append(t)
        t.start()
        time.sleep(ARRIVAL_GAP)
    for t in threads:
        t.join()

    ok = parking["peak"] <= TOTAL_SLOTS and parking["available"] == TOTAL_SLOTS
    send("log", f"CHECK: at most {parking['peak']} cars were ever inside, and all tickets are back "
                f"-> {'PASS' if ok else 'FAIL'}", "purple")
    send("result", "DONE: the semaphore never let more\nthan 5 cars in. Each car that left\n"
                   "returned a ticket for a waiting car.", "green")
    send("done")


# ---------------- Scenario 5 : DEADLOCK and PREVENTION ----------------
# Two resources that only ONE car can use at a time: the Entry Gate and a
# single-lane Ramp. Each one is a threading.Lock().

def two_resource_vehicle(name, first, first_name, second, second_name):
    send("rag", "request", name, first_name)
    send("log", f"{name} asks for the {first_name}.", "black")
    with first:
        send("rag", "hold", name, first_name)
        send("log", f"{name} now HAS the {first_name}.", "green")
        time.sleep(1.5)                            # the other car takes its first resource meanwhile

        send("rag", "request", name, second_name)
        send("log", f"{name} keeps the {first_name} and now ALSO wants the {second_name}.", "orange")
        with second:
            send("rag", "hold", name, second_name)
            send("log", f"{name} has BOTH the Gate and the Ramp, so it can drive through.", "green")
            time.sleep(1.5)
            send("rag", "release", name, second_name)
        send("rag", "release", name, first_name)
    send("log", f"{name} is through and gives back both. Finished.", "blue")


def run_scenario_5a():
    gate = threading.Lock()
    ramp = threading.Lock()
    # V1 is coming IN:  Gate first, then Ramp.
    # V2 is going OUT:  Ramp first, then Gate.   <- opposite order
    v1 = threading.Thread(target=two_resource_vehicle,
                          args=("V1", gate, "Entry Gate", ramp, "Ramp"), daemon=True)
    v2 = threading.Thread(target=two_resource_vehicle,
                          args=("V2", ramp, "Ramp", gate, "Entry Gate"), daemon=True)
    v1.start()
    v2.start()

    time.sleep(5)                                  # watchdog: give them 5 seconds

    if v1.is_alive() and v2.is_alive():
        send("deadlock")
        send("log", "1. Mutual Exclusion: the Gate and the Ramp can each be used by only one car.", "purple")
        send("log", "2. Hold and Wait: each car keeps what it has while waiting for more.", "purple")
        send("log", "3. No Preemption: nobody can take the Gate or Ramp away from a car.", "purple")
        send("log", "4. Circular Wait: V1 waits for V2, and V2 waits for V1 (the red loop).", "purple")
        send("log", "Nobody can move: V1 waits for V2 and V2 waits for V1 forever. This is a DEADLOCK.", "red")
        send("result", "DEADLOCK!\nThe arrows form a closed loop:\nGate > V1 > Ramp > V2 > Gate", "red")
    else:
        send("result", "No deadlock this time", "green")
    send("done")


def run_scenario_5b():
    gate = threading.Lock()
    ramp = threading.Lock()
    send("log", "NEW RULE: every car must take the Entry Gate FIRST, then the Ramp.", "purple")
    # Both cars now use the SAME order, so a closed loop cannot form
    v1 = threading.Thread(target=two_resource_vehicle,
                          args=("V1", gate, "Entry Gate", ramp, "Ramp"))
    v2 = threading.Thread(target=two_resource_vehicle,
                          args=("V2", gate, "Entry Gate", ramp, "Ramp"))
    v1.start()
    time.sleep(0.3)
    v2.start()
    v1.join()
    v2.join()

    send("log", "CHECK: both cars finished -> PASS. The rule prevented the deadlock.", "purple")
    send("result", "NO DEADLOCK\nSame order for every car,\nso no loop can form.", "green")
    send("done")




# ==================================================================
# PART 3 : THE WINDOW (everything below only draws; it runs in the main thread)
# ==================================================================
CANVAS_W, CANVAS_H = 920, 400
LANE_Y = 160                 # y position of the arrival lane and the slots
GATE_X = 320                 # x position of the entry gate
EXIT_Y = 65                  # y position of the exit lane
CAR_SPEED = 14               # pixels moved per animation frame

# Colour theme: light page, grey asphalt, white parking lines
PAGE = "#f4f6f8"             # window background
GROUND = "#e3e8e4"           # canvas background (light concrete)
ASPHALT = "#6b7177"          # roads and parking area
LINE = "#ffffff"             # white road and parking lines
DARK = "#263238"             # main text colour
GREEN = "#2e7d32"
BLUE = "#1565c0"
ORANGE = "#e65100"
RED = "#c62828"
PURPLE = "#6a1b9a"
HIGHLIGHT = "#ff6d00"        # outline of the car that holds the lock

# Car colours: blue, green, yellow, red, pink, orange, purple, silver
CAR_COLORS = ["#1e88e5", "#43a047", "#fdd835", "#e53935",
              "#ec407a", "#fb8c00", "#8e24aa", "#b0bec5"]
CAR_TEXT = ["white", "white", DARK, "white", "white", DARK, "white", DARK]

# Positions of the circles and squares in the deadlock graph
RAG_NODES = {"V1": (460, 100), "V2": (460, 318),
             "Entry Gate": (230, 209), "Ramp": (690, 209)}

# Plain-English explanation shown above the picture for each button
INTRO = {
    "title": "SMART PARKING SYSTEM  -  Operating Systems made visible",
    "story": "Click a button above to start. Each button is a short animation of cars using a "
             "parking lot that has only 5 spaces.",
    "concept": "A computer has limited resources and many programs that want them at the same time. "
               "The operating system must share them safely. The parking lot shows the same problem.",
    "watch": "Go left to right: 1, 2, 3, 4, 5A, 5B. The NOW line under the picture explains "
             "every step as it happens.",
}

SCENARIOS = {
    "1": {
        "button": "1. Normal Parking", "color": "#bbdefb", "run": run_scenario_1,
        "title": "1. NORMAL PARKING  -  every car is a separate PROCESS",
        "story": "8 cars arrive one by one. The first 5 park. Cars 6, 7 and 8 find the lot full and "
                 "wait. Each time a car leaves, one waiting car drives in.",
        "concept": "Each car is a PROCESS: a task the operating system starts on its own, with its own "
                   "ID number (PID). A process that has to wait is BLOCKED until the OS wakes it up.",
        "watch": "The PID number under each car, the WAITING AREA, and the free-slot counter "
                 "(top-left) going 5 -> 0 -> back to 5.",
        "mode": "lot", "mutex": "LOCK: guards the slot list", "permits": True, "table": False},
    "2": {
        "button": "2. Race Condition", "color": "#ffcdd2", "run": run_scenario_2,
        "title": "2. RACE CONDITION  -  5 threads change shared data with NO protection",
        "story": "5 cars arrive at the SAME moment. Each one reads the 'free slots' board, sees 5, "
                 "picks Slot 1, and only later writes the new number. Nobody stops them doing it together.",
        "concept": "When several THREADS change the same shared data at the same time, updates get lost "
                   "and the data becomes wrong. This is a RACE CONDITION. The read-and-change step is "
                   "the CRITICAL SECTION.",
        "watch": "The table: every car READ '5 free' and WROTE '4 free'. The board ends at 4 (should be 0) "
                 "and all 5 cars are piled into Slot 1.",
        "mode": "lot", "mutex": "LOCK: NOT USED", "permits": False, "table": True},
    "3": {
        "button": "3. Mutex Lock", "color": "#fff9c4", "run": run_scenario_3,
        "title": "3. MUTEX LOCK  -  the same 5 cars, but now with one key",
        "story": "Same 5 cars, same moment. Now there is ONE key (the lock). Only the car holding the "
                 "key may read and change the board. The others wait for their turn.",
        "concept": "A MUTEX LOCK (threading.Lock) lets only ONE thread into the critical section at a "
                   "time. This removes the race condition.",
        "watch": "The thick orange outline shows who has the key. In the table each car now reads the "
                 "updated value: 5, 4, 3, 2, 1. The board ends at 0 and every car has its own slot.",
        "mode": "lot", "mutex": "LOCK: FREE", "permits": False, "table": True},
    "4": {
        "button": "4. Semaphore", "color": "#c8e6c9", "run": run_scenario_4,
        "title": "4. SEMAPHORE  -  a ticket machine with 5 tickets",
        "story": "8 cars again. A car needs a ticket to enter and gives it back when it leaves. "
                 "When no tickets are left, arriving cars wait.",
        "concept": "A SEMAPHORE (threading.Semaphore(5)) counts permits. It limits HOW MANY threads may "
                   "use a resource at once. A mutex is like a semaphore with only 1 permit.",
        "watch": "The 5 green ticket lights (top-right). When all are grey, cars wait. When a car leaves, "
                 "a light turns green and a waiting car moves in.",
        "mode": "lot", "mutex": "LOCK: guards the slot list", "permits": True, "table": False},
    "5A": {
        "button": "5A. Deadlock", "color": "#f8bbd0", "run": run_scenario_5a,
        "title": "5A. DEADLOCK  -  two cars wait for each other forever",
        "story": "There is one Entry Gate and one single-lane Ramp. V1 (coming in) takes the Gate and then "
                 "needs the Ramp. V2 (going out) takes the Ramp and then needs the Gate. Both wait... forever.",
        "concept": "DEADLOCK: tasks wait for each other in a circle, so none can continue. It needs 4 "
                   "conditions together: Mutual Exclusion, Hold and Wait, No Preemption, Circular Wait.",
        "watch": "The diagram. Solid green arrow = 'this car HAS it'. Dashed orange arrow = 'this car WANTS it'. "
                 "When the arrows form a closed loop, it turns red.",
        "mode": "rag", "mutex": "", "permits": False, "table": False},
    "5B": {
        "button": "5B. Prevention", "color": "#e1bee7", "run": run_scenario_5b,
        "title": "5B. DEADLOCK PREVENTION  -  one simple rule",
        "story": "Same two cars, one new rule: EVERY car must take the Entry Gate first, then the Ramp. "
                 "V2 now waits at the Gate while V1 finishes, then V2 goes.",
        "concept": "If everyone asks for resources in the SAME ORDER, a circle of waiting can never form. "
                   "This breaks the Circular Wait condition, so deadlock is impossible.",
        "watch": "V2's dashed arrow waits at the Entry Gate. No loop forms and both cars finish.",
        "mode": "rag", "mutex": "", "permits": False, "table": False},
}

# Things the drawing functions need to remember
window = None
canvas = None
log_box = None
now_label = None
story_labels = {}
title_label = None
buttons = []
cars = {}                                  # vid -> car drawing information
waiting = []                               # cars in the waiting area
slot_cars = [[] for _ in range(TOTAL_SLOTS)]
items = {}                                 # ids of status drawings on the canvas
rag_edges = {}                             # (vehicle, resource) -> arrow drawing
counter_value = TOTAL_SLOTS
mutex_holder = 0
mode = "intro"
scenario_start = time.time()


def slot_x(i):
    return 400 + i * 105


def arrival_x(vid):
    return 35 + ((vid - 1) % 5) * 58


def waiting_pos(k):
    return (65 + (k % 4) * 66, 295 + (k // 4) * 55)


def label(x, y, text, color=DARK, size=10, bold=True, **options):
    weight = "bold" if bold else "normal"
    return canvas.create_text(x, y, text=text, fill=color, font=("Arial", size, weight), **options)


# ---------------- drawing a car ----------------
def draw_car(x, y, vid, text, tag):
    # Side view of a car facing right. All parts share one tag, so the
    # whole car can be moved or deleted with a single command.
    color = CAR_COLORS[(vid - 1) % len(CAR_COLORS)]
    text_color = CAR_TEXT[(vid - 1) % len(CAR_TEXT)]
    canvas.create_oval(x - 29, y + 10, x + 29, y + 20, fill="#4a4f54", outline="", tags=tag)     # shadow
    body = canvas.create_polygon(
        x - 28, y + 9, x - 28, y - 2, x - 19, y - 6, x - 12, y - 16,
        x + 10, y - 16, x + 17, y - 6, x + 27, y - 3, x + 28, y + 9,
        fill=color, outline=DARK, width=1, smooth=True, tags=tag)
    canvas.create_polygon(x - 10, y - 6, x - 8, y - 13, x - 1, y - 13, x - 1, y - 6,
                          fill="#cfe8fc", outline="", tags=tag)                     # rear window
    canvas.create_polygon(x + 2, y - 6, x + 2, y - 13, x + 8, y - 13, x + 13, y - 6,
                          fill="#cfe8fc", outline="", tags=tag)                     # front window
    for wx in (x - 16, x + 16):                                                     # wheels
        canvas.create_oval(wx - 7, y + 3, wx + 7, y + 17, fill="#212121", outline="#212121", tags=tag)
        canvas.create_oval(wx - 3, y + 7, wx + 3, y + 13, fill="#bdbdbd", outline="", tags=tag)
    canvas.create_oval(x + 23, y - 2, x + 29, y + 3, fill="#fff59d", outline="", tags=tag)   # headlight
    canvas.create_oval(x - 29, y - 1, x - 25, y + 3, fill="#b71c1c", outline="", tags=tag)   # tail light
    lines = text.split("\n")
    canvas.create_text(x, y + 2, text=lines[0], fill=text_color, font=("Arial", 9, "bold"), tags=tag)
    if len(lines) > 1:                                                              # PID under the car
        canvas.create_text(x, y + 27, text=lines[1], fill="white", font=("Arial", 8, "bold"), tags=tag)
    return body


# ---------------- the Start Here screen ----------------
def draw_intro():
    canvas.delete("all")
    label(CANVAS_W // 2, 26, "WHAT DOES EACH PICTURE MEAN?", BLUE, 16)
    rows_y = [80, 135, 190, 245, 300]

    # 1. a car
    canvas.create_rectangle(70, rows_y[0] - 24, 150, rows_y[0] + 24, fill=ASPHALT, outline="")
    draw_car(110, rows_y[0], 1, "V1", "intro")
    # 2. a parking slot
    canvas.create_rectangle(70, rows_y[1] - 24, 150, rows_y[1] + 24, fill=ASPHALT, outline="")
    canvas.create_rectangle(80, rows_y[1] - 18, 140, rows_y[1] + 18, outline=LINE, width=3)
    label(110, rows_y[1], "P", LINE, 16)
    # 3. the free-slot board
    canvas.create_rectangle(70, rows_y[2] - 16, 150, rows_y[2] + 16, fill="white", outline=GREEN, width=2)
    label(110, rows_y[2], "Free: 5", GREEN, 12)
    # 4. the waiting area
    canvas.create_rectangle(70, rows_y[3] - 20, 150, rows_y[3] + 20, fill=ASPHALT, outline=ORANGE,
                            width=3, dash=(6, 4))
    label(110, rows_y[3], "WAIT", "white", 11)
    # 5. the gate (red and white barrier)
    canvas.create_line(95, rows_y[4] - 22, 95, rows_y[4] + 22, width=8, fill=RED)
    canvas.create_line(95, rows_y[4] - 22, 95, rows_y[4] + 22, width=8, fill="white", dash=(6, 6))
    label(130, rows_y[4], "GATE", RED, 10)

    meanings = [
        ("Car", "=  a running task: a PROCESS or a THREAD"),
        ("Parking slot", "=  a SHARED RESOURCE (only one car may use it)"),
        ("Free-slots board", "=  a SHARED VARIABLE that every task reads and changes"),
        ("Waiting area", "=  the BLOCKED state: the OS pauses a task until it can continue"),
        ("Gate and Ramp", "=  resources only one car can hold at a time (used for Deadlock)"),
    ]
    for i in range(5):
        label(200, rows_y[i], meanings[i][0], BLUE, 12, anchor="w")
        label(360, rows_y[i], meanings[i][1], DARK, 12, bold=False, anchor="w")

    label(CANVAS_W // 2, 365, "Click  1. Normal Parking  to begin, then go left to right.", ORANGE, 13)


# ---------------- drawing the parking lot ----------------
def draw_parking_lot(scenario):
    canvas.delete("all")
    items.clear()
    # status texts
    items["counter"] = label(15, 18, "", GREEN, 12, anchor="w")
    items["actual"] = label(15, 42, "", DARK, 11, anchor="w")
    items["mutex_box"] = canvas.create_rectangle(400, 8, 610, 38, fill="#e8f5e9", outline=GREEN, width=2)
    items["mutex_text"] = label(505, 23, scenario["mutex"], GREEN, 10)
    items["permits"] = []
    if scenario["permits"]:
        label(628, 23, "Tickets (permits):", DARK, 10, anchor="w")
        for i in range(TOTAL_SLOTS):
            x = 785 + i * 25
            items["permits"].append(canvas.create_oval(x - 9, 14, x + 9, 32, outline=DARK, width=1))
    # arrival lane: grey road with a white dashed centre line
    canvas.create_rectangle(0, 128, GATE_X, 192, fill=ASPHALT, outline="")
    canvas.create_line(0, LANE_Y + 24, GATE_X, LANE_Y + 24, fill=LINE, dash=(12, 10), width=2)
    label(10, 117, "ARRIVAL LANE", DARK, 9, anchor="w")
    # exit lane
    canvas.create_rectangle(350, EXIT_Y - 22, CANVAS_W, EXIT_Y + 22, fill=ASPHALT, outline="")
    label(CANVAS_W - 12, EXIT_Y, "EXIT  >>", "white", 10, anchor="e")
    # parking area: grey asphalt with white bay lines and slot numbers
    canvas.create_rectangle(340, 98, CANVAS_W - 10, 222, fill=ASPHALT, outline="")
    items["slots"] = []
    items["slot_labels"] = []
    for i in range(TOTAL_SLOTS):
        x = slot_x(i)
        label(x, 112, "P", "#8a9096", 12)
        items["slots"].append(canvas.create_rectangle(x - 45, 105, x + 45, 215, outline=LINE, width=3))
        items["slot_labels"].append(label(x, 233, f"Slot {i + 1}", DARK, 10))
    # entry gate (red and white barrier)
    canvas.create_line(GATE_X, 110, GATE_X, 210, width=8, fill=RED)
    canvas.create_line(GATE_X, 110, GATE_X, 210, width=8, fill="white", dash=(8, 8))
    label(GATE_X, 100, "GATE", RED, 10)
    # lower half: either the "what each car did" table, or the waiting area
    if scenario["table"]:
        draw_table()
    else:
        canvas.create_rectangle(20, 250, 300, 392, fill=ASPHALT, outline=ORANGE, width=3, dash=(6, 4))
        label(30, 262, "WAITING AREA (lot full)", "white", 9, anchor="w")
    update_status()


def draw_table():
    # Table showing what every car read from and wrote to the shared board
    canvas.create_rectangle(10, 246, 510, 396, fill="white", outline="#b0bec5")
    label(20, 258, "WHAT EACH CAR DID WITH THE SHARED BOARD", BLUE, 10, anchor="w")
    columns_x = [45, 160, 300, 430]
    headers = ["Car", "1. READ", "2. WROTE", "Got slot"]
    for c in range(4):
        label(columns_x[c], 282, headers[c], DARK, 10)
    canvas.create_line(15, 293, 505, 293, fill="#b0bec5", width=2)
    items["table"] = {}
    for vid in range(1, 6):
        y = 293 + vid * 19
        row = [label(columns_x[0], y, f"V{vid}", DARK, 10)]
        canvas.create_rectangle(columns_x[0] - 30, y - 6, columns_x[0] - 18, y + 6,
                                fill=CAR_COLORS[vid - 1], outline=DARK)        # colour key of the car
        for c in range(1, 4):
            row.append(label(columns_x[c], y, "-", DARK, 10, bold=False))
        items["table"][vid] = row


def update_table(vid, column, text):
    canvas.itemconfig(items["table"][vid][column], text=text, fill=BLUE, font=("Arial", 10, "bold"))


def update_status():
    actual = sum(len(s) for s in slot_cars)
    correct = (counter_value == TOTAL_SLOTS - actual)
    canvas.itemconfig(items["counter"], text=f"Free-slots board says: {counter_value}",
                      fill=GREEN if correct else RED)
    canvas.itemconfig(items["actual"], text=f"Cars really parked: {actual}"
                      + ("" if correct else "   <-- BOARD IS WRONG!"),
                      fill=DARK if correct else RED)
    for i in range(TOTAL_SLOTS):
        if len(slot_cars[i]) > 1:
            canvas.itemconfig(items["slots"][i], outline=RED, width=5)
            canvas.itemconfig(items["slot_labels"][i], text=f"Slot {i + 1}: {len(slot_cars[i])} CARS!", fill=RED)
        else:
            canvas.itemconfig(items["slots"][i], outline=LINE, width=3)
            canvas.itemconfig(items["slot_labels"][i], text=f"Slot {i + 1}", fill=DARK)
    free_permits = TOTAL_SLOTS - actual
    for i in range(len(items["permits"])):
        canvas.itemconfig(items["permits"][i], fill="#43a047" if i < free_permits else "#cfd8dc")


def set_mutex(holder):
    global mutex_holder
    if mutex_holder in cars:                       # remove highlight from the old key holder
        canvas.itemconfig(cars[mutex_holder]["body"], outline=DARK, width=1)
    mutex_holder = holder
    if holder == 0:
        canvas.itemconfig(items["mutex_box"], fill="#e8f5e9", outline=GREEN)
        canvas.itemconfig(items["mutex_text"], text="LOCK: FREE", fill=GREEN)
    else:
        canvas.itemconfig(items["mutex_box"], fill="#ffebee", outline=RED)
        canvas.itemconfig(items["mutex_text"], text=f"LOCK: V{holder} has the key", fill=RED)
        if holder in cars:
            car = cars[holder]
            canvas.itemconfig(car["body"], outline=HIGHLIGHT, width=4)
            car["path"].append((GATE_X + 5, LANE_Y))       # key holder drives up to the gate
            canvas.tag_raise(car["tag"])


# ---------------- moving the cars ----------------
def create_car(vid, text):
    x, y = -40, LANE_Y
    tag = f"car{vid}"
    body = draw_car(x, y, vid, text, tag)
    cars[vid] = {"tag": tag, "body": body, "x": x, "y": y,
                 "path": [(arrival_x(vid), LANE_Y)], "remove": False}


def place_waiting_cars():
    for k in range(len(waiting)):
        car = cars[waiting[k]]
        target = waiting_pos(k)
        if not car["path"] or car["path"][-1] != target:
            car["path"].append(target)


def car_park(vid, slot, available):
    global counter_value
    if vid in waiting:
        waiting.remove(vid)
        place_waiting_cars()
    slot_cars[slot].append(vid)
    k = len(slot_cars[slot]) - 1                   # more than 0 only when cars share a slot (race)
    car = cars[vid]
    car["path"].append((GATE_X + 35, LANE_Y))
    car["path"].append((slot_x(slot) + k * 8, LANE_Y + k * 8))
    canvas.tag_raise(car["tag"])
    counter_value = available
    update_status()


def car_leave(vid, slot, available):
    global counter_value
    slot_cars[slot].remove(vid)
    car = cars[vid]
    car["path"].append((slot_x(slot), EXIT_Y))
    car["path"].append((CANVAS_W + 50, EXIT_Y))
    car["remove"] = True
    counter_value = available
    update_status()


def animate():
    # Every 30 ms, move each car a small step towards its next target point
    for vid in list(cars.keys()):
        car = cars[vid]
        if car["path"]:
            target_x, target_y = car["path"][0]
            dx = target_x - car["x"]
            dy = target_y - car["y"]
            distance = math.hypot(dx, dy)
            if distance <= CAR_SPEED:
                step_x, step_y = dx, dy
                car["path"].pop(0)
            else:
                step_x = dx / distance * CAR_SPEED
                step_y = dy / distance * CAR_SPEED
            canvas.move(car["tag"], step_x, step_y)
            car["x"] += step_x
            car["y"] += step_y
        elif car["remove"]:
            canvas.delete(car["tag"])
            del cars[vid]
    window.after(30, animate)


# ---------------- the deadlock graph (Scenario 5) ----------------
def draw_rag():
    canvas.delete("all")
    label(CANVAS_W // 2, 20, "Who HAS what, and who WANTS what  (Resource Allocation Graph)", BLUE, 13)
    for name in ["Entry Gate", "Ramp"]:            # resources = squares
        x, y = RAG_NODES[name]
        canvas.create_rectangle(x - 50, y - 40, x + 50, y + 40, fill=ASPHALT, outline=DARK, width=2)
        label(x, y, name, "white", 12)
    for name, vid, role in [("V1", 1, "coming IN"), ("V2", 2, "going OUT")]:
        x, y = RAG_NODES[name]                     # cars = circles
        canvas.create_oval(x - 40, y - 40, x + 40, y + 40, fill="white",
                           outline=CAR_COLORS[vid - 1], width=4)
        draw_car(x, y - 4, vid, name, "rag_car")
        label(x + 60, y, role, DARK, 10, anchor="w")
    # legend
    canvas.create_line(20, 385, 60, 385, width=4, fill=GREEN, arrow="last")
    label(68, 385, "HAS it (holds)", GREEN, 10, anchor="w")
    canvas.create_line(200, 385, 240, 385, width=4, fill=ORANGE, arrow="last", dash=(6, 4))
    label(248, 385, "WANTS it (waiting)", ORANGE, 10, anchor="w")
    label(420, 385, "Square = resource     Circle = car (thread)", DARK, 10, bold=False, anchor="w")


def draw_arrow(from_name, to_name, text, color, dashed):
    x1, y1 = RAG_NODES[from_name]
    x2, y2 = RAG_NODES[to_name]
    distance = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / distance, (y2 - y1) / distance
    gap = 55                                       # stop the arrow at the edge of the shapes
    line = canvas.create_line(x1 + ux * gap, y1 + uy * gap, x2 - ux * gap, y2 - uy * gap,
                              width=4, fill=color, arrow="last", arrowshape=(16, 20, 6),
                              dash=(8, 5) if dashed else "")
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    word = label(mid_x - uy * 18, mid_y + ux * 18, text, color, 10)
    return line, word


def rag_update(action, vehicle, resource):
    key = (vehicle, resource)
    if key in rag_edges:                           # remove the old arrow first
        for item in rag_edges[key]:
            canvas.delete(item)
        del rag_edges[key]
    if action == "request":
        rag_edges[key] = draw_arrow(vehicle, resource, "wants", ORANGE, True)
    elif action == "hold":
        rag_edges[key] = draw_arrow(resource, vehicle, "has", GREEN, False)


def rag_deadlock():
    for line, word in rag_edges.values():
        canvas.itemconfig(line, fill=RED)
        canvas.itemconfig(word, fill=RED)


# ---------------- explanations, log and buttons ----------------
LOG_COLORS = {"black": DARK, "green": GREEN, "blue": BLUE,
              "orange": ORANGE, "red": RED, "purple": PURPLE}


def add_log(text, color):
    elapsed = time.time() - scenario_start
    log_box.insert("end", f"[{elapsed:5.1f}s] {text}\n", color)
    log_box.see("end")
    now_label.config(text="NOW:  " + text, fg=BLUE if color == "black" else LOG_COLORS.get(color, DARK))


def show_result(text, color):
    color = GREEN if color == "green" else RED
    if mode == "rag":
        label(460, 209, text, color, 12, justify="center")
    elif items.get("table"):
        label(715, 320, text, color, 12, justify="center")
    else:
        label(615, 320, text, color, 13, justify="center")


def show_story(info):
    title_label.config(text=info["title"])
    story_labels["story"].config(text=info["story"])
    story_labels["concept"].config(text=info["concept"])
    story_labels["watch"].config(text=info["watch"])


def set_buttons(state):
    for b in buttons:
        b.config(state=state)


def handle_event(event):
    kind = event[0]
    if kind == "log":
        add_log(event[1], event[2])
    elif kind == "arrive":
        create_car(event[1], event[2])
    elif kind == "wait":
        waiting.append(event[1])
        place_waiting_cars()
    elif kind == "park":
        car_park(event[1], event[2], event[3])
    elif kind == "leave":
        car_leave(event[1], event[2], event[3])
    elif kind == "row":
        update_table(event[1], event[2], event[3])
    elif kind == "mutex":
        set_mutex(event[1])
    elif kind == "rag":
        rag_update(event[1], event[2], event[3])
    elif kind == "deadlock":
        rag_deadlock()
    elif kind == "result":
        show_result(event[1], event[2])
    elif kind == "done":
        set_buttons("normal")


def poll_events():
    # Read all messages sent by the car threads/processes and update the picture
    while True:
        try:
            event = events.get_nowait()
        except queue.Empty:
            break
        handle_event(event)
    window.after(50, poll_events)


def reset_state():
    global counter_value, mutex_holder, scenario_start
    cars.clear()
    waiting.clear()
    rag_edges.clear()
    items.clear()
    for s in slot_cars:
        s.clear()
    counter_value = TOTAL_SLOTS
    mutex_holder = 0
    scenario_start = time.time()
    log_box.delete("1.0", "end")


def show_intro():
    global mode
    reset_state()
    mode = "intro"
    show_story(INTRO)
    now_label.config(text="NOW:  Read what each picture means, then click  1. Normal Parking.", fg=BLUE)
    draw_intro()


def start_scenario(key):
    global mode
    scenario = SCENARIOS[key]
    reset_state()
    mode = scenario["mode"]
    show_story(scenario)
    now_label.config(text="NOW:  Starting...", fg=BLUE)
    if mode == "lot":
        draw_parking_lot(scenario)
    else:
        draw_rag()
    set_buttons("disabled")
    # Run the OS logic in a separate thread so the window keeps animating
    threading.Thread(target=scenario["run"], daemon=True).start()


def build_window():
    global window, canvas, log_box, title_label, now_label
    window = tk.Tk()
    window.title("Smart Parking System - OS Case Study Simulation")
    window.configure(bg=PAGE)

    # row of buttons
    button_bar = tk.Frame(window, bg=PAGE)
    button_bar.pack(pady=(6, 2))
    all_buttons = [("Start Here", "#eceff1", show_intro)]
    for key in SCENARIOS:
        all_buttons.append((SCENARIOS[key]["button"], SCENARIOS[key]["color"],
                            lambda k=key: start_scenario(k)))
    for text, color, command in all_buttons:
        b = tk.Button(button_bar, text=text, padx=10, font=("Arial", 10, "bold"),
                      bg=color, fg=DARK, activebackground="#90a4ae", activeforeground="white",
                      disabledforeground="#9e9e9e", relief="raised", bd=1, cursor="hand2",
                      command=command)
        b.pack(side="left", padx=3, ipady=2)
        buttons.append(b)

    # title + the three explanation lines
    title_label = tk.Label(window, font=("Arial", 14, "bold"), bg=PAGE, fg=BLUE)
    title_label.pack(pady=(2, 0))
    story_frame = tk.Frame(window, bg="white", highlightthickness=1, highlightbackground="#cfd8dc")
    story_frame.pack(fill="x", padx=8, pady=3)
    for row, (key, heading, color) in enumerate([("story", "WHAT HAPPENS", BLUE),
                                                 ("concept", "OS CONCEPT", PURPLE),
                                                 ("watch", "WATCH FOR", ORANGE)]):
        tk.Label(story_frame, text=heading, width=14, anchor="nw", font=("Arial", 10, "bold"),
                 bg="white", fg=color).grid(row=row, column=0, sticky="nw", padx=(6, 0), pady=1)
        story_labels[key] = tk.Label(story_frame, anchor="w", justify="left", wraplength=780,
                                     font=("Arial", 10), bg="white", fg=DARK)
        story_labels[key].grid(row=row, column=1, sticky="w", pady=1)

    # the animation area
    canvas = tk.Canvas(window, width=CANVAS_W, height=CANVAS_H, bg=GROUND,
                       highlightthickness=1, highlightbackground="#b0bec5")
    canvas.pack(padx=8, pady=2)

    # the live "NOW" explanation line
    now_label = tk.Label(window, font=("Arial", 12, "bold"), bg=PAGE, fg=BLUE,
                         anchor="w", justify="left", wraplength=910)
    now_label.pack(fill="x", padx=10, pady=(2, 0))

    # the full event log
    log_frame = tk.Frame(window, bg=PAGE)
    log_frame.pack(fill="both", expand=True, padx=8, pady=(2, 8))
    scrollbar = tk.Scrollbar(log_frame)
    scrollbar.pack(side="right", fill="y")
    log_box = tk.Text(log_frame, height=5, font=("Consolas", 9), bg="white", fg=DARK,
                      relief="solid", bd=1, yscrollcommand=scrollbar.set)
    log_box.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=log_box.yview)
    for name, code in LOG_COLORS.items():
        log_box.tag_config(name, foreground=code)

    show_intro()
    poll_events()
    animate()


# ==================================================================
# MAIN PROGRAM
# ==================================================================
if __name__ == "__main__":
    multiprocessing.freeze_support()           # needed for Windows
    build_window()
    window.mainloop()
