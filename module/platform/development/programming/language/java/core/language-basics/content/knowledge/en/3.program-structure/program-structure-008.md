# Indentation to Express Structure and Avoid Scope Misunderstandings in Java

When reading Java code, **indentation** helps the human eye see which statements belong to a class, method, `if` branch, or loop. However, unlike some programming languages, Java **does not use indentation depth to determine block scope**. Curly braces `{ }` and syntactic structure are what the compiler uses to understand the program.

Therefore, a Java snippet **can be neatly indented yet do the wrong thing** if you omit curly braces. This lesson helps you read and write clear code blocks, understand variable scope, and prevent logic bugs caused by misleading layout. Examples are compatible with JDK 17 or later.

## 1. Core Rule: Indentation Is for Humans, Braces Are for Syntax

Compare two snippets:

~~~java
int score = 4;

if (score >= 5) {
    System.out.println("Dat");
    System.out.println("Cap chung chi");
}
~~~

With `score = 4`, **no lines are printed**: both statements are inside the `if` block, the condition is false, so the block is skipped.

But if you omit the braces:

~~~java
int score = 4;

if (score >= 5)
    System.out.println("Dat");
    System.out.println("Cap chung chi");
~~~

Output:

~~~text
Cap chung chi
~~~

Java interprets the second snippet as equivalent to:

~~~java
if (score >= 5) {
    System.out.println("Dat");
}
System.out.println("Cap chung chi");
~~~

Only **the single statement immediately following `if`** is controlled when there is no `{ }` block. The second `println` line always runs, **regardless of how many spaces it is indented**.

> Convention to adopt: **always use `{ }` with `if`, `else`, `for`, and `while`**, even when a branch has only one statement. This is an error-prevention convention, not a syntactic requirement in every case.

## 2. Class, Method, and Block Structure

Common indentation levels when reading a Java file:

~~~java
public class LayoutExample {                  // Level 0: class
    public static void main(String[] args) {  // Level 1: method
        int score = 8;                        // Level 2: inside method

        if (score >= 5) {                     // Level 2: if statement
            System.out.println("Dat");        // Level 3: inside if block
        }

        System.out.println("Hoan tat");        // Level 2: outside if block
    }
}
~~~

On JDK 17, save the snippet above in `LayoutExample.java`, compile, and run:

~~~bash
javac -encoding UTF-8 LayoutExample.java
java LayoutExample
~~~

Output:

~~~text
Dat
Hoan tat
~~~

Read the braces before reading the whitespace:

| Indicator | Role in Java | Common misconception |
| --- | --- | --- |
| `{` | Starts a block, class body, or method body depending on context | Relying only on indentation column |
| `}` | Ends the matching block | Failing to notice a variable is now out of scope |
| `;` | Terminates certain kinds of statements/declarations | Putting a stray `;` right after `if` |
| Leading whitespace | Formats code for readability | Thinking it creates a block on its own |
| `if` / `else` | Determines execution branch | Assuming `else` always pairs with the `if` at the same indentation |
| `for` / `while` | Repeats one statement or one block | Assuming all indented lines repeat |

In source code, `{ }` must match properly. In a Java-aware editor, placing the cursor on one brace usually highlights its matching partner.

## 3. Practice Program: Clear Indentation to Reveal Scope

Create the file **`IndentScopeDemo.java`**:

~~~java
public class IndentScopeDemo {
    static String classify(int score) {
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException(
                    "Diem phai nam trong khoang 0..10");
        }

        if (score >= 8) {
            return "Gioi";
        }

        if (score >= 5) {
            return "Dat";
        }

        return "Can co gang";
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println(
                    "Cach dung: java IndentScopeDemo <diem>");
            return;
        }

        try {
            int score = Integer.parseInt(args[0]);
            String result = classify(score);

            System.out.println("Diem: " + score);
            System.out.println("Xep loai: " + result);
            System.out.println("Hoan tat");
        } catch (NumberFormatException ex) {
            System.out.println("Loi: diem phai la so nguyen");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        }
    }
}
~~~

### Running on Windows PowerShell or Linux

In the directory containing `IndentScopeDemo.java`, both environments work with:

~~~bash
java -version
javac -version
javac -encoding UTF-8 IndentScopeDemo.java
java IndentScopeDemo 8
~~~

Output:

~~~text
Diem: 8
Xep loai: Gioi
Hoan tat
~~~

Another case:

~~~bash
java IndentScopeDemo 4
~~~

~~~text
Diem: 4
Xep loai: Can co gang
Hoan tat
~~~

**Point to note:** the statement `System.out.println("Hoan tat");` sits after the classification call and after valid input parsing. It runs for every valid score, independent of the `score >= 8` or `score >= 5` branches.

The `return` statements in `classify` end the method immediately at the matching branch. Therefore, after `return "Gioi";`, the program does not continue checking `if (score >= 5)` in **the same call to `classify`**.

**Input test table:**

| Command | Primary result |
| --- | --- |
| `java IndentScopeDemo 10` | `Xep loai: Gioi` |
| `java IndentScopeDemo 8` | `Xep loai: Gioi` |
| `java IndentScopeDemo 7` | `Xep loai: Dat` |
| `java IndentScopeDemo 5` | `Xep loai: Dat` |
| `java IndentScopeDemo 4` | `Xep loai: Can co gang` |
| `java IndentScopeDemo 0` | `Xep loai: Can co gang` |
| `java IndentScopeDemo -1` | `Loi: Diem phai nam trong khoang 0..10` |
| `java IndentScopeDemo 11` | `Loi: Diem phai nam trong khoang 0..10` |
| `java IndentScopeDemo abc` | `Loi: diem phai la so nguyen` |
| `java IndentScopeDemo` | Prints usage instructions |

The two `catch` blocks separate **string-to-number parsing errors** from **out-of-range number errors**. `NumberFormatException` is a subclass of `IllegalArgumentException`, so the more specific catch branch must come before the more general one.

## 4. Subtle Bug: Which `if` Does `else` Belong To?

Look at a snippet without braces:

~~~java
boolean registered = false;
int score = 3;

if (registered)
    if (score >= 5)
        System.out.println("Du dieu kien");
    else
        System.out.println("Chua dat diem");
~~~

Even if the author meant `else` to pair with `if (registered)`, in Java **`else` binds to the nearest `if` that can syntactically match it**. Here, `else` belongs to `if (score >= 5)`, and the entire inner branch does not run because `registered` is `false`.

**Output: no lines printed.**

Rewrite it to make the intent explicit:

~~~java
boolean registered = false;
int score = 3;

if (registered) {
    if (score >= 5) {
        System.out.println("Du dieu kien");
    } else {
        System.out.println("Chua dat diem");
    }
} else {
    System.out.println("Chua dang ky");
}
~~~

**Output:**

~~~text
Chua dang ky
~~~

Curly braces do not merely make code pretty: they **define the exact branches** the programmer intends to pair together.

## 5. Variable Scope Does Not Depend on Indentation

A local variable declared in a block is normally usable only within that corresponding scope:

~~~java
int score = 7;

if (score >= 5) {
    String message = "Dat";
    System.out.println(message); // Valid.
}

// System.out.println(message); // Does not compile:
// message went out of scope at the closing } of if.
~~~

To use a result outside the block, declare the variable in the appropriate outer scope and assign its value inside:

~~~java
int score = 7;
String message;

if (score >= 5) {
    message = "Dat";
} else {
    message = "Can co gang";
}

System.out.println(message); // Dat
~~~

The compiler verifies that `message` has been definitely assigned before use (*definite assignment*). Adding spaces or indenting the `println` line to the right **cannot extend a variable's scope**.

Pairs of `{ }` can create standalone blocks inside a method:

~~~java
{
    int temporary = 5;
    System.out.println(temporary); // 5
}
// System.out.println(temporary); // The name temporary is not visible here.
~~~

Therefore, when you encounter `cannot find symbol` for a local variable, check the **brace pairs and where the variable was declared**, not just the spacing.

## 6. Loops Missing Braces Also Cause Confusion

Example:

~~~java
int i;
for (i = 0; i < 3; i++)
    System.out.println("Lan " + i);
    System.out.println("Ket thuc");
~~~

Even though both `println` lines have the same indentation, the `for` loop controls only **the first call**. Output:

~~~text
Lan 0
Lan 1
Lan 2
Ket thuc
~~~

If you want both calls to execute on every iteration, place them inside a block:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("Lan " + i);
    System.out.println("Ket thuc");
}
~~~

Then `Ket thuc` is printed **three times**, each right after `Lan i`. That logic change comes from **curly braces**, not from adding whitespace.

Similarly with `while`, without braces only the single statement right after the loop repeats. If that statement does not move the condition toward termination, the program can loop forever. Writing explicit blocks helps make both the **condition** and the **control-variable update** visible.


## 7. A Formatter Reveals Actual Structure, Not Your Intent

An IDE formatter indents according to the **existing Java syntax**. If it moves a statement out to the outer level of an `if` or `for`, that is a cue to re-read where `{` and `}` sit; the formatter cannot know on its own whether you meant that statement to run only in the branch or every time.

When reviewing formatted code, check in this order:

1. **Compare brace pairs with intent:** which statements lie inside the class, method, branch, and loop blocks?
2. **Inspect tokens around conditions:** a `;` after `if (...)` or `while (...)` can create an empty body even when the layout looks reasonable.
3. **Test both paths:** run true and false condition cases, or 0 and multiple loop iterations, then compare actual behavior against expectations.

For example, a `println` statement aligned by the formatter at the same level as `if` is still **outside** the branch if a closing brace precedes it. To change behavior, you must fix the **brace or statement placement** and retest; adjusting whitespace alone is not enough.

## 8. Practical Formatting Guidelines

To keep Java 17 code readable in study and collaboration:

1. **Indent consistently**, typically choosing **4 spaces** per block level; avoid arbitrarily mixing tabs and spaces in the same file.
2. **Always use curly braces** for conditional statements and loops, even when the block has only one line.
3. Place the opening brace `{` consistently on the `class`, method, or `if` declaration line according to one style; align `}` with the corresponding column.
4. Do not use indentation to "imply" scope without real braces.
5. Whenever you add or move a brace, recompile and run both normal cases **and boundary cases**.
6. Use an automatic Java formatter when available, but **re-read the logic**: a formatter cannot infer your business intent.

Example of a readable layout:

~~~java
if (score >= 5) {
    System.out.println("Dat");
} else {
    System.out.println("Chua dat");
}
System.out.println("Hoan tat");
~~~

This is a **formatting convention**, not mandatory indentation syntax. The machine reads structure via keywords, separators, and blocks; human readers benefit from layout that faithfully mirrors that structure.

## 9. Self-Check Exercises

**Exercise 1 — Predict:** With `score = 4`, what will `if (score >= 5) println("Dat"); println("Xong");` (two separate statements) print if the second line is indented under `if` without braces?

*Answer:* `Xong`. Only the first statement depends on the condition.

**Exercise 2 — Fix the branch:** Take the `registered` example in section 4 and change it to `registered = true` and `score = 3`. After the braced revision, what output is printed?

*Answer:* `Chua dat diem`.

**Exercise 3 — Scope:** Why does placing `System.out.println(message);` after the `if` block in section 5 fail to compile? Fix it so the program can print `message` for both passing and non-passing scores.

*Answer:* The variable declared inside the block went out of scope; declare it before `if` and assign it in both `if` and `else`.

**Exercise 4 — Loop:** A student wants to print `Lan 0 - Xong`, `Lan 1 - Xong`, `Lan 2 - Xong`, with the two parts on two lines per iteration. Add `{ }` properly to the `for` loop and predict how many times `Xong` is printed.

*Answer:* Put both `println` calls inside the `for` block; `Xong` is printed three times.

**Exercise 5 — Debug:** Run `java IndentScopeDemo 5`, then try changing the condition from `score >= 5` to `score > 5`. What changes? Is that an indentation error or a condition error?

*Answer:* Score 5 changes from `Dat` to `Can co gang`; this is a **condition logic** error, showing that properly indented code can still have wrong business logic.

### Lesson Checklist

- [ ] Explain that Java relies on `{ }` and syntactic structure, not indentation depth, to determine blocks.
- [ ] Always use curly braces when writing `if`/`else` and loops.
- [ ] Recognize that a second statement is not controlled if `if` lacks a block.
- [ ] Understand that `else` pairs with the nearest syntactically eligible `if`.
- [ ] Identify where a local variable's scope begins and ends using braces.
- [ ] Spot `if (condition);` creating an unintended empty branch.
- [ ] Compile and run `IndentScopeDemo.java` on JDK 17+ with boundary values.

**Key takeaway:** Indentation is a **map for human readers**, whereas curly braces `{ }` and syntax rules are the **structure Java actually executes**. When the two disagree, the machine follows the syntax, not the intent implied by whitespace.
