# Choosing Exceptions, Optional, or Structured Result Types in Java API Design

## Objectives and Context

An API has two parts to its contract: **the success value** and **the meaning of other outcomes**. In Java Core, those other outcomes can be “no result, which is still normal”, “request rejected by business rules”, “parameter violates a precondition”, or “unable to execute due to an I/O/infrastructure error”. The three tools—`exception`, `Optional<T>`, and **structured result types**—express different semantics.

After this lesson, you will know how to choose a return type based on semantics, design unambiguous contracts, leverage `sealed interface` and `record` in Java 17, distinguish checked from unchecked exceptions, handle error causes, and thoroughly test all branches.

## 1. Classify Before Choosing a Tool

| Outcome | Example | Representation to Consider |
| --- | --- | --- |
| Success guaranteed to have a value | Computing the sum of two valid numbers | Return `T` directly |
| Success, possibly absent, no need to know “why” | Looking up a product by code; no matching product exists | `Optional<Product>` |
| Multiple **expected** business outcomes, each branch carrying different information | Purchase request: accepted, code does not exist, invalid quantity, insufficient stock | `QuoteResult`/`Result<T,E>` |
| Caller misuses the API or violates an invariant | Passing a `null`/blank code when prohibited by the contract | `IllegalArgumentException`, `NullPointerException`, or an appropriate exception |
| Operation cannot complete due to a technical error | Unable to read file, database query failed | Appropriate exception, preserving `cause` |

This table is a guideline, not an absolute rule. For example, a **negative quantity** may be `InvalidQuantity` when accepting a form and wanting to display a correctable error; in an internal API requiring `quantity > 0` from an already-validated caller, it may be an `IllegalArgumentException`. The core question is: **does the caller expect this situation and have to handle it as a normal value?**

Before writing a signature, ask:
1. Does the method complete successfully according to its contract?
2. If it completes, does the caller need to distinguish “no value” or multiple different states?
3. If it does not complete, is it a caller contract violation, an infrastructure error, or a broken invariant?
4. Should the caller continue, display a message, fix the data, retry, or stop processing?

## 2. When to Use Exceptions?

Exceptions express that **the successful execution flow has been interrupted**. `throw` stops the method from returning a normal value; the JVM searches for a matching `catch` across call frames. An exception has a type, a message, a stack trace, and optionally a root cause (`cause`). You should not continuously throw exceptions as a branching mechanism for business states that occur frequently.

Commonly used types:

- **`IllegalArgumentException`**: a parameter value does not satisfy a documented precondition. For a reference parameter that must be non-`null`, `Objects.requireNonNull` throws `NullPointerException` and can provide a clear message.
- **`IllegalStateException`**: the object or process is not in a state that permits the operation.
- **`IOException`**: an I/O operation failed; the caller may have an alternative fallback or report an appropriate error.
- **Custom domain exceptions**: use when an abnormal error category has distinct handling semantics; avoid creating many classes just to change the message.

### Checked and Unchecked Exceptions

`Exception` and its subclasses are **checked**, except `RuntimeException` and its subclasses (unchecked). `Error` is also a `Throwable`, but it is normally not something to catch in business logic. The compiler requires catching or declaring `throws` for checked exceptions; unchecked exceptions do not require declaration.

| Criterion | Checked, e.g., `IOException` | Unchecked, e.g., `IllegalArgumentException` |
| --- | --- | --- |
| At compile time | Requires `catch` or `throws` | Not required |
| Typical use | External failures that the API wants the caller to explicitly consider | Precondition violation, invalid state, or errors with a propagation policy |
| Risk | Callers catch blindly or have to propagate through many layers | Undocumented contracts cause callers to miss error branches |

There is no rule that “severe errors are checked, minor errors are unchecked”. You need to consider **what the calling layer can recover from**, the conventions of the library in use, and public signature compatibility.

Java example using a checked exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigReader {
    static String read(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

This is an **illustrative class** without a `main` method. When the file cannot be read, `Files.readString` throws an appropriate `IOException`; when read successfully, the result is a string. Stdout cannot be determined because the snippet does not execute reading a specific file. Do not turn a file-reading error into `Optional.empty()`: “data not found after a successful lookup” is different from “do not know whether data exists because I/O failed”.

If the API decides to wrap a checked exception into an unchecked one, preserve the cause:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigService {
    static String requireConfig(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException e) {
            throw new UncheckedIOException("Cannot read config: " + path, e);
        }
    }
}
~~~

This snippet is also illustrative without `main`. `UncheckedIOException` preserves `cause` so upper layers can still trace the original error. Only wrap when the contract calls for it; do not convert every checked exception into unchecked by default.

**How to catch exceptions properly:** catch at a boundary capable of handling them (switching data sources, bounded retries, displaying an error, mapping an HTTP response), or add context and rethrow. Avoid `catch (Exception ignored)`, returning `null`/`false` after swallowing an error, catching `Throwable`/`Error` in normal logic, and logging the same error repeatedly at every layer.

## 3. When to Use Optional<T>?

`Optional<T>` answers exactly one question: **after a valid operation has been performed, is there a value of T or not?** It does not carry an error cause, an invalid quantity, or an error code, nor does it prevent a method from throwing exceptions.

Example:

~~~java
import java.util.Map;
import java.util.Optional;

class Catalog {
    private static final Map<String, String> NAMES =
            Map.of("P01", "Notebook");

    static Optional<String> findName(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return Optional.ofNullable(NAMES.get(sku));
    }
}
~~~

The `Catalog` class is illustrative code without `main`. `findName("P01")` has a value; `findName("P02")` is an empty Optional. `null` or blank input violates the contract and throws an exception; these two situations are not confused with “valid code but not found”.

Useful APIs:

| Method | Meaning |
| --- | --- |
| `Optional.of(x)` | Creates a non-empty Optional; `x == null` causes `NullPointerException` |
| `Optional.ofNullable(x)` | Returns a present Optional when `x != null`, otherwise empty |
| `Optional.empty()` | Represents valid absence |
| `map(f)`, `flatMap(f)` | Transforms when a value is present; `flatMap` is for functions that already return Optional |
| `filter(p)` | Keeps the value if it satisfies the predicate |
| `ifPresent(f)`, `ifPresentOrElse(f, emptyAction)` | Handles one or both branches |
| `orElse(defaultValue)` | Uses a fallback value; the argument expression is evaluated eagerly |
| `orElseGet(supplier)` | Computes the fallback value only when the Optional is empty |
| `orElseThrow(supplier)` | Converts absence into an exception where the caller requires a value |
| `isPresent()`, `isEmpty()` | Checks the two states |

Example of the caller deciding the policy:

~~~java
String name = Catalog.findName("P02").orElse("Chưa có tên");

String requiredName = Catalog.findName("P02")
        .orElseThrow(() -> new IllegalStateException("Product P02 is required"));
~~~

These expressions assume `Catalog` is already defined above. The first expression chooses a fallback value; the second throws an exception because **the caller imposes a requirement that the record must exist**. You should not call `Optional.get()` when you are not sure a value is present, because an empty Optional causes `NoSuchElementException` and usually provides little contextual information.

Common mistakes:
- **Returning `null` instead of an Optional object:** if the signature is `Optional<T>`, always return an actual Optional.
- **Swallowing infrastructure errors and returning `empty()`:** makes it impossible to distinguish a lost connection from a nonexistent record.
- **Using `Optional<List<T>>` when you only mean an empty collection:** usually just return `List.of()` or an empty list. Use Optional only when *the absence of the list itself* has a distinct meaning.
- **Overusing Optional in parameters and fields:** Optional is especially useful in **return types**. Optional parameters can be expressed with overloads, builders, or an appropriate request type; consider framework/serialization requirements when using Optional as a field.
- **Unnecessary Optional nesting:** when a transformation already returns Optional, use `flatMap`.
- **Thinking Optional replaces validation:** invalid input or abnormal errors still need their own contract.

## 4. When to Use Structured Result Types?

When an operation has **multiple valid outcomes according to the business workflow**, the caller needs the outcome kind and its corresponding data. For example, evaluating a purchase request might yield:
- `Accepted`: eligible, along with SKU and quantity;
- `UnknownProduct`: the entered code does not exist;
- `InvalidQuantity`: the quantity requested by the user is invalid;
- `OutOfStock`: the desired quantity exceeds stock, along with requested and available quantities.

Returning `boolean`, `null`, `Optional.empty()`, or throwing a `RuntimeException("out of stock")` for all cases leaves the caller without enough information to display, fix data, or collect metrics.

In Java 17+, **`sealed interface` + `record`** is especially suitable. `sealed` restricts which types are permitted to implement it, while each `record` holds typed data for a state. `record` generates accessors, `equals`, `hashCode`, and `toString`, but does not automatically validate business rules on its data; add a constructor when invariants require it.

Another general option is `Result<T,E>` with two branches `Success<T,E>` and `Failure<T,E>`, where `E` should be a structured enum/record/hierarchy. If `E` is just a free-form string, callers easily end up parsing the message content by string matching or `contains`, leading to a fragile API when wording or language changes.

### 4.1. Complete Java 17 Example: Combining All Three Mechanisms

Save the following code as **`ApiOutcomeDemo.java`**. The catalog is kept in memory so results are reproducible. `quote` only **evaluates the request**; it does not place an order and does not deduct inventory.

~~~java
import java.util.Map;
import java.util.Optional;

public class ApiOutcomeDemo {
    record Product(String sku, int available) {}

    sealed interface QuoteResult
            permits Accepted, UnknownProduct, InvalidQuantity, OutOfStock {}

    record Accepted(String sku, int quantity) implements QuoteResult {}
    record UnknownProduct(String sku) implements QuoteResult {}
    record InvalidQuantity(int quantity) implements QuoteResult {}
    record OutOfStock(String sku, int requested, int available) implements QuoteResult {}

    private static final Map<String, Product> STOCK = Map.of(
            "P01", new Product("P01", 5)
    );

    static Optional<Product> findProduct(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return Optional.ofNullable(STOCK.get(sku));
    }

    static QuoteResult quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            return new InvalidQuantity(quantity);
        }
        Product product = STOCK.get(sku);
        if (product == null) {
            return new UnknownProduct(sku);
        }
        if (quantity > product.available()) {
            return new OutOfStock(sku, quantity, product.available());
        }
        return new Accepted(sku, quantity);
    }

    static String describe(QuoteResult result) {
        if (result instanceof Accepted ok) {
            return "OK " + ok.sku() + " x" + ok.quantity();
        }
        if (result instanceof UnknownProduct missing) {
            return "NOT_FOUND " + missing.sku();
        }
        if (result instanceof InvalidQuantity invalid) {
            return "INVALID_QUANTITY " + invalid.quantity();
        }
        if (result instanceof OutOfStock stock) {
            return "OUT_OF_STOCK " + stock.available();
        }
        throw new IllegalStateException("Unknown QuoteResult: " + result);
    }

    public static void main(String[] args) {
        System.out.println(findProduct("P01").isPresent());
        System.out.println(findProduct("P02").isEmpty());
        System.out.println(describe(quote("P01", 2)));
        System.out.println(describe(quote("P01", 8)));
        System.out.println(describe(quote("P02", 1)));
        System.out.println(describe(quote("P01", 0)));
        try {
            quote("", 2);
        } catch (IllegalArgumentException e) {
            System.out.println("EXCEPTION " + e.getMessage());
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 17 ApiOutcomeDemo.java
java ApiOutcomeDemo
~~~

Exact stdout:

~~~text
true
true
OK P01 x2
OUT_OF_STOCK 5
NOT_FOUND P02
INVALID_QUANTITY 0
EXCEPTION sku must not be blank
~~~

Meaning of each branch:
1. `findProduct("P01")` returns a present Optional; `findProduct("P02")` returns empty. The search still completes according to the contract.
2. `quote("P01", 2)` returns `Accepted`; `quote("P01", 8)` returns `OutOfStock` with `requested=8`, `available=5`.
3. `quote("P02", 1)` returns `UnknownProduct`, an expected business outcome, different from an unqueryable database error.
4. `quote("P01", 0)` returns `InvalidQuantity` so the caller can prompt the user to fix the quantity.
5. `quote("", 2)` throws `IllegalArgumentException` because a blank string violates the API's precondition.
6. `STOCK` is immutable. If writing an actual order-placement method, transactions/concurrency control and inventory consistency are needed; a `quote` result does not guarantee reserving stock.

**Validation order is also part of the contract.** For example, invalid quantity is checked before SKU lookup; when both the quantity is invalid and the product does not exist, the result is `InvalidQuantity`. If an API wants to report multiple errors at once, it should return a validation result containing a list of errors.

Java 17 stably supports `instanceof` pattern matching as in the example, whereas `switch` pattern matching in Java 17 is still a preview feature, so it is omitted from an example meant to run with standard `javac --release 17`. For callers in languages/versions supporting exhaustive `switch` over a sealed hierarchy, exhaustiveness checking can be leveraged; whereas the Java 17 `if/else` chain in the example must manually handle all variants.

### 4.2. Multiple Validation Errors in One Result

Instead of stopping at the first error in a form, you can return a structure containing field codes and error codes:

~~~java
import java.util.List;

record FieldError(String field, String code) {}

record ValidationFailure(List<FieldError> errors) {
    ValidationFailure {
        errors = List.copyOf(errors);
    }
}
~~~

The two records here are only type-declaration examples, without `main`. `List.copyOf` creates an unmodifiable copy via the returned list and rejects `null` elements; if the list must be non-empty, an additional check is needed. Error codes like `REQUIRED`, `NOT_INTEGER`, or `OUT_OF_RANGE` are more stable than free-form messages. The UI can localize messages from error codes on its own.

## 5. All Three Tools Can Be Used in the Same API

You do not need to force an entire module into a single style:

~~~text
findProduct(validSku)        -> Optional<Product>
quote(validSku, quantity)    -> QuoteResult
readConfig(path)             -> String, throws IOException
findProduct(blankSku)        -> IllegalArgumentException
~~~

The signature table above is a **semantic diagram**, not complete Java declaration syntax. It reflects four situations: a lookup that may be absent, a multi-branch business outcome, an abnormal I/O error, and a caller contract violation.

Even a method declaring `Result<Order, DomainError>` may still throw an I/O exception if a lower layer fails outside the expected business outcomes. When designing, clarify which errors are `DomainError` and which propagate as exceptions. Do not arbitrarily convert every `Exception` into `Failure`, as that can hide programming bugs that are breaking invariants.

## 6. Which Layer Should Translate Outcomes?

| Situation Source | What the Java Layer Should Understand | What the Communication Boundary Can Do |
| --- | --- | --- |
| Valid lookup, no record | Repository/service returns Optional per contract | REST can turn absence into 404 when the resource is required to exist |
| Insufficient stock per business rules | Service returns `OutOfStock` | REST can map to 409 Conflict per application contract |
| User enters invalid data | Validation/service returns a result containing error codes | UI displays per-field errors; REST often considers 400 or 422 |
| Cannot connect to database | Infrastructure propagates exception with full cause | REST boundary handles as an appropriate server error; do not report 404 |
| Caller passes prohibited parameter | Method throws precondition violation exception | Fix the caller or add validation at the data ingestion point |

The HTTP status codes above are only examples of **adapter-layer translation**. `Optional.empty()` itself does not “mean HTTP 404”; in Java Core, it is simply an empty result. The REST layer decides the status based on the endpoint contract. Do not expose stack traces, connection strings, or sensitive information externally. You can log with context at the handling boundary and preserve `cause` for diagnostics; avoid logging the same error redundantly at every layer.

**Retry:** only retry errors that are likely transient and when the operation is safe to retry; do not blindly retry order placements that have side effects. “Out of stock” or “negative quantity entered” are usually states requiring user changes, not reasons for automatic retry.

## 7. Quick Decision Tree

~~~text
Does the operation complete per contract?
|
+-- YES
|   +-- Always has T                     -> T
|   +-- Only present/absent T            -> Optional<T>
|   +-- Multiple business outcomes       -> Structured result type
|
+-- NO
    +-- Caller violates precondition     -> Appropriate exception
    +-- I/O failure, corrupted state     -> Appropriate exception, preserve cause
~~~

This is a design diagram, not a Java program. If a “not found” case needs specific error data or needs to be distinguished from “insufficient permissions”, “expired”, or “not yet activated”, a structured result type may be clearer than Optional. If you only need “present or absent”, Optional is simple and expressive enough.

## 8. Bad Designs and How to Fix Them

### A. Using `null` for Every Failure

~~~java
// Anti-pattern: null could mean not found,
// invalid input, or a query error.
Product findProduct(String sku) { /* ... */ return null; }
~~~

This is non-standalone illustrative code, because `Product` and the real body are not defined. Fix: declare `Optional<Product>` for valid not-found cases; exceptions for precondition violations and uncompletable errors; or a result type when expected branches need to be distinguished. Merely replacing `null` with `Optional.empty()` while keeping the old conflation does not fix the design flaw.

### B. Throwing Exceptions to Handle Every Business Event

~~~java
// Anti-pattern if out of stock is a frequent state the UI must handle:
if (requested > available) {
    throw new IllegalStateException("out of stock");
}
~~~

This is a fragment assuming `requested` and `available` are already declared. When the caller needs the remaining quantity and a way to suggest modifying the order, `OutOfStock(requested, available)` carries that information directly in the data type. Conversely, negative inventory outside invariants may genuinely be an abnormal condition that should throw an exception.

### C. Swallowing Infrastructure Errors and Returning Empty Optional

~~~java
// Anti-pattern: caller assumes the record definitely does not exist.
try {
    return repository.findById(id);
} catch (RuntimeException ignored) {
    return Optional.empty();
}
~~~

This fragment assumes `findById` returns Optional. A failed query means **it could not be determined** whether the record exists. It must not be turned into evidence of “does not exist”.

### D. Returning Error Codes via a Free-Form String

~~~java
record WeakResult(boolean success, String message) {}
~~~

When callers have to do `message.contains("stock")` to make decisions, a single change in wording or language breaks the logic. Replace it with subtypes/stable error codes and typed data fields; messages should only be for display and diagnostics.

### E. Misusing `Optional.get()` or `orElse`

`get()` throws `NoSuchElementException` if empty. `orElse(expensiveFallback())` calls `expensiveFallback()` even when the Optional has a value due to Java's argument evaluation rules; use `orElseGet(() -> expensiveFallback())` when lazy fallback creation is needed. `Optional.of(null)` causes NPE; use `ofNullable` when the input may be `null`.

## 9. Designing Public API Contracts

A good signature should be accompanied by documentation:
- **Preconditions:** are `null`, blank strings, or negative numbers allowed? Which conditions are user-fixable validation and which are caller errors?
- **Success:** can it return `null`? Is absence or multiple variants possible? Do records allow nullable fields?
- **Failure:** which checked exceptions are in `throws`; which important unchecked exceptions must be documented; how are I/O errors and `cause` preserved?
- **Side effects:** does the method only check or actually write data? Is retry safe?
- **Compatibility:** does adding a result subtype or changing `T` to `Optional<T>` require callers to change?

Changing `Product findById(String)` to `Optional<Product> findById(String)` is a **Java signature change**, forcing callers to update. For published libraries, consider creating a new API with a clear name and a migration path. Adding a new variant to a sealed result hierarchy is also a contract change for callers that assumed the old set of cases. Do not treat `Result<T,String>` as a compatibility guarantee when the meanings of strings can change arbitrarily.

When standardized results are needed across many APIs, `Result<T,E>` can be used with `E` as a domain error type. However, avoid abstracting just to replace a simple “present/absent” two-value case with a heavy wrapper.

## 10. Contract-Based Test Matrix

| Input / Scenario | Expected Behavior | Key Assertion |
| --- | --- | --- |
| `findProduct("P01")` | Optional containing Product | Value is present and has the right SKU |
| `findProduct("P02")` | Empty Optional | Does not throw due to missing record |
| `findProduct("")` | `IllegalArgumentException` | Invalid input does not turn into `empty()` |
| `quote("P01", 2)` | `Accepted` | Correct SKU and quantity |
| `quote("P01", 8)` | `OutOfStock` | `requested=8`, `available=5` |
| `quote("P02", 1)` | `UnknownProduct` | Not confused with query error |
| `quote("P01", 0)` | `InvalidQuantity` | Error code for caller to fix input |
| Both invalid quantity and nonexistent SKU | `InvalidQuantity` in the example | Stable validation order |
| File read denied | `IOException` or wrapper with cause | Does not fall into the “absent” branch |
| API wrapping I/O error | `UncheckedIOException` with original cause | Does not lose diagnostic context |

In the illustrative program, `STOCK` is an immutable Map so no I/O error occurs; to test infrastructure errors, you need to provide a dependency that simulates failure. Tests should verify **the result type and its inner fields**, not just `toString()` strings or messages.

## 11. Final Decision Checklist

1. If there is only **a single value or normal absence**, use `Optional<T>`; do not use it to hide errors.
2. If there are **multiple expected business outcomes requiring different handling**, use a specifically typed result type, such as a sealed hierarchy.
3. If a **precondition violation, invariant violation, or abnormal execution failure** occurs, use an appropriate exception instead of turning it into an “empty success” code.
4. Ensure values and errors carry enough data for the caller to act on, without forcing the caller to parse wording.
5. Document nullability, validation order, recoverability, side effects, and retry safety.
6. When translating exceptions, preserve `cause`; when translating results to HTTP/UI, map at the communication boundary.
7. Test success, absence, all business branches, invalid input, and external dependency failures.

**Practice Exercise:** Design `parseAge(String raw)` for a form that may receive a blank string, non-numeric text, an out-of-range number, or a valid age. Explain the benefits of `MissingAge`, `NotANumber`, `OutOfRange`, and `ValidAge` compared to `Optional<Integer>`. Then design `findUserById(long id)` where `id` is valid and a “not found” result is normal: `Optional<User>` may be the clearest choice. Finally, simulate an I/O error in the data repository and demonstrate that the API does not equate “query failed” with “user does not exist”.

Core criterion: **return types and exceptions must accurately express the real-world meaning of each outcome**, helping callers make the right decisions.