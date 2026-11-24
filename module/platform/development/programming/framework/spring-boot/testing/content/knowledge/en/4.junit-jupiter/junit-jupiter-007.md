# Testing Null, Empty, Boundary Values, and Input Combinations with JUnit Jupiter

## 1. Objective: test the full input domain, not just the happy path

A Spring Boot method may work fine on sample data yet still fail when a parameter is omitted, a string contains only whitespace, a number sits right on a limit, or multiple conditions occur together. Rather than writing hundreds of random tests, we partition the input domain into meaningful groups, select representative points, and test interactions across multiple parameters.

After this lesson, you will be able to:
- Distinguish **null**, **empty**, **whitespace-only (blank)**, invalid values, and valid values without conflating them.
- Choose values **just below, right at, and just above** min/max boundaries using boundary value analysis (BVA).
- Use **@NullSource, @EmptySource, @NullAndEmptySource, @ValueSource, @CsvSource, @MethodSource** in JUnit Jupiter to organize test data.
- Build input combination matrices, knowing when to use full combinations and when to reduce cases based on risk.
- Verify the same requirement at the Java method level and at the Spring Boot HTTP boundary using MockMvc, because values received after binding can differ from raw URL strings.

**Principle:** Every test must prove a requirement. A passing test does not mean every input is covered; test scope is only clear when equivalence classes, boundaries, and key interactions are identified.

## 2. Distinguishing null, empty, blank, and related cases

Inputs in the following states may require different responses:

| Java Input | Meaning | Appropriate check |
|---|---|---|
| null | No object/reference value | value == null; do not call methods on value |
| "" | String exists with length 0 | value.isEmpty() or length() == 0 |
| " " | Has one space; not empty, but blank | value.isBlank() returns true |
| "\t\n" | Has tab and newline; not empty, but blank | value.isBlank() returns true |
| "ab" | Two characters; has data but may not meet minimum length | Check length against requirement |
| "abc" | Three characters; may sit right at the minimum boundary | Check min/max rules |
| List.of() | Collection exists with 0 elements | collection.isEmpty() |
| new String[0] | Array exists with no elements | array.length == 0 |
| Integer age = null | No age provided | Check null before comparing |
| Integer age = 0 | Has numeric value 0; not null | Compare against valid range |

In Java 17:
- **String.isEmpty()** checks whether length is exactly 0. The string " " is not empty.
- **String.isBlank()** recognizes an empty string or one containing only code points treated as whitespace by Java; it is not guaranteed to match every character that visually looks like space on screen.
- **String.length()** counts UTF-16 code units, not necessarily user-perceived characters. For Unicode/emoji usernames, define the length counting rule (code units, code points, or grapheme clusters) before setting boundaries.
- **String.trim(), strip()** alter data before checking; whether to normalize or reject strings with whitespace must come from business requirements. Do not trim in tests if production does not trim.
- An **empty Collection** differs from a **null Collection**, and a Collection containing a single null element differs from both; List.of(null) is rejected by Java.

Example of a check prone to NullPointerException:

~~~java
// Wrong if username == null:
if (username.isEmpty()) {
    // ...
}

// Safe order:
if (username == null) {
    // Handle missing value.
} else if (username.isEmpty()) {
    // Handle zero-length string.
} else if (username.isBlank()) {
    // Handle whitespace-only string.
}
~~~

The snippet above illustrates conditional structure, not a standalone program. When designing APIs, distinguish "parameter must be present" from "parameter must have content" and "content must be valid"; these are three conditions that may require three groups of tests.

## 3. Equivalence partitioning before selecting data

**Equivalence partitioning** divides the input domain into groups that the system is expected to treat similarly. We pick a few representative points per group to cut down redundant tests while still verifying business semantics.

Suppose a registration username check has these illustrative rules:

1. null → **MISSING**.
2. String of length 0 → **EMPTY**.
3. String consisting only of whitespace → **BLANK**.
4. Name shorter than 3 → **TOO_SHORT**.
5. Name longer than 12 → **TOO_LONG**.
6. Otherwise → **VALID**.

**Specification note:** The sample feature measures length with String.length(), does not automatically strip/trim, and does not restrict the character alphabet. Thus " abc " has length 5 and is considered VALID. If the product requires stripping leading/trailing whitespace, both the specification and implementation/tests must be updated.

Partition table:

| Group | Representative data | Result |
|---|---|---|
| Missing reference | null | MISSING |
| Empty string | "" | EMPTY |
| Whitespace-only string | " ", "\t" | BLANK |
| Length under 3 | "a", "ab" | TOO_SHORT |
| Length between 3–12 | "abc", "abcd", "abcdefghijkl" | VALID |
| Length over 12 | "abcdefghijklm" | TOO_LONG |

Partitioning alone is not enough: if a developer accidentally writes length <= 3 instead of < 3, a 6-character input will still pass. That is why boundary value testing must be combined with partitioning.

## 4. Boundary Value Analysis (BVA) — m − 1, m, m + 1

Bugs often hide in comparison operators (<, <=, >, >=), indices, count limits, and type conversions. For an inclusive valid range **[min, max]**, the minimal high-value dataset consists of:

- min − 1: just below the lower limit, must be rejected.
- min: right at the lower limit, must be accepted.
- min + 1: just above the lower limit, must be accepted.
- max − 1: just below the upper limit, must be accepted.
- max: right at the upper limit, must be accepted.
- max + 1: just above the upper limit, must be rejected.

Example for valid username length of 3–12 UTF-16 code units:

| Length | String | Expected result |
|---|---|---|
| 2 | "ab" | TOO_SHORT |
| 3 | "abc" | VALID |
| 4 | "abcd" | VALID |
| 11 | "abcdefghijk" | VALID |
| 12 | "abcdefghijkl" | VALID |
| 13 | "abcdefghijklm" | TOO_LONG |

For valid ages from 18 to 120 (inclusive on both ends), choose **17, 18, 19, 119, 120, 121**, plus null if the field may be omitted. You cannot use a single test with 0 to substitute for both boundaries; off-by-one bugs require points immediately adjacent to each limit.

Numeric coverage needs to be broader when using primitive types: e.g., Integer.MIN_VALUE, Integer.MAX_VALUE, overflow on addition, and parsing non-numeric strings. Those cases should only be added if the method/API can receive such values and real risk warrants testing them. If the condition is "length less than or equal to 12" instead of "less than 12", update the expectation table to match the spec.

## 5. Data source annotations in JUnit Jupiter

JUnit Jupiter supports **@ParameterizedTest** to run the same test method multiple times with different parameter sets. Each run is a separate invocation with its own assertions and outcome in the report.

| Annotation | When to use | Known limitations |
|---|---|---|
| @NullSource | Need one invocation passing null | Cannot be used for primitive parameters int/boolean; use Integer/Boolean |
| @EmptySource | Need a supported empty value, typically String "" or certain collections/arrays | Does not generate whitespace; parameter type must be supported |
| @NullAndEmptySource | Combines null + empty for one parameter | Does not generate " " or multi-parameter cases |
| @ValueSource | Simple single-parameter list: strings, ints, longs… | Does not take multiple columns; cannot pass null directly |
| @CsvSource | Short multi-column table, handy for expected values | Requires knowing how null/empty values, quotes, and type conversions work |
| @MethodSource | Generates complex parameters, objects, null, Stream<Arguments>, combinations | Factory in the same class must normally be static, unless using PER_CLASS lifecycle |

Short example with null and empty strings:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@ParameterizedTest
@NullAndEmptySource
void missingOrEmptyNeverValid(String name) {
    assertNotEquals(RegistrationRules.UsernameStatus.VALID,
            RegistrationRules.classifyUsername(name));
}
~~~

This is a **sample method** placed inside a test class, not a standalone Java file. It creates two runs, one with null and one with "". It **does not** include the " " case. To add whitespace-only data, use @ValueSource(strings = {" ", "\t", "\n"}) or @MethodSource.

**Common pitfall with @CsvSource:** An empty field between two commas is normally interpreted as null. A field empty-quoted with the configured quote character (single quote by default) yields an empty string; the two values are not equivalent. You can use nullValues and emptyValue when you want explicit interpretation rules. Prefer @MethodSource if multi-column data contains commas, newlines, or needs strict null/empty distinction.

## 6. Complete runnable example with Spring Boot 3.3.5, Java 17, and Gradle

The example uses a small registration rule to demonstrate **null**, **empty**, **blank**, **boundaries**, and **combinations**. There are two parts:

- **Plain Java testing with JUnit Jupiter:** Verifies exact rules, runs fast, requires no Spring ApplicationContext.
- **HTTP boundary testing with MockMvc:** Verifies how request parameters are converted by Spring MVC into Java arguments before reaching the rules.

Additional spec for the example: requires a VALID username, age from 18 to 120 (inclusive), and acceptance of terms. There is no account persistence or security logic; the GET endpoint simply returns the validation result without actually registering an account.

Project structure:

~~~text
settings.gradle
build.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/RegistrationRules.java
src/main/java/demo/testing/RegistrationController.java
src/test/java/demo/testing/RegistrationRulesTest.java
src/test/java/demo/testing/RegistrationHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jupiter-input-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter-test provides Jupiter along with utilities like AssertJ, Mockito, and Spring Test; this example uses Jupiter directly and MockMvc. Calling useJUnitPlatform() instructs Gradle to run tests via JUnit Platform. The example uses fixed Spring Boot/Gradle versions for illustration; when applying to an existing project, use the versions managed by that project.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/RegistrationRules.java**

~~~java
package demo.testing;

public final class RegistrationRules {
    private RegistrationRules() {
    }

    public enum UsernameStatus {
        MISSING, EMPTY, BLANK, TOO_SHORT, TOO_LONG, VALID
    }

    public static UsernameStatus classifyUsername(String username) {
        if (username == null) {
            return UsernameStatus.MISSING;
        }
        if (username.isEmpty()) {
            return UsernameStatus.EMPTY;
        }
        if (username.isBlank()) {
            return UsernameStatus.BLANK;
        }
        if (username.length() < 3) {
            return UsernameStatus.TOO_SHORT;
        }
        if (username.length() > 12) {
            return UsernameStatus.TOO_LONG;
        }
        return UsernameStatus.VALID;
    }

    public static boolean eligible(
            String username, Integer age, boolean acceptedTerms) {
        return classifyUsername(username) == UsernameStatus.VALID
                && age != null
                && age >= 18
                && age <= 120
                && acceptedTerms;
    }
}
~~~

The classification function uses an intentional check order: avoiding calling isEmpty()/isBlank() on null, while separating empty from blank. Integer is used for age to test null as well; age >= 18 is safe because the && operator short-circuits after age != null. A name with spaces on both sides is still measured by its original length; this is the declared illustrative rule.

**src/main/java/demo/testing/RegistrationController.java**

~~~java
package demo.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registration")
class RegistrationController {

    record EligibilityResult(String usernameStatus, boolean eligible) {
    }

    @GetMapping("/check")
    EligibilityResult check(
            @RequestParam(required = false) String username,
            @RequestParam(required = false) Integer age,
            @RequestParam(defaultValue = "false") boolean acceptedTerms) {
        return new EligibilityResult(
                RegistrationRules.classifyUsername(username).name(),
                RegistrationRules.eligible(username, age, acceptedTerms));
    }
}
~~~

A valid request such as:

~~~text
GET /api/registration/check?username=abc&age=18&acceptedTerms=true
~~~

returns JSON with usernameStatus equal to VALID and eligible equal to true. When username is omitted completely, the optional String parameter receives null; when sent as username=, it receives an empty string. These binding rules are why HTTP tests are needed alongside unit tests. For acceptedTerms, defaultValue = "false" applies when the parameter is missing or left empty; that is a design choice for this example, not a universal rule for all APIs.

### 6.1. Testing equivalence classes and boundaries with @MethodSource

**src/test/java/demo/testing/RegistrationRulesTest.java**

~~~java
package demo.testing;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.Arguments;

import static demo.testing.RegistrationRules.UsernameStatus;
import static org.junit.jupiter.api.Assertions.*;

class RegistrationRulesTest {

    @ParameterizedTest(name = "{index}: username={0} => {1}")
    @MethodSource("usernameCases")
    void classifiesUsername(
            String username, UsernameStatus expected) {
        assertEquals(
                expected, RegistrationRules.classifyUsername(username));
    }

    static Stream<Arguments> usernameCases() {
        return Stream.of(
                Arguments.of(null, UsernameStatus.MISSING),
                Arguments.of("", UsernameStatus.EMPTY),
                Arguments.of(" ", UsernameStatus.BLANK),
                Arguments.of("\t\n", UsernameStatus.BLANK),
                Arguments.of("ab", UsernameStatus.TOO_SHORT),
                Arguments.of("abc", UsernameStatus.VALID),
                Arguments.of("abcd", UsernameStatus.VALID),
                Arguments.of("abcdefghijk", UsernameStatus.VALID),
                Arguments.of("abcdefghijkl", UsernameStatus.VALID),
                Arguments.of("abcdefghijklm", UsernameStatus.TOO_LONG),
                Arguments.of(" abc ", UsernameStatus.VALID)
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    void nullAndEmptyAreDifferentFromValidName(String username) {
        assertNotEquals(
                UsernameStatus.VALID,
                RegistrationRules.classifyUsername(username));
    }

    @ParameterizedTest
    @ValueSource(strings = {" ", "\t", "\n"})
    void whitespaceOnlyIsBlank(String username) {
        assertEquals(
                UsernameStatus.BLANK,
                RegistrationRules.classifyUsername(username));
    }

    @ParameterizedTest(name = "{index}: age={0}, valid={1}")
    @CsvSource({
            "17, false",
            "18, true",
            "19, true",
            "119, true",
            "120, true",
            "121, false"
    })
    void checksAgeBoundaries(int age, boolean expected) {
        assertEquals(
                expected,
                RegistrationRules.eligible("alice", age, true));
    }

    @ParameterizedTest
    @NullSource
    void nullAgeIsRejected(Integer age) {
        assertFalse(RegistrationRules.eligible("alice", age, true));
    }

    @Test
    void falseConsentIsRejected() {
        assertFalse(
                RegistrationRules.eligible("alice", 18, false));
    }

    private record NameSample(String value, boolean valid) {
    }

    private record AgeSample(Integer value, boolean valid) {
    }

    @ParameterizedTest(
            name = "{index}: username={0}, age={1}, terms={2} => {3}")
    @MethodSource("registrationCombinations")
    void testsInputCombinations(
            String username, Integer age,
            boolean acceptedTerms, boolean expected) {
        assertEquals(
                expected,
                RegistrationRules.eligible(
                        username, age, acceptedTerms));
    }

    static Stream<Arguments> registrationCombinations() {
        List<NameSample> names = List.of(
                new NameSample(null, false),
                new NameSample("", false),
                new NameSample("ab", false),
                new NameSample("abc", true),
                new NameSample("abcdefghijkl", true),
                new NameSample("abcdefghijklm", false)
        );

        List<AgeSample> ages = List.of(
                new AgeSample(null, false),
                new AgeSample(17, false),
                new AgeSample(18, true),
                new AgeSample(120, true),
                new AgeSample(121, false)
        );

        return names.stream().flatMap(name ->
                ages.stream().flatMap(age ->
                        Stream.of(false, true).map(terms ->
                                Arguments.of(
                                        name.value(), age.value(), terms,
                                        name.valid() && age.valid() && terms)
                        )
                )
        );
    }
}
~~~

**Points to observe in the test code:**

1. usernameCases() returns Stream<Arguments>, because each run needs two values: input and expected. With @MethodSource in the same class, the factory is static when @TestInstance(PER_CLASS) is not configured.
2. @NullAndEmptySource generates the null and "" cases, not " ". @ValueSource for " ", "\t", "\n" provides separate test runs.
3. @CsvSource converts input strings to int and boolean matching the method's parameter types. Age is int because every row in the table has a number; testing null requires Integer in a separate test.
4. usernameCases() explicitly checks length thresholds 2/3/4 and 11/12/13. Comparing against the **exact enum result** is far better than just assertNotNull.
5. The name and age samples in the combination matrix carry **independent expected flags** (valid or not per requirements) before calling the production function. The final expected outcome is derived from the business table "valid name AND valid age AND accepted terms", without calling the method under test to compute expected values.
6. List.of() contains non-null NameSample/AgeSample records; the value field inside a record can be null. This differs from List.of(null), which throws a NullPointerException.
7. testsInputCombinations runs many test cases, yet the report still shows one parameterized Java method with individual invocations. Choosing a name template displaying the data helps track down failing inputs.

### 6.2. Testing after Spring MVC binds HTTP data

**src/test/java/demo/testing/RegistrationHttpTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationHttpTest {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
            "abc, VALID, true",
            "ab, TOO_SHORT, false",
            "abcdefghijklm, TOO_LONG, false"
    })
    void checksHttpInputAndExpectedResult(
            String username, String expectedStatus, boolean eligible)
            throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", username)
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value(expectedStatus))
                .andExpect(jsonPath("$.eligible").value(eligible));
    }

    @Test
    void missingQueryParameterBecomesNull() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("MISSING"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void emptyQueryParameterIsNotNull() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", "")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("EMPTY"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void whitespaceQueryParameterIsBlank() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", " ")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("BLANK"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void invalidNumericQueryParameterReturns400() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", "abc")
                        .param("age", "not-a-number")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Here MockMvc exercises Spring Boot's MVC configuration without opening a real network port. The tests explicitly distinguish **omitted parameter**, **empty parameter**, and **whitespace parameter**, even though all three result in eligible = false. If you only asserted eligible = false, binding bugs that collapse MISSING/EMPTY/BLANK could slip through.

The age field must convert to Integer. When "not-a-number" fails to bind to Integer, Spring MVC normally returns HTTP 400 due to a type conversion failure; this tests the **HTTP layer**, not RegistrationRules. If a project defines a @ControllerAdvice or custom error rules, verify the actual contract instead of assuming every application returns the exact same body.

### 6.3. Running and reading results

In the project directory, if the Gradle Wrapper is present:

~~~bash
./gradlew test
~~~

With PowerShell on Windows:

~~~powershell
.\gradlew.bat test
~~~

If no Wrapper is present yet, use a compatible installed Gradle to generate a Wrapper or run gradle test. The files above are a complete example for source and build files; ./gradlew only works when the Wrapper files also exist.

When all assertions succeed, the Gradle test task completes successfully; view the HTML report at **build/reports/tests/test/index.html**. Displayed logs and total test counts can vary with Gradle settings, but expected cases include:

- 11 invocations in usernameCases().
- 2 invocations from @NullAndEmptySource.
- 3 invocations from @ValueSource with whitespace.
- 6 invocations for age via @CsvSource.
- 1 invocation for null age and 1 invocation for rejected consent.
- **60 invocations** from 6 name states × 5 age states × 2 consent values.
- 3 HTTP invocations with @CsvSource and 4 individual HTTP methods.

Therefore the total in this example suite is **91 runs** (84 unit runs and 7 HTTP runs), assuming no other tests were added to the project. A failing run displays the corresponding input in the invocation name to help pinpoint the cause. If you modify data or test filters, counts will change; always check the real report rather than blindly trusting a green build.

## 7. Input combinations: avoid testing each condition only in isolation

Suppose eligibility depends on three axes:

| Axis | Representative values | Number of choices |
|---|---|---|
| Username | null, "", "ab", "abc", length 12, length 13 | 6 |
| Age | null, 17, 18, 120, 121 | 5 |
| Terms consent | false, true | 2 |

A **full Cartesian product** yields 6 × 5 × 2 = 60 cases. Under the current rule, only 2 valid name choices × 2 valid age choices × 1 consent true value = 4 cases are accepted; the remaining 56 must be rejected. Combining them catches interaction bugs such as "when age = null and acceptedTerms = true, the system throws NullPointerException" or "length-13 username slips through if age is valid".

**You should not always run every combination.** With 10 parameters of 5 values each, full Cartesian is 5^10 = 9,765,625 cases. Practical strategy:

1. Identify important partitions and boundaries for **each** parameter first.
2. If the matrix is small, use full combinations, especially for rules combining allow/deny checks.
3. If the matrix is too large, prioritize high-risk combinations, valid cases, each invalid input type, co-occurring boundaries, and interdependent conditions.
4. Consider **pairwise** testing so every pair of values across any two axes appears in at least one case; pairwise **does not guarantee** catching bugs triggered only when three or more conditions coincide.
5. When certain combinations cannot occur in production, document the real constraint and exclude them intentionally instead of dropping test cases arbitrarily.
6. Document why the dataset was chosen and add a new regression case whenever production encounters a bug for a specific combination.

JUnit Jupiter **does not require a special Cartesian product annotation**: @MethodSource can generate Stream<Arguments> via loops or flatMap as shown. Third-party libraries offer parameter combination helpers, but they are unnecessary to understand the core mechanism.

## 8. Selecting test data by input type

### 8.1. String

Distinguish: null, "", whitespace-only, very short, right at min, just above min, normal, just below max, right at max, above max, Unicode/emoji, punctuation, and leading/trailing spaces when relevant to the specification.

If normalization applies (e.g., strip, case folding, Unicode normalization), test **before and after normalization**. Rules like "at most 12 display characters" must define the exact counting unit; String.length() does not satisfy that requirement automatically.

### 8.2. Integers, decimals, and monetary amounts

Test null for wrappers, 0, negative, positive, min−1/min/min+1, max−1/max/max+1, data-type limits when reachable, and arithmetic that could overflow. With BigDecimal, check scale/rounding, compare using compareTo when only numeric value matters, and explicitly test rounding rules.

Distinguish **testing Java rules** from **testing HTTP string type conversion**: "age=abc", "age=", and omitted age may traverse different binding paths.

### 8.3. Collections, arrays, and pagination data

Test null collections, empty collections, single element, exact max size, over max size, duplicate elements, null elements (if supported by the container), ordering, and first/last indices. A List containing one null element is not an empty List. If an API forbids null elements, tests must prove they are rejected.

For page and size, typical boundaries include page = 0 if zero-indexed, page = −1, size = 0, size = 1, size = max, and size = max+1; do not assume every API uses the same pagination conventions.

### 8.4. Enums, booleans, and dependent parameter pairs

Enums have finite values; test meaningful values, unsupported states, invalid token handling at the HTTP layer, and null if optional. Booleans have no numeric boundaries but have two states false/true plus a possible "omitted" state when using the Boolean wrapper. When parameters depend on one another, always test at least one valid scenario and several conflicting scenarios.

## 9. Assertions and test design to avoid false confidence

### Checking concrete outcomes

An assertion like assertNotNull(result) is very weak when the requirement expects enum TOO_LONG. Much better is assertEquals(TOO_LONG, result). For exceptions, use assertThrows to check the right exception type and important message when part of the contract; however, **do not turn null into an exception on your own** if the specification expects returning MISSING.

### Avoid computing expected values with the production function

Bad example:

~~~java
// Nearly meaningless test: calls the same method again to compute expected.
boolean expected = RegistrationRules.eligible("abc", 18, true);
assertEquals(expected, RegistrationRules.eligible("abc", 18, true));
~~~

Better: supply expected values from an independent rule table, e.g., name abc + age 18 + consent true → true; age 17 → false; null name → false. In the combination matrix, validity flags on NameSample/AgeSample are **declared independently** and combined per the specification.

### Avoid pointless duplicate tests

Having a couple of overlapping cases between @NullAndEmptySource and a full matrix is fine to illustrate Jupiter features, but real projects should organize data to avoid dozens of identical assertions that add no bug-finding power. Conversely, **do not oversimplify** to the point of dropping boundaries or meaningful states.

### Choosing the right test level

- **Unit/Jupiter:** Fast, verifies branching, boundaries, and combinations with clear data.
- **Spring MVC slice or MockMvc:** Verifies parsing, binding, validation, statuses, and JSON; do not replace with direct method calls.
- **Integration tests with real DB/systems:** Required when rules rely on DB constraints, uniqueness, transactions, or external services. Use isolated data with proper cleanup/transactions.
- **Contract tests:** Needed when error codes, JSON fields, and data types must remain compatible with other consumers.

A single case may appear at multiple levels because it proves different risks; for example, null in a unit test proves Java logic, while a missing query parameter in MockMvc proves binding and mapping.

## 10. Common JUnit Jupiter mistakes when testing inputs

| Mistake | Why it is wrong | Fix |
|---|---|---|
| Testing only valid inputs | Misses missing data, empty strings, malformed formats, and boundaries | Build partitions and BVA before coding tests |
| Lumping null, "", and " " into one group | May yield different results or execution paths | Test null/empty/blank separately per contract |
| Applying @NullSource to int | Primitives cannot accept null | Use Integer or test malformed inputs at HTTP |
| Thinking @EmptySource provides whitespace | Empty string differs from whitespace | Add @ValueSource or @MethodSource |
| Using @ValueSource for multiple columns/complex objects | Misuses single-argument source | Use @CsvSource or @MethodSource |
| Non-static @MethodSource under default lifecycle | Jupiter cannot invoke factory method as expected | Make factory static, or intentionally use PER_CLASS |
| Confusing empty CSV cells with empty strings | Unquoted cells can become null, empty quotes become "" | Use explicit CSV/emptyValue/nullValues syntax |
| Testing only min and max without adjacent sides | Hard to catch < vs <= bugs | Add min−1/min+1/max−1/max+1 |
| Testing each parameter only in isolation | Misses interaction bugs across conditions | Build combination matrices or pairwise sets per risk |
| Using String.length() for every notion of "character" | UTF-16 code units differ from code points/graphemes | Define counting units per product rules |
| Assuming HTTP matches direct method inputs | Frameworks have their own binding/defaults/validation | Add MockMvc or integration tests at boundaries |
| Concluding "green build = full coverage" | Tests may be filtered out, missing cases, or have weak assertions | Inspect reports and cross-check coverage against spec tables |

## 11. Workflow for applying to a real endpoint

When given a requirement like "register username of 3 to 12 characters, age 18–120, mandatory terms acceptance", follow this order:

1. **Write a decision table:** Specify how null, empty, blank, Unicode, trimming, non-numeric values, boundary signs, and error precedence are handled. If unclear, clarify the spec before deciding expected outcomes.
2. **Identify partitions:** Choose one or a few representative values for each state of each parameter.
3. **Determine BVA:** List min−1, min, min+1, max−1, max, max+1; add null/empty if meaningful.
4. **Build the combination matrix:** Count total cases and choose full combinations or a risk-reduced set keeping dangerous combinations.
5. **Write JUnit Jupiter tests:** Use @ValueSource/@CsvSource for short tables, @NullAndEmptySource for type-compatible cases, and @MethodSource when multiple parameters or data generators are needed.
6. **Check HTTP:** With Spring Boot, use MockMvc to test differences between missing, empty, whitespace, and malformed query parameters and responses.
7. **Review reports:** Count actual invocations executed, inspect input names on failure, verify assertions reflect business logic, and add regression cases for newly discovered bugs.

The most valuable test suite is not the one with the most random data, but the one that proves the **input equivalence groups, boundaries, and parameter interactions** that business requirements care about.
