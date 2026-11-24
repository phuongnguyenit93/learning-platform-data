# The TDD Cycle: Meaningful Failure, Fix, and Refactor

TDD (Test-Driven Development) is a software development approach where a test is written before the implementation it describes. The developer repeats a short three-step cycle: write a new test and watch it fail, make the smallest change needed to pass the test, then refactor the design while keeping all tests green.

This cycle is commonly called **Red – Green – Refactor**:

- **Red:** create a test expressing missing behavior and confirm it fails for the right reason.
- **Green:** write the simplest implementation that satisfies the behavior just described.
- **Refactor:** improve the structure of test and production code without changing verified behavior.

In Spring Framework Testing, TDD turns requirements into executable examples, gives early design feedback, and lowers the risk of change. Each iteration, however, must target the right test boundary: business rules, Spring container-provided behavior, or external infrastructure integration.

## 1. Why Does TDD Start with a Failing Test?

When starting from production code, developers often imagine required behavior first and only afterward look for ways to prove it works. TDD reverses that order: before adding behavior, write a concrete example showing the expected outcome.

A new test should clarify at least three things:

1. **Condition:** what is the input or initial state?
2. **Action:** which component is called and with what data?
3. **Expected outcome:** what is observed if behavior is right?

For example, a business rule states that orders below the free-shipping threshold incur a standard shipping fee. Rather than immediately writing conditional branches in a calculator, express that rule as a test: with a subtotal of 250,000 and non-express delivery, the shipping fee must be 30,000.

The test becomes an executable example of the requirement. If it fails before the matching implementation exists, we know the test detected the gap to solve. If it passes before behavior is implemented, either the test is not hitting the right execution path or assertions are too weak.

TDD is not merely writing lots of tests. Its value comes from each new test producing a clear signal, then changing the implementation to satisfy that signal.

## 2. The Full Red – Green – Refactor Loop

~~~mermaid
flowchart TD
    A["Pick a small behavior"] --> B["RED: write test"]
    B --> C["Run test and observe failure"]
    C --> D{"Failed for the right reason?"}
    D -->|"Not yet"| E["Fix test, fixture, or test runner setup"]
    E --> C
    D -->|"Yes"| F["GREEN: minimal implementation"]
    F --> G["Re-run new test and related suite"]
    G --> H{"All green?"}
    H -->|"Not yet"| F
    H -->|"Yes"| I["REFACTOR: improve structure"]
    I --> J["Re-run tests"]
    J --> K{"Behavior still intact?"}
    K -->|"Not yet"| I
    K -->|"Yes"| L["Pick next behavior"]
    L --> A
~~~

Each loop should be small enough that the developer knows exactly which change turned the test from red to green. When one cycle spans many classes, rules, and external systems, pinpointing failures becomes hard.

### Red — Create a Trustworthy Failure Signal

In the Red step, write a test for an unfulfilled behavior. Then run the test and verify:

- The test compiles and actually executes.
- An assertion fails because actual differs from expected, or throws an exception matching the specified behavior.
- The test traverses the target component and intended path.
- The failure does not stem from environment configuration, an unstarted dependency, a misnamed test, or a broken fixture.

A compilation error from undeclared classes or methods is not a good Red signal for verifying behavior. Before evaluating assertions, build the minimal skeleton so the test can run. Likewise, if a Spring test fails because a bean is missing due to incomplete test configuration, that does not yet prove the business rule is wrong.

Read the failure cause rather than just seeing red in the IDE. A message like "expected 30000 but was 0" can be a clear signal. A database connection error or context startup error may simply be an environment setup issue.

### Green — Make the Smallest Change to Satisfy the Test

Once you have a trustworthy Red signal, write the smallest amount of code that turns the test green.

The goal here is satisfying the behavior just described, not anticipating every future possibility upfront. Avoid adding extra abstractions, configuration, or branches without a requirement and a corresponding test.

Once green, re-run the new test alongside related tests. If the change breaks an already-verified behavior, the suite should alert you immediately. A new test turning green while an existing test turns red shows the change is incomplete.

### Refactor — Improve Structure Without Changing Behavior

While tests are green, improve code so it stays readable and easy to evolve:

- Name classes, methods, variables, and tests after business meaning.
- Remove duplication, obscure conditionals, or unnecessary branches.
- Split responsibilities when a class takes on too much.
- Extract repeated magic values into named constants.
- Clarify test fixtures and helpers without hiding the behavior under test.
- Delete dead code and unneeded abstractions.

After each meaningful structural change, re-run tests. If a refactor alters business outcomes, it is no longer a pure refactoring; return to Red–Green to specify and implement the new behavior.

## 3. TDD Example for a Business Rule

Suppose a store has this shipping policy:

- Standard shipping costs 30,000.
- Orders with a subtotal of 500,000 or more qualify for free standard shipping.
- Express shipping has a flat 50,000 fee regardless of the standard free-shipping threshold.

We want a pure Java class to compute shipping fees. This rule does not need a Spring container, database, or HTTP to verify. Thus, the first TDD loop can use JUnit 5 and instantiate the calculator directly.

### First Cycle: RED

Start with a test describing an order below the free-shipping threshold:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {

    @Test
    void chargesStandardFeeBelowFreeShippingThreshold() {
        var calculator = new ShippingFeeCalculator();

        BigDecimal actual = calculator.calculate(
                new BigDecimal("250000"),
                false
        );

        assertEquals(new BigDecimal("30000"), actual);
    }
}
~~~

To let the test compile and run, create a minimal initial implementation:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        return BigDecimal.ZERO;
    }
}
~~~

Run the test. Actual is 0 while expected is 30,000. This is a meaningful Red: the test reached the method under test, received a result, and pinpointed the missing behavior.

If the test reports a missing class or fails to run, fix compilation/setup issues first. Do not treat setup errors as evidence that the shipping rule was tested.

### First Cycle: GREEN

Replace the minimal stub with logic satisfying the described case:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        if (express) {
            return new BigDecimal("50000");
        }

        if (subtotal.compareTo(new BigDecimal("500000")) >= 0) {
            return BigDecimal.ZERO;
        }

        return new BigDecimal("30000");
    }
}
~~~

Re-run the test. The 250,000 subtotal case should receive a 30,000 fee and turn green.

At this point, there is no need to add handling for every imaginable input. Continue with the next clearly specified behavior.

### Next Cycle: Add Free Standard Shipping Behavior

Write a test right at the 500,000 boundary:

~~~java
@Test
void waivesStandardFeeAtFreeShippingThreshold() {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal("500000"),
            false
    );

    assertEquals(BigDecimal.ZERO, actual);
}
~~~

Run the test before changing code. If it turns green immediately, check whether the current implementation happened to support it already or whether the test truly exercised the intended branch. In this example, the previous cycle already added the threshold condition, so the new test passes right away. That is still valuable: the new test documents a critical behavior and guards it against future edits.

Next, write a test for express delivery:

~~~java
@Test
void chargesExpressFeeRegardlessOfSubtotal() {
    var calculator = new ShippingFeeCalculator();

    BigDecimal actual = calculator.calculate(
            new BigDecimal("900000"),
            true
    );

    assertEquals(new BigDecimal("50000"), actual);
}
~~~

If the current implementation returns 50,000, the test turns green immediately because the express branch was written in the first cycle. When writing a new test, red is not an end in itself at any cost. The goal is concrete evidence for the behavior; if the behavior already works and the test fails when the rule breaks, the test remains valuable.

### Refactor: Name the Policy Values

Once tests cover all three rules, improve readability by naming the fees and threshold:

~~~java
import java.math.BigDecimal;

public final class ShippingFeeCalculator {

    private static final BigDecimal STANDARD_FEE =
            new BigDecimal("30000");

    private static final BigDecimal EXPRESS_FEE =
            new BigDecimal("50000");

    private static final BigDecimal FREE_SHIPPING_THRESHOLD =
            new BigDecimal("500000");

    public BigDecimal calculate(BigDecimal subtotal, boolean express) {
        if (express) {
            return EXPRESS_FEE;
        }

        if (subtotal.compareTo(FREE_SHIPPING_THRESHOLD) >= 0) {
            return BigDecimal.ZERO;
        }

        return STANDARD_FEE;
    }
}
~~~

Naming makes the numbers self-explanatory. Tests must stay green after refactoring. We added no new rules; we only made the implementation express the existing policy more clearly.

### Expand Boundary Tests

Thresholds are common spots for operator mistakes. If the policy says "500,000 or more," tests must distinguish below-threshold from exact-threshold. A parameterized test can express those examples cleanly:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeBoundaryTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @ParameterizedTest
    @CsvSource({
        "499999, 30000",
        "500000, 0",
        "500001, 0"
    })
    void calculatesStandardFeeAtThresholdBoundaries(
            String subtotal,
            String expectedFee
    ) {
        BigDecimal actual = calculator.calculate(
                new BigDecimal(subtotal),
                false
        );

        assertEquals(new BigDecimal(expectedFee), actual);
    }
}
~~~

This suite distinguishes greater-than from greater-than-or-equal. Changing **>=** to **>** causes the 500,000 case to fail and reveals the boundary bug.

The examples above use **BigDecimal** to avoid floating-point representation errors in monetary math. In real applications, rounding rules, currency units, taxes, and money representation also need separate requirements and tests if within business scope.

## 4. What Makes a Failure Meaningful?

Not all red test states carry equal value. A failure is meaningful when it proves the described behavior does not yet meet the expected outcome.

Several situations can be distinguished:

| Run result | Meaning | Action to take |
|---|---|---|
| Assertion reports expected != actual | Test ran and observed wrong behavior | Confirm this is new behavior, then implement |
| Test fails to compile | Specification cannot execute yet | Fix imports, signatures, classes, or test structure |
| No tests found / zero tests executed | No evidence yet | Check names, packages, filters, and runner config |
| Spring fails to build `ApplicationContext` | Possibly test config or app config error | Inspect context startup cause before concluding |
| Cannot connect to database/broker | Infrastructure or test env not ready | Check services, endpoints, ports, and test data |
| Failure due to timeout or leftover data | Unstable signal | Isolate resources and eliminate order dependencies |

A good Red has an error message close to the behavior under test. If a test aims to verify shipping fees yet fails because the database did not start, the test provides no signal on that rule.

When a test verifies an exception, the expected exception must appear explicitly in the assertion. For instance, if negative inputs are forbidden by requirement, the test can use **assertThrows** to verify the exact exception type. An unexpected `NullPointerException` or configuration error must never be mistaken for an expected failure.

Check the reverse as well: if a new test passes right away, verify whether it truly distinguishes correct from incorrect implementations. An assertion checking only that an object is non-null rarely suffices to guard a complex rule.

## 5. TDD at Different Test Boundaries in Spring

TDD is a development cycle, not a specific annotation or test type. Red–Green–Refactor works at any layer as long as the test describes that layer's behavior accurately.

### Business Rules: Favor Fast Loops

For domain models, calculators, validators, and application services depending on interfaces, start with plain JUnit. Instantiate objects directly and use fakes/stubs/mocks to control dependencies as needed.

The benefit is fast feedback without waiting for Spring context startup while keeping tests focused on behavior. The shipping fee calculator above fits this category.

If a rule can be tested only by booting the entire application, review the component's dependencies. Business logic may be tightly coupled to the database, system clock, or external APIs, making testing hard to control.

### Spring Container: Verify Spring-Provided Behavior

When the behavior under test is dependency injection, conditional beans, profiles, properties, AOP, or transaction proxies, tests must go through a Spring context.

Write a test for bean configuration, run it to observe the bean is unregistered or miswired, fix configuration, and re-run. For Spring Boot auto-configuration, **ApplicationContextRunner** lets you spin up lightweight contexts with tailored properties and classpath settings.

In TDD at this layer, distinguish configuration bugs from business bugs. If the goal is verifying a transaction proxy, fetch the bean from the context and invoke the method through that bean. Instantiating with **new** bypasses the proxy and cannot test proxy behavior.

### Spring MVC: Develop Endpoints with Test Slices

For controllers, **@WebMvcTest** and MockMvc let you specify request/response contracts before finishing the controller or mapping. Tests can verify:

- HTTP method and URL mapping.
- Path variables, query parameters, and request body binding.
- Validation returning appropriate errors.
- Status codes, headers, and JSON responses matching contract.
- Exceptions translated into HTTP responses per convention.

For example, a test for an order-lookup endpoint can send a GET request with an order ID and assert status 200 with JSON containing that ID. If the mapping does not exist yet, the test fails because the expected response is missing. Implement the controller and needed config until the test passes.

An MVC slice test typically mocks services or provides dedicated test dependencies. It focuses on the HTTP adapter; it does not prove the real database holds data or service business rules work.

### Persistence: Evolve Repositories from Data Behavior

For JPA repositories, **@DataJpaTest** helps verify mappings, queries, and persistence behavior in a suitable context. Write tests specifying data to store and retrieve, observe the unmet query, then implement the repository or mapping.

If the application relies on dialects, column types, locking, or engine-specific features of PostgreSQL/MySQL, run tests against the matching engine—such as with Testcontainers. An H2 test proves behavior only in the configured H2 environment; it does not automatically prove production database compatibility.

### Integration Flows: Use When Collaboration Itself Is Under Test

A business flow may cross controller, service, repository, and broker. When the requirement is verifying collaboration across multiple components, use a broader integration test such as **@SpringBootTest** with appropriate dependencies.

Red–Green–Refactor still applies, though feedback is slower. Keep integration tests for risks that require that scope while expressing finer-grained rules via fast business-layer tests.

| Boundary | Common Spring/JUnit tools | Behaviors suited for TDD |
|---|---|---|
| Business logic | JUnit 5, fakes/stubs/mocks | Rules, calculations, decisions, orchestration |
| Container/configuration | Spring TestContext, ApplicationContextRunner | Beans, profiles, properties, proxies, auto-configuration |
| MVC adapter | @WebMvcTest, MockMvc | Mapping, binding, validation, HTTP responses |
| Persistence | @DataJpaTest, database tests | Entity mapping, repository queries, data transactions |
| Application integration | @SpringBootTest, Testcontainers | Collaboration across multiple components and infrastructure |

## 6. True Refactoring in TDD

Refactoring means changing internal structure while preserving tested external behavior. This step keeps code understandable as rules accumulate.

### Refactoring Production Code

Signs code may need refactoring:

- Multiple methods repeat the same condition or calculation.
- One method mixes branches with unrelated responsibilities.
- Variable names obscure business meaning.
- A class requires too many dependencies to perform a small behavior.
- One simple change forces edits in many unrelated places.
- Tests are hard to set up because business logic is tangled with infrastructure access.

You can extract a policy, turn magic values into named constants, rename methods, or split a class into smaller responsibilities. Every change should stay protected by green tests.

Do not use the refactoring step to add new rules, change error messages, or alter side-effect ordering. Those changes need new tests describing the new behavior and a separate Red–Green loop.

### Refactoring Test Code

Tests need maintenance just like production code. As tests grow, check that:

- Each test has a name describing condition and outcome.
- Arrange does not obscure the action under test.
- Test data is concise and meaningful.
- Shared helpers are extracted only when genuinely reducing duplication without hurting readability.
- Too many unrelated behaviors are not crammed into one test.
- Test abstractions do not grow more complex than the logic under test.

You can apply the Arrange – Act – Assert structure:

~~~java
@Test
void waivesStandardFeeAtFreeShippingThreshold() {
    // Arrange
    var calculator = new ShippingFeeCalculator();
    var subtotal = new BigDecimal("500000");

    // Act
    var actual = calculator.calculate(subtotal, false);

    // Assert
    assertEquals(BigDecimal.ZERO, actual);
}
~~~

This structure helps readers spot inputs, action, and outcome. You do not need to force three comments into every test if variable names and layout are already crystal clear.

## 7. Habits That Undermine the TDD Cycle

### Writing Tests Without Running Them Before Implementation

If tests are written alongside implementation and run only once at the end, you never know whether the test could detect missing behavior. Assertions might accidentally pass against broken code, or the test might skip the target branch.

Run the test right after writing it and inspect the Red output before adding logic.

### Treating Every Red Error as a Valid Red Step

Compilation errors, Spring context startup failures, and database connection errors all turn tests red. They do not necessarily say anything about the specified behavior.

Read the stack trace and identify which phase failed: compilation, discovery, setup, execution, or assertion. Move to Green only when the failure signal matches the test's target.

### Writing One Oversized Test for Multiple Behaviors

A single test checking mapping, fee calculation, database persistence, message publishing, and HTTP responses makes failures hard to diagnose. When it turns red, developers must investigate many boundaries at once.

Split independently testable behaviors into tests suited to each layer. Use integration tests to verify overall collaboration when that collaboration itself must be proved.

### Mocking Every Dependency and Assuming Integration Works

Mocks keep tests fast and control branches. Yet if every repository, HTTP client, and broker is mocked, tests no longer verify protocols, SQL, or live connection config.

Keep mocks at boundaries requiring isolation; add adapter/infrastructure tests when real compatibility is a risk worth checking.

### Implementing Too Much Before Re-Running Tests

Writing a batch of tests, adding several classes, and editing multiple configs before running tests scatters potential root causes. Short loops narrow down the scope of changes to inspect.

### Refactoring While Tests Are Red

Refactoring on top of failing tests makes it impossible to tell whether a failure stems from unfinished behavior or structural edits. Get relevant tests back to green first, then refactor.

### Judging Quality by Coverage Alone

Coverage shows which code executed, not whether assertions detect wrong results. A test can execute every line without checking critical conditions.

Test quality lies in distinguishing valid behavior from invalid behavior. For boundaries, try temporarily flipping an operator or return value to confirm tests fail where expected. Mutation testing also adds evidence of assertion strength, though it never replaces understanding requirements.

## 8. Keep Loops Short and Feedback Reliable

To make TDD effective in a Spring project, organize test runs by cost and scope:

1. When writing business tests, run just the target test class or method for instant feedback.
2. After implementing, re-run the new test alongside tests near the modified component.
3. After refactoring, re-run related tests to confirm behavior remained intact.
4. Before finishing changes, run a broad enough suite to catch regressions across affected components.
5. For tests relying on databases, brokers, or external services, ensure test environments initialize and clean up deterministically.

Feedback speed matters because developers need to see the impact of recent edits. Still, never sacrifice infrastructure test realism just to make every test fast. A fast test with a fake and a slower test against a real database answer different questions; both can be necessary.

One complete TDD cycle usually leaves behind three outcomes:

- An executable example describing the required behavior.
- An implementation satisfying that example.
- Clean code that remains easy to change without breaking verified behavior.

## 9. When Is a TDD Cycle Considered Complete?

A cycle does not finish merely because the IDE shows green. Understand the evidence the test provides:

- The new test ran and produced a valid Red for the right reason, or confirmed existing behavior previously lacking test protection.
- Implementation turned the new test green.
- Related tests remain green after the change.
- Refactoring altered no observable behavior.
- Test name, data, and assertions accurately express the requirement.
- Dependencies are isolated at a level matching the boundary under test.

If a test cannot run due to environment issues, clearly separate that state from a behavioral test failure. Never declare a Red–Green cycle complete without execution evidence.

TDD creates a chain of small decisions: specify behavior, observe the gap, implement just enough, and refine design. With Spring Framework Testing, keep this cycle at the right boundary. Check business rules with fast tests; check container-provided behavior with Spring contexts; check infrastructure integration with suitable adapters and services. When each test answers one clear question, red shows what is missing, green shows the behavior holds, and refactoring keeps the system easy to evolve.

