# Nested Tests for Grouping Scenarios

JUnit Jupiter provides the **@Nested** annotation to organize test methods into contextually related groups. Instead of placing every test in a class into one flat list, you can describe a shared state or condition on an inner nested class and place the corresponding behaviors inside that group.

For example, when testing a shopping cart, scenarios can be divided into:

- When the cart is empty: total is zero, cannot check out.
- When the cart contains items: total is calculated accurately, checkout is allowed.
- When the cart has expired: checkout cannot proceed.

These groups still belong to the same test class and test the same component, yet the nested structure helps readers understand each group's preconditions before reading the test methods inside.

## 1. What Problem Does @Nested Solve?

A test class can quickly accumulate many methods when a component has multiple states and each state has multiple behaviors to verify. If all methods sit at the same flat level, test names have to repeat the condition:

~~~java
class ShoppingCartTest {

    @Test
    void emptyCartHasZeroTotal() {
        // ...
    }

    @Test
    void emptyCartCannotBeCheckedOut() {
        // ...
    }

    @Test
    void cartWithItemsCalculatesTotal() {
        // ...
    }

    @Test
    void cartWithItemsCanBeCheckedOut() {
        // ...
    }
}
~~~

Those tests still run, but shared conditions remain scattered across method names. With **@Nested**, conditions are lifted to the group level:

~~~java
class ShoppingCartTest {

    @Nested
    class WhenCartIsEmpty {
        @Test
        void hasZeroTotal() {
            // ...
        }

        @Test
        void cannotBeCheckedOut() {
            // ...
        }
    }

    @Nested
    class WhenCartContainsItems {
        @Test
        void calculatesTotal() {
            // ...
        }

        @Test
        void canBeCheckedOut() {
            // ...
        }
    }
}
~~~

Reading this structure, the two main contexts are immediately visible. Inner method names only need to describe the specific behavior because the condition is already expressed by the group name.

**@Nested** offers three primary benefits:

1. **Context-based grouping:** tests sharing the same initial state or business condition sit together.
2. **Reuse of shared setup:** the outer class can establish the baseline fixture; the nested class can add scenario-specific data.
3. **Hierarchical display:** IDEs and test reports can present groups and test methods in a parent–child hierarchy.

**@Nested** only organizes test structure. It does not create a database, open a separate transaction, or turn tests into a sequentially ordered workflow.

## 2. Basic Rules for Nested Classes in JUnit Jupiter

A class used with **@Nested** must be a **non-static inner class** of the enclosing test class. That class can access fields and methods of the outer class instance following Java's access rules.

~~~java
class AccountServiceTest {

    private AccountService accountService;

    @BeforeEach
    void setUp() {
        accountService = new AccountService();
    }

    @Nested
    class WhenAccountIsActive {

        @Test
        void allowsTransfer() {
            // Can access the outer class's accountService.
            assertDoesNotThrow(() -> accountService.transfer(/* data */));
        }
    }
}
~~~

The example illustrates the access relationship; the actual `transfer` call and data types depend on the application's API. Nested test classes are usually left package-private, just as JUnit Jupiter allows test classes and methods without `public`.

Several rules to remember:

- A nested class must carry the **@Nested** annotation for JUnit Jupiter to recognize it as a nested test class.
- Nested classes must not be declared `static`.
- Nested classes can contain test methods, lifecycle callbacks, and further **@Nested** classes.
- Multiple nesting levels are allowed, though each level should represent a meaningful condition.
- Test methods inside nested classes remain independent tests; they do not depend on whether another method ran first.

Do not add **@Test** to the nested class itself. The **@Nested** annotation marks the group's role; individual methods inside use **@Test**, **@ParameterizedTest**, or another appropriate test type.

## 3. Full Example: Grouping by Shopping Cart State

Suppose the application has a `ShoppingCart` with behaviors: calculating totals, adding items, and checking out. We want to test two main states: an empty cart and a cart containing items.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {

    private ShoppingCart cart;

    @BeforeEach
    void createEmptyCart() {
        cart = new ShoppingCart();
    }

    @Nested
    @DisplayName("When cart is empty")
    class WhenCartIsEmpty {

        @Test
        @DisplayName("Has zero total")
        void hasZeroTotal() {
            assertEquals(BigDecimal.ZERO, cart.total());
        }

        @Test
        @DisplayName("Rejects checkout")
        void rejectsCheckout() {
            assertThrows(
                EmptyCartException.class,
                () -> cart.checkout()
            );
        }
    }

    @Nested
    @DisplayName("When cart contains items")
    class WhenCartContainsItems {

        @BeforeEach
        void addProducts() {
            cart.addItem("book", new BigDecimal("50.00"), 2);
            cart.addItem("pen", new BigDecimal("10.00"), 1);
        }

        @Test
        @DisplayName("Calculates total of items")
        void calculatesTotal() {
            assertEquals(new BigDecimal("110.00"), cart.total());
        }

        @Test
        @DisplayName("Allows checkout")
        void allowsCheckout() {
            assertDoesNotThrow(() -> cart.checkout());
        }
    }
}
~~~

`ShoppingCart`, `EmptyCartException`, and the business methods in this example are illustrative models. Notice the preparation structure:

- `createEmptyCart()` on the outer class runs before every test, creating a fresh cart.
- For `WhenCartIsEmpty`, no extra setup is needed since the cart is already empty.
- For `WhenCartContainsItems`, `addProducts()` adds items before each test in that group.
- Each test verifies a single behavior for its corresponding state.

As a result, common preparation is not duplicated in every method, while group-specific data stays right where the group is defined.

## 4. Lifecycle of Outer and Nested Classes

An important aspect of using **@Nested** is understanding lifecycle callback ordering. JUnit Jupiter applies callbacks from enclosing and nested classes in hierarchical order.

For a test method inside a nested class:

1. The outer class's **@BeforeEach** callback executes.
2. The nested class's **@BeforeEach** callback executes.
3. The test method runs.
4. The nested class's **@AfterEach** callback executes.
5. The outer class's **@AfterEach** callback executes.

This lets the outer class set up the baseline fixture and the nested class add scenario-specific conditions:

~~~java
class PaymentServiceTest {

    private PaymentService paymentService;
    private FakePaymentGateway gateway;

    @BeforeEach
    void setUpBaseEnvironment() {
        gateway = new FakePaymentGateway();
        paymentService = new PaymentService(gateway);
    }

    @Nested
    class WhenGatewayAcceptsPayment {

        @BeforeEach
        void configureAcceptedPayment() {
            gateway.acceptNextPayment();
        }

        @Test
        void returnsSuccessfulResult() {
            // paymentService and gateway are already prepared.
        }
    }

    @Nested
    class WhenGatewayDeclinesPayment {

        @BeforeEach
        void configureDeclinedPayment() {
            gateway.declineNextPayment();
        }

        @Test
        void returnsDeclinedResult() {
            // Each test in this group receives the declined state.
        }
    }
}
~~~

The example assumes a fake gateway that allows controlling responses. The outer callback creates a fresh environment; each group's callback selects the appropriate response. Because test methods run independently, no test depends on another group having configured the gateway.

### 4.1. Splitting Preparation Responsibilities

A clear division of responsibilities looks like this:

| Location | What to Prepare |
|---|---|
| Constructor or field initializer | Simple immutable values not dependent on test lifecycle |
| Outer **@BeforeEach** | SUT, mocks/fakes, and baseline state shared across all groups |
| Nested **@BeforeEach** | Group-specific state |
| Test method | Data used only in one scenario and the action under test |
| Nested **@AfterEach** | Clean up resources created solely by that group |
| Outer **@AfterEach** | Clean up baseline resources created by the outer class |

Avoid putting every operation into the outer class's **@BeforeEach**. When groups have differing conditions, preparing them inside the nested class keeps those conditions visible in their relevant context.

### 4.2. @BeforeAll and @AfterAll

Under the default **PER_METHOD** lifecycle, **@BeforeAll** and **@AfterAll** methods must be `static`. For a nested test class, to use non-`static` **@BeforeAll** or **@AfterAll** inside the nested class, the corresponding test instance lifecycle must be **PER_CLASS**.

You can configure the lifecycle with **@TestInstance(TestInstance.Lifecycle.PER_CLASS)**. A single instance is then used for test methods in that class, and class-level callbacks can be instance methods:

~~~java
@Nested
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WhenUsingSharedResource {

    @BeforeAll
    void openSharedResource() {
        // Prepare shared resource for the group.
    }

    @AfterAll
    void closeSharedResource() {
        // Release resource after the group completes.
    }
}
~~~

Use **PER_CLASS** only when there is a clear reason, such as managing an expensive resource across the group. Because multiple test methods share the same instance, mutable fields can retain state between tests. If you use this lifecycle, ensure each test leaves no state that affects subsequent tests.

Usually, **@BeforeEach** is the better choice for scenario data. It gives every test a clear initial state and reduces the risk of order dependency.

## 5. Grouping by Condition, Then Sub-Grouping by Sub-State

JUnit Jupiter permits multiple levels of nesting. This is useful when a behavior depends on layered conditions.

Example with accounts:

- General scenario: account is active.
  - When balance is sufficient: transfer succeeds.
  - When balance is insufficient: transfer is rejected.
- General scenario: account is locked.
  - Transfers are disallowed.
  - Withdrawals are disallowed.

~~~java
class TransferServiceTest {

    private TransferService transferService;
    private Account source;
    private Account destination;

    @BeforeEach
    void setUpAccounts() {
        source = Account.activeWithBalance(new BigDecimal("500.00"));
        destination = Account.activeWithBalance(new BigDecimal("100.00"));
        transferService = new TransferService();
    }

    @Nested
    @DisplayName("When source account is active")
    class WhenSourceAccountIsActive {

        @Nested
        @DisplayName("When balance is sufficient")
        class WhenBalanceIsSufficient {

            @Test
            void transfersAmount() {
                // Arrange
                BigDecimal amount = new BigDecimal("200.00");

                // Act
                transferService.transfer(source, destination, amount);

                // Assert
                assertEquals(new BigDecimal("300.00"), source.balance());
                assertEquals(new BigDecimal("300.00"), destination.balance());
            }
        }

        @Nested
        @DisplayName("When balance is insufficient")
        class WhenBalanceIsInsufficient {

            @Test
            void rejectsTransfer() {
                // Arrange
                BigDecimal amount = new BigDecimal("900.00");

                // Act + Assert
                assertThrows(
                    InsufficientBalanceException.class,
                    () -> transferService.transfer(source, destination, amount)
                );
            }
        }
    }
}
~~~

The example focuses on expressing relationships between conditions; the `Account` factory methods and API are illustrative. The outermost level prepares baseline accounts, the middle level defines account state, and the innermost level describes the specific case.

Avoid nesting classes merely to create extra heading layers. If a subgroup introduces no distinct condition or meaning, one **@Nested** level is enough. Overly deep hierarchies force readers to trace through many classes just to understand one test method.

## 6. Using @DisplayName for Readable Group Labels

Java class names should describe conditions consistently, such as **WhenAccountIsLocked**. The **@DisplayName** annotation allows supplying friendlier labels in IDEs and reports:

~~~java
@Nested
@DisplayName("When account is locked")
class WhenAccountIsLocked {

    @Test
    @DisplayName("Rejects transfer request")
    void rejectsTransfer() {
        // ...
    }
}
~~~

**@DisplayName** can be placed on the outer test class, nested classes, and individual methods. Use group names to describe conditions, and method names to describe behaviors or outcomes. Avoid repeating the exact same phrase in both the group name and method name.

An example display hierarchy can be visualized as:

~~~text
TransferServiceTest
└── When source account is active
    ├── When balance is sufficient
    │   └── Transfers amount successfully
    └── When balance is insufficient
        └── Rejects transaction
~~~

Display names are labels for human readers. They do not change how JUnit selects tests or evaluates execution conditions.

## 7. Combining @Nested with Other JUnit Jupiter Test Types

A nested class is an ordinary test class in many respects, so it can contain any test method type supported by JUnit Jupiter.

### 7.1. Parameterized Tests Inside a Group

When a group has multiple inputs checking the same rule, you can place **@ParameterizedTest** inside a nested class:

~~~java
@Nested
@DisplayName("When quantity is invalid")
class WhenQuantityIsInvalid {

    @ParameterizedTest
    @ValueSource(ints = {0, -1, -5})
    void rejectsQuantity(int quantity) {
        assertThrows(
            InvalidQuantityException.class,
            () -> orderService.create(commandWithQuantity(quantity))
        );
    }
}
~~~

The group supplies the "invalid quantity" context; the parameterized test supplies multiple representative inputs for that same rule. If values have distinct outcomes or meanings, use separate tests or named parameter sources so reports remain clear.

### 7.2. Tags for Filtering Tests

**@Tag** can be applied to a test class, nested class, or method to mark test groups by execution purpose, such as **slow**, **database**, or **integration**:

~~~java
@Nested
@Tag("database")
class WhenPersistingOrder {

    @Test
    void storesOrder() {
        // ...
    }
}
~~~

**@Nested** and **@Tag** serve different purposes:

- **@Nested** describes structural and contextual relationships among tests.
- **@Tag** attaches labels to configure test selection or exclusion during runs.

A group can be both organized with **@Nested** and tagged if tests in that group share the same execution requirements.

### 7.3. Other Annotations

Annotations such as **@Disabled**, **@Timeout**, **@RepeatedTest**, and **@DisplayName** can still be used depending on test intent. Place annotations at the class level when a policy applies to the entire group, or at the method level when only one test requires that behavior. Never use annotations to hide a failing group of tests or turn flaky tests into permanently skipped tests.

## 8. Using @Nested in Spring Framework Tests

JUnit Jupiter handles discovering and executing nested classes. Spring TestContext can provide the context, dependency injection, and Spring testing features for that test class.

Example:

~~~java
@SpringBootTest
class CustomerServiceIntegrationTest {

    @Autowired
    private CustomerService customerService;

    @Nested
    @DisplayName("When customer is active")
    class WhenCustomerIsActive {

        @Test
        void allowsProfileUpdate() {
            // Use customerService injected from the Spring context.
        }
    }

    @Nested
    @DisplayName("When customer is locked")
    class WhenCustomerIsLocked {

        @Test
        void rejectsProfileUpdate() {
            // Verify behavior within the same Spring context.
        }
    }
}
~~~

In this example, the outer class declares the Spring configuration and dependencies. The nested test classes organize scenarios by customer status. By default, Spring test configuration from the enclosing class is inherited by nested test classes.

### 8.1. Controlling Configuration Inheritance with @NestedTestConfiguration

Spring Framework provides **@NestedTestConfiguration** to control whether a nested test class inherits test configuration from its enclosing class. The default is **INHERIT**, meaning the enclosing class's Spring configuration is inherited. When a nested class needs its own configuration, you can choose **OVERRIDE**:

~~~java
@SpringBootTest
class ApplicationIntegrationTest {

    @Nested
    class UsesApplicationContext {
        @Test
        void verifiesApplicationBean() {
            // ...
        }
    }

    @Nested
    @NestedTestConfiguration(
        NestedTestConfiguration.EnclosingConfiguration.OVERRIDE
    )
    @ContextConfiguration(classes = IsolatedTestConfiguration.class)
    class UsesIsolatedContext {

        @Test
        void verifiesIsolatedBean() {
            // ...
        }
    }
}
~~~

The snippet illustrates selecting an inheritance policy; actual configuration must match the application's test context. **@NestedTestConfiguration** belongs to Spring TestContext and has been available since Spring Framework 5.3. When using older Spring versions, check support before applying it.

Some guidelines when combining nested tests with Spring:

- Place shared configurations like **@SpringBootTest** or **@ContextConfiguration** on the outer class if all groups use the same environment.
- Keep scenario data and mock setup inside groups or test methods rather than turning nested classes into unnecessary context-rebuilding points.
- If a group requires a different context, state the inheritance policy and override configuration explicitly.
- Remember that Spring's context cache keys off context configuration. Different configurations create distinct contexts and increase execution time.
- Do not assume **@Nested** creates a separate transaction. Test transactions are governed by Spring Test configuration and active transactional annotations.

## 9. How @Nested Differs from Splitting Test Classes or Using @Tag

Not every group of tests needs a nested class. Choose an organization style based on relationships between scenarios and configuration scope.

| Organization Style | Suitable When | Points to Consider |
|---|---|---|
| Flat test methods | Small number of tests, simple conditions | Method names may have to repeat conditions |
| **@Nested** | Many tests for one component across different contexts or states | Adds class nesting and lifecycle rules |
| Splitting into multiple test classes | Groups have independent configurations, fixtures, or test responsibilities | May need to share helpers or configuration |
| **@Tag** | Filtering tests by category or execution cost | Tags do not create a parent–child hierarchy |

For instance, service tests can live in one class with nested groups by business state. However, if repository tests need a real database, API tests need a web layer, and service tests only need mocks, splitting them into separate test classes with dedicated configurations is often clearer.

A helpful distinction:

- Use **@Nested** when the question is **"which scenarios of the same subject do these tests belong to?"**
- Use multiple test classes when the question is **"are these different test scopes or environments?"**
- Use **@Tag** when the question is **"which tests should be included or excluded?"**

These approaches can be combined. One test class can hold multiple nested groups, each with its own tags.

## 10. Common Organizational Mistakes

### 10.1. Nested Classes That Rename Without Adding Context

A class named **NestedTests** or **MoreTests** does not help readers understand test conditions. Name classes after states or conditions, such as **WhenAccountIsLocked** or **WhenRequestIsInvalid**.

### 10.2. Nesting Too Many Levels

If a test method sits deep inside several classes whose intermediate layers add no meaningful condition, the structure becomes hard to navigate. Add a level only when it clarifies a genuine dimension of classification.

### 10.3. Putting Too Much Specific Data in the Outer Class

If the outer class always creates a locked account, the "active account" group has to undo that state or build another account. Keep the outer fixture neutral; make each group responsible for transitioning the fixture into its own state.

### 10.4. Using Mutated State Across Tests

Do not let one test method mutate a shared field and expect the next test to receive that state. Tests may run individually, in parallel, or in a different order. Each test must establish its own preconditions via lifecycle callbacks or helpers.

### 10.5. Using Test Order to Describe a Workflow

Do not build a group with "step 1 create account", "step 2 deposit funds", "step 3 transfer funds" and require tests to run sequentially. If a workflow must be tested, a single test method can execute the full sequence of actions and assert the final outcome. Other independent tests should still create their own data.

### 10.6. Using @BeforeAll with the Wrong Lifecycle

In nested classes, class-level callbacks are subject to **PER_CLASS** rules. Unless a shared resource is genuinely needed, using **@BeforeEach** is simpler and carries less risk of state sharing.

### 10.7. Repeating Spring Configuration in Every Group

If nested groups share one context, declaring the configuration on the outer class reduces duplication. If a group needs a different configuration, express the override explicitly via Spring TestContext mechanisms rather than sprinkling annotations arbitrarily.

### 10.8. Confusing Nested Tests with Nested Production Classes

**@Nested** is a structure for test classes. There is no need to create nested classes in production code just to mirror test structure. Test organization should serve scenario expression without forcing production design into the same shape.

## 11. Reading Results and Troubleshooting Nested Tests

When a test fails, the hierarchy helps identify context before reading the assertion. A report may display a path such as:

~~~text
ShoppingCartTest
└── When cart contains items
    └── Calculates total of items
        FAILED
~~~

From the group name, you can deduce that the test ran after the outer baseline fixture and the group's fixture were prepared. When investigating, check in order:

1. Did the outer class create the right baseline state for all groups?
2. Did the group's **@BeforeEach** callback overwrite or corrupt that state?
3. Did the test method create any additional per-test data it needed?
4. Does the assertion verify the right behavior for that group?
5. Is any mutable state, mock, or resource shared across tests?

If only tests in one nested group fail, start with that group's callbacks. If every group fails together, inspect the outer fixture or configuration. If failures only occur when running the full suite, check shared resources, **PER_CLASS** lifecycle, transactions, and order dependencies.

When running from an IDE, you can select an individual test method, a nested class, or the entire test class. Running a single nested group is useful for isolating issues, though final verification should still run against the project's full target suite.

## 12. Reusable Organization Template

For a component with multiple states, you can start with this structure:

~~~java
class ComponentTest {

    private Component component;

    @BeforeEach
    void setUp() {
        component = new Component();
    }

    @Nested
    @DisplayName("When condition A holds")
    class WhenConditionA {

        @BeforeEach
        void prepareConditionA() {
            // Set up state A.
        }

        @Test
        void performsExpectedBehavior() {
            // Additional Arrange if needed.
            // Act.
            // Assert.
        }
    }

    @Nested
    @DisplayName("When condition B holds")
    class WhenConditionB {

        @BeforeEach
        void prepareConditionB() {
            // Set up state B.
        }

        @Test
        void performsAlternativeBehavior() {
            // Additional Arrange if needed.
            // Act.
            // Assert.
        }
    }
}
~~~

When designing nested groups, consider:

- Does the group name describe a concrete condition or state?
- Do tests inside genuinely share that context?
- Is the outer baseline fixture neutral and helpful to the groups?
- Is group-specific setup placed in the right group's callback or test method?
- Could the lifecycle accidentally share state across tests?
- Can the structure be understood solely from class, group, and method names?
- Does each nesting level add information, or merely deepen the hierarchy?
- Is Spring configuration intentionally inherited or overridden?

## Conclusion

**@Nested** helps JUnit Jupiter express test scenarios in a parent–child hierarchy. The outer class holds baseline setup, nested classes define states or conditions, and test methods verify specific behaviors. When grouped by meaningful context, paired with proper lifecycle callbacks, and kept independent per test, nested structures make test suites easier to read, investigate, and extend.
