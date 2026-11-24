# JUnit Jupiter: `@MethodSource`, `@CsvSource`, and `@CsvFileSource`

## Objectives

In Spring Boot, many rules must be verified across **multiple input datasets**: minimum/maximum values, true–false branches, and valid/invalid data. Instead of duplicating the same test body, JUnit Jupiter supports **parameterized tests**: writing one test method and executing it multiple times, receiving a different parameter set each time.

After this lesson, you will be able to:

- Use `@ParameterizedTest` with `@MethodSource`, `@CsvSource`, and `@CsvFileSource`.
- Choose the appropriate data source: generated in Java, declared concisely inside the annotation, or managed separately in a CSV file.
- Use `Stream<Arguments>` for multiple parameters and `Stream<T>` for a single parameter; understand `static` rules for factory methods.
- Handle data types, commas inside strings, empty cells, `null`, headers, and resource paths.
- Create a Java 17/JUnit Jupiter example runnable with Gradle, verify exact test invocation counts, and handle common errors.

This lesson covers **JUnit Jupiter 5 parameter sources**, not a full Spring Boot system testing guide or using CSV in production.

## 1. Principle of parameterized tests

With `@Test`, each method is a single independent test case. With `@ParameterizedTest`, **the same method body is invoked multiple times**. JUnit fetches datasets from the source annotation, converts values to the method's parameter types when needed, and runs assertions for each invocation.

~~~text
@ParameterizedTest
       |
       +-- @MethodSource("cases")        -> data from a Java method
       |
       +-- @CsvSource({...})             -> CSV data written in the annotation
       |
       +-- @CsvFileSource(resources=...) -> CSV data in a resource file
       |
       v
Each row/Arguments set -> one invocation -> run test body -> separate result
~~~

For example, a calculation with four rows of data will be executed four times by JUnit, not as "a single test checking four rows inside a loop". This lets the report pinpoint **which input set failed**; including parameter values in display names makes diagnosis even easier.

These three annotations belong to `org.junit.jupiter.params.provider`, while `@ParameterizedTest` belongs to `org.junit.jupiter.params`. To use them, the test classpath needs the **`junit-jupiter-params`** module along with the Jupiter engine to execute them.

### Quick comparison table

| Source | Where is the data? | When is it a good fit? | Limitations to remember |
| --- | --- | --- | --- |
| `@MethodSource` | A Java factory method, returning `Stream`, `Iterable`, array, etc. | Complex objects, `null`, code-generated data, test cases with varied parameter types | Methods in the same test class must normally be `static`; multiple parameters should be wrapped in `Arguments`. |
| `@CsvSource` | CSV lines declared directly in the annotation | Small data tables, basic-type columns, easy to read next to assertions | Large datasets become hard to read; must remember quoting and `null` rules. |
| `@CsvFileSource` | CSV file on classpath or file path | Long test case tables provided by testers/business, meant to be reviewed like documentation | File must be packaged/read properly; headers and CSV format must match the test signature. |

Choose the source based on the **nature of the dataset**, not solely row count. External data should be version-controlled alongside code; expected value calculations must remain independent of the algorithm under test.

## 2. Setting up a Java 17 project with JUnit Jupiter

You can experiment standalone without booting Spring Boot. In a minimal Gradle Groovy DSL project, the structure looks like this (Wrapper scripts are generated or already present at the root):

~~~text
junit-params-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/RewardPointsCalculator.java
    └── test/
        ├── java/com/example/testing/RewardPointsCalculatorTest.java
        └── resources/cases/reward-points.csv
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'junit-params-demo'
~~~

**`build.gradle`** — example using JUnit 5.10.2/compatible BOM so the code runs standalone. In a real Spring Boot project, prefer dependency versions managed by the project's Spring Boot/BOM.

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`org.junit.jupiter:junit-jupiter` is an aggregator artifact including Jupiter API, params, and engine in the JUnit 5.10.2 lineup. `useJUnitPlatform()` tells Gradle to run tests on JUnit Platform; the launcher provides the appropriate runtime component. The Java toolchain requires an available JDK 17 or configured provisioning.

In a Spring Boot project that **already has the plugin and BOM/dependency management**, the corresponding common configuration is:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` typically brings in JUnit Jupiter, including params; do not declare duplicate conflicting JUnit versions. If using a different Spring Boot release, let its version management determine compatible dependencies. **Do not copy both `dependencies` blocks into the same project**: choose one approach based on your project type.

## 3. Business rule to test

Suppose a system awards loyalty points based on purchase amount:

- Every **100 currency units** earns **1 base point**, using integer division. For example, purchasing 299 earns 2 points.
- `premium` customers receive **double** the base points.
- Purchases under 100 earn 0 points.
- Negative values are rejected with `IllegalArgumentException`.

Implement the rule in **`src/main/java/com/example/testing/RewardPointsCalculator.java`**:

~~~java
package com.example.testing;

public final class RewardPointsCalculator {

    public int pointsFor(int purchaseAmount, boolean premium) {
        if (purchaseAmount < 0) {
            throw new IllegalArgumentException(
                    "purchaseAmount must be non-negative");
        }

        int basePoints = purchaseAmount / 100;
        return premium ? basePoints * 2 : basePoints;
    }
}
~~~

Because the exercise uses `int` in hypothetical units to focus on testing techniques, do not infer production currency-handling design from this example. Expected numbers are derived manually from the rule above, without calling `pointsFor` itself to compute expected values.

## 4. Complete example using all three sources

Create **`src/test/java/com/example/testing/RewardPointsCalculatorTest.java`**:

~~~java
package com.example.testing;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.CsvFileSource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.MethodSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.params.provider.Arguments.arguments;

class RewardPointsCalculatorTest {

    private final RewardPointsCalculator calculator =
            new RewardPointsCalculator();

    record Purchase(int amount, boolean premium) {}

    // 1) @MethodSource: Java object combined with expected value.
    @ParameterizedTest(name = "method {index}: {0} -> {1} points")
    @MethodSource("structuredCases")
    void calculatesFromMethodSource(Purchase purchase, int expected) {
        int actual = calculator.pointsFor(
                purchase.amount(), purchase.premium());

        assertEquals(expected, actual);
    }

    static Stream<Arguments> structuredCases() {
        return Stream.of(
                arguments(new Purchase(0, false), 0),
                arguments(new Purchase(99, true), 0),
                arguments(new Purchase(100, false), 1),
                arguments(new Purchase(100, true), 2),
                arguments(new Purchase(250, true), 4)
        );
    }

    // With one parameter, returning Stream<Integer> is possible.
    @ParameterizedTest(name = "invalid purchase {0} is rejected")
    @MethodSource("invalidAmounts")
    void rejectsNegativeAmounts(int amount) {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.pointsFor(amount, false));
    }

    static Stream<Integer> invalidAmounts() {
        return Stream.of(-1, -100);
    }

    // 2) @CsvSource: small table right next to the test code.
    @ParameterizedTest(
            name = "inline CSV {index}: amount={0}, premium={1}, points={2}")
    @CsvSource({
        "199, false, 1",
        "199, true, 2",
        "500, false, 5",
        "500, true, 10",
        "550, true, 10"
    })
    void calculatesFromInlineCsv(int amount, boolean premium, int expected) {
        int actual = calculator.pointsFor(amount, premium);

        assertEquals(expected, actual);
    }

    // 3) @CsvFileSource: data stored in a resources file.
    @ParameterizedTest(
            name = "file CSV {index}: amount={0}, premium={1}, points={2}")
    @CsvFileSource(
            resources = "/cases/reward-points.csv",
            numLinesToSkip = 1)
    void calculatesFromCsvFile(int amount, boolean premium, int expected) {
        int actual = calculator.pointsFor(amount, premium);

        assertEquals(expected, actual);
    }
}
~~~

None of these methods need `@Test`: **`@ParameterizedTest` marks them as parameterized tests on its own**. In the same class, `structuredCases` and `invalidAmounts` are **factory methods** providing data; they are not tests and do not carry `@Test`. The Java `record Purchase` (available since Java 16, works cleanly in Java 17) keeps the two input fields concise and provides a handy `toString()` for display names.

### Placing the CSV file in the right location

Create **`src/test/resources/cases/reward-points.csv`** with the exact content:

~~~csv
amount,premium,expected
1,false,0
99,false,0
100,false,1
101,true,2
299,true,4
300,false,3
999,true,18
1000,false,10
~~~

Because `resources = "/cases/reward-points.csv"` references a **path on the test classpath**, Gradle copies files from `src/test/resources` onto the test runtime classpath by default. The leading `/` indicates the classpath root, not the Windows/Linux filesystem root. If you save the file in a different folder, update the path to match. `numLinesToSkip = 1` skips the header row so JUnit does not try to convert the string `amount` to an `int`.

**Cross-checking several rows in the CSV:**

| Input | Expected | Why |
| --- | --- | --- |
| `1,false` | `0` | Integer division of 1 by 100 is 0. |
| `101,true` | `2` | Base 1 point, doubled for premium. |
| `299,true` | `4` | Integer division of 299 by 100 is 2, times 2 equals 4. |
| `999,true` | `18` | Base 9 points, times 2 equals 18. |
| `1000,false` | `10` | Base 10 points, non-premium is not doubled. |

All sample code in sections 2–4 forms **a runnable project**. Run from the root containing the Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If the project does not yet have a Wrapper, you can generate one from a valid installed Gradle via `gradle wrapper --gradle-version <compatible-version>` and commit the Wrapper files; choose a version compatible with your Java version and plugins. In an existing Spring Boot project, use the Wrapper already provided by the repository.

With the **exact datasets listed**, the executions are:

| Test method | Number of datasets | Invocations |
| --- | ---: | ---: |
| `calculatesFromMethodSource` | 5 | 5 |
| `rejectsNegativeAmounts` | 2 | 2 |
| `calculatesFromInlineCsv` | 5 | 5 |
| `calculatesFromCsvFile` | 8 rows after header | 8 |
| **Total** | **20** | **20** |

All should pass with the sample code. There is no `System.out.println`, so the tests **produce no business stdout**. Gradle normally prints `BUILD SUCCESSFUL` when the task succeeds; view exact test counts in `build/reports/tests/test/index.html` or XML under `build/test-results/test/`. If the task is marked `UP-TO-DATE`/`FROM-CACHE`, cached results may be reused; to force re-execution for diagnostics, run `./gradlew test --rerun-tasks`.

## 5. `@MethodSource`: Java factory methods

`@MethodSource` reads data from a **factory method** that can be named explicitly:

~~~java
@ParameterizedTest
@MethodSource("caseProvider")
void testSomething(int value, String label) {
    // ...assertions...
}

static Stream<Arguments> caseProvider() {
    return Stream.of(
            arguments(1, "one"),
            arguments(2, "two")
    );
}
~~~

This snippet **only illustrates syntax**, not a standalone program. Each `Arguments` set holds **two arguments in the exact order** received by the test: `int`, then `String`. If the factory returns a `Stream<Integer>`, the corresponding test has only one parameter (like `invalidAmounts` in the runnable example).

### Important rules

1. **Naming:** `@MethodSource("structuredCases")` looks for the `structuredCases` factory. If you omit the name in the annotation, JUnit uses the test method's name as the factory name and may require declaring a factory with that same name (typically an overload taking no parameters). Specifying the name explicitly improves readability.
2. **`static`:** factories inside the test class must be `static` by default. The exception is when the test class uses `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, where instance factory methods can be declared. Factories in another class must be `static`.
3. **Return value:** Jupiter accepts several source types such as `Stream`, `Iterable`, `Iterator`, arrays, or primitive stream types; `Stream<Arguments>` is the common choice for multiple parameters. Each element must match the test's parameter count and types.
4. **Complex objects:** `Arguments.of(...)` can hold objects, records, enums, collections, and `null`; cases needing complex object setup usually fit better here than in plain-text CSV.
5. **Independent data:** factories should produce deterministic data without depending on test order, clocks, networks, or shared databases. JUnit may invoke factories during discovery and execution; avoid side effects inside providers.

You can reference a provider in another class using a fully qualified name with `#`, for example `@MethodSource("com.example.testing.CommonCases#validInputs")`, with a `static` method and appropriate visibility. This is helpful when multiple tests share a case set, though you should avoid creating a hard-to-trace "central dumping ground of cases".

**When to prefer it?** When data involves rich objects, expected exceptions, multi-branch scenarios, objects that cannot be represented cleanly in CSV, or when code is needed to deterministically generate boundary values. Do not write a provider loop that computes expected values using the SUT's own algorithm: if both share the same bug, the test may still pass.

## 6. `@CsvSource`: small inline tables

`@CsvSource` treats each string in `value = {...}` as a CSV row. JUnit converts columns to test parameters in order. When you declare:

~~~java
@CsvSource({
    "500, false, 5",
    "500, true, 10"
})
~~~

the row `"500, true, 10"` is **a single Java string** containing three CSV columns, sequentially converted into `int=500`, `boolean=true`, and `int=10` for the example method. These are not three separate Java array elements.

### Delimiter, quote, and whitespace rules

By default, `@CsvSource` uses a **comma** as the delimiter and a **single quote `'`** as the quote character. If a string value contains a comma, you must quote it according to `@CsvSource`'s CSV rules:

~~~java
@ParameterizedTest
@CsvSource({
    "'North, Vietnam', 1",
    "'', 0"
})
void exampleCsvStrings(String region, int expectedFlag) {
    // Standalone example: receives "North, Vietnam" then receives an empty string "".
}
~~~

The snippet above only illustrates passing values and contains no assertions, so it is **not a complete test yet**. You can change the delimiter, for example `@CsvSource(value = {"100; true; 2"}, delimiter = ';')`; then `;` acts as the separator. Do not configure `delimiter` and `delimiterString` simultaneously.

| Written in `@CsvSource` | Value received if the parameter is `String` |
| --- | --- |
| `"red, blue"` (two columns, unquoted) | `"red"` and `"blue"` |
| `"'red, blue', 1"` | First column is `"red, blue"`; second is `"1"` before conversion to `int` |
| `"name, ''"` | Second column is empty string `""` |
| `"name, "` | Second column is `null` (no value) |
| `"name, NIL"` with `nullValues = "NIL"` | Second column is `null` |

**`''` differs from an unquoted empty cell:** empty string `""` and `null` can trigger different assertions/validation paths. A `null` column cannot be converted to primitive parameters `int`, `boolean`; use wrapper types like `Integer` if intentionally testing `null`. With `@CsvSource`, leading/trailing whitespace in unquoted columns is typically trimmed; data with meaningful whitespace must be quoted or have settings adjusted. If multiple lines are needed in Java 17, `@CsvSource(textBlock = """...""")` is an option, following proper Java text block rules and line/comment handling per current JUnit documentation.

**When to prefer it?** When there are a few rows of numbers or short strings, such as testing boundary numbers, account types, and their corresponding expected results. Keeping the test next to its dataset lets reviewers see all examples without opening another file.

## 7. `@CsvFileSource`: data tables stored in files

With `@CsvFileSource(resources = "/cases/reward-points.csv", numLinesToSkip = 1)`, each **record** in the file after the header is processed into a parameter set. This works well when there are many rows or when data is reviewed by QA/domain experts.

### Resource loading mechanism

- `resources = "/cases/reward-points.csv"` reads a resource on the **test classpath**, with the path starting with `/` to resolve from the classpath root.
- In standard Java/Gradle layouts, place the file in `src/test/resources/cases/reward-points.csv`. If using custom source sets, ensure resources are included on the test task's runtime classpath.
- `numLinesToSkip = 1` skips the first header line. If not skipped and the first row is `amount,premium,expected`, JUnit will try to convert `amount` to `int` and fail during argument conversion.
- Multiple resources can be specified via `resources = {"/cases/a.csv", "/cases/b.csv"}`; ensure the files share the same schema.
- `@CsvFileSource` also supports filesystem paths via the `files` attribute, but resources under `src/test/resources` package, share, and run more reliably on CI than paths depending on the working directory.

### CSV files use double quotes by default

Unlike `@CsvSource`, `@CsvFileSource` **uses double quotes `"` by default** to quote strings containing commas:

~~~csv
region,level
"North, Vietnam",1
"South, Vietnam",2
~~~

If an author uses single quotes `'North, Vietnam'` in the file without changing `quoteCharacter`, the inner comma may be treated as a column separator, causing a parameter count mismatch.

The **empty data** rules are similar in meaning but differ in quote character:

| In CSV file | Default meaning |
| --- | --- |
| `""` (quoted with double quotes) | Empty string `""` |
| An empty column between two commas | `null` |
| `NIL` with `nullValues = "NIL"` | `null` |
| `"North, Vietnam"` | One column containing the comma |

A CSV file may contain comment lines starting with `#`, which JUnit skips. Do not abuse comments to alter column semantics. When data contains special characters, save the file in UTF-8 and keep quote/delimiter rules aligned with the annotation.

### Managing file data responsibly

A CSV file should not become an incomprehensible "pile of golden data". Test authors must know which rule each row protects; column names, commit diffs, and boundary explanations should stay clear. Use synthetic data, and never commit personal information or real credentials to the repository. Files should be reviewed alongside code because altering **expected** values can also mask bugs. If scenarios require different structures, consider splitting files per contract or choosing `@MethodSource` with case objects.

## 8. Choosing a source based on real situations

| What do you have? | Preferred choice | Reason |
| --- | --- | --- |
| 3–10 pairs of numbers and expected values | `@CsvSource` | Concise, quick to read beside the test |
| 50 input/expected rows reviewed by QA | `@CsvFileSource` | Separates data, easy to review CSV rows and use in CI |
| Inputs with records, enums, objects, exception types | `@MethodSource` | Factory creates strongly typed objects |
| Single `String` parameter with `null`, empty, blank | `@NullSource`/`@EmptySource`/`@ValueSource` or `@MethodSource` | Simpler than forcing into CSV |
| Test suite with rule-generated deterministic data | `@MethodSource` | Can construct cases in Java while remaining easy to verify |
| Data with commas, newlines, or complex quotes | `@MethodSource` or properly escaped CSV | Reduces risk of parser altering values |

Having many rows does not automatically require switching to a CSV file. If expectations involve complex business structures, a `record` with descriptive field names helps prevent misreading columns much better than a 12-column file of primitive values.

## 9. Invocation names and running the right tests

Display names in the examples use `name = "...{index}...{0}..."`:

- `{index}` is the execution index provided by Jupiter.
- `{0}`, `{1}`, … are the display strings of each argument.
- Names showing inputs and expected values help quickly locate failing rows in IDEs, HTML reports, and CI.

For example, the case `199, true, 2` will appear as **`inline CSV 2: amount=199, premium=true, points=2`** if it is the second row of `@CsvSource`. Labels may be formatted differently by formatters/IDEs; the **assertion results and invocation count** are what provide verification.

Run the entire class in a Gradle project:

~~~bash
./gradlew test --tests 'com.example.testing.RewardPointsCalculatorTest'
~~~

Run a single parameterized method:

~~~bash
./gradlew test --tests 'com.example.testing.RewardPointsCalculatorTest.calculatesFromInlineCsv'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests 'com.example.testing.RewardPointsCalculatorTest'
~~~

`--tests` selects a method by name, and one parameterized method can still produce **multiple invocations**. Do not expect `--tests <method>` to run only one CSV row. In some Gradle/JUnit versions, filtering down to a single invocation by display name has limitations and varies; for diagnosis, it is usually easier to select the method and inspect the index/arguments in the report.

When you need more configuration/discovery logs, use `./gradlew test --info` or `--stacktrace`. Standard report files appear under `build/reports/tests/test/` and `build/test-results/test/` of the executed Gradle module. For multi-project builds, you may need a task path like `:orders:test` if that is the actual project path.

## 10. Common errors and how to resolve them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| JUnit does not recognize `@ParameterizedTest` | Missing `junit-jupiter-params`, engine, or `useJUnitPlatform()` | Check test dependencies, Gradle task, and imports |
| Error reporting method source not found | Typo in `@MethodSource` or referenced package/class | Match the factory name; specify the name explicitly |
| Factory method must be static | Instance factory under default lifecycle | Make it `static`, or configure `@TestInstance(PER_CLASS)` when genuinely needed |
| Parameter count mismatch | `Arguments`/CSV has missing or extra columns | Inspect each row and the method signature |
| `ArgumentConversionException` | String cannot convert to `int`/`boolean`/enum, or `null` passed to primitive | Fix data, parameter type, or use an explicit converter |
| Content containing commas split wrongly | Wrong CSV quote character for that annotation | `@CsvSource` defaults to `'`; `@CsvFileSource` defaults to `"` |
| Header `amount` forced into `int` | Forgot to skip the header line in CSV file | Use `numLinesToSkip = 1` or appropriate header settings |
| `Cannot find resource` | Wrong path, wrong `src/test/resources` source, or not packaged | Check classpath and leading `/` on resource path |
| CSV file works locally but fails on CI | Machine-specific path, encoding, or uncommitted data | Use repo-tracked resources and consistent encoding |
| Test always passes even when logic is broken | Expected values generated by the SUT itself, or weak assertions | Write expected values independently from specs; inject intentional bugs to check |
| Flaky test | Provider uses random/time/network/shared state | Fix seeds/data, control dependencies, and build independent cases |
| Huge table makes reports hard to read | Redundant rows, meaningless cases | Group by requirement, set clear invocation names, drop unnecessary duplicates |

### Four easy-to-confuse points to remember

**(1) `@Test` differs from `@ParameterizedTest`:** Methods receiving arguments from a source must carry `@ParameterizedTest`. If only `@Test` is used, JUnit will not bind `@CsvSource` data to test parameters.

**(2) One method is not one invocation:** With five rows, the test runs five times. To check pass/fail per case, inspect reports by invocation or display name.

**(3) `null` is not the same as `""`:** An unquoted empty CSV cell normally maps to `null`; a quoted empty string remains a non-`null` value. For primitives, JUnit cannot pass `null`.

**(4) A provider is not an oracle:** Factories supply inputs and expected values, but expected values must derive **from business specifications**; do not repeat SUT logic to validate itself.

## 11. Practice exercises

**Exercise A — `@CsvSource`:** Add cases for `purchaseAmount = 99, 100, 199, 200` with `premium=false`. Write expected values independently before running. For each row, verify the exact step changes at multiples of 100.

**Exercise B — `@MethodSource`:** Extend `Stream<Arguments>` to accept a `Purchase` object and an `expected` value for `premium=true` at thresholds 100, 200, 300. Add a `Stream<Integer>` for large negative values; use `assertThrows`.

**Exercise C — `@CsvFileSource`:** Add two rows to `reward-points.csv` for `purchaseAmount = 1099, premium=true` and `purchaseAmount = 1999, premium=false`. Expected values are `20` and `19` respectively. Verify that the total invocation count increases from **20 to 22** without changing the test body.

**Exercise D — bug detection:** Temporarily change `purchaseAmount / 100` to `purchaseAmount / 200` locally; cases with non-zero expected points must fail. Revert the change and rerun. This confirms the tests verify the real rule, not just that JUnit loaded the CSV file.

**Remember:** `@MethodSource` is the most flexible for Java objects/data, `@CsvSource` keeps small tables readable right beside the test, and `@CsvFileSource` suits separately managed data tables. Whichever source you choose, match column counts and types accurately, clarify `null`/quoting rules, and keep expected values independent so every invocation provides real verification.
