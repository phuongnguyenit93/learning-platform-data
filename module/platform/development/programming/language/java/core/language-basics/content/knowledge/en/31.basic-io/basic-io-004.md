# Reading Program Arguments from `String[] args` — Java 17+

## 1. What is `String[] args`?

A Java application can receive data as soon as it is invoked from the **command line**. The familiar entry point is:

~~~java
public static void main(String[] args) {
    // Read and process the arguments passed by whoever runs the program.
}
~~~

- `main` is the entry-point method of a Java program under the traditional execution model.
- `String[] args` is a **formal parameter** of type **array of strings**. Each element `args[i]` holds one **application argument** passed by the user after the main class name.
- `args.length` indicates the number of elements actually passed.
- Indices start at `0` and end at `args.length - 1`.
- Data in `args` is initially **`String`**, even when the user types `123` or `true`. The program must convert it to another type if needed.

Example:

~~~bash
java -cp . CommandLineArgsDemo Lan 3 --upper
~~~

Here, the array inside `main` has:

~~~text
args.length = 3
args[0]     = "Lan"
args[1]     = "3"
args[2]     = "--upper"
~~~

The quotation marks in the descriptive block above only illustrate string values; they are **not characters Java automatically adds to the value**. In the complete example in section 9, the program receives a user's name, a greeting count, and an uppercase option.

## 2. Distinguishing `java` launcher options from application arguments

Consider the command:

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

| Part of command | Role |
|---|---|
| `java` | The Java launcher |
| `-cp .` | Option for the **launcher/JVM**: sets the classpath root to the current directory |
| `CommandLineArgsDemo` | Name of the class containing `main` |
| `"Lan Anh"` | **First application argument** (index 0); shell quotes group the two words |
| `2` | **Second application argument** (index 1), which in Java is the string `"2"` |

**The main class name is not in `args`.** Likewise, the `-cp` option placed before the class name is not an element of `args`. The command above produces `args.length == 2`.

Parameters **after the main class name** are passed to the application. If you type `--upper` after the class name, Java does not automatically recognize it as a business flag: the **application code** itself must inspect `args[i]` and decide what it means.

JVM options such as `-ea` or `-Dkey=value` generally must be placed **before the main class name** when you want the JVM to process them. If placed after the class name, they may become strings inside the program's `args`, depending on how it is launched.

## 3. Iterating over the array and checking length before reading

Looping while preserving **order and index**:

~~~java
for (int i = 0; i < args.length; i++) {
    System.out.println("args[" + i + "]=" + args[i]);
}
~~~

Looping when only values are needed:

~~~java
for (String argument : args) {
    System.out.println(argument);
}
~~~

When you want to read a required position, you must verify that the position exists:

~~~java
if (args.length == 0) {
    System.out.println("No arguments");
    return;
}
String first = args[0];
System.out.println(first);
~~~

If the user runs the program **without passing any arguments**, `args.length == 0` and accessing `args[0]` will throw `ArrayIndexOutOfBoundsException`. This is an error you must prevent with a conditional check, not a case where Java automatically supplies a fallback empty string.

With the standard Java launcher, `main` is called with a `String[]` array containing the application arguments (possibly empty). If other code calls `main(null)` directly, that is a separate situation created by the caller, not standard CLI behavior to rely on.

## 4. Every element starts out as a string

Suppose:

~~~bash
java -cp . CommandLineArgsDemo Lan 3
~~~

`args[1]` has type `String` and value `"3"`, not the integer `3`. Do not perform arithmetic multiplication on `args[1]` before converting it.

~~~java
int times;
try {
    times = Integer.parseInt(args[1]);
} catch (NumberFormatException ex) {
    System.out.println("Invalid integer");
    return;
}
~~~

- `Integer.parseInt("3")` returns `3`, an `int`.
- `Integer.parseInt("abc")` throws `NumberFormatException`.
- `Integer.parseInt("3.5")` also cannot be parsed into an `int` using decimal integer syntax.
- `Integer.parseInt(" 3 ")` does not automatically strip surrounding whitespace; an explicit rule is needed, such as `args[1].strip()` before parsing if the contract allows it.
- If the text represents a number outside the range of `int`, `parseInt` can also throw `NumberFormatException`.

Successful conversion is **not enough** to confirm valid input. If the application's `times` parameter is only allowed in `1..5`, you must also check:

~~~java
if (times < 1 || times > 5) {
    System.out.println("times must be 1..5");
    return;
}
~~~

Validating the value domain of input data **must always run**; do not replace it with an `assert` statement that could be disabled when starting the JVM.

## 5. Required arguments, optional arguments, and order

A CLI program should publish a clear **input contract**. For example, this lesson uses the convention:

~~~text
java -cp . CommandLineArgsDemo <name> <times> [--upper]
~~~

| Position | Required? | Meaning | Example |
|---|---|---|---|
| `args[0]` | Yes | Name of the person to greet, must not be all whitespace | `Lan`, `"Lan Anh"` |
| `args[1]` | Yes | Greeting count, decimal integer from 1 to 5 | `3` |
| `args[2]` | No | Only supported flag: `--upper` | `--upper` |

Because there are two required arguments and one optional argument, the valid count is **2 or 3**. How to check:

~~~java
if (args.length < 2 || args.length > 3) {
    // Print usage and reject the request.
}
~~~

Position matters: `CommandLineArgsDemo 3 Lan` **is not automatically swapped** into name `Lan` and three greetings. The program may fail trying to parse `Lan` as an `int` because the second position must be a number.

`[--upper]` in the **usage** guide is **documentation notation** indicating the option may be omitted; the user **does not type the square brackets** unless the application specifies otherwise.

The `--upper` option is defined by the program itself. The Java launcher does not automatically provide parsing for `--name`, `--times`, or flexible flag ordering. To support more complex forms, you must write a parser yourself or use a suitable CLI library.

## 6. Shell quotes, whitespace, and Unicode

When you want to pass a name containing spaces as **a single argument**, you must use the quoting syntax appropriate for your shell:

**Bash (Linux/macOS):**

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

**PowerShell (Windows):**

~~~powershell
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

In both commands above, `args[0]` is the string `Lan Anh` with a space in the middle. The `"` characters tell the shell to group the words and normally do not become part of the value of `args[0]`.

If you omit the quotes:

~~~bash
java -cp . CommandLineArgsDemo Lan Anh 2
~~~

then the application receives **three arguments**: `"Lan"`, `"Anh"`, `"2"`. Under this lesson's contract, the program will attempt to parse `"Anh"` as the greeting count and reject it.

Special characters such as spaces, `*`, `$`, quotation marks, and backslashes follow different rules across shells. Do not rely on a Bash escape sequence assuming it behaves identically in PowerShell. For common examples, double quotes around names with spaces are sufficient.

Java supports Unicode strings in `args`. When entering Vietnamese text, the console and font/terminal encoding configuration must support Unicode to display characters accurately. The complete program uses ASCII data for stdout blocks that require exact matching.

## 7. Normalizing, validating, and rejecting invalid input

Distinguish between **reading an argument** and **valid input**:

~~~java
String name = args[0].strip();

if (name.isEmpty()) {
    System.out.println("name must not be blank");
    return;
}
~~~

`String.strip()` (available since Java 11) removes certain Unicode whitespace characters according to `Character.isWhitespace`. If the name contains only whitespace recognized by `strip`, the remaining string is empty and rejected.

For `times`, two layers of validation are needed: (1) it parses as an `int`; (2) its value falls within the allowed range. For the flag:

~~~java
boolean upper = false;
if (args.length == 3) {
    if (!"--upper".equals(args[2])) {
        System.out.println("unknown option");
        return;
    }
    upper = true;
}
~~~

Compare strings with `String.equals` instead of `==`: `==` checks whether two references point to the same object, not whether the string contents match.

**Do not pass passwords/tokens directly in CLI arguments** if the environment may expose the process list, shell history, or command logs. In real applications, do not blindly echo all of `args` when they might contain sensitive data. The demo only prints non-sensitive arguments provided for learning syntax.

## 8. Returning status to the operating system: exit codes

Command-line applications often need to distinguish success from invalid syntax or input. A common convention:

- **Exit status 0**: processing succeeded.
- **Non-zero exit status**, such as 2: invalid input or invocation according to the program's contract.

~~~java
public static void main(String[] args) {
    int status = run(args);
    if (status != 0) {
        System.exit(status);
    }
}
~~~

`System.exit(2)` terminates the JVM with code 2; this is a call at the application boundary and **should not be placed inside a library utility method** where the caller would lose the chance to handle it.

The demo program below intentionally prints usage messages to **stdout** so exact stdout matching is possible in learning scenarios. In real-world CLIs, errors and usage are typically printed to **stderr** via `System.err`, while successful data output is printed to `System.out`; define the contract clearly when applying this. Also note: the shell prompt and exit code are not part of stdout content.

## 9. Complete Java 17+ program

Create the file with the exact name **`CommandLineArgsDemo.java`**:

~~~java
import java.util.Locale;

public final class CommandLineArgsDemo {
    private CommandLineArgsDemo() {}

    static int run(String[] args) {
        // Illustrate the position and content of each input element.
        System.out.println("args.length=" + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }

        // Two required arguments, one optional.
        if (args.length < 2 || args.length > 3) {
            System.out.println("error: expected 2 or 3 arguments");
            printUsage();
            return 2;
        }

        String name = args[0].strip();
        if (name.isEmpty()) {
            System.out.println("error: name must not be blank");
            return 2;
        }

        int times;
        try {
            times = Integer.parseInt(args[1]);
        } catch (NumberFormatException ex) {
            System.out.println("error: times must be an integer");
            return 2;
        }

        if (times < 1 || times > 5) {
            System.out.println("error: times must be 1..5");
            return 2;
        }

        boolean upper = false;
        if (args.length == 3) {
            if (!"--upper".equals(args[2])) {
                System.out.println("error: unknown option " + args[2]);
                return 2;
            }
            upper = true;
        }

        System.out.println("name=" + name);
        System.out.println("times=" + times);
        System.out.println("upper=" + upper);

        String message = "Hello, " + name + "!";
        if (upper) {
            message = message.toUpperCase(Locale.ROOT);
        }
        for (int i = 0; i < times; i++) {
            System.out.println(message);
        }
        return 0;
    }

    private static void printUsage() {
        System.out.println(
                "usage: java -cp . CommandLineArgsDemo <name> <times> [--upper]");
    }

    public static void main(String[] args) {
        int status = run(args);
        if (status != 0) {
            System.exit(status);
        }
    }
}
~~~

**Requirements:** JDK 17 or later, no Maven, Gradle, external libraries, or preview features needed. Save as UTF-8. `run` handles input processing, while `main` is the entry point and returns the exit code on error. The program **does not guess** the name or greeting count if arguments are missing.

### Compiling

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 CommandLineArgsDemo.java
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\CommandLineArgsDemo.java
~~~

Compilation produces `CommandLineArgsDemo.class` in the current directory. Use `-cp .` when running from the directory containing the `.class` file.

### Valid run — name with a space

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

The same syntax works in PowerShell with these illustrative arguments.

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan Anh
args[1]=2
name=Lan Anh
times=2
upper=false
Hello, Lan Anh!
Hello, Lan Anh!
~~~

### Valid run — using the `--upper` flag

~~~bash
java -cp . CommandLineArgsDemo Lan 3 --upper
~~~

**Exact expected stdout:**

~~~text
args.length=3
args[0]=Lan
args[1]=3
args[2]=--upper
name=Lan
times=3
upper=true
HELLO, LAN!
HELLO, LAN!
HELLO, LAN!
~~~

`Locale.ROOT` ensures consistent uppercase conversion for the example message, avoiding case-conversion differences caused by the machine's default locale. Both valid commands return **exit status 0**.

### Running with missing arguments

~~~bash
java -cp . CommandLineArgsDemo
~~~

**Exact expected stdout:**

~~~text
args.length=0
error: expected 2 or 3 arguments
usage: java -cp . CommandLineArgsDemo <name> <times> [--upper]
~~~

Because `args[0]` is not read when there are not enough elements, the program avoids `ArrayIndexOutOfBoundsException`. It prints usage instructions and exits with **exit status 2**.

### Running with an invalid number

~~~bash
java -cp . CommandLineArgsDemo Lan abc
~~~

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan
args[1]=abc
error: times must be an integer
~~~

`Integer.parseInt("abc")` throws `NumberFormatException`. The program catches the exception in the right place to explain the input requirement and returns **exit status 2**.

### Running with an out-of-range number

~~~bash
java -cp . CommandLineArgsDemo Lan 0
~~~

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan
args[1]=0
error: times must be 1..5
~~~

The value `0` parses successfully, yet is invalid under the `1..5` greeting count rule. Therefore it still returns **exit status 2**. This is a clear example that **successful type conversion does not mean valid data**.

## 10. Reading multiple arguments and CLI design choices

If an application accepts an **arbitrary-length list of names**, you can use a loop:

~~~java
for (String name : args) {
    System.out.println("Hello, " + name + "!");
}
~~~

This is illustrative code inside an appropriate `main`, differing from the contract of `CommandLineArgsDemo` in section 9. For a variable-length list, an enhanced `for` loop fits when only values are needed; an indexed `for` loop fits when positions matter.

In real projects, clearly define the input style:

| CLI style | Example | What you must handle yourself |
|---|---|---|
| Positional arguments | `tool input.txt 3` | Argument count, order, type conversion |
| Optional flag | `tool input.txt --verbose` | Supported flags, default values |
| Key-value option | `tool --count=3` | Parsing keys, values, and duplicate keys |
| Multiple items | `tool Alice Bob Carol` | Variable count, whether names need quoting |
| Interactive input | `Scanner(System.in)` | Reading from stdin at runtime, **not `args`** |

`String[] args` serves data **passed at launch time**, whereas `System.in`/`Scanner` serves data **read while the program runs**. They are two different input sources that can be combined, but do not automatically replace one another.

If a CLI grows complex with multiple subcommands, valued flags, help text, or standard formatting, a command-line parsing library can be helpful; first, understand accurately that `args` is an array of strings.

## 11. Common mistakes

| Mistake | Cause | How to handle |
|---|---|---|
| Reading `args[0]` immediately without checking `length` | Zero arguments causes `ArrayIndexOutOfBoundsException` | Check for sufficient element count |
| Assuming `args[1]` is already an `int` | Elements always have type `String` | Call `Integer.parseInt` and catch errors |
| Treating a parsed number as immediately valid | Value may be negative, 0, or out of bounds | Additionally validate the value domain |
| Mistaking the class name or `-cp` for an argument | They are part of the launcher command | Application arguments start **after the class name** |
| Typing a multi-word name without quotes | The shell splits it into multiple elements | Use quotes according to shell syntax |
| Using `args[0] == "--upper"` | `==` compares references | `"--upper".equals(args[0])` |
| Thinking Java automatically understands `--flag` options | `args` is just an array of strings | Write a parser for supported flags |
| Silently accepting unknown flags | User typos go unnoticed | Reject and report an error |
| Putting `-ea` after the class name expecting JVM assertions enabled | Arguments after the class name are usually passed to `args` | Put JVM options before the class name |
| Putting passwords in CLI arguments and echoing all args | Can leak in shell history/logs/process list | Avoid passing/logging sensitive data this way |
| Using `assert` to validate required input | Assertions can be disabled | Use `if`, exceptions, and always-on error checks |
| Printing errors without telling the user the expected syntax | Hard to fix the invocation | Write a specific message and appropriate usage |

## 12. Exercises with answers

**A — Identifying the array.** Given the command:

~~~bash
java -cp . CommandLineArgsDemo "Mai Anh" 2 --upper
~~~

What is `args.length`, and what is `args[0]`?

**Answer:** `args.length == 3`; `args[0]` is `"Mai Anh"`, `args[1]` is `"2"`, and `args[2]` is `"--upper"`.

**B — First argument.** With `java -cp . CommandLineArgsDemo`, which operation fails if executed immediately?

**Answer:** reading `args[0]`, because the array has no elements. You must check `args.length` first.

**C — Type conversion.** Why can `Integer.parseInt(args[1])` fail?

**Answer:** because the user might pass a string that does not represent a valid `int`, such as `"abc"` or a value outside the `int` range. You must catch `NumberFormatException` or handle it per the contract.

**D — Wrong argument order.** Is `java -cp . CommandLineArgsDemo 3 Lan` valid under this lesson's interface?

**Answer:** **No**. `args[0]` is interpreted as the name `3`; `args[1]` is `Lan`, which cannot be parsed as an `int`.

**E — Two shells.** To pass the name `Lan Anh` as **a single element**, what must you do?

**Answer:** use appropriate quoting such as `"Lan Anh"` in the illustrative Bash/PowerShell commands.

**F — Optional flag.** In `java -cp . CommandLineArgsDemo Lan 2 --upper`, what decides the meaning of `--upper`?

**Answer:** the application code. The Java launcher passes that string into `args[2]`; in `run`, the code checks `"--upper".equals(args[2])`.

**G — Distinguishing command line and stdin.** Does `Scanner(System.in)` automatically re-read `args[0]`?

**Answer:** **No**. `System.in` is the runtime input stream; `args` is the array of arguments passed at startup.

## 13. Checklist and conclusion

- [ ] Know that `public static void main(String[] args)` receives the array of application argument strings.
- [ ] Read `args.length` and elements `args[i]` accurately.
- [ ] Do not confuse `-cp` or the main class name with the contents of `args`.
- [ ] Check the argument count before reading by index.
- [ ] Know that every `args[i]` starts out as a `String`.
- [ ] Know how to convert `String` to `int` and catch `NumberFormatException`.
- [ ] Validate the value domain after parsing.
- [ ] Understand how shell quoting groups arguments containing spaces.
- [ ] Distinguish required arguments from application-defined optional flags.
- [ ] Use `String.equals` to compare flags, not `==`.
- [ ] Know how to handle errors and non-zero exit codes for invalid invocations.
- [ ] Avoid printing secrets from the command line to logs or the console.
- [ ] Distinguish CLI arguments from runtime input read from `System.in`.
- [ ] Compile `CommandLineArgsDemo.java` with JDK 17+, run all valid/invalid cases, and verify exact stdout.

**Conclusion:** `String[] args` is **the array of argument strings supplied by the caller to a Java application**. Reading it properly starts with `args.length`, understanding **order and position**, converting types when needed, and **validating** data before processing. Shell quoting, JVM options, application-specific flags, and `System.in` input belong to different layers; distinguishing them clearly helps you write safe, user-friendly Java CLIs.