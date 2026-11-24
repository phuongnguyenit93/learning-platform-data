# Preserving Cause When Wrapping Errors at the Spring Layer

In a Spring application, an error often passes through multiple layers before reaching its final handler. For example, a JDBC driver may throw `SQLException`, the repository layer translates it into `DataAccessException`, and then the service layer adds business context before returning an error to the controller.

When a layer catches an exception and creates a new exception, it must preserve the original exception as the **cause**. The cause preserves the technical root cause and original stack trace, helping pinpoint where the error began. If you only create a new exception with a message without passing the cause, the cause chain is broken and critical information may be lost.

The core principle is: when translating exception types or adding context at a layer boundary, create the new exception with the caught exception as the cause. If there is no need to change the error type or add information, you can rethrow the original exception.

## 1. Exception Wrapping and Cause in Java

Java supports exception chaining through `Throwable`'s `cause` property. A new exception can hold the old exception as its cause:

~~~java
try {
    repository.save(order);
} catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order " + order.getId(),
        ex
    );
}
~~~

Custom exception constructor:

~~~java
public class OrderPersistenceException extends RuntimeException {

    public OrderPersistenceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Here:

- `OrderPersistenceException` is a persistence-layer error understood by the caller.
- `SQLException` is the original technical cause.
- The new message adds the order ID to provide diagnostic context.
- The stack trace of the cause can still be retrieved and displayed.

`Throwable` provides constructors accepting both `message` and `cause`. This is the approach to use when creating exception wrappers.

## 2. Why Preserve the Cause?

An exception usually contains more information than just a message:

- The original error type, such as `SQLException`, `IOException`, or a persistence library error.
- The stack trace where the error actually originated.
- Further causes if the error was already wrapped across multiple layers.
- Error codes, `SQLState`, vendor codes, or diagnostic data specific to the original exception.
- Additional information in framework or library subclasses.

If only the message is kept, upper layers may know the operation failed without knowing the specific reason. This makes distinguishing data errors, connection errors, configuration errors, and programming bugs harder.

Example to avoid:

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order: " + ex.getMessage()
    );
}
~~~

This creates a new exception without linking it to `SQLException`. The new stack trace only shows where the wrapper was created; the original exception details are no longer in the cause chain.

Way to preserve the cause:

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order " + orderId,
        ex
    );
}
~~~

The message provides business context, while the cause preserves the technical reason.

## 3. How Does the Cause Chain Work?

An error can be wrapped across multiple layers:

~~~text
Database driver
    |
    v
SQLException
    |
    v
DataAccessException
    |
    v
OrderPersistenceException
    |
    v
OrderServiceException
    |
    v
Exception handler
~~~

Each wrapper holds the lower layer's exception as its cause. When inspecting the stack trace or calling `getCause()`, you can trace the chain from the high-level error down to the original error.

Example:

~~~java
try {
    jdbcOperation();
} catch (SQLException ex) {
    DataAccessException dataAccess =
        new DataAccessResourceFailureException(
            "Database operation failed",
            ex
        );

    throw new OrderPersistenceException(
        "Unable to save order",
        dataAccess
    );
}
~~~

The cause chain looks like:

~~~text
OrderPersistenceException
  cause -> DataAccessResourceFailureException
              cause -> SQLException
~~~

In practice, it is not necessary to wrap exceptions at every layer. Create a wrapper only when that layer needs to switch abstractions or add valuable context.

## 4. Use a Constructor Taking Cause Instead of Message Alone

When creating a custom exception, provide a constructor accepting both `message` and `cause`:

~~~java
public class OrderServiceException extends RuntimeException {

    public OrderServiceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

If you need to support cases without a cause, you can add another constructor:

~~~java
public OrderServiceException(String message) {
    super(message);
}
~~~

Then, where the error is caught:

~~~java
try {
    orderRepository.save(order);
} catch (DataAccessException ex) {
    throw new OrderServiceException(
        "Could not save order " + order.getId(),
        ex
    );
}
~~~

Do not omit the cause just because the new exception already has a readable message. The message and the cause serve two different purposes: the message explains the current layer's context; the cause explains the reason for the prior error.

## 5. When Should You Rethrow the Original Exception?

Not every `catch` block needs to create a wrapper. If the current layer has no new information, does not need to change the exception type, and does not perform recovery handling, it can rethrow the same exception:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    if (shouldRetry(ex)) {
        retryLater();
    } else {
        throw ex;
    }
}
~~~

Rethrowing the same exception object preserves the original type, cause chain, and stack trace.

Some principles:

- **Rethrow the original exception:** when there is no need to switch abstractions or add context.
- **Wrap with cause:** when the current layer needs to provide a more appropriate exception type or add useful information.
- **Handle and do not rethrow:** only when the error has been fully handled according to the application's contract.
- **Do not swallow errors:** avoid catching and ignoring or returning default values that mask failures.

If you only want to log and rethrow, use `throw ex` in the same `catch` block. Avoid creating unnecessary wrappers just to add a log statement.

## 6. Using initCause When No Suitable Constructor Exists

`Throwable` provides the `initCause(Throwable cause)` method to set the cause after creating an exception.

~~~java
SQLException original = obtainSQLException();

OrderPersistenceException wrapped =
    new OrderPersistenceException("Cannot save order");

wrapped.initCause(original);

throw wrapped;
~~~

This is useful with older exception classes that lack a constructor taking a cause. However, if you can design custom exceptions, prefer the constructor:

~~~java
new OrderPersistenceException("Cannot save order", original)
~~~

Cause can only be set according to `Throwable` rules; calling `initCause` when the cause was already initialized or set can throw `IllegalStateException`. Do not call `initCause` out of habit when the constructor already accepts a cause.

## 7. Built-In Spring Exceptions Supporting Cause

Many exceptions in Spring are designed to preserve the cause via a constructor taking `Throwable`.

For example, the Spring DAO hierarchy uses `DataAccessException` as the base class for data access errors. This class belongs to Spring's runtime exception hierarchy and has constructors accepting both `message` and `cause`.

Some common subclasses:

- `DataAccessResourceFailureException`: failure accessing a data resource.
- `DataIntegrityViolationException`: constraint or data integrity violation.
- `DuplicateKeyException`: duplicate key conflict.
- `InvalidDataAccessApiUsageException`: invalid usage of a data access API.

Example of creating an exception in Spring's abstraction:

~~~java
throw new DataAccessResourceFailureException(
    "Cannot reach the reporting database",
    sqlException
);
~~~

When using an appropriate Spring exception, pass the cause into the constructor rather than creating a generic `RuntimeException` containing only a message.

## 8. Exception Translation at the Spring DAO Layer

An important goal of Spring DAO is translating persistence-technology-specific exceptions into a consistent `DataAccessException` hierarchy.

For example, a JDBC driver throws `SQLException`. `JdbcTemplate` uses exception translation to convert this error into an appropriate subclass of `DataAccessException`.

~~~java
@Repository
public class JdbcOrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void save(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.getId(),
            order.getStatus()
        );
    }
}
~~~

When a JDBC operation fails, `JdbcTemplate` performs translation via `SQLExceptionTranslator`. The thrown exception belongs to the `DataAccessException` hierarchy; the original JDBC exception is usually preserved in the cause chain.

As a result, the service layer can handle errors using Spring's abstraction without depending directly on each JDBC driver's specific exception types.

Do not manually catch `SQLException` and create a `DataAccessException` containing only a message if the framework already has a suitable translation mechanism. Using `JdbcTemplate` and corresponding abstractions keeps error classification consistent.

## 9. Exception Translation with @Repository

Spring supports translating exceptions from persistence technologies on beans annotated with `@Repository` through the persistence exception translation infrastructure when configured.

Example:

~~~java
@Repository
public class JpaOrderRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public void save(Order order) {
        entityManager.persist(order);
    }
}
~~~

When `PersistenceExceptionTranslationPostProcessor` is registered, Spring can apply an interceptor to translate certain persistence exceptions into `DataAccessException`.

Error translation depends on the configured translator and the exception type thrown by the provider. A good translation preserves the original exception as the cause so upper-layer code can handle errors via Spring's abstraction while still investigating technical root causes.

Note: the `@Repository` annotation by itself is not a `catch` statement. Exception translation requires the corresponding Spring infrastructure to be enabled and the bean to pass through its proxy/interceptor mechanism.

## 10. Wrapping Errors When Moving from Repository to Service

Repository and service layers may use two different abstractions.

- The repository knows persistence details and can throw `DataAccessException`.
- The service understands the business meaning of the operation and can provide `OrderServiceException`.
- The controller or exception handler decides how to map errors into client responses.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public void placeOrder(Order order) {
        try {
            repository.save(order);
        } catch (DataAccessException ex) {
            throw new OrderServiceException(
                "Could not place order " + order.getId(),
                ex
            );
        }
    }
}
~~~

The service layer adds information about the business action—placing an order—and the order ID. The cause remains `DataAccessException`, which in turn can still hold the driver or persistence provider exception.

If the service has no separate abstraction or adds no useful context, it can let `DataAccessException` propagate instead of wrapping another layer.

## 11. Do Not Lose Cause When Creating Exceptions in Configuration or Bean Layers

Spring also uses exception wrappers to add information about beans, resources, or configuration.

For example, `BeanCreationException` has constructors supporting bean info and cause:

~~~java
try {
    initializeClient();
} catch (IOException ex) {
    throw new BeanCreationException(
        "paymentClient",
        "Failed to initialize payment client",
        ex
    );
}
~~~

The wrapper indicates which bean failed to initialize, while `IOException` remains the cause.

Similarly, when creating custom exceptions in a `BeanFactoryPostProcessor`, `FactoryBean`, or configuration component, pass the original exception if translating errors into Spring's abstraction.

This is especially useful because a bean creation failure can be wrapped further by other container layers before reaching the final log. The cause chain helps find the initial error rather than just seeing a message that a bean could not be created.

## 12. Cause Chain and NestedRuntimeException Methods

Spring Core has `NestedRuntimeException` as the base for many framework exceptions. This class provides several convenience methods for working with the cause chain:

- `getCause()`: standard `Throwable` method returning the direct cause.
- `getRootCause()`: returns the deepest cause found in the nested chain, or `null` if there is no cause.
- `getMostSpecificCause()`: returns the root cause if present, otherwise returns the current exception itself.
- `contains(Class<?> exType)`: checks whether the nested exception chain contains the requested exception type.

Example:

~~~java
try {
    service.perform();
} catch (NestedRuntimeException ex) {
    Throwable root = ex.getRootCause();
    Throwable mostSpecific = ex.getMostSpecificCause();

    if (ex.contains(SQLException.class)) {
        // The cause chain contains SQLException.
    }
}
~~~

These methods are convenient for diagnostics. However, when needing to inspect error types for business decisions, consider catching or classifying exceptions by appropriate abstraction rather than checking only the class name of the root cause.

## 13. Do Not Replace Cause with an Unrelated New Exception

A common mistake is catching an exception and creating another exception without passing the cause:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new IllegalStateException(
        "Gateway unavailable"
    );
}
~~~

The code above breaks the link to `IOException`. In logs, operators only see `IllegalStateException` created at the current layer.

Fix by passing the cause:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new IllegalStateException(
        "Gateway unavailable",
        ex
    );
}
~~~

If a dedicated business exception exists, use it:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new PaymentGatewayException(
        "Payment gateway call failed",
        ex
    );
}
~~~

The new exception name should reflect the abstraction or context of the handling layer, while the cause retains the original technical error.

## 14. Do Not Only Concatenate the Original Exception's Message

You can include the original exception's message in the new message, but that does not replace the cause.

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot save order: " + ex.getMessage(),
        ex
    );
}
~~~

Here both pieces of information are useful:

- The new message helps readers understand which business operation failed.
- The cause's message can appear in the stack trace.
- The cause preserves its exception type, stack trace, and specific metadata.

If you only concatenate `ex.getMessage()` without passing `ex`, the application still loses the cause chain.

Also avoid exposing raw technical messages in public responses to end users. Internal messages and client responses should be designed for their respective audiences.

## 15. Logging Exceptions Properly

When logging an exception, pass the `Throwable` object itself to the logger so the logging framework can record the stack trace and cause chain.

~~~java
try {
    orderService.placeOrder(order);
} catch (OrderServiceException ex) {
    log.error(
        "Failed to place order id={}",
        order.getId(),
        ex
    );
    throw ex;
}
~~~

Avoid logging only the message:

~~~java
log.error("Failed to place order: {}", ex.getMessage());
~~~

The second approach usually omits the stack trace and cause chain, making investigation harder.

There is no need to re-log the full stack trace at every layer. If repository, service, controller, and global handler all log the same exception, the system may generate many duplicate records. Choose an appropriate handling boundary to log in full; other layers can add context via wrappers or let the exception propagate.

## 16. Preserve Cause Without Exposing Internal Details to Clients

Preserving the cause is an internal diagnostic requirement. It does not mean returning the entire cause chain to HTTP clients or users.

For example, a `SQLException` may contain table names, SQL statements, server addresses, or system structure details. These details may be useful in internal logs but should not automatically appear in public responses.

An exception handler can build a safe response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderServiceException.class)
    public ResponseEntity<ProblemDetail> handle(
            OrderServiceException ex) {

        ProblemDetail problem =
            ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR
            );

        problem.setTitle("Unable to place order");
        problem.setDetail(
            "The order could not be processed."
        );

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(problem);
    }
}
~~~

The cause still exists inside the exception for internal logging or observability. The response only contains information selected for the client.

Do not return `ex.getCause().getMessage()` by default, especially for persistence, connection, or external library errors.

## 17. Cause Differs from Suppressed Exceptions

Java has two mechanisms that often appear in stack traces:

- **Cause:** the reason the current exception was created or thrown; accessed via `getCause()`.
- **Suppressed exception:** secondary errors arising while handling or closing resources when another exception had already occurred; accessed via `getSuppressed()`.

Try-with-resources example:

~~~java
try (InputStream input = openFile()) {
    process(input);
}
~~~

If `process` throws `IOException` and `close()` also throws `IOException`, the error in `process` is typically the primary exception; the resource-closing error is attached as a suppressed exception.

When wrapping the primary exception, keep that primary exception as the cause. Its suppressed exceptions remain accessible via `getSuppressed()`.

Do not confuse preserving the cause with manually collecting every secondary exception as a cause. The two relationships have different meanings.

## 18. Cause Chain and Transaction Rollback Rules

In Spring transactions, the thrown exception type can affect rollback decisions.

Under common default `@Transactional` rules:

- `RuntimeException` and `Error` trigger transaction rollback.
- Checked exceptions do not automatically trigger rollback by default.

Example:

~~~java
@Transactional
public void placeOrder(Order order) {
    try {
        repository.save(order);
    } catch (SQLException ex) {
        throw new OrderServiceException(
            "Cannot place order",
            ex
        );
    }
}
~~~

`OrderServiceException` in the example is a `RuntimeException`, so the transaction typically rolls back by default.

If the wrapper is a checked exception, review rollback rules:

~~~java
@Transactional(rollbackFor = OrderCheckedException.class)
public void placeOrder(Order order)
        throws OrderCheckedException {
    // ...
}
~~~

Preserving the cause does not decide rollback on its own. The Spring transaction interceptor primarily inspects the thrown exception type and configured rollback rules; the cause chain aids root-cause diagnosis without replacing those rules.

When changing exception types at a service boundary, verify whether the change alters the rollback behavior the application expects.

## 19. Avoid Repeated Wrapping Without Adding Value

An overly long wrapper chain can make stack traces hard to read if each layer merely changes the message without adding useful context.

Unnecessary example:

~~~text
RuntimeException
  -> RuntimeException
      -> RuntimeException
          -> SQLException
~~~

If layers all use the same generic exception type, readers struggle to see which abstraction actually matters.

Wrap when there is a specific reason:

- Translating from a technology exception to a Spring abstraction.
- Translating from persistence to a business error.
- Adding useful resource, bean, operation, or request IDs.
- Normalizing errors according to a module contract.

If there is no new value, let the original exception propagate. A short, meaningful cause chain is usually easier to maintain than many generic wrapper layers.

## 20. Complete Example: Preserving Cause Across Repository and Service

Service-layer exception definition:

~~~java
public class OrderServiceException extends RuntimeException {

    public OrderServiceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Repository using `JdbcTemplate`:

~~~java
@Repository
public class JdbcOrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.getId(),
            order.getStatus()
        );
    }
}
~~~

Service adding business context:

~~~java
@Service
public class OrderService {

    private final JdbcOrderRepository repository;

    public OrderService(JdbcOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void placeOrder(Order order) {
        try {
            repository.insert(order);
        } catch (DataAccessException ex) {
            throw new OrderServiceException(
                "Failed to place order " + order.getId(),
                ex
            );
        }
    }
}
~~~

If JDBC encounters an error, `JdbcTemplate` translates the exception to `DataAccessException`. The service then wraps that error in `OrderServiceException` and keeps `DataAccessException` as the cause.

When handling at an outer layer:

~~~java
try {
    orderService.placeOrder(order);
} catch (OrderServiceException ex) {
    log.error(
        "Order processing failed, orderId={}",
        order.getId(),
        ex
    );
}
~~~

The log contains the stack trace of `OrderServiceException` and the cause chain underneath. The API layer can map `OrderServiceException` to a safe response without exposing database details.

## 21. Investigation Checklist When Cause Is Lost

When a stack trace only shows a Spring-layer wrapper, check:

1. Does the new exception's constructor accept a `Throwable cause`?
2. Does the exception creation call pass the caught exception as the second argument?
3. Does any code only concatenate `ex.getMessage()` into the new message?
4. Did an intermediate layer catch an exception and throw another without passing the cause?
5. Did any framework translator or custom adapter create a new exception without retaining the original exception?
6. Does the logger receive the `Throwable` object or only a message?
7. Are there secondary exceptions in `getSuppressed()` that need separate inspection?
8. Did the new wrapper type change which rollback rule or exception handler is triggered?

You can inspect the cause directly in code:

~~~java
Throwable cause = wrappedException.getCause();

if (cause != null) {
    log.debug(
        "Underlying exception type: {}",
        cause.getClass().getName()
    );
}
~~~

When testing exception translation, verify the wrapper type, contextual message, and that the cause is preserved as the exact expected object or exception type.

## 22. Common Misconceptions

**Misconception 1: Including the original error's message in the new message is enough.**  
A message does not replace a cause. Pass the original exception to a constructor taking `Throwable`.

**Misconception 2: Every Spring layer must create a new wrapper.**  
Wrap only when needing to change abstractions or add helpful context. Otherwise, rethrow the original exception.

**Misconception 3: The cause chain determines transaction rollback.**  
Default rollback is primarily based on the thrown exception type and rollback rules; the cause supports diagnostics.

**Misconception 4: @Repository automatically catches every exception.**  
Exception translation requires the corresponding Spring infrastructure. `JdbcTemplate` and persistence translation have their own mechanisms for translating errors.

**Misconception 5: Logging the message is enough to investigate.**  
Pass the `Throwable` to the logger to keep the stack trace, cause chain, and suppressed info.

**Misconception 6: Preserving the cause means returning the cause to clients.**  
The cause serves internal diagnostics. APIs should return safe, user-appropriate information.

**Misconception 7: Suppressed exceptions are the same as cause.**  
Cause is the reason for the wrapper; suppressed exceptions are secondary errors attached separately, typically while closing resources.

## 23. Key Takeaways

- Exception wrapping is used to switch abstractions or add context as errors move across layers.
- The `Throwable(message, cause)` constructor is the clear way to preserve the original exception.
- If there is no need to change the error type or add context, rethrow the original exception.
- Do not create wrappers containing only a message or only concatenating `getMessage()` without a cause.
- Many Spring exceptions support constructors taking a cause; `DataAccessException` and its subclasses are key examples at the DAO layer.
- `JdbcTemplate` and persistence exception translation standardize technology errors into Spring abstractions; preserve the cause when writing custom translators or wrappers.
- `NestedRuntimeException` provides `getRootCause()`, `getMostSpecificCause()`, and `contains()` to aid diagnostics.
- Logging should accept the `Throwable` to record the stack trace and cause chain.
- The cause chain differs from suppressed exceptions.
- Do not expose internal cause details in public responses if they contain sensitive technical information.
- When changing exception types in `@Transactional` services, check rollback rules because the wrapper type can affect rollback behavior.
- Avoid repeated wrapping if each layer adds no valuable information or abstraction.

When wrapping errors at a Spring layer, choose an exception representing the current layer's proper abstraction, add helpful context, and always pass the caught exception as the cause. Then check logs, exception handlers, and transaction rules to ensure the root cause remains traceable throughout the entire processing flow.
