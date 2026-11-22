# Naming Custom Exceptions by Failure Condition and Abstraction Level in Java

When designing a **custom exception** in Java, the goal is not merely to name a class that extends `Exception` or `RuntimeException`. The exception name should help the reader answer two questions: **"What failed?"** and **"Which layer is responsible for interpreting that failure?"**. A good name clarifies contract behavior, recovery strategy, and the meaning of `catch`; a generic name or one that leaks implementation details can make an API difficult to use, maintain, and evolve across infrastructure changes.

For example, in an order system:

- `OrderNotFoundException`: the order requested by the caller could not be found.
- `OrderAlreadyPaidException`: the payment operation was rejected because the order has already been paid.
- `PaymentDeclinedException`: the payment request was declined according to the business outcome of the payment process.
- `PaymentGatewayUnavailableException`: the payment gateway could not be reached or used to determine the outcome.

All of the classes above can be **illustrative application-defined names**, not built-in Java classes. They communicate different situations. In particular, "declined" and "unable to call the system to determine the outcome" are **not equivalent**: retry policies and user notifications may differ.

This lesson guides you on how to choose exception names based on failure conditions and **abstraction level** (domain, application/service, infrastructure, API boundary), when to reuse standard exceptions, when to create dedicated classes, how to choose between checked and unchecked, preserving the root cause, designing constructors, and testing behavior. Examples use Java 17+.

## 1. What is a custom exception and why does it need a clear name?

A custom exception is a class defined by an application or library that extends a class in the `Throwable` hierarchy, typically `Exception` or `RuntimeException`:

~~~java
// A checked exception type.
class OrderNotFoundException extends Exception {
    OrderNotFoundException(String message) {
        super(message);
    }
}

// An unchecked exception type.
class OrderAlreadyPaidException extends IllegalStateException {
    OrderAlreadyPaidException(String message) {
        super(message);
    }
}
~~~

A dedicated name is useful when the caller needs to **distinguish a meaningful failure case** from others. For example, the caller can display "order not found" for `OrderNotFoundException`, while blocking duplicate payment for `OrderAlreadyPaidException`.

Conversely, if a method merely receives a negative argument when the contract requires a non-negative value, a standard `IllegalArgumentException` is usually sufficient:

~~~java
static void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity phải dương");
    }
}
~~~

A `BadQuantityException` class is not automatically better if it does not add contract semantics, classification behavior, or useful information. Creating a custom exception requires a concrete design reason, avoiding the creation of many types just so their names look "business-oriented".

**Principle:** an exception name is part of the **API language**, not just a label for a log message. When it is exposed from a library or module, client classes can use that exact exception type in `catch`, tests, or documentation.

## 2. Naming by failure condition: "what happened?"

A good name typically expresses an **unexpected state or outcome**, tied to a specific object or operation:

| Situation | Name to consider | Overly vague name |
| --- | --- | --- |
| Requested order not found | `OrderNotFoundException` | `NotFoundError`, `DataException` |
| Paying an already paid order again | `OrderAlreadyPaidException` | `ProcessException`, `FailException` |
| Out of stock during ordering | `InsufficientInventoryException` | `StockErrorException`, `SomethingWrongException` |
| Failed to load application configuration | `ConfigurationLoadException` | `FileErrorException`, `ServiceException` |
| Session has expired | `SessionExpiredException` | `ExpiredException` |
| Unable to authorize access | `AuthorizationDeniedException` | `SecurityProblemException` |
| Order is locked and cannot be modified | `OrderLockedException` | `UpdateException` |
| Payment gateway service is unavailable | `PaymentGatewayUnavailableException` | `HttpException` at the business layer |

Each name "to consider" is an **illustrative design option**, and should be checked against the project's domain language. If the standard API already has a suitable type, prefer reusing it instead of creating a new class.

Commonly useful keywords in names:

- **`NotFound`**: the target object does not exist according to the lookup contract; do not use it for every connection error that prevents the lookup operation from completing.
- **`Already...`**: the operation violates an already-completed state, e.g., `OrderAlreadyPaidException`.
- **`Invalid...`**: invalid data rule or state, though it must specify *what* is invalid.
- **`Expired`**: a session/token resource has expired over time, not just a "system error".
- **`Unavailable`**: a dependency/system is temporarily unavailable, which is not synonymous with the request being rejected for business reasons.
- **`Load`/`Parse`/`Decode`**: failure of a conversion/loading operation within an abstraction; distinguish malformed data from inaccessible data.

A good name does not have to be long. `OrderNotFoundException` is already clear within a specific domain; `OrderLookupFailedDueToInternalDatabaseConnectivityException` typically both leaks implementation and is unstable.

## 3. What is the "abstraction level" of an exception?

A system typically has multiple layers:

~~~text
API / UI
   ↓
Application / Service
   ↓
Domain / Business Rules
   ↓
Infrastructure / Database / Files / Network
~~~

This diagram is a common organizational example, not a mandatory structure for every application. The same incident can be **interpreted differently** as it crosses layer boundaries.

For example, when access to a configuration file is denied:

1. Infrastructure calls `Files.readString(path)` and receives an `IOException` or an appropriate subclass.
2. The configuration loading layer knows its operation is **loading application configuration**, so it can wrap it into `ConfigurationLoadException`, keeping `IOException` as the cause.
3. The API/UI layer decides how to report it to the user, potentially logging the full internal error and returning a safe message.

At the infrastructure layer, `IOException` already has meaning. At the configuration layer, stating only `IOException` may be too detailed or too narrow for the contract's meaning. However, crossing a layer boundary does not automatically require wrapping; only wrap when it **adds valuable new semantics**.

### 3.1. Domain exceptions

Names emphasize business rules or concepts:

~~~java
// Illustrative names in the order domain.
class OrderAlreadyPaidException extends IllegalStateException { /* ... */ }
class InsufficientInventoryException extends RuntimeException { /* ... */ }
~~~

Here, the exception type should not depend on the detail of whether data is stored in PostgreSQL, MongoDB, a CSV file, or an external API. If you replace the storage backend and the domain name still holds true, that is a sign of a reasonable abstraction level.

### 3.2. Application/service exceptions

Names express that an operation provided by a service has failed:

~~~java
// Illustrative names at the service layer.
class ConfigurationLoadException extends RuntimeException { /* ... */ }
class ReportGenerationException extends Exception { /* ... */ }
~~~

The caller knows that **loading configuration** or **generating a report** failed, while detailed errors from the parser, file, network, or renderer can reside in `cause`.

### 3.3. Infrastructure exceptions

Names can reflect a technical dependency at that exact layer, such as `StorageUnavailableException` in a storage adapter. However, not every `IOException`/`SQLException` needs a dedicated wrapper. Keep the standard exception when it already sufficiently represents the contract that callers at that layer need to handle.

### 3.4. API boundary

At a REST/HTTP, GraphQL, or UI boundary, it may be necessary to translate internal exceptions into a **structured response** or a user-friendly message. An HTTP status/error code does not have to be the exception class name. For example, `OrderNotFoundException` may be mapped to HTTP 404 in a specific API, but the domain class should not by default be named `Http404Exception` just for controller convenience.

**Do not assume** that every `NotFound` is always HTTP 404, every validation error is HTTP 400, or every exception corresponds to a fixed status; mapping is the policy of each individual API.

## 4. Name by failure condition, not by the throw statement

Consider the method:

~~~java
static void pay(Order order) {
    if (order.isPaid()) {
        throw new OrderAlreadyPaidException(order.id());
    }
    // Perform the valid payment operation.
}
~~~

This is an **illustrative snippet**, requiring appropriate definitions of `Order` and `OrderAlreadyPaidException`. The rule here is "an already-paid order cannot be paid again". The name `OrderAlreadyPaidException` describes the **condition**, not the "throw" operation.

Poorly descriptive names:

- `PayException`: only says it is related to payment, without stating the reason.
- `InvalidException`: does not say what is invalid.
- `RuntimeFailureException`: reflects a technicality rather than a contract.
- `Exception1`, `CustomException`, `MyException`: carry no domain meaning.
- `OrderException`: can be used as a grouping parent class, but is usually too broad if thrown directly for every specific error.

A parent class `OrderException` **can be reasonable** when callers need to catch an entire group of domain errors, though subclasses should still reflect individual situations. Avoid creating a deep inheritance hierarchy just to mirror the entire business diagram.

## 5. Appropriate granularity: specific enough to be useful

There are two bad extremes:

**Too broad:** having only `ApplicationException` and passing different messages for all cases. Callers have to compare message strings to decide how to handle them:

~~~java
// Illustrative code that should not be used to classify errors.
catch (ApplicationException ex) {
    if ("NOT_FOUND".equals(ex.getMessage())) {
        // Fragile: depends on string message.
    }
}
~~~

**Too narrow:** creating a class for every statement or every infrastructure detail, such as `PostgresQuery42TimeoutOnOrdersTableException`. When switching databases, the exception type no longer expresses a stable contract, even though the caller only needs to know that the storage operation is temporarily unavailable.

Questions to decide whether a separate subtype is needed:

1. **Does the caller take a different action?** For example, out of stock prompts choosing another quantity, while payment gateway error notifies to retry.
2. **Is this a stable condition of the API contract?** Or is it just a bug/internal detail that might disappear during refactoring?
3. **Can "when it is thrown" be documented accurately?** If not, the type name may be too vague.
4. **Does the consuming layer understand that name?** If the caller is the order domain, a name containing a vendor SDK may be at the wrong abstraction level.
5. **Is a standard type already sufficient?** For null, index, or invalid state, Java already has `NullPointerException`, `IndexOutOfBoundsException`, `IllegalArgumentException`, `IllegalStateException`.

Prefer **fewer types with clearly distinct meanings** over a massive exception tree that offers no practical handling differences.

## 6. Runnable Java 17+: `OrderNotFoundException` and `OrderAlreadyPaidException`

This example separates two different domain situations: a lookup with no result and a payment operation rejected due to the current state.

Save as `OrderNamingDemo.java`:

~~~java
public class OrderNamingDemo {
    enum Status { DRAFT, PAID }

    static final class Order {
        final String id;
        Status status = Status.DRAFT;

        Order(String id) {
            this.id = id;
        }
    }

    static final class OrderNotFoundException extends Exception {
        OrderNotFoundException(String orderId) {
            super("Không tìm thấy đơn " + orderId);
        }
    }

    static final class OrderAlreadyPaidException extends IllegalStateException {
        OrderAlreadyPaidException(String orderId) {
            super("Đơn " + orderId + " đã thanh toán");
        }
    }

    static Order find(String orderId) throws OrderNotFoundException {
        if (!"A-17".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new Order(orderId);
    }

    static void pay(Order order) {
        if (order.status == Status.PAID) {
            throw new OrderAlreadyPaidException(order.id);
        }
        order.status = Status.PAID;
    }

    public static void main(String[] args) throws OrderNotFoundException {
        Order order = find("A-17");
        pay(order);
        System.out.println("Trạng thái: " + order.status);
        try {
            pay(order);
        } catch (OrderAlreadyPaidException ex) {
            System.out.println("Nghiệp vụ: " + ex.getMessage());
        }
        try {
            find("B-42");
        } catch (OrderNotFoundException ex) {
            System.out.println("Tra cứu: " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OrderNamingDemo.java
java OrderNamingDemo
~~~

Exact stdout:

~~~text
Trạng thái: PAID
Nghiệp vụ: Đơn A-17 đã thanh toán
Tra cứu: Không tìm thấy đơn B-42
~~~

### Analyzing the naming decisions

- **`OrderNotFoundException`**: represents a lookup result where no matching order exists. In the illustrative program, this class is a checked exception, so `find` declares `throws OrderNotFoundException`; the caller catches it or propagates the declaration.
- **`OrderAlreadyPaidException`**: represents the current state making the operation invalid; the example chooses to extend `IllegalStateException`, so it is an unchecked exception and the caller is not forced to `catch` it.
- The names of the two exceptions allow separating handling paths **without inspecting the text message**. This is the substantive benefit of dedicated exception types.
- `find` is a deterministic lookup simulator, and `pay` only changes state in memory. The program does not implement real payment processing, does not handle concurrent transactions, and does not prove idempotency of a payment API.
- If in a real application "not found" is an expected normal outcome, using `Optional<Order>` instead of throwing a checked exception may be more appropriate. This is an **API design choice**, with no single right answer.
- If "already paid" is treated as an idempotent successful outcome, the API can return the status instead of throwing `OrderAlreadyPaidException`. This lesson focuses on **naming once you have decided it is an exception**, rather than prescribing that this situation must always throw.

### Why use `extends IllegalStateException` instead of `extends RuntimeException`?

Both are valid for unchecked exceptions. Choosing `IllegalStateException` expresses that the error relates to the **state of the object or operation**, and allows callers who wish to catch `IllegalStateException` as a group if truly appropriate. In return, you must ensure the "disallowed state" semantics match the contract. If the project has a common domain hierarchy for clear reasons, another parent class may be chosen.

Do not decide the parent class merely by what sounds nice. The parent class is part of the type relationship and affects `catch`, so it should match both **semantics and checked/unchecked policy**.

## 7. Runnable Java 17+: wrapping I/O errors at the application configuration boundary

At the infrastructure layer, Java already has `IOException`; callers at the application layer care more about whether **loading configuration** succeeded. `ConfigurationLoadException` is a name tied to the responsibility of the upper layer.

Save as `ConfigurationBoundaryDemo.java`:

~~~java
import java.io.IOException;

public class ConfigurationBoundaryDemo {
    static final class ConfigurationLoadException extends RuntimeException {
        ConfigurationLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readFromStorage(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("tệp cấu hình không đọc được");
        }
        return "mode=prod";
    }

    static String loadConfiguration(boolean fail) {
        try {
            return readFromStorage(fail);
        } catch (IOException ex) {
            throw new ConfigurationLoadException(
                    "Không thể nạp cấu hình ứng dụng", ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("Giá trị: " + loadConfiguration(false));
        try {
            loadConfiguration(true);
        } catch (ConfigurationLoadException ex) {
            System.out.println("Tầng ứng dụng: " + ex.getMessage());
            System.out.println("Nguyên nhân kỹ thuật: "
                    + ex.getCause().getClass().getSimpleName()
                    + " - " + ex.getCause().getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ConfigurationBoundaryDemo.java
java ConfigurationBoundaryDemo
~~~

Exact stdout:

~~~text
Giá trị: mode=prod
Tầng ứng dụng: Không thể nạp cấu hình ứng dụng
Nguyên nhân kỹ thuật: IOException - tệp cấu hình không đọc được
~~~

**Key takeaways:**

1. `readFromStorage` declares `throws IOException` because that is the technical contract of the read step.
2. `loadConfiguration` translates it into an **application-meaningful** error: unable to load configuration. It does not use a name like `FileReadErrorException` at the higher abstraction.
3. The `(message, cause)` constructor preserves `IOException` so `getCause()` can be queried and the full stack trace printed during debugging.
4. Callers of `loadConfiguration` can catch a stable application-level error type even if the configuration storage details change.
5. `ConfigurationLoadException` in the example is unchecked because it extends `RuntimeException`. This is an illustrative decision. If callers must perform a compile-time checked recovery step, the project may choose a checked exception.
6. `readFromStorage` uses simulated values so stdout does not depend on a real file. In production code, logic must handle `IOException` from actual reading APIs as well as logging and data security policies.

**Do not wrap if it adds no new value.** If the abstraction calling `readFromStorage` already declares `IOException` and callers are handling that exact type, adding `new RuntimeException("read failed", ex)` just to rename it can make the contract less clear.

## 8. Name by failure type or failed operation?

Both naming approaches can be useful:

- **By condition:** `OrderNotFoundException`, `SessionExpiredException`, `InsufficientInventoryException`.
- **By operation:** `ConfigurationLoadException`, `ReportGenerationException`, `InvoiceExportException`.

Choose the approach that better reflects what **the caller actually wants to know**. With `OrderNotFoundException`, the caller distinguishes not found from being unable to reach the system. With `ReportGenerationException`, an operation-based name is acceptable if all report generation failures share a similar handling policy at the consuming layer.

However, `ProcessFailedException` or `OperationException` identifies neither the operation nor the condition. If a class's contract cannot be distinguished from its name, reconsider whether it should exist at all.

Decision diagram:

~~~text
Is there a specific failure case?
    |
    +-- Yes --> Does the caller need to distinguish and handle it separately?
    |             |
    |             +-- Yes --> Name clearly by the condition.
    |             |
    |             +-- No --> Use a standard exception or suitable parent class.
    |
    +-- No --> Did an operation at the current abstraction fail?
                  |
                  +-- Yes --> Name by operation/abstraction level if valuable.
                  |
                  +-- No --> Reconsider whether a custom exception is needed.
~~~

The diagram is only a **thinking guide** and does not replace analyzing the product's contract and error policy.

## 9. Distinguishing business outcomes from infrastructure errors

A dangerous mistake is using the same type for two non-equivalent conditions.

For example, with payments:

| Condition | Illustrative name | Potentially different response |
| --- | --- | --- |
| Bank/payment gateway confirms the transaction was declined | `PaymentDeclinedException` | Display a safe reason; request another payment method |
| Payment gateway does not respond | `PaymentGatewayUnavailableException` | Check transaction status before retrying; do not claim payment was declined |
| Order was already paid previously | `OrderAlreadyPaidException` | Avoid duplicate charging; return appropriate status |
| Invalid request data | `IllegalArgumentException` or API validation type | Fix input data before calling again |

**Important warning:** "payment gateway timeout" does not necessarily prove the transaction was not executed. If retrying could create a duplicate payment, safe handling requires idempotency/reconciliation mechanisms with the payment system. This example shows that **exception names do not just affect logs, they also affect business decisions**.

Do not use `PaymentFailedException` for every outcome if the caller needs to distinguish declined, already processed, and unknown status. Conversely, if the API genuinely exposes only one high-level error and all causes share the exact same handling, a general class with a cause can be reasonable.

## 10. Boundary between input validation and domain exceptions

Standard types like `IllegalArgumentException`, `IllegalStateException`, and `NullPointerException` are very useful when the contract does not require a dedicated type.

For example:

~~~java
static void setPageSize(int pageSize) {
    if (pageSize < 1 || pageSize > 500) {
        throw new IllegalArgumentException("pageSize phải từ 1 đến 500");
    }
}
~~~

If this is just a precondition of an internal method, there is no need to create `InvalidPageSizeException` in most cases. However, if a public API has a special notification policy or recovery path for a validation scenario, a dedicated type can be helpful.

How to decide:

- **Call precondition violation:** usually consider standard exceptions.
- **Specific domain rule/invariant:** consider a domain name if the caller needs to distinguish it.
- **An expected normal outcome:** consider the return type/`Optional`/result object instead of overusing exceptions.
- **A failed system dependency:** keep the standard exception or wrap at a high-level boundary.
- **Programming bug:** usually no need for a separate `UnexpectedBugException` class per location.

Avoid a structure where all errors are caught via `catch (Exception ex)` and rethrown as `BusinessException("failed")`; this can turn technical bugs into business errors and lose the classification operators need.

## 11. Choosing `Exception` vs `RuntimeException` by contract

Naming expresses the **failure condition**. Choosing the superclass determines **how Java checks it** at the call site:

| Characteristic | `extends Exception` (not under RuntimeException) | `extends RuntimeException` |
| --- | --- | --- |
| Classification | Checked | Unchecked |
| Is the caller forced by the compiler to catch or declare when it can escape? | Yes | No |
| Suitable when | The API needs to expose a condition with clear handling capability at the call boundary | Contract/state violation or project policy wants to propagate errors without forcing catch |
| Can use constructor `(message, cause)`? | Yes | Yes |
| Should it be named by domain/boundary? | Yes | Yes |

**There is no rule that "business errors are always checked" or "infrastructure errors are always unchecked".** For example, `OrderNotFoundException` can be checked or unchecked depending on the contract; a missing order can also be represented by `Optional.empty()`. A name expressing a condition does not have to encode the checked/unchecked choice.

Specific considerations:

1. Does the caller have a reasonable recovery path and do you want to **enforce recognizing** that case at compile time?
2. Is this API misuse or a situation that can occur even when the caller invokes it correctly?
3. Does the ecosystem/framework in the project have any constraints or conventions?
4. Changing a checked exception in a public API can force existing callers to update `catch`/`throws`; have you considered compatibility?
5. If using unchecked, are the error conditions documented clearly enough?

Do not push every domain error into `RuntimeException` just to avoid writing `throws`; nor turn every possible error into a checked exception that overloads API signatures.

## 12. What information should constructors provide?

A simple, useful custom exception typically supports a message and a cause:

~~~java
public class ConfigurationLoadException extends RuntimeException {
    public ConfigurationLoadException(String message) {
        super(message);
    }

    public ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a **complete class**, saved in `ConfigurationLoadException.java` if used directly. There is no need to mechanically write every constructor; only expose the overloads callers actually need.

When an error has stable metadata, you can add fields with contract meaning:

~~~java
public class OrderNotFoundException extends Exception {
    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Không tìm thấy đơn " + orderId);
        this.orderId = orderId;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

The code above is a complete class, using system-specific naming and an `orderId()` getter. For a broad API, you must decide whether to expose identifiers and what information to give the caller; **do not put sensitive data** such as payment details, tokens, passwords, or personal data into messages/logs just for debugging convenience.

If the error includes a `cause`, the constructor passes it to `super(message, cause)` instead of storing only `cause.getMessage()`, because a text string does not preserve the exception type, stack trace, or suppressed errors of the cause.

### Should an error code enum be exposed?

In an API requiring structured classification, a documented `ErrorCode` or result type can be used instead of creating countless exception subtypes. For example, errors sharing the same handling policy can be distinguished via `code()`; however, if callers typically write `catch (SpecificException)`, dedicated subtypes may be clearer.

**Do not use text messages as stable error codes.** Messages can be translated, edited, and enriched with context; such changes should not break caller logic.

## 13. Preserving the cause appropriately when crossing abstractions

A method can wrap a lower-layer exception to provide upper-layer semantics:

~~~java
// Illustrative within catch (IOException ex).
throw new ConfigurationLoadException(
        "Không thể nạp cấu hình ứng dụng", ex);
~~~

Application-layer consumers see `ConfigurationLoadException`; investigators can call `getCause()` to see the original `IOException`. This is **different from arbitrary renaming**:

~~~java
// Do not lose the cause:
catch (IOException ex) {
    throw new ConfigurationLoadException("Không thể nạp cấu hình ứng dụng");
}
~~~

The snippet above is valid if the `(String)` constructor exists, but the technical cause has been dropped from the cause chain. If there are information security requirements, manage user-facing presentation and internal logging rather than discarding all error details by default.

**Preserving the cause is not an excuse to wrap at every layer.** If a layer simply forwards an exception that already matches the declared contract, a wrapper may be unnecessary. Wrapping at multiple layers with the same `"failed"` message clutters logs without adding meaning.

When there are suppressed exceptions from `try-with-resources`, if the lower layer received them and that exception is used as the wrapper's cause, they remain attached to the cause. When investigating, check suppressed exceptions on the relevant layers, not just the outermost one.

## 14. Can exception names contain specific technologies?

**Yes, but only at the right abstraction level.**

In a PostgreSQL adapter, a technical name can make sense if the adapter's public API is tightly coupled to PostgreSQL. However, if a public domain/order API is designed to be storage-agnostic, propagating `PostgresConnectionRefusedException` directly to callers can lock the domain into the current implementation.

Example distinction:

~~~text
Infrastructure:
    SQLException("connection refused")
            |
            v
Application boundary:
    OrderRepositoryUnavailableException(..., cause)
            |
            v
Order service:
    unable to look up order in the current attempt
~~~

This diagram is illustrative; it is not mandatory for every layer to create a new exception object. Choose a responsible boundary to express a meaningful condition to the caller, and preserve the technical cause.

If the domain API **needs** to distinguish "order not found" from "lookup could not be performed", do not turn both into `OrderNotFoundException`. Failing to return a result due to a network error does not prove the order does not exist.

## 15. Naming groups and inheritance trees: keep it simple first

You can organize them as:

~~~java
// Illustrative naming skeleton.
class OrderException extends RuntimeException { /* ... */ }
class OrderAlreadyPaidException extends OrderException { /* ... */ }
class OrderLockedException extends OrderException { /* ... */ }
~~~

A `catch (OrderException ex)` can catch domain errors sharing the same superclass, while callers needing specific handling can catch the subtype. However, consider:

- Do the errors truly share the same **handling policy** at the broad catch site?
- Is the inheritance tree forcing unrelated conditions into the same group?
- Does it overlap with standard superclasses like `IllegalStateException`?
- Do you need to support both checked and unchecked? A single inheritance tree cannot be both checked and unchecked across two branches.
- Does the `OrderException` superclass name provide real practical value, or just add another layer?

Inheritance is not required to have good custom exception names. Many applications use independent exception classes and only create a hierarchy when there is genuine **shared handling value**.

## 16. Naming conventions and code readability

Several practical Java conventions:

1. **Class names use PascalCase**, e.g., `OrderNotFoundException`.
2. **The `Exception` suffix** helps readers and IDEs recognize the class's place in the exception hierarchy. This is a very common convention.
3. **Avoid the `Error` suffix** for normal application errors; `java.lang.Error` belongs to a branch with different semantics and is generally not a mechanism for reporting recoverable business errors.
4. Use **specific terms understood consistently by the team**. If the domain calls the object `Invoice`, do not inconsistently use `Bill` in one place and `Invoice` in another.
5. **Do not encode the entire error message** in the class name, e.g., `OrderWithIdMissingInDatabaseException`; the message and metadata can carry dynamic details.
6. Keep names **stable with the contract**. Names tied to a vendor or database easily become outdated when changing platforms.
7. For errors with the same condition across multiple contexts, consider one exception type + a clear field/code rather than duplicate classes differing only by operation name.

A codebase may have its own conventions; stay consistent with existing style, but do not sacrifice accuracy of error semantics just to fit a naming pattern.

## 17. When should `@throws` be documented?

JavaDoc documentation should clearly state the **throwing condition**, not merely repeat the exception name:

~~~java
/**
 * Pays an order that is in an eligible state.
 *
 * @param order the valid order to pay
 * @throws OrderAlreadyPaidException if the order has already been paid
 */
static void pay(Order order) {
    // Business implementation body.
}
~~~

This is illustrative and requires defining `Order` and `OrderAlreadyPaidException`. This documentation helps the caller know when the error occurs and whether to check the state before calling.

An unhelpful JavaDoc:

~~~java
/**
 * @throws OrderAlreadyPaidException when OrderAlreadyPaidException occurs
 */
~~~

The `@throws` tag is **documentation**, whereas the `throws SomeCheckedException` clause in the signature is **language syntax that affects compile-time checking**. For unchecked exceptions, you can document them with `@throws` even when the signature does not declare `throws`.

Keep the name, the condition in JavaDoc, the thrown type in code, and the tests synchronized. If the contract specifies `OrderNotFoundException`, do not implement a branch that throws `IllegalArgumentException` for that same case without a reason.

## 18. Anti-patterns that help spot wrong abstraction levels

### 18.1. Turning infrastructure errors into "not found"

~~~java
// Anti-pattern: do not treat a DB query error as proof that the object does not exist.
catch (SQLException ex) {
    throw new OrderNotFoundException("Không thấy đơn");
}
~~~

This snippet illustrates a **semantically wrong** decision; it also depends on the corresponding constructor. If the query failed because the database is offline, you have not determined whether the order exists. Use `OrderLookupException`, `RepositoryUnavailableException`, or a type matching the contract and preserve `cause`, instead of asserting `NotFound`.

### 18.2. Conflating payment declined with timeout

~~~text
PaymentDeclinedException
    != PaymentGatewayUnavailableException
~~~

Being declined is a **known outcome**; being unable to reach the gateway is the **absence of a determined outcome**. In a billing system, confusing the two can lead to incorrect retries.

### 18.3. Overusing the name `ValidationException`

`ValidationException` can be reasonable if the API unifies multiple validation errors into one type with a list of fields/violations. However, if every `ValidationException` only has a free-form message, callers struggle to separate "invalid email", "missing code", and "limit exceeded". When structured handling is needed, consider an object containing a list of violations rather than creating an exception subtype for every field.

### 18.4. Renaming infrastructure per line of code

`JdbcQueryFailedAtLine52Exception` reflects a fragile implementation location, not a stable abstraction. The stack trace/cause already provides the technical location; the type name should contribute distinct **semantic meaning**.

## 19. Testing exception names as part of the contract

Do not test only the message. You should have tests for:

- **Right exception type for the right condition:** non-existent order -> `OrderNotFoundException`, already paid order -> `OrderAlreadyPaidException`.
- **Not throwing that exception under other conditions:** a database timeout must not report "order not found" without verifying the result.
- **Cause is preserved:** if the service layer wraps `IOException`, `getCause()` must be the original technical exception (or a documented intermediate wrapper).
- **Structured information:** if the exception has `orderId()`, the field must match the input id and not be mixed only into the message.
- **Checked/unchecked distinction matches the contract:** the compiler requires catch-or-declare for checked exceptions; unchecked does not.
- **Compatibility:** when adding or changing error types in a public API, callers handling by type may need updates.

Manual test example without external libraries:

~~~java
// Illustrative within a method that has access to OrderNamingDemo.
try {
    OrderNamingDemo.find("B-42");
    throw new AssertionError("Dự kiến phải ném OrderNotFoundException");
} catch (OrderNamingDemo.OrderNotFoundException ex) {
    System.out.println("Đúng loại: " + ex.getClass().getSimpleName());
}
~~~

In the `OrderNamingDemo` source in section 6, the nested classes have package-private access; place the test snippet in the same package or adjust modifiers when extracting into a public API. This is a **non-standalone illustrative snippet**, as it depends on code from the previous example.

The check targets the **exception type**. If you only assert the string `"Không tìm thấy"`, a wrong exception type could still pass by accidentally having a similar message.

## 20. When should you not create a custom exception?

Not every unsuccessful situation needs `throw`. Some alternatives:

| Situation | Potentially suitable option | Reason |
| --- | --- | --- |
| Looking up an object by id where non-existence is common | `Optional<Order>` or result type | Avoids forcing callers into an exceptional path for an expected outcome |
| Parsing user input with multiple violations | Result containing a list of `ValidationError` | Displays multiple errors at once instead of only the first error |
| Clearly invalid programmatic input | `IllegalArgumentException` | Standard exception already expresses the precondition |
| Index out of bounds | `IndexOutOfBoundsException` | Standard exception is already clear |
| Routine I/O task | `IOException` or standard subclass | Do not add a wrapper if the calling layer already accepts the I/O contract |
| Business flow that can wait/choose an option | Result object/enum with status | Caller handles every outcome explicitly |

Custom exceptions are best suited when **the error is truly exceptional within the specific contract** and the caller benefits from distinguishing it by type or metadata.

## 21. Naming checklist before publishing an API

Before creating or renaming an exception, ask yourself:

1. **What exact condition causes this exception type to be thrown?**
2. **Does the name clearly identify the failed domain object or operation?**
3. **Could the name mislead the reader into thinking an outcome was determined when in reality only the operation failed to complete?**
4. **Which abstraction does it belong to, and can callers at that layer understand it?**
5. **Does it leak unnecessary vendor, table, file path, HTTP status, or implementation details?**
6. **Is a standard exception or result object already sufficient?**
7. **Do callers need to handle it specifically by type? If not, can it be grouped reasonably?**
8. **Should it be checked or unchecked based on the caller's obligation?**
9. **Are `cause`, stack trace, and necessary diagnostic information preserved?**
10. **Do the message/metadata avoid exposing sensitive data?**
11. **Do JavaDoc `@throws` and tests state the exact same condition?**
12. **Will the name and contract still make sense if the implementation changes?**

If you cannot express the condition in a concrete sentence such as "thrown when the order is in PAID state and the API does not allow paying again", the custom exception name may be too broad or the problem may not be modeled properly yet.

## 22. Common mistakes

| Mistake | Why is it dangerous? | Better approach |
| --- | --- | --- |
| Naming `MyException`, `CustomException`, `Exception1` | Communicates neither condition nor abstraction | Name after the failure case |
| Labeling every error `BusinessException` | Forces callers to parse vague text/codes | Group meaningfully or use a structured result |
| Calling a timeout `NotFoundException` | May falsely report that an object does not exist | Distinguish "no result" from "unable to look up" |
| Calling every payment failure `PaymentDeclinedException` | Easy to confuse timeout with declined | Separate known states from undetermined states |
| Wrapping `IOException` while dropping `cause` | Loses original stack trace/error type | `super(message, cause)` |
| Using exception classes with vendor names in domain APIs | Locks the abstraction to infrastructure details | Wrap at the boundary with a stable name |
| Creating a custom exception for every `IllegalArgumentException` | Bloats the API with little benefit | Use built-in types when sufficient |
| Choosing checked/unchecked purely by preference | Makes handling difficult for callers or causes them to miss catchable cases | Design by contract and recovery paths |
| Misusing `Error` for business errors | Violates `Throwable` hierarchy expectations | Extend `Exception`/`RuntimeException` appropriately |
| Using messages as control codes | Changing a message breaks logic | Use contracted types/codes |
| Wrapping errors at every layer with the same message | Long cause chains, noisy logs | Wrap only when adding new semantics |
| Names overly specific to SQL/file/line | Hard to change implementation | Express meaning at the current abstraction |

## 23. Self-check questions

**Question 1.** When an order lookup fails because the database is offline, should `OrderNotFoundException` be thrown?

**Answer:** Not just because the query failed. Failing to look up **does not prove** the order does not exist. Use an error type that expresses an unavailable dependency or a failed lookup operation, matching the abstraction.

**Question 2.** Do `OrderAlreadyPaidException` and `OrderNotFoundException` have the same meaning?

**Answer:** No. One is a payment state violation; the other is failing to find the object.

**Question 3.** Should an exception name be tied to an SQL table name or public API semantics?

**Answer:** In a public domain/application API, prefer stable semantics that callers understand. SQL details belong more appropriately in the infrastructure layer or the cause.

**Question 4.** Must every custom exception extend `RuntimeException`?

**Answer:** No. You can extend `Exception` to create a checked exception; the choice depends on the caller's catch/declare contract.

**Question 5.** Why can `ConfigurationLoadException` be better than `IOException` at an application boundary?

**Answer:** It explains that the **configuration loading operation** failed, without forcing the caller to understand whether the configuration source is a file, network, or other storage; `IOException` can be preserved as the cause.

**Question 6.** If no caller handles `InvalidPageSizeException` differently from `IllegalArgumentException`, should a separate class be created?

**Answer:** Usually not necessary, unless there is a special contract or metadata that makes a dedicated type useful.

**Question 7.** Should `ex.getMessage()` be used as a durable error code?

**Answer:** No. Use an exception type or a documented error code when classification is needed.

**Question 8.** When wrapping `IOException`, what should the custom exception constructor have?

**Answer:** It should accept `message` and `cause`, passing them to `super(message, cause)` to preserve diagnostic information.

**Question 9.** Is an exception named after an operation like `ReportGenerationException` always a wrong choice?

**Answer:** No. It is suitable when failure at that operation level is the unit of abstraction the caller needs to handle. A generic name like `OperationException` is what is usually hard to use.

**Question 10.** If an API treats "already paid" as an idempotent successful outcome, must it throw `OrderAlreadyPaidException`?

**Answer:** No. When the situation is a valid outcome under the contract, it can return the appropriate status. The choice of exception depends on the API semantics.

## 24. References

- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): checked exception constructors and relationship with `Throwable`.
- [Java SE 17 API — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): unchecked exceptions, message/cause constructors.
- [Java SE 17 API — `IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html) and [`IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): two common standard types usable instead of creating custom classes.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, stack trace, suppressed exceptions, and diagnostic methods.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exception rules and handling.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): the `throws` clause of methods.

**Remember:** custom exceptions should be named after a **failure condition meaningful to the caller** and the **abstraction level exposing the error**. Use dedicated names when they aid classification/action; use standard exceptions when sufficient; avoid vague names or leaking infrastructure; and preserve `cause` when wrapping so technical root causes are not lost.
