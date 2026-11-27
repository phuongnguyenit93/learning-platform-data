# Modeling Success, Failure, and Valid Variants with `sealed` in Java 17

When a method performs a business operation, the result is often more than a single value. For example, looking up a customer by ID may result in **found**, **not found**, or **rejected due to an invalid ID**. If it only returns `null`, a `boolean`, or an object containing multiple optional fields, callers can easily misunderstand the state and miss how each case should be handled.

In Java 17, **`sealed interface`/`sealed class`** lets you define in advance which types may directly implement or extend a root type. Combined with **`record`**, you represent each case with a meaningful data type carrying only the necessary information. This design approach is especially useful for **success/failure results**, **workflow states**, **domain messages**, and controlled sets of variants.

> The hands-on content uses only stable features in Java 17: `sealed` (stable since Java 17), `record`, and pattern matching for `instanceof` (both stable before Java 17). No `--enable-preview` flag is needed.

## 1. The Problem: A Result Object with Too Many Ambiguous States

Suppose a program looks up a customer and uses the following data type:

~~~java
class LookupResponse {
    boolean success;
    Customer customer;
    String errorCode;
    String errorMessage;
}
~~~

In terms of domain semantics, we only want one of two branches:

- Success: there is a customer.
- Failure: there is a failure reason.

However, the data type above allows inconsistent combinations:

| `success` | `customer` | `errorCode` | Problem |
| --- | --- | --- | --- |
| `true` | Customer | `null` | Valid success state |
| `false` | `null` | Error code | Valid failure state |
| `true` | `null` | `null` | Success, but no data |
| `false` | Customer | Error code | Has both success data and an error |
| `true` | Customer | Error code | Two contradictory conclusions |

Relying on a "verbal convention" that developers must not assign invalid field combinations is not enough. A better design turns **valid states** into **valid data types**.

A simple form:

~~~java
sealed interface LookupResult permits Found, Failed { }

record Found(Customer customer) implements LookupResult { }

record Failed(ErrorInfo error) implements LookupResult { }
~~~

Here, a `LookupResult` can only directly be `Found` or `Failed`. Each record stores only the data specific to that case: `Found` has no error field; `Failed` has no customer field.

**Important point:** `sealed` only restricts the type hierarchy. It does not automatically forbid `null`, blank strings, negative numbers, or violated business invariants. To protect those, you need additional checks in constructors.

## 2. How `sealed` Works in Java 17

The `sealed` keyword can be used with a class or an interface:

~~~java
public sealed interface OperationResult permits Success, Failure {
}
~~~

The `permits` list declares the types allowed to **directly** implement `OperationResult`. Each permitted subtype must decide how the hierarchy may be extended further:

| Subtype declaration | Meaning |
| --- | --- |
| `final` | Disallows further inheritance |
| `sealed` | Allows further inheritance, restricted by a subtype list |
| `non-sealed` | Reopens inheritance for subsequent classes/subtypes |

A `record` is always `final`, making it well suited as a "leaf" in a closed result model:

~~~java
sealed interface Result permits Success, Failure { }

record Success(String value) implements Result { }

record Failure(String reason) implements Result { }
~~~

If you declare a new type that is not in `permits`:

~~~java
// Compile error: Cancelled is not permitted by Result.
record Cancelled(String reason) implements Result { }
~~~

The compiler will reject it. This prevents unintended direct extensions of the result model.

### Subtype Location Rules

In a **named module** of the Java Platform Module System, a permitted subtype must belong to the **same module** as the `sealed` type. In an **unnamed module** (the usual classpath execution), the subtype must belong to the **same package**. The subtype must also directly declare `extends` or `implements` for the corresponding `sealed` type.

In another case, when all direct subtypes are declared in the same compilation unit (the same source file), the compiler can infer the list of permitted types if `permits` is omitted. However, declaring `permits` explicitly often helps learners clearly see the scope of accepted variants.

### Why Is It Often Combined with `record`?

`record` provides clear state data with automatically generated constructor, accessors, `equals`, `hashCode`, and `toString`. For example:

~~~java
record Found(Customer customer) implements LookupResult { }
~~~

It has the `customer()` accessor, and the data stored in the record component is `final`. There is no need to manually write getters or setters for result data.

However, a record only guarantees **shallow immutability**: if a component references a mutable collection, the contents of that collection can still be modified. When true immutability is needed, prefer immutable components and defensive copies, such as `List.copyOf(input)`.

## 3. Modeling Success/Failure for a Concrete Use Case

Let's design a feature that looks up a customer by an ID entered from the command line.

### 3.1. Valid Outcomes

Suppose customer data is already in memory. A request can produce:

1. `Found`: a customer is found for a valid ID.
2. `Failed` with `INVALID_ID`: the input ID is blank, not an integer, or not positive.
3. `Failed` with `NOT_FOUND`: the ID is valid but does not exist in the data.

The two direct types `Found` and `Failed` represent the success and failure branches. Inside `Failed`, an `ErrorCode` enum distinguishes the supported reasons.

~~~text
FindResult                          (sealed interface)
├── Found(Customer)                 (record, success)
└── Failed(ErrorInfo)               (record, failure)
      └── ErrorInfo
          ├── INVALID_ID
          └── NOT_FOUND
~~~

Because the list of error codes is finite and these codes share the same data shape (`code`, `message`), an enum is appropriate. Later, we will use nested `sealed` types for errors carrying **different payloads**.

### 3.2. Standalone Compilable and Runnable Java 17 Example

Put all the code below into **`src/demo/SealedResultDemo.java`**:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;

public final class SealedResultDemo {

    private SealedResultDemo() {
    }

    public record Customer(int id, String name) {
        public Customer {
            if (id <= 0) {
                throw new IllegalArgumentException("ID must be positive");
            }
            Objects.requireNonNull(name, "name");
            if (name.isBlank()) {
                throw new IllegalArgumentException("Name must not be blank");
            }
        }
    }

    public enum ErrorCode {
        INVALID_ID,
        NOT_FOUND
    }

    public record ErrorInfo(ErrorCode code, String message) {
        public ErrorInfo {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
            if (message.isBlank()) {
                throw new IllegalArgumentException("Error message must not be blank");
            }
        }
    }

    public sealed interface FindResult permits Found, Failed {
    }

    public record Found(Customer customer) implements FindResult {
        public Found {
            Objects.requireNonNull(customer, "customer");
        }
    }

    public record Failed(ErrorInfo error) implements FindResult {
        public Failed {
            Objects.requireNonNull(error, "error");
        }
    }

    private static final Map<Integer, Customer> CUSTOMERS = Map.of(
            1, new Customer(1, "An"),
            2, new Customer(2, "Bình")
    );

    public static FindResult findCustomer(String rawId) {
        if (rawId == null || rawId.isBlank()) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID must be a positive integer"));
        }

        final int id;
        try {
            id = Integer.parseInt(rawId.strip());
        } catch (NumberFormatException ex) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID must be a positive integer"));
        }

        if (id <= 0) {
            return new Failed(new ErrorInfo(
                    ErrorCode.INVALID_ID,
                    "ID must be a positive integer"));
        }

        Customer customer = CUSTOMERS.get(id);
        if (customer == null) {
            return new Failed(new ErrorInfo(
                    ErrorCode.NOT_FOUND,
                    "Customer not found"));
        }

        return new Found(customer);
    }

    public static String describe(FindResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Found found) {
            return "Found: " + found.customer().name()
                    + " (#" + found.customer().id() + ")";
        }

        if (result instanceof Failed failed) {
            ErrorInfo error = failed.error();
            return "Failed [" + error.code() + "]: " + error.message();
        }

        throw new IllegalStateException(
                "Unhandled result variant: "
                        + result.getClass().getName());
    }

    public static void main(String[] args) {
        for (String rawId : new String[] {"1", "99", "abc"}) {
            System.out.println(
                    rawId + " -> " + describe(findCustomer(rawId)));
        }
    }
}
~~~

This is a self-contained Java source file: `Customer`, `ErrorInfo`, `FindResult`, and its subtypes are all nested inside the enclosing `SealedResultDemo` class. `Map.of(...)` provides a small dataset so it can run without setting up a database.

### 3.3. Compiling and Running with JDK 17

From the root directory containing `src/demo/SealedResultDemo.java`:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/SealedResultDemo.java
java -cp out demo.SealedResultDemo
~~~

The `--release 17` option instructs the Java compiler to target the Java 17 language, APIs, and bytecode. `-encoding UTF-8` specifies the encoding of the source file. `-d out` places the `.class` files in the output directory; `java -cp out` runs the class by its fully qualified package name.

Expected output:

~~~text
1 -> Found: An (#1)
99 -> Failed [NOT_FOUND]: Customer not found
abc -> Failed [INVALID_ID]: ID must be a positive integer
~~~

When you want to test other scenarios, you can change the array in `main` to `{"2", "0", "-3", " 1 ", "99999999999999999"}`; the `findCustomer` method still always returns one of the two valid types. An ID too large for `int` is handled via `NumberFormatException` and turned into `INVALID_ID`.

## 4. Invariants and the Meaning of Each Result Type

The design in the example carries the following invariants:

| Type | Required data | Invariant |
| --- | --- | --- |
| `Found` | `Customer` | Customer is non-`null` |
| `Failed` | `ErrorInfo` | Error info is non-`null` |
| `Customer` | `id`, `name` | Positive ID; non-`null` and non-blank name |
| `ErrorInfo` | `code`, `message` | Non-`null` error code; non-blank message |

The record compact constructors perform validation when an object is created:

~~~java
public record Found(Customer customer) implements FindResult {
    public Found {
        Objects.requireNonNull(customer, "customer");
    }
}
~~~

As a result, it is impossible to create a `new Found(null)` state without getting an exception right at the constructor. Methods that process the result do not need to re-check whether the customer exists after confirming the `Found` type.

Do not confuse **closing a type hierarchy** with **proving every domain invariant**. The compiler guarantees that `Found` and `Failed` are the valid direct subtypes; conditions such as requiring a positive ID are the responsibility of constructors or object-creation rules.

You can restrict constructors, use factory methods, or place records in an appropriate package/module scope if you need to control where results are allowed to be created. The level of encapsulation depends on your API requirements.

## 5. Handling Results with Pattern Matching for `instanceof`

The syntax:

~~~java
if (result instanceof Found found) {
    System.out.println(found.customer().name());
}
~~~

both checks the type and binds a safely cast variable within the branch scope. This is **pattern matching for `instanceof`**, a stable feature usable in Java 17 without preview flags.

With a result model, each variant should be handled explicitly:

~~~java
static void printResult(SealedResultDemo.FindResult result) {
    if (result instanceof SealedResultDemo.Found found) {
        System.out.println("Name: " + found.customer().name());
    } else if (result instanceof SealedResultDemo.Failed failed) {
        System.out.println("Error code: " + failed.error().code());
    } else {
        throw new IllegalStateException(
                "Unsupported type " + result.getClass().getName());
    }
}
~~~

**Java 17-specific note:** An `if`/`else if` chain is not proven by the compiler to cover every variant of a sealed hierarchy. When a new type is added to `permits`, existing `if` chains will not necessarily produce a compile error. A fallback branch prevents silently ignoring a new case, though you still need to update all result-handling sites when the API changes.

**Pattern matching for `switch`** is still in *preview* in Java 17, not yet a stable feature of this release. If the target is stable Java 17 source code, you can use `instanceof` as shown above or design explicit handling methods on the subtypes. Do not take `switch` syntax from Java 21 or later as a Java 17 example while ignoring the preview requirement.

## 6. Modeling Failure Variants with Nested `sealed` Types

An error-code enum works well if all errors share a similar structure. However, many business domains need **error kinds that carry different data**:

- Invalid cart: needs a message describing what is wrong.
- Insufficient funds: needs the required amount and the available balance.
- Payment succeeded: needs a receipt ID.

In that case, using a two-level sealed hierarchy expresses the model much better:

~~~java
sealed interface CheckoutResult
        permits Paid, CheckoutFailure {
}

record Paid(String receiptId) implements CheckoutResult {
}

sealed interface CheckoutFailure extends CheckoutResult
        permits InvalidCart, InsufficientFunds {
}

record InvalidCart(String reason) implements CheckoutFailure {
}

record InsufficientFunds(long required, long available)
        implements CheckoutFailure {
}
~~~

Diagram:

~~~text
CheckoutResult (sealed)
├── Paid(receiptId) (record)
└── CheckoutFailure (sealed)
    ├── InvalidCart(reason) (record)
    └── InsufficientFunds(required, available) (record)
~~~

`CheckoutFailure` is a **sealed** type because it still permits two direct subtypes. All three record types are the final "leaves" of the hierarchy. In practice, you should also add constructor checks: non-blank receipt ID, non-blank error reason, non-negative amounts, and for `InsufficientFunds` a clear rule defining the relationship between `required` and `available` according to business rules.

This design gives each request handler the exact data it needs:

~~~java
static String message(CheckoutResult result) {
    if (result instanceof Paid paid) {
        return "Payment succeeded: " + paid.receiptId();
    }
    if (result instanceof InvalidCart invalid) {
        return "Invalid cart: " + invalid.reason();
    }
    if (result instanceof InsufficientFunds insufficient) {
        return "Short by "
                + (insufficient.required() - insufficient.available())
                + " currency units";
    }
    throw new IllegalStateException("Unsupported result");
}
~~~

Even though `InvalidCart` and `InsufficientFunds` do not directly implement `CheckoutResult` and instead go through `CheckoutFailure`, both are still valid cases of `CheckoutResult`. This hierarchy style is worth using when failure reasons have different data and behavior, or when you need to represent the error group as its own type.

Do not use `non-sealed` for the failure branch if your intent is to **enumerate all valid variants**: `non-sealed` allows that branch to be extended with new subtypes and breaks the closedness of the subtree below.

## 7. Reusing via a Generic `Result<T>` Model

If many operations share the same two result shapes, rather than redefining `Found`/`Failed` everywhere, you can create a generic type. This example is a standalone design pattern, separate from the `SealedResultDemo` class above:

~~~java
import java.util.Objects;

record Problem(String code, String message) {
    public Problem {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(message, "message");
        if (code.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Invalid error information");
        }
    }
}

sealed interface Result<T> permits Result.Ok, Result.Err {

    record Ok<T>(T value) implements Result<T> {
        public Ok {
            Objects.requireNonNull(value, "value");
        }
    }

    record Err<T>(Problem problem) implements Result<T> {
        public Err {
            Objects.requireNonNull(problem, "problem");
        }
    }
}
~~~

Example declaration and usage:

~~~java
Result<String> success = new Result.Ok<>("Saved");
Result<String> failure =
        new Result.Err<>(new Problem("CONFLICT", "Data already exists"));

if (success instanceof Result.Ok<?> ok) {
    System.out.println(ok.value());
}
~~~

Checking `instanceof Result.Ok<?>` verifies the `Ok` variant without assuming you can check the generic type argument `String` at runtime. Because of **type erasure**, type arguments do not automatically remain reliable identifying information at runtime. To build a safer and more convenient API for transforming `T` values, you can add `map`, `flatMap`, or `fold` methods with explicit generic signatures.

The benefit of `Result<T>` is that the **success data type** varies by operation while the success/failure structure stays consistent:

~~~java
Result<Customer> customerResult;
Result<Integer> countResult;
Result<String> messageResult;
~~~

Still, a generic `Problem` type can easily become too broad: callers may end up having to interpret raw error code strings themselves. When error variants carry distinct domain meaning and different data, choosing a dedicated hierarchy like `CheckoutFailure` is usually clearer.

## 8. Choosing `sealed`, `enum`, `Optional`, Exceptions, or Another Return Type?

| Tool | When to use | Limitations to note |
| --- | --- | --- |
| `sealed interface` + `record` | Controlled number of variants, each carrying its own data | Requires defining and maintaining a hierarchy |
| `enum` | Fixed set of named values with little per-case data | Cannot attach distinct record components to each constant as separate subtypes |
| `Optional<T>` | Result is purely presence or absence of a value, with no explanation needed for absence | Does not describe detailed causes |
| Exceptions | Programming bugs, precondition violations, infrastructure failures, or appropriate exceptional control flow | Should not replace every expected business outcome |
| A `record` with `success` and nullable fields | Quick integration with a mandatory external format | Allows contradictory states without strict validation |

For example, a cache lookup with no value can return `Optional<Value>`; whereas account registration with failures such as email already in use, invalid name, or ineligible user is better expressed with a set of named failure types.

You should distinguish **expected business failures** (for example, a customer ID does not exist) from **unexpected errors** (for example, corrupted data, lost database connection, missing configuration). Some infrastructure errors can be translated into a failure variant if the API contract genuinely requires it, but you should not catch every `RuntimeException` and return `Failed("UNKNOWN")` in a way that hides programming bugs.

## 9. Designing API Contracts and Avoiding Invalid States

When building a sealed model for a method, you can follow this sequence:

1. **List meaningful business outcomes.** For example: `Created`, `AlreadyExists`, `ValidationFailed`; do not start from existing `boolean` fields.
2. **Identify the data specific to each outcome.** `Created` needs the new ID, `AlreadyExists` may need the duplicate ID, and `ValidationFailed` needs the list of input errors.
3. **Choose the classification levels.** If there is only success/failure with uniform errors, use two records. If each error has a distinct payload, add a nested `sealed` type for the failure branch.
4. **Enforce invariants at creation time.** Check for null, blank strings, and negative numbers; copy input collections with `List.copyOf` when needed.
5. **Define how callers handle the result.** Read every intended variant, and have a clear handling path for unsupported cases.
6. **Consider the stability of the hierarchy.** Adding a new variant is a significant change for API consumers because they may need to handle an additional case.

For example, with an input validation error, an error list needs to be defensively copied:

~~~java
import java.util.List;
import java.util.Objects;

record ValidationFailed(List<String> errors) {
    public ValidationFailed {
        Objects.requireNonNull(errors, "errors");
        errors = List.copyOf(errors);
        if (errors.isEmpty()) {
            throw new IllegalArgumentException(
                    "Must contain at least one validation error");
        }
    }
}
~~~

`List.copyOf` creates a copy that cannot be mutated through the returned reference while rejecting `null` elements; as a result, the contents of `errors` cannot be altered through the input list after the record is created.

**Note on closed models:** `sealed` prevents **new types from directly implementing** the supertype outside the permitted list. It does not by itself guarantee the whole system has no invalid states, does not guarantee every variant is handled by an `if` chain, and does not replace validating each payload's invariants.

## 10. Combining `sealed` with Source Code Organization

In real projects, you can place result types close to the use case they describe:

~~~text
src/main/java/
└── vn/example/customer/
    ├── Customer.java
    ├── CustomerService.java
    └── FindCustomerResult.java
~~~

For example, a `FindCustomerResult.java` file placing the interface and records directly inside keeps the variants close together:

~~~java
package vn.example.customer;

import java.util.Objects;

public sealed interface FindCustomerResult
        permits FindCustomerResult.Found,
                FindCustomerResult.NotFound {

    record Found(Customer customer) implements FindCustomerResult {
        public Found {
            Objects.requireNonNull(customer, "customer");
        }
    }

    record NotFound(int requestedId) implements FindCustomerResult {
        public NotFound {
            if (requestedId <= 0) {
                throw new IllegalArgumentException("ID must be positive");
            }
        }
    }
}
~~~

With this layout, API consumers can refer to `FindCustomerResult.Found` and `FindCustomerResult.NotFound`. The two records nested inside the interface are member types; records are inherently `final`. If you want an `InvalidId` error type, add it to the `permits` list and define the corresponding record.

If a module exposes a public API to other modules, maintaining a clear result contract helps reduce mismatches as values cross service, controller, or adapter layers. However, adding or removing permitted variants should be treated as an API contract change with a compatibility plan.

### Serialization Considerations

Many APIs return results as JSON. JSON is just data and has no concept of Java `sealed`. If network exchange is required, design an explicit **discriminator** such as `"type": "found"`, `"type": "not_found"`, or `"type": "invalid_id"`, paired with protocol schema/validation. Java ↔ JSON mapping depends on the serialization library and is not automatically guaranteed by `sealed`.

Similarly, records and sealed types are strong choices for an internal **domain model**, whereas public DTOs should be designed around the actual API contract. Avoid letting your JSON format accidentally depend on Java class names or package details.

## 11. Practice Exercises

1. Modify `SealedResultDemo`: add a `CUSTOMER_INACTIVE` code to `ErrorCode`, add a deactivated customer, and return `Failed` with that code when looked up.
2. Split `Failed` into two records `InvalidId` and `NotFound` directly implementing `FindResult`. Update `permits`, the lookup method, and the handling branches.
3. Design `OrderResult` with `Placed(orderId)`, `Rejected(reason)`, and `Pending(retryAfterSeconds)`. Add checks so `orderId` is not blank and `retryAfterSeconds` is positive.
4. Refactor a model from dedicated types to a generic `Result<T>`; identify where it is more convenient and where it loses domain information.
5. Add a new variant to `permits` and observe the existing `if` branches. Explain why Java 17 requires manual updates or a fallback branch instead of the compiler reporting every missing case by default.

A good result model should let readers immediately see **which outcomes can occur, what data each outcome contains, and which states are rejected as soon as the object is created**. In Java 17, `sealed` defines the variant set, `record` expresses each variant's data, and constructors plus application logic enforce the domain invariants.
