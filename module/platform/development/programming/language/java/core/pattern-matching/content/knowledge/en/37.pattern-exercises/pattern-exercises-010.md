# Checking with the Java Compiler — Pattern Matching Synthesis Practice

## 1. Why check with the compiler instead of only reading code?

In Java Pattern Matching practice, a snippet of code can **look right** yet fail to compile because the Java version does not support the syntax, the pattern variable scope is wrong, a `switch` expression is missing a case, a case is dominated by an earlier branch, or a generic type cannot be checked at runtime.

Conversely, code that **compiles successfully** can still have logic bugs: `when` checks the wrong condition, a null record component is handled improperly, or a fallback branch returns an unexpected value. Therefore, a complete check must have **two gates**:

1. **Compile-time check:** The `javac` compiler verifies syntax, type system, variable scope, exhaustiveness, domination, and language feature usage requirements.
2. **Runtime test:** Run the program with intentionally chosen data; assertions verify that results and exceptions match the business contract.

The lesson “**Checking with the Java compiler**” belongs to the **Synthesis Practice** group. The goal is not just to learn a few terminal commands, but to know how to **write, compile, explain errors, fix code, re-run, and protect results with tests**.

After this lesson, you will practice:

- Identifying the actual `java`, `javac`, source/release, and runtime versions.
- Compiling type patterns in `instanceof` with Java 17 and record/switch patterns with Java 21.
- Analyzing typical errors: **non-exhaustive switch, dominated case, flow scope, record pattern arity, generic type erasure**.
- Using **intentionally non-compiling** snippets to verify that the compiler catches the right error categories without including them in production builds.
- Writing a complete Java 21 program and running **16 assertions** to test match branches, false guards, null, nested records, and fallbacks.
- Integrating `javac`/Maven/Gradle into CI without confusing warnings with errors or compile success with application correctness.

**Versions used in this lesson:** Type patterns for `instanceof` became standard in **Java 16 (JEP 394)**. Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became standard in **Java 21**. The main example uses **stable Java 21, without `--enable-preview`**.

## 2. Before fixing errors: identify the right Java compiler and release

On a machine with multiple JDKs, the `java` command used to **run** a program and the `javac` command used to **compile** it do not necessarily come from the same installation. IDEs, Maven, Gradle, and CI may also select a different toolchain than the current terminal.

Start with:

```bash
java -version
javac -version
```

The output depends on the JDK on your machine, so **there is no single fixed stdout** for those two commands. They tell you which runtime/Java compiler the shell selected, which does not automatically prove that your IDE or build system is using the same version.

Check which target releases the compiler supports:

```bash
javac --help
```

Important options:

| Option | Meaning |
| --- | --- |
| `javac --release 17` | Compiles against the language level, standard APIs, and class-file target for Java 17 supported by the current compiler. |
| `javac --release 21` | Compiles against Java 21 language/API levels; requires a JDK compiler capable of targeting Java 21. |
| `javac -d out ...` | Writes `.class` files into the `out` directory instead of mixing them with source files; useful for a CLI example. |
| `javac -Xlint:all` | Enables additional supported **warning** categories; does not replace mandatory compiler checks. |
| `javac -Werror` | Treats emitted warnings as build errors; not needed to catch syntax errors or non-exhaustive switches. |
| `--enable-preview` | Enables preview features for the **release matching the compiler**; not a switch to enable any future Java feature. |

**Important:** Using JDK 21/24 to run `javac --release 17` still means the source must be valid under **Java 17**—you cannot use Java 21 final record patterns. Conversely, JDK 17 does not understand `--release 21` and typically reports an error equivalent to “release version 21 not supported”.

Nor can you compile class files targeting Java 21 and run them directly on Java 17. An older runtime may throw `UnsupportedClassVersionError` because it does not support the class file version, even if the source code compiled successfully in another environment.

### 2.1. Source, compile, and runtime are three separate stages

1. **Source compatibility:** Is the syntax valid at the target release?
2. **Binary/API compatibility:** Are the classes/APIs used by the program compatible with the release target and dependencies?
3. **Runtime behavior:** Does the program produce the right result when run on the intended JVM?

The compiler only resolves what can be checked statically. With pattern matching, Java knows type relationships and case structure, but it does not know which business values are “valid” unless you encode those constraints in Java.

## 3. Remember Java milestones to avoid misdiagnosing the compiler

| Feature | Standard / preview milestone | How to interpret when building |
| --- | --- | --- |
| `record` class | Standard **Java 16**, JEP 395 | Java 17 creates and accesses records normally. |
| `instanceof String text` | Standard **Java 16**, JEP 394 | Works in Java 17 without preview. |
| Record pattern `Point(var x, var y)` | Preview Java 19 (JEP 405); second preview Java 20 (JEP 432); **final Java 21** (JEP 440) | Not supported in Java 17; usable directly in Java 21. |
| Pattern matching for `switch` | Preview since Java 17; **final Java 21**, JEP 441 | `case String s`, `when`, and pattern switches require no preview in Java 21. |
| Unnamed pattern `_` | Preview Java 21 (JEP 443); **final Java 22** (JEP 456) | Do not use `_` as a standard feature when targeting Java 21. |

A simple example: having `record` does not mean you have record deconstruction. Java 17 can compile:

```java
record Point(int x, int y) {}

static int readX(Object input) {
    if (input instanceof Point point) {
        return point.x();
    }
    return -1;
}
```

However, if you use `input instanceof Point(var x, var y)` at source level 17, the compiler rejects it because it is a Java 21 **record pattern**. The fix is to raise the source level to 21 or keep a type pattern with accessors; do not add `--enable-preview` on Java 17 expecting features introduced in Java 19/21 to magically appear.

## 4. End-to-end workflow for checking a Java file

When you have `CompilerPatternCheckDemo.java` from Section 9, run:

```bash
javac --release 21 CompilerPatternCheckDemo.java
java CompilerPatternCheckDemo
```

The first line validates Java 21 syntax/types and produces class files if successful. The second line runs `main` and executes the assertions. If compilation fails, **do not** mistake leftover `.class` files from an earlier build for the result of the new source. You can use a dedicated output directory for clarity:

```bash
javac --release 21 -d out CompilerPatternCheckDemo.java
java -cp out CompilerPatternCheckDemo
```

Prerequisite: create the `out` directory if needed by your environment before compiling. When using `-d out`, classes are placed under the output path, and `java -cp out ...` runs the newly built output. This avoids accidentally running stale classes in the working directory.

### 4.1. Compilation process exit codes

In a build pipeline, it is important to **check whether `javac` exited successfully**. On a Unix-like shell:

```bash
javac --release 21 CompilerPatternCheckDemo.java
echo $?
```

`echo $?` prints the exit code of the previous command. **`0`** means success; a non-zero code means the command reported an error. This snippet only illustrates how to check the status; in CI, it is better to let the build fail directly rather than just printing the exit code and continuing.

In Windows PowerShell, use `$LASTEXITCODE` for native processes like `javac`; do not copy Bash's `$?` syntax into PowerShell assuming identical semantics.

### 4.2. Understanding javac diagnostics

A diagnostic typically includes:

- The file path and line/column near the error location.
- **The error kind**, such as symbol not found, incompatible types, missing case, or dominated case.
- A snippet of the source line and a pointer to the position.

Exact wording varies by compiler version and source structure. Therefore, the “Common errors” section below gives **the meaning and examples** rather than asking you to match exact error message characters.

## 5. How does the compiler check type patterns and variable scope?

A type pattern binds a variable **only where Java determines the pattern has matched**.

Valid example since Java 16:

```java
static String describe(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    return "other";
}
```

On the right-hand side of `&&`, Java knows `input instanceof String text` is true. If `input` is `null`, an `Integer`, or a blank `String`, the condition evaluates to false and the code returns `"other"`.

### 5.1. Error: using a pattern variable outside flow scope

An **intentionally invalid** example—keep it in a separate test class:

```java
// DOES NOT COMPILE in a regular Java class:
static int invalidScope(Object input) {
    if (input instanceof String text) {
        System.out.println(text);
    }
    return text.length();
}
```

After the `if`, execution could have taken the **non-matching** branch, so `text` is not definitely bound. The compiler forbids using it in `return`.

Fix with a guard clause:

```java
static int safeLength(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

At the last line, every path where the pattern was false has already exited via `return -1`, so the compiler knows `text` exists.

### 5.2. Why changing && to || can break compilation

```java
// DOES NOT COMPILE:
if (input instanceof String text || text.length() > 3) {
    System.out.println(text);
}
```

`||` only evaluates the right-hand side when the left-hand side is false, which means the pattern did not match and `text` is not bound. Using `&&` is appropriate when the right-hand side needs the pattern variable.

### 5.3. Expression already has the exact static type

For a variable whose static type is already `String`, you do not need a pattern checking the same type again. Some redundant checks such as `String s; s instanceof String text` are rejected by Java when the expression type is already a subtype of the pattern type. Use `s` directly and handle null according to your contract instead of inserting patterns everywhere.

**Conclusion:** The compiler checks **scope and the type system**, not whether the logic after a match (for example, whether `isBlank()` should be true or false) fits business rules. That part requires runtime tests.

## 6. Compiler checks for record patterns in Java 21

Declaration:

```java
record Point(int x, int y) {}
```

Valid record pattern in Java 21:

```java
static int sum(Object input) {
    if (input instanceof Point(var x, var y)) {
        return x + y;
    }
    return 0;
}
```

From the record declaration, the compiler knows `Point` has **two components** of type `int`. It checks that the nested pattern list has the right count and compatible types.

### 6.1. Wrong component count

```java
// DOES NOT COMPILE: Point has two components, but the pattern only has one.
static int wrongArity(Object value) {
    return switch (value) {
        case Point(var x) -> x;
        default -> 0;
    };
}
```

Java 21 reports an error equivalent to **“incorrect number of nested patterns”** or wrong component count. This is not because runtime input lacks data: the `Point` record already defines its structure at compile time.

Fix:

```java
static int corrected(Object value) {
    return switch (value) {
        case Point(var x, var y) -> x;
        default -> 0;
    };
}
```

You do not have to use `y`, but you must still provide a pattern for the second position when targeting Java 21 without the unnamed pattern preview. Java 22 standardized the unnamed pattern `_`, but you should not put `_` into source targeting Java 21 by default.

### 6.2. Nested record patterns and null

Example:

```java
record Amount(int cents, String currency) {}
record Payment(String id, Amount amount) {}
```

Pattern:

```java
// Java 21 snippet inside a switch with an Object selector:
case Payment(var id, Amount(var cents, var currency)) -> ...
```

It matches only when the selector is a `Payment` and its `amount` component is a **non-null** `Amount` record. However, `currency` can still be null because `var currency` only binds the `String` component by type—it **does not automatically require non-null**.

If `amount == null`, the nested `Amount(...)` does not match; you need a fallback branch on `Payment` if you want to handle it explicitly:

```java
case Payment(var id, var amount) -> "missing-amount";
```

The compiler checks the pattern structure, whereas **validation of `cents` and `currency`** belongs in guards, constructors, domain services, or tests depending on your design. Section 9 illustrates both layers.

## 7. Compiler checks for switch exhaustiveness and case order

### 7.1. Exhaustiveness: sealed interfaces help find missing branches

Suppose:

```java
sealed interface Message permits Text, Payment, Quit {}
record Text(String value) implements Message {}
record Amount(int cents, String currency) {}
record Payment(String id, Amount amount) implements Message {}
record Quit() implements Message {}
```

A `switch` expression over `Message` must cover the subtypes `Text`, `Payment`, and `Quit` (or use a catch-all branch). The following example is **intentionally wrong**:

```java
// DOES NOT COMPILE: missing Payment and Quit.
static String incomplete(Message message) {
    return switch (message) {
        case Text(var value) -> "text";
    };
}
```

The compiler reports an error like **“the switch expression does not cover all possible input values”**. Adding `Quit` while still forgetting `Payment` does not resolve the error.

The fix that preserves static checking benefits is to list all cases **without adding an unconditional `default`**:

```java
static String classifyMessage(Message message) {
    return switch (message) {
        case Text(var value) -> "text";
        case Payment(var id, var amount) -> "payment";
        case Quit() -> "quit";
    };
}
```

In this snippet, a null selector can throw `NullPointerException` because there is no `case null`. Type exhaustiveness does not automatically define null behavior. If you want to return an explicit code, add `case null -> "missing";`.

### 7.2. A `when` guard does not cover an entire subtype

```java
// DOES NOT COMPILE: Text(null) or Text(" ") has no matching branch.
static String guardOnly(Message message) {
    return switch (message) {
        case Text(var value) when value != null && !value.isBlank()
                -> "text:" + value;
        case Payment(var id, var amount) -> "payment";
        case Quit() -> "quit";
    };
}
```

Even though all three subtypes are named, the guarded `Text` branch only handles **a subset** of `Text` values. Therefore, the compiler cannot prove exhaustiveness. Fix by adding an unguarded `Text` branch **after** the guarded one:

```java
case Text(var value) when value != null && !value.isBlank()
        -> "text:" + value.strip();
case Text(var value) -> "empty-text";
```

This also makes the policy for null or blank strings explicit in code. In the main example, pattern guards and fallbacks are combined in this way.

### 7.3. Domination: a broad case hides a narrow case

```java
// DOES NOT COMPILE: String is dominated by the preceding CharSequence.
static String dominated(Object input) {
    return switch (input) {
        case CharSequence chars -> "chars";
        case String text -> "text";
        default -> "other";
    };
}
```

Every `String` is a `CharSequence`, so the later `String` case is flagged by the compiler as a **dominated case label**. The fix is to place the narrower case first:

```java
static String ordered(Object input) {
    return switch (input) {
        case String text -> "text";
        case CharSequence chars -> "chars";
        default -> "other";
    };
}
```

**Do not confuse the two error types:**

- **Non-exhaustive:** there are still valid values with no matching case.
- **Dominated:** a case is covered by an earlier case and can never be selected.

A `default` branch does not fix domination by itself. You must reorder the cases or remove the redundant branch.

### 7.4. Switch expressions vs. traditional switch statements

In Java 21, **switch expressions** and **enhanced switch statements** must be exhaustive. However, a **traditional switch statement** over an enum can still omit some cases and compile under backward-compatibility rules. For example:

```java
enum Status { NEW, ACTIVE, DONE }

static void printStatus(Status value) {
    switch (value) {
        case NEW -> System.out.println("new");
        case ACTIVE -> System.out.println("active");
        // Missing DONE; a traditional switch statement can still compile.
    }
}
```

Do not assume every `switch (...) { case ... -> ... }` is forced to be exhaustive by the compiler: the `->` arrow does not determine whether it is an expression or a statement. If you want the compiler to help catch missing enum cases, consider using a value-returning `switch` expression, or additional static analysis/test rules for statements.

## 8. Generic type erasure: why is `List<String>` not a regular type pattern?

This is a common mistake when migrating manual casts to type patterns.

```java
// DOES NOT COMPILE if raw has type Object.
static int invalidGeneric(Object raw) {
    return raw instanceof java.util.List<String> names
            ? names.size()
            : 0;
}
```

The compiler may report `java.lang.Object cannot be safely cast to java.util.List<java.lang.String>` or a diagnostic stating the type cannot be safely checked. Because of **type erasure**, at runtime a plain `List` does not retain the full `String` type argument on the object for `instanceof` to verify.

The right approach for an `Object` input:

```java
static int countStrings(Object raw) {
    if (!(raw instanceof java.util.List<?> values)) return 0;

    int count = 0;
    for (Object value : values) {
        if (value instanceof String text) {
            count++;
        }
    }
    return count;
}
```

Here the compiler checks `List<?>` and `values` has a wildcard list type; each element is checked with its own type pattern. A `List<Integer>` still matches `List<?>`, but none of its elements match `String`.

**Do not work around this with an unchecked cast and suppressed warnings.** If element types are not guaranteed, casting to `List<String>` only defers the failure to a later element access. Validate data at system boundaries.

## 9. Complete Java 21 program: accepted by the compiler and verified with 16 tests

Create **`CompilerPatternCheckDemo.java`** with the following full content:

```java
public class CompilerPatternCheckDemo {
    sealed interface Message permits Text, Payment, Quit {}
    record Text(String value) implements Message {}
    record Amount(int cents, String currency) {}
    record Payment(String id, Amount amount) implements Message {}
    record Quit() implements Message {}

    static String dispatch(Message message) {
        return switch (message) {
            case null -> "null-message";

            case Text(var value) when value != null && !value.isBlank()
                    -> "text:" + value.strip();
            case Text(var value) -> "empty-text";

            case Payment(var id, Amount(var cents, var currency))
                    when cents > 0 && currency != null && !currency.isBlank()
                    -> "payment:" + id + ":" + cents + ":" + currency;
            case Payment(var id, Amount(var cents, var currency))
                    -> "invalid-payment";
            case Payment(var id, var amount) -> "missing-amount";

            case Quit() -> "quit";
        };
    }

    static String classify(Object input) {
        if (input instanceof String value && !value.isBlank()) {
            return "string:" + value.strip();
        }
        if (input instanceof Integer number) {
            return "integer:" + number;
        }
        return input == null ? "null-value" : "other";
    }

    static int checks;

    static void expect(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                name + " expected " + expected + ", actual " + actual
            );
        }
        checks++;
        System.out.println("PASS " + name + " => " + actual);
    }

    public static void main(String[] args) {
        expect("text", "text:hello",
                dispatch(new Text(" hello ")));
        expect("text-blank", "empty-text",
                dispatch(new Text("  ")));
        expect("text-null", "empty-text",
                dispatch(new Text(null)));

        expect("payment", "payment:P1:250:USD",
                dispatch(new Payment("P1", new Amount(250, "USD"))));
        expect("payment-zero", "invalid-payment",
                dispatch(new Payment("P2", new Amount(0, "USD"))));
        expect("payment-negative", "invalid-payment",
                dispatch(new Payment("P3", new Amount(-10, "USD"))));
        expect("payment-null-currency", "invalid-payment",
                dispatch(new Payment("P4", new Amount(100, null))));
        expect("payment-blank-currency", "invalid-payment",
                dispatch(new Payment("P5", new Amount(100, " "))));
        expect("payment-null-amount", "missing-amount",
                dispatch(new Payment("P6", null)));

        expect("quit", "quit", dispatch(new Quit()));
        expect("null-message", "null-message", dispatch(null));

        expect("string", "string:Java", classify(" Java "));
        expect("blank-string", "other", classify("   "));
        expect("integer", "integer:7", classify(7));
        expect("long", "other", classify(7L));
        expect("null-value", "null-value", classify(null));

        System.out.println("checks=" + checks);
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 CompilerPatternCheckDemo.java
java CompilerPatternCheckDemo
```

**Exact stdout:**

```text
PASS text => text:hello
PASS text-blank => empty-text
PASS text-null => empty-text
PASS payment => payment:P1:250:USD
PASS payment-zero => invalid-payment
PASS payment-negative => invalid-payment
PASS payment-null-currency => invalid-payment
PASS payment-blank-currency => invalid-payment
PASS payment-null-amount => missing-amount
PASS quit => quit
PASS null-message => null-message
PASS string => string:Java
PASS blank-string => other
PASS integer => integer:7
PASS long => other
PASS null-value => null-value
checks=16
```

### 9.1. Which static checks does this code pass?

- `sealed interface Message` has three subtypes: `Text`, `Payment`, and `Quit`. The final general branches for each subtype make the `switch` expression **exhaustive** without needing a `default`.
- `case Text(var value) when ...` comes before `case Text(var value)` so the broader case does not dominate the narrower one.
- `case Payment(... Amount(...)) when ...` comes before the unguarded nested `Payment(... Amount(...))` case. The final `case Payment(var id, var amount)` covers `Payment` with a null `amount` and any remaining cases.
- The record patterns have the right component counts: `Payment` has two and `Amount` has two.
- Pattern variables `value`/`id`/`cents`/`currency` are only used within valid scopes.
- `case null` handles a null selector explicitly.
- `classify` combines `instanceof String value && ...`, so the right-hand side only uses `value` after the pattern matches.

### 9.2. What has the compiler NOT proven?

The compiler cannot deduce on its own that `250` cents is valid while `0` cents is invalid under business rules. Nor does it know that `currency` can be blank, or that returning `"invalid-payment"` is the expected result. That is why the 16 assertions test both **valid and boundary values**.

For example, `new Payment("P6", null)` does not match the nested `Amount(...)` pattern and falls into the remaining `Payment` case. By contrast, `new Payment("P4", new Amount(100, null))` matches the nested record, fails the guard, and is handled by the unguarded nested case as `invalid-payment`. These two cases differ by only one null level, making them easy to miss if you only test the happy path.

In `classify`, `"   "` is a `String` that fails the guard, so the result is `other`. `7L` is a `Long`, does not match `Integer`, and also produces `other`. The compiler guarantees valid control flow; tests guarantee **correct results** for the chosen inputs.

### 9.3. Assertions without external test libraries

The `expect` method compares `expected` with `actual`. If they are unequal, it throws `AssertionError` and the program stops before completing all checks. `PASS` is printed only after a successful comparison.

The line `checks=16` means **the 16 checks in the example passed**, not that every possible Java input or business rule is covered. In a larger project, move these tests to JUnit 5 or your existing test framework, adding interaction tests and boundary data as required by the product.

## 10. Compile-time error set for self-practice

This is an important exercise: **predict why the compiler rejects each snippet**, then fix it. The intentionally invalid snippets **do not belong in the runnable file from Section 9**. If you put them into the same source folder and run a normal build, the build will fail by design.

| Error snippet | Expected compiler outcome | How to fix |
| --- | --- | --- |
| Only `case Text` when selector is sealed `Message` | Non-exhaustive `switch` expression | Add `Payment` and `Quit` or an intentional fallback. |
| `case Text(...) when ...` with no other `Text` branch | False guard leaves `Text` uncovered | Add an unguarded `Text` case after the specific branch. |
| `case CharSequence` before `case String` | `String` case is dominated | Put `String` before `CharSequence`. |
| `Point(var x)` for `record Point(int x,int y)` | Wrong arity in nested patterns | Use two component patterns. |
| `raw instanceof List<String> names` on raw `Object` | Cannot safely check generic type argument | Use `List<?>` and check each element. |
| `return text.length()` after `if (raw instanceof String text) {...}` | Pattern variable is not in guaranteed scope | Negated guard clause and early return. |
| Record deconstruction with `--release 17` | Syntax not supported at source level 17 | Use type pattern + accessors or upgrade to source 21. |

### 10.1. How to organize negative compilation tests

If you want to test the compiler like a unit test, put **each intentionally invalid snippet** into its own fixture or a compilation-negative test step. The goal of such a test is to **expect the compiler to reject it**, not to expect the program to run.

Conceptual workflow example in a Unix-like shell:

```bash
# BadSwitch.java is an intentionally invalid fixture, outside main source.
if javac --release 21 BadSwitch.java; then
    echo "FAIL: compiler unexpectedly accepted BadSwitch.java"
    exit 1
else
    echo "PASS: compiler rejected BadSwitch.java"
fi
```

This example only verifies that the compiler returns a non-zero exit code. If you need to assert the *exact cause* (rather than a typo or missing import), check the **diagnostic kind**, location, and fixture structure. Do not rely strictly on exact message wording, as it can change across JDK versions.

**Do not mix intentionally non-compiling fixtures into `src/main/java` or `src/test/java` in a regular build.** Doing so will keep the entire pipeline red even when production code is valid. Create a separate job or check when the team genuinely needs compile-negative tests.

## 11. Comparing Java 17 and Java 21 commands

### 11.1. Type patterns for `instanceof` on Java 17

Small file **`TypePattern17.java`**:

```java
public class TypePattern17 {
    static String parse(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "text:" + text.strip();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(parse(" java "));
        System.out.println(parse(7));
        System.out.println(parse(null));
    }
}
```

Commands:

```bash
javac --release 17 TypePattern17.java
java TypePattern17
```

Output:

```text
text:java
other
other
```

This small comparison demonstrates that type patterns with `instanceof` **do not require Java 21**. The `strip()` and `isBlank()` methods were already available in earlier Java releases prior to Java 17.

### 11.2. Record deconstruction is invalid at release 17

Even if the project defines `record Point`, the snippet:

```java
// DOES NOT COMPILE with --release 17:
record Point(int x, int y) {}

static int first(Object input) {
    if (input instanceof Point(var x, var y)) return x;
    return -1;
}
```

is rejected by the compiler with a message equivalent to **“deconstruction patterns are not supported in -source 17”**. This is not a missing constructor on `Point` or a broken classpath: **Java 17 simply does not have record patterns**.

Java 17-compatible fix:

```java
static int first(Object input) {
    if (input instanceof Point point) return point.x();
    return -1;
}
```

If the project upgrades to Java 21, use `Point(var x, var y)` as a standard feature. Do not apply Java 21 preview flags to source level 17; the compiler does not use preview flags to “backport” features to an earlier release.

## 12. Integrating compiler checks into Maven, Gradle, and CI

### 12.1. Maven Compiler Plugin with Java 21

In a Maven Java project with appropriate plugin configuration running on a JDK supporting 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

In CI, run a build command that executes both compile and test phases, for example:

```bash
mvn clean verify
```

If the code has a pattern switch missing a case or a flow-scoping error, the compiler fails the build step. If the code compiles but an assertion fails, the test step fails. Those two failure sources should be reported separately for accurate diagnosis.

### 12.2. Gradle Groovy DSL

Example Java 21 toolchain configuration in `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

In a project with the Gradle Wrapper, prefer the wrapper command appropriate for your OS:

```bash
./gradlew clean test
```

On Windows, use `gradlew.bat clean test` when applicable. The snippets above are illustrative configurations, not complete build files; your Maven/Gradle/plugin versions must support JDK 21 and the actual test runner.

### 12.3. What should a minimal CI pipeline prove?

A good pipeline should:

1. **Verify the toolchain:** compiler, source/release, and runtime versions match.
2. **Compile main code:** block invalid syntax, invalid types, non-exhaustive switches, and dominated cases.
3. **Compile tests:** do not let test source errors go unnoticed.
4. **Run tests:** compare expected/actual values and check null, true/false guards, fallbacks, and exceptions.
5. **Run additional lint/static analysis when valuable:** IDE inspections, Error Prone, PMD, Checkstyle, or SpotBugs can catch distinct bug classes depending on their Java 21 support.
6. **Report failures at the right stage:** compile errors are distinct from test failures and runtime/dependency/environment failures.

A warning does not necessarily fail a build unless `-Werror` is enabled; a compile error always makes `javac` fail. Do not lower build standards by removing `-Werror` or disabling tests without evaluating the impact.

**Tooling limits:** External static analysis can help, but `javac` remains the arbiter of syntax and language rules at your chosen release level. No linter can turn Java 17 code with unsupported record patterns into valid code.

## 13. Common misconceptions when reading error messages

| Symptom | Cause worth checking | How to handle |
| --- | --- | --- |
| `invalid source release: 21` | `javac` is too old for target 21 | Select a JDK compiler/toolchain that supports Java 21. |
| `deconstruction patterns not supported in source 17` | Java 21 record pattern used at release 17 | Keep a type pattern with accessors or raise the release. |
| `switch expression does not cover all possible input values` | Missing subtype or guard only covers a subset | List an appropriate unguarded case or an intentional fallback. |
| `case label is dominated` | Broader branch appears before narrower branch | Reorder cases or remove the redundant branch. |
| `cannot find symbol: text` after `instanceof` | Pattern variable used outside flow scope | Use a guard clause/early return or place code inside the right branch. |
| `incorrect number of nested patterns` | Record pattern has too few or too many components | Compare the record declaration with the pattern position count. |
| `Object cannot be safely cast to List<String>` | Erasure makes the generic type non-reifiable here | Use `List<?>` and validate elements. |
| `NullPointerException` at runtime in `switch` | Null selector has no explicit handler or branch code dereferences a null component | Add `case null`/guards per contract; test null at every level. |
| `ClassCastException` at runtime in legacy cast code | Direct cast not protected by a type check | Use a type pattern + non-match path or report an explicit error. |
| `UnsupportedClassVersionError` at runtime | Runtime is older than the bytecode produced by the compiler | Align target/runtime or compile for a lower release if source is compatible. |
| Code runs in IDE but fails to compile in CI | IDE and CI use different source levels/JDKs | Compare toolchains, `--release`, and build configuration. |
| Code compiles but returns wrong output for blank/null data | Compiler does not check business semantics | Write tests with expected values per contract. |
| Fallback branch hides new subtypes | `default` keeps the `switch` exhaustive when the type hierarchy grows | On sealed hierarchies, consider omitting `default` so the compiler prompts updates. |
| Build emits warnings yet CI stays green | Warnings are not treated as errors | Review `-Xlint` and `-Werror` policies instead of guessing whether errors exist. |

When encountering a diagnostic, **fix the earliest cause first and recompile**. A single syntax error near the top of a file can cascade into many secondary errors. Do not “patch over” it by adding casts, adding `default`, or silencing warnings without understanding the root error.

## 14. Self-assessment exercises

### Exercise A — Complete an exhaustive switch

Given:

```java
sealed interface Event permits Created, Deleted {}
record Created(String id) implements Event {}
record Deleted(String id) implements Event {}

// DOES NOT COMPILE: missing Deleted.
static String describe(Event event) {
    return switch (event) {
        case Created(var id) -> "created:" + id;
    };
}
```

**Requirement:** Fix without using `default`, and add explicit null handling.

**Answer:**

```java
static String describe(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created(var id) -> "created:" + id;
        case Deleted(var id) -> "deleted:" + id;
    };
}
```

The compiler verifies that all subtypes are covered. Test `Created("A")`, `Deleted("B")`, and `null` to verify branch outputs.

### Exercise B — Spot the dominated case

```java
// DOES NOT COMPILE.
static String classify(Object input) {
    return switch (input) {
        case Number n -> "number";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Fix by moving `case Integer n` before `case Number n`. Reason: every `Integer` is a `Number`. After fixing, test that `7` returns `integer`, `7L` returns `number`, and a string returns `other`. Simply adding `default` does not resolve domination.

### Exercise C — A false guard also needs a branch

Given:

```java
record Order(int quantity) {}

// DOES NOT COMPILE when the selector has type Order and only a guarded case exists.
static String status(Order order) {
    return switch (order) {
        case Order(var quantity) when quantity > 0 -> "ok";
    };
}
```

Add:

```java
static String status(Order order) {
    return switch (order) {
        case null -> "missing";
        case Order(var quantity) when quantity > 0 -> "ok";
        case Order(var quantity) -> "invalid";
    };
}
```

Test `Order(1)` → `ok`; `Order(0)` and `Order(-1)` → `invalid`; `null` → `missing`. The compiler guarantees pattern exhaustiveness, while tests verify that the definition of “positive quantity” matches business rules.

### Exercise D — Java 17 compatibility

Given:

```java
record Pair(String left, String right) {}

// DOES NOT COMPILE at source level 17:
static String left(Object input) {
    if (input instanceof Pair(var a, var b)) return a;
    return "other";
}
```

Rewrite for Java 17 compatibility:

```java
static String left(Object input) {
    if (input instanceof Pair pair) {
        return pair.left();
    }
    return "other";
}
```

Test `new Pair("A","B")` → `A` and `null` → `other`. This exercise does not require upgrading the release; the goal is to understand the boundary between **record classes** (Java 16+) and **record deconstruction patterns** (Java 21 final).

## 15. Final checklist before submitting Pattern Matching code

1. **Right JDK?** Check `java -version`, `javac -version`, Maven/Gradle toolchain, and CI image.
2. **Right source/release?** Type pattern `instanceof` works since Java 16; record/switch patterns are standard since Java 21.
3. **Abusing preview flags?** Do not enable preview for already-standard features or to “force” future syntax onto an older release.
4. **Valid flow scope?** Pattern variables are only used along control-flow paths where the compiler guarantees a match.
5. **Right component count in case patterns?** Check arity and types against the record declaration.
6. **Exhaustive switch?** Pay special attention to sealed hierarchies, `when` guards, and intentional fallbacks.
7. **Valid case order?** Narrow cases before broad cases; specific guarded cases before unguarded cases of the same type.
8. **Null handled?** Distinguish a null selector from null components inside a record.
9. **No non-reifiable generic type arguments in `instanceof`?** Use wildcards and check elements when needed.
10. **Clean compile at the target release?** Do not rely solely on IDE highlighting or stale class files on disk.
11. **Tests have independent expected values?** Test matches, non-matches, true/false guards, boundary values, and exceptions.
12. **CI runs both compile and test?** The compiler catches many structural errors; tests protect semantics.
13. **Negative compilation tests separated?** Do not put intentionally invalid code into regular build sources.
14. **Re-checked errors after fixing?** Do not use `default` or drop logic just to silence a diagnostic without understanding the root cause.

## 16. Conclusion

**Checking with the Java compiler** is an active step to confirm that a Pattern Matching snippet is **valid for the chosen Java version and type system**. `javac` can catch invalid scope, wrong component counts, missing `switch` expression cases, guards that do not cover a subtype, dominated cases, and many generic checks that cannot be performed safely.

However, **compile success does not replace runtime tests**. The Java 21 program in Section 9 shows the right combination: the compiler accepts the sealed `switch` and record patterns, while **16 assertions** confirm that valid, blank, null, failing-condition, and fallback inputs produce the exact expected results.

The workflow to remember: **identify JDK/source level → compile → read diagnostics → fix the root cause → recompile → run assertions → integrate into CI**. Following that cycle, you not only know the new syntax, but can also reliably verify and maintain Java Pattern Matching code.

**Official documentation:**

- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java SE 21 Language Specification — switch blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [javac command reference, Java 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
