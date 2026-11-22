# Practice: Console Menu with Input Validation (Java 17+)

## 1. Problem statement and goal

A **console menu** is a program that displays a list of choices, reads user input, and executes the matching action. Menus typically need to **repeat** until the user explicitly chooses to exit. Reading choices with only `nextInt()` followed by `switch` quickly breaks when the user enters letters, out-of-range numbers, empty lines, or ends the input stream (*EOF*).

This practice builds a **points total management menu** in Java 17+ with these options:

| Choice | Action | Additional input |
| --- | --- | --- |
| `1` | Add points to current total | Enter an integer from `1` to `1000` |
| `2` | View current total points | None |
| `3` | Reset total points to `0` | None |
| `0` | Exit the program | None |

**Input contract:**

- Menu choice must be an **integer from 0 to 3**.
- Points added must be an **integer from 1 to 1000**; `0`, negative numbers, and fractions are not accepted.
- If non-integer text is entered (`abc`, `1.5`, blank line, or an integer outside `int` range), the program **prints an error and re-prompts the same field**, without exiting or changing the total.
- If an out-of-range integer is entered, the program prints the exact valid range and re-prompts.
- If the input stream ends before a valid choice or value is given, the program prints `Input ended.` and exits cleanly.
- The initial total is `0` and increases only when a **valid add-points action** completes.

This is an illustrative menu for practicing loops, branching, input validation, and state management, not a production loyalty system.

## 2. Input – Process – Output analysis

| Part | Content | Java approach |
| --- | --- | --- |
| Input | Choice `0`–`3` | `Scanner.nextLine()`, `Integer.parseInt()` |
| Input | Points to add `1`–`1000` when choosing `1` | Same input reading and validation helper |
| Process | Repeat menu until exit | `while (true)` |
| Process | Map choice to action | `switch` with `case ... ->` syntax |
| Process | Accumulate or reset `total` | `long total` declared **outside** the loop |
| Output | Menu, prompts, errors, added points, total, goodbye message | `System.out.println()` |

Choosing `long` for the total allows repeated additions to exceed `int` range safely; points per turn fit in `int` since each addition is capped at `1000`. This exercise sets no cap on total turns; in a very long-running program, consider capping the total or using `Math.addExact()` to prevent `long` overflow. For a normal console study session, that is not a practical issue.

### Logic diagram

```text
Initialize total = 0
        |
        v
Display menu
        |
        v
Read and validate choice
        |
        +-- EOF ------------------------> Notify and exit
        |
        +-- Invalid type/range ---------> Print error, re-prompt choice
        |
        v
switch(choice)
        |
        +-- 1: prompt points -- invalid --> print error, re-prompt points
        |                    |
        |                    +-- valid ---> add to total, notify
        |                    |
        |                    +-- EOF -----> notify and exit
        |
        +-- 2: print current total
        |
        +-- 3: reset total to 0
        |
        +-- 0: say goodbye and exit
        |
        v
Return to menu after actions 1, 2, or 3
```

The key point is that the **retry loop inside each prompt** and the **outer menu loop** have two separate responsibilities. Bad input at the points prompt should not bounce the user back to the main menu, and bad input at the menu prompt must never alter the total.

## 3. Complete Java 17+ code: MenuConsoleApp.java

Create a file named **`MenuConsoleApp.java`** with the exact contents below:

```java
import java.util.Scanner;

public final class MenuConsoleApp {
    private MenuConsoleApp() {
    }

    /**
     * Reads an integer within the allowed range.
     * Returns null if the input stream has ended.
     */
    private static Integer readIntInRange(
            Scanner scanner, String prompt, int min, int max) {

        while (true) {
            System.out.println(prompt);

            if (!scanner.hasNextLine()) {
                return null;
            }

            String text = scanner.nextLine().strip();
            final int value;

            try {
                value = Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                System.out.println("Error: enter an integer.");
                continue;
            }

            if (value < min || value > max) {
                System.out.println("Error: value must be from "
                        + min + " to " + max + ".");
                continue;
            }

            return value;
        }
    }

    public static void main(String[] args) {
        long total = 0L;

        try (Scanner scanner = new Scanner(System.in)) {
            while (true) {
                System.out.println("=== MENU ===");
                System.out.println("1. Add points");
                System.out.println("2. View total");
                System.out.println("3. Reset total");
                System.out.println("0. Exit");

                Integer choice = readIntInRange(
                        scanner, "Choice (0-3):", 0, 3);

                if (choice == null) {
                    System.out.println("Input ended.");
                    return;
                }

                switch (choice) {
                    case 1 -> {
                        Integer points = readIntInRange(
                                scanner, "Points (1-1000):", 1, 1000);

                        if (points == null) {
                            System.out.println("Input ended.");
                            return;
                        }

                        total += points;
                        System.out.println("Added: " + points);
                    }
                    case 2 -> System.out.println("Total: " + total);
                    case 3 -> {
                        total = 0L;
                        System.out.println("Total reset.");
                    }
                    case 0 -> {
                        System.out.println("Goodbye.");
                        return;
                    }
                    default -> throw new AssertionError(
                            "Unexpected validated menu choice");
                }
            }
        }
    }
}
```

### Section-by-section explanation

**`readIntInRange()` — single place for type and range validation.** The method prints the prompt, reads a full line via `nextLine()`, strips leading/trailing whitespace with `strip()`, and parses it with `Integer.parseInt()`. If parsing fails, `catch (NumberFormatException)` prints an error and uses `continue` to re-prompt **the exact same question**. If the number is outside `[min, max]`, it likewise prints an error and re-prompts.

**`Integer` instead of `int` for the return value.** The method must distinguish two separate outcomes: reading a valid integer vs. **hitting EOF before getting a number**. `Integer` can return `null` on EOF, while `0` remains a **valid choice meaning exit**. Therefore `0` is never overloaded to mean EOF. Once `choice != null` is checked, `switch (choice)` unboxes safely to `int`.

**Outer `while (true)` — redisplaying the menu.** After choice 1, 2, or 3, execution finishes the `switch` branch and loops back to the top. Choice 0 executes `return` to exit `main`. `try-with-resources` closes the scanner upon exiting the block.

**`switch (choice)` — executing a single action.** Arrow syntax `case 1 ->` is supported in Java 17 and prevents accidental *fall-through* unlike legacy `case 1:` if `break` is forgotten. For branches with multiple statements, wrap them in `{ ... }`.

**`total` outside the loop — preserving state.** Placing `long total = 0L;` inside `while` would wipe the total every time the menu reappears. Only branch 1 (valid points entry) adds to the total; branch 3 explicitly resets it.

**`default` acts as a programming safeguard.** Because `readIntInRange` constrains choices to 0–3, `default` is unreachable under normal flow. If someone later updates the menu options inconsistently, `AssertionError` catches the design bug instead of silently ignoring it.

## 4. Compiling and running via CLI

Use **JDK 17+** in the folder containing `MenuConsoleApp.java`. Create the `out` directory once if it does not exist:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out MenuConsoleApp.java
java -cp out MenuConsoleApp
```

These `javac` and `java` commands work on Windows PowerShell, Windows CMD, Linux, and macOS. When compilation succeeds, `javac` usually prints nothing. `-d out` specifies where `MenuConsoleApp.class` is written; `-cp out` tells the JVM where to look for classes. Omit `.class` when calling `java`.

The program prints the menu and waits for input. Press Enter after each number. You can also save an input sequence in `sample.txt` to reproduce exact stdout:

- **Linux/macOS or Windows CMD:** `java -cp out MenuConsoleApp < sample.txt`.
- **Windows PowerShell:** `Get-Content -LiteralPath sample.txt | java -cp out MenuConsoleApp`.

In interactive mode, the terminal may echo keys typed by the user. Those echoed characters are **not part of stdout** produced by Java `println()` calls; the examples below show only the program's stdout.

## 5. Testing a normal menu flow

Create `sample.txt` with six **input** lines:

```text
1
7
2
3
2
0
```

Meaning: add 7 points, view total, reset total, view total again, exit.

**Exact stdout**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Points (1-1000):
Added: 7
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total: 7
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total reset.
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Total: 0
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Goodbye.
```

Trace each step:

1. Choice `1` makes the program prompt `Points (1-1000):`, receive `7`, and compute `total = 0 + 7`.
2. Choice `2` **does not ask for points**; it only prints `Total: 7`.
3. Choice `3` sets `total = 0` and confirms with `Total reset.`.
4. Choice `2` again prints `Total: 0`, confirming the reset took effect.
5. Choice `0` prints `Goodbye.` and exits; the menu does not print a sixth time.

## 6. Testing invalid input

Create another input file with three lines:

```text
abc
9
0
```

**Exact stdout**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Error: enter an integer.
Choice (0-3):
Error: value must be from 0 to 3.
Choice (0-3):
Goodbye.
```

Explanation:

- `abc` cannot be parsed as an `int`; `Integer.parseInt("abc")` throws `NumberFormatException`. The program **catches the error inside the helper** and re-prompts the choice.
- `9` is a valid `int` type-wise, yet outside the 0–3 menu range; the program reports a **range** error instead of treating it as a hidden option.
- `0` is valid and triggers the exit branch.
- On both invalid inputs, **the full menu is not reprinted** because validation happens in the inner prompt loop inside `readIntInRange()`, keeping the user focused on the active field.

Similarly, if you choose 1 and then enter `0`, `-1`, `1001`, `1.5`, a blank line, or `999999999999999999999` at the points prompt, the program keeps re-prompting until it receives an integer from 1 to 1000 or hits EOF. Those invalid entries **never change the total**.

**Important:** format errors and range errors are distinct. `"1.5"` is text that fails `Integer.parseInt`, whereas `1001` parses successfully yet violates the business rule.

## 7. Handling EOF instead of hanging or crashing

EOF (*end of file*) occurs when a redirected file runs out of lines, a pipe closes, or the user signals end-of-input in their terminal. EOF is **different** from choice 0:

- **Choice 0:** the user chose to exit; the program prints `Goodbye.`.
- **Hitting EOF:** no more data is available to read; the helper returns `null`, and the program prints `Input ended.`.

An empty input (an empty file `empty.txt` with zero lines) produces **exact stdout**:

```text
=== MENU ===
1. Add points
2. View total
3. Reset total
0. Exit
Choice (0-3):
Input ended.
```

If input contains only `1` followed by EOF, the program prints the menu, accepts choice 1, prints `Points (1-1000):`, and then `Input ended.`. It neither adds points nor loops infinitely.

`hasNextLine()` checks whether **another line is available**, not whether that line is an integer. That is why both steps are needed: `hasNextLine()` for EOF and `Integer.parseInt()` for numeric validity.

In an interactive console, `hasNextLine()` may **block waiting for input** when the user has not sent a line or closed the stream yet. Waiting for input is not an infinite loop; distinguish that from code that repeatedly reads the same invalid token without consuming it.

## 8. Why read a whole line and parse instead of calling `nextInt()`?

A common pattern beginners write is:

```java
int choice = scanner.nextInt();
```

If the user types `abc`, this call throws `InputMismatchException`. Moreover, mixing `nextInt()` with `nextLine()` leaves the trailing newline in the buffer, causing the next `nextLine()` to return an empty string.

This lesson's approach is:

```java
String text = scanner.nextLine().strip();
int choice = Integer.parseInt(text);
```

This snippet illustrates just **two statements**, assuming `scanner` exists and input is formatted properly; in the full example, parsing sits inside `try/catch` so bad input does not crash the program.

Advantages of line-based reading:

- Each entry corresponds to **one clear line**, leaving no stray newline behind.
- Easy to distinguish **EOF**, empty strings, whitespace-only lines, non-numeric input, and out-of-range numbers.
- Prompts and error messages stay predictable.
- No need to create multiple `Scanner` objects wrapping `System.in`.

If an input format genuinely puts multiple numbers on one line, token-based reading can be more convenient. There is no rule saying `nextInt()` is always wrong; the point is matching the reading strategy to the input format and handling errors cleanly.

## 9. Distinguishing loop control statements

In menu programs, it is easy to mix up `continue`, `break`, and `return`.

| Statement | Effect | How it applies here |
| --- | --- | --- |
| `continue` | Skips the rest of the **current iteration** and starts the next iteration of the innermost loop | On bad input in `readIntInRange()`, **re-prompts that field** |
| `break` | Exits the innermost loop or legacy `switch` | Could exit the menu loop, though the example uses `return` on choice 0 |
| `return` | Exits the currently executing method | In `main`, terminates the program; in the helper, returns the value or `null` |
| `case ... ->` | Arrow `switch` branch; never falls through to the next branch | Keeps actions 1, 2, 3, and 0 independent |

**Note:** If you use legacy `switch (choice) { case 0: break; ... }`, `break` inside `case 0:` only exits `switch`, **not the enclosing `while` loop**. The program would reprint the menu instead of exiting. You would need a loop flag, a labeled `break` where appropriate, or `return` as in the sample.

In Java 17, arrow `switch` (`case 1 -> ...`) can be used as a switch statement. Put multi-statement branches in `{ ... }`. No `break` is needed at the end of an arrow branch.

## 10. Test cases to cover

| Input / path | Result to verify |
| --- | --- |
| `0` at the very first menu | Prints `Goodbye.`, never asks for points |
| `1, 7, 2, 0` (one value per line) | Prints `Added: 7`, then `Total: 7`, then exits |
| `1, 7, 3, 2, 0` | Final total is 0 after reset |
| `abc, 0` | Reports format error, re-prompts, then exits |
| `-1, 4, 0` | Reports range error twice, then exits |
| `1, abc, 5, 2, 0` | Does not add `abc`; adds 5 points and shows `Total: 5` |
| `1, 1001, 1000, 2, 0` | Rejects 1001, accepts boundary 1000, total 1000 |
| `1, 0, 1, 2, 0` | Points 0 rejected; then adds 1 point |
| Empty file | Prints `Input ended.` and exits |
| Only `1` then EOF | Enters add-points branch, exits safely when no points follow |
| Line with spaces ` 2 ` | `strip()` allows parsing as choice 2 |
| Number outside `int` range | `NumberFormatException` caught, re-prompts without crashing |

**Testing rule:** Run each scenario in a **separate execution** with the items in the input column placed on **consecutive lines**, not separated by commas on one line. When testing error cases, verify not only that the error message appears, but also that state did not change unexpectedly.

## 11. Common programming mistakes and how to avoid them

**(a) Placing `total` inside the menu loop.** Running `long total = 0;` every time the menu displays loses accumulated points. Initialize the total **once** before the loop.

**(b) Failing to consume bad input.** With `Scanner.nextInt()`, an invalid token stays in the buffer; looping with `hasNextInt()` without discarding the token freezes the loop on the bad input. Reading with `nextLine()` as in the sample **consumes the whole line** before parsing, so every check moves forward.

**(c) Chaining `if` statements without a clear exit path.** As menu options grow, independent `if` blocks become hard to track. `switch` maps each choice cleanly to one action, while the outer loop handles repetition.

**(d) Catching `Exception` and ignoring it.** Swallowing all exceptions makes user typos indistinguishable from code bugs. `readIntInRange()` catches only `NumberFormatException`, the expected input-parsing error.

**(e) Skipping EOF checks.** Calling `scanner.nextLine()` with no lines remaining throws `NoSuchElementException`. Check `hasNextLine()` and signal EOF cleanly to the caller.

**(f) Confusing integers with floating-point numbers.** `1.0` equals 1 numerically, yet is not a valid integer string for `Integer.parseInt()`; accepting decimals requires an explicit conversion rule rather than silent rounding.

**(g) Off-by-one bounds.** Choices `0` and `3` are valid; `-1` and `4` are invalid. Points `1` and `1000` are valid; `0` and `1001` are not. Testing exact boundaries catches `<` vs. `<=` mistakes.

**(h) Creating multiple Scanners for `System.in`.** Separate scanners maintain separate buffers and compete over the same input stream; share one scanner across the interactive session. Closing `Scanner(System.in)` closes the underlying stream; closing it at the end of `main` fits a standalone practice program.

**(i) Leaving an infinite menu with no exit path.** `while (true)` is appropriate only when there are well-defined exits: choice 0, EOF, or handled fatal errors.

## 12. Ways to improve after it works

When expanding the menu, keep the core principles intact:

1. **Extract each action into a method** once branches grow long. For example, `showTotal(total)` or `addPoints(scanner, total)` should have a clear contract: whether it mutates state and how it handles EOF.
2. **Keep business logic separate from I/O** as the app grows. Point addition can become a pure method testable without `Scanner`.
3. **Add a point-history view** if the problem requires recording individual changes; that calls for a list or record type instead of just a sum variable.
4. **Enforce a cap on total or use `Math.addExact()`** if additions are unbounded and overflow safety is critical.
5. **Standardize message language/formatting** and user docs if the menu serves broader audiences.
6. **Write automated input tests** using fixed strings via `new Scanner(String)` or piped input files compared against stdout. Larger suites can use JUnit, though it is optional for core Java.

Do not over-engineer too early: first make sure the simple menu **redisplays cleanly, validates inputs properly, leaves total unchanged on errors, and exits cleanly**.

## 13. Summary checklist

Before considering the program finished, verify:

- Does the menu show clear choices `0`–`3`, and do `switch` cases match the prompts?
- Does `while` have clean exits for both `0` and EOF?
- Do letters, blank lines, out-of-range numbers, and numbers beyond `int` avoid crashing the program?
- Does invalid data **re-prompt the same field** without adding points or changing the total?
- After choices 1, 2, and 3, does the menu reappear?
- Does `total` persist across iterations unless intentionally added to or reset?
- Is `0` to exit distinct from `null` on EOF?
- Does the program use one `Scanner` with an appropriate lifetime, avoiding `nextInt()` + `nextLine()` newline bugs?
- Did I run `javac`/`java` and verify valid scenarios, invalid inputs, and EOF?

**Remember:** A solid console menu needs **a loop to stay interactive, a `switch` to dispatch actions, input validation right at the input boundary, and clear exit paths**. Getting those four parts right makes your exercise predictable even when users enter bad input.
