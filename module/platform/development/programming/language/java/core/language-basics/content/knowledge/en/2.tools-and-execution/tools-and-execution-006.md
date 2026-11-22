# Testing Expressions, Variables, and Methods with JShell

## 1. What is JShell used for?

**JShell** is a REPL (*Read–Evaluate–Print Loop*) tool bundled with the **JDK since Java 9**. You enter a small Java snippet (*snippet*), JShell compiles/evaluates it, displays the result or an error message, and lets you enter the next one. It is a fast way to check a calculation, try an API, create variables, and declare methods **without having to create a class with `main`**.

~~~text
You enter an expression / declaration / JShell command
                 |
                 v
       JShell processes Java snippet
                 |
        +--------+---------+
        |                  |
      Valid              Error
        |                  |
  Updates state       Prints diagnostics
  and shows result    rejects invalid snippet
        |
     Continue input
~~~

Unlike the OS terminal, the **`jshell>`** prompt is where you enter *Java code and internal JShell commands*. Commands like `javac`, `java`, `cd`, or `ls` are OS shell commands, not Java expressions to type directly at `jshell>`.

JShell is great for learning the language, exploring APIs, and building small examples. It does not replace writing structured programs, automated test suites, or build systems for real projects.

## 2. Preparing the JDK and launching JShell

This lesson uses **JDK 17 or higher**. Open Bash, PowerShell, or your IDE's terminal and type:

**Bash (Linux/macOS/Git Bash):**

~~~bash
java -version
javac -version
jshell --version
jshell
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
jshell --version
jshell
~~~

When the tool is ready, you typically see a welcome banner and a prompt similar to:

~~~text
|  Welcome to JShell -- Version 17...
|  For an introduction type: /help intro

jshell>
~~~

The version and greeting may vary by JDK distribution, options, and environment. You **only type the part after `jshell>`**, do not retype the prompt. If the system reports `jshell` is not recognized, check that you installed a **JDK** and that the JDK's `bin` directory is on `PATH`; having only a Java runtime or a wrong `PATH` setup can cause this tool to be missing.

JShell accepts a snippet as soon as the code fragment is complete. For multi-line declarations or unclosed blocks, it will wait for you to finish, usually with a continuation prompt.

## 3. Testing expressions and observing results

Type the following in turn into JShell:

~~~java
2 + 3 * 4
(2 + 3) * 4
7 / 2
7.0 / 2
"Java".toUpperCase()
Math.max(10, 25)
~~~

The resulting values in order are:

| Expression | Value | Why? |
|---|---|---|
| `2 + 3 * 4` | `14` | Multiplication has higher precedence than addition |
| `(2 + 3) * 4` | `20` | Parentheses change grouping |
| `7 / 2` | `3` | Both operands are integers, so integer division |
| `7.0 / 2` | `3.5` | Has a `double` operand |
| `"Java".toUpperCase()` | `"JAVA"` | Calls a `String` method |
| `Math.max(10, 25)` | `25` | Returns the larger number |

For example, JShell can display an expression result like:

~~~text
jshell> 2 + 3 * 4
$1 ==> 14
~~~

`$1` is an **auto-generated temporary variable** for the snippet result; in your session it might be `$2`, `$3`... if you have entered other commands. Therefore, when following a specific calculation, rely on the **value to the right of `==>`**, not on the `$n` sequence number.

JShell can also accept `;` at the end of appropriate snippets. For simple interactive expressions, omitting the semicolon is often more convenient; when writing Java programs in files, follow full statement syntax.

## 4. Creating, reading, and updating variables

Try a very small purchase calculation:

~~~java
int unitPrice = 120_000;
int quantity = 3;
int subtotal = unitPrice * quantity;
subtotal
quantity = 4;
subtotal
subtotal = unitPrice * quantity;
subtotal
~~~

Values worth checking:

| Step | Result |
|---|---|
| Create `unitPrice` and `quantity` | 120,000 and 3 |
| Compute `subtotal` the first time | 360,000 |
| Reassign `quantity = 4` | `quantity` is 4 |
| Read `subtotal` immediately afterward | **Still 360,000** |
| Reassign `subtotal = unitPrice * quantity` | **480,000** |

**Note:** the `subtotal` variable holds the **value computed at the time of assignment**, not a spreadsheet formula that automatically updates when `quantity` changes.

You can query JShell for the current state:

~~~text
/vars
~~~

It lists variables created in the session along with their types/values. If you enter:

~~~java
var label = "Don hang";
label.length()
~~~

`var` infers the `String` type from the initial value; Java still performs static type checking. `var` does not mean the variable is allowed to change to an arbitrary type later.

### When redeclaring a name

In JShell, you can try:

~~~java
int level = 1;
level = 2;
level
~~~

This is a **reassignment**, not a new declaration. JShell also supports replacing an already declared snippet with a new snippet in the interactive environment. However, do not confuse that convenience rule with being able to declare two duplicate local variables of the same name inside a normal Java block.

## 5. Declaring methods and calling them right away

A method lets you name a calculation and test the same logic with multiple arguments.

Enter into JShell:

~~~java
int square(int n) { return n * n; }
square(5)
square(-3)
~~~

The call results are `25` and `9`, respectively.

Next:

~~~java
long lineTotal(long unitPrice, int quantity) {
    if (unitPrice < 0 || quantity < 0) {
        throw new IllegalArgumentException("Gia hoac so luong am");
    }
    return Math.multiplyExact(unitPrice, (long) quantity);
}
lineTotal(120_000L, 3)
lineTotal(120_000L, 4)
~~~

The values are `360000` and `480000`, respectively. JShell lets you declare methods much like class members, without requiring you to type `public class Demo { ... }` for every test.

Check the method list:

~~~text
/methods
~~~

### How do expressions and method invocation statements differ?

- `square(5)` is a **method call expression** with return value `25`.
- `System.out.println(square(5));` is a **method invocation statement** producing the side effect of printing `25`; `println` returns `void`.
- `square` is defined in the JShell session state; you can call it again without redeclaring it on each line.

A method must match its return type: `int square(int n) { return "abc"; }` is rejected because `String` cannot become `int` in this `return` statement.

## 6. Quickly testing conditions, strings, and null

Enter in turn:

~~~java
int amount = 300_000;
boolean activeMember = true;
activeMember && amount >= 200_000
String customer = null;
customer != null && !customer.isBlank()
"Java".equals(customer)
~~~

The boolean expression values in order are **`true`**, **`false`**, **`false`**.

Analysis:

- `&&` is a short-circuit operator: when `customer != null` is `false`, the right-hand side is **not evaluated**, avoiding calling `isBlank()` on `null`.
- `"Java".equals(customer)` is safe when `customer == null`, because the object on which the method is called is a non-null string literal.
- For reference types, `==` checks whether two references point to the same object; it is not general string-content comparison in all cases.

Try a ternary condition:

~~~java
String category = amount >= 300_000 ? "LON" : "NHO";
category
~~~

The result is `"LON"`. When multiple branches or complex logic are needed, writing a method and using `if` is easier to read than nesting multiple ternary operators.

## 7. Recognizing errors from JShell feedback

JShell attempts to compile the snippet and reports errors when syntax, names, or types are invalid:

| Try in JShell | Result to recognize |
|---|---|
| `int age = "hai muoi";` | Type error: cannot assign `String` to `int` |
| `missing + 1` | Name error: variable `missing` is not yet defined |
| `square("5")` | Argument mismatch error for `square(int)` |
| `7 / 0` | Integer division by 0 causes `ArithmeticException` **at evaluation time** |
| `String s = null; s.length()` | `NullPointerException` when calling a method through `null` |
| `int x = Integer.MAX_VALUE; x + 1` | `int` overflow, resulting in `-2147483648` |

The exact wording of error messages can vary between JDK versions, so read the **error category** and offending snippet instead of memorizing the entire message string.

If an erroneous snippet is rejected, previously valid snippets normally remain in the session state; you can fix and re-enter it.

An expression can be **syntactically valid yet wrong in intent**. For instance, `7 / 2` returns `3` accurately per Java's integer division rules, yet if the problem requires `3.5`, you need to change the expression to `7.0 / 2`. JShell helps you observe behavior; it cannot guess your business requirements.

## 8. JShell commands to inspect and manage the session

Commands starting with `/` are **JShell-specific commands**, not division operators or Java syntax.

| Command | Effect |
|---|---|
| `/help` | View help and supported commands |
| `/help intro` | View the introductory guide |
| `/vars` | List variables in the session |
| `/methods` | List declared methods |
| `/types` | List defined types |
| `/imports` | View active imports |
| `/list` | Display snippets in the session with IDs |
| `/drop <id-or-name>` | Drop the selected snippet/declaration |
| `/reset` | Reset snippet state, useful when starting fresh |
| `/save <file>` | Save snippets as source text |
| `/open <file>` | Load and execute snippets from a file |
| `/exit` | Exit JShell |

Specific IDs depend on session history. Check `/list` to find the ID before using `/drop`. Do not pick IDs from someone else's screenshot.

Example:

~~~text
jshell> /vars
jshell> /methods
jshell> /list
jshell> /reset
jshell> /exit
~~~

After `/reset`, try calling `square(5)` again: if you have not re-entered the definition of `square`, JShell no longer finds that method. This demonstrates that JShell state **belongs to the interactive session**, and does not automatically become a class in a project.

## 9. Saving a JShell exercise for reuse

You can create a file named **`practice.jsh`** with an editor, containing the following Java snippets (no `package`, no `main` needed):

~~~java
int price = 50_000;
int count = 2;
int subtotal = price * count;
int discounted(long amount, int percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Du lieu khong hop le");
    }
    return (int) (amount * (100 - percent) / 100);
}
subtotal
discounted(subtotal, 10)
~~~

From JShell, in the directory containing the file, type:

~~~text
/open practice.jsh
/vars
/methods
~~~

**Values to confirm:** `subtotal = 100000`, `discounted(subtotal, 10) = 90000`. Display formatting also depends on JShell's feedback settings.

A `.jsh` file stores session snippets, not a Java class compilable with `javac practice.jsh`. If you want to directly save the snippets you typed in the session, use `/save practice.jsh`, and then you can `/reset` and `/open practice.jsh` to retry.

**Arithmetic limitation of the demo:** the `discounted` method in the file uses small amounts only for quick testing; `amount * (100 - percent)` can overflow `long`, and casting `long` to `int` can lose information. Therefore, do not use this snippet as a production billing module. In the final exercise, you will fix both the formula and the return type.

### Running a snippet file from the terminal

JShell can be launched with a snippet file, for example from the directory containing `practice.jsh`:

**Bash:**

~~~bash
jshell practice.jsh
~~~

**PowerShell:**

~~~powershell
jshell .\practice.jsh
~~~

Either way, the snippets are evaluated inside JShell; you do not get an application class file with `public static void main` merely by saving `.jsh`.

## 10. From JShell to a complete Java program

Once an idea has been tested, move it into a class with `main` for packaging and repeatable intentional execution. Create **`Experiment.java`**:

~~~java
public final class Experiment {
    private Experiment() {}

    static int square(int n) {
        return Math.multiplyExact(n, n);
    }

    public static void main(String[] args) {
        int value = args.length == 0 ? 5 : Integer.parseInt(args[0]);
        System.out.println("Binh phuong: " + square(value));
    }
}
~~~

Run with **JDK 17+**:

**Bash:**

~~~bash
javac --release 17 -encoding UTF-8 Experiment.java
java Experiment
java Experiment 7
~~~

**PowerShell:**

~~~powershell
javac --release 17 -encoding UTF-8 .\Experiment.java
java Experiment
java Experiment 7
~~~

Outputs from the two runs respectively:

~~~text
Binh phuong: 25
Binh phuong: 49
~~~

This lesson intentionally distinguishes: typing `square(5)` in JShell uses **session snippet state**; running `java Experiment` uses **a compiled class with `main`**. Both approaches complement each other rather than replacing one another in all situations.

With non-integer arguments, `Integer.parseInt` may throw `NumberFormatException`. With sufficiently large numbers, `Math.multiplyExact` detects `int` overflow with `ArithmeticException`. Running with 5 does not mean it works for every input.

## 11. A structured practice session

Follow these steps in a fresh JShell session, recording the **actual values**, not just the lines you type:

1. Open `jshell`; use `/help intro` if unfamiliar.
2. Compute `9 / 4` and `9.0 / 4`; explain why they are `2` and `2.25`.
3. Create `int price = 75_000;` and `int count = 2;`. Try `price * count`.
4. Change `count = 3;`; recheck the expression. If you assigned the result to a separate variable, observe whether the old value updates automatically.
5. Declare `long total(long unitPrice, int quantity)` with `Math.multiplyExact` and reject negative quantities; call the method with at least three inputs.
6. Type `/vars`, `/methods`, `/list` and point out which snippets were created.
7. Try one type error, one name error, and one runtime exception; note the differences.
8. Save the session with `/save`, reopen after `/reset`, and verify the tests can be reproduced.

### Suggested results table

| Test | Value/result to confirm |
|---|---|
| `9 / 4` | `2` |
| `9.0 / 4` | `2.25` |
| `75_000 * 2` | `150000` |
| `75_000 * 3` | `225000` |
| `Math.multiplyExact(75_000L, 3L)` | `225000` |
| `"hello".substring(1, 4)` | `"ell"` |
| `(String) null` then call `.length()` | `NullPointerException` when the method is called |

## 12. Exercises with solution guides

### Exercise A — write a score-checking method

Create `boolean passed(int score)` returning `true` when `score >= 50`; reject scores below 0 or above 100 with `IllegalArgumentException`.

One solution:

~~~java
boolean passed(int score) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("Score 0..100");
    }
    return score >= 50;
}
~~~

Test `passed(49)`, `passed(50)`, `passed(100)`, `passed(101)`. Expected: `false`, `true`, `true`, then an exception. The exact boundary `50` tests the difference between `>` and `>=`.

### Exercise B — fix return type and overflow

In `practice.jsh`, replace the billing calculation with a method returning `long`, constraining inputs and using safer operations:

~~~java
long discounted(long amount, int percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Invalid input");
    }
    long kept = 100L - percent;
    long numerator = Math.multiplyExact(amount, kept);
    return numerator / 100L;
}
~~~

`discounted(100_000L, 10)` gives `90000`. When `amount` is very large, `multiplyExact` can throw an exception instead of silently producing a wrong number. This is an **overflow detection approach**, not yet a solution to compute arbitrarily large `long` values; to compute accurately across the entire range you can use `BigInteger` or change the algorithm per business requirements.

### Exercise C — explain session state

After `/reset`, call `passed(50)` before redefining the method. Why does it not work?

**Answer:** the snippet defining `passed` belonged to the cleared session state; JShell does not store that method as a class on the classpath for future sessions to load automatically. Re-enter it, use `/open` with an appropriate snippet file, or write structured `.java` source code.

## 13. Completion checklist

- [ ] Can launch JShell from JDK 17+ in Bash or PowerShell.
- [ ] Distinguish terminal commands (`jshell`, `javac`, `java`) from internal JShell commands (`/vars`, `/list`, `/exit`).
- [ ] Can evaluate arithmetic, string, and boolean expressions and explain result types.
- [ ] Can declare, read, and update variables; understand variables store values, not self-updating formulas.
- [ ] Can declare and invoke methods with parameters/return types.
- [ ] Distinguish snippet compilation errors from evaluation-time exceptions.
- [ ] Use `/vars`, `/methods`, `/list`, `/reset` to inspect state.
- [ ] Save/open `.jsh`, understanding it is not equivalent to a Java class with `main`.
- [ ] Compile and run `Experiment.java` with expected output.
- [ ] Recognize JShell's limitations: suitable for quick experiments, does not replace project tests/builds.

**Conclusion:** JShell is a concise laboratory for learning how Java evaluates expressions, stores variables, and invokes methods. Observe actual results and errors, understand session state, and then move code that needs long-term testing and reuse into `.java` files with `main` or an appropriate test suite.
