# Sealed Types and Generics in Domain Modeling

## 1. The Design Problem: Finite Cases, Each Carrying Its Own Typed Data

In Java 17, **sealed classes/interfaces** and **generics** answer two different questions that complement each other very well:

- **Sealed:** Which *subtypes* does a domain allow? Who has the right to add a new case?
- **Generics:** Which *type of data* is a valid case carrying? How far can the compiler check values passed through an API?

Suppose an e-commerce application has the following operations:

1. Find an order by ID, returning an `Order` if found.
2. Look up a customer, returning a `Customer` if found.
3. Calculate the amount of an order, returning a `Long`.

Each operation can **succeed** or **fail**, yet the success data differs. We want to express:

```text
Outcome<T>                        T = data type of the success result
│
├── Success<T>                    contains value of type T
│
└── Failure<T>                    contains error information

Outcome<Order>                    order lookup result
Outcome<Customer>                 customer lookup result
Outcome<Long>                     amount calculation result
```

This is a classic domain modeling problem: **closing the permitted set of cases** while **preserving the static type of the payload** across service, domain, and adapter layers.

Java 17 standardized sealed classes/interfaces (JEP 409). In this lesson, the examples use only language features **stable on JDK 17**, without relying on preview features.

## 2. Why Does a Model Missing Sealed or Missing Generics Break Easily?

### 2.1. Using Only `Object`: Ambiguous Result Types

An overly generic API might return:

```java
record OperationResult(boolean success, Object value, String error) {
}
```

All of the following states can be constructed:

```java
new OperationResult(true, "not an Order", null);
new OperationResult(false, new Object(), null);
new OperationResult(true, null, "both succeeded and failed");
```

Callers must cast from `Object`, manually inspect `success`, and infer whether `value` and `error` are allowed to coexist. The set of constructible states is larger than the set of valid business states.

### 2.2. Using Only an Open Generic Interface: Typed Payload, Uncontrolled Case Set

```java
interface Outcome<T> {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String reason) implements Outcome<T> {
}
```

This preserves the success value's type. However, another library or piece of code can arbitrarily declare:

```java
record Unexpected<T>(Object content) implements Outcome<T> {
}
```

If the domain truly has only two branches, `Success` and `Failure`, an open interface cannot enforce that rule at compile time.

### 2.3. Combining Sealed and Generics to Clarify the Contract

```java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String reason) implements Outcome<T> {
}
```

Here:

1. `Outcome<T>` restricts the permitted **direct subtypes**: only `Success` and `Failure`.
2. `T` specifies the payload type in the success branch.
3. `Success<T>` and `Failure<T>` both fulfill the same `Outcome<T>` contract.
4. Both records are implicitly `final`; thus neither branch can be extended further.

For example, `Success<Order>` is a valid case of `Outcome<Order>`, whereas `Success<String>` **cannot** be assigned to an `Outcome<Order>` variable.

**Note:** `permits Success, Failure` lists the **classes/records permitted as subtypes**, not individual parameterized types such as `Success<Order>` or `Success<Customer>`. The `permits` list governs *inheritance structure*, while generics govern *data types*.

## 3. Complete Example: `Outcome<T>` with `map` and `fold`

A useful result model does more than declare two branches. We also want to:

- Return `Order`, `Customer`, and `Long` values under static type contracts.
- **Transform** the success value from `T` to `U` without losing the failure branch.
- **Handle** a result with two functions, one per case.
- Avoid forcing callers to cast from `Object`.

### 3.1. Complete Java 17 Code

Create the file **SealedGenericDemo.java**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class SealedGenericDemo {

    // T specifies the data type of the success branch.
    sealed interface Outcome<T> permits Success, Failure {

        <U> Outcome<U> map(Function<? super T, ? extends U> mapper);

        <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        );
    }

    record ErrorInfo(String code, String message) {
        public ErrorInfo {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
            if (code.isBlank() || message.isBlank()) {
                throw new IllegalArgumentException("Error must have a code and message");
            }
        }
    }

    // Success branch carries a payload of type T.
    record Success<T>(T value) implements Outcome<T> {
        public Success {
            Objects.requireNonNull(value, "value");
        }

        @Override
        public <U> Outcome<U> map(
                Function<? super T, ? extends U> mapper
        ) {
            Objects.requireNonNull(mapper, "mapper");
            U mapped = Objects.requireNonNull(
                    mapper.apply(value), "mapped value"
            );
            return new Success<>(mapped);
        }

        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        ) {
            Objects.requireNonNull(onSuccess, "onSuccess");
            Objects.requireNonNull(onFailure, "onFailure");
            return onSuccess.apply(value);
        }
    }

    // T is the expected result type; this branch carries only error information.
    record Failure<T>(ErrorInfo error) implements Outcome<T> {
        public Failure {
            Objects.requireNonNull(error, "error");
        }

        @Override
        public <U> Outcome<U> map(
                Function<? super T, ? extends U> mapper
        ) {
            Objects.requireNonNull(mapper, "mapper");
            return new Failure<>(error);
        }

        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        ) {
            Objects.requireNonNull(onSuccess, "onSuccess");
            Objects.requireNonNull(onFailure, "onFailure");
            return onFailure.apply(error);
        }
    }

    record Order(String id, long amountInCents) {
        public Order {
            Objects.requireNonNull(id, "id");
            if (id.isBlank() || amountInCents < 0) {
                throw new IllegalArgumentException("Invalid order");
            }
        }
    }

    static Outcome<Order> findOrder(String id) {
        if ("O-100".equals(id)) {
            return new Success<>(new Order("O-100", 125_000L));
        }
        return new Failure<>(
                new ErrorInfo("ORDER_NOT_FOUND", "Not found " + id)
        );
    }

    public static void main(String[] args) {
        for (String id : List.of("O-100", "O-999")) {
            Outcome<Order> found = findOrder(id);

            // Transform only the success payload.
            Outcome<Long> amount = found.map(Order::amountInCents);

            String message = amount.fold(
                    cents -> "Amount: " + cents + " cents",
                    error -> "Error " + error.code() + ": " + error.message()
            );

            System.out.println(message);
        }
    }
}
```

Compile and run with JDK 17:

```shell
java -version
javac --release 17 SealedGenericDemo.java
java SealedGenericDemo
```

Output:

```text
Amount: 125000 cents
Error ORDER_NOT_FOUND: Not found O-999
```

The example intentionally uses **records nested inside a class** so all code runs in a single file. In a real project, each type can be split into separate files and placed in the appropriate package/module.

### 3.2. `map` Preserves the Meaning of the Failure Branch

The signature:

```java
<U> Outcome<U> map(Function<? super T, ? extends U> mapper);
```

expresses transforming an `Outcome<T>` into an `Outcome<U>`.

- If the object is `Success<T>`, `mapper` transforms `value: T` into `U`, yielding `Success<U>`.
- If the object is `Failure<T>`, there is no success value to transform; the result is `Failure<U>` carrying the same error info.

For example:

```java
Outcome<Order> order = new Success<>(
        new Order("O-101", 50_000L)
);

Outcome<Long> total = order.map(Order::amountInCents);
```

Here `Order::amountInCents` is a function from `Order` to `Long`. The compiler infers `U = Long`. No cast is required and no payload is stored in `Object`.

The `Failure<T>` class still takes type parameter `T` despite having no field of type `T`, because it must belong to the same result type. For instance, `Failure<Order>` means **an operation expected to return an `Order` that failed**.

This design is a practical choice, not a mandatory Java rule. Some libraries separate the error type into a second generic type parameter or use a different error-handling API. The purpose of sealed/generics remains clarifying the domain and type contract.

### 3.3. `fold` Unifies Handling Both Branches into One API

The signature:

```java
<R> R fold(
        Function<? super T, ? extends R> onSuccess,
        Function<? super ErrorInfo, ? extends R> onFailure
);
```

The caller supplies two functions; the final result has type `R`. Each record executes its corresponding branch. For example:

```java
String label = findOrder("O-100").fold(
        order -> order.id() + " found",
        error -> error.code() + " - " + error.message()
);
```

In the success branch, the lambda receives the exact type `Order`, so it can call `order.id()`. In the failure branch, the lambda receives `ErrorInfo`. This reduces the need to scatter `instanceof` across classes that consume the result.

**Limitation to understand:** `fold` is a two-case handling API declared by the designer; Java does not generate it automatically from `sealed`. Permitted subtypes must implement this contract. If a new branch is later added to the model, you must revisit the meaning of `fold`, test its behaviors, and decide whether an additional handler branch is required.

## 4. Why Do Generics Matter When Placing Sealed Types in a Domain Model?

### 4.1. Preventing Data Mix-Ups Across Use Cases

Suppose you have:

```java
record Customer(String id, String name) {
}

Outcome<Order> orderResult = findOrder("O-100");
Outcome<Customer> customerResult =
        new Success<>(new Customer("C-1", "An"));
```

Assigning `customerResult` to an `Outcome<Order>` variable is a compile error. `sealed` alone does not catch a mismatched payload type; the generic parameter `T` is what establishes that constraint.

### 4.2. Declaring APIs Around Actual Data Needs

A repository or domain service can define:

```java
interface OrderLookup {
    Outcome<Order> findById(String id);
}

interface CustomerLookup {
    Outcome<Customer> findById(String id);
}
```

Both share the same success/failure case structure, yet callers do not have to guess what `Object` type a result holds. Return types clearly describe each use case's contract.

### 4.3. Combining Generics with Records

A record can have type parameters:

```java
record Page<T>(List<T> items, int totalItems) {
    public Page {
        items = List.copyOf(items);
        if (totalItems < items.size()) {
            throw new IllegalArgumentException("Invalid totalItems");
        }
    }
}
```

Then:

```java
Outcome<Page<Order>> orders =
        new Success<>(new Page<>(
                List.of(new Order("O-102", 10_000L)),
                1
        ));
```

This is a **nested generic type**: `Outcome` represents the operation result, `Page` represents paginated data, and `Order` is the domain entity/value.

`List.copyOf` produces a list that cannot be mutated through its API and rejects `null` elements. Still, if the elements are objects with mutable state, consider copying or protecting the inner objects. Records are not deeply immutable by default.

## 5. Sealed Types with Multiple Generic Parameters: Success Type and Error Type

In the first example, every error used `ErrorInfo`. In larger systems, individual use cases may want to encode the **error type** so the compiler distinguishes business errors from malformed data.

You can declare `DomainResult<T, E>`, where:

- `T` is the data type on success.
- `E` is the domain error type on failure.

Example:

```java
sealed interface DomainError permits OrderNotFound, InvalidOrder {
}

record OrderNotFound(String orderId) implements DomainError {
}

record InvalidOrder(String reason) implements DomainError {
}

sealed interface DomainResult<T, E extends DomainError>
        permits Ok, Err {
}

record Ok<T, E extends DomainError>(T value)
        implements DomainResult<T, E> {
}

record Err<T, E extends DomainError>(E error)
        implements DomainResult<T, E> {
}
```

In use:

```java
DomainResult<Order, OrderNotFound> loaded =
        new Err<>(new OrderNotFound("O-404"));

DomainResult<Order, InvalidOrder> checked =
        new Err<>(new InvalidOrder("Negative amount"));
```

In this model, `E extends DomainError` is a **bounded type parameter**. It ensures the error type belongs to the `DomainError` domain. If a team needs a result that can hold multiple kinds of errors, it can pick a designed common error type:

```java
DomainResult<Order, DomainError> result =
        new Err<>(new OrderNotFound("O-404"));
```

**Distinguish two guardrails:**

1. `DomainError` is sealed with branches `OrderNotFound` and `InvalidOrder`, restricting the direct error kinds.
2. `E extends DomainError` prevents arbitrarily using `String`, `Exception`, or a non-`DomainError` class as the error type.

Choosing a very narrow `E` (such as `OrderNotFound`) can be helpful for simple methods, yet also complicates signatures when a use case has multiple errors. In public APIs, balance type precision with readability and usability.

**Note on type invariance:** `DomainResult<Order, OrderNotFound>` is not automatically a `DomainResult<Order, DomainError>`. Java generics are **invariant**, even though `OrderNotFound implements DomainError`. The section below explains how to accept data flexibly when needed.

## 6. Sealed and Generics Control Two Different Kinds of Extension

### 6.1. `permits` Cannot Contain Concrete Type Arguments

You cannot write a list such as:

```java
// INVALID: permits expects subtype names, not
// parameterized generic applications.
sealed interface Outcome<T>
        permits Success<Order>, Success<Customer> {
}
```

To constrain `T` to a domain, use a **bounded type parameter**:

```java
sealed interface DomainEntity permits OrderEntity, CustomerEntity {
}

record OrderEntity(String id) implements DomainEntity {
}

record CustomerEntity(String id) implements DomainEntity {
}

static <T extends DomainEntity> T requireEntity(T entity) {
    return java.util.Objects.requireNonNull(entity);
}
```

`T extends DomainEntity` states that the payload type must belong to types compatible with `DomainEntity`. Meanwhile, the sealed `DomainEntity` defines direct inheritance limits.

This **does not** force `T` to be one specific class name from `permits`: `T` can be `DomainEntity` itself (the parent type), and a hierarchy with a `non-sealed` branch can still be extended indirectly. If stricter control over data types is needed, design the domain structure and APIs accordingly rather than expecting generic bounds to solve every case automatically.

### 6.2. `final`, `sealed`, and `non-sealed` Still Matter for Generic Subtypes

Example:

```java
sealed interface DataEvent<T> permits SavedEvent, ChangeEvent {
}

record SavedEvent<T>(T entity) implements DataEvent<T> {
}

non-sealed interface ChangeEvent<T> extends DataEvent<T> {
}

record UpdatedEvent<T>(T entity) implements ChangeEvent<T> {
}
```

`DataEvent` has only two direct permitted subtypes: `SavedEvent` and `ChangeEvent`. `SavedEvent` is a record, so inheritance stops there. However, `ChangeEvent` is `non-sealed`, allowing other subtypes to implement it and indirectly become `DataEvent`.

If business rules require a **strictly finite set of cases**, do not open a branch with `non-sealed` without good reason. Being generic does not change this rule.

### 6.3. Subtype Placement Is Still Constrained

In Java 17:

- A sealed type in a **named module** may permit direct subclasses only in the same **named module**.
- A sealed type in an **unnamed module** may permit direct subclasses only in the same **package**.

This is a sealed constraint regardless of whether the class/interface is generic. In modularized codebases, check architectural boundaries before making an interface sealed.

## 7. Variance and Wildcards: Using `Outcome<T>` Across Type Levels

Java generics are **invariant** by default. If `CustomerEntity implements DomainEntity`, `Outcome<CustomerEntity>` and `Outcome<DomainEntity>` remain distinct types.

```java
Outcome<CustomerEntity> customer =
        new Success<>(new CustomerEntity("C-1"));

// INVALID:
// Outcome<DomainEntity> entity = customer;
```

If you only need to **read** the result from the parent type's perspective, use a wildcard:

```java
static void printEntity(Outcome<? extends DomainEntity> outcome) {
    String text = outcome.fold(
            entity -> "Entity: " + entity,
            error -> "Error: " + error.message()
    );
    System.out.println(text);
}
```

This snippet builds on `Outcome` from the complete example and `DomainEntity` defined above. It accepts `Outcome<CustomerEntity>`, `Outcome<OrderEntity>`, and cases whose payload type is a subtype of `DomainEntity`.

```java
printEntity(new Success<>(new CustomerEntity("C-1")));
```

Because `? extends DomainEntity` does not tell you the **specific subtype**, callers can safely rely only on contracts present on `DomainEntity`. You cannot treat the payload as `CustomerEntity` or insert an arbitrary payload into a structure of unknown type.

### 7.1. Meaning of `? super T` and `? extends U` in `map`

The signature:

```java
<U> Outcome<U> map(Function<? super T, ? extends U> mapper);
```

uses wildcards in both directions:

- `? super T`: the function can **accept** a value of type `T` or a suitable supertype. For instance, a mapper accepting `Object` can still process an `Order`.
- `? extends U`: the function can **return** a value of type `U` or a subtype of `U`.

This applies the *Producer Extends, Consumer Super* (PECS) principle to data flowing into and out of a generic API.

Not every generic method needs complex wildcards. Add this flexibility only when it reflects real usage patterns while keeping the signature understandable.

### 7.2. Do Not Use Raw Types to Bypass the Compiler

Avoid:

```java
// Avoid:
Outcome result = new Success<>("abc");
```

`Outcome` here is a **raw type**; the compiler no longer enforces type `T` as intended. Raw types trigger unchecked warnings and defer errors to runtime.

Prefer:

```java
Outcome<String> result = new Success<>("abc");
```

If the payload type is genuinely unknown, `Outcome<?>` expresses that far more clearly than raw `Outcome`, though when consuming it you can rely only on `Object` or a known bound.

## 8. Type Erasure: `sealed` Does Not Keep Generic Payloads Fully Present at Runtime

Generics in Java are primarily checked at **compile time**. After compilation, much of the generic type argument information undergoes **type erasure**.

For example:

```java
Outcome<Order> order = new Success<>(new Order("O-1", 100L));
Outcome<String> text = new Success<>("hello");
```

At runtime, both can be instances of the `Success` class. The runtime does not automatically distinguish them as two separate classes `Success<Order>` and `Success<String>`.

This leads to important constraints:

### 8.1. Do Not Use `instanceof` with Non-Reifiable Parameterized Types

```java
Object any = new Success<>("hello");

// INVALID if checking a specific parameterized type at runtime:
// if (any instanceof Success<String>) { ... }

if (any instanceof Success<?> success) {
    Object value = success.value();
    System.out.println(value);
}
```

`Success<?>` checks the actual runtime type `Success` without pretending the runtime knows the specific type argument. The value read from `success.value()` in this example can only be treated as `Object`.

When you already have `Outcome<Order>` at compile time, leverage strongly typed APIs (`map`, `fold`) instead of checking the class and performing unchecked casts.

### 8.2. Do Not Overload Solely by Generic Type Parameters

These two overloads have the same signature after type erasure and cannot be declared side by side:

```java
// INVALID inside the same class:
// void handle(Outcome<Order> result) { }
// void handle(Outcome<Customer> result) { }
```

Give methods distinct names per use case, pass a type token when needed, or design an appropriate polymorphic API.

### 8.3. Sealed Reflection Differs from Generic Type Reflection

Java 17 supports inspecting sealed structure via `Class`:

```java
System.out.println(Outcome.class.isSealed());

for (Class<?> child : Outcome.class.getPermittedSubclasses()) {
    System.out.println(child.getSimpleName());
}
```

In the example above, the permitted types are `Success` and `Failure`. This reflection API tells you **which classes are permitted to inherit**, not a list of parameterized usages such as `Outcome<Order>`, `Outcome<String>`, and other type arguments.

Consequently, you cannot rely on `permits` or `getPermittedSubclasses()` to automatically validate the payload type of a deserialized object without an appropriate additional mechanism.

## 9. Handling Sealed Generic Results in Java 17

### 9.1. `instanceof` Patterns Are Stable

Java 17 supports pattern matching for `instanceof` (standardized in Java 16). Example when the concrete type argument is unknown:

```java
static String describeUnknown(Object candidate) {
    if (candidate instanceof Success<?> success) {
        return "Success: " + success.value();
    }
    if (candidate instanceof Failure<?> failure) {
        return "Failure: " + failure.error().code();
    }
    return "Not a supported Outcome";
}
```

Here `T` of `Success` is unknown; reading via `Object` is the safe approach. In code that already knows `Outcome<Order>`, using `fold` preserves the `Order` type much more cleanly.

### 9.2. Pattern Matching for `switch` Is Not Yet Stable in Java 17

Some articles on sealed types use:

```java
// Illustrates syntax from a later stage than Java 17; do not use as
// a stable Java 17 example:
// return switch (outcome) {
//     case Success<?> s -> "...";
//     case Failure<?> f -> "...";
// };
```

In **JDK 17**, pattern matching for `switch` is still a **preview** feature. It was standardized in **Java 21**; record patterns are also not a stable Java 17 feature. Therefore, lessons and applications compiling with `--release 17` should use `instanceof` patterns, polymorphism, or an API like `fold` depending on the goal.

With `if`/`instanceof` chains, Java 17 **does not automatically check exhaustiveness** against the sealed subtype list. Sealed governs **direct inheritance** rights; it does not prove that every business branch in a program has been handled.

### 9.3. Polymorphism Reduces Branching Dependencies

The `fold` example in Section 3 lets each `Success`/`Failure` branch invoke the matching function itself. For logic closely tied to each subtype, you can define abstract methods on the sealed interface and let subtypes implement them.

Not all processing belongs inside domain objects. If logic belongs to the HTTP, UI, persistence, or integration layer, keep it in the appropriate layer so the domain model does not take on unnecessary adapter dependencies.

## 10. Designing Error Types: One Generic Parameter vs. Two?

The two common forms have distinct trade-offs:

| Model | Example | Strengths | Considerations |
|---|---|---|---|
| Single parameter `T` | `Outcome<Order>` | Short signatures, easy to use, uniform error shape | Less detailed error typing at the API level |
| Two parameters `T, E` | `DomainResult<Order, DomainError>` | Captures both success and error payloads in static types | More complex APIs, factories, and return types |
| Two parameters with narrow error | `DomainResult<Order, OrderNotFound>` | Precisely documents the error a use case can produce | Harder to compose multi-step pipelines producing different errors |

For example, a pipeline combining lookup, business validation, and payment can produce several error kinds. If every method is forced to use an ultra-narrow `E`, composing results may require designing error-mapping operators (`mapError`, `flatMap`, or matching combinators). In such cases, using a shared sealed `DomainError` can fit better.

Sealed types and generics are **expressive tools**; they do not by themselves provide transactions, retries, exception handling, or validation. Those behaviors still must be designed around business requirements.

## 11. Relationship to `Optional<T>`, Exceptions, and `null`

`Optional<T>`, available since Java 8, is useful when a value **may be absent**, such as an optional lookup:

```java
java.util.Optional<Order> findOptionalOrder(String id);
```

However, `Optional.empty()` cannot explain **why** an operation failed: not found, invalid input, business rejection, or lack of permissions.

`Outcome<T>` makes both success and failure cases explicit with an error payload. Conversely, if an API only needs presence vs. absence without classifying errors, `Optional<T>` is usually simpler.

Exceptions remain useful where exceptional control flow is appropriate, especially unrecoverable errors within the call scope or infrastructure failures. Using a sealed result type does not mean every exception must be caught and mechanically converted into `Failure`.

Regarding `null`: generics do not forbid `null` by default. For example, `Success<String>(null)` compiles if the constructor does not check it. In the complete example, `Objects.requireNonNull` is a **design decision** to disallow `null` payloads inside `Success`.

## 12. Sealed Generics and Serialization / API Boundaries

Sealed generic models often appear in service/domain layers, yet when data crosses process boundaries via JSON, message brokers, or storage, keep in mind:

1. **Type erasure:** `Outcome<Order>` does not automatically retain full `Order` type info in every runtime or deserialization operation.
2. **Discriminator:** receivers may need a type-discriminating field like `SUCCESS`/`FAILURE` or a clear schema to know which variant to construct.
3. **Versioning:** when adding a new permitted subtype, older clients may not yet know how to parse or handle it.
4. **Generic payload:** serializers must know the exact payload type or receive appropriate metadata/schemas; do not assume runtime always has full type info from `T`.
5. **Framework constraints:** JSON, JPA, validator, or mapping libraries must be on versions supporting Java 17/record/sealed for the features actually used.

An external JSON contract might be designed as:

```json
{
  "kind": "SUCCESS",
  "data": {
    "id": "O-100",
    "amountInCents": 125000
  }
}
```

And the error case:

```json
{
  "kind": "FAILURE",
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "Not found O-999"
  }
}
```

This is merely an **API contract illustration**; Java `sealed` does not enforce JSON shape or auto-generate discriminators. You must configure serializers, validate untrusted input, and establish compatibility strategies when APIs evolve.

Records fit many DTOs/value objects, yet are not the default choice for every JPA entity with lifecycle hooks, proxies, and mutable state requirements. When integrating frameworks, separate **domain models**, **DTOs**, and **persistence entities** according to each layer's needs.

## 13. Risks When Evolving the Model Later

Suppose `Outcome<T>` initially has only `Success`/`Failure`. Later, business requirements add a **pending** case:

```java
sealed interface Outcome<T> permits Success, Failure, Pending {
}

record Pending<T>(String trackingId) implements Outcome<T> {
}
```

From a domain perspective, this changes the contract meaning of every `Outcome<T>`. If the interface has a `fold` method taking only two functions, handling `Pending` must be redesigned. Common options:

- Expand `fold` to three functions and update implementations along with all callers.
- Keep one phase's result binary and model asynchronous/pending state in a separate domain type.
- Evolve the API in a deliberately compatible way, such as a new version or dedicated contract adapters.

Do not force `Pending` into `Failure` merely to reuse an old signature if the domain does not consider pending a failure.

A small edit to a `permits` list can be a **semantic breaking change**, even when parts of the codebase still compile. For a shared library used across modules, treat adding or removing branches as a contract change requiring evaluation, documentation updates, and testing.

## 14. Common Design Mistakes

| Situation | Why to avoid | Suitable design approach |
|---|---|---|
| Using `Result<Object>` for every use case | Loses payload type information and invites bad casts | Declare `Result<Order>`, `Result<Customer>`, etc. |
| Sealed interface with an arbitrarily open `non-sealed` branch | Indirect cases are no longer truly closed | Use `record`/`final` at leaf branches when the domain must stay finite |
| Using `permits` as if it could restrict `T` | `permits` restricts direct subclasses, not substituted generic arguments | Use generic bounds or dedicated APIs for payload families |
| Assigning `Result<Child>` to `Result<Parent>` | Generics are invariant | Use wildcards for read-only APIs, or define conversion operations |
| Using raw `Result` | Loses type checking, causes warnings and runtime bugs | Specify type arguments or `Result<?>` when the type is unknown |
| Checking `instanceof Success<Order>` on `Object` | Type erasure makes parameterized types non-reifiable | Use `Success<?>` or strongly typed APIs |
| Confusing `sealed` with value validation | `sealed` only governs inheritance | Use constructor validation, domain invariants, and tests |
| Assuming records are deeply immutable | Fields can still reference mutable objects | Make defensive copies or use immutable components |
| Using pattern `switch` as stable Java 17 syntax | Pattern matching for `switch` is preview in Java 17 | Use `instanceof` patterns, polymorphism, or `fold` |
| Trying to replace every exception with generic results | Bloats APIs and can mask system failures | Distinguish expected business failures from unexpected errors |
| Serializing without a branch discrimination contract | Receivers may not know which subtype or payload type to expect | Design explicit discriminators, schemas, and versioning |

## 15. Practice Roadmap for Domain Modeling with Sealed Types and Generics

### Exercise 1 — User Authentication Result

Design:

```text
AuthenticationResult<T>
├── Authenticated<T>(T principal)
├── AuthenticationRejected<T>(reason)
└── AdditionalVerification<T>(challengeId)
```

Requirements:

1. Declare the sealed interface and three generic records, with all three as direct permitted cases.
2. `principal` in the success branch must have type `T`.
3. Write a service returning `AuthenticationResult<UserPrincipal>`.
4. Write a presentation function using Java 17 `instanceof` patterns or a three-branch `fold` contract.
5. Evaluate whether additional verification is a final outcome of the operation or belongs to a separate workflow model.

### Exercise 2 — Two Type Parameters and Domain Errors

Create `InventoryResult<T, E extends InventoryError>` with two branches `Available` and `Unavailable`; `InventoryError` is a sealed interface containing `OutOfStock` and `InvalidSku`.

Requirements:

1. Write type declarations compatible with JDK 17 without preview flags.
2. Construct `InventoryResult<Product, InventoryError>` values for both success and failure.
3. Try assigning `InventoryResult<Product, OutOfStock>` to `InventoryResult<Product, InventoryError>`; explain why the compiler rejects it.
4. Identify when a general error type is preferable vs. when a narrow error type helps.

### Exercise 3 — Transforming Results Without Dropping Errors

Using `Outcome<T>` from Section 3, build the pipeline:

```text
findOrder(id)
  -> Outcome<Order>
  -> map(Order::amountInCents)
  -> Outcome<Long>
  -> map(cents -> cents > 100_000L)
  -> Outcome<Boolean>
```

Test with an existing ID and a non-existent ID. Explain why the mapper does not run in the `Failure` branch, and why the error information remains intact as the success type changes from `Order` to `Boolean`.

### Exercise 4 — Testing Sealed and Type Erasure Limits

1. Try creating `record Skipped<T>(String reason) implements Outcome<T>` without declaring it in `permits`; read the compile error message.
2. Try writing `if (obj instanceof Success<Order>)` when `obj` has type `Object`; find out why it is rejected.
3. Change it to `if (obj instanceof Success<?> s)`; identify what type can be safely read from `s.value()`.
4. Call `Outcome.class.getPermittedSubclasses()`; distinguish permitted class info from generic type argument info.

### Exercise 5 — Architectural Decision

Consider a platform where partners can write custom report-export plugins. Each plugin may return different data and add result kinds depending on plugin features.

Distinguish **which boundary should be closed with `sealed`** (e.g., standard orchestration outcomes owned by the platform), **which boundary must stay open** (e.g., the plugin SPI), and **which boundary needs generics** (e.g., the data type returned by a plugin). A solid solution may use both sealed interfaces and open interfaces at different levels.

## 16. Post-Lesson Self-Assessment

You have mastered this topic when you can answer these questions:

1. How does `sealed` controlling subtypes differ from generics controlling payloads?
2. Why cannot `Outcome<Order>` be assigned to `Outcome<Object>` or vice versa?
3. Why can `Failure<T>` carry type parameter `T` without having a field of type `T`?
4. How does `map` preserve the error while changing type `T` to `U`?
5. How does `fold` differ from writing sequential `if`/`instanceof` checks?
6. What does `E extends DomainError` check versus what sealed `DomainError` checks?
7. Why is `permits Success<Order>` invalid?
8. How does type erasure affect `instanceof`, overloading, and deserializing generic payloads?
9. Why must you think carefully before adding a new result branch?
10. Which handling approaches in this lesson run stably on Java 17, and which Java version finalized pattern `switch`?

## 17. References

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design decisions and sealed rules standardized in Java 17.
- [Java Language Specification — Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): generic types, type parameters, type erasure, sealed classes/interfaces, and inheritance rules.
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/): APIs for `Class`, `Function`, `Objects`, `List`, and Java SE 17 types.
- [dev.java — Learn Java](https://dev.java/learn/): Java language documentation on generics, records, and object design.

When designing a domain model, start with the question **"Which cases does the system permit, and what data does each case carry?"**. `sealed` restricts valid cases; generics ensure each case carries a properly typed payload. Combining both clarifies domain contracts, reduces casts, and provides a safe foundation for evolving Java 17 applications.
