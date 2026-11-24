# Writing Regression Tests Before or Alongside Bug Fixes in Spring Boot

## 1. Why Must Bug Fixes Include Regression Tests?

A fixed bug can return during a later refactor, configuration change, library upgrade, or feature addition. A **regression test** captures the correct behavior using concrete inputs and assertions so future test runs catch if that behavior breaks again.

Suppose users discover that **a discount coupon is still accepted at its exact expiration timestamp**. A developer edits the condition in the service and sees the problem disappear. However, without keeping a test for the `now == expiresAt` case, a future logic edit can accidentally reintroduce the bug.

Writing a regression test before or during a bug fix achieves four outcomes:

1. **Reproduce the bug repeatably:** Turn symptoms from descriptions or logs into an executable check.
2. **Verify the fix works:** The test fails due to the faulty behavior before the fix and passes after the fix.
3. **Prevent old bugs from returning:** The regression test stays in the codebase and runs continuously in CI.
4. **Clarify the business contract:** Assertions document what the system must do in easily overlooked situations, especially boundary conditions and error paths.

This is an evidence-based bug-fixing practice, not a mandate that every team adopt full Test-Driven Development for all features. The key point is **proving the new test genuinely catches the reported bug and continues protecting the behavior after the fix**.

## 2. Identify the Exact Bug Before Writing the Test

Never use the currently buggy output as your expected value. Separate the facts clearly:

| Element | Example |
|---|---|
| Symptom | Coupon accepted at its exact expiration timestamp |
| Reproduction input/state | `now == expiresAt` |
| Current actual result | `canRedeem(...)` returns `true` |
| Correct result per contract | `canRedeem(...)` must return `false` |
| Suspected root-cause scope | Time comparison expression in the service |
| First appropriate test | JUnit unit test on expiration logic |
| Additional boundaries to consider | Controller, timezone, persistence, or Security if relevant to the bug |

Minimal bug-report evidence should state the version/commit, inputs, reproduction steps, actual result, expected result, and relevant environmental conditions (profile, timezone, database, permissions). Never put real tokens, passwords, or production customer data into test fixtures.

**Confirm the requirement before locking it down with a test.** In the example above, the rule is that the coupon is valid when `now < expiresAt`. If the real business rule actually allowed redemption at the exact expiration moment, that would be a different contract requiring a different test. A wrong regression test can lock a bug in place long term.

## 3. The RED → GREEN → REGRESSION Workflow

### Step 1. Reproduce with the Smallest Case

Pick the exact layer where the bug occurs: service logic, controller/validation, Spring context, repository/database, Security, or HTTP client. If the bug is a time comparison expression in a service, starting with a plain JUnit unit test is faster and easier to isolate than booting the full Spring context.

Reproducing via the UI or Postman is a helpful first step, but convert it into an automated test whenever possible. The test must contain clear inputs, actions, and assertions.

### Step 2. Write the Test for Correct Behavior and Run Before the Fix

Against the buggy version, the new test must fail (**RED**) **for the right reason**. For instance, the assertion reports expected `false` but actual `true` at the expiration threshold.

Distinguish these states:
- **Valid RED:** The test runs and the assertion catches the faulty behavior to be fixed.
- **Invalid RED:** The test fails to compile, misses a bean, fails to boot the database, or has a broken fixture; this is not yet evidence of catching the business bug.
- **GREEN from the start:** The test may not be hitting the buggy branch, may be running against already-fixed code, or may be in an environment that fails to reproduce the issue. Investigate before accepting it as a valid regression test.

If the test fails only intermittently, isolate the source of flakiness instead of claiming reproduction.

### Step 3. Fix the Root Cause and Re-run the Test

Modify production code to satisfy the confirmed contract. **Never relax expected values or delete assertions just to force the test green.** When the test is validly red before the fix and green afterward, the team has concrete evidence for that exact scenario.

Check the root cause carefully: the same faulty comparison might exist in multiple code paths. A superficial fix that satisfies one test without addressing the root cause can leave bugs behind.

### Step 4. Run Related Tests and CI

Once the new test is green, run other tests in the service/module and any affected integration tests. The CI pipeline should run the appropriate suite before merging; with branch protection enabled, failing tests block merges. Commit the new test alongside the fix and keep it to prevent future regressions.

## 4. Java 17+ Example: Reproducing and Fixing a Boundary Bug

### 4.1. Business Assumptions

In a Spring Boot application, a promotional code is redeemable only **before** expiration, never at or after expiration. The service exposes `canRedeem(Instant expiresAt)`. For deterministic time testing, the service receives `java.time.Clock` via constructor injection instead of calling an uncontrolled system clock directly.

Initially, the service contains a buggy check:

```java
return !Instant.now(clock).isAfter(expiresAt);
```

This expression is equivalent to `now <= expiresAt`. When `now` equals `expiresAt`, it returns `true`, whereas the contract requires `false`.

### 4.2. Write the Regression Test Before Fixing

File `src/test/java/com/example/testing/CouponValidityServiceTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CouponValidityServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-03-01T10:00:00Z");

    private final CouponValidityService service =
            new CouponValidityService(Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void acceptsCouponBeforeExpiry() {
        assertTrue(service.canRedeem(NOW.plusMillis(1)));
    }

    @Test
    void rejectsCouponAtExactExpiry() {
        assertFalse(service.canRedeem(NOW));
    }

    @Test
    void rejectsCouponAfterExpiry() {
        assertFalse(service.canRedeem(NOW.minusMillis(1)));
    }
}
```

Three tests guard all three sides of the boundary:
- **Before expiry:** `expiresAt` is one millisecond after `NOW`; result is `true`.
- **Exact expiry:** `expiresAt == NOW`; result is `false`.
- **After expiry:** `expiresAt` is one millisecond before `NOW`; result is `false`.

With the buggy `!now.isAfter(expiresAt)` implementation, `rejectsCouponAtExactExpiry` **fails** because actual `true` differs from expected `false`. The other two pass. This pinpoints the exact equality-at-threshold defect rather than merely reporting “a test failed.”

### 4.3. Fix the Implementation Without Weakening Assertions

File `src/main/java/com/example/testing/CouponValidityService.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
public class CouponValidityService {

    private final Clock clock;

    public CouponValidityService(Clock clock) {
        this.clock = clock;
    }

    public boolean canRedeem(Instant expiresAt) {
        return Instant.now(clock).isBefore(expiresAt);
    }
}
```

`isBefore(expiresAt)` evaluates to `true` if and only if the current instant is **strictly less than** the expiration instant. At or after expiration, it returns `false`.

The application must provide a `Clock` bean so Spring can instantiate the service. File `src/main/java/com/example/testing/TimeConfiguration.java`:

```java
package com.example.testing;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

The three classes above form a complete Java example in package `com.example.testing`. This assumes they live in a Java 17+ Spring Boot project with `spring-boot-starter-test`, covered by component scanning, following standard Maven/Gradle source layout. The unit test instantiates the service directly, requiring no Spring context. In production, the app uses `Clock.systemUTC()`, while tests use `Clock.fixed(...)` for deterministic, repeatable results without `Thread.sleep`.

### 4.4. Running the Tests

If the project uses the Gradle wrapper:

```bash
./gradlew test --tests "com.example.testing.CouponValidityServiceTest"
```

On Windows PowerShell: `.\gradlew.bat test --tests "com.example.testing.CouponValidityServiceTest"`.

If the project uses the Maven wrapper:

```bash
./mvnw -Dtest=CouponValidityServiceTest test
```

On Windows PowerShell: `.\mvnw.cmd -Dtest=CouponValidityServiceTest test`.

These commands assume JUnit Jupiter is configured (normally included with the test starter) and the corresponding wrapper is present. **Before the fix:** `rejectsCouponAtExactExpiry` must fail on its assertion. **After the fix:** all three cases must pass. Do not assume a fixed stdout snippet, since logs vary by Gradle/Maven version, plugins, and runner configuration; inspect the test report or actual run output.

Scope limitation of this example: the three unit tests protect the expiration rule. They do not prove that HTTP endpoints, serialization, databases, Security filters, or input timezone conversions work properly. If the actual bug lies at those boundaries, add appropriate tests.

## 5. What If the Test Is Written Alongside or After the Fix?

During an urgent incident or hotfix, a team may fix code and add the test in the same cycle. To keep the regression test trustworthy:

1. Document the exact bug inputs and expected result **before forgetting the reproduction conditions**.
2. Add a test for the failing scenario with controllable inputs and dependencies.
3. If safe and feasible, run the test against the unfixed revision in a separate branch or temporarily reintroduce the exact buggy logic in a test environment and revert afterward to verify the test turns red on the bug.
4. Run the test against the fixed code and confirm green; run related suites and CI.
5. Commit the test with the fix; state explicitly in the PR if the pre-fix red state **could not** be verified.

Never modify a live deployed system just to prove a test turns red; use branches and safe test environments. If you could not reproduce the old state, a passing post-fix test is still useful, though **it has not been proven to catch the original defect**. Be transparent about this limitation during review instead of claiming “regression test verified” without evidence.

A concise PR note might state: “Before fix, coupon was valid at `now == expiresAt`. Added `rejectsCouponAtExactExpiry` showing assertion failure on old logic; switched to `isBefore`; new test and related suite pass.” Only state steps you actually verified.

## 6. Choosing the Right Test Layer in Spring Boot

Not every bug should be guarded by a heavy `@SpringBootTest` loading the entire application. Start at the lowest boundary that reproduces the root cause, then add higher-level checks when needed.

| Defect Location | Priority Test | Behavior to Verify |
|---|---|---|
| Calculations, conditions, state rules in a service | JUnit 5 unit test, Mockito when isolating dependencies | Return values, exceptions, boundary branches |
| Controller, JSON, request validation, HTTP status | Web slice with `@WebMvcTest` and `MockMvc` | Mappings, response body, status, error messages |
| Bean injection, Spring profiles, configuration, service chain | `@SpringBootTest` or targeted integration test | Context startup and real component wiring |
| Repository, JPA mappings, SQL, transactions | `@DataJpaTest` or integration test with matching DB | Queries, constraints, persisted data, transactions |
| Authentication and authorization | Tests going through the real security filter chain | 401/403/200 per access contract |
| HTTP clients, message queues, external databases | Contract/integration tests with stubs or test infra | Payloads, timeouts, errors, retries, idempotency |
| End-to-end business workflow | End-to-end tests in a controlled environment | User-observable behavior |

For instance, if the bug is that an incomplete request returns 200 instead of 400 from the controller, testing the service directly bypasses validation and fails to protect the bug. Send the request through `MockMvc` or an HTTP test and assert status/body. Conversely, for `<` versus `<=`, a fast unit test suffices to guard the comparison; add an integration test if the API's time parsing/conversion path also carries risk.

Annotation notes:
- `@SpringBootTest` loads the application context, but by default **does not** start a real HTTP server. If you need a random-port server, configure `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT`.
- `@WebMvcTest` is an MVC slice and does not automatically load all application beans/services; provide collaborators or test beans compatible with your Spring Boot/Spring Framework version.
- With JPA, in-memory databases may process SQL differently than PostgreSQL/MySQL. Use Testcontainers or a production-like test database when bugs depend on real DB semantics.
- With Security, do not disable filters in tests when the bug involves authorization: doing so can yield green tests while the vulnerability remains.

## 7. Designing Durable Regression Tests

### 7.1. Assert Behavior, Avoid Locking Down Implementation

Tests should observe the contract: return values, responses, persisted state, emitted events, or exceptions. Avoid asserting internal helper invocation counts unless invocation count is a business requirement. Tests tightly coupled to internal structure break on valid refactors and lose signal value.

### 7.2. Test the Exact Boundaries Related to the Bug

A `>`/`>=` or `<`/`<=` defect is reliably blocked by **before – exact – after threshold** cases. For input validation bugs, test valid, invalid, and boundary values. For transaction bugs, check both success and mid-flight failure behavior. Add only cases that genuinely protect the contract.

### 7.3. Eliminate Sources of Flakiness

- For time: inject `Clock` and use fixed instants; never rely on wall-clock time.
- For async: wait on observable conditions with bounded timeouts instead of arbitrary sleeps.
- For databases: use isolated fixtures, control state, and understand test rollback/commit behavior.
- For networking: use controlled stubs where appropriate; integration tests should run against reproducible isolated environments.
- For concurrency: trigger controlled contention and assert data invariants; sequential tests never prove thread safety.
- For mocks: never mock the class containing the bug or hardcode desired outputs and claim production code was tested.

### 7.4. Clear Test Names and Failure Messages

A name like `rejectsCouponAtExactExpiry` communicates the situation and expected outcome. Assertions should pinpoint exact discrepancies. If a test requires setting up many unrelated dependencies, reconsider the scope and extract clear fixture factories. Avoid stuffing multiple unrelated behaviors into a single test just to minimize test case count.

## 8. Considering Extra Tests at Boundaries That Hide Bugs

**Timezone or temporal-type bugs:** Java `Instant` represents an absolute point in time; `LocalDateTime` carries no timezone. If a controller parses temporal inputs incorrectly, a unit test using `Instant` may still pass. Add tests where input conversion occurs per the API contract.

**Transaction bugs:** A service test with a mocked repository will not catch faulty transaction rollbacks. Verify persisted state after failure inside a real database environment. Beware that default test transaction rollback can hide commit-time issues.

**Concurrency bugs:** Two requests modifying the same order state or redeeming a single-use coupon simultaneously can trigger race conditions. Sequential tests rarely reproduce these; use multi-threaded tests or integration tests with proper constraints/isolation. Never assume an in-JVM lock solves multi-instance deployments.

**Environment-specific configuration bugs:** A test context running with the default profile does not prove other profiles work. When a bug depends on profiles, properties, databases, or conditional beans, include the relevant configuration in the regression test.

**HTTP and Security bugs:** If the bug involves wrong HTTP status codes or bypassed authorization, tests must traverse the real MVC/Security filter chain. Mocking away all security may prevent test setup friction but fails to verify authorization flaws.

## 9. Common Mistakes When Writing Regression Tests

| Mistake | Why It Is Dangerous | Fix |
|---|---|---|
| Running the test only on fixed code | Unknown whether the test actually catches the old bug | Verify RED on old logic when feasible |
| Changing expected values to match buggy output | Legitimizes the defect | Anchor expectations to business requirements |
| Checking only `contextLoads()` | Green startup does not prove behavior works | Add assertions for the failing path |
| Mocking the buggy component | Verifies the mock instead of real logic | Run the real implementation being fixed |
| Skipping boundary conditions | Passes normal cases while bug persists | Test near and directly at thresholds |
| Using real time, shared data, or live networks | Suite becomes unstable | Fix inputs and isolate dependencies |
| Running only the new test, skipping others | Fix may break adjacent functionality | Run related suites and CI |
| Deleting the regression test after the fix | No warning if the bug returns | Keep the test in the suite |
| Starting with full-context tests for tiny logic | Slow suite, hard to locate root cause | Choose the smallest scope that reproduces |
| Over-generalizing from one green test | Misses API, DB, Security, and config bugs | State the verified scope clearly |

## 10. Checklist Before Closing a Bugfix or Merging a PR

- [ ] Expected behavior is confirmed, with minimal reproduction steps and bug evidence.
- [ ] The new test covers the failing scenario with expected results derived from the contract, not current code.
- [ ] Observed the test **fail for the exact bug on the unfixed version** when feasible; otherwise documented the limitation.
- [ ] The fix resolves the root cause and the new test turns green without weakening assertions.
- [ ] Related boundary cases are covered; API, database, Security, or Spring context tests added if the bug touches those layers.
- [ ] Tests are independent and repeatable without relying on wall-clock timing, execution order, or external systems.
- [ ] Related tests and CI ran; reported results reflect actual runs.
- [ ] Both test and fix remain in the codebase so future refactors and upgrades retain regression protection.

**Conclusion:** Writing regression tests before or alongside bug fixes turns past incidents into lasting safeguards. The strongest evidence is **RED for the right reason → GREEN after the fix**, using contract-aligned assertions, matching the test level to the bug's location, and keeping the suite reliable enough to protect Spring Boot across future changes.