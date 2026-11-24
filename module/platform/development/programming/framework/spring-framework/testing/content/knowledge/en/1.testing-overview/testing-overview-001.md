# What Is Testing and What Evidence Does a Test Provide?

In the Spring Framework, testing is how you verify whether a component or a group of components performs its expected behavior. A good test turns a requirement into a repeatable scenario: preparing data, performing an action, observing the result, and comparing that result against expected conditions.

Test results provide evidence about behavior in the executed scenario. They help a team detect bugs, confirm a business rule, and recognize when a change breaks existing behavior. However, a single passing run does not prove that the entire application is free of bugs. To properly understand the value of testing, you need to know what the test checked, under what conditions, and what it left uncovered.

## 1. Why Does Software Need Testing?

Source code expresses how a developer intends to solve a problem. Users, on the other hand, care about observable outcomes: which status an HTTP request returns, how an order total is calculated, how data is stored, or how an invalid case is rejected.

Deviations can emerge between the intent in the source code and the actual behavior. Deviations may come from:

- Processing logic that does not match business rules.
- Overlooked boundary conditions, such as a quantity of 0 or empty data.
- Components collaborating incorrectly, such as a controller passing the wrong data to a service.
- Configuration or integration mechanisms not working as expected.
- A new change accidentally breaking behavior that previously worked.

Reading source code and manual testing are useful, but they do not replace repeatable test scenarios. When a test is automated, the team can rerun it after every change and receive fast feedback on which behaviors were affected.

## 2. Testing Is a Conditional Experiment

You can think of a test as a repeatable experiment. The test author defines in advance the initial conditions, the action to perform, and the outcome considered correct.

A test scenario typically has four parts:

| Part | Meaning | Example |
|---|---|---|
| Context | Initial state or data | Order has 3 items |
| Input | Data supplied to the component | Unit price is 12.50 |
| Action | Operation to test | Calculate total amount |
| Expectation | Observable result required | Total amount is 37.50 |

When running the test, the program performs the action with the prepared data. Check statements, commonly called *assertions*, compare the actual result against the expected result.

This flow can be illustrated as follows:

```text
Requirement or rule
        |
        v
Initial conditions + input data
        |
        v
Execute the action under test
        |
        v
Observe the actual result
        |
        v
Compare with the expected result
        |
        +---- Match ------> PASS
        |
        +---- Mismatch ---> FAIL
```

The crucial point is that expectations must derive from the requirement or rule being protected. If the author merely copies the current behavior of the source code as the expected result, the test may confirm an existing bug instead of catching it.

## 3. What Kinds of Evidence Does a Test Provide?

Test evidence is the information gathered when a specific scenario is executed. Evidence may include:

- The return value of a method.
- The value or state of an object after processing.
- The HTTP status, headers, and response body of a request.
- Data actually written to or read from storage.
- An exception thrown when input is invalid.
- Interactions with a dependency, if the test intentionally checks those interactions.
- A PASS/FAIL status along with failure details that identify which assertion failed.

For example, if a test sends a request with quantity 3 and asserts that the total amount equals 37.50, the evidence gathered is: with the configured data and conditions, the invoked execution path produced the result 37.50.

That evidence is valuable because it is tied to an observable behavior. It is more concrete than a general claim such as "this function looks right". Yet the scope of the evidence is also bounded by the data, configuration, and parts of the system that actually participated in the test.

### What Do PASS and FAIL Tell Us?

**PASS** means that all check conditions in that run succeeded. It shows that the observed behavior matched the expectations written in the test.

**FAIL** means that at least one check condition was not met, or the test could not complete as expected. This is a signal that requires investigation. Possible causes include:

- The source code has a bug.
- The expectation in the test does not match the requirement.
- Test setup data or test configuration is wrong.
- A dependent component is unavailable.
- The test depends on timing, execution order, or shared state.

Therefore, FAIL does not automatically prove the source code is wrong; it indicates that the experiment failed to satisfy the stated conditions. The reader must inspect the error message, input data, and assertion to find the root cause.

Likewise, PASS does not automatically prove that the requirement is satisfied in every case. It is only meaningful within the scope that the test actually observed.

## 4. Example: Testing a Rule with a Unit Test

Suppose the application has a rule for calculating the total amount from a unit price and a quantity:

```java
import java.math.BigDecimal;

public class PriceCalculator {

    public BigDecimal total(BigDecimal unitPrice, int quantity) {
        if (unitPrice == null) {
            throw new IllegalArgumentException("unitPrice must not be null");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }

        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

We want to verify two behaviors: a valid quantity produces the right total amount, while a negative quantity is rejected.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class PriceCalculatorTest {

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void calculatesTotalForPositiveQuantity() {
        BigDecimal result = calculator.total(
                new BigDecimal("12.50"),
                3
        );

        assertEquals(new BigDecimal("37.50"), result);
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(new BigDecimal("12.50"), -1)
        );
    }
}
```

The first test provides evidence that an input unit price of 12.50 and quantity of 3 produce a result of 37.50. The second provides evidence that a negative quantity leads to an `IllegalArgumentException`.

These two tests do not verify every behavior of the class. They do not test a `null` unit price, a quantity of 0, very large values, or rounding rules if the business specifies them. Additional scenarios are needed when those rules fall within the requirement scope.

The example also shows that a test should clearly state the behavior it protects. The name `calculatesTotalForPositiveQuantity` describes the expected outcome; the name `rejectsNegativeQuantity` describes how the system handles invalid data. When a test fails, its name and assertions help the reader understand what is broken.

## 5. Evidence Changes with Test Scope in Spring

A Spring application usually consists of multiple layers: controllers receiving requests, services handling business logic, repositories accessing data, and configuration or integration components. Not every test needs to start the entire application.

Choosing the test scope determines the kind of evidence you can obtain:

| Scope | Common Testing Approach | Primary Evidence |
|---|---|---|
| Unit test | Call a Java class directly without starting a Spring context | Class logic under controlled inputs and dependencies |
| MVC slice test | Use `@WebMvcTest` and `MockMvc` | Mapping, parameter binding, validation, HTTP status, and response of the loaded MVC layer |
| Persistence slice test | Use `@DataJpaTest` | Persistence mapping and queries under the test database configuration |
| Integration test | Use `@SpringBootTest` | Collaboration among beans and configuration loaded in the application context |

These scopes answer different questions. Unit tests run fast and focus on logic. MVC slice tests verify the HTTP processing path at the MVC layer. Persistence slice tests focus on data access. Integration tests verify multiple components collaborating within the same application.

Starting a Spring context does not automatically mean every external system is tested. If a database, message broker, or HTTP service is replaced with a mock, the test only provides evidence about how the application interacts with that mock. To verify real integration, the test environment must include the corresponding component and the test must actually send data across the integration boundary.

### Example: Testing an Endpoint with MockMvc

Suppose a controller accepts a user's name and calls `GreetingService`:

```java
@RestController
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings")
    String greet(@RequestParam String name) {
        return greetingService.greet(name);
    }
}
```

An MVC slice test can verify the endpoint as follows:

```java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private GreetingService greetingService;

    @Test
    void returnsGreetingForName() throws Exception {
        when(greetingService.greet("Lan")).thenReturn("Xin chào, Lan");

        mockMvc.perform(get("/greetings").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Xin chào, Lan"));
    }
}
```

The test sends a GET request to `/greetings` with the parameter `name=Lan`. It asserts that the endpoint returns HTTP 200 and the response body is `Xin chào, Lan`.

The evidence here includes Spring MVC recognizing the mapping, reading the request parameter, invoking the controller, and producing the expected response. However, `GreetingService` has been replaced by a mock. Therefore, this test does not prove that the real logic inside the service is correct, nor does it prove that a database or external service works.

To verify service logic, write a unit test for the service. To verify the path from an HTTP request through the service to a repository or database, choose an integration test with appropriate dependencies. Each test needs a clear objective and scope.

## 6. What a Test Cannot Prove on Its Own

A test always has limits. Understanding those limits helps avoid overinterpreting a PASS result.

**Does not test every input.** A test only runs the scenarios described in it. Other inputs may take different execution branches and expose new bugs.

**Does not prove the entire application is bug-free.** A test suite can protect many critical behaviors, yet cannot cover every state, event ordering, and operating environment.

**Does not prove the production environment matches the test environment.** Configuration, database versions, permissions, networking, and real data may differ.

**Does not guarantee business requirements were understood correctly.** If the expectation in a test is wrong, the test can still PASS consistently. Test quality depends on the quality of the rules and expected data.

**Does not guarantee internal code is well designed.** A test can confirm correct output even when the source code is hard to maintain, slow, or poorly structured. Those concerns require other forms of review.

### Coverage Does Not Equal Correctness

Test coverage (*test coverage*) indicates which parts of the code were executed during a test run, depending on the metric such as lines, branches, or methods.

High coverage can show that many parts of the code ran, but it does not tell whether the results were properly verified. A test can execute a line without any meaningful assertion. Conversely, a handful of tests focused on high-risk rules can provide highly valuable evidence even if coverage is below 100%.

Therefore, coverage is a supporting indicator for finding unexecuted areas. It is not a certification that the program is correct.

## 7. Characteristics of a Reliable Test

A test is valuable when readers understand which behavior it protects and can trust the result of rerunning it.

- **Clear objective:** test names and assertions express a specific behavior.
- **Expectations independent of implementation:** expected results come from requirements or rules, not derived by re-invoking the very logic under test.
- **Verifies observable outcomes:** prioritizes outputs, state, or interactions that belong to the component's contract.
- **Includes representative data and edge cases:** covers normal cases, invalid data, and critical rule boundaries.
- **Repeatable:** does not depend randomly on time, execution order, shared state, or uncontrolled external services.
- **Clear failure reporting:** when it fails, the reader can identify the input, expectation, and actual result.

Mocks and stubs are useful tools for isolating a component, but their use should be deliberate. Mocks help control dependencies and verify interactions; at the same time, they can hide bugs in the real implementation of those dependencies. Only replace components that lie outside the target of the test.

## 8. How to Read Test Results

When a test run finishes, do not just look at the total PASS and FAIL counts. Read the results in order:

1. **Which test ran?** Identify the class and test method names to know which behavior was checked.
2. **What were the initial conditions?** Inspect the data, configuration, and mocks or stubs that were set up.
3. **Which action was performed?** Identify the method called or the HTTP request sent.
4. **Which assertions passed or failed?** Compare expected values against actual values, or read the reported exception.
5. **Which scope was not tested?** Determine whether real dependencies participated or were replaced, and which input branches lack corresponding scenarios.

For example, the message "expected 37.50 but was 35.00" indicates that the assertion on the total amount failed. It does not yet tell whether the cause lies in the formula, the input data, or the expectation. You must go back to the test scenario and business rules to pinpoint the fault.

When all tests PASS, you can conclude that the behaviors described in those tests satisfied their check conditions in the current run. This is useful evidence for continuing development and reducing regression risk. Confidence increases when tests have clear objectives, cover critical scenarios, and verify the right boundaries to protect.

## 9. Connecting Concepts to Spring Development Work

In a Spring project, testing should begin with the questions that need evidence:

- Is the service's business logic correct for key inputs?
- Does the controller accept the right parameters and return the right HTTP status and response?
- Does the repository persist and query data according to the mapping?
- Do beans and configuration collaborate properly when the application starts?
- Did a change break previously confirmed behavior?

The question determines the scope; the scope helps choose the test type; assertions define the evidence to gather. When a test PASSES or FAILS, the result should only be interpreted within the scope of that question.

Testing is therefore part of building verifiable software. It turns expectations into executable scenarios, helping teams detect deviations early and preserve evidence that critical behaviors continue to work after every change.
