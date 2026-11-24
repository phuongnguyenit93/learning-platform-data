# `@MockitoSpyBean` and Observing Real Bean Behavior

In a Spring integration test, we sometimes want to keep a real bean to test its behavior while also observing whether another component calls it properly. A Mockito spy satisfies this need: calls execute the real methods by default, while the test can verify interactions or selectively override a specific method.

Spring Framework 6.2 added the `@MockitoSpyBean` annotation to register a spy directly on a bean in the ApplicationContext. As a result, other beans receive the same Spring-managed spy via injection. The test can observe collaboration flows inside the context without creating an external Mockito object and hoping the application uses that exact instance.

The key point to remember is that a spy still executes real logic by default. Therefore, when using a spy, the test must account for input data, side effects, and state that the real methods may modify.

## How Does a Spy Bean Work?

A mock typically replaces a dependency's behavior with test-defined behavior. A spy preserves the object's real behavior and allows observing or stubbing specific calls.

| Mechanism | Default Behavior | Common Goal |
|---|---|---|
| Mockito mock / Spring `@MockitoBean` | Does not run real logic; returns default or stubbed values | Isolate the unit under test from its dependencies |
| Mockito spy / Spring `@MockitoSpyBean` | Calls the real method unless stubbed | Observe a real bean and verify how components collaborate |
| Mockito `@Spy` | Spies on an object created or provided by the test | Inspect an object within a pure Mockito test scope |
| Spring Boot `@SpyBean` | Spy bean mechanism in Spring Boot's context in older Boot versions | Similar, but part of Spring Boot's API |

With `@MockitoSpyBean`, Spring finds the matching bean in the ApplicationContext and wraps it in a Mockito spy. Components injected with that bean from the context receive the registered spy. This lets tests observe actual calls crossing bean boundaries in the application.

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["InvoiceService"]
    A --> C["TaxCalculator bean"]
    C --> D["Mockito spy wrapping the real bean"]
    B -->|Calls calculateTax| D
    D --> E["Runs real method unless stubbed"]
    E --> F["Mockito records interaction"]
    F --> G["Test asserts result and verifies call"]
~~~

A spy does not automatically turn every object of the same type in the JVM into a spy. It applies to the bean selected by Spring in the corresponding context. An object created via `new TaxCalculator()` outside the ApplicationContext remains a separate object and is not replaced by this annotation.

## Declaring `@MockitoSpyBean`

`@MockitoSpyBean` belongs to the package:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

The annotation is placed on a field in the test class to specify the bean to spy on. Example:

~~~java
@SpringJUnitConfig(InvoiceTestConfig.class)
class InvoiceServiceTest {

    @Autowired
    private InvoiceService invoiceService;

    @MockitoSpyBean
    private TaxCalculator taxCalculator;

    @Test
    void calculatesInvoiceUsingRealTaxCalculator() {
        BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
        verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
    }
}
~~~

In this example, `InvoiceService` is a real bean retrieved from the ApplicationContext. `TaxCalculator` also starts as a real bean, and Spring then wraps it with a spy. When `invoiceService.total(...)` calls `calculateTax(...)`, the real method executes and Mockito records the call so the test can verify it.

`@MockitoSpyBean` requires an existing bean to wrap. If the context has no matching bean, Spring cannot create a replacement spy the way it can create a mock bean; test context initialization fails. This matches the intent of a spy: the test wants to observe a real configured implementation.

## Full Example: Observing a Real Bean

Suppose an invoice service calls a tax calculation bean:

~~~java
import java.math.BigDecimal;

class TaxCalculator {

    BigDecimal calculateTax(BigDecimal netAmount) {
        return netAmount.multiply(new BigDecimal("0.10"));
    }
}

class InvoiceService {

    private final TaxCalculator taxCalculator;

    InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    BigDecimal total(BigDecimal netAmount) {
        BigDecimal tax = taxCalculator.calculateTax(netAmount);
        return netAmount.add(tax);
    }
}
~~~

Spring configuration creating the two real beans:

~~~java
@Configuration
class InvoiceTestConfig {

    @Bean
    TaxCalculator taxCalculator() {
        return new TaxCalculator();
    }

    @Bean
    InvoiceService invoiceService(TaxCalculator taxCalculator) {
        return new InvoiceService(taxCalculator);
    }
}
~~~

The test can verify both the business result and the interaction with the tax bean:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@SpringJUnitConfig(InvoiceTestConfig.class)
class InvoiceServiceSpyTest {

    @Autowired
    private InvoiceService invoiceService;

    @MockitoSpyBean
    private TaxCalculator taxCalculator;

    @Test
    void callsRealTaxCalculator() {
        BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
        verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
    }
}
~~~

The test proves two things:

1. The total amount is 110.00 when the real tax bean applies the 10% rate.
2. `InvoiceService` called `TaxCalculator.calculateTax()` with the pre-tax amount of 100.00.

If you only assert the result, you know the output is right without directly confirming that the collaborator was called with the expected argument. If you only verify the call, you know the interaction occurred without proving the final business result is correct. Combining assertions and verification when both belong to the contract under test makes the test's intent clear.

## Selective Stubbing While Keeping the Real Bean

A spy can replace the result of a specific method in a test. Other methods continue running real logic.

For example, to test how `InvoiceService` handles a tax amount supplied by a special policy:

~~~java
import static org.mockito.Mockito.doReturn;

@Test
void usesTaxValueProvidedByCollaborator() {
    doReturn(new BigDecimal("5.00"))
        .when(taxCalculator)
        .calculateTax(new BigDecimal("100.00"));

    BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

    assertThat(total).isEqualByComparingTo("105.00");
    verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
}
~~~

In this test, `InvoiceService` remains a real bean. The spy intercepts only the `calculateTax(100.00)` call and returns 5.00 as configured by the test. This is useful when you want to test a service branch with a deterministic collaborator result while keeping the rest of the Spring context and real logic intact.

### Why Use `doReturn` When Stubbing a Spy?

With a regular mock, the following style is familiar:

~~~java
when(mock.calculateTax(amount)).thenReturn(expectedTax);
~~~

When applied directly to a spy, the `mock.calculateTax(amount)` expression inside `when(...)` can execute the real method during stub setup. If the real method accesses a database, makes an HTTP call, mutates state, or throws an exception, test preparation can cause side effects or fail before the test even begins.

With a spy, prefer the `doReturn(...).when(spy).method(...)` syntax:

~~~java
doReturn(expectedTax)
    .when(taxCalculator)
    .calculateTax(amount);
~~~

Similar variants include `doThrow(...)`, `doNothing()`, `doAnswer(...)`, and `doCallRealMethod()`. They let you configure behavior without invoking the real method during stubbing.

Example testing how a service handles an error thrown by a collaborator:

~~~java
doThrow(new IllegalStateException("Tax service unavailable"))
    .when(taxCalculator)
    .calculateTax(new BigDecimal("100.00"));

assertThatThrownBy(() ->
    invoiceService.total(new BigDecimal("100.00"))
).isInstanceOf(IllegalStateException.class);
~~~

In this example, the spy throws the test-configured exception for the specific call. The test can verify how the service reacts when the collaborator fails.

## Verifying Interactions with Mockito

After the behavior runs, Mockito provides APIs to verify which calls the spy received:

~~~java
verify(taxCalculator).calculateTax(amount);
verify(taxCalculator, times(1)).calculateTax(amount);
verify(taxCalculator, never()).calculateTax(otherAmount);
verifyNoMoreInteractions(taxCalculator);
~~~

Common options:

| API | Meaning |
|---|---|
| `verify(spy).method(...)` | Verify that the method was called at least once |
| `times(n)` | Verify an exact number of calls |
| `never()` | Verify that the method was not called |
| `atLeastOnce()` | Verify at least one call |
| `atMost(n)` | Verify no more than the specified number of calls |
| `ArgumentCaptor` | Capture actual arguments for inspection |

Example using `ArgumentCaptor`:

~~~java
ArgumentCaptor<BigDecimal> amountCaptor =
    ArgumentCaptor.forClass(BigDecimal.class);

invoiceService.total(new BigDecimal("100.00"));

verify(taxCalculator).calculateTax(amountCaptor.capture());

assertThat(amountCaptor.getValue())
    .isEqualByComparingTo("100.00");
~~~

A captor is appropriate when the argument passed to a collaborator is an important part of the contract. Avoid verifying every internal call or call order that has no significance for the behavior under test. If tests couple too tightly to implementation details, a behavior-preserving refactor can break them.

## Selecting the Right Bean When Multiple Candidates Exist

If the ApplicationContext contains multiple beans of the same type, Spring needs to know which bean to spy on. Field-level `@MockitoSpyBean` uses the field's type to locate candidates; the field name can act as a fallback qualifier when disambiguating.

You can explicitly specify the bean with `@Qualifier`:

~~~java
@SpringJUnitConfig(PaymentTestConfig.class)
class PaymentServiceTest {

    @Autowired
    private PaymentService paymentService;

    @MockitoSpyBean
    @Qualifier("remotePaymentGateway")
    private PaymentGateway paymentGateway;
}
~~~

If there are two `PaymentGateway` beans and the test wants to observe `remotePaymentGateway`, the qualifier makes bean selection unambiguous. Check bean names, qualifiers, and active profiles if Spring reports multiple candidates or no matching bean.

Do not add a duplicate-typed bean just to help the annotation select one. Identify the bean the service actually uses and apply the matching qualifier.

## Spy Beans and AOP Proxies

In a Spring application, a bean may be wrapped by proxies for transactions, caching, security, or other aspects. When spying on a proxied bean, the test needs to understand whether calls go through the proxy or hit the target directly.

Several points to keep in mind:

- If you need to verify behavior at the bean boundary called by another service, observe the bean injected from the ApplicationContext.
- If a method is called through a Spring AOP proxy, interceptors can participate before or after the real call.
- Self-invocation—one method in the same object calling another method on `this`—typically bypasses the Spring AOP proxy. Therefore, a test should not assume every internal call triggers transactions or aspects.
- Stubbing a method on a spy can alter real behavior that a proxy or dependent bean expects; stub only what needs to be controlled.
- For beans with complex proxies, verify which reference the test is checking and whether calls actually pass through that reference.

A spy is useful for observing a bean, but it does not replace dedicated tests for transactions, security, or caching. If the goal is to prove an interceptor works, verify the outcome through the proxy in an appropriately configured test.

## Resetting Spies Between Tests

Spring manages the spy bean in the context and resets the Mockito spy after each test method by default according to the bean override reset policy. This ensures calls and stubbing from one test do not accidentally affect the next test, even when the ApplicationContext is cached and reused.

Because the spy is tied to the bean in the context, do not recreate the spy or reassign the reference inside individual test methods. Let Spring manage its lifecycle and declare the annotation on the test class.

If a test class shares a context with other classes, keep in mind that the spy bean belongs to the shared context. Resetting clears Mockito state such as stubbing and invocation history; it does not undo side effects performed by real methods. For example, if a spied method writes to a database, sends a message, or mutates singleton state, Mockito reset does not erase that data. Side effects still require transaction rollback, fixture cleanup, or a separate isolation mechanism.

## Distinguishing `@MockitoSpyBean`, `@MockitoBean`, and `@Spy`

Three annotations/mechanisms are often confused:

~~~java
@MockitoBean
private PaymentGateway paymentGateway;
~~~

`@MockitoBean` creates a mock bean to replace the bean in the context. Calls do not run real logic unless the test stubs or configures calling the real method.

~~~java
@MockitoSpyBean
private PaymentGateway paymentGateway;
~~~

`@MockitoSpyBean` wraps an existing bean with a spy. Calls run real logic by default and can be verified or selectively stubbed.

~~~java
@Spy
private PaymentGateway paymentGateway = new PaymentGateway();
~~~

Mockito's `@Spy` creates a spy for a test-scoped object. The Mockito annotation itself does not instruct Spring to replace a bean in the ApplicationContext. If a Spring service holds a different bean instance, this spy field may not observe calls made by the service.

Therefore, when the goal is to monitor a bean used by other beans in the Spring context, `@MockitoSpyBean` is the right choice. When you only need to spy on a local object in a pure Mockito unit test, `@Spy` may suffice.

## Distinguishing from Spring Boot's `@SpyBean`

Earlier Spring Boot versions provided `@SpyBean` in the Boot Test package. Spring Framework 6.2 added `@MockitoSpyBean` in the Spring TestContext Framework itself as part of its bean override mechanism.

When reading a codebase, check the Spring Framework and Spring Boot versions to choose the right API. For applications using Spring Framework 6.2 or later, you can use `org.springframework.test.context.bean.override.mockito.MockitoSpyBean`. Older projects can continue using the `@SpyBean` API provided by their Boot version or use a manual Mockito spy.

Do not import the wrong annotation simply because the names look similar. IDEs may auto-import from the wrong package if both Spring Boot Test and Spring Test are on the classpath.

## Limitations and Situations Requiring Caution

A spy runs real methods, so the test needs an environment safe enough for that method's side effects. Before spying, consider:

- Does the method write to a database or participate in a transaction?
- Does the method make HTTP calls, send messages, or write files?
- Does the bean hold mutable state shared across test methods?
- Does the method depend on time, thread-locals, or a request context?
- Is the bean proxied by AOP, or are there multiple implementations of the same type?
- Does the test truly need to verify that interaction, or is checking the public outcome enough?

Mockito cannot intercept every kind of method. The ability to spy/stub `final` methods depends on the mock maker and the project's Mockito configuration; `private` or `static` methods cannot be spied in the usual way as instance calls. For hard-to-observe APIs, it may be necessary to adjust the dependency design or test behavior at a public boundary.

Do not use a spy to assert internal implementation details just because Mockito supports `verify`. If a business goal can be confirmed via output results, asserting outputs is usually more resilient than asserting every internal call.

## Example: Verifying a Collaborator Is Not Called on Invalid Input

A spy is also useful when you want to verify that a real bean is not invoked on a particular business branch:

~~~java
@Test
void doesNotCalculateTaxForNegativeAmount() {
    assertThatThrownBy(() ->
        invoiceService.total(new BigDecimal("-1.00"))
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(taxCalculator);
}
~~~

The test assumes `InvoiceService` validates negative amounts before calling `TaxCalculator`. Because `taxCalculator` is a spy, `verifyNoInteractions` confirms that the service does not invoke the collaborator on the invalid-input branch. The real tax calculator method is not executed in this test.

Checking for no interactions is meaningful when the contract requires skipping the collaborator. If an internal call has no impact on behavior or resources, there is no need to bind the test to it.

## Choosing and Using a Spy Intentionally

Start from the observation goal. If you need to keep the real bean and verify that another bean calls it properly, use `@MockitoSpyBean`. If you want to replace an entire dependency to isolate a unit, use `@MockitoBean`. If you only need to spy on a local object outside a Spring context, use Mockito's `@Spy`.

When using `@MockitoSpyBean`, ensure the bean already exists in the context, select the right candidate by type and qualifier, let real methods run where appropriate, and use `doReturn`/`doThrow` when stubbing to avoid accidentally invoking the real method during setup. Verify contract-level interactions while managing real-method side effects with appropriate transactions or cleanup.

A good spy lets the test observe how real beans collaborate in the ApplicationContext while retaining control over selected calls. Used within the right scope, it helps uncover wiring and collaboration bugs that pure mocks might hide, while keeping the test focused on the behavior it needs to prove.
