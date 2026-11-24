# Maintenance Cost and Identifying Low-Value Tests

Automated testing is an investment: we spend time writing and maintaining tests to catch regressions before users encounter bugs. Yet a “green” test does not automatically create meaningful confidence. If it merely confirms mocked return values, depends on internal helper names, or fails intermittently, maintenance costs can outweigh its benefits.

In Spring Boot, those costs also include booting `ApplicationContext`, database migrations, launching containers, waiting on network calls, cleaning up data, and investigating CI failures. **A strong testing strategy maximizes meaningful defect detection relative to maintenance cost**, while preserving solid evidence that critical contracts hold.

After this lesson, you will be able to: categorize a test's costs; spot signs of low-value tests; distinguish redundant tests from complementary tests across levels; choose unit, slice, or integration tests by risk; improve brittle tests; and establish an evidence-based test suite review process.

## 1. Tests Have Value When They Protect a Clear Contract or Risk

A **behavioral contract** is what callers of a feature have a right to expect. Callers may be REST API clients, public service method callers, database consumers, message subscribers, or external services.

Observable behaviors include:

- Return values and boundary cases: money, limits, state.
- Promised errors: service exception types, HTTP status codes, and public API error codes.
- Data changes: persisted records, rolled-back transactions, no data loss.
- Side effects: emitted events, payment requests, or emails sent through an outbound port.
- Permissions and security: whether an actor is allowed or denied an action.

Conversely, private method names, mapper invocation counts, loop vs. stream choices, and temporary object instantiation order are usually **implementation details**. If the implementation changes while observable behavior stays right, contract-protecting tests should continue to pass.

Ask two questions before keeping or adding a test:

1. **What real defect would turn this test red?** For example, miscalculating the fee right at the free-shipping threshold, returning HTTP 500 instead of 400, or charging twice.
2. **What valid refactor would turn this test red?** If extracting a helper, renaming an internal class, or swapping adapters breaks the test, it may be coupled to structure rather than behavior.

Not every contract is pure business behavior. If requirements specify idempotency, maximum query counts, atomicity, or ordering of two events, those technical properties are worth testing too.

## 2. Categories of Maintenance Cost

| Cost Category | Spring Boot Examples | Impact |
|---|---|---|
| Writing and understanding | Building fixtures, complex mock setups, vague test names | Slows reviews and onboarding |
| Execution | Booting context, Testcontainers, database migrations, HTTP/I/O | Slow CI feedback; tests run less often |
| Updating with source changes | Adding internal fields breaks snapshots; changing constructors or helpers breaks `verify` | Valid refactors force widespread test edits |
| Environment stability | Shared data, timeouts, `Thread.sleep`, clocks, public APIs | Flaky tests requiring reruns and investigation |
| Diagnosis | Assertions saying only “expected true”; noisy logs or hard-to-trace fixtures | Unclear whether defect is in product, test, or infra |
| Infrastructure upkeep | Docker, auxiliary services, credentials, CI config, database seeds | Higher operational effort and external dependencies |

You can think qualitatively as:

```text
Test value ≈ risk protected
             × regression detection power
             × signal reliability

Lifecycle cost ≈ authoring + repeated runs + updates + investigation + infra
```

This is a mental model, **not an exact scoring formula**: risk and opportunity cost cannot be reduced to a single number. An integration test taking several minutes that guards payments or transaction rollbacks can be well worth keeping; a millisecond unit test checking a default getter may hold little value.

Illustrative example: a test group adding 5 minutes per CI run across 30 runs/day adds 150 job-minutes/day. That is not necessarily 150 human wait minutes since jobs can run in parallel. However, if one intermittent failure costs a developer 20 minutes to investigate, human cost can easily exceed machine cost.

## 3. Signs a Test May Be Low Value

Use the table below as **signals to investigate**, not an automatic deletion rule.

| Signal | Why Signal Is Weak | Valid Exceptions |
|---|---|---|
| Runs a method and exits with no assertions or side-effect checks | Can pass even when behavior is broken | Deliberate smoke tests verifying startup succeeds |
| Mocks the exact object under test | Asserts `thenReturn` value instead of running real logic | Mocking dependencies outside the tested boundary makes sense |
| `verify` on every internal call, mapper/helper count, or private call order | Structural refactors break tests despite right outputs | Charge count, event emission, or query limits are real requirements |
| Near-identical tests differing only in name, with same data/branch/assertion | Inflates test count without catching new defects | Two test levels may protect two different contracts |
| `@SpringBootTest` used just to check pure math | Expensive context startup with no extra signal | Specific flows needing wiring, transaction, or config proof |
| Asserting raw JSON snapshots, debug logs, or internal exception messages | Compatible changes break tests | Schemas, audit logs, or messages are part of the public contract |
| Tests using `sleep`, wall-clock time, live networks, or test ordering | Prone to flakiness; fails to reflect stable product bugs | Time logic can be contractual using a controllable clock |
| Testing standard uncustomized framework behavior | Tests JUnit, Java, or Spring rather than product code | Custom binders, converters, or security config still need tests |
| Requires constant edits even when requirements did not change | Coupled to concrete DTOs/fixtures/internals | When the real contract changes, tests should update |
| Coverage rises while assertions remain unrelated | Executing lines does not prove logic is right | Coverage remains helpful for finding unexecuted paths |

**Example `contextLoads()`:** A single test verifying the application boots cleanly can catch circular bean dependencies, missing properties, or auto-configuration failures. It has value as a smoke test. Copying dozens of tests booting identical contexts without verifying new contracts adds redundant overhead. Review context caching, per-test configuration, and each variant's purpose before merging them.

**Example repository:** `when(repository.findById(id)).thenReturn(...)` followed by asserting the mocked result does not verify JPA queries, entity mappings, constraints, or real transactions. If SQL/JPA is the target, test against a database at the proper level.

## 4. Java 17+ Example — A Very Fast Test That Only Tests Mockito

Assume a Spring Boot module with shipping rules:

- Standard orders under `200.00`: fee is `15.00`.
- Standard orders of `200.00` or more: free shipping.
- Express shipping: fee is `30.00` for any valid subtotal.
- Negative or `null` `subtotal` is invalid.
- Returned fee has two decimal places.

**`src/main/java/com/example/shipping/ShippingFeeService.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class ShippingFeeService {
    private static final BigDecimal THRESHOLD = new BigDecimal("200.00");
    private static final BigDecimal STANDARD = new BigDecimal("15.00");
    private static final BigDecimal EXPRESS = new BigDecimal("30.00");

    public BigDecimal quote(BigDecimal subtotal, boolean express) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }
        if (express) {
            return EXPRESS;
        }
        return subtotal.compareTo(THRESHOLD) >= 0
                ? new BigDecimal("0.00")
                : STANDARD;
    }
}
```

**Low-value test example** (counterexample—do not use this to protect logic):

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ShippingFeeLowValueTest {
    @Test
    void returnsWhatTheMockWasToldToReturn() {
        ShippingFeeService service = mock(ShippingFeeService.class);
        BigDecimal subtotal = new BigDecimal("200.00");
        when(service.quote(subtotal, false))
                .thenReturn(new BigDecimal("0.00"));

        BigDecimal actual = service.quote(subtotal, false);

        assertThat(actual).isEqualByComparingTo(new BigDecimal("0.00"));
    }
}
```

All logic inside `ShippingFeeService.quote` is bypassed. Even if production code changed so orders of 200.00 charged 15.00, this mock test would stay green. The assertion proves nothing about the “free at 200.00+” rule.

Replace it by **testing the real service directly** with meaningful scenarios.

**`src/test/java/com/example/shipping/ShippingFeeServiceTest.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingFeeServiceTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @ParameterizedTest
    @CsvSource({
        "0.00, false, 15.00",
        "199.99, false, 15.00",
        "200.00, false, 0.00",
        "200.01, false, 0.00",
        "100.00, true, 30.00",
        "500.00, true, 30.00"
    })
    void calculatesFeeAccordingToPolicy(
            String subtotal, boolean express, String expectedFee) {
        BigDecimal actual = service.quote(new BigDecimal(subtotal), express);

        assertThat(actual).isEqualByComparingTo(new BigDecimal(expectedFee));
        assertThat(actual.scale()).isEqualTo(2);
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() -> service.quote(new BigDecimal("-0.01"), false))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNullSubtotal() {
        assertThatThrownBy(() -> service.quote(null, true))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Why is this better?** The test runs real logic, covers boundary values 199.99/200.00/200.01, express shipping, and invalid inputs. If a developer confuses `>=` with `>`, the at-threshold case catches it. If the `if` structure changes or helpers are extracted without changing outcomes, the tests still pass.

`@Service` does not require `@SpringBootTest`; we can instantiate the plain Java object to test the algorithm. `BigDecimal.compareTo` compares numeric value, and `isEqualByComparingTo` applies those semantics in AssertJ. Asserting `scale()==2` is appropriate only because **the specification explicitly required** two decimal places; omit it if scale is not part of the contract.

The opposite mistake is equally common: testing every private method indirectly via reflection or `spy`. Instead of freezing internal method breakdowns, build input–output tables against product rules and run the entire suite after refactors.

## 5. Web Slices Protect the HTTP Contract Without Fully Duplicating Unit Tests

The unit tests above **do not** prove HTTP request binding, JSON formatting, or error mapping to 400. A web test adds regression protection at that boundary.

**`src/main/java/com/example/shipping/ShippingController.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/shipping")
public class ShippingController {
    private final ShippingFeeService service;

    public ShippingController(ShippingFeeService service) {
        this.service = service;
    }

    @GetMapping
    public ShippingResponse quote(
            @RequestParam BigDecimal subtotal,
            @RequestParam(defaultValue = "false") boolean express) {
        return new ShippingResponse(service.quote(subtotal, express));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse invalidSubtotal(IllegalArgumentException ignored) {
        return new ErrorResponse("INVALID_SUBTOTAL");
    }

    public record ShippingResponse(BigDecimal fee) {}
    public record ErrorResponse(String code) {}
}
```

**`src/test/java/com/example/shipping/ShippingControllerWebTest.java`**

```java
package com.example.shipping;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ShippingController.class)
@Import(ShippingFeeService.class)
class ShippingControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Test
    void exposesFeeViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "200.00")
                .param("express", "false"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.fee").value(0.0));
    }

    @Test
    void rejectsNegativeSubtotalViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "-0.01"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_SUBTOTAL"));
    }

    @Test
    void rejectsNonNumericSubtotalViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "abc"))
            .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` builds an MVC-only context; `@Import` brings in the small real service. Assertions protect status codes, JSON fields, and HTTP error mapping. This verifies a **different contract** from unit tests, even when both pass `subtotal=200.00`.

The example assumes a Spring Boot project with `@SpringBootApplication` in an appropriate root package, MVC enabled, and no extra Spring Security restrictions. If security is active, configure authentication/authorization in the test to match the real API rather than stripping filters just to make tests pass.

A web test that only runs `verify(service).quote(...)` without inspecting the HTTP response becomes a structural controller test. Verify what the client sees. Conversely, avoid full response snapshots containing fields outside the contract; adding a compatible field is not necessarily a regression.

## 6. When `verify` Is Genuinely a High-Value Test

Calling a dependency can be a **required side effect**. For example, a registration use case must request sending a verification email. Mocking the mail port and verifying the outbound message is sensible because unit tests should not send real emails.

**Two self-contained illustrative snippets:**

```java
package com.example.shipping;

interface VerificationMailPort {
    void send(String email, String token);
}

final class RegistrationNotifier {
    private final VerificationMailPort mail;

    RegistrationNotifier(VerificationMailPort mail) {
        this.mail = mail;
    }

    void notifyUser(String email, String token) {
        mail.send(email, token);
    }
}
```

```java
package com.example.shipping;

import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class RegistrationNotifierTest {
    @Test
    void requestsVerificationEmail() {
        VerificationMailPort mail = mock(VerificationMailPort.class);
        RegistrationNotifier notifier = new RegistrationNotifier(mail);

        notifier.notifyUser("mai@example.com", "token-123");

        verify(mail).send("mai@example.com", "token-123");
    }
}
```

Here `verify(mail).send(...)` checks an **outbound port**. If duplicate emails must be prevented by requirement, verifying `times(1)` can be a high-value assertion. Conversely, verifying `mapper.toDto` or internal helper call counts can fail on refactors even when user-facing behavior stays unchanged.

Keep evidence levels clear: the unit test above proves the application **requested sending through the port**; it does not prove the real email provider accepted or delivered the message. Adapter contracts, retries, or real delivery require dedicated integration tests when those risks matter.

## 7. Flaky Tests Drive Up Cost and Erode Trust

**Flaky** means the same code and inputs can randomly pass or fail. This trains teams to blindly rerun CI and eventually ignore real failures.

Common flakiness sources:

| Source of Instability | Symptom | Fix |
|---|---|---|
| `Thread.sleep(500)` waiting on async work | Occasional timeouts on slower CI runners | Wait on an observable condition/signal with a clear deadline |
| `Instant.now()` and host timezone | Failures near midnight or boundary timestamps | Inject `Clock`, fix instant and timezone |
| Shared database records | Parallel runs collide on IDs; order affects results | Dedicated fixtures, proper rollback/cleanup/isolation |
| Calling public external APIs | Network errors, rate limits, service downtime | Controlled fake server or test adapter |
| Unseeded randomness | Cannot reproduce failing inputs | Fixed seed or log seed alongside failure data |
| Shifting config/environment | Unstable context cache, port collisions | Isolate config, ports, and resources per test |

The snippet below checks voucher validity without waiting on a real clock:

**`src/main/java/com/example/shipping/VoucherWindow.java`**

```java
package com.example.shipping;

import java.time.Clock;
import java.time.Instant;

public final class VoucherWindow {
    private final Clock clock;

    public VoucherWindow(Clock clock) {
        this.clock = clock;
    }

    public boolean accepts(Instant expiresAt) {
        return Instant.now(clock).isBefore(expiresAt);
    }
}
```

**`src/test/java/com/example/shipping/VoucherWindowTest.java`**

```java
package com.example.shipping;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class VoucherWindowTest {
    @Test
    void checksBeforeAtAndAfterExpiry() {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");
        Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
        VoucherWindow policy = new VoucherWindow(fixedClock);

        assertThat(policy.accepts(now.minusSeconds(1))).isFalse();
        assertThat(policy.accepts(now)).isFalse();
        assertThat(policy.accepts(now.plusSeconds(1))).isTrue();
    }
}
```

The contract here is: **a voucher is valid only when the current instant precedes expiration**. The test checks all three boundary points without depending on system time.

For async flows, use `CountDownLatch`, acknowledgements, or bounded condition-waiting utilities, then assert results. For databases, manage transactions and cleanup explicitly. A CI retry mechanism can reduce transient disruption once root cause is understood, but must never become a permanent bandage hiding nondeterminism.

## 8. Choosing the Right Test Level to Cut Unnecessary Cost

| Level | Best-Fit Target | When Is This Level Insufficient? |
|---|---|---|
| Unit (JUnit 5, AssertJ) | Calculations, validation, business decisions, pure exception handling | Does not prove Spring MVC, JPA mappings, or real transactions |
| MVC slice (`@WebMvcTest`) | Routing, binding, JSON, controller advice, HTTP-boundary security | Does not prove end-to-end DB or out-of-slice beans |
| JPA slice (`@DataJpaTest`) | Queries, entity mappings, constraints on a suitable database | Does not prove APIs or multi-service workflows |
| Integration (`@SpringBootTest`) | Bean wiring, configuration, transactions, adapter integration | Too slow if used for every small calculation |
| End-to-end | Critical system journeys and infrastructure links | High setup and diagnosis cost; unsuitable for covering all logic branches |

**The minimum level that observes the contract** is usually the best choice. Keep bulk calculation cases in fast unit tests; use slices to test MVC/JPA; use targeted integration tests for transactions, configuration, and real integrations. Never replace persistence tests with a mocked repository and claim real SQL works.

In Spring Boot, you can reduce execution overhead by:

1. Keeping pure logic separated from I/O for direct unit testing.
2. Using `@WebMvcTest` and `@DataJpaTest` when only a slice is needed.
3. Leveraging Spring Test's `ApplicationContext` caching via consistent test configurations; use `@DirtiesContext` only when a test genuinely mutates context state so it cannot be reused.
4. Building small, business-named fixtures instead of seeding an entire database graph for one simple case.
5. Isolating databases, ports, topics, mutable state, and external dependencies.
6. Keeping necessary integration tests for risks that mock-based unit tests cannot catch.

Two tests both using `200.00` are not necessarily duplicates: the unit test verifies the free-shipping threshold, the web test verifies query binding and JSON, and the integration test verifies transaction persistence. Judge by **which defect each test catches**, not input similarity alone.

## 9. Measuring Evidence via CI and Change History

Never judge “low value” solely by test count, coverage, or runtime. Track signals:

| Observation | Data Sources | What to Analyze |
|---|---|---|
| Runtime per test/group | Gradle test reports, JUnit XML, CI stages | Slow due to logic, context startup, DB, or containers? |
| Flaky failure/rerun rate | CI history across commits and environments | Product bug, flaky test, or infra failure? |
| Tests requiring edits after refactors | PR diffs, commit history, review comments | Coupled to implementation, or did the contract change? |
| Production bugs slipping past suite | Incidents, bug reports, regressions | Which critical contract lacked verification? |
| Diagnostic clarity | Stack traces, assertion messages, fixtures, logs | Does a test failure point usefully to the cause? |
| Exclusive risk protection | Test–contract–layer mapping | Would deleting this test leave an unprotected gap? |

`JaCoCo` and coverage metrics show which code paths ran; **they do not guarantee assertions catch wrong behavior**. Mutation testing tools like PIT deliberately alter expressions/branches to see if tests catch faulty variants. Use it diagnostically to expose weak assertions—never treat mutation score as a complete measure of business value.

Illustrative evaluation matrix:

| Test | Risk Protected | Cost and Signal | Suggested Decision |
|---|---|---|---|
| Mock `ShippingFeeService` returning 0.00 then asserting 0.00 | Runs no business logic | Very fast but useless | **Replace** with real unit test |
| `quotesFeeAtThreshold` | Miscalculating exact free threshold | Fast, deterministic, boundary-focused | **Keep** |
| `shippingApiReturns400` | Broken HTTP contract | Moderate slice cost, clear signal | **Keep** |
| 8 `contextLoads` with identical context | Checks identical startup | Redundant, pays context cost | **Review and consolidate** if truly identical contracts |
| `orderPaymentRollsBackOnFailure` | Loss of transaction atomicity | Slower, but failure impact is severe | **Keep**, optimize setup |
| `sleep`-based async test | Event completion | Flaky, poor diagnosis | **Rewrite** wait mechanism and assertions |

An “expensive” test is not automatically low value. The right call depends on **defect severity**, defect-catching power, complementarity with other tests, and true maintenance cost.

## 10. Process for Handling Low-Value Tests

**Step 1 — Map requirements and risks.** For a module, list business rules, API contracts, permissions, promised transactions/atomicity, and critical integrations. Record which test protects each contract.

**Step 2 — Read the test alongside its intent.** Identify Given/When/Then and assertions. Ask: “If correct code becomes buggy, does this test fail?” and “If code undergoes a valid refactor, does this test pass?” Never rely solely on test names or green status.

**Step 3 — Measure cost with root causes.** Inspect Gradle/CI reports, flakiness history, and PRs constantly touching tests; distinguish context startup, I/O, fixtures, mock setup, and investigation overhead. Never assume every slow test is useless.

**Step 4 — Pick one of four actions:**

- **Keep** tests protecting critical contracts with reliable signals; optimize fixtures/infra if slow.
- **Rewrite** tests with sound intent that mock the wrong target, assert internals, rely on wall-clock/network, or use rigid fixtures.
- **Consolidate** tests at the same layer covering the same contract and variant without adding defect detection; preserve cases via clear naming or parameterization.
- **Delete** tests protecting no meaningful behavior **after** verifying remaining contracts are covered or any risk is deliberately accepted.

**Step 5 — Verify after changes.** Run related tests and a sufficiently broad suite; compare runtime, stability, and failure message clarity. Confirm plausible business bugs fail the tests while valid refactors do not trigger false failures.

For instance, merging multiple fee cases into one `@ParameterizedTest` improves clarity and cuts duplication. Yet never delete a web test checking HTTP 400 just because a service test checks `IllegalArgumentException`: those are two separate contracts.

## 11. Running the Examples and Checking Output

In a Spring Boot 3.x project using Gradle and Java 17+, the examples require `spring-boot-starter-web` for the controller and `spring-boot-starter-test` for JUnit 5, AssertJ, Mockito, and MockMvc. Do not add duplicates if the module already declares them.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Place files in matching packages and directories as shown. Run in an environment with Gradle Wrapper and valid Spring Boot configuration:

```bash
./gradlew test --tests com.example.shipping.ShippingFeeServiceTest --tests com.example.shipping.ShippingControllerWebTest --tests com.example.shipping.RegistrationNotifierTest --tests com.example.shipping.VoucherWindowTest
```

On Windows, use `.\gradlew.bat`. In multi-project builds, replace `test` with the module task, such as `:some-module:test` when that module exists in the real project. Default test reports typically reside in `build/reports/tests/test/index.html` and `build/test-results/test/` within the matching build directory.

The sample tests are designed to pass when all files are in place, Spring Boot bootstrap is discoverable from the test package, and no additional security configuration blocks requests. When all tests pass, Gradle is expected to print `BUILD SUCCESSFUL`. This is the **expected outcome based on the sample code**, not a claim of execution in a specific repository. JUnit tests emit no fixed application stdout.

Specifying `--tests` runs **only the selected classes**; to verify the full module, run the complete suite. After rewriting or consolidating tests, compare CI metrics under equivalent conditions, paying attention to failure diagnostic quality.

## 12. Common Mistakes

**“More tests always mean more safety.”** Quantity says nothing about which contracts are protected. One boundary-test table with clear assertions beats many duplicate tests using identical inputs.

**“Passing tests mean the logic is right.”** A mock-only test can pass while real logic is badly broken. Verify the real subject ran and critical outputs were checked.

**“If a refactor turns a test red, the refactor is wrong.”** The test might simply be coupled to a helper or non-contractual snapshot. Check the contract before concluding. If the contract genuinely changed, a red test is right.

**“100% coverage is enough.”** Coverage tracks executed lines, not assertion quality or defect detection. Boundaries, error paths, and side effects must still be chosen by risk.

**“Slow tests are not worth keeping.”** Rollback, authorization, or payment integration tests can be slower yet hugely valuable. Optimize setup or test level rather than dropping requirements.

**“Delete flaky tests so CI stays green.”** A flaky test may guard a critical feature. Fix the source of nondeterminism; blind retries can mask real defects.

**“Use `@SpringBootTest` for everything to match production.”** Unit tests for pure math need no context. Conversely, replacing all persistence/transaction tests with mocks fails to prove real integration behavior.

## 13. Exercise and Checklist

Scenario: the team changes `ShippingFeeService` from `if` statements to a `FeePolicy` strategy. For subtotals `199.99`, `200.00`, and express delivery, outputs stay identical. The API still returns `{"fee":0.00}` above threshold and HTTP 400 for negative numbers.

1. Which tests **must stay green**? Boundary unit tests and HTTP contract tests.
2. Which tests might **turn red needlessly**? Tests running `verify` on old helpers, mapper methods, or internal step order.
3. If the new code charges 15.00 at exact 200.00, which test catches it? The threshold unit test (and other layers if they include that case).
4. If the API returns 500 instead of 400 for negative inputs, which test catches it? The web slice test.
5. If a transaction test is slow yet catches lost data after failed payments, should it be deleted for runtime? No; keep that protection and optimize how it runs if appropriate.

Checklist before accepting a test:

- [ ] Clearly states the contract or risk the test protects.
- [ ] Assertions verify real outputs, errors, state changes, or side effects.
- [ ] The test fails when critical behavior breaks, rather than only on structural edits.
- [ ] Does not mock the logic under test; mocks dependencies at sensible boundaries.
- [ ] Does not lock down private helpers, mapper invocation counts, or non-contractual logs.
- [ ] Includes necessary boundary and error cases without duplicating existing tests' intent.
- [ ] Picks the right unit/slice/integration/e2e level.
- [ ] Controls data, clocks, networks, and shared state.
- [ ] Runtime, flakiness, and failure investigation cost match the protected risk.
- [ ] When editing, merging, or deleting tests, the remaining suite still covers critical contracts.

**Key takeaway:** A test's value lies in **how quickly and reliably it catches important regressions**, not in test count or fixture complexity. Prioritize meaningful behavioral tests that survive valid refactors, and pick the right Spring Boot test layers to keep a suite useful long term.