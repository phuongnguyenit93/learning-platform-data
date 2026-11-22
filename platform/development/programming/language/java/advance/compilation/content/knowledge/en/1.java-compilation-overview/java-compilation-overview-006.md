# Code That Compiles Successfully Does Not Guarantee Correct Runtime Behavior

When `javac` exits with a success status code, what has been confirmed is that **the source code passed the checks performed by the compiler under the current configuration and produced the corresponding compilation output**. That is a very important milestone, yet still far from concluding “the program definitely runs, runs stably, and returns correct results”.

A program may:

- **Fail to start** due to missing dependent classes or using an incompatible Java version.
- **Start up but terminate midway** due to invalid data, division by zero, missing files, dropped network connections, or exhausted resources.
- **Run to completion and print results** yet produce results that violate business rules.
- **Produce correct results on one run** yet fail when data, environment, execution order, or concurrent threads change.

This lesson helps recognize each situation, understand why the compiler cannot provide guarantees in place of running tests and verification, and design a workflow that reduces risk.

## 1. What Does “Compile Success” Actually Confirm?

With standard Java compilation:

~~~text
.java source code
    |
    | javac: parse syntax, resolve names/types, check
    | many language rules, emit bytecode
    v
Generated .class file
    |
    | java: load classes, link, initialize, run main
    v
Program executes
    |
    | data, dependencies, operating system, network, users...
    v
Observed behavior
    |
    | compared against requirements and test cases
    v
Conclusion on correctness within the verified scope
~~~

`javac` commonly catches issues such as syntax errors, undeclared variables, incompatible type assignments, or method calls that do not match signatures known at compile time. However, it **does not execute every statement, does not know all data that will arrive, and cannot infer human business intent**.

Four distinct conclusions must be separated:

| Conclusion | Minimum evidence | What is not yet guaranteed |
| --- | --- | --- |
| Compile success | `javac` command exits cleanly; matching output produced | Runs on target environment |
| Startup success | Runtime locates and loads components needed to start | All subsequent execution paths are safe |
| One successful run | Program raises no errors on a specific run | Output satisfies requirements, all other inputs are correct |
| Verification passed | Tests/checks against criteria defined for a specific scope | Zero remaining bugs in every possible scenario |

**There is no valid inference that “green build ⇒ absolute quality correctness”.** A green build usually indicates that a set of checks passed; confidence depends on what those checks actually cover.

## 2. Example One: Valid Code That Calculates the Wrong Total

Consider the requirement: total payment equals **unit price times quantity, plus delivery fee**. Save the following standalone code as **`OrderBill.java`**:

~~~java
public class OrderBill {
    public static void main(String[] args) {
        int unitPrice = 19_000;
        int quantity = 3;
        int deliveryFee = 2_500;

        // Violates requirement: need to add the fee, but subtracted it instead.
        int payable = unitPrice * quantity - deliveryFee;

        System.out.println("Tiền phải trả: " + payable);
    }
}
~~~

In the directory containing the file:

~~~sh
javac -encoding UTF-8 OrderBill.java
java OrderBill
~~~

The program runs normally and prints:

~~~text
Tiền phải trả: 54500
~~~

However, the correct result per the requirement is `19_000 × 3 + 2_500 = 59_500`, i.e., `59500`. The error lies in the **meaning of the formula**, while the minus sign is completely valid in syntax and types. `javac` has no business specification to understand that the delivery fee must be added.

Fix the payment calculation line to:

~~~java
int payable = unitPrice * quantity + deliveryFee;
~~~

After **recompiling** and running `java OrderBill`, stdout is now:

~~~text
Tiền phải trả: 59500
~~~

This is a **logic bug**: the code compiles, the application runs, yet still returns the wrong answer. It is often more dangerous than an obvious compile error because it easily slips past if you only observe that the application throws no exceptions.

### Lessons from Logic Bugs

- Specifications must include **expected results independent of how the code is written**. If tests merely copy the same wrong formula, the tests will also pass falsely.
- Rules such as discounts, taxes, fees, rounding, and quantity limits need to be expressed as input/output examples and boundary conditions.
- Running a single simple example is insufficient: many bugs only surface at zero, negative values, very large numbers, empty orders, or alternate processing branches.

## 3. Example Two: Compiles Fine but Fails Only at Runtime

Save the following standalone code as **`ShareCalculator.java`**:

~~~java
public class ShareCalculator {
    public static void main(String[] args) {
        int total = 120;
        int people = Integer.parseInt(args[0]);
        int perPerson = total / people;

        System.out.println("Mỗi người nhận: " + perPerson);
    }
}
~~~

Compile:

~~~sh
javac ShareCalculator.java
~~~

Run with valid input:

~~~sh
java ShareCalculator 4
~~~

Output:

~~~text
Mỗi người nhận: 30
~~~

Now try different inputs one by one:

~~~sh
java ShareCalculator 0
java ShareCalculator abc
java ShareCalculator
~~~

These runs fail for different reasons:

| Input | Problem | Runtime error type |
| --- | --- | --- |
| `4` | Valid | Prints `Mỗi người nhận: 30` |
| `0` | Integer division by 0 | `ArithmeticException` |
| `abc` | String does not represent a valid integer | `NumberFormatException` |
| No argument | Accesses `args[0]` even though array is empty | `ArrayIndexOutOfBoundsException` |

The table lists **exception types** instead of copying full stack traces, because file paths, line numbers, and formatting depend on the environment. All cases above stem from **the same `.class` file that compiled successfully**.

`javac` knows `args` has type `String[]` and `Integer.parseInt` accepts a `String`. Yet it does not know how many arguments the user will pass, what string it will be, or whether the integer equals 0. Those constraints are only determined at runtime.

### Version with Input Validation

We can turn invalid situations into intentional messages. Save the following complete version into **`SafeShareCalculator.java`**:

~~~java
public class SafeShareCalculator {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("Cần đúng một số người.");
            return;
        }

        int people;
        try {
            people = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.out.println("Số người phải là số nguyên.");
            return;
        }

        if (people <= 0) {
            System.out.println("Số người phải lớn hơn 0.");
            return;
        }

        int perPerson = 120 / people;
        System.out.println("Mỗi người nhận: " + perPerson);
    }
}
~~~

~~~sh
javac -encoding UTF-8 SafeShareCalculator.java
java SafeShareCalculator 4
java SafeShareCalculator 0
java SafeShareCalculator abc
java SafeShareCalculator
~~~

In sequence, each `java` command prints exactly one line:

~~~text
Mỗi người nhận: 30
Số người phải lớn hơn 0.
Số người phải là số nguyên.
Cần đúng một số người.
~~~

This program handles **identified** risks: missing arguments, non-numeric strings, and non-positive values. It still does not define a policy for handling remainders when `120` is not evenly divisible by the number of people or when business rounding rules exist. **Exception handling does not replace understanding requirements**.

## 4. Example Three: Compile Compatibility Does Not Mean Runtime Environment Compatibility

A program can generate valid bytecode on a development machine yet fail to run on the target machine.

### JDK/JVM Version Differences

`.class` files store format version information. For example:

- Java 17 typically emits classfile major version **61**.
- Java 21 typically emits classfile major version **65**.

If compiled targeting Java 21 and then the class files are moved to a Java 17 runtime, the Java 17 JVM does not understand the newer format and may report `UnsupportedClassVersionError`. This error typically appears during class loading, **not while `javac` ran successfully on the development machine**.

When you need to deploy on Java 17 and are using a newer JDK supporting that target, try:

~~~sh
javac --release 17 OrderBill.java
~~~

`--release 17` constrains the language level, bytecode format, and the Java platform API set that the compiler allows referencing for the target. This approach is more reliable than setting `-source` and `-target` separately when wanting compatible standard APIs. However, **it does not automatically guarantee that third-party libraries, configurations, patches, or runtime environments are compatible**.

Use the commands:

~~~sh
javac -version
java -version
javap -verbose OrderBill
~~~

to check compiler/runtime versions and classfile details (look for the `major version` field in `javap -verbose` output). Do not infer the target runtime solely from the JDK on the coding machine.

### Missing Classes or Libraries at Runtime

A project may compile when a library is placed on the **compile classpath**, yet lack the corresponding JAR on the **runtime classpath** at execution time. When the JVM needs to load or link the missing component, the program may encounter `NoClassDefFoundError` or related loading/linkage errors. `ClassNotFoundException` is commonly observed when code attempts to dynamically load a class via APIs such as `Class.forName`.

For instance, code calling a library present on the build machine will not necessarily find that library after copying only `.class` files to the runtime machine. Dependencies and packaging must be managed consistently, rather than treating missing-class errors as proof that the compiler checked incorrectly.

Some binary compatibility issues are subtler: code compiled against version A of a library, while runtime uses version B that changed a method signature or behavior. When invoking that member, linkage errors such as `NoSuchMethodError` may occur, or unexpected results may be returned. **Testing in an environment with actual dependencies** uncovers these issues.

## 5. Categories of Issues Remaining After Compilation

| Category | Concrete example | Why is `javac` insufficient? | How to verify |
| --- | --- | --- | --- |
| Input data | Zero, malformed strings, missing required fields | Actual data only arrives at runtime | Validation and boundary testing |
| Business logic | Subtracting fee instead of adding | Compiler does not know payment rules | Expected output examples, unit tests |
| Runtime dependencies | Missing JAR, wrong class version | Compile and runtime may use different environments | Run packaged artifacts on target environment |
| I/O and resources | File not found, no write permission, disk full | Files/filesystems change at runtime | Integration tests and I/O error handling |
| Network and external services | Timeouts, connection refused, altered API data | Future network and service state is unknown | Integration tests, timeouts, controlled retries |
| Concurrency | Two threads unsafely updating shared state | Type checking does not prove absence of race conditions | Synchronization design, load/concurrency testing |
| Memory, performance | `OutOfMemoryError`, processing takes too long | Resource consumption depends on data scale and runtime | Load testing, memory measurement, profiling |
| Security | Unchecked access permissions, data leaks | Syntactically valid code can still have vulnerabilities | Security review, authorization and data tests |
| Deployment | Wrong env vars, port busy, different timezone | Operational conditions are outside static checks | Smoke tests, monitoring, environment configuration |
| Stability | One test passes, many other runs fail | Failures depend on timing, data, or environment | Intentional repeated runs, log collection |

Do not attribute all of these failures to “compiler errors”. Proper categorization clarifies who needs to check what: the code author, build configurator, operator, or requirement validator.

### Situations Easily Misjudged

**A caught exception does not mean business success.** If a program catches every `Exception` and returns a default value, the system may not crash yet still output wrong results. Decide when fallback is permissible and how to report errors meaningfully.

**Finishing `main` does not mean processing succeeded.** An API call may fail while the program still exits with code 0; an output file may be missing data; a transaction may have been rolled back. Verify expected output effects, not merely process exit status.

**No visible exception does not mean no bugs.** An integer addition can overflow without throwing an exception by default; a comparison rule may be wrong yet still return a valid `true`/`false`.

**Measurement units and input formats can alter results.** Computing in milliseconds when seconds are required; rounding money too early; using locale-specific decimal commas vs. dots — all of these can compile and run.

## 6. Example Four: Integer Overflow Can Still Produce a Value

Save as **`OverflowExample.java`**:

~~~java
public class OverflowExample {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int wrapped = max + 1;

        System.out.println("Giá trị tính được: " + wrapped);
        System.out.println("Giá trị lớn nhất của int: " + max);
    }
}
~~~

~~~sh
javac OverflowExample.java
java OverflowExample
~~~

Exact stdout:

~~~text
Giá trị tính được: -2147483648
Giá trị lớn nhất của int: 2147483647
~~~

Type `int` has a 32-bit signed range. Adding `Integer.MAX_VALUE + 1` overflows and wraps around according to Java integer arithmetic rules; `javac` accepts the program and the JVM does not automatically throw an exception on ordinary `int` addition. If business rules require detecting overflow, use `Math.addExact` or another suitable representation/constraint.

Overflow-checking version, save as **`CheckedAddition.java`**:

~~~java
public class CheckedAddition {
    public static void main(String[] args) {
        try {
            int result = Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("Phát hiện tràn số nguyên.");
        }
    }
}
~~~

~~~sh
javac -encoding UTF-8 CheckedAddition.java
java CheckedAddition
~~~

Output:

~~~text
Phát hiện tràn số nguyên.
~~~

In monetary calculations, you must also consider units, scale, rounding, and business rules; `Math.addExact` only addresses integer addition overflow risk and **does not automatically fix all payment calculation bugs**.

## 7. Tests Can Catch Logic Bugs the Compiler Misses

To separate **desired behavior** from **code-produced behavior**, write functions with clear contracts and test representative examples. Create **`OrderPolicyTest.java`**, a standalone self-checking program using only standard Java:

~~~java
public class OrderPolicyTest {
    static int amountToPay(int unitPrice, int quantity, int deliveryFee) {
        return unitPrice * quantity + deliveryFee;
    }

    static void check(String name, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        check("don mot san pham", 21_500, amountToPay(19_000, 1, 2_500));
        check("don ba san pham", 59_500, amountToPay(19_000, 3, 2_500));
        check("mien phi van chuyen", 38_000, amountToPay(19_000, 2, 0));
        check("khong mua san pham", 2_500, amountToPay(19_000, 0, 2_500));
    }
}
~~~

~~~sh
javac -encoding UTF-8 OrderPolicyTest.java
java OrderPolicyTest
~~~

Output when all four expectations match:

~~~text
PASS don mot san pham
PASS don ba san pham
PASS mien phi van chuyen
PASS khong mua san pham
~~~

Each `check` compares the actual result against **the expected value calculated from requirements**, rather than merely confirming the function returns a number. If you replace adding `deliveryFee` in `amountToPay` with subtraction, the program still compiles, yet the first test throws `AssertionError`: that bug is caught at the **testing step**, not inside `javac`.

In real projects, such tests are typically organized with JUnit and run via Gradle/Maven; this example uses `main` so learners can run it with plain JDK without adding dependencies.

### Designing Meaningful Test Suites

1. **Normal cases:** Common values; results can be calculated independently.
2. **Boundaries:** 0, single item, minimum/maximum values, or right next to contract thresholds.
3. **Invalid data:** Missing fields, bad formats, values violating rules; verify the program rejects clearly.
4. **Environment failures:** Lost connection, non-existent files, missing permissions, unavailable dependencies.
5. **Interaction and concurrency:** Data updated mid-processing, two requests modifying the same resource concurrently.
6. **Regression:** Fixed bugs retained as tests so they do not accidentally reappear.

There is no need to force every project to have the same test count. Each test should answer a concrete question: *what bug could happen that the compiler misses, and what evidence shows desired behavior is preserved?*

## 8. Post-Compilation Verification Layers

A typical workflow:

~~~text
Source code + behavior contract
           |
           v
Compile / static checks
           |  syntax/type error? -> fix code
           v
Unit tests
           |  business logic error in small scope? -> fix logic
           v
Integration tests
           |  dependency / database / API issue? -> fix configuration, integration
           v
Packaging + run actual artifacts
           |  JVM, JAR, classpath, config match?
           v
Smoke tests / end-to-end tests
           |  critical flows work?
           v
Runtime monitoring
           |  logs, metrics, alerts, error handling
           v
Feedback and verified fixes
~~~

### Role of Each Layer

| Layer | Purpose | Limitation |
| --- | --- | --- |
| Compiler/static checks | Eliminate language, type, and certain non-runtime issues | Does not prove business logic or runtime environment |
| Unit tests | Compare small functions/units against requirements | May miss interactions between components |
| Integration tests | Verify real connections or close simulations between components | Does not guarantee every production configuration |
| Smoke/end-to-end | Verify primary flows through near-real artifacts and environment | Usually has limited coverage of detailed branches |
| Load, security, endurance testing | Check risks outside normal execution paths | Must be designed per need, cannot be inferred from green build |
| Runtime observability | Detect abnormal behavior with real data and load | Detects after deployment; does not fix bugs automatically |

**No single layer replaces all the others.** For instance, unit tests might show a payment calculation function is right, yet when deployed with a different currency/locale or external data, the system still errs. Conversely, a passing end-to-end test may never hit input boundaries that crash the program.

### Testing the Right Artifact

A process error is testing build directory A, yet deploying a different JAR or using newer dependencies. For test conclusions to hold value:

- Identify the exact source code, build parameters, JDK version, dependencies, and artifacts tested.
- When necessary, use the exact same artifact (or a verified reproducible artifact) for the next environment.
- Run at least critical operations on **an environment close to deployment conditions**.
- If a build fails while old `.class`/JAR files remain, never treat the old artifact still running as proof that the new source code is valid.

## 9. Reading Symptoms to Find the Right Error Category

Suppose an issue occurs; diagnose along the following sequence.

### Case A: `javac` reports errors and fails to produce the desired new output

Inspect messages about syntax, imports, class names, visibility, type mismatches, and method signatures. These are usually **compilation** issues; resolve them before expecting new code to run.

### Case B: `javac` succeeds but `java` fails to enter the main flow

Check the fully-qualified class name, classpath/module path, presence of an appropriate `main` method, dependent JARs, and JVM version. For example, `Could not find or load main class` is a class lookup/loading or run configuration issue; `UnsupportedClassVersionError` suggests class files newer than the target JVM.

### Case C: Runs partway then throws an exception

Read the exception type, stack trace, and execution conditions. Record **the minimal input and environment state needed to reproduce**. Distinguish data errors (such as `NumberFormatException`), arithmetic errors (`ArithmeticException`), and resource access errors (`IOException`). Do not hide stack traces or collapse all errors into a generic “unknown error” message during investigation.

### Case D: No exception yet wrong result returned

Check requirements, intermediate values, units of measure, branch conditions, and independent expected outcomes. Write a minimal test reproducing the bug. Do not start by raising timeouts or tweaking JVM flags if the issue truly lies in logic.

### Case E: Fails only in production or under load

Compare JDKs, artifacts, classpaths, environment variables, connections, permissions, memory, timezones, locales, traffic, and thread configurations. Gather timestamped evidence with sensitive info masked and reproduction steps. Concluding “it works on my machine” speaks only about **one environment**, not disproving errors in another.

## 10. Scope and Limitations to Remember

- **The compiler is not a business tester.** It holds no canonical answers for money calculations, deadlines, authorization, or customer scenarios.
- **The type system cannot eliminate all bugs.** A type-valid `int` value can still be invalid in the business domain, such as zero people.
- **The compiler cannot pre-check all runtime states.** Deleted files, dropped networks, unresponsive services, or exhausted resources are conditions that change after build time.
- **Bytecode verification in the JVM differs from `javac`.** The JVM has its own verification/linkage checks to safeguard the validity of loaded code; this likewise does not prove business correctness.
- **Static analyzers, tests, and reviews complement each other.** Tools analyzing deeper than the compiler can warn on additional bug patterns, yet every warning and conclusion has scope and limits.
- **You cannot infer “zero bugs remain” from all current tests being green.** Tests cover only the specified and executed scenarios/properties; add meaningful tests whenever new requirements or risks emerge.

## 11. Reinforcement Exercises

**Exercise 1 — Verify logic bugs.** Run `OrderBill.java`, record the printed output and the correct output per requirements. Explain why both results pass `javac`, and fix the formula.

**Exercise 2 — Data and failure timing.** Run `ShareCalculator.java` with arguments `4`, `0`, `abc`, and no arguments. Make a table showing which case completes normally, which throws exceptions, and the data-related cause.

**Exercise 3 — Input validation boundaries.** Test `SafeShareCalculator.java` with `4`, `0`, `abc`, no arguments, and `7`. With `7`, integer division yields `17` with a remainder of `1`; identify what requirement must be added if business rules disallow losing the remainder.

**Exercise 4 — Test before fixing.** Replace addition with subtraction in `amountToPay` inside `OrderPolicyTest.java`; predict which test fails first. Run and observe `AssertionError`, then fix it back.

**Exercise 5 — Deployment.** State what you would inspect if `.class` files were compiled with Java 21 while the runtime host only has Java 17; distinguish editing code, configuring `--release`, and upgrading runtime as appropriate.

### Self-Check

1. Why does `javac` accept a formula subtracting the shipping fee despite the wrong result? — Because the operators and types are valid, while the rule to add the fee sits outside static checking.
2. If `java ShareCalculator 0` throws `ArithmeticException`, did `javac` fail? — No; the error occurred during runtime with input data 0.
3. Why does a JAR run on a developer's machine yet fail on another machine? — JVM, classpath, dependencies, configuration, or resources may differ.
4. Why must we know the *expected* value in tests? — To compare against correct behavior per requirements, avoiding merely verifying that the program returns some value.
5. What is stronger evidence than “compile success”? — Combining contract-based testing, deployment environment checks, measurement, and observing actual behavior within the scope needing assurance.

**Core takeaway:** `javac` answers the question *“Is the code valid under the applied compilation rules and able to produce output?”*. Running tests and verification answers a different question: *“Given concrete data, environment, and requirements, does the program do the right thing?”*. To trust a Java application, both kinds of evidence are needed, along with recognizing their limits.
