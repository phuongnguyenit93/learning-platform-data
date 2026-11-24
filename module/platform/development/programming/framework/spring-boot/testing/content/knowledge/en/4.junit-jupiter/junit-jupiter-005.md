# @ParameterizedTest with Simple Data Sources in JUnit Jupiter

When the same rule must be tested with multiple input values, writing separate `@Test` methods can lead to duplicated code: object creation, method calls, and assertions look nearly identical, differing only in data. **JUnit Jupiter's `@ParameterizedTest`** lets you declare **a single test method** and run it **multiple times (invocations)**, each time with an argument set supplied by a data source.

This lesson focuses on readable and commonly used data sources: **`@ValueSource`, `@NullSource`, `@EmptySource`, `@NullAndEmptySource`, `@CsvSource`, and `@EnumSource`**. The goal is to know how to choose the right source, test boundary data, write meaningful assertions, run tests in a Spring Boot project, and recognize when to move to more complex sources.

## 1. Mechanism of a parameterized test

A regular test:

```java
@Test
void acceptsAmy() {
    assertTrue(policy.isValid("amy"));
}
```

If we add the names `bob_42` and `abc123456789` with the same expected rule, we can write:

```java
@ParameterizedTest
@ValueSource(strings = {"amy", "bob_42", "abc123456789"})
void acceptsValidUsernames(String username) {
    assertTrue(policy.isValid(username));
}
```

JUnit Jupiter takes each value in turn from `@ValueSource` and passes it into the `username` parameter. These are **3 separate executions** of the same method; each invocation has its own pass/fail result in the test report. When one invocation fails, the offending data should be clearly visible so the right case can be fixed.

Basic structure:

```text
@ParameterizedTest + data source
              |
              v
     Generate argument sets
              |
      +-------+-------+
      |       |       |
    case 1  case 2  case 3
      |       |       |
      +--- execution --+
              |
      assertion per run
```

Three key components:

1. **`@ParameterizedTest`** marks the method to run multiple times. Do not also put `@Test` on the same method.
2. **Argument source** produces the values: one value per invocation from `@ValueSource`, multiple values per invocation from `@CsvSource`, etc.
3. **Method parameters and assertions** receive the data, execute the **real** behavior under test, and compare results. A parameterized test is useless if it only asserts on the source data itself without calling the SUT.

**Design mindset example:** "Every valid username is accepted" is one behavior that can run with many names. "Valid usernames are accepted" and "Invalid usernames are rejected" have different expectations; you can split them into two test methods for clear messages and assertions, or use `@CsvSource` if the same call and expected value are supplied row by row.

## 2. Preparing JUnit Jupiter in a Spring Boot project

In a Spring Boot project using Gradle, you typically use Spring Boot's test dependency starter. The relevant configuration section in `build.gradle` (Groovy DSL) looks like:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **configuration snippet added** to a project that already declares Spring Boot/Gradle plugins and dependency version management; it is not a standalone build file. Spring Boot's standard test starter includes the required JUnit Jupiter libraries in standard setups, including support for parameterized tests. For Java projects **not using** the Spring Boot starter, ensure `junit-jupiter-params` along with compatible JUnit Jupiter engine/API versions are on the test classpath.

Common imports:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.EmptySource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;
```

Note: the source annotations live in `org.junit.jupiter.params.provider`, whereas `@Test` lives in `org.junit.jupiter.api`. They operate on **JUnit Platform/Jupiter** and do not require starting a Spring application context when testing plain Java logic.

Standard file locations:

```text
src/
├── main/java/example/testing/UsernamePolicy.java
└── test/java/example/testing/UsernamePolicyTest.java
```

JUnit and Gradle require standard Java or Spring Boot source/test directory configuration.

## 3. Quick selection table for simple data sources

| Annotation | Produces arguments | Best suited when | Key things to remember |
| --- | --- | --- | --- |
| `@ValueSource` | **One** literal value per invocation | Lists of strings, numbers, booleans, chars, etc. sharing one expectation | Single test parameter; cannot directly supply `null` |
| `@NullSource` | One invocation containing `null` | Catching missing-input handling bugs | Cannot pass `null` to primitive parameters like `int` |
| `@EmptySource` | One invocation with a parameter-type-compatible empty value | Testing `""` or empty collections/arrays | Empty is different from `null` and whitespace-only strings |
| `@NullAndEmptySource` | Combines null and empty cases | String/collection APIs checking for missing/empty values | Can be combined with `@ValueSource` for whitespace |
| `@CsvSource` | Each row has **multiple columns/arguments** | Input → expected output tables or multiple parameters | Requires understanding delimiters, quotes, type conversion, and blank cells |
| `@EnumSource` | Selected enum constants | Statuses, command types, operating modes | Can include specific names or exclude names |

Quick selection rule: **single argument → `@ValueSource`; null/empty → corresponding source; multiple arguments per row → `@CsvSource`; enum states → `@EnumSource`**. When data must be generated dynamically, consists of complex objects, needs reuse across places, or is too long to write inline in an annotation, consider `@MethodSource` or a dedicated source. There is no need to reach for those heavier tools for the simple cases in this lesson.

## 4. Runnable example: testing usernames and edit status

Let's agree on the business contract before writing tests:

- Valid usernames have **3–12 characters**, starting with a lowercase ASCII letter `a–z`; remaining characters may only be lowercase ASCII letters, digits, or underscore `_`.
- `null`, empty strings, whitespace-only strings, invalid characters, or invalid lengths are all invalid.
- The helper that strips whitespace from **both ends** returns the remaining text; it **does not convert uppercase to lowercase**.
- A record can only be edited when in `DRAFT` status.

The policy and tests are kept small to stay focused on JUnit parameterization.

### 4.1. Production class

Create `src/main/java/example/testing/UsernamePolicy.java`:

```java
package example.testing;

public final class UsernamePolicy {

    public boolean isValid(String username) {
        return username != null
                && username.matches("[a-z][a-z0-9_]{2,11}");
    }

    public String stripOuterWhitespace(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return input.strip();
    }

    public boolean canEdit(Status status) {
        return status == Status.DRAFT;
    }

    public enum Status {
        DRAFT,
        SUBMITTED,
        APPROVED,
        REJECTED
    }
}
```

Explanation:

- The regex `[a-z][a-z0-9_]{2,11}` requires **one** leading lowercase letter, followed by **2–11** allowed characters: 3–12 in total. `String.matches(...)` matches the entire string.
- Checking `username != null` before the regular expression avoids a `NullPointerException` when `null` is passed.
- `String.strip()` (Java 11+) removes whitespace as defined by Java Unicode at both ends without altering the middle.
- `canEdit` illustrates sharing the same `false` expectation across multiple enum states.

This is plain Java; no `@Service` or `@SpringBootTest` is needed. In a real Spring Boot application, logic like this may be called from a service/controller without changing how its rules are unit-tested.

### 4.2. Complete test suite with data sources

Create `src/test/java/example/testing/UsernamePolicyTest.java`:

```java
package example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UsernamePolicyTest {

    private final UsernamePolicy policy = new UsernamePolicy();

    @ParameterizedTest(name = "[{index}] valid username: {0}")
    @ValueSource(strings = {"amy", "bob_42", "abc123456789"})
    void acceptsValidUsernames(String username) {
        assertTrue(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] invalid format: {0}")
    @ValueSource(strings = {
            "ab", "Tom", "9tom", "tom-adam", "abc1234567890"
    })
    void rejectsInvalidFormats(String username) {
        assertFalse(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] missing or blank: {0}")
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t"})
    void rejectsMissingOrBlankUsernames(String username) {
        assertFalse(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] strip [{0}] -> [{1}]")
    @CsvSource({
            "'  amy  ',amy",
            "' bob_42 ',bob_42",
            "'  TOM ',TOM"
    })
    void stripsOuterWhitespace(String input, String expected) {
        assertEquals(expected, policy.stripOuterWhitespace(input));
    }

    @ParameterizedTest(name = "[{index}] cannot edit: {0}")
    @EnumSource(
            value = UsernamePolicy.Status.class,
            names = {"SUBMITTED", "APPROVED", "REJECTED"}
    )
    void cannotEditNonDraftStatus(UsernamePolicy.Status status) {
        assertFalse(policy.canEdit(status));
    }

    @Test
    void canEditDraft() {
        assertTrue(policy.canEdit(UsernamePolicy.Status.DRAFT));
    }
}
```

The **expected total number of executions** for the file above is **19** (assuming tests are discovered by the runner and configured properly), counted from the sources:

| Test method | Source | Invocation count |
| --- | --- | ---: |
| `acceptsValidUsernames` | Three strings in `@ValueSource` | 3 |
| `rejectsInvalidFormats` | Five strings in `@ValueSource` | 5 |
| `rejectsMissingOrBlankUsernames` | Null + empty + two whitespace strings | 4 |
| `stripsOuterWhitespace` | Three rows in `@CsvSource` | 3 |
| `cannotEditNonDraftStatus` | Three enum values | 3 |
| `canEditDraft` | One regular `@Test` | 1 |
| **Total** | | **19** |

These are **19 invocations**, not 19 declared methods. Each case has its own input, and failures of an invocation can be displayed by JUnit tied to that specific value; reporting style and whether execution continues after failure depend on the runner/configuration.

Run from the Gradle project directory:

```bash
./gradlew test --tests example.testing.UsernamePolicyTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.UsernamePolicyTest"
```

**Expectation:** all cases above pass on Java 17+ in a project with the proper JUnit Jupiter Params dependency. There is no fixed stdout string for the test command because Gradle/JUnit and logging settings can format output differently. If a test turns red, the report identifies the failing invocation and assertion so you can cross-reference the source data.

### 4.3. Running plain Java logic without JUnit

To see the production class run standalone, create `src/main/java/example/testing/UsernamePolicyDemo.java`:

```java
package example.testing;

public class UsernamePolicyDemo {
    public static void main(String[] args) {
        UsernamePolicy policy = new UsernamePolicy();

        System.out.println(policy.isValid("amy"));
        System.out.println(policy.isValid("Tom"));
        System.out.println(
                policy.stripOuterWhitespace("  bob_42  "));
        System.out.println(
                policy.canEdit(UsernamePolicy.Status.DRAFT));
    }
}
```

Compile/run commands from the project root directory:

```bash
javac -d out src/main/java/example/testing/UsernamePolicy.java src/main/java/example/testing/UsernamePolicyDemo.java
java -cp out example.testing.UsernamePolicyDemo
```

Exact stdout of `main`:

```text
true
false
bob_42
true
```

The `javac` command here proves the two plain Java files work with the JDK without Spring or JUnit; by itself it **does not run parameterized tests**. Running tests requires the JUnit engine and test dependencies via Gradle or an equivalent test runner.

## 5. Deep dive into each data source

### 5.1. `@ValueSource`: a list of one value per invocation

`@ValueSource` fits best when a test accepts **one parameter** and applies the same verification logic. Besides `strings`, common forms include `ints`, `longs`, `doubles`, `booleans`, `chars`, and `classes`; JUnit also supports other primitive types as listed in the API. Declare the single source attribute matching your test case.

Example testing an integer helper (this is an **illustrative test method snippet**, assuming `isEven(int)` already exists in the SUT):

```java
@ParameterizedTest
@ValueSource(ints = {0, 2, 4, 100})
void acceptsEvenNumbers(int value) {
    assertTrue(numberPolicy.isEven(value));
}
```

JUnit passes each number into `value` one by one. Avoid writing four tests with the same assertion just to swap numbers.

**Limitations:** `@ValueSource` is not a multi-column table. Do not write `@ValueSource(strings = {"amy", "false"})` expecting JUnit to form a `(String, boolean)` pair. If you want a test method with two parameters `username` and `expected`, choose `@CsvSource` or an appropriate source producing `Arguments`.

`@ValueSource` also cannot express `null`; use `@NullSource`, `@NullAndEmptySource`, or another source when a null case is needed.

### 5.2. `@NullSource`, `@EmptySource`, and `@NullAndEmptySource`

Three cases to distinguish on a `String` parameter:

| Input | Value | Meaning |
| --- | --- | --- |
| `null` | No String object | Not a zero-length string |
| `""` | String with `length() == 0` | Empty string |
| `" "` or `"\t"` | String **containing whitespace characters** | Not empty; may be considered blank per business rules |

`@NullSource` creates **one** invocation with `null`. `@EmptySource` creates one invocation with a parameter-type-compatible empty value, such as an empty `String`; it also works with several compatible collection/array types. `@NullAndEmptySource` combines both for supported types.

Simple example:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "\t"})
void rejectsBlankInput(String input) {
    assertFalse(policy.isValid(input));
}
```

Here JUnit creates **4 invocations**: `null`, `""`, one space, and one tab character. If the policy only checks `isEmpty()` and ignores blank strings, tests with whitespace will expose the gap.

**Do not pass `null` to primitive parameters** such as `int`, `long`, or `boolean`. Java primitives cannot hold null; the test will fail during argument conversion before checking business logic. If null genuinely needs to be represented, use wrappers `Integer`/`Long`/`Boolean` or an appropriate reference type.

Note what happens when a method declares multiple source annotations: each annotation contributes its own invocations under JUnit's mechanism; **they are not combined as a Cartesian product**. `@NullAndEmptySource` plus `@ValueSource(strings = {" "})` creates three independent invocations, not pairs of data.

### 5.3. `@CsvSource`: multiple arguments per row

One CSV line represents one case; each column corresponds to a parameter in the test method. This is a natural choice for **input → expected** tables:

```java
@ParameterizedTest(name = "[{index}] {0} => {1}")
@CsvSource({
        "amy,true",
        "Tom,false",
        "abc123456789,true",
        "abc1234567890,false"
})
void validatesExpectedResult(String username, boolean expected) {
    assertEquals(expected, policy.isValid(username));
}
```

This is an **addition inside the `UsernamePolicyTest` class** using existing imports; it will run 4 more invocations if added to the complete file in section 4.2. JUnit can convert simple CSV values such as `"true"` and `"false"` into `boolean` parameters; numeric strings can convert into `int`, `long`, and other built-in types. When data cannot be converted to the parameter type, the error happens during argument conversion, not in the rule under test.

**Delimiters and quotes** are crucial:

- `@CsvSource` separates columns by commas by default; the default quote character for wrapping a CSV value is **single quote** `'`.
- The value `"'  amy  ',amy"` wraps the first string in single quotes to preserve leading and trailing spaces. If written `"  amy  ,amy"` without quotes, JUnit may strip surrounding whitespace around tokens by default.
- An unquoted empty field (e.g., `"alice,"`) is interpreted as **`null`** at that column position under default settings. A field containing empty single quotes (e.g., CSV value `''`) represents an **empty string** `""`. Do not confuse null with empty when testing validation.
- The literal string `"null"` in CSV is **not automatically** Java null. If you need a special label converted to null, use `@CsvSource`'s `nullValues` setting or another source, and state the rule clearly.
- If a value contains a comma, quote that entire field per CSV rules; if you need a different separator, attributes such as `delimiter`/`delimiterString` may be appropriate.

Example illustrating the meaning of three data rows:

```java
@CsvSource({
        "alice,ACTIVE",
        "bob,PENDING",
        "'last,first',DISPLAY_NAME"
})
```

This is **only the data annotation**; to run it, place it on a `@ParameterizedTest` with two matching parameter types. The last row passes `"last,first"` as **one** column, not two; the single quotes are not included in the value passed to the test method.

Common CSV mistakes include mismatching the column count against the method signature, confusing Java quote syntax with CSV quotes, or unintentionally losing leading/trailing whitespace when testing trimming. When unsure, write 1–2 rows first, run the test, and inspect invocation names/values before expanding the table.

### 5.4. `@EnumSource`: sourcing data from an enum

An enum has a finite set of states, so `@EnumSource` lets you test multiple states without typing strings and converting manually.

To include all enum constants:

```java
@ParameterizedTest
@EnumSource(UsernamePolicy.Status.class)
void statusIsDefined(UsernamePolicy.Status status) {
    assertTrue(status.name().length() > 0);
}
```

This snippet illustrates providing **all enum values**. In real tests, replace the illustrative assertion with meaningful SUT behavior; merely checking that `status.name()` has positive length adds little business protection.

The business example in the runnable test suite selected specific states:

```java
@EnumSource(
        value = UsernamePolicy.Status.class,
        names = {"SUBMITTED", "APPROVED", "REJECTED"}
)
```

We can express the same dataset by **excluding** `DRAFT`:

```java
@EnumSource(
        value = UsernamePolicy.Status.class,
        mode = EnumSource.Mode.EXCLUDE,
        names = "DRAFT"
)
```

The two annotations above are **two alternatives for the same test**, not to be placed together. When a new state is added to the enum, picking a fixed name list versus "all except DRAFT" behaves differently:

- **Specifying a `names` list:** the new state is not automatically tested; suitable when only the listed cases belong to the verified set.
- **Excluding `DRAFT`:** the new state is automatically included in the "cannot edit" group; suitable when the rule is "only DRAFT can be edited". The test can catch an implementation that forgets to lock down the new state.

That is a test design choice, not merely annotation syntax. Enum names in `names` must match actual constants. If input arrives as an HTTP string (e.g., `"submitted"`), testing the enum alone does not prove Spring automatically converts HTTP input, handles lowercase, or returns the right error status; those require testing at the HTTP boundary.

## 6. Naming invocations to diagnose failures quickly

By default, parameterized test reports usually display the index and arguments; you can explicitly format names:

```java
@ParameterizedTest(name = "[{index}] username={0}")
@ValueSource(strings = {"amy", "bob_42"})
void acceptsValidUsernames(String username) {
    assertTrue(policy.isValid(username));
}
```

In the pattern:

- `{index}` is the invocation index (starting from 1).
- `{0}` is the first argument, `{1}` is the second argument if present.
- `{arguments}` can display the argument list formatted by JUnit.

If a failing case displays `[2] username=bob_42`, you can trace directly back to the exact data row to reproduce it. For long, sensitive, or complex inputs, choose concise names and avoid printing secrets in reports. Tests should use synthetic data rather than real user values.

Name methods after behavior, such as `rejectsMissingOrBlankUsernames`. `@DisplayName` (if used) and `@ParameterizedTest`'s `name` improve report readability, but they do not replace assertions.

## 7. Matching data sources with good test design

Parameterized tests fit when **the same rule** is checked with multiple inputs and a consistent assertion structure. You can use this decision table:

| Scenario | Choice | Reason |
| --- | --- | --- |
| 3–10 String values that must all be accepted | `@ValueSource(strings = {...})` | Single parameter, single expectation, easy to read |
| API must distinguish null, empty, and whitespace | `@NullAndEmptySource` + `@ValueSource` | Distinguishes missing/empty input varieties |
| Each input has a different output | `@CsvSource` | Each row shows an input–expected pair |
| Test the same rule across enum states | `@EnumSource` | Avoids typoed enum names and covers state groups |
| Each case needs completely different setup/mocking | Separate `@Test` methods | Behavior and fixtures differ; forcing them together hurts readability |
| Data consists of records/DTOs/multi-level structures | `@MethodSource` or appropriate source | Inline annotation literals are no longer maintainable |
| Hundreds of cases live in a test data file | `@CsvFileSource` or controlled fixtures | Avoids huge Java files and simplifies data updates |

**Do not automatically merge every test into one table.** For instance, "valid username returns true", "null input throws an exception", and "system stores an event on signup" differ in behavior and assertion type. If you force all three into one test with `if/else` chains to pick assertions, failures become hard to read and the test can hide important logic. Parameterize only variants that *truly share the same contract*.

Pick meaningful datasets: for a 3–12 length check, include 2, 3, 12, 13; for the leading character, include lowercase, uppercase, and digits; for empty inputs, include null, empty, and whitespace. Testing random numbers without a rationale is no substitute for boundary testing.

**Deterministic** data keeps results reproducible. Avoid values tied to the current clock, external APIs, or unseeded randomness. An enum list can grow over time; choosing INCLUDE/EXCLUDE should reflect the real rule so adding enum constants does not accidentally make tests pass vacuously.

## 8. In Spring Boot, which layer do parameterized tests belong in?

`@ParameterizedTest` is a **JUnit Jupiter** capability, not a Spring annotation. It applies across multiple test levels:

1. **Plain Java unit tests:** checking validation, calculations, mappings, policies; fastest execution, no ApplicationContext needed. `UsernamePolicyTest` above belongs here.
2. **Service tests with mocks:** each case can stub repository/client responses based on input and assert results and meaningful interactions. Only parameterize if setup and goals are similar across cases.
3. **Spring MVC slice:** use `@WebMvcTest` and `MockMvc` to test multiple request parameters/statuses/JSON payloads with the same assertion shape. Spring Test prepares the controller and required collaborators for the method.
4. **Repository or integration tests:** `@DataJpaTest`/`@SpringBootTest` can be combined with parameterized tests, though each invocation may interact with the DB/context and requires controlling data, transactions, and cleanup.
5. **Security/role matrix:** `@EnumSource` or `@CsvSource` describes permissions by role and status; run the real security infrastructure if you want to prove Spring filters/authorization work.

**Illustrative MVC snippet only, inside a test class already configured with `MockMvc` and `@WebMvcTest`:**

```java
@ParameterizedTest
@ValueSource(strings = {"", "a", "9tom"})
void invalidUsernameReturnsBadRequest(String username)
        throws Exception {
    mockMvc.perform(post("/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"" + username + "\"}"))
            .andExpect(status().isBadRequest());
}
```

The snippet above is **not a standalone test class**: it needs a `POST /users` controller, proper validation/exception mapping, a `MockMvc` bean, matching security config, and static imports from Spring Test. The illustrative values are strings safe to embed directly in JSON; **do not build JSON via string concatenation for arbitrary data** in real applications because escaping is required. For complex payloads, use a JSON serializer or proper request builder.

A green run in an MVC test proves the HTTP contract being tested; it **does not automatically prove persistence works** if the repository was replaced with a mock. Likewise, a service test using a mock repository does not prove SQL; boundary selection depends on requirements, while `@ParameterizedTest` simply repeats the same test with different datasets.

## 9. Lifecycle of each invocation and state concerns

A parameterized test creates multiple logic executions, which does not mean those executions should depend on one another. By default, JUnit Jupiter uses the **PER_METHOD** test instance lifecycle: each invocation can get a new test instance, and callbacks such as `@BeforeEach` run for each invocation. This keeps cases isolated when fixtures are prepared properly.

Even so, shared state can remain in `static` variables, Spring singletons, databases, files, caches, or test containers. Do not assume invocations automatically reset every external resource. If one case mutates a shared data list, the next invocation may turn red due to execution order unrelated to business logic. Perform controlled setup/cleanup, use transactions/rollback where appropriate, and avoid relying on source order or test order when not guaranteed.

In tests with Mockito, configure stubs per invocation according to input rather than sharing a muddled mock that passes because of call counts left by a previous case. With `@SpringBootTest` and context caching, Spring can reuse the ApplicationContext across runs; caching speeds up execution but **does not isolate application data** per invocation.

Useful principles:

- Prefer assertions on meaningful outputs and side effects rather than locking down internal helper call order.
- Name data cases clearly so that when a row fails, you immediately know the exact rule/boundary.
- Avoid pulling in network or system-clock dependencies just to parameterize simple inputs.
- If different cases require completely different fixtures, split into behavior-named test methods instead of large branching logic inside one test.

## 10. Common mistakes and how to fix them

**Mistake 1 — Forgetting the data source.** Adding `@ParameterizedTest` without an argument source leaves JUnit unable to generate parameterized runs; inspect reports and add an appropriate source. Do not confuse an unexecuted test with a passing test.

**Mistake 2 — Using `@ValueSource` for two parameters.** `@ValueSource` provides one argument per invocation. If a method takes `String input, boolean expected`, `@CsvSource` is more suitable; make sure column count, signature, and types match.

**Mistake 3 — Feeding `@NullSource` to a primitive parameter.** `null` cannot be assigned to `int` or `boolean`. Use a reference/wrapper type when null is a type-valid input, or test with another source.

**Mistake 4 — Confusing `""`, `null`, and whitespace.** `@EmptySource` does not equal a space character. Add `@ValueSource(strings = {" ", "\t"})` if business logic must reject blank strings.

**Mistake 5 — Misusing `@CsvSource` syntax.** Data with commas or unquoted edge spaces can split incorrectly or lose whitespace. In JUnit's default CSV format, quote with single quotes `'`; an unquoted empty cell differs from `''`.

**Mistake 6 — Expecting arbitrary conversions.** CSV strings automatically convert to built-in types, but cannot arbitrarily convert any JSON/DTO string into a domain object by default. Use a converter, `@MethodSource`, or fixtures for complex cases.

**Mistake 7 — `@EnumSource` covers the wrong set.** Listing names and missing a newly added state leaves that case untested; use `Mode.EXCLUDE` when the rule means "all enums except X", or choose a fixed list when that is the actual contract.

**Mistake 8 — Test method only checks the source data.** `assertEquals(expected, expected)` always passes without executing production code. Call the real SUT and assert its return value/exception/side effect.

**Mistake 9 — Merging distinct behaviors with chains of `if` statements in a test.** If each case needs different mocks, exceptions, and setup, split into distinctly named tests; parameterize only cases sharing the same behavior.

**Mistake 10 — Using `@SpringBootTest` for pure calculations.** Unnecessary contexts slow feedback and obscure failure locations. Plain Java classes can be tested with JUnit without booting Spring. Only use a context when wiring, transactions, security, or adapters are actually what you need to prove.

**Mistake 11 — Earlier cases affecting later cases.** Shared static data, DBs, or caches make results order-dependent. Isolate state per invocation and verify proper cleanup.

**Mistake 12 — Using too many values while missing boundary cases.** Ten values in the middle of a range do not replace inputs right below/above thresholds. Prioritize equivalence class representatives, boundary values, and business error cases.

## 11. Practice checklist

Before using `@ParameterizedTest`:

- Do the cases truly share the same **behavior and assertion structure**?
- How many parameters does each invocation take? A single value should use `@ValueSource`; a multi-column row should use `@CsvSource`.
- Are null, empty, whitespace, extremes, and malformed values included where relevant?
- For enums, does a fixed list or "all except..." reflect the rule?
- Does CSV data contain commas, quotes, or leading/trailing spaces requiring proper quoting?
- Are invocation names formatted so failing data can be traced immediately?
- Is the real SUT executed at the proper boundary instead of only testing stubs/mocks?
- Is each invocation independent from state of other invocations?
- Is the test discovered by the JUnit engine and run with the right Java/test dependencies?

**Remember:** `@ParameterizedTest` verifies **one behavior against multiple datasets** using a single test method. Choose the simplest source that fits: `@ValueSource` for one parameter, null/empty sources for missing values, `@CsvSource` for input–expected tables, and `@EnumSource` for enum states. Test quality comes from **representative inputs, assertions observing real behavior, and independence of each invocation**, not from cramming many `@Test` methods into one annotation.
