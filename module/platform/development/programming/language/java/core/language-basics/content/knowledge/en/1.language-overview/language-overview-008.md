# Core Java Learning Roadmap and an End-to-End Example Program

Learning Java easily feels fragmented if today you write an addition, tomorrow you learn `if`, and the next day you learn loops without seeing how they work together to solve a problem. An effective roadmap should have a **concrete destination**: after each topic, you add a capability to the **same program**, run it yourself, and verify the output.

This lesson proposes foundational milestones for learning core Java alongside a running example: **tracking daily self-study minutes**. The program takes a daily minute goal together with actual durations for multiple days, then calculates the total, the average, and the number of days meeting the goal. This is a command-line practice project requiring no frameworks, databases, or advanced object-oriented programming knowledge.

## 1. Learn by Capabilities, Not Just by Lessons Read

| Milestone | Knowledge to master | Verifiable capability | Addition to the example |
| --- | --- | --- | --- |
| 1. Run a program | JDK, `.java` file, `main`, `javac`, `java`, `println` | Compile and print a message | Print the heading “Study Tracker” |
| 2. Represent data | `int`, `long`, `double`, `boolean`, `String`, variables and operators | Explain the right type and unit for each variable | Store goal, minutes, compute total and average |
| 3. Make decisions | Comparisons, `if`, `else`, `&&`, `||` | Predict which branch runs at boundary values | Decide which day met the goal |
| 4. Process multiple values | `for`, arrays, indices, `args` | Iterate accurately over each element with no off-by-one error | Aggregate multiple days instead of one day |
| 5. Organize code | Methods, parameters, return types, variable scope | Separate processing from input/output | Write a method to validate minutes |
| 6. Handle input and testing | `parseInt`, exceptions, normal and boundary tests | Distinguish compile errors, data errors, and logic errors | Reject negative numbers, non-numeric strings, missing days |

This is a **suggested sequence**, not a mandatory number of days to finish. Move on to the next milestone only when you can explain why the program produces its current output and fix a small bug yourself without copying the entire solution.

You do not need to learn generics, streams, networking, or frameworks to run your first example. Those topics can be learned when a problem creates a genuine need for them.

## 2. Define Requirements Before Programming

Suppose you want to see whether you studied at least **60 minutes per day** over the last four days.

Sample input:

- Goal: `60` minutes/day.
- Actual durations in order: `45`, `60`, `20`, `80` minutes.

Output requirements:

| Value | Hand-calculated result |
| --- | ---: |
| Number of days | 4 |
| Total minutes | 45 + 60 + 20 + 80 = 205 |
| Days meeting goal | 2 (day 2 and day 4) |
| Daily average | 205 / 4 = 51.25 minutes |

**Program conventions:**

- The goal must be an integer **greater than 0**.
- Each day's minutes must be a **non-negative** integer; a 0-minute day still counts as one day.
- There must be at least one day to avoid division by 0.
- A day whose duration **equals** the goal counts as meeting it (`>=`).
- Each command-line argument must represent an integer in the `int` range; a value like `10.5` is invalid in this version.
- The average may have a fractional part. The program prints up to two digits after the decimal point, **without rounding the input minutes**.

Stating conventions before coding matters more than immediately picking which loop to use: the program must match the defined requirements.

## 3. Turning Requirements into Processing Steps

Write the algorithm in words:

1. Read the first argument as the goal; subsequent arguments are the minutes for each day.
2. If the goal is missing or all day data is missing, print usage instructions.
3. Convert text into integers and reject invalid data.
4. Set `total` (total minutes) and `daysMet` (days meeting goal) to 0.
5. Loop through each day: add minutes to total; if minutes `>=` goal, increment `daysMet`.
6. Divide total by the number of days using floating-point division to compute the average.
7. Print the goal, number of days, total, days meeting the goal, and average.

An easy mistake to make is forgetting that **the goal is not a day**. When processing the arguments array, element `args[0]` is the goal, while the days start at `args[1]`. If you accidentally count `args[0]` as a day as well, all statistics will be wrong even though the program still compiles.

## 4. Complete Java Program

Create a file named **`StudyTracker.java`** with the following content (compatible with JDK 17 and later):

~~~java
import java.util.Locale;

public class StudyTracker {
    static int parseMinutes(String raw) {
        int minutes = Integer.parseInt(raw);
        if (minutes < 0) {
            throw new IllegalArgumentException(
                    "So phut khong duoc am");
        }
        return minutes;
    }

    public static void main(String[] args) {
        if (args.length < 2) {
            System.out.println(
                    "Cach dung: java StudyTracker "
                    + "<mucTieuPhut> <ngay1> [ngay2] ...");
            return;
        }

        try {
            int goal = parseMinutes(args[0]);
            if (goal == 0) {
                throw new IllegalArgumentException(
                        "Muc tieu phai lon hon 0");
            }

            long total = 0L;
            int daysMet = 0;

            for (int i = 1; i < args.length; i++) {
                int minutes = parseMinutes(args[i]);
                total += minutes;

                if (minutes >= goal) {
                    daysMet++;
                }
            }

            int days = args.length - 1;
            double average = (double) total / days;

            System.out.println(
                    "Muc tieu: " + goal + " phut/ngay");
            System.out.println("So ngay: " + days);
            System.out.println("Tong phut: " + total);
            System.out.println(
                    "Ngay dat muc tieu: " + daysMet);
            System.out.printf(
                    Locale.ROOT,
                    "Trung binh: %.2f phut/ngay%n",
                    average);
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Loi: Moi tham so phai la so nguyen hop le");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        }
    }
}
~~~

### Explanation Milestone by Milestone

**Variables and types:** `goal`, `minutes`, and `daysMet` are `int`; `total` is `long` so summing many days has a wider range than an individual day's minutes; `average` is `double` because the average may not be a whole number. These names indicate the meaning of the data rather than just `a`, `b`, `c`.

**Conditions:** `if (minutes >= goal)` checks each day. The `>=` operator includes equality, so 60 minutes meets a 60-minute goal.

**Loops and arrays:** `args` is a `String[]`. The `for` loop starts at index 1, runs while `i < args.length`, and increments `i` after each iteration. Java indexes arrays starting from 0.

**Methods:** `parseMinutes(String raw)` takes an input string, parses it to `int`, and rejects negative numbers. Giving the validation rule a method name lets it be reused for both the goal and each day.

**Exceptions:** `Integer.parseInt` can throw `NumberFormatException` if the string is malformed or outside the `int` range. This is a subclass of `IllegalArgumentException`, so the program catches `NumberFormatException` first to give a specific message.

**Division:** `(double) total / days` forces floating-point division. If you wrote `total / days`, integer division would discard the fractional part **before** assigning to the `double` variable.

**Limitations:** This is a small single-run application. It does not save history to a file, read the system clock, or verify whether the user actually studied; the minutes are provided by the user.

## 5. Compile, Run, and Verify the Results

Open a terminal in the directory containing `StudyTracker.java`. First check the tools:

~~~bash
java -version
javac -version
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StudyTracker.java
java StudyTracker 60 45 60 20 80
~~~

Expected output:

~~~text
Muc tieu: 60 phut/ngay
So ngay: 4
Tong phut: 205
Ngay dat muc tieu: 2
Trung binh: 51.25 phut/ngay
~~~

Try tracing by hand:

- `total` progresses through the values 0 → 45 → 105 → 125 → 205.
- `daysMet` increments only on minutes 60 and 80, so the result is 2.
- `days = args.length - 1 = 5 - 1 = 4`.
- `average = 205.0 / 4 = 51.25`.

This program is an example **small enough to trace completely**, yet contains data, conditions, loops, methods, and error handling to practice across multiple learning milestones.

## 6. Testing Boundary Cases

Do not run only the sample data. Try the following cases:

| Run command | Result to check | Related concept |
| --- | --- | --- |
| `java StudyTracker 60 60` | One day, one day met, average 60.00 | Equality threshold |
| `java StudyTracker 60 0 120` | Two days, one day met, average 60.00 | Zero value is still valid |
| `java StudyTracker 60 59` | Zero days met | Value just below threshold |
| `java StudyTracker 60` | Prints usage instructions | Missing day data |
| `java StudyTracker 0 20` | Reports goal must be > 0 | Validity check |
| `java StudyTracker -1 20` | Reports minutes cannot be negative | Input check |
| `java StudyTracker 60 20 -5` | Reports negative-number error | Invalid value in middle of list |
| `java StudyTracker 60 abc` | Reports string is not an integer | Parsing and exceptions |
| `java StudyTracker 60 2.5` | Reports string is not an integer | Convention accepts integers only |
| `java StudyTracker 60 2147483648` | Reports number outside `int` range | Data type limits |

With valid data, the number of days met always lies between 0 and the number of days. Total minutes must be non-negative. These are simple **invariants for self-checking results**.

Note: `total` is a `long`, though in principle it still has a limit. With the plausible number of arguments for an ordinary command-line program, `long` overflow is unlikely; if expanded into a tool processing massive datasets, add overflow checks (such as `Math.addExact`) and suitable storage rules.

## 7. Adding One Exercise per Milestone to the Same Program

You do not need to write a completely different application after each lesson. You can keep using `StudyTracker` and upgrade it step by step:

| Upgrade milestone | Concrete exercise | Sign of doing it right |
| --- | --- | --- |
| Variables and expressions | Print how many minutes short each day was from the goal | Does not report negative shortfall for days that met the goal |
| Conditions | Classify each day: 0 minutes, below goal, met goal | Accurate on 0, goal−1, goal, goal+1 |
| Loops | Print each day's index number alongside its minutes | Does not include the goal in the day list |
| Methods | Create `static boolean metGoal(int minutes, int goal)` | Every result matches the old condition |
| Arrays | Copy valid minutes into an `int[]` before aggregating | Element count equals number of days entered |
| Testing | Write a separate input/expected output table | Tests normal, boundary, and invalid cases |
| Beyond fundamentals | Store data with a `List` or file, add automated tests | Preserves original statistical meaning |

One small illustrative upgrade:

~~~java
static boolean metGoal(int minutes, int goal) {
    return minutes >= goal;
}
~~~

If you add this method **inside the `StudyTracker` class**, you can replace the `if (minutes >= goal)` condition in `main` with `if (metGoal(minutes, goal))`. The results must remain identical. If the output changes, that is a sign the refactor altered behavior.

Do not do all exercises at once. At each step, make just one change, compile, re-run the sample cases, and compare against expected results.

## 8. How to Study and Self-Check Progress

Use a small repeating study loop at each milestone:

1. **Read with purpose:** grasp keywords, meanings, and the minimal example.
2. **Predict first:** write down expected output before running.
3. **Type and run yourself:** use `javac` and `java`, fixing errors based on real messages.
4. **Change one condition:** test boundary values to see why syntax and data types matter.
5. **Explain it back:** answer in your own words “why is this line here?”.
6. **Record one error you hit:** compile error, runtime error, or logic bug, and how you found the cause.

You can consider a milestone achieved when you can do **three things** yourself: explain the code, predict output for new input, and make a small change without breaking previously working behavior.

### Learning Pitfalls to Avoid

- **Copying code without understanding:** getting the right output once does not prove you grasp the processing steps.
- **Learning syntax detached from problems:** after reading about loops, immediately apply them to concrete data.
- **Upgrading too early:** there is no need to create multiple classes, databases, or GUIs just to count minutes.
- **Skipping boundary cases:** `>=` and `>` may differ by only one character yet change results.
- **Confusing “compiles” with “correct”:** `javac` checks syntax and types; it does not automatically know what “meeting the goal” means.
- **Treating error messages as failure:** errors are evidence that helps isolate an incorrect condition.

## 9. End-of-Lesson Self-Assessment

Answer before re-running the program:

**1.** With `java StudyTracker 30 10 30 40`, what are the total minutes, days met, and average?

*Answer:* Total 80 minutes, 2 days met, average `80 / 3 ≈ 26.67` minutes/day.

**2.** If the loop started at `i = 0` instead of `i = 1`, what problem occurs?

*Answer:* The goal is mistakenly counted as data for a day; total, days met, and day count no longer keep their intended meaning.

**3.** Why must `days` be calculated as `args.length - 1`?

*Answer:* One argument is used to specify the goal; the remaining arguments are the individual days.

**4.** Why can a string `"20"` be converted to minutes, whereas `"hai mươi"` is not accepted in the current version?

*Answer:* `Integer.parseInt` only parses strings formatted as valid integers per API rules; it does not understand numbers written in Vietnamese words.

**5.** If you wanted to allow fractional minutes like `45.5`, what would need to be reconsidered?

*Hint:* You must revise input requirements, data types and parsing, validation rules, comparisons, formatting/display, and tests. Do not merely swap `int` to `double` while ignoring special values and the meaning of minutes.

## Key Takeaways

**An effective Java learning roadmap is a chain of capabilities verified through an increasingly complete program.** Learn variables to represent data, conditions to express rules, loops to process multiple values, methods to organize work, and testing to confirm the program meets requirements. With `StudyTracker`, every new concept has a place to be applied and outputs you can verify yourself—that is the bridge from understanding syntax to solving problems independently with Java.
