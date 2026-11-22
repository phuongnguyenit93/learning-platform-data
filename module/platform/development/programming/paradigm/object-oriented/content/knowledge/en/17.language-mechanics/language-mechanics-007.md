# Object string representations and diagnostic information in Java

> **Topic:** OOP → Language Mechanics.  
> **Goal:** Understand `Object.toString()`; distinguish developer diagnostics from user-facing or API data; design concise, safe diagnostic strings; use logging/exceptions appropriately; and test for sensitive-data leakage.

## 1. Why represent objects as strings?

While an application runs, we often need to know **which object is being processed and which parts of its state matter**. For example, when an order fails to transition from `CREATED` to `PAID`, a log line like:

~~~text
Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
~~~

is more useful than something like:

~~~text
com.example.Order@6d06d69c
~~~

The first identifies the order ID, status, item count, and trace ID. The second mostly shows the object's class and a hash value, often insufficient for debugging.

In Java, **`toString()`** is the fundamental method for providing an object's text representation. It is declared by `java.lang.Object` and inherited by all Java objects:

~~~java
public String toString()
~~~

A class can **override** `toString()` to display more meaningful information. Typical uses include **debugging, logging, and viewing objects in a debugger**.

**An essential distinction:** A `toString()` result need not be suitable for end users, does not promise JSON/XML formatting, and generally **should not** be an interchange format between systems. Use DTOs and suitable serializers for stable schemas.

## 2. What does `Object.toString()` produce by default?

The default implementation of `Object.toString()` is conceptually equivalent to:

~~~java
public String toString() {
    return getClass().getName() + "@"
            + Integer.toHexString(hashCode());
}
~~~

It produces the **fully qualified class name**, an `@` sign, and a hexadecimal representation of `hashCode()`.

For example:

~~~java
class Ticket {
    private final String code = "T-17";
}

Ticket ticket = new Ticket();
System.out.println(ticket);
~~~

It may print a string shaped like:

~~~text
Ticket@1b6d3586
~~~

The value after `@` **is not fixed** and may differ between runs. Do not treat it as a memory address, database ID, or domain identifier.

### Three misconceptions about the default string

1. `hashCode()` **is not a memory address**. Java's API does not guarantee that `@...` contains a physical address or heap location.
2. `Object.toString()` calls **`hashCode()`**, so a class overriding `hashCode()` may affect its default string representation.
3. Distinct objects **may share a hash code**. `hashCode()` is not a unique identifier or business trace key.

When an identity-based hash independent of overridden `hashCode()` is needed, Java provides `System.identityHashCode(object)`; even this value **is not guaranteed globally unique** and cannot substitute for business IDs.

### How does `toString()` relate to `println` and string concatenation?

Java converts objects to strings automatically in many contexts:

~~~java
Ticket ticket = new Ticket();

System.out.println(ticket);                // println(Object)
System.out.println("Ticket: " + ticket);   // phép nối chuỗi
String text = String.valueOf(ticket);       // String.valueOf(Object)
String formatted = String.format("%s", ticket);
~~~

These operations generally use `toString()` for non-`null` objects. Overriding one method can therefore improve readability across many debugging/logging situations.

Remember how null is handled:

~~~java
Object missing = null;

System.out.println(String.valueOf(missing)); // "null"
System.out.println(java.util.Objects.toString(
        missing, "<chưa có>"));               // "<chưa có>"
~~~

Do not call `missing.toString()` directly: it throws `NullPointerException`. `String.valueOf(Object)` and `Objects.toString(Object, String)` have their own null-handling conventions.

## 3. Practical Java 17 example: diagnosing an order

Suppose an `Order` holds business information and sensitive data:

- **Useful diagnostics:** order ID, status, item count, and trace ID.
- **Do not print:** customer email addresses or access tokens for external services.
- **Avoid including directly in `toString()`:** full processing histories, huge object collections, and data requiring database queries.

Implement `toString()` with a **deliberate field allowlist**, rather than including everything.

Create **`ObjectDiagnosticsDemo.java`** and run it on JDK 17 or later:

~~~java
import java.util.List;
import java.util.Objects;

// Enum mô tả các trạng thái hợp lệ.
enum OrderStatus {
    CREATED, PAID, CANCELLED
}

// Record chỉ chứa dữ liệu có thể hiển thị trong ví dụ này.
record OrderLine(String sku, int quantity) {
    OrderLine {
        Objects.requireNonNull(sku, "sku");

        if (!sku.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}

final class Order {
    private final String id;
    private final OrderStatus status;
    private final List<OrderLine> lines;
    private final String traceId;

    // Hai trường này được giữ cho nghiệp vụ, KHÔNG ghi ra toString.
    private final String customerEmail;
    private final String accessToken;

    Order(
            String id,
            OrderStatus status,
            List<OrderLine> lines,
            String traceId,
            String customerEmail,
            String accessToken) {

        this.id = requireSafeId(id, "id");
        this.status = Objects.requireNonNull(status, "status");
        this.lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
        this.traceId = requireSafeId(traceId, "traceId");

        this.customerEmail = Objects.requireNonNull(
                customerEmail, "customerEmail");
        this.accessToken = Objects.requireNonNull(
                accessToken, "accessToken");
    }

    private static String requireSafeId(String value, String name) {
        Objects.requireNonNull(value, name);
        if (!value.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    String id() {
        return id;
    }

    int itemCount() {
        return lines.size();
    }

    @Override
    public String toString() {
        return "Order{"
                + "id='" + id + '\''
                + ", status=" + status
                + ", itemCount=" + itemCount()
                + ", traceId='" + traceId + '\''
                + '}';
    }

    // API riêng dành cho hiển thị nghiệp vụ; không dựa vào toString().
    String customerMessage() {
        return "Đơn " + id + " hiện ở trạng thái " + status;
    }
}

public class ObjectDiagnosticsDemo {
    public static void main(String[] args) {
        Order order = new Order(
                "ORD-42",
                OrderStatus.CREATED,
                List.of(
                        new OrderLine("SKU-1", 2),
                        new OrderLine("SKU-2", 1)),
                "REQ-72",
                "khach@example.com",
                "secret-token-do-not-log");

        System.out.println(order); // Tự gọi toString().
        System.out.println("Kiểm tra: " + order);
        System.out.println(order.customerMessage());

        OrderLine line = new OrderLine("SKU-1", 2);
        System.out.println(line); // Record sinh toString() mặc định.
    }
}
~~~

Compile and run:

~~~bash
javac ObjectDiagnosticsDemo.java
java ObjectDiagnosticsDemo
~~~

Output:

~~~text
Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
Kiểm tra: Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
Đơn ORD-42 hiện ở trạng thái CREATED
OrderLine[sku=SKU-1, quantity=2]
~~~

### Why is this design useful?

- `Order.toString()` provides **the minimum useful investigation context**: which order, its status, line count, and trace.
- It omits `customerEmail` and `accessToken`. Even partially masked data must be evaluated against privacy policies; a safer default is **not including those fields**.
- `lines` is snapshotted with `List.copyOf` during construction, preventing external changes to the list structure. Because `OrderLine` is a record containing only `String` and `int` components, its sample values have no internal mutable state.
- `customerMessage()` expresses **customer-facing content** under its own contract, independent of developer diagnostic text.
- `traceId` is supplied by the processing flow and can link events across components. It **does not create correlation/tracing automatically** unless the system propagates and records trace IDs.

The example uses a **simple snapshot**. In real systems, consider normalized diagnostic DTOs/fields rather than making `toString()` navigate complex entities or lazy-loaded ORM objects.

## 4. Principles for a good `toString()` method

No single format is mandatory for every class. Instead, evaluate practical criteria:

| Criterion | Practice | Risk if ignored |
|---|---|---|
| **Concise** | Choose IDs, status, and a few error-relevant attributes | Excessive logs, poor readability, increased storage costs |
| **Meaningful** | `orderId`, `status`, `itemCount` | Only hashes or obscure fields |
| **Data-safe** | Use allowlists; exclude tokens, passwords, and unnecessary personal information | Leaks through logs and monitoring tools |
| **Free of side effects** | Do not change state, access networks, or write to databases | Inspecting an object causes unexpected behavior |
| **Null-tolerant** | Handle optional nullable fields | `NullPointerException` while logging |
| **Predictable performance** | Avoid lazy-loading relationships and huge object graphs | N+1 queries, blocked threads, enormous strings |
| **Not treated as a stable API format** | Allow wording changes to aid diagnostics | Consumers parsing `toString()` break after refactoring |
| **Concurrency-aware** | Use immutable snapshots or consistent synchronized state reads | String combines data from different instants |

A `toString()` method may be invoked frequently in consoles, IDEs, string formatting, object arguments to loggers, and exception messages. It should be **fast, safe, and unsurprising**.

### Information that should not appear in `toString()` by default

- Passwords, access/refresh tokens, API keys, session cookies, OTP codes, and internal secrets.
- Detailed personal information (email, phone, address, identifiers) without a clear logging justification.
- Raw request/response bodies that may contain user data.
- Entire large collections, files, images, blobs, or query results.
- Service objects, connections, ORM proxies, bidirectional graphs, or relationships that could trigger queries.

Even **IDs** may be sensitive in some systems. Follow data-classification policies; do not assume “not a password” means safe to log.

## 5. `toString()` for `record`, collection, and array types

### 5.1. Records generate strings from declared components

Java `record` automatically generates `toString()`, `equals()`, and `hashCode()` from components unless overridden. For example:

~~~java
record Coordinate(int x, int y) {}

System.out.println(new Coordinate(2, 5));
// Coordinate[x=2, y=5]
~~~

This is convenient for **Value Objects containing approved display data**. But beware of records containing sensitive fields:

~~~java
// RỦI RO nếu để record tự sinh toString().
record Credentials(String username, String password) {}

// System.out.println(new Credentials("alice", "secret"));
// Có thể làm lộ cả password trong biểu diễn mặc định.
~~~

You can override it:

~~~java
record SafeCredentials(String username, String password) {
    @Override
    public String toString() {
        return "SafeCredentials{username='" + username
                + "', password=<redacted>}";
    }
}
~~~

In production, consider hiding `username` too if it is sensitive. **Logging is not the only caller** of `toString()`: debuggers and exception handlers may also invoke it.

### 5.2. Collections may invoke each element's `toString()`

~~~java
List<OrderLine> lines = List.of(
        new OrderLine("SKU-1", 2),
        new OrderLine("SKU-2", 1));

System.out.println(lines);
// [OrderLine[sku=SKU-1, quantity=2],
//  OrderLine[sku=SKU-2, quantity=1]]
~~~

This is a conceptual example; actual output is usually **on one line**. Collection `toString()` may invoke `String.valueOf`/`toString()` for elements, so **one sensitive element can leak the whole collection's data**.

Avoid appending `list.toString()` to logs on hot paths when a collection contains thousands of elements. Log the `size`, failed-item counts, or a few approved IDs instead. Concurrent modifications may also affect iteration during string construction.

### 5.3. Arrays differ from collections

Java arrays do not default to a per-element string representation like `List`:

~~~java
int[] values = {1, 2, 3};

System.out.println(values);
// Chuỗi dạng [I@... (tên kiểu mảng + hash), không phải [1, 2, 3].

System.out.println(java.util.Arrays.toString(values));
// [1, 2, 3]
~~~

For nested arrays:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};

System.out.println(java.util.Arrays.toString(matrix));
// Các phần tử int[] được in dưới dạng tham chiếu [I@...

System.out.println(java.util.Arrays.deepToString(matrix));
// [[1, 2], [3, 4]]
~~~

`Arrays.deepToString` can also print large amounts of data; apply it only to information approved for logging in complex structures.

### 5.4. Cyclic references can cause recursive failures

Two objects can reference each other: `Parent → Child → Parent`. If `Parent.toString()` includes `child`, while `Child.toString()` includes `parent`, they can recurse indefinitely until `StackOverflowError`.

An example to avoid:

~~~java
class Parent {
    Child child;

    @Override
    public String toString() {
        return "Parent{child=" + child + "}";
    }
}

class Child {
    Parent parent;

    @Override
    public String toString() {
        return "Child{parent=" + parent + "}";
    }
}
~~~

Instead of printing the whole graph, print **related object IDs** or a *shallow representation*:

~~~java
// Hướng thiết kế tốt hơn (minh họa ý tưởng):
// "Parent{id=10, childId=20}"
// "Child{id=20, parentId=10}"
~~~

Avoid reflection-based printing of every field: sensitive data, reference cycles, lazy loading, and performance are hard to control.

## 6. `toString()` is not `equals()` or `hashCode()`

These three methods from `Object` have different purposes:

| Method | Returns | Typical purpose |
|---|---|---|
| `toString()` | `String` | Inspect/represent an object |
| `equals(Object)` | `boolean` | Test the class's defined equality semantics |
| `hashCode()` | `int` | Support hash structures such as `HashMap`/`HashSet` under the `equals` contract |

Overriding `toString()` **does not require** overriding `equals()` or `hashCode()` for diagnostic purposes. Conversely, custom `equals()` must ensure equal objects share `hashCode()` values.

Do not feed `toString()` output into `equals()` algorithms or use it as a default persistence key. Improving a debug format must not change business identity or collection behavior.

### Is `toString()` a stable format?

There is no universal guarantee that custom `toString()` representations are version-stable schemas. Some Java types document specific formats, but **read each API's contract** before relying on it.

For example:

~~~java
// KHÔNG NÊN:
database.save("order_dump", order.toString());

// KHÔNG NÊN:
String responseBody = order.toString(); // coi như JSON cho client

// NÊN:
// DTO -> JSON serializer có schema/validation/phân quyền rõ ràng.
~~~

For structured traces, log permitted fields such as `orderId`, `status`, and `traceId` separately through a structured logging system. For API communication, use DTOs with defined schemas.

## 7. Logging and diagnosing failures correctly

`System.out.println` is useful for quick demonstrations, but Java/Spring applications should use a **logging API** that supports levels, destinations, formatting configuration, and exception handling.

Useful diagnostic information often includes:

- **Events:** creating an order, rejecting payment, or completing a state transition.
- **Identifiers and correlation:** `orderId`, `traceId`, and assigned request/correlation IDs.
- **Relevant state:** current values and attempted actions.
- **Failure causes:** exception type, appropriate message, stack trace, and cause chain.
- **Time and context:** timestamps and environments, usually supplied by logging/tracing frameworks.

### 7.1. Java Util Logging (built into the JDK)

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

final class OrderDiagnostics {
    private static final Logger LOG =
            Logger.getLogger(OrderDiagnostics.class.getName());

    static void inspect(Order order) {
        // Supplier: xây chuỗi chẩn đoán khi thông điệp được log.
        LOG.log(Level.FINE, () -> "Order snapshot: " + order);
    }

    static void reportFailure(String orderId, Exception error) {
        // Logger nhận Throwable riêng để giữ stack trace.
        LOG.log(Level.WARNING,
                "Cannot process order " + orderId, error);
    }
}
~~~

This standalone snippet assumes `Order` is defined as in the main example. `OrderDiagnostics.inspect(order)` is useful only if the logger is configured to emit `FINE`. The `Supplier<String>` overload avoids building the string when that log level is disabled.

**Note:** `Supplier` cannot sanitize sensitive data: if `Order.toString()` exposes tokens, enabled logging still leaks them. User-provided `orderId` values also need control-character/newline filtering to prevent log injection; the primary example validates ID format.

### 7.2. SLF4J / Spring: parameterized logging

In SLF4J applications, typical syntax looks like:

~~~java
// Snippet dành cho dự án đã có SLF4J, không chạy bằng JDK trần.
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(CheckoutService.class);

log.debug("Processing order: {}", order);
log.warn("Failed processing order {}", order.id(), exception);
~~~

`CheckoutService` is an illustrative class name; replace it with your actual class. The `order` argument may be stringified during logger processing, so **`toString()` must be safe by design**. SLF4J's parameterized logging usually avoids string concatenation until logging is needed, although performance depends on implementation and usage.

For errors, passing a `Throwable` to a suitable logging overload retains **stack traces**, instead of only concatenating `exception.toString()`. Backends and configurations may handle traces differently.

### 7.3. `Exception.toString()`, `getMessage()`, and stack traces

~~~java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getMessage()); // Mô tả riêng.
    System.out.println(ex.toString());    // Tên exception + mô tả.
    ex.printStackTrace();                 // Stack trace ra stderr.
}
~~~

Conceptually:

| Method | Main information |
|---|---|
| `ex.getMessage()` | Exception message (possibly null) |
| `ex.toString()` | Exception class and message, if available |
| `ex.printStackTrace()` | Stack trace and exception/cause information written to a stream |
| `logger.log(Level.WARNING, "...", ex)` | Sends the exception to a configured logger |

Avoid indiscriminate `ex.printStackTrace()` calls in production services when a logger is available: writing directly to a default stream makes log routing difficult. Stack traces can also expose sensitive exception-message data, so exception messages need careful design.

## 8. Common mistakes when overriding `toString()`

### Mistake A: automatically printing all fields without a security review

~~~java
// Minh họa SAI:
@Override
public String toString() {
    return "Account{email=" + email
            + ", apiToken=" + apiToken + "}";
}
~~~

One `log.info("{}", account)` call can leak secrets into long-lived logs. Build **an allowlist of diagnostic fields** and review nested objects.

### Mistake B: fetching external data inside `toString()`

~~~java
// Minh họa SAI:
@Override
public String toString() {
    return "Order{items=" + repository.findAllByOrder(id) + "}";
}
~~~

A `println(order)` call could inadvertently cause I/O, N+1 queries, deadlocks, or errors from closed connections. Gather needed information **before** creating a diagnostic snapshot; let `toString()` format only readily available data.

### Mistake C: depending on `toString()` for business decisions

~~~java
// Không nên dùng:
if (order.toString().contains("status=PAID")) {
    // ...
}
~~~

Business rules must rely on `order.status()`, enums, or explicitly contracted methods, not parsing text intended for humans.

### Mistake D: returning null or unexpectedly throwing exceptions

The `Object.toString()` contract expects an object representation string. Overrides should return **a non-null string** without depending on uninitialized optional fields.

~~~java
// Nếu nickname có thể null:
@Override
public String toString() {
    return "Profile{nickname="
            + java.util.Objects.toString(nickname, "<missing>")
            + "}";
}
~~~

The snippet assumes a `nickname` field. Use existing data; avoid complex callbacks or virtual method calls that might fail while formatting the object.

### Mistake E: unbounded or concurrency-unsafe output

Printing tens of thousands of elements can increase GC pressure and latency. Reading mutable fields without synchronization may yield **an inconsistent state snapshot**. For large or concurrent data, consider a size-limited immutable diagnostic DTO, collected under suitable synchronization and logged in a structured form.

Not every `toString()` needs a `StringBuilder`. Short `+` string concatenations are clear and usually optimized by the compiler/JVM. Optimize based on measured costs and performance goals.

## 9. Testing string representations and security policies

Unit tests for `toString()` should check **important properties**: a lookup ID is included, the state appears, sensitive data does not leak, and valid objects do not trigger exceptions.

Place `ObjectDiagnosticsDemoTest.java` in the same package test source set as `ObjectDiagnosticsDemo.java`, with a JUnit Jupiter 5 dependency:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ObjectDiagnosticsDemoTest {

    private Order order() {
        return new Order(
                "ORD-42",
                OrderStatus.CREATED,
                List.of(new OrderLine("SKU-1", 2)),
                "REQ-72",
                "private@example.com",
                "token-top-secret");
    }

    @Test
    void diagnosticContainsUsefulFields() {
        String diagnostic = order().toString();

        assertTrue(diagnostic.contains("ORD-42"));
        assertTrue(diagnostic.contains("CREATED"));
        assertTrue(diagnostic.contains("itemCount=1"));
        assertTrue(diagnostic.contains("REQ-72"));
    }

    @Test
    void diagnosticDoesNotLeakSecrets() {
        String diagnostic = order().toString();

        assertFalse(diagnostic.contains("private@example.com"));
        assertFalse(diagnostic.contains("token-top-secret"));
        assertFalse(diagnostic.contains("customerEmail"));
        assertFalse(diagnostic.contains("accessToken"));
    }

    @Test
    void recordRepresentsSafeComponents() {
        String diagnostic = new OrderLine("SKU-1", 2).toString();

        assertEquals("OrderLine[sku=SKU-1, quantity=2]", diagnostic);
    }

    @Test
    void nullConversionIsPredictable() {
        assertEquals("null", String.valueOf((Object) null));
        assertEquals("<missing>", java.util.Objects.toString(
                null, "<missing>"));
    }
}
~~~

**Why not always `assertEquals` the entire `toString()`?** If its purpose is only diagnostics, exact punctuation assertions can be brittle under reasonable format changes. Check which fields **must appear or must remain hidden**. Compare the whole string only when its format is an explicit contract.

**Security testing limitation:** Proving two known secrets are absent **does not establish** that all other sensitive information is excluded. Review new fields, nested object contents, actual logs, and data-classification rules.

## 10. When should you create a separate diagnostic model?

`toString()` suits brief human-readable descriptions, but larger systems often need varying levels of detail:

- **Public information:** approved tracking IDs and statuses that users may see.
- **Developer information:** permitted internal IDs, correlation codes, technical states, and component names.
- **Deep investigation data:** timings, retry counts, error codes, sanitized span IDs, and access-controlled details.

When an object needs different representations for different purposes, do not force everything into `toString()`. Define distinct APIs:

~~~java
record OrderDiagnostic(
        String orderId,
        String status,
        int itemCount,
        String traceId
) {}

record OrderPublicView(
        String reference,
        String customerFacingStatus
) {}
~~~

These records illustrate **data shapes**. In real APIs, do not serialize `OrderDiagnostic` to public endpoints merely because it is a record: specify destinations, permissions, and approved fields. Record-generated `toString()` methods also expose components, so safe component selection matters.

With structured logging, instead of writing only:

~~~text
Order{id='ORD-42', status=CREATED, traceId='REQ-72'}
~~~

a system can record individual fields:

~~~json
{
  "event": "order.processing",
  "orderId": "ORD-42",
  "status": "CREATED",
  "traceId": "REQ-72"
}
~~~

This JSON is **an illustrative logging schema**, not the output of `Object.toString()`. A structured-logging framework must handle serialization, field filtering, sanitization, and size limits.

## 11. Practice exercise: diagnosing PaymentAttempt

Build a `PaymentAttempt` class with these fields:

| Field | Example | May appear in the demo string? |
|---|---|---|
| `attemptId` | `ATT-17` | Yes |
| `orderId` | `ORD-42` | Yes |
| `status` | `PENDING` | Yes |
| `retryCount` | `2` | Yes |
| `providerToken` | `sk_example_secret` | **No** |
| `payerEmail` | `customer@example.com` | **No** |
| `failureCode` | `PROVIDER_TIMEOUT` | Yes, if an approved error code |

Requirements:

1. Override `toString()` to return a short string with IDs, status, retry count, and an optional error code.
2. Do not include email, tokens, or raw provider responses in the string.
3. If `failureCode` is null, display a fixed value such as `none` without throwing.
4. Write tests proving secrets are absent and the string contains the required diagnostic fields.
5. Create a list of 100.000 attempts and explain why logging the whole list merely to find failed retry counts is unwise.
6. Write a separate `toCustomerMessage()` method or DTO mapper returning only customer-friendly status.
7. When a provider call raises an exception, log the `Throwable` through a suitable API to retain the stack trace instead of concatenating `ex.toString()`.

### Self-check questions

1. Why is a `ClassName@1a2b3c` string not a memory address or business ID?
2. Which object method does `System.out.println(order)` generally use?
3. How does `String.valueOf(null)` differ from calling `nullReference.toString()`?
4. What does a record-generated `toString()` include, and why can it be dangerous?
5. When should `Arrays.toString` and `Arrays.deepToString` be used?
6. Why can cyclic references cause `StackOverflowError` in custom `toString()` methods?
7. Why is parsing `toString()` for order status an unstable design?
8. How does passing `Exception` to a logger differ from only writing `ex.getMessage()`?
9. When is a diagnostic DTO or structured logging preferable to `toString()`?

**Remember:** **`toString()` provides a useful representation for inspecting objects**, defined by the class. Favor **clear semantics, approved data, fast execution, and no side effects**. Customer-facing details, API serialization, domain contracts, and structured diagnostic logs deserve their own interfaces rather than depending on a debug string.
