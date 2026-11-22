# Splitting Business Logic into Small Functions with Clear Inputs and Outputs in Java

## 1. The Problem: A Method That Does Everything Is Hard to Understand and Test

When implementing a business process, we often need to do several different things: normalize data, check conditions, perform calculations, decide policies, persist data, and return results. If all of this is crammed into one long method, readers struggle to tell **what data goes in, which rules apply, what result comes out, and which steps have side effects**.

For example, a `checkout()` method might read from the database, calculate discounts, create an invoice, write logs, and send notifications all at once. These operations have different types of dependencies and different ways of being tested. Functional design aims to break them into **transformations with clear contracts**, then compose them into the overall business flow.

Goals of this lesson:

1. Identify **business steps with distinct meaning**, rather than splitting methods mechanically by line count.
2. Define each function's **input**, **output**, pre/postconditions, and possible errors.
3. Prefer **pure functions** (*pure functions*) for computation and decision logic that can be separated from I/O.
4. Avoid mutation and hidden dependencies that make function calls produce unexpected results.
5. Compose small functions into a pipeline or orchestrator that is **easy to read, easy to test, and easy to change**.
6. Place database writes, notifications, and external service calls at **clear side-effect boundaries**.

**More functions do not automatically mean good design.** A good small function must have **one named responsibility**, accept enough data to do its job, and return a meaningful value/effect.

## 2. What Does a Function with Clear Inputs and Outputs Mean?

A function is often described as a mapping:

~~~text
input (data/conditions) ──► function ──► output (value/result)
~~~

Example:

~~~java
static int lineTotal(int unitPrice, int quantity) {
    return Math.multiplyExact(unitPrice, quantity);
}
~~~

This is an **illustrative method** with two `int` inputs and one `int` output. With `unitPrice=12` and `quantity=3`, it returns `36`. `Math.multiplyExact` also explicitly expresses the rule **throw `ArithmeticException` if multiplication overflows the `int` range**, instead of silently producing an overflowed value.

A function contract should answer:

| Question | What Must Be Clear |
|---|---|
| What does the function receive? | Parameter types, meaning, and data units |
| What does the function return? | Return type, business meaning, whether it can be empty/null |
| Preconditions? | Valid inputs, required data, value domain |
| Postconditions? | Which rules the result reflects, which invariants are preserved |
| Does it mutate state? | Whether it mutates parameters/fields, writes to DB, or does I/O |
| How can it fail? | Exceptions, error result types, or absent-value branches |
| Does it have external dependencies? | Clock, random, global config, services, network |
| Is it safe to rerun? | Same input gives same output, whether it causes repeated side effects |

Not every function is forced to use only primitives. On the contrary, **a well-named input data type** is often better than a method taking too many loose parameters like `apply(int a, int b, boolean x, int y, String z)`.

## 3. Inputs and Outputs as Business-Meaningful Data Types

### 3.1. Avoiding “Primitive Obsession”

If a business domain uses money, quantity, and discount rate, all of them might be `int`s yet **carry completely different meanings**. The following method makes it easy to pass arguments in the wrong order:

~~~java
static int calculate(int a, int b, int c, int d) {
    return a * b - c + d;
}
~~~

Callers have a hard time knowing whether `a` is unit price or quantity, or whether `c` is discount or shipping fee.

Improve it with function names, parameter names, and data types:

~~~java
record Line(String sku, int unitPrice, int quantity) {}

static int subtotal(Line line) {
    return Math.multiplyExact(line.unitPrice(), line.quantity());
}
~~~

Here `Line` represents a line item, and `subtotal` has a clear purpose. Note that a record does not automatically validate `quantity > 0` or `unitPrice >= 0`; those constraints should be encoded in the constructor or at the data validation boundary.

### 3.2. Records Make Outputs Transparent

A quote calculation might return multiple quantities:

~~~java
record Quote(int subtotal, int discount, int shipping, int total) {}
~~~

Instead of returning an `int[]` array that forces callers to remember positions `0,1,2,3`, a record provides named accessors `subtotal()`, `discount()`, `shipping()`, and `total()`.

However, **a record does not automatically make every object deeply immutable**. A record only holds its components in `final` fields; if a component is a `List<MutableItem>`, callers can still mutate its elements. To make a model immutable, you need to check **the entire object graph and apply defensive copying** when needed.

## 4. A Business Example: Calculating a Quote with Independent Steps

Suppose the requirements are:

- Each order line has a unit price and a quantity.
- `subtotal` is the sum of `unitPrice × quantity`.
- Members receive a **10% discount on `subtotal`**, rounded down using integer division for non-negative values.
- Shipping fee is **15** if the amount after discount is **less than 100**; otherwise **0**.
- Total payable is `subtotal - discount + shipping`.
- Input data must be valid; the quote calculation flow **must not write to a database or mutate order lines**.

This can be split into steps:

~~~text
Order ──► subtotal ──► discount ──► afterDiscount ──► shipping
             │            │                              │
             └────────────┴───────────► Quote ◄──────────┘
~~~

Instead of mixing everything into one giant lambda, each rule has a name and a contract:

| Function | Input | Output | Responsibility |
|---|---|---|---|
| `lineCost(Line)` | A valid order line | `int` | Calculate cost of one line |
| `subtotal(Order)` | List of order lines | `int` | Sum line costs |
| `discount(int, boolean)` | Subtotal, member status | `int` | Discount rule |
| `shipping(int)` | Total after discount | `int` | Shipping fee rule |
| `quote(Order, boolean)` | Order and member status | `Quote` | Coordinate calculations into the final result |

The diagram shows **data dependencies**; it does not force the program to use a single Stream API pipeline for all steps. An orchestrator with a clear call order is often easier to understand than a nested chain of `map` calls.

## 5. Complete Java 17 Program: Small Functions, Clear Contracts, and Immutable Results

Save file **`FunctionalOrderPricingDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class FunctionalOrderPricingDemo {
    record Line(String sku, int unitPrice, int quantity) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("invalid price or quantity");
            }
        }
    }

    record Order(List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("order is empty");
            }
        }
    }

    record Quote(int subtotal, int discount, int shipping, int total) {}

    static int lineCost(Line line) {
        return Math.multiplyExact(line.unitPrice(), line.quantity());
    }

    static int subtotal(Order order) {
        return order.lines().stream()
                .mapToInt(FunctionalOrderPricingDemo::lineCost)
                .reduce(0, Math::addExact);
    }

    static int discount(int subtotal, boolean member) {
        return member ? subtotal / 10 : 0;
    }

    static int shipping(int afterDiscount) {
        return afterDiscount < 100 ? 15 : 0;
    }

    static Quote quote(Order order, boolean member) {
        int sub = subtotal(order);
        int off = discount(sub, member);
        int afterDiscount = Math.subtractExact(sub, off);
        int delivery = shipping(afterDiscount);
        int total = Math.addExact(afterDiscount, delivery);
        return new Quote(sub, off, delivery, total);
    }

    public static void main(String[] args) {
        Order order = new Order(List.of(
                new Line("pen", 12, 3),
                new Line("book", 25, 2)
        ));

        Quote regular = quote(order, false);
        Quote member = quote(order, true);

        System.out.println("regular=" + regular);
        System.out.println("member=" + member);
        System.out.println("lines=" + order.lines());
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac FunctionalOrderPricingDemo.java
java FunctionalOrderPricingDemo
~~~

Stdout:

~~~text
regular=Quote[subtotal=86, discount=0, shipping=15, total=101]
member=Quote[subtotal=86, discount=8, shipping=15, total=93]
lines=[Line[sku=pen, unitPrice=12, quantity=3], Line[sku=book, unitPrice=25, quantity=2]]
~~~

**Step-by-step walkthrough:**

1. `lineCost(pen) = 12 × 3 = 36`; `lineCost(book) = 25 × 2 = 50`.
2. `subtotal(order)` sums both lines, yielding `86`.
3. For a regular customer, `discount(86, false) = 0`. For a member, `discount(86, true) = 86 / 10 = 8` due to integer division.
4. Both `86` and `78` after discount are below the `100` threshold, so the shipping fee is `15`.
5. Regular total is `86 - 0 + 15 = 101`; member total is `86 - 8 + 15 = 93`.
6. `quote()` only coordinates the calculations and returns a new `Quote`. It does not write files, call a database, or modify `Order`.
7. `Order`'s constructor uses `List.copyOf` to create an unmodifiable list and prevent external structural modification of the input. Because `Line` contains `String` and primitive fields, the elements in the example have stable value state.
8. `Math.multiplyExact`, `Math.addExact`, and `Math.subtractExact` help detect overflow in key integer operations. Discount rules also need domain-range control; in the example, inputs are validated and values are small so no overflow occurs.

**Further design improvements:** in real monetary applications, clearly define **the smallest currency unit**, rates, rounding policies, taxes, stacked discounts, and value-domain limits. You can use `long` or `BigDecimal` depending on the business domain. Those decisions belong to the function's **contract**, and should not be left to be inferred from a short arithmetic expression.

## 6. Why Do Small Functions Make Testing More Effective?

When each step has explicit inputs/outputs, it can be tested independently:

| Rule | Test Input | Expected |
|---|---|---|
| `lineCost` | Unit price `12`, quantity `3` | `36` |
| `subtotal` | Two line totals `36` and `50` | `86` |
| `discount` | `86`, member | `8` |
| `discount` | `86`, non-member | `0` |
| `shipping` | `78` | `15` |
| `shipping` | `100` | `0` |
| `quote` | Sample order, member | `Quote(86,8,15,93)` |
| Validation | Quantity `0` | Throws `IllegalArgumentException` |
| Overflow | Multiplication exceeds `int` | Throws `ArithmeticException` |

In a “one method does everything” design, testing a shipping-fee rule might require mocking repositories, setting up a fake database, or walking through unrelated branches. With `shipping(int)`, testing right at the boundary values `99` and `100` is enough to prove the threshold policy in isolation.

**The ideal unit of testing is a meaningful behavior**, not just “one function per line”. Splitting `return x + 1;` into three anonymous helpers that force readers to jump across multiple files can make the design worse.

### 6.1. Testing Rules at Boundary Values

Example shipping fee rule:

~~~java
static int shipping(int afterDiscount) {
    return afterDiscount < 100 ? 15 : 0;
}
~~~

The cases `99`, `100`, and `101` clearly distinguish the “less than” branch from “less than or equal to”. If a rule is written vaguely as “free shipping when near 100” without an exact condition, implementation and QA teams can easily interpret it differently.

**For a specific function**, beyond input/output you must define **boundaries**, invalid data, rounding behavior, and errors: for example, is `afterDiscount < 0` allowed, should it throw an exception, or will it be guaranteed by the caller?

## 7. Separating Normalization, Validation, and Decision into Three Kinds of Functions

In a registration problem, we can separate:

1. **Normalize:** convert raw input into a canonical form.
2. **Validate:** return valid/invalid errors without logging or throwing exceptions for every ordinary business error.
3. **Decide:** produce a decision based on the validated result.

Example data flow:

~~~text
Registration raw
    │
    ▼ normalize(raw) ──────────► Registration normalized
                                   │
                                   ▼ validate(normalized)
                               List<String> errors
                                   │
                                   ▼ decide(normalized, errors)
                                  Decision
~~~

Benefit: trim/lowercase rules are not mixed with age-limit rules or database-write effects. When a policy changes, a single step can be modified and tested independently.

### 7.1. Distinguishing Programming Errors from Business Errors

Input with a malformed email or underage value can be represented by a **validation result** containing errors. That differs from a programming error such as passing a `null` object forbidden by the contract, which may warrant `Objects.requireNonNull` or an exception.

There is no universal rule that every business error must return `List<String>`. You can use an enum, a `ValidationError` record, a project-specific result type, or exceptions when appropriate. What matters is that **the function's contract is consistent**, never forcing callers to guess what a `null` return value means.

## 8. Complete Java 17 Program: Normalization and Validation Without I/O

Save file **`FunctionalRegistrationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FunctionalRegistrationDemo {
    record Registration(String username, String email, int age) {}

    record Decision(Registration normalized, List<String> errors) {
        Decision {
            errors = List.copyOf(errors);
        }

        boolean accepted() {
            return errors.isEmpty();
        }
    }

    static Registration normalize(Registration input) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(input.username(), "username");
        Objects.requireNonNull(input.email(), "email");

        return new Registration(
                input.username().strip(),
                input.email().strip().toLowerCase(Locale.ROOT),
                input.age()
        );
    }

    static List<String> validate(Registration value) {
        List<String> errors = new ArrayList<>();

        if (value.username().isBlank()) {
            errors.add("username.required");
        }
        if (!value.email().contains("@")) {
            errors.add("email.invalid");
        }
        if (value.age() < 18) {
            errors.add("age.under18");
        }
        return List.copyOf(errors);
    }

    static Decision decide(Registration input) {
        Registration normalized = normalize(input);
        List<String> errors = validate(normalized);
        return new Decision(normalized, errors);
    }

    public static void main(String[] args) {
        Decision valid = decide(
                new Registration("  Mai  ", " Mai@Example.COM ", 20));
        Decision invalid = decide(
                new Registration("   ", "invalid", 16));

        System.out.println("valid=" + valid);
        System.out.println("accepted=" + valid.accepted());
        System.out.println("invalid=" + invalid);
        System.out.println("accepted=" + invalid.accepted());
    }
}
~~~

Run:

~~~bash
javac FunctionalRegistrationDemo.java
java FunctionalRegistrationDemo
~~~

Stdout:

~~~text
valid=Decision[normalized=Registration[username=Mai, email=mai@example.com, age=20], errors=[]]
accepted=true
invalid=Decision[normalized=Registration[username=, email=invalid, age=16], errors=[username.required, email.invalid, age.under18]]
accepted=false
~~~

**Why is this split sensible?**

- `normalize` only standardizes representation. It **does not fully validate** the email or age.
- `validate` handles business rules expressible on a normalized `Registration`, then returns an unmodifiable list of errors. It uses an **internal** `ArrayList` to build the result—using local mutable state does not automatically give the function external side effects if that state is never exposed and the observable result is deterministic.
- `decide` is an orchestrator connecting both transformations and packaging the result in `Decision`, letting callers clearly see the normalized data, errors, and acceptance status.
- `Decision` derives `accepted()` from the error list; there is no need to store a mutable flag that someone has to keep synchronized after changing errors.
- Adding a maximum-age check or username-format rule can be done inside `validate` without touching normalization or callers.
- To validate real emails in production, define a specific contract and use an appropriate validator; the `contains("@")` check **is only an illustration of a simple rule**, not a complete email validation standard.

**Failure cases:** `normalize` rejects a `null` `input` or `null` string fields. Inputs like an email missing `@` or age `16` are reported as business error results. This clearly separates **precondition failures** from **validation failures**.

## 9. The Pure Core and Side-Effecting Shell Model

A useful way to organize code is **functional core, imperative shell**:

- **Functional core** consists of functions that compute, normalize, decide, and transform data from inputs and return outputs. Most of it can be tested using only inputs and outputs.
- **Imperative shell** receives requests, reads external config/data, calls the core, saves to the DB, emits events, or returns HTTP responses. This is where **side effects are made explicit**.

~~~text
HTTP/CLI/Service request
        │
        ▼
Shell: read data, determine context
        │
        ▼
Core: validate → calculate → decide
        │
        ▼
Shell: save results / publish events / return response
~~~

You do not necessarily have to organize this into literally two packages in a codebase. It is a **principle of separating responsibilities**; methods with real effects should have names and contracts indicating that they perform I/O or update state.

### 9.1. Why Should You Not Write to the DB Inside `map`?

~~~java
// Warning: hidden side effect inside transformation.
List<Receipt> receipts = requests.stream()
        .map(request -> {
            Receipt receipt = calculate(request);
            repository.save(receipt);  // Writes to DB inside mapper.
            return receipt;
        })
        .toList();
~~~

The snippet above is an illustration using hypothetical existing classes and methods. It mixes two responsibilities: **computation** and **persistence**. Later, if you want to reuse `calculate` for a preview without saving, or handle retries/transactions separately, the code becomes hard to control. Adding parallelism, short-circuiting, or a different terminal operation also makes relying on callback invocation counts as a business guarantee dangerous.

Instead, **separate the effects clearly**:

~~~java
List<Receipt> receipts = requests.stream()
        .map(this::calculate)
        .toList();

repository.saveAll(receipts);
~~~

These two statements make the boundary obvious: first only create the values, then perform the persistence step. Of course, a real application still needs to design transactions/idempotency, partial failures, and write permissions; splitting the lines of code does not automatically solve all of those problems.

## 10. Java 17 Program: Compute First, Call Effects Afterward

Save file **`FunctionalCoreShellDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FunctionalCoreShellDemo {
    record Request(String id, List<Integer> prices) {
        Request {
            prices = List.copyOf(prices);
        }
    }

    record Receipt(String id, int total) {}

    static Receipt calculate(Request request) {
        int total = request.prices().stream()
                .mapToInt(Integer::intValue)
                .sum();
        return new Receipt(request.id(), total);
    }

    static class InMemoryStore {
        private final List<Receipt> saved = new ArrayList<>();

        void save(Receipt receipt) {
            saved.add(receipt);
            System.out.println("saved:" + receipt.id() + ":" + receipt.total());
        }

        int size() {
            return saved.size();
        }
    }

    public static void main(String[] args) {
        List<Request> requests = List.of(
                new Request("A", List.of(10, 20)),
                new Request("B", List.of(7, 8))
        );

        List<Receipt> receipts = requests.stream()
                .map(FunctionalCoreShellDemo::calculate)
                .toList();

        System.out.println("computed=" + receipts);

        InMemoryStore store = new InMemoryStore();
        receipts.forEach(store::save);
        System.out.println("stored=" + store.size());
    }
}
~~~

Compile and run:

~~~bash
javac FunctionalCoreShellDemo.java
java FunctionalCoreShellDemo
~~~

Stdout:

~~~text
computed=[Receipt[id=A, total=30], Receipt[id=B, total=15]]
saved:A:30
saved:B:15
stored=2
~~~

**Analysis:**

1. `Request` holds a structural snapshot of the price list using `List.copyOf`. With immutable `Integer` elements and non-null sample data, the request cannot be structurally mutated from outside.
2. `calculate(Request)` has the contract **one request → one receipt**. It only sums the prices and creates a new record, without writing to `store`.
3. `map(FunctionalCoreShellDemo::calculate).toList()` produces the list of receipts; `computed` is printed **before** any `saved` line appears.
4. `store.save` is the step with a side effect, called separately after all values have been computed. `InMemoryStore` is only a simulation to make the boundary clear, not a real database/transaction mechanism.
5. `forEach` here is called on `List<Receipt>`, with a clear order in this sequential example; if transactions/retries are needed in production, use a service/repository with an appropriate contract instead of relying on `forEach` to automatically guarantee atomicity.
6. The sums in the example use `int` and small data. For money or large datasets, you need an overflow policy and appropriate data types.

The lesson is not that all side effects are “bad”: they should be **made explicit in the name/contract and placed where they are easy to control**.

## 11. How Do Java Functional Interfaces Support Design?

You do not need to create a class for every transformation. Java provides standard interfaces:

| Type | Shape | When Appropriate |
|---|---|---|
| `Function<T,R>` | `T → R` | Convert one value to another value |
| `UnaryOperator<T>` | `T → T` | Transform within the same type |
| `Predicate<T>` | `T → boolean` | Test a condition |
| `BiFunction<T,U,R>` | `(T,U) → R` | Function taking two parameters |
| `Supplier<T>` | `() → T` | Supply a value when called |
| `Consumer<T>` | `T → void` | Perform an action with side effects |
| `IntFunction<R>`, `IntUnaryOperator` | Primitive variants | Avoid boxing when reasonable |

**Functional interfaces express technical signatures, not business semantics.** For example, a `Function<Order,Quote>` does not by itself prove that every `Order` is valid, has no I/O, or always computes prices correctly. Those guarantees come from **contracts, implementation, and tests**.

### 11.1. `compose` and `andThen`: Chaining Transformations with Matching Contracts

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        s -> s.toUpperCase(Locale.ROOT);

Function<String, String> normalized = trim.andThen(upper);

System.out.println(normalized.apply("  hello  ")); // HELLO
~~~

This is illustrative code, requiring `import java.util.function.Function;` and `import java.util.Locale;`.

- `trim.andThen(upper)` applies `trim` **first**, then `upper`.
- `upper.compose(trim)` produces the corresponding transformation order.
- `compose` and `andThen` only connect type-compatible functions; they **do not automatically solve** null checks, exceptions, side effects, or undefined business conditions.

### 11.2. Choosing Between Methods and Lambdas

A named business rule like `calculateShipping` is often easier to read and reuse than a long lambda:

~~~java
// Assuming calculateShipping(int) is available.
IntUnaryOperator shippingPolicy = MyPolicy::calculateShipping;
~~~

But there is no need to turn **every** method into a `Function`/`Supplier` or pass callbacks through many layers. If a function is only used directly in one place, calling a regular method is usually clearer. Functional interfaces are most useful when **you need to pass behavior** (such as a replaceable discount policy).

## 12. Separating Responsibilities Without Over-Fragmentation

An important question: **when should you extract a new function?**

Consider extracting when:

- The step has a **specific business name** like `validateAddress`, `discountForMember`, `calculateTax`.
- The step can be **tested independently** across multiple edge cases.
- The rule is likely to **change independently**.
- The step has **stable enough inputs/outputs** to be reused.
- Extracting helps **clarify side effects or error contracts**.
- The step needs the same rule in multiple places without copy-pasting.

**Do not split mechanically** if:

- The helper merely renames a very simple expression while forcing readers to jump across multiple files to follow the business flow.
- The new function takes a pile of local variables from the old function without a clear domain concept.
- An intermediate value only serves a single expression right next to it and the variable name is already clear enough.
- Splitting causes dependencies to be hidden in global state/mutable fields instead of passing explicit inputs.
- Creating multi-layered abstract classes/strategies/factories just to handle a fixed rule with no extension requirement.

**Cohesion (*cohesion*) matters more than absolute method shortness.** A 20-line function performing one named decision with one clear result can be better than 10 one-line functions that are hard to trace.

## 13. Designing Clear Error Contracts

When splitting business logic, callers need to know **what the function will do if the data is invalid**.

Common options:

1. **Throw exceptions for precondition violations**: e.g., `Objects.requireNonNull(input)`, `IllegalArgumentException` if a negative quantity is a misuse of the API.
2. **Return a structured validation result**: suitable when users can submit multiple invalid fields and all errors need to be displayed.
3. **Use `Optional<T>`**: suitable when a result can be **legitimately absent** without needing detailed error descriptions.
4. **Use a dedicated result type** such as a sealed interface or record holding status/error: useful when multiple business branches must be distinguished.
5. **Separate I/O errors** from computation errors: DB writes can fail due to network issues, but a pure discount function should not force callers to handle network exceptions.

Do not let `null` carry multiple meanings (“not found”, “error”, “not yet computed”, “validly empty”). Such ambiguities make a function's output unclear.

### 13.1. Validation Should Be Independent of Decisions and I/O

In the registration problem, `validate` returns a list of errors, while `decide` packages the status and normalized data. When an accepted registration needs to be saved, the **shell** reads `decision.accepted()` and calls the repository. Thus, validation tests need no DB, and repository tests need not re-execute every normalization rule.

In real systems, validation results can become stale if data changes between checking and writing. For consistency requirements, the shell/repository still needs transactions or appropriate race-prevention mechanisms. Having small functions helps identify where to place that guarantee; it does not replace it.

## 14. Immutability and Avoiding Mutated Input Parameters

A small function can return a clear result and still run into trouble if **its input is modified elsewhere**.

~~~java
record Report(List<StringBuilder> names) {}
~~~

The record above only holds references to the list and the mutable `StringBuilder`s. Using `List.copyOf(names)` in the constructor protects **the list structure**, but does not deep-copy each `StringBuilder`. If you want a snapshot of the result, convert elements to `String` before copying.

Example:

~~~java
List<String> names = mutableNames.stream()
        .map(StringBuilder::toString)
        .toList();
~~~

This illustrative snippet assumes `mutableNames` has type `List<StringBuilder>`. The output strings have immutable state at the moment of conversion. When the input can be modified by another thread **during the snapshot**, appropriate synchronization is needed for consistency; `toList()` is not a transactional snapshot.

**Functions with clear inputs/outputs** do not mean data must always be immutable, but there should be a clear policy: may the function mutate input? Does the output share references with the input? May the caller mutate the output?

## 15. Small Functions and Concurrent Execution

An often-cited benefit of pure functions is ease of parallel execution. However, merely “splitting into many small functions” does not automatically make code thread-safe.

For parallel Streams:

- Mappers/predicates should be **stateless, non-interfering**, and not modify the source collection.
- If a function reads a mutable cache or configuration, it still depends on external state.
- Writing to an `ArrayList` or incrementing a shared `int` counter inside callbacks can cause race conditions.
- `reduce` operations require an associative accumulator, a proper identity, and a compatible combiner.
- Money/sum calculations also need to consider overflow, floating-point precision, and rounding order.

Example of what not to do:

~~~java
// WARNING: accumulating into an external list in a parallel stream.
List<String> output = new ArrayList<>();
input.parallelStream().map(x -> {
    output.add(transform(x));
    return x;
}).count();
~~~

Beyond race risks, a terminal operation like `count()` on a sized source can **skip calling the mapper** when the implementation can prove the result without traversing. Therefore, do not rely on side effects in intermediate operations as mandatory logic.

A better approach when you actually need to build a list:

~~~java
List<String> output = input.parallelStream()
        .map(MyService::transform)
        .toList();
~~~

This illustrative snippet requires `MyService.transform` to be a type-compatible, stateless, and thread-safe function. The Stream collector handles building the list according to contract, without needing an `ArrayList` outside the pipeline for workers to update concurrently.

## 16. Refactoring from a Long Method to Small Functions Step by Step

A safe way to transition:

**Step 1 — Document existing behavior.** Identify inputs, outputs, business rules, I/O, exceptions, and existing tests. Do not rush to change algorithms.

**Step 2 — Identify named computations.** For example `subtotal`, `discount`, `shipping`. Check which rules depend on values from other rules.

**Step 3 — Design data types.** Use `Order`, `Line`, `Quote`, or domain-appropriate DTOs instead of passing loose parameter lists.

**Step 4 — Extract pure functions first.** Move I/O-free calculations and validations into methods with explicit inputs and deterministic outputs. Write tests for boundary values.

**Step 5 — Create an orchestrator.** A `quote()` or `decide()` method calls sub-functions in logical order and returns the final result. You do not need `Function.andThen` everywhere; direct method calls can be easier to read.

**Step 6 — Isolate effects.** Move DB/log/event-emitting operations to a service/shell step with transaction and error contracts. If side effects currently sit inside a mapper, confirm business requirements before moving them to avoid accidentally changing execution order.

**Step 7 — Regression testing.** Compare outputs against the old implementation across normal, boundary, invalid, empty, and overflow cases. For I/O parts, test interactions and failure scenarios separately.

**Step 8 — Review complexity.** If splitting created too many one-line helpers, unnecessary dependency injection, or hidden state variables, merge them back along responsibility boundaries.

This process can be applied incrementally without rewriting the entire application. Each refactoring step should preserve business behavior or only change behaviors that have been requested and tested.

## 17. Common Mistakes When “Splitting” Business Logic

| Mistake | Consequence | Improvement |
|---|---|---|
| Function takes too many primitives | Easy to pass arguments in wrong order or meaning | Use domain-appropriate records/value objects |
| Function named `process` or `handle` with unclear output | Readers must open implementation to know its purpose | Name them `normalizeEmail`, `calculateShipping`, `validateOrder` |
| Ignoring null/empty cases | Callers have to guess what the function returns | Define preconditions, Optional, or error results |
| Computing and writing to DB inside a mapper | Hard to test, retry, and preview | Separate computation core and I/O shell |
| Every helper reads mutable static config | Hidden dependencies, flaky tests | Pass config/snapshot via explicit input |
| A function returns a shared mutable object | Callers interfere with each other | Defensive copy or immutable output |
| A function has too many boolean flags | Hard-to-follow branching | Enum/strategy/named request types |
| Over-splitting without responsibility boundaries | Code jumps across many places, hard to read | Group steps belonging to the same concept |
| Using Stream for every operation | Complex flow, easy to hide side effects | Use loops/orchestrator when clearer |
| Forgetting reduce identity/associativity rules | Parallel results are unreliable | Check reduce contract or use collectors |
| Abusing unchecked exceptions for all user errors | Hard to return structured validation messages | Choose an explicit error result type |
| Assuming purity is automatic just by using lambdas | Side effects and state still exist | Inspect implementation and dependencies |
| Not testing limits/constraints | Bugs at thresholds, empty inputs, overflow | Test branches and boundary values |
| Splitting functions while still mutating inputs | Side effects remain | Create new values or make update commands explicit |

## 18. Functional Design Review Checklist

1. Can each step be described in **one concrete business sentence**?
2. Does the function name clearly state **the action or calculation**?
3. Are the inputs sufficient and of the right type, unit, and meaning?
4. Does the function return a meaningful output, or does it mutate external variables to “return results”?
5. Are validation, null, empty, overflow, rounding, and exceptions addressed?
6. Do callbacks mutate inputs, external state, or the Stream source?
7. Does the result share mutable references with inputs/callers?
8. Can the function be unit tested with inputs/outputs without starting a database or web server?
9. Which rules change independently and have boundary test cases?
10. Does the function read time, random, configuration, or environment? If so, are dependencies explicit?
11. Are side-effecting operations separated from transformations?
12. Is there an orchestrator showing the order in which data flows through steps?
13. Are overly tiny functions making the flow harder to follow?
14. Is Stream actually needed, or is a direct loop/statement clearer?
15. If run in parallel, are callbacks stateless/non-interfering and reducing results per contract?

Passing the checklist does not mean a system will never have bugs. It helps make critical assumptions **visible directly in the API structure**, so tests, code reviews, and rule changes cause fewer unintended side effects.

## 19. Self-Check Exercises

**Question 1.** What is the problem with a method taking `(int a, int b, int c, int d)` to calculate prices without clear data types or naming?

**Question 2.** Why does `map(p -> { p.setPrice(...); return p; })` not represent a “side-effect-free transformation”?

**Question 3.** In the quote calculation example, why is `shipping(int afterDiscount)` easier to test than when it is buried inside a long `checkout()`?

**Question 4.** Is a function that does not modify its inputs, yet writes logs and reads the clock, guaranteed to be pure?

**Question 5.** How should `normalize` and `validate` differ in responsibility?

**Question 6.** Why might `List.copyOf` not be enough to guarantee deep immutability if elements are mutable entities?

**Question 7.** When is `Function.andThen` used? Is it mandatory to use it to call two functions in sequence?

**Question 8.** Why should you not use `peek`/`map` to guarantee every element is audit-logged in a Stream?

**Question 9.** In the `FunctionalCoreShellDemo` example, what is the functional core and what is the imperative shell?

**Question 10.** When should you **not** extract a short expression into a new function?

**Short Answers:**

1. Parameters lack semantics and are easily passed in the wrong position; use clear names/records/value objects.
2. Because it mutates the input object itself and can affect other references.
3. The function has one input and one result with a clear threshold; it is easy to test `99` and `100` without preparing I/O dependencies.
4. No; side effects and external dependencies are still present.
5. `normalize` converts representation; `validate` evaluates conditions and returns error information.
6. Because copying the list structure does not clone each child object.
7. When you want to chain type-compatible `Function`s; calling regular methods is still completely valid.
8. Short-circuiting and optimizations may skip callbacks; side effects are not guaranteed to run for every element.
9. `calculate(Request)` is the core; `store.save(...)` and the persistence lifecycle belong to the shell.
10. When it does not create a distinct business concept, forces readers to jump across multiple places, or hides dependencies.

## 20. Official References

- [Java SE 17 — java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html): standard functional interfaces and their intended uses.
- [Java SE 17 — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): `apply`, `compose`, and `andThen`.
- [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `map`, `reduce`, `toList`, pipeline characteristics, and callback requirements.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): non-interference, statelessness, and side-effect notes.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): creating an unmodifiable structural snapshot list.
- [Java SE 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html): record syntax and data with explicit components.

**Key Takeaway:** Good functional design is not about the number of lambdas or helpers, but about **named business steps with clear inputs/outputs and well-defined conditions and errors**. Use small functions to separate **normalization – validation – calculation – decision**; coordinate them in a readable orchestrator; and move **persistence/I/O/side effects** to appropriate boundaries. This design makes code easier to test, easier to extend, and safer against state mutations.
