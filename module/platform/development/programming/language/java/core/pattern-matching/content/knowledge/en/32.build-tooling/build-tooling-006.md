# Checkstyle and Pattern Conventions in Java 21

## 1. Objectives

In the **Build and tooling** group, adopting pattern matching does not stop at code that compiles. A codebase written by multiple people needs **consistent conventions** for pattern variable names, line wrapping with `instanceof` / record patterns, formatting `when` guards, handling `switch` branches, and knowing where not to overuse deconstruction.

**Checkstyle** is a static analysis tool primarily intended to check **style and certain coding practices**. It has checks specifically for pattern variables and modern Java syntax, but it **does not replace `javac`, unit tests, or behavioral code reviews**.

After this lesson, you will know how to:

- Set up a Checkstyle configuration applicable to a Java 21 project, using the exact module names and their supported scopes.
- Enforce `lowerCamelCase` for pattern variables and restrict reassigning bound variables.
- Format `instanceof`, record patterns, `switch`, and `when` for readability, without "code golf".
- Distinguish style rules from errors checked by the compiler: types, scope, dominance, exhaustiveness, and `null`.
- Integrate Checkstyle into Gradle, Maven, or CLI, and accurately interpret the check results.
- Build a pattern-matching review checklist for things tools cannot fully conclude automatically.

**Example versions:** Java 21, Checkstyle **14.3.0** is the illustrative version chosen for the configuration file. The Checkstyle 14.x branch requires **JDK 21 or higher to run Checkstyle**. This is a **version pinned for the example**, not a requirement that every project must use this exact version. For projects with different toolchains, you must choose a Checkstyle version that supports both the source syntax and the JDK running the analyzer.

## 2. Three Verification Layers to Keep Separate

A quality pipeline should clearly distinguish:

| Tool / Layer | Responsible for checking | Cannot conclude on its own |
|---|---|---|
| **`javac --release 21`** | Syntax, types, pattern variable scope, certain `switch` dominance/exhaustiveness rules | Variable naming style, business meaning of each case |
| **Checkstyle** | Configured rules such as variable naming, whitespace, line length, certain coding practices | Full coverage of all `null` values, guard correctness, equivalence after refactoring |
| **Tests and review** | Real inputs, business outcomes, fallback branches, `null`, boundaries, behavior preservation | Cannot guarantee all cases if test data and coverage are insufficient |

For example:

```java
if (input instanceof String DATA) {
    System.out.println(DATA);
}
```

The snippet above **compiles validly**, but under a `lowerCamelCase` pattern variable convention, the name `DATA` is a style violation. The Checkstyle `PatternVariableName` module can detect this.

Conversely, the snippet:

```java
if (input instanceof String text || text.isBlank()) {
    System.out.println("text");
}
```

is an example that is **invalid regarding flow scoping**: on the right-hand side of `||`, `text` might not be bound. Before debating formatting, the compiler must catch and eliminate this error.

**Sensible verification order:** build with the compiler for the right Java version → run Checkstyle → run unit/integration tests → review domain decisions that machines lack the context to prove.

## 3. Checks Directly Related to Pattern Matching

Checkstyle is configured using **modules**. Not every plausible-sounding name exists; use the actual names and scopes from the Checkstyle documentation.

| Module | Purpose and notes | Available in Checkstyle since |
|---|---|---|
| **`PatternVariableName`** | Checks pattern variable names against the `format` regex. Unlike `LocalVariableName`, which does not process pattern variables | 8.36 |
| **`PatternVariableAssignment`** | Reports when a bound pattern variable is reassigned, to prevent the variable from changing meaning after matching | 10.26.0 |
| **`WhitespaceAround`** | Checks whitespace around a supported set of tokens; includes the `LITERAL_WHEN` token, but check the limitations regarding switch expressions | Long-standing check, supported tokens depend on version |
| **`LineLength`** | Checks line length; useful for nested record patterns and long guards | Long-standing check |
| **`MissingSwitchDefault`** | Checks for missing `default` in **certain traditional switch statements**. **Does not check switch expressions or switch statements using pattern/null labels**, because the compiler already performs corresponding exhaustiveness checks | 3.1 |
| **`WhenShouldBeUsed`** *(optional)* | Detects a pattern case containing a single `if` inside its block that could be clearly expressed with a `when` guard | 10.18.0 |

The modules listed above have official documentation in the references section. **Not every rule needs to be enabled in every project.** For example, `WhenShouldBeUsed` reflects a preference for how guards are written; discuss within the team before applying it broadly, especially when the `if` has side effects, an `else`, or logic that must preserve ordering.

### 3.1. Why not just use LocalVariableName?

In Checkstyle, `LocalVariableName` is designed for regular local variables and **does not check pattern variables**. To catch:

```java
if (value instanceof String CUSTOMER_ID) {
    // Pattern variable name is in ALL_CAPS, violating this convention.
}
```

you need `PatternVariableName`. If only `LocalVariableName` is enabled, a team might assume the naming rule set covers the new pattern syntax when in reality it does not.

### 3.2. Why is PatternVariableAssignment useful even though javac allows reassignment?

Since Java 16, pattern variables are **not implicitly final**. Therefore, the following snippet is valid syntax:

```java
if (value instanceof String text) {
    text = text.trim();
    System.out.println(text);
}
```

However, when `text` is reassigned, readers might assume it still represents the exact matched value. `PatternVariableAssignment` helps the team forbid this style at the style layer. A clearer way to write it:

```java
if (value instanceof String text) {
    String normalizedText = text.trim();
    System.out.println(normalizedText);
}
```

This is a **convention choice**, not a claim that `javac` requires pattern variables to be `final`.

## 4. A checkstyle.xml File for Java 21

Assume the project has the following structure:

```text
project/
├── build.gradle               # or pom.xml
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
└── src/
    └── main/
        └── java/
            └── ...
```

Create **`config/checkstyle/checkstyle.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="LineLength">
        <property name="max" value="100"/>
    </module>

    <module name="TreeWalker">
        <module name="PatternVariableName">
            <property name="format" value="^[a-z][a-zA-Z0-9]*$"/>
        </module>
        <module name="PatternVariableAssignment"/>
        <module name="WhitespaceAround"/>
        <module name="MissingSwitchDefault"/>
    </module>
</module>
```

### Exact Breakdown of Each Part

- **`Checker`** is the root module. `LineLength` is placed **directly inside Checker**, not inside `TreeWalker`.
- **`TreeWalker`** contains checks that need to parse Java syntax, such as `PatternVariableName` and `PatternVariableAssignment`.
- The regex `^[a-z][a-zA-Z0-9]*$` is a **fairly strict** choice: pattern names start with a lowercase ASCII letter, followed by letters/digits, disallowing underscores or all-uppercase names. Teams can choose another regex if project conventions require it.
- **`WhitespaceAround`** applies Checkstyle's default token set; it does not mean it acts as a formatter for an entire `switch`.
- **`MissingSwitchDefault`** is kept to illustrate a traditional check; do not mistakenly think enabling it means you must add `default` to every `switch expression` or pattern `switch`.

The XML configuration above has been checked for **valid XML syntax** and confirmed for the intended module tree; **actually running Checkstyle** still requires downloading/depending on the right tool version and running one of the commands in Section 8. This template does not force every project to replace its entire existing style set; if a project already uses `google_checks.xml` or internal rules, **merge them intentionally** to avoid duplicate or conflicting checks.

**Version note:** `PatternVariableAssignment` is only available starting in Checkstyle **10.26.0**; an older Checkstyle version will not recognize this module. Moreover, parse support for Java 21 syntax also depends on the Checkstyle version, not just the JDK running the analyzer. Therefore, pin the Checkstyle version in the build rather than relying on the plugin's default version.

## 5. Naming Conventions for Pattern Variables

Naming is part of the **cognitive API** for the reader: the variable bound in a branch is what you will use next.

**Recommended:**

```java
if (input instanceof String customerId) {
    System.out.println(customerId);
}

if (input instanceof Integer retryCount) {
    System.out.println(retryCount);
}
```

**Not recommended under this convention:**

```java
if (input instanceof String CUSTOMER_ID) {
    System.out.println(CUSTOMER_ID);
}

if (input instanceof Integer retry_count) {
    System.out.println(retry_count);
}
```

Both snippets illustrate **the body of a method that has an `input` variable**, not standalone programs. With the regex in Section 4, `CUSTOMER_ID` and `retry_count` do not conform to the pattern naming standard.

### Choose Names That Express Roles, Not Just Satisfy Regex

`text`, `customerId`, `retryCount`, and `request` usually help readers understand the context better than single-letter names like `x`, `s`, `r` when the logic is longer.

In a record pattern:

```java
case Search(String query, int limit) when limit > 0 -> ...
```

`query` and `limit` express the component meanings. Do not change them to `a` / `b` just because a pattern is already short. `PatternVariableName` can check a regex, but it **cannot evaluate on its own whether a name expresses business meaning well enough**.

### Avoid Shadowing and Name Collisions

If a pattern name causes a scope conflict with another variable, `javac` will report a scope error. This is a language error, distinct from a naming check. Do not fix a shadowing error merely by adding meaningless suffixes; name the variable according to its role or split the processing scope for clearer reading.

## 6. Formatting Conventions for Type, Record, and Switch Patterns

### 6.1. Keep Simple Type Patterns on One Line

```java
if (input instanceof String text) {
    return text.trim();
}
```

If there is a simple guard, use `&&` with short-circuiting:

```java
if (input instanceof String text && !text.isBlank()) {
    return text.trim();
}
```

The `text` variable is only used when the pattern matches. With a `null` root, `instanceof` returns false. When the expression gets long, wrap lines by responsibility group rather than cramming every condition onto one line.

### 6.2. Nested Record Patterns: Wrap by Structural Level

When multiple components must be deconstructed:

```java
if (input instanceof Order(
        var orderId,
        Customer(var customerName, Address(var city, var country)),
        var total)
        && total >= 100
        && "VN".equals(country)) {
    return "READY:" + orderId;
}
```

**This is an illustrative snippet**, assuming the `Order`, `Customer`, and `Address` records are already declared and the method returns `String`. Suggested conventions:

- Split large components across lines with consistent indentation so it is clear which record level contains which.
- Name components according to the domain; do not deconstruct unnecessary levels.
- Align `&&` conditions underneath one another so short-circuit ordering is readable.
- Keep **null-safe** string comparisons such as `"VN".equals(country)` when a component may be null.
- Do not assume reference components are non-null just because the outer record matched.

**Do not enforce a single indentation style with a simple regex.** Checkstyle has whitespace/indentation checks, but support levels for each AST token and version can vary. Run it directly on real Java 21 code, inspect the sensible violations, and then finalize the team rules.

### 6.3. `when` Guards: Short and Named Expressions

```java
case Search(String query, int limit)
        when query != null && !query.isBlank() && limit > 0
        -> "SEARCH:" + query.trim() + "/" + limit;
```

If a guard has more business constraints, instead of chaining six more conditions inside `when`, consider a method such as `isEligible(query, limit)`. Extracting a helper is only safe when it preserves evaluation order, `null` handling, and short-circuiting.

**`WhenShouldBeUsed`** is an optional check that can suggest converting a single `if` inside a pattern case block into a `when` guard. However, it cannot replace human judgment on whether moving the condition to the case label preserves exceptions/side effects.

### 6.4. Do Not Force `default` into Sealed/Enum Switch Expressions

```java
sealed interface Request permits Search, Refresh {}

record Search(String query, int limit) implements Request {}
record Refresh(String target) implements Request {}
```

For a `switch expression` that handles both types, you can list the specific branches **without `default`**. When a new subtype is added, the compiler can force updating the handling site — the advantage of exhaustive checking.

Conversely, a `switch` over `Object` has unbounded value types and usually **needs `default`** if no type pattern covers the remainder. Thus, a style rule saying "every switch must have default" is both crude and can cause new subtypes to be missed.

**Actual check scope:** According to Checkstyle documentation, `MissingSwitchDefault` **does not check switch expressions**, and **does not check switch statements with pattern or null labels**. It remains useful for certain other traditional switch statements. Do not misconfigure this check to replace the Java 21 compiler's exhaustiveness checking.

## 7. Standalone Java 21 Program: Convention-Compliant Example

Create **`PatternStyleDemo.java`**:

```java
import java.util.Objects;

public class PatternStyleDemo {
    sealed interface Request permits Search, Refresh {}
    record Search(String query, int limit) implements Request {}
    record Refresh(String target) implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case null -> "NULL_REQUEST";
            case Search(String query, int limit)
                    when query != null && !query.isBlank() && limit > 0
                    -> "SEARCH:" + query.trim() + "/" + limit;
            case Search(var query, var limit) -> "INVALID_SEARCH";
            case Refresh(var target)
                    when target != null && !target.isBlank()
                    -> "REFRESH:" + target.trim();
            case Refresh(var target) -> "INVALID_REFRESH";
        };
    }

    static String classify(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.trim();
        }
        return "OTHER";
    }

    static void test(String label, String actual, String expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("search good", handle(new Search("java", 3)), "SEARCH:java/3");
        test("search trimmed", handle(new Search(" java ", 1)), "SEARCH:java/1");
        test("search blank", handle(new Search("  ", 1)), "INVALID_SEARCH");
        test("search null", handle(new Search(null, 1)), "INVALID_SEARCH");
        test("limit zero", handle(new Search("java", 0)), "INVALID_SEARCH");
        test("limit negative", handle(new Search("java", -1)), "INVALID_SEARCH");
        test("refresh good", handle(new Refresh(" cache ")), "REFRESH:cache");
        test("refresh blank", handle(new Refresh(" ")), "INVALID_REFRESH");
        test("refresh null", handle(new Refresh(null)), "INVALID_REFRESH");
        test("request null", handle(null), "NULL_REQUEST");
        test("text", classify("hello"), "TEXT:hello");
        test("blank text", classify("  "), "OTHER");
        test("wrong type", classify(12), "OTHER");
        test("null type", classify(null), "OTHER");
    }
}
```

Compile and run:

```bash
javac --release 21 PatternStyleDemo.java
java PatternStyleDemo
```

**Verified stdout:**

```text
search good => SEARCH:java/3
search trimmed => SEARCH:java/1
search blank => INVALID_SEARCH
search null => INVALID_SEARCH
limit zero => INVALID_SEARCH
limit negative => INVALID_SEARCH
refresh good => REFRESH:cache
refresh blank => INVALID_REFRESH
refresh null => INVALID_REFRESH
request null => NULL_REQUEST
text => TEXT:hello
blank text => OTHER
wrong type => OTHER
null type => OTHER
```

The example was **compiled with `javac --release 21` and run successfully across 14 scenarios**, with each result compared independently against expected values. This is a **Java syntax and behavior check**, not a substitute for running the Checkstyle binary on this file; run the Checkstyle tool using a command in Section 8 to determine actual style results in that environment.

Notable style points:

- Pattern variables `query`, `limit`, `target`, and `text` have role-descriptive names in `lowerCamelCase`.
- Pattern variables are not reassigned; `trim()` values are used directly to construct results.
- The `switch expression` covers `Search` and `Refresh` with guarded + fallback case pairs for each type, **without `default`**. `case null` is declared explicitly because the contract wants to return `NULL_REQUEST`.
- Guards place the `null` check before `isBlank()`; null query/target cases do not throw NPE.
- `classify` demonstrates `instanceof String text && ...` clearly without manual casting.
- Invalid data outcomes are verified by tests rather than expecting Checkstyle to validate logic.

## 8. Running Checkstyle in a Project

Choose **one** of the three approaches suited to your existing build. This illustration assumes Java sources are in `src/main/java` and the configuration is at `config/checkstyle/checkstyle.xml`. If your project layout differs, adjust the paths accordingly.

### 8.1. Gradle with the Checkstyle Plugin

Add to **`build.gradle`** (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'checkstyle'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

checkstyle {
    toolVersion = '14.3.0'
    configFile = file('config/checkstyle/checkstyle.xml')
}
```

Run in a project using the Gradle Wrapper:

```bash
./gradlew checkstyleMain
./gradlew check
```

- `checkstyleMain` checks the main Java sources.
- `check` integrates configured checks, including Checkstyle and tests per the Gradle model.
- Choose a JDK to run Checkstyle that is compatible with the tool version; **Checkstyle 14.x requires JDK 21+**. In some projects with special toolchains, you need to configure a separate launcher for the Checkstyle task.
- Do not treat `java.toolchain` as an automatic guarantee that every older Gradle version will support Checkstyle 14.x; verify the wrapper version and actual tool configuration.

According to Gradle documentation, the Checkstyle plugin may have a **default analyzer version** different from the one you need; therefore, pin `toolVersion` instead of just applying the plugin and assuming all new pattern checks are supported.

### 8.2. Maven with the Maven Checkstyle Plugin

Inside **`<build><plugins>`** in `pom.xml`, use a plugin entry:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <configuration>
        <configLocation>config/checkstyle/checkstyle.xml</configLocation>
        <encoding>UTF-8</encoding>
        <consoleOutput>true</consoleOutput>
        <failsOnError>true</failsOnError>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>com.puppycrawl.tools</groupId>
            <artifactId>checkstyle</artifactId>
            <version>14.3.0</version>
        </dependency>
    </dependencies>
    <executions>
        <execution>
            <id>checkstyle-verify</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**This is a fragment for `pom.xml`**, not a complete `pom.xml`. The Maven plugin and the Checkstyle library have **independent release cycles**: if you do not specify the Checkstyle dependency, the plugin may run an older bundled Checkstyle version and fail to recognize the modules or Java 21 syntax you intend to enforce.

Run:

```bash
./mvnw checkstyle:check
./mvnw verify
```

If not using the Maven Wrapper, replace `./mvnw` with `mvn`. The `verify` phase in the configuration runs the `check` goal as part of the build lifecycle. Run on a JDK compatible with the pinned Checkstyle version; if the build uses a different JDK, configure the toolchain/execution accordingly.

**Note:** the illustrative configuration has `failsOnError` to stop when the tool encounters a processing error; failing the build on **style violations** is also governed by goal properties such as `failOnViolation` (the default for the `check` goal). In strict pipelines, confirm the desired properties from the plugin documentation and a real CI run.

### 8.3. CLI Without Maven/Gradle

If you have an appropriate standalone Checkstyle JAR, e.g. `checkstyle-14.3.0-all.jar`, run:

```bash
java -jar checkstyle-14.3.0-all.jar \
    -c config/checkstyle/checkstyle.xml \
    src/main/java
```

The command above illustrates a **Unix/Linux/macOS shell**; on PowerShell you can write it on one line or use a backtick for line continuation instead of `\`. Checkstyle checks all Java files in the specified directory; if targeting a single file, replace the directory path with the Java file path.

Do not commit a manually downloaded JAR into the repository if the project already has dependency management via Gradle/Maven. Verify the official download source and control versions in CI.

## 9. What Does Each Kind of Violation Look Like?

### 9.1. Pattern Name Not Matching the Format

```java
if (input instanceof String STRING_VALUE) {
    System.out.println(STRING_VALUE);
}
```

With the `PatternVariableName` configuration in Section 4, the name `STRING_VALUE` does not match `^[a-z][a-zA-Z0-9]*$`. Fix it to `stringValue`.

This is a **style violation**, not an example where you wait for the compiler to report a syntax error.

### 9.2. Reassigning a Pattern Variable

```java
if (input instanceof String text) {
    text = text.trim();
}
```

`PatternVariableAssignment` reports the reassignment. Fix:

```java
if (input instanceof String text) {
    String normalizedText = text.trim();
}
```

The second snippet only illustrates how to avoid reassigning a pattern variable; a broader rule set may flag an unused local variable. In production code, make sure to actually use `normalizedText`.

### 9.3. Expression Too Long

```java
if (input instanceof String text && text != null && !text.isBlank() && text.length() >= 5 && text.startsWith("A")) {
    System.out.println(text);
}
```

Even though the first line compiles in a valid context, it is hard to read. `LineLength max=100` helps catch the mechanical issue. In this example, `text != null` is redundant because the root `instanceof String text` only binds when non-null, but **Checkstyle is not responsible for proving every redundant null check**.

Fix by splitting the conditions:

```java
if (input instanceof String text
        && !text.isBlank()
        && text.length() >= 5
        && text.startsWith("A")) {
    System.out.println(text);
}
```

If there are many more domain conditions, extract them into a clearly named method instead of wrapping lines indefinitely.

### 9.4. Using `default` Out of Habit

```java
return switch (request) {
    case Search(var query, var limit) -> "SEARCH";
    case Refresh(var target) -> "REFRESH";
    default -> "OTHER";
};
```

Suppose `Request` is a sealed type with only `Search` and `Refresh`. `default` here can suppress the signal when someone adds a new subtype. For a closed-domain `switch expression`, consider **omitting `default`** so `javac` forces adding a case when the type hierarchy changes.

For nullable selectors, you still need an explicit policy for `case null` or exceptions. A regular `default` does not automatically handle null in Java 21 pattern switches.

### 9.5. No Checkstyle Errors, Yet the Code Is Still Wrong

A snippet with completely clean style:

```java
if (input instanceof String text && text.isBlank()) {
    return "VALID";
}
```

can still be functionally wrong if the requirement is "only accept non-blank strings". The bug is the missing `!`, not whitespace or pattern naming. Both the compiler and Checkstyle may accept it, so behavioral tests must catch it.

## 10. Handling MissingSwitchDefault Properly

This is a common point of confusion between style and program correctness.

### Switch Expression

```java
enum State { NEW, ACTIVE, CLOSED }

static String label(State state) {
    return switch (state) {
        case NEW -> "NEW";
        case ACTIVE -> "ACTIVE";
        case CLOSED -> "CLOSED";
    };
}
```

The compiler knows the enum set at build time and can check exhaustiveness. **Do not add `default` just because of a generic style rule.** Checkstyle `MissingSwitchDefault` currently does not check switch expressions.

### Pattern Switch Statement

```java
static void logEvent(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case String text -> System.out.println("string:" + text);
        default -> System.out.println("other");
    }
}
```

This is a standalone illustrative method using a Java 21 pattern switch. For switch statements using pattern/null labels, Checkstyle `MissingSwitchDefault` also skips the check according to current documentation; the compiler is responsible for exhaustiveness per language rules. Note that *compiler exhaustiveness* does not automatically guarantee each branch returns the right business message.

### Traditional Switch Statement

For an older-style traditional switch statement, for example:

```java
static void printLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("low");
            break;
        case 2:
            System.out.println("high");
            break;
    }
}
```

states other than 1/2 are unhandled. In this context, `MissingSwitchDefault` still has a reason to exist to encourage clarifying the fallback. **Do not apply this conclusion mechanically to exhaustive switch expressions over enums or sealed hierarchies.**

## 11. Should You Enable WhenShouldBeUsed?

Checkstyle has the **`WhenShouldBeUsed`** module since version 10.18.0. This is an example of a module to use only if the team agrees on it:

```xml
<module name="WhenShouldBeUsed"/>
```

This line is inserted **inside `TreeWalker`** in the configuration.

A pattern case with a single `if` inside its block:

```java
case String text -> {
    if (text.isEmpty()) {
        System.out.println("empty text");
    }
}
```

may be suggested to be rewritten as:

```java
case String text when text.isEmpty() -> {
    System.out.println("empty text");
}
```

In a `switch` with other matching branches, moving the action from inside the block to a guard can **change which branch is selected** when the condition is false. Therefore, **do not automatically treat the two snippets above as semantically equivalent in every switch**. Review the entire case ordering and fallback branches before modifying. This is a clear example showing that a static style rule does not replace behavioral review.

Do not enable this module across the entire repository just to make every case shorter. You can try it on a small module, observe false positives / cases that should not be refactored, and only then bring it into CI.

## 12. Integrating Checkstyle into CI as a Quality Gate

A minimal pipeline might look like:

```text
Source code
    |
    +--> javac --release 21     -> syntax, type, scope, exhaustiveness errors
    |
    +--> Checkstyle             -> naming, assignment, whitespace, length violations
    |
    +--> Unit tests             -> null, guard, branch, boundary, output
    |
    +--> Code review            -> clarity of intent, domain policy, maintenance cost
    |
    +--> Merge if gates pass and review is approved
```

**Recommended practices:**

- Pin the Checkstyle version and config in the repository so local and CI enforce the same policy.
- Ensure the JDK running the analyzer is recent enough; specifically, Checkstyle 14.x requires **JDK 21+**.
- Ensure compile/test uses the right source target: `--release 21` for record/pattern switch examples, rather than just checking with `javac` on a default JDK.
- If a project has multiple Java 11/17/21 modules, do not blindly apply the same Java 21 rule set to modules on older toolchains.
- Start with a high-signal rule set; avoid hundreds of new warnings causing "noise".
- When exceptions must be suppressed, document the reason clearly in the suppression configuration and review periodically, avoiding disabling all rules for a large directory.
- Use a consistent formatter if the team wants automatic formatting; **Checkstyle primarily reports style errors, not auto-fixes every line of code**.

### When the Build Fails, Classify Before Fixing

| Symptom | Issue Type | How to Handle |
|---|---|---|
| `javac` does not recognize `case ... when ...` | Mismatched Java source level/toolchain | Verify `--release 21` and JDK |
| Checkstyle reports `Unable to create Root Module` or check not found | Analyzer too old, wrong module name, or XML config error | Check Checkstyle version and check name |
| Checkstyle reports a parse error on a record pattern | Analyzer version does not yet support the Java syntax used, or source has a syntax error | Update analyzer; run `javac` to verify source |
| PatternVariableName flags name `DATA` | Naming style | Rename to `data` or intentionally adjust convention |
| PatternVariableAssignment flags reassigning `text` | Style/maintainability | Create a new variable for the processed value |
| LineLength flags a long line | Formatting | Wrap lines or extract a helper |
| Compiler reports dominated case | Pattern switch rules | Review broad/narrow case ordering |
| Compiler reports non-exhaustive switch | Missing branch in closed domain | Add the variant, **do not add default to mask the error** |
| Tests report NullPointerException on a leaf component | Runtime semantics | Check nullable components and short-circuiting |
| Tests produce wrong branch despite clean style | Business logic | Check guard/fallback, expected values, and boundary data |

An analyzer warning is a signal to analyze, not a reason to auto-fix in a way that changes behavior. In particular, moving an `if` from inside a case block to `when` or removing `default` must be reviewed across the entire switch.

## 13. Pattern Convention Checklist for Pull Request Reviews

| Criterion | Review Question |
|---|---|
| **Variable names** | Do they follow `lowerCamelCase` and express their role? |
| **Reassignment** | Is a pattern variable modified after binding? Can a new variable be used instead? |
| **Depth** | Is deconstructing each nested record necessary, or is a shallow type pattern clearer? |
| **Null** | Are root null, nested record null, and null reference components handled properly? |
| **Guards** | Are `&&`/`||` ordering, parentheses, and short-circuiting preserved? |
| **Scope** | Is the pattern variable only used where the compiler guarantees it has matched? |
| **Switch** | Do guarded branches precede general branches; is the fallback domain-accurate? |
| **Exhaustiveness** | For enums/sealed types, is `default` omitted when you want the compiler to catch new variants? |
| **Formatting** | Do naming, indentation, line length, and whitespace follow team conventions? |
| **Tooling** | Is Checkstyle running on a version that supports the current Java syntax and JDK? |
| **Tests** | Are there tests for wrong types, null, numeric boundaries, false guards, new branches, and independent expected values? |

Use this checklist alongside Checkstyle results: automated checks reduce review effort on mechanical details, while reviewers focus on **business meaning** and cases tools cannot analyze.

## 14. Self-Check Questions

**1. Can Java compile `if (input instanceof String NAME)`?**  
Yes, if `input` has a compatible type. If Checkstyle is configured for `lowerCamelCase` pattern names, `NAME` is a style error, not a type error.

**2. Why is enabling `LocalVariableName` not enough to check pattern variable names?**  
Because Checkstyle has a separate `PatternVariableName` check; `LocalVariableName` documentation explicitly states it does not check pattern variables.

**3. Can `text` be reassigned after `instanceof String text` matches?**  
The Java language since 16 allows it within the appropriate scope, but Checkstyle `PatternVariableAssignment` can forbid it as a readability policy.

**4. Does enabling `MissingSwitchDefault` force adding `default` to a switch expression over an enum?**  
No. This check does not inspect switch expressions and also skips switch statements with pattern/null labels per current documentation.

**5. Does Checkstyle prove that the guard `when query != null && !query.isBlank()` is business-correct?**  
No. It can check certain style tokens, but verifying output and null handling still requires tests.

**6. When using Checkstyle 14.x, which JDK runs the analyzer?**  
Minimum JDK 21 per Checkstyle 14.x compatibility information. Do not confuse the JDK running the analyzer with the `--release` of the source code.

**7. Why should you pin the Checkstyle dependency when using the Maven plugin?**  
Because the plugin and the analyzer library have separate versions; the bundled version may be too old to understand Java 21 syntax or checks.

**8. Should you enable `WhenShouldBeUsed` and automatically convert every `if` in a case into `when`?**  
No. You need to inspect all branches, fallbacks, and case ordering; changing it can affect which branch is selected.

**9. If `javac` reports a dominated branch while Checkstyle has not run yet, which tool's issue should be fixed first?**  
Fix the syntax/semantics checked by the compiler first, then run Checkstyle and tests.

**10. If a pattern is long yet still under 100 characters per line, are the conventions already satisfied?**  
Not necessarily. Line length does not measure cognitive complexity; a domain method or shallower type pattern may be needed.

## Conclusion

**Checkstyle helps keep pattern-matching conventions consistent, but it does not replace the compiler and tests.** For Java 21, start with `PatternVariableName`, `PatternVariableAssignment`, and a sensible whitespace/line-length set; understand the exact scope of `MissingSwitchDefault` and treat `WhenShouldBeUsed` as an optional policy. Pin an analyzer version compatible with the Java syntax in use and integrate it into the build so everyone gets the same results.

The goal is not to make every pattern as short as possible, but to achieve **clear naming, readable structure, safe null/guard handling, and intentional handling of switch variants**.

## Official References

- [Checkstyle — PatternVariableName](https://checkstyle.org/checks/naming/patternvariablename.html)
- [Checkstyle — PatternVariableAssignment](https://checkstyle.org/checks/coding/patternvariableassignment.html)
- [Checkstyle — LocalVariableName](https://checkstyle.org/checks/naming/localvariablename.html)
- [Checkstyle — WhitespaceAround](https://checkstyle.org/checks/whitespace/whitespacearound.html)
- [Checkstyle — LineLength](https://checkstyle.org/checks/sizes/linelength.html)
- [Checkstyle — MissingSwitchDefault](https://checkstyle.org/checks/coding/missingswitchdefault.html)
- [Checkstyle — WhenShouldBeUsed](https://checkstyle.org/checks/coding/whenshouldbeused.html)
- [Checkstyle — Versions and JDK Requirements](https://checkstyle.org/index.html)
- [Gradle — The Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Apache Maven — Maven Checkstyle Plugin](https://maven.apache.org/plugins/maven-checkstyle-plugin/)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
