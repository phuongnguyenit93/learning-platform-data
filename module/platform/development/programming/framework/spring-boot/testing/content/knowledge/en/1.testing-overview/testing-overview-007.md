# Testing Observable Behavior and Avoiding Coupling to Implementation Details

In Spring Boot, testing is valuable when it tells you **whether the system keeps its promise to its users or callers**. A test can be “green” yet have little value if it only confirms class A called method B; conversely, a good test still passes when you swap an algorithm, extract a class, or optimize a query as long as the result users receive does not change.

**After this lesson, you can:** define the observable boundary of a feature; turn requirements into test cases covering inputs–outputs–errors–side effects; write unit tests and web slice tests that protect behavior; know when to verify interactions with dependencies; and spot assertions that break tests merely because of refactoring.

## 1. What Is “Observable Behavior”?

It is what a consumer of a feature can perceive or is entitled to rely on under the **contract** (behavioral contract). The “consumer” may be an HTTP API client, a class calling a public method, an event consumer, or an external system.

| Testing Boundary | Behavior Worth Verifying | Details Usually Not Worth Fixing |
|---|---|---|
| HTTP API | Status, JSON structure and semantics, validation, access permissions, contracted headers | Controller method names, how many times the controller calls a service, internal DTO mappers |
| Public service | Return value, specified error types, modified state, requests sent through outbound ports | Private method names, loops vs. streams, number of temporary objects |
| Persistence | Saved/read data, business constraints, atomicity when required | Generated SQL, helper names, repository call count unless there is a performance contract |
| Messaging/remote API | Events or requests that must actually be sent, payload content, idempotency keys when specified | How payloads are built, adapter class names, intermediate mapping steps |

For example: the requirement “members get a 10% discount, total rounded to two decimal places” creates a contract about **the final amount**. It does not require code to have an `applyDiscount()` method, multiply directly, or look up a rate table. A test tied to that internal method will falsely fail on valid refactoring.

**Key distinction:** “Observable” does not necessarily mean only `return`. An order being persisted, an email being requested to send, a transaction being rejected, or an event being emitted are also meaningful outcomes. You can verify interactions at **outbound ports** when the interaction itself is the business outcome.

## 2. Going From Requirements to Test Cases

Before picking `@SpringBootTest` or Mockito, write the contract in concrete sentences:

1. **Given:** what are the initial state and valid/invalid inputs?
2. **When:** which public operation or request is executed?
3. **Then:** which outcomes must be observable? Should errors, persisted data, or outbound messages also be checked?
4. **Out of contract:** which implementation changes should be allowed without breaking the test?

Example for a quoting feature:

| Scenario | Input | Expected Outcome |
|---|---|---|
| Regular customer | `subtotal=100.00`, `member=false` | `100.00` |
| Member | `subtotal=100.00`, `member=true` | `90.00` |
| Rounding | `subtotal=1.05`, `member=true` | `0.95`, HALF_UP rule |
| Valid boundary value | `subtotal=0.00` | `0.00` |
| Invalid business data | Negative subtotal or `null` at service | `IllegalArgumentException` |
| Wrong HTTP type | `subtotal=abc` | HTTP `400 Bad Request` |

Choose cases that represent **distinct behavioral groups**: normal, boundary, decision branches, errors, and critical side effects. Do not write dozens of tests just because the code has dozens of internal branches; nor should you only test the happy path and skip errors customers actually encounter.

Test names should state clearly what must be true, such as `memberReceivesTenPercentDiscount` or `rejectsNegativeSubtotal`, rather than `callsHelperMethod`. Every test should have a clear verifiable outcome; a test that merely runs a method without asserting or verifying anything observable creates a false sense of safety.

## 3. Example 1 — Unit Testing Business Behavior Without Starting Spring

Suppose a Spring Boot application has the two dependencies `spring-boot-starter-web` and `spring-boot-starter-test`, using Java 17+. Put both files in package `com.example.testing`.

**`src/main/java/com/example/testing/QuoteService.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private static final BigDecimal MEMBER_FACTOR = new BigDecimal("0.90");

    public BigDecimal quote(BigDecimal subtotal, boolean member) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }

        BigDecimal factor = member ? MEMBER_FACTOR : BigDecimal.ONE;
        return subtotal.multiply(factor).setScale(2, RoundingMode.HALF_UP);
    }
}
```

**`src/test/java/com/example/testing/QuoteServiceTest.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class QuoteServiceTest {
    private final QuoteService service = new QuoteService();

    @ParameterizedTest
    @CsvSource({
        "100.00, false, 100.00",
        "100.00, true, 90.00",
        "19.99, true, 17.99",
        "1.05, true, 0.95",
        "0.00, true, 0.00"
    })
    void returnsContractedAmount(String input, boolean member, String expected) {
        BigDecimal actual = service.quote(new BigDecimal(input), member);

        assertThat(actual).isEqualByComparingTo(new BigDecimal(expected));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() -> service.quote(new BigDecimal("-1.00"), true))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNullSubtotal() {
        assertThatThrownBy(() -> service.quote(null, false))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Why is this a behavioral test?** Every assertion targets the amount or error type received by the service's caller. There is no `verify(service).someInternalMethod()`, no counting multiplications, and no reading private fields. If you change how the discount rate is represented while keeping the contract intact, the tests still pass. `isEqualByComparingTo` compares numeric values of `BigDecimal`; `BigDecimal.equals` also compares scale, so only use `equals` when scale itself is part of the contract.

This is a **pure unit test**: no `@SpringBootTest`, database, or HTTP server. The `@Service` annotation makes the class discoverable when running the app, yet does not force you to boot a Spring context when testing pure algorithms.

The **Arrange – Act – Assert** pattern is clear: prepare `BigDecimal`, invoke `quote`, then assert the value. For exceptions, the observed behavior is the exception thrown by the public method; if the error message wording is not yet contracted, check only the exception type and avoid locking in exact wording that may change.

## 4. Example 2 — Protecting the HTTP Contract with `@WebMvcTest`

When called over HTTP, the requirements differ from a service unit test: Spring MVC must bind query parameters, build a JSON response, and translate errors into appropriate HTTP statuses. We verify **request/response**, not which helpers the controller called.

**`src/main/java/com/example/testing/QuoteController.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping
    public QuoteResponse getQuote(
            @RequestParam BigDecimal subtotal,
            @RequestParam(defaultValue = "false") boolean member) {
        return new QuoteResponse(service.quote(subtotal, member));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError handleInvalidSubtotal(IllegalArgumentException error) {
        return new ApiError(error.getMessage());
    }

    public record QuoteResponse(BigDecimal total) {}
    public record ApiError(String message) {}
}
```

**`src/test/java/com/example/testing/QuoteControllerWebTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
@Import(QuoteService.class)
class QuoteControllerWebTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void exposesMemberQuoteThroughHttp() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "100.00")
                .param("member", "true"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.total").value(90.0));
    }

    @Test
    void mapsNegativeSubtotalToBadRequest() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "-1.00"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").isNotEmpty());
    }

    @Test
    void rejectsUnparsableSubtotal() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "abc"))
            .andExpect(status().isBadRequest());
    }
}
```

Here `@WebMvcTest` initializes the Spring MVC slice rather than the full application; `@Import(QuoteService.class)` supplies the simple real service to the controller. The test verifies routing, data binding, serialization, and HTTP error mapping. It does not lock tests to service invocation counts or Java method names. If the project enables Spring Security, configure authentication/CSRF according to the API contract; do not arbitrarily disable filters just to turn tests “green”.

Note the difference between the two errors: `subtotal=abc` fails to convert to `BigDecimal`, so Spring MVC typically responds with `400` right at binding; `subtotal=-1.00` parses fine yet violates a business rule, so the controller in this example has an `@ExceptionHandler` returning `400`. If an application has no corresponding business-error mapping, do not assume every `IllegalArgumentException` automatically becomes `400`.

This test suite protects HTTP properties explicitly stated in requirements. When the API must also guarantee access control, headers, error formats, pagination, or idempotency, cover those properties in dedicated tests. Avoid snapshotting the entire response when only certain fields are actually part of the contract: adding a valid JSON field should not break tests if clients still work properly.

## 5. When Is Mockito's `verify(...)` Reasonable?

An interaction **can itself be the side effect that needs protection**. For example, after a user completes registration, the application must request sending a welcome email. If the email sender is an outbound port of the system, verifying the send call makes sense because it is the use case's contract.

The following is a separate example; classes are in the same package, unrelated to `QuoteService`:

```java
package com.example.testing;

interface MailPort {
    void sendWelcome(String email);
}

final class WelcomeNotifier {
    private final MailPort mailPort;

    WelcomeNotifier(MailPort mailPort) {
        this.mailPort = mailPort;
    }

    void notifyRegistration(String email) {
        mailPort.sendWelcome(email);
    }
}
```

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class WelcomeNotifierTest {
    @Test
    void requestsWelcomeEmailForNewRegistrant() {
        MailPort mailPort = mock(MailPort.class);
        WelcomeNotifier notifier = new WelcomeNotifier(mailPort);

        notifier.notifyRegistration("an@example.com");

        verify(mailPort).sendWelcome("an@example.com");
    }
}
```

`verify` here checks the command sent through an outbound port, which is the outcome of the action. If business rules specify “do not send email when input is invalid”, verifying **no interaction** with the port on that branch is also meaningful. For real flows, you can use a fake/adapter recording requests, or an integration test with a simulated message broker when delivery capability needs proving.

Conversely, assertions like “controller called mapper twice”, “service called private helper before validator”, or “repository ran exactly three methods in exact order” usually couple to **how code is written**. Check call counts or order only when that is genuinely a requirement: e.g., never charging payment twice, a business-significant order of two events, or a query count limit being a defined performance goal.

**Rule for choosing mocks:** mock dependencies outside the test scope to deterministically create scenarios (remote API error, timeout, out of stock); keep the algorithm under test real. Always mocking the very method you want to test and asserting the mocked return value tests mock setup, not production logic.

## 6. Refactoring Must Not Turn Tests “Red” If the Contract Unchanged

A good test has **refactoring resilience**. Ask: “If today I switch from a loop to a stream, extract a helper, swap a storage adapter, or rename an internal method, while outputs and side effects remain correct, will the test still pass?”

| Fragile Test | More Resilient Verification |
|---|---|
| `verify(spy).calculateDiscount()` | Assert final total across multiple cases |
| Assert DTO by inspecting every internal field, including unpublished ones | Assert only fields that are actually part of the HTTP/API contract |
| `verify(repository, times(2)).findById(...)` because current code looks up twice | Assert business outcomes and persisted state; measure query count separately if there is a performance requirement |
| Assert exact exception message wording when no wording spec exists | Assert error type, HTTP status, or public error code; lock exact wording only when published |
| Rely on `Thread.sleep(500)`, machine clock, or test order | Inject `Clock`, fake schedulers, control data and independent state |
| Test reads `private` fields via reflection | Verify public behavior or side effects; extract genuine logic into a component with its own contract if needed |

For instance, `QuoteService` can be changed to read the percentage from configuration, use a pricing strategy, or split into multiple classes. As long as the input–output table still holds, business tests need no edits. Yet if requirements change from “10% off” to “15% off”, tests **must fail** until both contract and code are updated; that is a useful failure.

Do not misinterpret “avoid coupling to implementation” as “never test architecture”. Certain technical properties are also contracts when required: transactions must roll back atomically, sensitive data must not appear in HTTP responses, duplicate events must not be emitted, APIs must be idempotent, or query counts must stay below a threshold. In those cases, choose the appropriate measurement and test level to verify that exact property.

## 7. Keeping Tests Stable with Time, Data, and Environments

Tests depending on real time, randomness, or external networks easily fail sporadically. Behavior can still be tested without depending on when the test runs: inject `java.time.Clock` and fix the instant in tests. Example:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ExpiryPolicyTest {
    @Test
    void expiresExactlyAtDeadline() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        Clock clock = Clock.fixed(now, ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(clock);

        assertThat(policy.expired(now)).isTrue();
        assertThat(policy.expired(now.plusSeconds(1))).isFalse();
    }
}
```

Right at the deadline, the policy in this example considers it expired; one second before the deadline (i.e., deadline one second after `now`), it is still valid. The test expresses the **boundary rule**, without waiting for a real clock or depending on machine time zones.

Similarly, for UUID/random values you can inject a generator; for external HTTP you can use a fake server, WireMock, or a controllable adapter; for databases use independent fixture data and intentional rollback/cleanup. A test that only passes when run after another test indicates leaked state, not desired behavior.

## 8. Choosing the Right Test Level in Spring Boot

Not every behavior needs `@SpringBootTest`:

| Level | Use When Protecting | Suggested Tools |
|---|---|---|
| Unit | Algorithms, business branches, service validation | JUnit 5, AssertJ, Mockito at dependency boundaries |
| Web slice | Routing, binding, validation, JSON, status, controller advice, MVC security | `@WebMvcTest` + `MockMvc` |
| Persistence slice | JPA mapping, constraints, queries, transactions with an appropriate DB | `@DataJpaTest`; Testcontainers when realistic DB behavior is needed |
| Integration | Bean interactions, config, and real components in a flow | `@SpringBootTest`; `MockMvc` or HTTP client when needed |
| End-to-end | External journeys across connected systems | Integrated test environment with controlled data |

Use the **smallest level that still observes the contract you need to protect**. Fast unit tests for many variants; slice tests for Spring MVC/JPA; selective integration tests for paths spanning multiple components. Do not use `@SpringBootTest` for a pure calculation, nor use unit tests that completely mock the repository to conclude real JPA queries are right.

When testing errors, distinguish where an error originates from where it is mapped: a service may throw `IllegalArgumentException`; for the API to return `400`, an appropriate HTTP handler must exist. For security, `401`/`403`, authentication, and authorization are observable behaviors, so test allowed and denied scenarios according to the product contract.

## 9. Running the Examples and Understanding Results

In a Spring Boot module using Gradle/Groovy, ensure the corresponding dependencies exist (if the module already has them, do not declare duplicates):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the exact file/class/package names from the examples. Run from the Gradle project directory that has the `test` task (for multi-project builds, prepend the appropriate module task path):

```bash
./gradlew test --tests com.example.testing.QuoteServiceTest --tests com.example.testing.QuoteControllerWebTest --tests com.example.testing.WelcomeNotifierTest --tests com.example.testing.ExpiryPolicyTest
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`. Tests use JUnit 5; `spring-boot-starter-test` supplies AssertJ and Mockito. Expected outcome: all test methods pass; Gradle reports `BUILD SUCCESSFUL` when the project is configured properly and dependencies resolve. There is no fixed business stdout line, because the examples are JUnit tests rather than a `main()` application printing to the console. If the app enables Spring Security or custom web configuration, web slice tests need configuration matching the real API as noted in Section 4.

You can test refactoring resilience yourself: rewrite the calculation internals into a new helper while keeping the result identical, re-run tests, and confirm no test needs editing. Then intentionally change the factor to `0.80` without changing requirements: the test `100.00,true,90.00` must fail. That is the difference between **tests catching behavioral regressions** and **tests catching code style edits**.

## 10. Checklist Before Accepting a Test

- [ ] Test name expresses a business rule or public contract.
- [ ] Given/When/Then is clear; assertions verify observable outputs, errors, state, or side effects.
- [ ] Covers boundary values, invalid data, and meaningful branches; not just the happy path.
- [ ] Does not verify helpers, mapping counts, or internal call order unless part of the contract.
- [ ] External dependencies are mocked/faked; the logic being protected still runs for real.
- [ ] Test does not depend on wall-clock time, public networks, execution order, leftover data, or random logs.
- [ ] Test level is sufficient to observe what is claimed (unit, web slice, persistence, or integration).
- [ ] Safe refactoring leaves tests passing; broken behavior causes tests to fail with clear cause.

**Self-check question:** If a developer replaces the entire internals of a service while API responses, data state, errors, and contracted events stay identical, which tests should pass? Which tests would fail even though users see no change? Keep the first group as your primary safety net, and re-examine why the second group exists.

**Core message:** Good testing locks down **what the system must do** and leaves open **how the system does it**. That boundary lets tests catch regressions without blocking refactoring.