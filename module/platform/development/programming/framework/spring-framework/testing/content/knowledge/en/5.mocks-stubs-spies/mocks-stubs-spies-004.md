# Configuring Exceptions from Mocked Components

In unit testing, a service often depends on a repository, HTTP client, payment gateway, or external component. To test error branches without causing real failures, we can configure a mock to throw an exception on the exact call under test. The test then confirms that the service handles, translates, or propagates the error according to its contract.

Mockito provides two primary stubbing approaches: `when(...).thenThrow(...)` for value-returning methods and `doThrow(...).when(...)` for `void` methods. Combine them with JUnit's `assertThrows` to verify exceptions, root causes, and related interactions.

## Learning Objectives

After this lesson, you will be able to:

- Configure mocks to throw checked exceptions and unchecked exceptions.
- Use `thenThrow` for value-returning methods.
- Use `doThrow` for `void` methods.
- Configure consecutive behaviors or throw exceptions conditionally based on arguments.
- Verify that a service translates, preserves, or handles exceptions from a collaborator.
- Understand checked exception constraints and how Mockito validates exception types.
- Avoid pitfalls when configuring exceptions on mocks and spies.
- Properly simulate failures for asynchronous APIs returning `CompletableFuture`.

## 1. Why configure exceptions on mocks?

Suppose `CheckoutService` calls `PaymentGateway` to collect payment. When the gateway times out, the service must translate the technical error into an error suited to the business domain. If we only test the success path, we do not know whether the service behaves properly when a collaborator fails.

You can simulate scenarios such as:

- An HTTP client encountering a timeout or connection failure.
- A repository throwing a data access exception.
- A payment gateway declining a transaction or failing to respond.
- A message publisher unable to send a message.
- File storage unable to read or write a resource.
- A collaborator throwing an exception for specific input data.

Mocks let tests control the timing and type of exception. Tests do not need to disable the network, take down a database, or inject flaky failures into the test environment.

A test using mocks only confirms how the class under test reacts to a simulated exception. It does not prove that the HTTP client, database driver, or external service actually throws that exception in production. The integrated behavior of those components must be tested at another appropriate level.

## 2. Example: a service translating a gateway exception into a business error

We start with a gateway that can throw a checked exception:

~~~java
public interface PaymentGateway {

    PaymentResult charge(PaymentCommand command)
            throws PaymentGatewayException;
}
~~~

Illustrative data types:

~~~java
public record PaymentCommand(String orderId, long amount) {}

public record PaymentResult(String transactionId) {}

public class PaymentGatewayException extends Exception {

    public PaymentGatewayException() {
        super();
    }

    public PaymentGatewayException(String message) {
        super(message);
    }
}
~~~

The service handling errors from the gateway:

~~~java
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public Receipt checkout(PaymentCommand command) {
        try {
            PaymentResult result = paymentGateway.charge(command);
            return new Receipt(command.orderId(), result.transactionId());
        } catch (PaymentGatewayException exception) {
            throw new CheckoutFailedException(
                "Payment could not be completed",
                exception
            );
        }
    }
}
~~~

The business exception preserves the original exception as its cause:

~~~java
public class CheckoutFailedException extends RuntimeException {

    public CheckoutFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}

public record Receipt(String orderId, String transactionId) {}
~~~

In the test, we configure the mock gateway to throw `PaymentGatewayException`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void convertsGatewayFailureToCheckoutFailure() throws Exception {
        PaymentCommand command =
            new PaymentCommand("ORDER-100", 250_000);

        PaymentGatewayException gatewayFailure =
            new PaymentGatewayException("Gateway timed out");

        when(paymentGateway.charge(command))
            .thenThrow(gatewayFailure);

        CheckoutFailedException thrown = assertThrows(
            CheckoutFailedException.class,
            () -> checkoutService.checkout(command)
        );

        assertEquals(
            "Payment could not be completed",
            thrown.getMessage()
        );
        assertSame(gatewayFailure, thrown.getCause());

        verify(paymentGateway).charge(command);
    }
}
~~~

Three things happen:

1. `when(paymentGateway.charge(command))` specifies the call the mock needs to handle.
2. `thenThrow(gatewayFailure)` defines the exception thrown when that call occurs.
3. `assertThrows` invokes the service and verifies the exception exposed outwardly by the service.

`assertSame` verifies that the cause is the exact original exception instance. This is useful when the service must preserve cause details for logging, diagnostics, or higher-level handling.

## 3. Using thenThrow for value-returning methods

Basic syntax:

~~~java
when(mock.someMethod(arguments))
    .thenThrow(exception);
~~~

Example:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new PaymentGatewayException("Connection refused"));
~~~

When code calls the exact method with matching arguments, the mock throws the exception instead of returning a default value.

### Passing an exception instance

~~~java
PaymentGatewayException failure =
    new PaymentGatewayException("Payment provider unavailable");

when(paymentGateway.charge(command))
    .thenThrow(failure);
~~~

Pass an instance when the test needs to check the message, cause, or specific state of the exception. Mockito throws the provided instance.

If the same stub is called multiple times, reusing one instance can make stack traces harder to read. For tests needing a fresh exception instance per call, consider passing the class.

### Passing an exception class

~~~java
when(paymentGateway.charge(command))
    .thenThrow(PaymentGatewayException.class);
~~~

Mockito instantiates the exception type when the stub is called. This style fits when the test only needs the exception type without custom message or cause configuration. The exception class must have a constructor Mockito can use for instantiation.

If you need a custom message or want to check the exact cause, passing an instance is usually clearer.

### Throwing unchecked exceptions

Unchecked exceptions do not need to be declared in the method signature:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new IllegalStateException("Gateway is not initialized"));
~~~

The setup is identical to checked exceptions. The difference lies in Java rules: unchecked exceptions belong to `RuntimeException` or `Error`, so the method does not require a `throws` declaration.

## 4. Checked exceptions must match the method signature

Java requires checked exceptions to be declared or handled. Mockito also validates checked exception compatibility when configuring a stub.

If a method declares:

~~~java
PaymentResult charge(PaymentCommand command)
        throws PaymentGatewayException;
~~~

then you can configure:

~~~java
when(paymentGateway.charge(command))
    .thenThrow(new PaymentGatewayException("Provider unavailable"));
~~~

However, if a method does not declare checked exceptions:

~~~java
public interface ProductCache {
    Product find(String productId);
}
~~~

then configuring an incompatible checked exception fails:

~~~java
when(productCache.find("P-100"))
    .thenThrow(new IOException("Disk error"));
~~~

Mockito reports a configuration error because `IOException` is a checked exception that the `find` method does not declare. In this case, you can use an unchecked exception fitting the contract:

~~~java
when(productCache.find("P-100"))
    .thenThrow(new IllegalStateException("Cache is unavailable"));
~~~

Do not turn checked exceptions into unchecked ones just to make tests run. Choose an exception matching the API published by the collaborator. If the API genuinely can throw a checked exception, the method signature must reflect that.

## 5. Using doThrow for void methods

For value-returning methods, Mockito can record the call inside the `when(...)` expression. `void` methods have no value to pass into `when`, so the `doThrow(...).when(...)` syntax is required.

Suppose a notifier has a method for sending notifications:

~~~java
public interface NotificationClient {

    void send(Notification notification)
            throws NotificationDeliveryException;
}

public record Notification(String recipient, String message) {}

public class NotificationDeliveryException extends Exception {

    public NotificationDeliveryException(String message) {
        super(message);
    }
}
~~~

Configure the mock to throw an exception:

~~~java
doThrow(new NotificationDeliveryException("SMTP unavailable"))
    .when(notificationClient)
    .send(any(Notification.class));
~~~

A service translating the error into a business exception:

~~~java
public class NotificationService {

    private final NotificationClient client;

    public NotificationService(NotificationClient client) {
        this.client = client;
    }

    public void notifyUser(Notification notification) {
        try {
            client.send(notification);
        } catch (NotificationDeliveryException exception) {
            throw new NotificationFailedException(
                "Could not notify recipient",
                exception
            );
        }
    }
}
~~~

~~~java
public class NotificationFailedException extends RuntimeException {

    public NotificationFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Test:

~~~java
@Test
void convertsDeliveryFailureToNotificationFailure() throws Exception {
    NotificationClient client = mock(NotificationClient.class);
    NotificationService service = new NotificationService(client);

    Notification notification =
        new Notification("ada@example.com", "Your order is ready");

    NotificationDeliveryException cause =
        new NotificationDeliveryException("SMTP unavailable");

    doThrow(cause)
        .when(client)
        .send(notification);

    NotificationFailedException thrown = assertThrows(
        NotificationFailedException.class,
        () -> service.notifyUser(notification)
    );

    assertSame(cause, thrown.getCause());
    verify(client).send(notification);
}
~~~

This syntax also works with unchecked exceptions:

~~~java
doThrow(new IllegalStateException("Client is closed"))
    .when(notificationClient)
    .send(any(Notification.class));
~~~

When using argument matchers, follow Mockito's rule: if a call has multiple parameters and you use a matcher for one parameter, use matchers for all parameters of that call.

## 6. Configuring multiple consecutive calls

Some scenarios require simulating a first call failing while a subsequent call succeeds. Mockito lets you chain behaviors on the same stub.

For example, the first client call times out and the next returns the product:

~~~java
when(catalogClient.find("BOOK-1"))
    .thenThrow(new CatalogTimeoutException("Temporary timeout"))
    .thenReturn(new Product("BOOK-1", "Spring Testing"));
~~~

Test verifying the sequence of behaviors:

~~~java
@Test
void receivesFailureFirstAndProductOnRetry() {
    when(catalogClient.find("BOOK-1"))
        .thenThrow(new CatalogTimeoutException("Temporary timeout"))
        .thenReturn(new Product("BOOK-1", "Spring Testing"));

    assertThrows(
        CatalogTimeoutException.class,
        () -> catalogClient.find("BOOK-1")
    );

    Product product = catalogClient.find("BOOK-1");

    assertEquals("Spring Testing", product.name());
}
~~~

If a stub has multiple chained behaviors and call counts exceed the declared behaviors, Mockito keeps repeating the last behavior. For example, after throwing an exception once and returning a product once, subsequent calls continue returning the product.

You can configure multiple consecutive exceptions:

~~~java
when(catalogClient.find("BOOK-1"))
    .thenThrow(
        new CatalogTimeoutException("First timeout"),
        new CatalogTimeoutException("Second timeout")
    )
    .thenReturn(new Product("BOOK-1", "Spring Testing"));
~~~

This setup is useful for testing retries, but place it at the boundary actually used by retry logic. If a service has a retry loop, call the service and assert on both the outcome and the invocation count, rather than calling the mock manually and concluding that retry works.

Example verifying the number of attempts:

~~~java
verify(catalogClient, times(3)).find("BOOK-1");
~~~

The expected count must match the service's retry policy, including both the initial attempt and retries.

## 7. Conditionally throwing exceptions with thenAnswer

Sometimes an exception depends on the call's arguments or state. In such cases, you can use `thenAnswer` to decide behavior inside a callback.

For example, the client only times out for one product code:

~~~java
when(catalogClient.find(anyString()))
    .thenAnswer(invocation -> {
        String productId = invocation.getArgument(0);

        if ("SLOW-ITEM".equals(productId)) {
            throw new CatalogTimeoutException("Lookup timed out");
        }

        return new Product(productId, "Available product");
    });
~~~

Test:

~~~java
@Test
void throwsOnlyForTheSlowProduct() {
    when(catalogClient.find(anyString()))
        .thenAnswer(invocation -> {
            String productId = invocation.getArgument(0);

            if ("SLOW-ITEM".equals(productId)) {
                throw new CatalogTimeoutException("Lookup timed out");
            }

            return new Product(productId, "Available product");
        });

    assertThrows(
        CatalogTimeoutException.class,
        () -> catalogClient.find("SLOW-ITEM")
    );

    Product product = catalogClient.find("BOOK-1");

    assertEquals("BOOK-1", product.id());
}
~~~

`thenAnswer` is flexible but can make tests harder to read if the callback contains extensive logic. If you only need to throw a fixed exception, use `thenThrow`. Only use `thenAnswer` when the decision genuinely depends on parameters, invocation counts, or data inside the invocation.

## 8. Configuring exceptions on spies

Mocks do not execute real implementations by default. Spies are different: they wrap a real object and usually invoke real methods when unstubbed.

Example:

~~~java
CatalogRepository repository = spy(new CatalogRepository());
~~~

If you write:

~~~java
when(repository.load("BOOK-1"))
    .thenThrow(new CatalogAccessException("Unavailable"));
~~~

then the expression `repository.load("BOOK-1")` is invoked immediately when Mockito evaluates the argument to `when`. With a spy, the real call can run during the setup step. If the real method accesses files, databases, or throws an exception, the test can fail before the stub is installed.

To avoid calling the real implementation during stubbing, use the `doThrow` form:

~~~java
doThrow(new CatalogAccessException("Unavailable"))
    .when(repository)
    .load("BOOK-1");
~~~

This form is especially useful for spies when the real method has side effects or cannot run during test preparation.

For `void` methods on spies, `doThrow` is also the appropriate configuration style:

~~~java
doThrow(new IllegalStateException("Cannot refresh"))
    .when(repository)
    .refresh();
~~~

| Object | Commonly used syntax | Note |
|---|---|---|
| Mock, value-returning method | `when(mock.call()).thenThrow(...)` | Mock does not run real implementation |
| Mock, void method | `doThrow(...).when(mock).call()` | No return value to use in when |
| Spy, value-returning method | `doThrow(...).when(spy).call()` | Avoids calling real implementation during stubbing |
| Spy, void method | `doThrow(...).when(spy).call()` | Configures exception without running real method |

Do not use a spy just because you want part of a dependency to be real. In unit tests, mocks or fakes usually create clearer boundaries. Only use a spy when you need to preserve most real behavior and intentionally override specific calls.

## 9. What to check after an exception is thrown?

A good test does not stop at verifying an exception occurred. Verify the error contract that the class under test must fulfill.

### Check the exception type

~~~java
CheckoutFailedException thrown = assertThrows(
    CheckoutFailedException.class,
    () -> checkoutService.checkout(command)
);
~~~

`assertThrows` returns the thrown exception instance itself, so you can further inspect its message, cause, or custom properties.

### Check the message and cause

~~~java
assertEquals(
    "Payment could not be completed",
    thrown.getMessage()
);
assertInstanceOf(
    PaymentGatewayException.class,
    thrown.getCause()
);
~~~

If you need to confirm the exact cause instance:

~~~java
assertSame(gatewayFailure, thrown.getCause());
~~~

### Confirm the collaborator was called

~~~java
verify(paymentGateway).charge(command);
~~~

This proves the service went through the expected failure-inducing call.

### Confirm subsequent steps did not happen

Suppose the service only saves a receipt after successful payment. When the gateway throws an exception, the test should confirm that the repository was not called:

~~~java
verifyNoInteractions(receiptRepository);
~~~

If the repository already had other prior interactions, use a more specific check:

~~~java
verify(receiptRepository, never()).save(any(Receipt.class));
~~~

Choose assertions reflecting the business contract. There is no need to verify every internal call if it does not affect outcomes or side effects users care about.

## 10. Synchronous exceptions and asynchronous methods

A common point of confusion involves methods returning `CompletableFuture`. When a dependency operates asynchronously, task failure is typically represented by a failed future rather than being thrown directly at method invocation time.

Example interface:

~~~java
public interface RemoteCatalogClient {
    CompletableFuture<Product> findAsync(String productId);
}
~~~

To simulate a failed future:

~~~java
when(remoteCatalogClient.findAsync("BOOK-1"))
    .thenReturn(
        CompletableFuture.failedFuture(
            new CatalogTimeoutException("Remote lookup timed out")
        )
    );
~~~

The service may handle errors inside the pipeline:

~~~java
public CompletableFuture<Product> findProduct(String productId) {
    return remoteCatalogClient.findAsync(productId)
        .exceptionally(exception -> {
            throw new CompletionException(
                new CatalogUnavailableException(
                    "Catalog is unavailable",
                    exception
                )
            );
        });
}
~~~

In tests, await or join the future and assert on the exception according to how the asynchronous API exposes it. For example:

~~~java
CompletionException thrown = assertThrows(
    CompletionException.class,
    () -> service.findProduct("BOOK-1").join()
);
~~~

If you use `thenThrow` on a method returning a future:

~~~java
when(remoteCatalogClient.findAsync("BOOK-1"))
    .thenThrow(new IllegalStateException("Client not initialized"));
~~~

then the exception occurs synchronously at the moment `findAsync` is called. That differs from returning a future in a failed state. Choose the simulation matching the collaborator's real contract.

## 11. Common pitfalls when configuring exceptions

- **Using `when(...).thenThrow(...)` for void methods:** Java has no return value to place inside when; use `doThrow(...).when(mock).method(...)`.
- **Throwing an undeclared checked exception:** Mockito reports an invalid stubbing error. Check the method signature and use a compatible exception type.
- **Configuring wrong arguments:** a stub only applies to calls matching its arguments or matchers. Non-matching calls may receive the mock's default value instead of the exception.
- **Inconsistent matcher usage:** if one parameter uses a matcher, the remaining parameters in that same call also require matchers.
- **Checking only the exception while ignoring post-error behavior:** a service might throw the right exception type yet still persist data or invoke a collaborator that should not have been called.
- **Using a spy like a mock:** spies execute real implementations when unstubbed. Consider side effects and use `doThrow` syntax when needed.
- **Reusing one exception instance across multiple tests:** each test should create and configure its own mock and exception, avoiding shared state.
- **Simulating synchronous errors for asynchronous APIs:** if an API returns a failed future, return `CompletableFuture.failedFuture(...)` to test the right handling path.
- **Using overly generic exceptions:** prefer exception types meaningful to the collaborator's contract so tests clearly express the scenario being simulated.
- **Treating mocks as integration proof:** mock tests verify the reaction of the class under test; they do not verify protocols or real failures of external services.

## 12. Workflow for configuring and verifying exceptions

When you need to test a collaborator's error branch, follow this sequence:

1. Identify which call can fail and which exception type the API declares or specifies.
2. Create a mock with Mockito or use a mock already injected into the class under test.
3. Choose the right syntax: `when(...).thenThrow(...)` for value-returning methods, `doThrow(...).when(...)` for void methods or when avoiding real implementation calls on spies.
4. Configure an exception instance if checking message/cause; use a class when only the exception type is needed.
5. Invoke the class under test to traverse the error branch.
6. Use `assertThrows` or the check appropriate to an asynchronous API.
7. Verify the exposed message, cause, and business state.
8. Verify that the collaborator was called properly and unwanted side effects did not occur.
9. Run tests independently and ensure each test creates and configures its own dependencies.

## Conclusion

Mockito lets you simulate collaborator failures in a controlled way. Use `thenThrow` for value-returning methods, `doThrow` for void methods, and for spy scenarios where calling the real implementation during configuration must be avoided. Combine stubbing with `assertThrows`, cause inspection, and side-effect verification to prove the class under test handles errors according to its contract.

A mock can create the exact failure scenario a test needs, but the value of the test lies in the reaction of the service or class under test. Keeping tests focused on that reaction makes error branches clear, stable, and easy to maintain.

