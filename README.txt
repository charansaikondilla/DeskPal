===========================================================================
  DeskPal  -  your kawaii desktop buddy for Windows
===========================================================================

  A little dog, cat or person that lives on top of everything on your
  screen.  It walks around, reacts when you click it, watches your
  battery and your working time, and reminds you to take breaks, drink
  water, rest your eyes, stretch and breathe.


---------------------------------------------------------------------------
  HOW TO START IT  (about two minutes, once)
---------------------------------------------------------------------------

  1.  Put this whole DeskPal folder anywhere you like.
      Documents, Desktop, anywhere.  It does not matter.

  2.  If you do not already have Python:
        - go to  https://www.python.org/downloads/
        - download Python for Windows and run the installer
        - IMPORTANT: on the very first installer screen, tick the box
          "Add python.exe to PATH", then click Install Now
      That is the only thing you ever need to install.  DeskPal uses
      nothing else - no pip, no downloads, no account, no internet.

  3.  Double-click  Start-DeskPal.bat

      Start-Buddy.bat also works. Start-DeskPal.bat is the simple launcher
      to use whenever you want to activate DeskPal.

  Your buddy appears in the bottom right corner and says hello.

  To test the Ganesh animations, double-click the buddy to open Settings,
  choose the Emotes tab, then click Walking, Running, Getting hungry,
  Holding a laddu, Eating a laddu, Satisfied, or Celebrating.

  For the DeskPal launch page, double-click Start-DeskPal-Launch.bat.
  It opens http://127.0.0.1:8766/ on this computer.
  Click Launch DeskPal to start the actual desktop companion as Ganesh.
  The page confirms the app is visible, then offers desktop emote controls.
  Start-Ganesh-Experience.bat also opens this new launcher.


---------------------------------------------------------------------------
  HOW TO USE IT
---------------------------------------------------------------------------

  Left click  ............  pet it (click a few times in a row, it will
                            dance, then fall in love with you)
  Drag  ..................  move it anywhere, on any monitor
  Hover  .................  it tells you the time, your battery and when
                            the next break is due
  Double click  ..........  open Settings
  Right click  ...........  the full menu

  The right-click menu has:
      Take a break now
      Start focus session         (a Pomodoro timer next to your buddy)
      Breathe with me             (box 4-4-4-4 / 4-7-8 / calm 4-6)
      Rest my eyes (20 sec)
      Tricks                      (dance, disco, wave, spin, bow, stretch,
                                   jumping jacks, celebrate, nap, and a
                                   "More silly tricks" submenu with 14 more
                                   - see the full list below - plus
                                   say something nice)
      Change character            (Puppy / Kitty / Buddy)
      Come to my mouse  /  Go back to the corner
      Quiet for a while           (30 min, 1 hour, 2 hours)
      Hide me                     (15 min, 1 hour, 4 hours)
      How I am doing...           (your week in a small chart)
      Settings...
      Quit DeskPal


---------------------------------------------------------------------------
  WHAT'S NEW IN 1.3  -  health, your way
---------------------------------------------------------------------------

  * A redesigned app: six pages (Today, Focus, Health, Goals, Ganesh,
    Settings), a cleaner layout, light and dark themes, six accent
    colours, keyboard shortcuts 1-6, and a live Ganesh in the sidebar.
  * Health page: one card per reminder (break, eye rest, water, stretch,
    posture, snack, breathing). Each card shows a live countdown, today's
    count against your daily target, and lets you set the interval, the
    target, and the exact words Ganesh says on the desktop card.
  * Log check-ins from the app ("Drank a glass", "Stretched", ...) - they
    count towards the rings and restart that reminder's timer.
  * Your own reminders: name, interval and message. Ganesh fires them on
    the desktop with Done / 10 more min / Skip, and keeps a streak.
  * Daily targets and health rings on the Today page, plus active minutes
    per day for the week and an "all time" line.
  * Schedule: "only remind me during work hours", quiet hours, idle pause
    and full-screen detection, all on the Health page.
  * Goals show the last seven days as dots. Focus page has 25/5, 50/10
    and 90/20 presets that are saved as your defaults, and focus stats.
  * Settings search box.
  * Fixed: clicking a switch's knob did nothing (only its text label
    worked). Every switch is now a real label.

---------------------------------------------------------------------------
  WHAT'S NEW IN 1.2  -  real-time app window
---------------------------------------------------------------------------

  * Start DeskPal.bat now opens DeskPal as its own app window (no browser
    tabs, no console) with Ganesh on the desktop at the same time.
  * Live presence strip: active / idle state, focus timer and health
    reminders refresh every second from real tracked data.
  * Settings page inside the app (toggles, intervals, choices) - the old
    Tk settings window is retired; "Settings..." opens the app page.
  * Full emote set and actions (Walk, Run, Hungry, Laddu toss, Wave,
    Celebrate) can be triggered from the app and are acknowledged by the
    desktop companion.
  * Works fully offline - no CDN scripts or fonts; charts are hand-drawn.
  * Reliability: the engine now drains every queued command each tick
    (it used to accept one per 100 ms with a backlog of 1, so a settings
    change made while the app window was polling could be refused and
    silently lost). The goals list no longer rebuilds every second.
  * verify_launch.py drives the real app end to end (launch, emotes,
    settings, actions, live presence, security, zero tracebacks). It
    always tests a freshly launched app and cleans up after itself, so
    it can be run back to back.

---------------------------------------------------------------------------
  WHAT'S NEW IN 1.1  -  18 brand new animations
---------------------------------------------------------------------------

  Every one of these works with all three characters (Puppy, Kitty and
  Buddy), plays instantly from the right-click Tricks menu, and was built
  on the exact same tested, crash-proof animation engine as everything
  else - so it is exactly as safe as the moves that shipped in 1.0.

  In the main Tricks menu:
      Disco moves         arms alternate side to side on the beat, with
                          little music notes floating up
      Spin around!        a quick joyful twirl in place
      Take a bow          a graceful theatrical bow, arms out wide

  Tucked inside "More silly tricks":
      Shimmy              a playful side-to-side wiggle
      Applause            claps along with sparkles popping around it
      Peekaboo!           covers its eyes, then pops out with a little star
                          burst
      Ta-da!              throws its arms out with a burst of confetti, like
                          the end of a magic show
      Moonwalk            glides backwards while "walking" forward -
                          smoother than it has any right to be
      Robot mode          stiff, jerky, deadpan robot dance - blush and tail
                          switch off completely for the bit
      Fly like a hero     rises up like a tiny superhero, with a sparkle and
                          star trail underneath
      Karate chop!        a quick flurry of chops with an impact sparkle
      Magic trick         raises a paw, then - abracadabra - a burst of
                          stars and sparkles
      Brrr (shiver)       a cold little shiver and chattering mouth
      Achoo! (sneeze)     builds up... and sneezes
      Hiccup              a few surprised little hiccup-jumps
      Confused            tilts its head side to side with question marks
                          popping up above it
      Boo! (surprise)     jumps back, wide-eyed, with a little "!" mark

  Two small engine upgrades made these possible, and both are completely
  invisible unless you go looking: characters can now move their left and
  right paw/hand independently (used by Disco and Robot mode for a true
  alternating look), and a couple of tricks can briefly turn the whole
  character around mid-animation for a proper spin.

  Nothing about how DeskPal reminds you to take breaks, drink water, rest
  your eyes or breathe changed in this update - it is purely more ways
  for your buddy to be silly with you in between.


---------------------------------------------------------------------------
  WHAT IT REMINDS YOU ABOUT
---------------------------------------------------------------------------

  Break        every 45 minutes of ACTIVE work   (default, adjustable)
  Eye rest     every 20 minutes  - the 20-20-20 rule
  Water        every 60 minutes
  Stretch      every 90 minutes  - with a different idea every time
  Posture      every 30 minutes
  Breathing    every 3 hours     - a full guided breathing session

  It also notices, on its own:

    - your battery getting low, and when it is fully charged
    - that it has got late (it gets sleepy and suggests bed)
    - that you have been inside the same app for a very long time
    - that you stepped away from the keyboard: the break timer counts
      only the minutes you are actually using the laptop, and when you
      come back it says hello instead of nagging you
    - that a game or video is running full screen: it stays quiet

  Every one of these can be turned off or retimed in Settings, and the
  Quiet hours setting silences everything between two times of day.


---------------------------------------------------------------------------
  THINGS WORTH KNOWING
---------------------------------------------------------------------------

  * It floats above every window, on any of your monitors, and it does
    NOT steal your keyboard focus - you can keep typing while it walks
    around.  The see-through part of its window is click-through, so it
    never blocks what is underneath.

  * To start it automatically with Windows:
      Settings  ->  Buddy tab  ->  "Start automatically when Windows starts"
    (If that ever fails, press Win+R, type  shell:startup  and drop a
    shortcut to Start-Buddy.bat into the folder that opens.)

  * Your settings, your stats and a log file live in:
      %APPDATA%\DeskPal
    Settings -> About -> "Open that folder" takes you straight there.

  * Only one buddy can run at a time.  If you double-click the launcher
    twice, the second one politely tells you it is already running.

  * To close it: right click -> Quit DeskPal.


---------------------------------------------------------------------------
  IF SOMETHING GOES WRONG
---------------------------------------------------------------------------

  Double-click  If-Something-Goes-Wrong.bat
  It starts the buddy with a visible console, checks that Python and
  tkinter are working and prints anything that fails.

  The buddy is written so that a failure in any single feature is caught,
  written to the log and skipped - it does not take the rest down with it.

    Nothing appears at all
        -> run If-Something-Goes-Wrong.bat and read the messages
        -> the buddy may be sitting on a second monitor that is turned
           off: right click the taskbar... actually simpler, delete
           %APPDATA%\DeskPal\settings.json and start it again, it will
           go back to the bottom right corner of the main screen

    It is too big or too small
        -> Settings -> Buddy -> Size

    It gets in the way
        -> drag it somewhere else, or right click -> Hide me

    Too many reminders
        -> Settings -> Reminders, turn off the ones you do not want
        -> or right click -> Quiet for a while


---------------------------------------------------------------------------
  Made for you.  Be kind to yourself today.
===========================================================================
