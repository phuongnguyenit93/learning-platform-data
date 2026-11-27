# Custom Assertions via Methods in the Base Test

## 1. When Built-In Matchers Are Not Enough

**Spring Cloud Contract (SCC)** uses contracts written in **Groovy DSL** or **YAML DSL** to verify communication behavior between a **producer** and a **consumer**. From a contract, the system can generate producer-side tests and create stubs for the consumer to run with **Stub Runner**, then integrate those steps into CI to detect incompatible API changes.

Common matchers such as `byEquality`, `byRegex`, `byType`, and date/time matchers solve many scenarios. Yet some rules require Java code, for example:

- Discount percentage must lie in the closed interval **0–50**.
- An inventory allocation array must be non-empty and must not contain duplicate warehouse codes.
- A monetary value must satisfy rounding or divisibility rules by payment unit.
- An ID has a specialized structure that cannot be readably expressed with regex alone.

A **custom assertion** is a check method defined by the development team, called by the **generated producer test** as instructed by the contract. In Groovy DSL, the common form is `byCommand('assertRule($it)')`; in YAML DSL, it is `type: by_command` with `value` containing the call.

This lesson focuses on **writing custom assertions as base-test methods** and connecting them to contracts, generated tests, Stub Runner, and CI.

After this lesson, you will be able to explain the test-generation flow, write `byCommand`/`by_command` matchers, implement Java assertions, configure `baseClassForTests`, verify that tests actually invoke the method, and identify where custom assertions cannot substitute for consumer checks.

## 2. Where Custom Assertions Fit in the Producer–Consumer Flow

~~~mermaid
flowchart TD
    A["Groovy or YAML contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    C --> D["Call real producer"]
    D --> E["Extract value via JSONPath"]
    E --> F["Call assertion method in base test"]
    F --> G{"Assertion passes?"}
    G -- "No" --> H["Test fails, blocks change"]
    G -- "Yes" --> I["Producer verification passes"]
    B --> J["Stub artifact"]
    J --> K["Consumer test with Stub Runner"]
~~~

**Distinguish both sides:** a custom assertion in a **response matcher** checks the response returned by the **real producer** when generated tests run. Stub Runner normally returns the **sample response** taken from the contract; it does not load and execute Java methods from the producer's base test.

| Component | Role |
|---|---|
| `response.bodyMatchers` (Groovy) / `response.matchers.body` (YAML) | Specifies the target field and validation rule |
| `$it` | Placeholder for the JSONPath-extracted value in generated tests |
| `byCommand` / `by_command` | Instructs the generated test to call a custom method |
| `ContractTestBase` | Sets up the test environment and provides assertion methods |
| Generated producer test | Verifies producer code against the contract |
| Stub artifact + Stub Runner | Verifies consumer code uses sample behavior properly |
| CI | Integrates, tracks, and blocks incompatible changes |

## 3. Running Example: Discount Percentage

Suppose **Promotion Service** exposes:

~~~http
GET /api/promotions/SKU-123 HTTP/1.1
Accept: application/json
~~~

Sample response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "discountPercent": 15,
  "currency": "VND"
}
~~~

**Checkout Service** reads `discountPercent` to display and compute prices. Both teams agree:

1. `discountPercent` is a **JSON number**, not a string.
2. Its value lies in **[0, 50]**.
3. It can vary by campaign, so **it is not forced to always equal 15**.
4. `sku` stays `SKU-123` and `currency` stays `VND` in this scenario.

If you use equality for `discountPercent: 15`, a producer returning 25 would be flagged as wrong despite being valid. If you use only a type matcher, a producer returning 75 could still pass. A Java assertion checking **both type and numeric range** expresses the requirement clearly.

| Response `discountPercent` | Expected | Why |
|---|---|---|
| `0` | PASS | Equals min |
| `15` | PASS | Within range |
| `50` | PASS | Equals max |
| `50.01` | FAIL | Exceeds max |
| `-1` | FAIL | Below min |
| `75` | FAIL | Exceeds max |
| `"15"` | FAIL | String differs from Number |
| `null` | FAIL | Not a Number |
| Missing field | FAIL or error during JSONPath extraction; verify actual test | Fails schema |

## 4. Writing the Contract in Groovy DSL

Example file `src/test/resources/contracts/promotions/discount-percent.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout requires a valid discount percentage'

    request {
        method GET()
        url '/api/promotions/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-123',
            discountPercent: 15,
            currency: 'VND'
        )

        bodyMatchers {
            jsonPath(
                '$.discountPercent',
                byCommand('assertValidDiscountPercent($it)')
            )
        }
    }
}
~~~

Meaning:

- The `request` block declares the method, URL, and headers sent to the producer.
- The `response` block declares the HTTP status, content type, and sample body.
- `jsonPath('$.discountPercent', ...)` selects the exact field to verify.
- `byCommand('assertValidDiscountPercent($it)')` instructs the **generated test** to invoke the identically named method with the extracted value.
- `$it` is an SCC placeholder; it is not a controller variable.

Place the matcher in **response** because you need to inspect data returned by the producer. Fixed fields such as `sku` and `currency` can still be verified via default equality or corresponding matchers. Custom assertions should focus on rules that genuinely require Java.

## 5. Equivalent YAML DSL

If using YAML, you can describe the same behavior:

~~~yaml
description: Checkout requires a valid discount percentage
name: valid_discount_percent

request:
  method: GET
  url: /api/promotions/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    discountPercent: 15
    currency: VND
  matchers:
    body:
      - path: $.discountPercent
        type: by_command
        value: 'assertValidDiscountPercent($it)'
~~~

| Groovy | YAML | Role |
|---|---|---|
| `bodyMatchers` | `matchers.body` | Where body matchers are declared |
| `jsonPath('$.discountPercent', ...)` | `path: $.discountPercent` | Selects JSON field |
| `byCommand(...)` | `type: by_command` | Uses custom command |
| `'assertValidDiscountPercent($it)'` | `value: 'assertValidDiscountPercent($it)'` | Assertion invocation |

YAML and Groovy here are **two alternative notations**; do not keep both under the contracts folder if they describe the exact same scenario. When converting DSLs, inspect generated tests/stubs to ensure semantics remain equivalent.

## 6. Project Structure and Base Test Class

Producer layout example:

~~~text
promotion-service/
├── pom.xml
└── src/
    └── test/
        ├── java/
        │   └── com/example/promotion/
        │       └── ContractTestBase.java
        └── resources/
            └── contracts/
                └── promotions/
                    └── discount-percent.groovy
~~~

`ContractTestBase` has **two responsibilities**:

- Setting up the environment for generated tests to call the producer, e.g., MockMvc, WebTestClient, or real HTTP.
- Providing the `assertValidDiscountPercent` method for generated tests to inherit and invoke.

There is no rule that every project uses the same base class. Configuration depends on **test mode**, JUnit, Spring Boot, and the Spring Cloud Contract version. The next example illustrates **MockMvc via RestAssuredMockMvc**.

## 7. Writing the Custom Assertion Method in the Base Test

~~~java
package com.example.promotion;

import java.math.BigDecimal;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    WebApplicationContext applicationContext;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.webAppContextSetup(applicationContext);
    }

    public void assertValidDiscountPercent(Object actual) {
        assertThat(actual)
                .as("discountPercent must be a JSON number")
                .isInstanceOf(Number.class);

        BigDecimal percent = new BigDecimal(actual.toString());

        assertThat(percent)
                .as("discountPercent must be within [0, 50]")
                .isBetween(BigDecimal.ZERO, new BigDecimal("50"));
    }
}
~~~

Explanation of each decision:

1. `public void` ensures generated tests can invoke the inherited method.
2. `Object actual` accepts the JSONPath input, and then the method **checks the type itself**. Runtime data may be `Integer`, `Long`, `BigDecimal`, or another `Number` subtype.
3. `isInstanceOf(Number.class)` rejects string `"15"` even though it parses as a number.
4. `BigDecimal` enables clear decimal range checks.
5. AssertJ's `isBetween` checks **both endpoints** 0 and 50 inclusive.
6. The assertion **throws an error** when the condition fails; the test runner marks the test failed.

If the percentage must be an **integer**, add an assertion on fractional digits / JSON type; the code above **allows 12.5** because it lies within the valid interval. That is an intentional illustrative choice.

Assertion methods live in **test sources**, not production code. In this example, the method should inspect only the passed-in value and avoid querying databases, making external HTTP calls, or depending on current wall-clock time.

## 8. Configuring Maven and Gradle to Link the Base Test

For Maven, `spring-cloud-contract-maven-plugin` provides `baseClassForTests`. Illustrative plugin snippet (pick an actual plugin version compatible with your BOM):

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>4.x.y</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>com.example.promotion.ContractTestBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`4.x.y` is only an **illustrative version placeholder**; replace it with an actual version matching your project's Spring Boot and Spring Cloud Release Train. You cannot run this snippet verbatim with `4.x.y`.

The verifier dependency typically belongs in test scope, without pinning a version if already managed by the Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

For Gradle with the Spring Cloud Contract plugin applied:

~~~groovy
contracts {
    baseClassForTests = 'com.example.promotion.ContractTestBase'
}
~~~

Checks to confirm in your project:

- The package/class in `baseClassForTests` matches the test source.
- The test framework plus `RestAssuredMockMvc` and AssertJ libraries are on the **test classpath**.
- The test mode aligns with how the base class initializes the environment.
- The plugin runs test generation and the test runner executes them.
- The Contract plugin version aligns with Contract dependencies resolved by the BOM.

Maven's `dependencyManagement` does not automatically manage **build plugin** versions. When upgrading the Spring Cloud Release Train, check the plugin version as well.

## 9. What Does the Generated Test Execute?

When processing contracts, SCC can generate a test class extending the base class and calling the assertion method. The code sketch below illustrates **the concept** only; it is **not exact generated source**:

~~~java
// Pseudocode: exact structure, method names, and test API depend on SCC version.
class GeneratedDiscountTest extends ContractTestBase {

    @Test
    void verifyPromotionResponse() {
        // Send GET /api/promotions/SKU-123 to producer.
        // Verify response status and headers.
        // Extract $.discountPercent from response JSON.
        Object actual = /* JSONPath value */;
        assertValidDiscountPercent(actual);
    }
}
~~~

After test generation, inspect the generated source:

1. Request uses the exact method, URL, and headers.
2. The test actually extracts `$.discountPercent`.
3. There is a call to `assertValidDiscountPercent(...)` passing the extracted value.
4. The test class **extends** the right base class or has access to the method.
5. Status, headers, and other matchers are still asserted.
6. Tests are compiled and **executed**, not merely generated.

Having a contract with `byCommand` is not yet proof the assertion ran. The proof lies in the generated source and test report.

## 10. How to Confirm the Custom Assertion Truly Catches Bugs

A useful test is mutating the producer's response value in the test environment and re-running the **same generated test**:

| Response Returned by Producer | Expected |
|---|---|
| `15` | PASS |
| `0` | PASS |
| `50` | PASS |
| `50.01` | FAIL |
| `75` | FAIL |
| `-2` | FAIL |
| `"15"` | FAIL (wrong type) |
| `null` | FAIL |

Practice:

1. Run the test with `15` and observe PASS.
2. Have the producer return `75`; the test must fail with a message about `[0, 50]`.
3. Have the producer return `"15"`; the test must fail due to wrong type.
4. Test `0` and `50` to confirm inclusive boundaries.
5. Restore the valid implementation.

If `75` still leaves the test green, check whether the contract was discovered, whether the matcher is on `response`, whether the generated test invokes the assertion, whether the helper actually throws on failure, and whether the build actually runs the generated tests.

## 11. Comparing Custom Assertions with Built-In Matchers

| Rule | Best Approach | Why |
|---|---|---|
| `status` must equal `ACTIVE` | Equality | Compares a single value |
| ID matches `SKU-[0-9]+` | Regex | Concisely describable |
| `quantity` is a number | Type matcher | Checks type |
| Timestamp matches format | Date/time matcher | Built-in rules exist |
| `discountPercent` in `[0,50]` | Custom method | Involves numeric logic |
| Warehouse codes in array do not repeat | Custom method | Requires iterating elements |
| Response total equals product of multiple fields | Integration assertion with full context | `$it` is usually one JSONPath-extracted value |
| Performance, security, database checks | Separate integration/E2E tests | Outside this matcher's responsibility |

Custom assertions make contracts **coupled to test code**. Use them only when a rule is genuinely difficult to express with standard matchers. Calling a Java helper for every field that only needs equality strips declarativeness from the contract and makes reviews harder.

## 12. Advanced Example: Validating an Inventory Allocation Array

Another producer returns:

~~~json
{
  "sku": "SKU-123",
  "allocations": [
    {"warehouseCode": "HCM-01", "quantity": 2},
    {"warehouseCode": "HN-02", "quantity": 3}
  ]
}
~~~

Rule: `allocations` must be a non-empty array; each element has a non-blank warehouse code; warehouse codes must be unique; quantity must be positive.

Groovy matcher:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        sku: 'SKU-123',
        allocations: [
            [warehouseCode: 'HCM-01', quantity: 2],
            [warehouseCode: 'HN-02', quantity: 3]
        ]
    )
    bodyMatchers {
        jsonPath('$.allocations', byCommand('assertValidAllocations($it)'))
    }
}
~~~

The following Java method should live **inside the base test or a helper called by the base test**:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

public void assertValidAllocations(Object actual) {
    assertThat(actual)
            .as("allocations must be a JSON array")
            .isInstanceOf(List.class);

    List<?> allocations = (List<?>) actual;
    assertThat(allocations).isNotEmpty();

    Set<String> seen = new HashSet<>();

    for (Object element : allocations) {
        assertThat(element).isInstanceOf(Map.class);
        Map<?, ?> item = (Map<?, ?>) element;

        Object codeValue = item.get("warehouseCode");
        assertThat(codeValue).isInstanceOf(String.class);

        String code = (String) codeValue;
        assertThat(code).isNotBlank();
        assertThat(seen.add(code))
                .as("Duplicate warehouseCode: " + code)
                .isTrue();

        Object quantity = item.get("quantity");
        assertThat(quantity).isInstanceOf(Number.class);
        assertThat(((Number) quantity).doubleValue())
                .isGreaterThan(0.0);
    }
}
~~~

**Note:** `$it` for a JSONPath returning an array may have different concrete runtime types depending on the JSONPath/Contract library. The sample above assumes a `List` of `Map`s; inspect generated sources and actual runtime types before adopting it. If `quantity` must be an integer, add a corresponding assertion since the current check only guarantees a **positive number**.

### When Checking Multi-Field Relationships

`$it` typically represents a single value at the selected JSONPath; for instance, a matcher on `$.totalVnd` receives only the total, not `quantity` and `unitPriceVnd`. For constraints like `totalVnd = quantity × unitPriceVnd`, either select a matcher capturing enough context if supported by the DSL and verify runtime types, or write a **dedicated integration test** inspecting the whole response. Never let a helper call external services to deduce missing fields.

## 13. Must Throw an Assertion Failure on Invalid Data

A helper that only returns a boolean may be ignored by the generated test:

~~~java
// Avoid: false return value may not be checked by the caller.
public boolean isValidPercent(Object raw) {
    if (!(raw instanceof Number)) {
        return false;
    }
    double percent = ((Number) raw).doubleValue();
    return percent >= 0 && percent <= 50;
}
~~~

A safer approach is a method using assertions or `throw new AssertionError(...)`:

~~~java
public void assertPercentWithinRange(Object raw) {
    if (!(raw instanceof Number)) {
        throw new AssertionError(
            "discountPercent must be a Number: " + raw
        );
    }

    double percent = ((Number) raw).doubleValue();
    if (!Double.isFinite(percent) || percent < 0 || percent > 50) {
        throw new AssertionError(
            "discountPercent out of [0,50]: " + percent
        );
    }
}
~~~

For values requiring high precision such as money, use `BigDecimal` instead of `double` arithmetic. Assertion messages should state **which field failed**, **the actual value**, and **which rule was violated**.

## 14. Common Mistakes When Wiring Commands and Base Tests

| Symptom | Possible Cause | How to Diagnose |
|---|---|---|
| Generated test cannot find `assertValidDiscountPercent` | Wrong `baseClassForTests`, package, method name, or visibility | Inspect generated class and base class |
| Type compile error calling method | Method parameter too specific; JSONPath passes different type | Inspect generated call; accept `Object` and check type inside |
| Test stays green when producer returns 75 | Matcher not generated/executed or helper did not throw | Inspect generated source, run mutation test |
| Cryptic `NullPointerException` on null | Helper operates before checking null/type | Assert type first and include message |
| Stub Runner does not call helper | Stub only simulates response; helper lives in producer test | Write assertions in consumer test if needed |
| Passes locally but fails in CI | Different JDK, plugin, test dependency, or context | Align toolchain, inspect dependency tree |
| Flaky due to network or clock | Impure helper depending on external state | Remove I/O; use deterministic inputs |
| Build green but zero generated tests | Plugin did not find contracts or task did not run | Check generation logs and test reports |
| Contract changed yet CI runs old helper | Stale test sources/build cache | Run clean build and check fresh sources/artifacts |
| Limits loosened without catching broken consumer | Changed Java helper to overly broad rule | Review helper as part of contract, run consumer compatibility tests |

Follow the investigation path: **contract → generated test → base class → JSONPath value → assertion → stub/consumer**.

## 15. Organizing the Base Test When Rules Grow

As the number of custom assertions grows, keep the base test as the wiring point and move rules into dedicated helper classes:

~~~text
src/test/java/com/example/promotion/
├── ContractTestBase.java
└── assertions/
    ├── PromotionAssertions.java
    ├── MoneyAssertions.java
    └── AllocationAssertions.java
~~~

Example base-class method delegating to a dedicated helper:

~~~java
private final PromotionAssertions checks = new PromotionAssertions();

public void assertValidDiscountPercent(Object actual) {
    checks.assertValidDiscountPercent(actual);
}
~~~

The base test must still retain the producer test environment setup shown in Section 7. With multiple contract groups, you can use SCC's base-class mapping mechanisms per project config; inspect generated tests to confirm they pick the right base class rather than guessing from folder names.

Guidelines to follow:

- Method names should reflect **business meaning** and stay stable across refactors.
- Avoid unnecessary I/O or side effects.
- Shared helpers should have clear scope and be easy to boundary-test.
- Renaming a method or changing its signature requires updating every contract calling it.
- Loosening bounds inside a helper can constitute an **API commitment change** even if the DSL file is unchanged.

## 16. Green Producer Does Not Mean Safe Consumer

Suppose the initial discount limit was `50`. The team wants to raise the maximum to `80` and updates `assertValidDiscountPercent` to allow `0..80`. Producer tests may stay green. Yet an older Checkout Service might cap UI display at 50 or assume values are always <= 50.

Therefore:

- **Producer verification:** generated tests confirm the producer's response satisfies the current rule in the Java helper.
- **Consumer verification:** actual consumer code must handle the new stub and relevant boundary values.
- **Stub artifact:** must be built from the **candidate contract/commit** and explicitly versioned so CI does not accidentally use an older version.
- **Migration:** when loosening or changing an impactful rule, update consumers or support an appropriate transition plan.

One stub with sample response `15` does not prove the consumer handles every value from 0 to 50; you can add boundary-value contract/stub cases or consumer tests with edge responses.

## 17. Integrating the Workflow into CI/CD

~~~mermaid
flowchart LR
    A["Change code, contract, or Java helper"] --> B["Generate producer contract tests"]
    B --> C["Compile generated tests + base class"]
    C --> D{"Producer tests pass?"}
    D -- "No" --> X["Block merge or release"]
    D -- "Yes" --> E["Package candidate stub"]
    E --> F["Consumer tests with Stub Runner"]
    F --> G{"Consumer tests pass?"}
    G -- "No" --> X
    G -- "Yes" --> H["Proceed to remaining release gates"]
~~~

In an SCC-configured project, reference Maven command:

~~~bash
./mvnw clean verify
~~~

For Gradle:

~~~bash
./gradlew clean test
~~~

On Windows, use the respective wrappers `mvnw.cmd` or `gradlew.bat`. Depending on the plugin, generated test locations and task names can differ; inspect the actual logs. Do not infer that matchers ran merely from exit code 0 if the build found no contracts.

In CI, retain traceability: contract name, Boot/Cloud/Contract versions, generated test report, assertion status, stub coordinates `group:artifact:version:stubs` with corresponding commit, and consumer test results. Checks must run against the **exact candidate stub**, never a cached prior version.

## 18. Hands-on Exercise

**Context:** Promotion Service exposes `GET /api/promotions/SKU-123`, and Checkout Service consumes the discount rate.

**Round 1 — Create the assertion:**

1. Write a Groovy or YAML contract with `discountPercent: 15`.
2. Attach `byCommand('assertValidDiscountPercent($it)')` or `by_command`.
3. Create a Java base class with a method checking `Number` in `[0,50]`.
4. Configure the plugin and run the generated producer test.
5. Open the generated test source and verify the method is called.

**Round 2 — Check boundaries and wrong types:**

1. Have the producer return 0 and 50; verify green.
2. Have it return 51, -1, and 75; verify red.
3. Have it return `"15"`; verify type failure.
4. Restore the implementation.

**Round 3 — Add an array:**

1. Add `allocations` for two warehouses.
2. Write `assertValidAllocations` checking unique warehouse codes and positive quantities.
3. Intentionally duplicate a `warehouseCode` and set a quantity to 0; the test must catch both.
4. Inspect actual JSONPath runtime types so the method makes no wrong assumptions.

**Round 4 — Consumer and CI:**

1. Package the candidate stub from the verified contract.
2. Have the consumer run Stub Runner against the exact candidate artifact.
3. Call via the real client and assert data and supported cases.
4. Gate the release on both producer and consumer results.

**Deliverables:** contract, base/helper code, generated test showing the assertion call, PASS/FAIL mutation report, candidate stub version, and consumer test results.

## 19. Pre-Merge Checklist

- [ ] Custom assertion serves a rule that standard matchers cannot express clearly.
- [ ] Matcher resides in **response** when verifying producer responses.
- [ ] JSONPath points to the right field in the sample body.
- [ ] Method name and `$it` expression match the active Groovy/YAML DSL.
- [ ] Generated test inherits the right base class and can access the method.
- [ ] Method verifies null/type/range and throws an assertion failure on invalid values.
- [ ] Intentional failure tests prove the assertion is active.
- [ ] Generated tests are created, compiled, and run against the real producer.
- [ ] Method avoids network, current clock time, database access, or side effects.
- [ ] Rule changes inside helpers are reviewed as contract changes.
- [ ] Stub Runner is used appropriately; consumer maintains its own assertions.
- [ ] CI uses exact candidate artifacts and logs version/commit metadata.

## 20. Self-Check Questions

**1. Why isn't `by_type` enough to verify a 0..50 discount?**

Because 75 is still a `Number`. A custom assertion is needed to enforce the **interval rule**.

**2. What is `$it` in `assertValidDiscountPercent($it)`?**

It is a placeholder representing the JSONPath-extracted value when SCC generates the producer test, not a controller variable.

**3. What is the risk of a method returning `false` without throwing?**

If the generated test simply invokes the method and ignores its return value, the test can still pass. Use assertions or throw `AssertionError`.

**4. Why must the base class be configured in the plugin?**

So generated tests can inherit or access assertion methods alongside the producer test environment setup.

**5. Does Stub Runner execute the producer's Java methods?**

No. Custom assertions in response matchers verify the producer. Consumer tests must verify their own handling of sample responses.

**6. If you loosen the helper limit from 50 to 80, is that a contract change?**

Likely yes. Even though the DSL didn't change, the response range accepted by producer verification changed. Evaluate the consumer and test with candidate stubs.

## 21. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests, and Stub Runner.
- [Spring Cloud Contract – Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matchers, custom commands, and `$it`.
- [Spring Cloud Contract – YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): `by_command` structure in YAML.
- [Spring Cloud Contract – HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): describing requests and responses.
- [AssertJ](https://assertj.github.io/doc/): writing clear assertions, failure messages, and comparisons.

**Version note:** DSL names, how generated tests invoke methods, and test mode settings can depend on the Spring Cloud Contract version. Consult the documentation for your chosen plugin version and inspect the actual generated source.

---

**Key takeaway:** The contract specifies **JSONPath + byCommand**, the base test provides the **failing Java assertion**, and the generated producer test enforces the rule on the **real response**. To evaluate consumer compatibility, continue by packaging the **candidate stub** and running consumer tests via Stub Runner in CI.
