# What Is the Java Language and How Is It Used to Express a Problem?

When first learning to program, many people see a program as just lines of text with `;`, `{}`, and hard-to-remember keywords. A more useful perspective is: **Java is a language for turning rules that solve a problem into instructions that a computer can verify and execute**. We need to understand the problem first, then choose the data, assign names, describe conditions, and compute using Java.

This lesson is for beginners learning core Java. You will build and run a small program without needing external libraries or frameworks.

## 1. What Will You Be Able to Do After This Lesson?

- Distinguish between the **Java language**, `.java` source files, the `javac` compiler, `.class` bytecode files, and the JVM.
- Turn a Vietnamese requirement into verifiable **input → processing rules → output**.
- Identify the roles of variables, data types, expressions, conditions, methods, and calls in a simple Java program.
- Create a Java class with `main`, compile it with `javac`, and run it with `java`.
- Test typical values, boundary values, and invalid data; distinguish between syntax errors, runtime errors, and logic errors.
- Understand the limits of a demonstration program: business rules must be defined by the problem, and Java does not automatically infer what the user wants.

## 2. What Is Java?

**Java** is a programming language with syntax and data type rules. With Java, we can write command-line applications, server systems, data processing tools, enterprise applications, and many other programs. Java is also a name commonly used to refer to the related ecosystem of tools, libraries, and runtime environment.

For example, the following two lines **express an intent** in Java syntax:

~~~java
int numberOfBooks = 3;
System.out.println(numberOfBooks * 25_000);
~~~

Read in Vietnamese: “There are 3 books, each costing 25,000 dong; print the total amount.” The result is `75000`. The machine does not understand “book” in the real-world sense; it operates on **the number 3**, **the number 25,000**, and multiplication according to the rules we write.

Java is not JavaScript. Their names are similar, but they are two different languages with different type systems, syntax, and execution environments.

### How Is Source Code Executed?

~~~mermaid
flowchart LR
    A["Problem and rules"] --> B["ShippingQuote.java<br/>source code"]
    B --> C["javac<br/>checks and compiles"]
    C --> D["ShippingQuote.class<br/>bytecode"]
    D --> E["JVM runs the program"]
    E --> F["Result or runtime error"]
~~~

- **`.java`:** a text file containing the source code that the programmer writes.
- **`javac`:** the Java compiler in the JDK; detects many syntax and data type errors, then produces bytecode if compilation succeeds.
- **`.class`:** a file containing bytecode for the JVM; it is not plain source code text.
- **JVM (Java Virtual Machine):** the execution environment for bytecode. The JVM also performs verification and many operations at runtime.
- **JDK (Java Development Kit):** the development toolkit, including `javac`, the `java` tool, and the components needed to build/run applications.

On another machine, compiled code can run with a compatible JVM if the Java version and dependencies match. Therefore, “write once, run anywhere” is a **portability goal**, not a guarantee that every Java program runs on every machine without configuration.

## 3. From a Vietnamese Problem Statement to a Processing Model

Suppose a delivery store sets an **illustrative rule** (not a real shipping carrier's rate table):

> Calculate the total amount the customer must pay. If the customer is a member or the order value is **500,000 VND or more**, shipping is free. Otherwise, the base shipping fee is **15,000 VND** for up to 5 km; starting from the 6th km, add **2,000 VND** for each km beyond 5 km.

We should not open the editor and write `if` right away. First, let us define the contract of the problem.

| Component | Name in Java | Meaning/Constraint |
| --- | --- | --- |
| Input 1 | `orderValueVnd`: `long` | Goods value, in **whole VND**, non-negative |
| Input 2 | `distanceKm`: `int` | Non-negative whole number of kilometers |
| Input 3 | `member`: `boolean` | Whether the customer is a member |
| Intermediate | `shippingVnd`: `long` | Shipping fee calculated from the three inputs |
| Output | `totalVnd`: `long` | Goods value + shipping fee |
| Data error | `IllegalArgumentException` | For example, negative price or distance |

Additional assumptions should be stated explicitly to avoid misunderstanding:

- Distance is rounded/recorded **as a whole number of km** before being passed into the program; this lesson does not handle decimal km yet.
- “500,000 or more” includes **exactly 500,000**, so use `>=`, not `>`.
- Free shipping only changes `shippingVnd`, not the goods value.
- The calculation does not include discounts, taxes, COD, or other fees because the problem does not ask for them.
- Invalid data must be reported as an error instead of silently turning into 0.

The choices above are **business rules**. Java only provides the way to represent them accurately.

### Writing the Algorithm in Words Before Writing Java

1. Receive the order value, the number of km, and the membership status.
2. Reject a negative order value or a negative number of km.
3. If the customer is a member **or** the order value is at least 500,000, the shipping fee is 0.
4. Otherwise, the shipping fee is 15,000 plus 2,000 for each km over 5.
5. Add the shipping fee to the order value and print both components along with the total.

This sequence of steps is the actual “solution”. Java helps turn the solution into executable statements, rather than inventing the algorithm for us.

## 4. How Does Java Express Each Part of the Problem?

| Idea in the problem | Java tool | Short example |
| --- | --- | --- |
| Store a value | Variable and type | `long orderValueVnd = 300_000L;` |
| Represent yes/no | `boolean` | `boolean member = false;` |
| Compute | Expression | `15_000L + 3L * 2_000L` |
| Compare against a threshold | Comparison operator | `orderValueVnd >= 500_000L` |
| Combine conditions | Logical operator | `member || orderValueVnd >= 500_000L` |
| Choose a branch | `if` / `else` or early `return` | Free or charged |
| Name a capability | Method | `calculateShipping(...)` |
| Receive data from the run command | `String[] args` parameter | `args[0]` holds the first text argument |
| Display results | `System.out.println(...)` | Print the total amount |

The underscores in a number like `300_000L` are only for readability: the value is still three hundred thousand. The suffix `L` indicates a `long` literal. The `||` operator means **OR**; only one condition needs to be true for the entire expression to be true.

You do not have to memorize every piece of syntax before understanding the problem; connect each statement to **something that needs to be done** in the requirement.

## 5. A Complete Java Program That Can Be Compiled and Run

Create a file named exactly **`ShippingQuote.java`** and copy all of the following code. The example is compatible with JDK 17 and later, and does not require features specific to Java 17.

~~~java
import java.util.Locale;

public class ShippingQuote {
    private static final long FREE_AT_VND = 500_000L;
    private static final long BASE_FEE_VND = 15_000L;
    private static final long EXTRA_KM_FEE_VND = 2_000L;

    static long calculateShipping(
            long orderValueVnd, int distanceKm, boolean member) {

        if (orderValueVnd < 0) {
            throw new IllegalArgumentException(
                    "Gia tri don khong duoc am");
        }
        if (distanceKm < 0) {
            throw new IllegalArgumentException(
                    "Khoang cach khong duoc am");
        }

        if (member || orderValueVnd >= FREE_AT_VND) {
            return 0L;
        }

        long extraKm = Math.max(0L, (long) distanceKm - 5L);
        long extraFee = Math.multiplyExact(
                extraKm, EXTRA_KM_FEE_VND);
        return Math.addExact(BASE_FEE_VND, extraFee);
    }

    public static void main(String[] args) {
        if (args.length != 3) {
            System.out.println(
                    "Cach dung: java ShippingQuote "
                    + "<tienHangVnd> <khoangCachKm> <true|false>");
            return;
        }

        try {
            long orderValueVnd = Long.parseLong(args[0]);
            int distanceKm = Integer.parseInt(args[1]);

            String memberText = args[2].toLowerCase(Locale.ROOT);
            if (!memberText.equals("true")
                    && !memberText.equals("false")) {
                throw new IllegalArgumentException(
                        "Thanh vien phai la true hoac false");
            }
            boolean member = Boolean.parseBoolean(memberText);

            long shippingVnd = calculateShipping(
                    orderValueVnd, distanceKm, member);
            long totalVnd = Math.addExact(
                    orderValueVnd, shippingVnd);

            System.out.println(
                    "Tien hang: " + orderValueVnd + " VND");
            System.out.println(
                    "Phi giao: " + shippingVnd + " VND");
            System.out.println(
                    "Tong cong: " + totalVnd + " VND");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Loi dinh dang so: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Loi du lieu: " + ex.getMessage());
        } catch (ArithmeticException ex) {
            System.out.println("Loi tran so: " + ex.getMessage());
        }
    }
}
~~~

**Explanation of the main blocks:**

- `public class ShippingQuote` defines the class containing the program. With this `public` class, the file name must be `ShippingQuote.java`.
- `main(String[] args)` is the standard entry point when running the class with `java ShippingQuote ...`. The arguments after the class name go into the `args` array as **strings**, not numbers yet.
- `Long.parseLong(...)` and `Integer.parseInt(...)` convert strings with valid numeric formatting into their corresponding numeric values; invalid data causes `NumberFormatException`.
- `calculateShipping` is a **method** that gives a name to the fee calculation operation. Its inputs and return value are declared right in its signature; the method does not read from the keyboard or print results itself.
- `if` checks the rules, and `return 0L` exits the method early when the free-shipping condition is met.
- `Math.max(0L, (long) distanceKm - 5L)` gives the number of km **beyond 5**, without producing a negative number; casting to `long` before subtraction ensures the calculation uses a wide enough type.
- `Math.multiplyExact` and `Math.addExact` perform integer arithmetic and throw `ArithmeticException` if the operation overflows the `long` type. This is a way to control risk as the problem scales.
- The three `catch` branches report three different error groups. `NumberFormatException` is a kind of `IllegalArgumentException`, so the more specific branch must be caught before the more general one; `ArithmeticException` is a different exception type.

This is **one executable Java class**, with no need to create an extra `package` or install libraries outside the JDK.

## 6. Compiling, Running, and Reading the Output

Open a terminal in the exact directory containing `ShippingQuote.java`. Check the JDK:

~~~bash
java -version
javac -version
~~~

Next:

~~~bash
javac -encoding UTF-8 ShippingQuote.java
java ShippingQuote 300000 8 false
~~~

Output:

~~~text
Tien hang: 300000 VND
Phi giao: 21000 VND
Tong cong: 321000 VND
~~~

Why is the shipping fee 21,000?

1. `member = false` and `300000 < 500000`, so free shipping does **not** apply.
2. The 8 km distance exceeds the 5 km base limit by **3 km**.
3. Extra fee: `3 * 2000 = 6000`.
4. Shipping fee: `15000 + 6000 = 21000`.
5. Total: `300000 + 21000 = 321000`.

Next, test the value **right at the threshold**:

~~~bash
java ShippingQuote 500000 8 false
~~~

~~~text
Tien hang: 500000 VND
Phi giao: 0 VND
Tong cong: 500000 VND
~~~

And a **member** customer:

~~~bash
java ShippingQuote 120000 8 true
~~~

~~~text
Tien hang: 120000 VND
Phi giao: 0 VND
Tong cong: 120000 VND
~~~

This way of running is a **command-line program**. Information passed through `args` is supplied by the user at launch, unlike interactively reading line by line from the keyboard. When you only want to learn language structure, taking input via arguments keeps the example concise and easy to repeat.

## 7. Reading a Line of Java by Its Meaning

Consider:

~~~java
long extraKm = Math.max(0L, (long) distanceKm - 5L);
~~~

We can read it from right to left:

1. `distanceKm` is an `int` integer.
2. `(long) distanceKm` converts the value to type `long`.
3. Subtract 5 to find the distance beyond the threshold.
4. `Math.max(0L, ...)` takes the larger value, avoiding a negative excess.
5. Assign the result to a variable named `extraKm` of type `long`.
6. The `;` ends this declaration/assignment statement.

This illustrates an **expression** (the part evaluated to a value) inside a **statement** (an action of the program).

Another example:

~~~java
if (member || orderValueVnd >= FREE_AT_VND) {
    return 0L;
}
~~~

- `if` asks whether the condition is true.
- `()` holds the condition.
- `||` combines two conditions. Java uses short-circuit evaluation: if `member` is already true, there is no need to evaluate the right-hand side.
- `{}` groups the statements belonging to the branch.
- `return` returns the result and ends that method call.

**`=` is assignment, whereas `==` is equality comparison** (for compatible types). Confusing these two concepts can cause compilation errors or logic errors.

## 8. Data Types Must Match the Meaning of the Problem

In Java, a data type is not merely decoration next to a variable name. The type determines the form of the value stored and which operations are valid.

| Type | What does it represent in this lesson? | What to avoid |
| --- | --- | --- |
| `int` | Whole km distance, within the valid range of `int` | Parsing a string that is too large into an `int` |
| `long` | Whole VND money amounts and total amount | Computing beyond the `long` limit |
| `boolean` | Yes/no membership status | Treating any arbitrary string as `true` |
| `String` | Text arguments in `args` | Passing strings into numeric addition without converting types |

Money is denominated in **whole VND**, so integer types are used. `double` is a floating-point number useful in many scientific calculations, but it should not be used by default to represent money accurately to the smallest unit because binary representation can introduce rounding errors. For money with fractional parts or complex rounding rules, `BigDecimal` and explicit unit/rounding rules may be needed.

Also avoid vague variable names like `x`, `a`, `n` for everything. `orderValueVnd` and `shippingVnd` are longer, but they show both the **meaning** and the **unit**, reducing the chance of accidentally adding money to kilometers.

## 9. Boundary Cases and Errors to Consider

A program running correctly on the 300,000 VND example is not enough to prove the algorithm is right. Use the following cases as a **manual test table**:

| Input: amount, km, member | Expected shipping fee | Reason |
| --- | ---: | --- |
| `300000 0 false` | 15,000 | Has not exceeded 5 km |
| `300000 5 false` | 15,000 | Exact end point of the base fee |
| `300000 6 false` | 17,000 | 1 km over |
| `300000 8 false` | 21,000 | 3 km over |
| `499999 8 false` | 21,000 | Just below the free-shipping threshold |
| `500000 8 false` | 0 | Exactly at the free-shipping threshold |
| `120000 8 true` | 0 | Member |
| `0 8 false` | 21,000 | Order value of 0 is still valid per assumptions |
| `-1 8 false` | Not calculated, reports error | Negative amount |
| `300000 -1 false` | Not calculated, reports error | Negative distance |
| `abc 8 false` | Not calculated, reports error | Cannot convert to `long` |
| `300000 8 yes` | Not calculated, reports error | Not in `true/false` |
| `300000 8` | Prints usage instructions | Missing argument |

A typical mistake is writing `orderValueVnd > 500_000L` instead of `>=`. Most other examples still pass, but **exactly 500,000** will be charged incorrectly. This is a logic error: the program can compile and run, yet **the result violates the requirement**.

### Three Different Categories of Issues

**Compile-time errors:** Writing invalid syntax, variable names, or incompatible types. For example:

~~~java
// Wrong: missing ; at the end of the statement.
long fee = 15_000L
~~~

`javac` reports an error and does not produce a valid runnable program.

**Runtime errors:** The code compiles, but inputs or state cause an exception. For example, `Long.parseLong("abc")` throws `NumberFormatException`; the program can catch it and notify the user.

**Logic errors:** The code compiles and runs normally, but implements the rules incorrectly. For example, `distanceKm >= 5` charges the extra fee starting at the 5th km if the algorithm is written wrong. Therefore, tests must be based on the **problem specification**, not merely on whether “the machine reported no error”.

Cases such as overly large numeric values, missing arguments, or the string `TRUE` also need to be decided by the contract. This example accepts `TRUE` because it deliberately converts to lowercase before checking.

## 10. Why Separate the Processing Method from `main`?

`main` is responsible for receiving and converting **program inputs**, calling processing, and printing results. `calculateShipping` is responsible for the **fee calculation rules**.

This separation helps you:

- Quickly read one method and know what it returns.
- Test fee calculation with many arguments without simulating a terminal.
- Change how input is obtained (command line, UI, API) without rewriting all the rules.
- Avoid scattering `500_000`, `15_000`, and `2_000` everywhere by giving them named constants.

There is no need to create many classes or frameworks just to calculate shipping fees. For a small example, **one class and one clear method** are enough.

You can verify a few calls yourself in a test program:

~~~java
System.out.println(ShippingQuote.calculateShipping(300_000, 8, false)); // 21000
System.out.println(ShippingQuote.calculateShipping(500_000, 8, false)); // 0
System.out.println(ShippingQuote.calculateShipping(300_000, 5, false)); // 15000
~~~

The three statements above are only an **illustrative snippet placed inside a method** in the same default directory/package; they are not a standalone Java file. A next learning step is turning these expectations into automated tests.

## 11. Things the Java Language Does Not Do for You

Java has a compiler that checks many rules, but it **does not automatically know business correctness**.

For example:

- `javac` can check that `calculateShipping` returns a `long` value along all valid control-flow paths.
- It cannot conclude “the base fee must be 15,000” unless you express that in code and test against the requirement.
- It does not decide on its own whether to charge by actual km, rounded km, or delivery zones.
- It does not automatically guarantee that data from users, databases, or the network always has valid values.
- A Java program can run across many suitable platforms, but file paths, network connections, encoding, and external libraries can still affect deployment.

A **correct program** requires both: the language executing the written code accurately, and **that code accurately expressing the problem**.

## 12. Self-Practice: Turning a New Requirement into Code

**Exercise 1 — Predict before running.** Keeping the program unchanged, run `java ShippingQuote 499999 5 false`. What should the shipping fee and total be?

*Verification answer:* shipping fee `15000`, total `514999`.

**Exercise 2 — Change a rule.** The store raises the free-shipping threshold from 500,000 to 600,000 VND. Point out the line to change, then test both `599999` and `600000` for a non-member customer.

*Hint:* change `FREE_AT_VND`, then check both below and right at the threshold. Do not edit your predicted answer before re-reading the requirement.

**Exercise 3 — Trace.** With `orderValueVnd = 200_000`, `distanceKm = 10`, and `member = false`, step sequentially through `if`, `extraKm`, `extraFee`, `shippingVnd`, and `totalVnd`.

*Answer:* `extraKm = 5`, `extraFee = 10000`, `shippingVnd = 25000`, `totalVnd = 225000`.

**Exercise 4 — Find the logic bug.** Someone writes:

~~~java
long extraKm = Math.max(0L, (long) distanceKm - 4L);
~~~

What happens to a non-free-shipping order at 5 km? Why does it violate the specification?

*Answer:* an extra 2,000 VND will be charged right at the 5th km; the specification states extra charges only start from the 6th km.

**Exercise 5 — Design a new problem yourself.** Write an **input / output / assumptions / rules / boundary cases** table for a small problem such as converting minutes to hours, calculating ticket prices by age, or finding the largest of three numbers. Then write pseudocode in Vietnamese before translating it into Java.

**Completion criteria:** You can explain a real-world requirement, map each component to Java data and statements, compile/run the program, and point out at least three cases where the result could be wrong if a rule is written imprecisely.

## Key Takeaways

Java is a **language for expressing algorithms and rules** using syntax that can be compiled, type-checked, and executed on the JVM. To use Java to solve a problem, proceed from **clear requirements → clear data and units → clear conditions/calculations → runnable code → testing both normal and boundary inputs**. When you know what each variable, statement, and method represents in the problem, learning Java constructs in greater detail becomes much more meaningful than merely memorizing keywords.
