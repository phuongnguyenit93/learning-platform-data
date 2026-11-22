# Using Immutable Objects to Pass Results Between Steps in Java

## 1. Why Does Functional Design Need Immutable Objects?

In a data processing pipeline, the output of an earlier step often becomes the input of the next step. For example, an order may need to go through **receive data → validate → calculate price → apply discount → issue receipt**. You could organize all steps to mutate a shared state object:

~~~java
// Sketch of a design that can be hard to follow:
void calculate(OrderState state) {
    state.total = state.price * state.quantity;
}
void discount(OrderState state) {
    state.total -= 500;
}
~~~

This is **non-standalone illustrative code**: `OrderState` is a hypothetical class with mutable fields. The problem is not that every mutation is wrong, but that steps share a reference and **mutate the same object**. A call elsewhere might observe half-updated data; re-running a step might apply a fee twice; calling steps in the wrong order might produce a different result while making it very hard to tell which step mutated the state.

A functional approach is **each step takes a value with stable state and returns a new value**:

~~~text
Input immutable
      |
      v
validate   : Input -> ValidatedInput
      |
      v
calculate  : ValidatedInput -> PricedInput
      |
      v
discount   : PricedInput -> Receipt
      |
      v
Receipt immutable
~~~

Intermediate values are objects representing *the result at a processing milestone*. There is no need to mutate the previous step's object to produce new information. With this model, the program is easier to test, easier to observe, well-suited for composition, and less prone to race conditions when data is shared for reading across tasks.

**Lesson goals:**

1. Understand what immutability is and why it fits functional pipelines.
2. Distinguish **non-reassigned references**, **shallowly immutable objects**, **structural snapshots**, and **deep immutability**.
3. Use Java 17 `record`s, constructor validation, `List.copyOf`, and defensive copies to create safe handoff data.
4. Write steps that return new results without mutating inputs; compose them with `Function.andThen` or clearly named methods.
5. Distinguish immutability from pure functions; handle clock, I/O, database, exceptions, configuration, and concurrency at appropriate boundaries.
6. Avoid aliasing, “getters leaking a mutable List”, misusing `Collections.unmodifiableList`, and excessive copying.
7. Run a standalone Java 17 program with original/updated states, calculate money using `long`, and verify validation.
8. Practice designing pipelines with explicit data and stage transitions.

## 2. What Exactly Does “Immutable Object” Mean?

### 2.1. Immutability from the API Perspective

An **immutable object** is an object whose observable state does not change after creation within the contract of that type. Instead of mutating the object, the program creates a new value containing the differences.

Example with `String`:

~~~java
String original = "java";
String upper = original.toUpperCase();

System.out.println(original); // java
System.out.println(upper);    // JAVA
~~~

`toUpperCase()` returns a `String` instead of mutating `original`. This is a simple way to picture “new result, old data remains usable”.

With domain objects:

~~~java
record Point(int x, int y) {
    Point translated(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

This is a standalone record with two primitive components. Calling `new Point(2,3).translated(1,2)` returns a `Point(3,5)`; the original object remains `Point(2,3)`. `translated` can be called a “with-style method”: a method that creates a value with the desired change.

### 2.2. `final` on a Variable Does Not Make the Object Immutable

~~~java
final List<String> names = new ArrayList<>();
names.add("An"); // Still valid.
~~~

Here `final` prevents **reassigning the reference** of the variable `names`. It does not forbid calling `add` on the `ArrayList` object. Therefore, you must not infer that a “final variable” means an “immutable collection”.

Similarly, a lambda capturing an effectively final local variable can hold a reference to a mutable object; other threads or code can still mutate that object. To share results safely, you must examine **the entire observable data graph**, not just the variable's modifier.

### 2.3. `record` Is Not Automatically Deeply Immutable

Java records are concise for representing data, and components become private final fields with accessors. However, if a component has a mutable type, the stored value is **a reference to that object**.

~~~java
record Team(List<String> names) {}

List<String> original = new ArrayList<>(List.of("An"));
Team team = new Team(original);
original.add("Binh");

System.out.println(team.names()); // [An, Binh]
~~~

This is a snippet inside a method importing `List` and `ArrayList`. Record `Team` has no setters, yet the state observable via `names()` changed! This is **aliasing**: the caller's object and the record point to the same mutable List.

Important lesson: **a record is a great tool for building value carriers, but it does not replace checking and copying mutable components**.

### 2.4. Shallow vs. Deep Immutability

| Concept | Typical Guarantee | Not Automatically Guaranteed |
| --- | --- | --- |
| `final` reference | That local/field reference cannot be reassigned | That the referenced object is immutable |
| Record with primitives and `String` | Final field references, suitable basic elements | If mutable objects are added, must re-evaluate |
| `Collections.unmodifiableList(backing)` | Cannot mutate List through the wrapper | Backing List can still be mutated elsewhere |
| `List.copyOf(backing)` | Unmodifiable structural snapshot with non-null elements | Deep-copying each mutable element |
| Deeply immutable model | Observable state does not change across related components | Does not exempt validation or error handling |

“Deeply immutable” is not a magic keyword built into Java; it is a **design contract** depending on field types and whether references can escape. For elements containing `StringBuilder`, `Date`, `byte[]`, or mutable Lists/Maps, you must decide how to create immutable copies, how to return data, and whether deep copying is needed.

## 3. Principles for Designing Immutable Results Between Steps

### 3.1. A Step Takes Input and Returns a New Result

A transformation function follows the model:

~~~java
Function<Input, Output> stage = input -> new Output(...);
~~~

This is a general syntax: `Input` and `Output` represent actual domain types. A good step should have clear inputs, not mutate the caller's objects, and return a result sufficient for the next step. Having type `Function` does not guarantee immutability; you must inspect **the lambda body** and object types.

### 3.2. Each Transition State Has Domain Meaning

Instead of one class with ten flags like `isValidated`, `hasPricing`, `isApproved` and many fields that are sometimes empty, you can use distinct types:

~~~text
Basket
  -> PricedBasket
  -> Receipt
~~~

`Basket` contains validated items. `PricedBasket` contains items and subtotal. `Receipt` contains subtotal, discount, and total. The pricing step does not return a “secretly mutated Basket”, but rather **a new type representing the new state**.

This design helps the compiler prevent out-of-order calls: a function accepting `PricedBasket` cannot be called directly with `Basket` without going through the pricing step.

### 3.3. Validate Right at the Object Creation Boundary

If a record expresses “quantity must be positive”, verify it in the constructor. Otherwise, a stage may receive an object whose invariants are already broken and either fail late or silently produce meaningless values.

~~~java
record Item(String name, int quantity) {
    Item {
        Objects.requireNonNull(name);
        if (name.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid item");
        }
    }
}
~~~

This is an illustrative record requiring `import java.util.Objects`. A record's compact constructor lets you validate or normalize components before fields are initialized. Afterward, any `Item` validly constructed through this constructor can be trusted regarding those checked conditions.

### 3.4. Copy Mutable Data When Crossing Boundaries

A record receiving a `List<Item>` from a caller should avoid holding a reference to an external mutable List:

~~~java
record Basket(List<Item> items) {
    Basket {
        items = List.copyOf(items);
    }
}
~~~

`List.copyOf` returns an unmodifiable List, copying the structural contents at the time of the call for mutable sources like `ArrayList`. It rejects a null List and null elements. Note that it **does not deep-copy `Item`**. That is why the `Item` model in the complete example is designed with only `String` and primitives, with no mutable components.

In a compact constructor, reassigning **the parameter `items`** is valid; Java then assigns the normalized value to the corresponding record field. This is how to block List aliasing without writing a verbose canonical constructor.

## 4. Defensive Copying: On the Way In and On the Way Out

### 4.1. Copying on Input Is Important

~~~java
List<String> incoming = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(incoming);

incoming.add("B");

System.out.println(snapshot); // [A]
~~~

Here, `snapshot` does not reflect element `B` added to the original List after copying. As a result, downstream stages see a stable dataset. However, if another thread is mutating `incoming` **at the exact moment of copying**, calling `List.copyOf` alone is not a synchronization solution for a consistent snapshot. Ownership and synchronization must be managed at the data-fetching boundary.

### 4.2. An Unmodifiable View Is Not a Snapshot

~~~java
List<String> incoming = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(incoming);

incoming.add("B");

System.out.println(view); // [A, B]
~~~

The wrapper only blocks modifications **through `view`**. It does not stop the caller from holding `incoming` and mutating it externally. For data passed between steps that require a snapshot, a view is insufficient if the backing source can still change.

### 4.3. Record Accessors Are Not the Only Thing to Check

With `record Basket(List<Item> items)` copied via `List.copyOf`, the `items()` accessor returns an unmodifiable List, so callers cannot `add`/`remove`/`set` via the List. But if `Item` is a mutable object, callers can still mutate an `Item`'s contents and stages will observe the change. Therefore, you must inspect **every component containing mutable objects**, not only protect the outer List.

For arrays, copy both on input and on output if the contract requires it:

~~~java
final class Bytes {
    private final byte[] data;

    Bytes(byte[] source) {
        this.data = source.clone();
    }

    byte[] copyData() {
        return data.clone();
    }
}
~~~

This class illustrates defensive copying in **both the constructor and the getter**. If the getter returned `data` directly, callers could mutate the internal array. Arrays cannot become unmodifiable merely by marking the field `final`.

### 4.4. Snapshot Does Not Mean Every Object Must Have a Different Identity

`List.copyOf` may return the same object if the input is already a suitable unmodifiable List. Do not write tests asserting `copy != original` as a condition for immutability; instead, test **the contract that it cannot be mutated and does not reflect structural changes from a mutable source** when appropriate.

## 5. Designing a Strongly Typed Pipeline with `record`

A unified example:

~~~java
record Item(String name, int quantity, long unitPriceCents) {}
record Basket(List<Item> items) {}
record PricedBasket(List<Item> items, long subtotalCents) {}
record Receipt(
        List<Item> items,
        long subtotalCents,
        long discountCents,
        long totalCents) {}
~~~

This is an initial sketch for the domain structure, **not yet including full validation/copying**. In the standalone runnable section, constructor validation and defensive copies will be added. Purpose of each type:

| Type | Meaning | Key Fields |
| --- | --- | --- |
| `Item` | Validated line item | name, quantity, unit price |
| `Basket` | Cart used as input | List of items |
| `PricedBasket` | Result of pricing step | List of items, subtotal before discount |
| `Receipt` | Result of finalization step | List of items, original subtotal, discount, payable total |

We choose **cents as `long`** in the example to avoid teaching the habit of using `double` for money. However, this is still a pedagogical example, without currency, taxes, rounding rules, compound discounts, or full financial business guarantees.

### 5.1. Creating a New Object with a With-Style Method

Instead of `basket.items().add(item)`, create a new `Basket`:

~~~java
Basket withAdded(Item item) {
    List<Item> updated = new ArrayList<>(items);
    updated.add(Objects.requireNonNull(item));
    return new Basket(updated);
}
~~~

This is a **method that must be placed inside record `Basket`** having component `items` and compact constructor `List.copyOf(items)`. The old `items` data does not change. A new list is created within the method scope, and then the constructor normalizes it into an unmodifiable snapshot.

For large collections, copying the entire List on every addition can be expensive; the performance section below explains how to choose when to copy and when to use other data structures.

### 5.2. Consistent Error Representation

Immutability does not mean no exceptions. A constructor can throw `IllegalArgumentException` if quantity is invalid, or `Math.multiplyExact` can throw `ArithmeticException` if multiplication overflows. This is a way to **detect and report errors** rather than allowing an object in an invalid state to be constructed.

If the application needs to collect validation errors rather than fail-fast, you can design a `ValidationResult<T>` type or a sealed interface between `Success` and `Failure`. Then errors become immutable data, passed through the pipeline just like normal results. Not every error has to become an exception.

## 6. Processing Steps Are Typed Transformations

### 6.1. Calculating Subtotal

The first step can have the type:

~~~java
Function<Basket, PricedBasket> price = basket -> {
    long subtotal = basket.items().stream()
            .mapToLong(Item::lineTotalCents)
            .reduce(0L, Math::addExact);
    return new PricedBasket(basket.items(), subtotal);
};
~~~

Here `Item::lineTotalCents` must be a method on record `Item` computing a `long`. `Math.addExact` makes explicit the policy of **never silently allowing overflow**. `0L` is the identity for addition, and summing `long`s within valid range produces the expected result.

**There is no statement mutating `Basket`**. The lambda receives `Basket`, reads items, calculates `subtotal`, and creates a new `PricedBasket`. This makes data flow easy to trace: `subtotal` is tied to the exact set of items at the time the object was created.

### 6.2. Finalizing Discount

~~~java
Function<PricedBasket, Receipt> discount = priced -> {
    long amount = Math.min(priced.subtotalCents(), 500L);
    long total = Math.subtractExact(
            priced.subtotalCents(), amount);
    return new Receipt(
            priced.items(),
            priced.subtotalCents(),
            amount,
            total);
};
~~~

This is a code fragment inside a class with the records and `Function` imported. The “max discount of 500 cents” rule is just for illustration; each time it computes from `PricedBasket`, the discount step does not mutate the `PricedBasket` object itself. If you want to keep historical values for auditing, you can store the result objects without worrying that a later stage will mutate their Lists through standard APIs.

### 6.3. Composing Steps with `Function.andThen`

~~~java
Function<Basket, PricedBasket> price = ...;
Function<PricedBasket, Receipt> discount = ...;

Function<Basket, Receipt> pipeline =
        price.andThen(discount);

Receipt receipt = pipeline.apply(basket);
~~~

This is a **typing outline**, where `...` stands for the implementations from the previous two sections. `price.andThen(discount)` requires the output of `price` to be compatible with the input of `discount`. The compiler helps catch mismatched stages. In practice, you can declare stages as regular methods and use method references `MyClass::price` to avoid storing unnecessary state.

`Function.andThen` does not by itself guarantee immutable results. If `price` returns the same mutated object, the pipeline still has side effects. **Immutability is a property of the model and how stages are written**, not merely of using composition APIs.

## 7. Complete Java 17 Program

The example creates a `Basket` from an input `ArrayList`; then mutates the `ArrayList` afterward to prove the snapshot does not change. Next, a pipeline calculates price and then discount to produce a `Receipt`. We also create a new `Basket` using a with-style method, verify the original `Basket` remains unchanged, and test a blocked mutation attempt.

Create file **`ImmutablePipelineDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class ImmutablePipelineDemo {

    record Item(String name, int quantity, long unitPriceCents) {
        Item {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid item");
            }
        }

        long lineTotalCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    record Basket(List<Item> items) {
        Basket {
            items = List.copyOf(items);
        }

        Basket withAdded(Item item) {
            List<Item> updated = new ArrayList<>(items);
            updated.add(Objects.requireNonNull(item));
            return new Basket(updated);
        }
    }

    record PricedBasket(List<Item> items, long subtotalCents) {
        PricedBasket {
            items = List.copyOf(items);
        }
    }

    record Receipt(
            List<Item> items,
            long subtotalCents,
            long discountCents,
            long totalCents) {
        Receipt {
            items = List.copyOf(items);
        }
    }

    static final Function<Basket, PricedBasket> PRICE = basket -> {
        long subtotal = basket.items().stream()
                .mapToLong(Item::lineTotalCents)
                .reduce(0L, Math::addExact);

        return new PricedBasket(basket.items(), subtotal);
    };

    static final Function<PricedBasket, Receipt> DISCOUNT = priced -> {
        long discount = Math.min(priced.subtotalCents(), 500L);
        long total = Math.subtractExact(
                priced.subtotalCents(), discount);

        return new Receipt(
                priced.items(),
                priced.subtotalCents(),
                discount,
                total);
    };

    public static void main(String[] args) {
        List<Item> incoming = new ArrayList<>(List.of(
                new Item("Book", 2, 1200L),
                new Item("Pen", 1, 300L)
        ));

        Basket original = new Basket(incoming);

        // Mutate the input List after creating Basket.
        incoming.add(new Item("External", 1, 999L));

        Function<Basket, Receipt> pipeline =
                PRICE.andThen(DISCOUNT);

        Receipt receipt = pipeline.apply(original);

        Basket updated = original.withAdded(
                new Item("Notebook", 1, 4000L));

        Receipt updatedReceipt = pipeline.apply(updated);

        System.out.println(
                "originalItems=" + original.items().stream()
                        .map(Item::name)
                        .toList());

        System.out.println(
                "receipt=" + receipt.subtotalCents()
                        + "/" + receipt.discountCents()
                        + "/" + receipt.totalCents());

        System.out.println(
                "updatedItems=" + updated.items().stream()
                        .map(Item::name)
                        .toList());

        System.out.println(
                "updatedTotal=" + updatedReceipt.totalCents());

        System.out.println(
                "originalStill=" + original.items().size());

        try {
            original.items().add(
                    new Item("CannotAdd", 1, 1L));
        } catch (UnsupportedOperationException ex) {
            System.out.println("listMutation=blocked");
        }

        try {
            new Item("Invalid", 0, 100L);
        } catch (IllegalArgumentException ex) {
            System.out.println("validation=rejected");
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac -encoding UTF-8 ImmutablePipelineDemo.java
java ImmutablePipelineDemo
~~~

**Exact stdout:**

~~~text
originalItems=[Book, Pen]
receipt=2700/500/2200
updatedItems=[Book, Pen, Notebook]
updatedTotal=6200
originalStill=2
listMutation=blocked
validation=rejected
~~~

### 7.1. Why Does Mutating `incoming` Not Change `original`?

`Basket` uses `List.copyOf(items)` on construction. Therefore `incoming.add(new Item("External",...))` only modifies the caller's `ArrayList`, not causing `Basket` to gain an extra item. `originalItems` only contains Book and Pen.

### 7.2. How Does the Original Pricing Work?

- Book: `2 * 1200 = 2400` cents.
- Pen: `1 * 300 = 300` cents.
- Subtotal: `2400 + 300 = 2700` cents.
- Discount per illustrative policy: `min(2700,500)=500` cents.
- Total: `2700 - 500 = 2200` cents.

No step mutates a subtotal field on `Basket`; `PricedBasket` and `Receipt` are **new values** with the corresponding components.

### 7.3. Why Does the New Basket Have Three Items While the Original Still Has Two?

`withAdded` creates a new `ArrayList` from the old `items`, adds Notebook, and builds a new `Basket`. `updated` has Book, Pen, Notebook; `original` still only has Book and Pen. The new subtotal is `2700 + 4000 = 6700` cents; subtracting `500` yields `updatedTotal=6200`.

This helps preserve past values for testing, comparison, and debugging, while preventing a stage from mutating the previous stage's result.

### 7.4. Why `listMutation=blocked`?

The `original.items()` accessor returns the unmodifiable List stored after `List.copyOf`. `add` is unsupported and throws `UnsupportedOperationException`. This protects **the List structure**, not a magical guarantee that every element object is immutable; for example, `Item` in this lesson has `String` and primitive fields so its fields themselves do not allow mutating state through the record's API.

### 7.5. Why `validation=rejected`?

`Item` requires `quantity > 0`. When creating `new Item("Invalid",0,100L)`, the compact constructor throws `IllegalArgumentException`. Thanks to validation at value-object creation time, the pipeline does not have to guess whether an `Item` is valid at every step. This is an intentional form of **fail fast**.

## 8. Immutability and Pure Functions: Related but Different

### 8.1. What Is a Pure Function?

A pure function (pure function) typically has two characteristics:

1. Same input value → same output value according to the observable semantics.
2. Produces no observable side effects beyond the return value.

For example, `price(Basket)` with fixed data and policy can closely fit this model: reading an immutable `Basket`, computing subtotal, and returning a new `PricedBasket`. If inputs are valid, there is no overflow, and there is no I/O, the result is stable.

### 8.2. Using Immutable Objects Does Not Automatically Make a Stage Pure

~~~java
Function<Basket, Receipt> stage = basket -> {
    auditService.sendEvent("pricing");
    return calculateReceipt(basket);
};
~~~

This is **non-standalone illustrative code**, with hypothetical `auditService` and `calculateReceipt`. Even though `Basket` and `Receipt` are immutable, the call to send an event is a side effect. The function is no longer pure in the sense above. Switching to records does not eliminate database, clock, random, or HTTP interactions.

The practical approach is **keeping side effects at clear boundaries**: read data into models, perform most transformations purely, then write/save/publish results through a separate adapter.

### 8.3. Clock, Random, and Configuration Should Be Explicit Inputs

If a stage reads `Instant.now()` internally, the same `Basket` across two calls can produce different timestamps. If the domain needs time, you can pass the timestamp into an immutable request or inject `Clock` in an appropriate API:

~~~java
record PricingRequest(Basket basket, Instant requestedAt) {}

PricingRequest request = new PricingRequest(
        basket, clock.instant());
~~~

This is an **illustrative code fragment** with existing `basket`/`clock` variables, importing `java.time.Instant` and `Clock`. Once the request holds the timestamp, internal computation steps can use the same value, avoiding multiple clock reads that cause discrepancies.

Similarly, tax config, discount rates, or locale should be represented by a stable value object for a single processing run; if a stage reads a mutable singleton on every call, the resulting data can depend on timing.

## 9. Benefits of Immutable Results in Workflows

### 9.1. Easier to Understand Order and Responsibility

Instead of one object being mutated across many methods, each result expresses meaning at one stage. When an error occurs in the discount step, you can inspect `PricedBasket` without worrying that the later step mutated the initial subtotal.

### 9.2. Easier to Unit Test Each Step Individually

~~~java
Basket basket = new Basket(List.of(
        new Item("Book", 2, 1200L)));

PricedBasket result = PRICE.apply(basket);

assert result.subtotalCents() == 2400L;
assert basket.items().size() == 1;
~~~

This is a code fragment in the context of the demo class; Java's `assert` keyword is disabled by default unless run with `-ea`. In a project test suite, use explicit JUnit assertions. Do not only check subtotal; also check **that the input was not mutated**.

### 9.3. Favorable for Caching When Appropriate

If value objects have stable equality semantics and stages are pure, you can build caches keyed by immutable values. Records provide component-based `equals`/`hashCode`, which is convenient in many cases. However, a record containing a mutable List or mutable object can still change key semantics and break the cache.

**Immutability does not automatically create memoization.** Without a designed cache, every call to `PRICE.apply(basket)` still runs the computation. Lifecycle, memory, keys, invalidation, and concurrency must be considered separately.

### 9.4. Reduced Need for Locking When Read-Only

If multiple threads read a truly immutable object, there is no need to coordinate mutations on that object. This is a major benefit of immutable results for concurrency or parallel pipelines.

However, **immutability does not mean the entire workflow is thread-safe**: database writes, logging, internal mutable objects, or unsafe memory publication at boundaries still need review. Make sure objects are created and handed off to other threads through proper publication mechanisms; with properly constructed final fields and not letting `this` escape during construction, Java provides specific guarantees on final-field semantics.

## 10. Applying in Streams: Transform Instead of Mutate

### 10.1. Pipeline Transforming into New Results

~~~java
List<Item> adjusted = items.stream()
        .map(item -> new Item(
                item.name(),
                item.quantity(),
                Math.addExact(item.unitPriceCents(), 100L)))
        .toList();
~~~

This is a code fragment with `items` of type `List<Item>` and the `Item` record from this lesson. Each element is **replaced by a new `Item`** with a price increased by 100 cents, instead of mutating the original `Item`. `Stream.toList()` returns an unmodifiable List on Java 17.

Note: increasing prices can overflow or violate business policies; `Math.addExact` reports an error instead of silently wrapping. The transformation in the example uses immutable objects and does not modify the source List.

### 10.2. Do Not Mutate the Source in `map` or `peek`

Anti-pattern:

~~~java
items.stream()
        .map(item -> {
            item.setPrice(...);
            return item;
        });
~~~

This is **non-standalone anti-pattern code**: `Item` in the example is a record so it has no `setPrice`. On real mutable objects, mutating elements while traversing can cause other pipelines sharing those objects to observe changing state. Especially with parallel Streams, callbacks mutating shared objects can cause race conditions.

To pass data from an earlier step to a later step, return new objects from `map`. If the business logic genuinely requires mutation, manage it at a clear boundary and do not assume Stream handles synchronization automatically.

### 10.3. `Collectors.toList()` Does Not Promise Immutability

~~~java
List<Item> collected = items.stream()
        .collect(Collectors.toList());
~~~

According to Javadoc, `Collectors.toList()` **makes no guarantees on implementation type, mutability, serializability, or thread safety**. If a later step needs an unmodifiable structural snapshot, use `Stream.toList()` on Java 17, `Collectors.toUnmodifiableList()` when nulls are not accepted, or `List.copyOf` at the appropriate boundary.

`Stream.toList()` can contain `null`, whereas `List.copyOf` and `Collectors.toUnmodifiableList()` reject `null`. Do not swap APIs just because their names look similar; determine requirements for nulls and List type.

## 11. Managing State Updates: Withers and Versioned Values

### 11.1. A Wither Creates a New Copy Instead of a Setter

Example:

~~~java
record UserProfile(String name, String city) {
    UserProfile withCity(String nextCity) {
        return new UserProfile(name, nextCity);
    }
}
~~~

In this case, `withCity` creates another `UserProfile` while the original object stays intact. If a field is a List, Map, array, or mutable object, you still must copy/validate accordingly. The name “withCity” only describes intent; the compiler does not check whether the method is pure.

### 11.2. Turning State into Versioned Values

When updating a multi-step workflow, you can use:

~~~java
record Versioned<T>(long version, T value) {}
~~~

This is an illustrative data type carrying a version and payload. A new version can be represented by `new Versioned<>(old.version()+1, nextValue)` instead of mutating the same holder. However, **a generic record does not force `T` to be immutable**. If `T` is a mutable `ArrayList`, the version does not protect the data by itself.

In systems with a database, versions can support optimistic concurrency control when checked/written within an appropriate transaction; merely incrementing a number in a Java object does not prevent races across multiple requests or processes.

### 11.3. Avoiding “Half-Valid” Intermediate Objects

When each stage uses its own type, a `PricedBasket` does not need an unassigned `paidAt` field, and `Receipt` does not need a `pricingDone` flag. This expresses valid states through types rather than one object with many nullable fields.

However, not every workflow needs a new record for every tiny statement. Choose stage types along **meaningful business boundaries**, avoiding overengineering with dozens of classes differing by a single field.

## 12. Validation, Exceptions, and Error Data

### 12.1. Immutability Needs Correct Invariants from Initialization

If `Receipt` records total, subtotal, and discount, those values must be consistent. In the complete example, the pipeline computes `total` via `Math.subtractExact`, but record `Receipt` only performs defensive copying and has not yet checked all financial relationships. In a real system, the constructor or factory should check:

- `subtotalCents >= 0` and `discountCents >= 0`.
- Discount does not exceed subtotal, unless the domain has another credit policy.
- `totalCents` matches the exact calculation and rounding rules.
- Currency and scale, taxes/fees, access permissions, and input validation.
- Which data source the order line items reconcile against the subtotal with.

Using a record does not prove any of those invariants by itself. DTO design should focus on domain correctness, not just concise syntax.

### 12.2. An Immutable Way to Represent Errors

In APIs that need to collect multiple errors, you can use a sealed type:

~~~java
sealed interface Outcome<T>
        permits Success, Failure {}

record Success<T>(T value) implements Outcome<T> {}

record Failure<T>(String message)
        implements Outcome<T> {}
~~~

This is an illustrative Java 17 snippet; `message` should be validated if the domain requires it. `Success<T>` **does not guarantee `T` is immutable**; the payload must be chosen or snapshotted per contract. A stage can return `Outcome<Receipt>`: the caller handles success or failure without mutating a multi-flag `ProcessState` object.

### 12.3. Not Every Error Should Be Turned into Data

For bugs, invariant violations, or resource failures, exceptions still have a role. The goal is to keep **each step's contract clear**. If you choose exceptions, do not swallow `IOException` or computation errors and return a fake zero-valued `Receipt` as if it succeeded.

Both exceptions and an `Outcome` type are compatible with immutable results, as long as side effects and state are handled consistently.

## 13. Concurrency, Sharing, and Parallel Streams

### 13.1. Value Objects Help Share Read-Only Data

A truly immutable `Basket` can serve as a source for multiple read-only computations without needing to synchronize mutations on the `Basket` itself. With a parallel pipeline:

~~~java
long subtotal = basket.items().parallelStream()
        .mapToLong(Item::lineTotalCents)
        .reduce(0L, Math::addExact);
~~~

Because the `Item`s in the example are immutable, the callback does not mutate the source, and integer addition has identity `0L`, the pipeline expresses a valid reduction when calculations do not overflow. `Math.addExact` can throw if a partial sum exceeds the limit, so the design needs a policy for the data range and cost, rather than assuming “parallel is always more accurate”.

### 13.2. Immutability and Stateless Lambdas Are Two Different Requirements

Even when the input is immutable, a callback can still cause side effects:

~~~java
AtomicInteger counter = new AtomicInteger();

basket.items().parallelStream()
        .map(item -> {
            counter.incrementAndGet();
            return item;
        });
~~~

This is an anti-pattern snippet (and has no terminal operation): using a shared `AtomicInteger` makes the callback stateful; atomic increments do not change the fact that it has a side effect. With Stream optimizations, some intermediate operations might not be invoked if the result does not require them. Do not use side effects inside `map` as a business counter.

If you need the item count, `basket.items().size()` or `stream().count()` is clearer. If you need the total quantity, use `mapToInt(Item::quantity).sum()` and control overflow.

### 13.3. Do Not Assume External Collections Are Thread-Safe by Default

`List.copyOf` returns a structurally unmodifiable List, but only enables safe sharing if elements/sources were constructed stably and used per contract. Connecting to a database, making HTTP calls, writing logs, updating caches, or mutating other internal objects may still require synchronization, transactions, or idempotency.

### 13.4. Use Parallel Execution Only When Beneficial

For a `Basket` with a few `Item`s and simple multiplication/addition, `parallelStream()` usually adds overhead. Write a sequential pipeline first, test correctness, and measure real workloads; only choose parallel execution when data is large enough, computation functions are independent, and the benefit is measurable.

## 14. Costs and Limits of Immutable Design

### 14.1. Copying Lists Has a Cost

`List.copyOf` and creating a new List in `withAdded` can take O(n) time when copying the structure of `n` elements. If every single-element change creates a copy of a list with millions of entries, CPU/memory cost can be high.

This does not make the technique wrong, but requires sensible choices:

- For small DTOs and infrequent updates, defensive copying is usually simple and easy to prove correct.
- For batch updates, you can accumulate internally using a **scope-confined** mutable builder, then publish an immutable snapshot when finished.
- For large datasets with many versions, consider persistent data structures with structural sharing (via a suitable library), instead of deep-copying everything at every step yourself.
- For domains that do not need snapshot sharing, a mutable structure with managed ownership may be more appropriate.

### 14.2. Structural Sharing Is Safe Only If Shared Parts Are Immutable

Two versions can share already-immutable data instead of copying everything. But if both versions point to a mutable component and one place mutates it, snapshot stability is broken. Structural sharing is a valid optimization **after** establishing the contract of each node/component.

### 14.3. Not Every Pipeline Needs a Separate Record for Every Step

If three steps merely transform a plain `String`, creating three records `ValidatedString`, `NormalizedString`, and `FinalString` can make the code harder to read without adding much value. Use domain types when they express invariants, responsibility boundaries, error info, or important metadata. Clarity and correctness matter more than the number of records.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking `final List` makes the List immutable | Only the reference is final; object can still be mutated | Use appropriate copy/view and control ownership |
| Using a record with `List` without copying | External List mutation changes the record | `List.copyOf` in the constructor |
| Using `Collections.unmodifiableList(source)` as a snapshot | Wrapper still reflects backing mutations | `List.copyOf` when a snapshot is needed |
| Thinking `List.copyOf` deep-copies `Item` | Mutable elements can still change | Immutable elements or appropriate deep copy |
| Getter returns internal `byte[]` | Callers mutate the internal array | Return clone/copy |
| Using `Collectors.toList()` and claiming the List is immutable | API makes no mutability guarantee | `Stream.toList()`/`List.copyOf` as required |
| Letting input objects be mutated in a stage | Earlier and later steps share state | Return new objects with explicit components |
| Using `andThen` and thinking callbacks become pure | Composition does not prevent side effects | Review logic and data types |
| Reading mutable clock/random/config inside a stage | Same input can produce different outputs | Pass fixed information into the request |
| Not validating when creating records | Can publish objects in invalid states | Compact constructor/factory with invariants |
| Using `long` and thinking money can never overflow | Still has representation limits | `Math.addExact`, `multiplyExact`, and domain policy |
| Copying data while another thread mutates the source | Snapshot may be inconsistent | Synchronization/transactions at the boundary |
| Unconditionally deep-copying everything at every step | Wastes memory/CPU | Copy at proper boundaries, consider structural sharing |
| Using a mutable field in a record as a Map key | `hashCode`/`equals` semantics can change | Use only stable components for keys |
| Assuming immutable objects make the whole system thread-safe | I/O, cache, DB, callbacks still have state | Synchronize side effects separately |

## 16. Practice Exercises

### Exercise 1 — Fix a Record Leaking a Mutable List

Given:

~~~java
record Team(List<String> members) {}
~~~

Create an `ArrayList`, construct a `Team`, then add a person to the `ArrayList`. Explain why `Team` observes the change. Write a compact constructor with `members = List.copyOf(members);`, test again, and verify the list returned by the accessor cannot `add`. What if the List contains mutable elements?

### Exercise 2 — Write a Wither Without Mutating Input

Design `record UserProfile(String name,String city)` with `withCity(String newCity)`. Create `original`, `updated`, print both, and prove `original` keeps the old city. Add validation ensuring `city` is not blank if the contract requires it.

### Exercise 3 — Design Stage Types

Define `RawOrder`, `ValidatedOrder`, and `PricedOrder`. Write `Function<RawOrder,ValidatedOrder>` and `Function<ValidatedOrder,PricedOrder>`, compose with `andThen`, and check input/output types. Explain how the compiler helps block calling a pricing step before validation.

### Exercise 4 — Snapshot vs. View

Create an `ArrayList` `["A"]`, create `Collections.unmodifiableList(source)` and `List.copyOf(source)`, then add `"B"` to `source`. Observe the view `[A,B]` versus the snapshot `[A]`. Describe when each type makes sense.

### Exercise 5 — Immutable List with Mutable Elements

Create `record Payload(List<StringBuilder> values)` with a `List.copyOf` compact constructor. After creation, call `append` on a `StringBuilder` held outside. Explain why `Payload` still observes the change, then propose a model with `List<String>` copied via `builder.toString()` at the boundary.

### Exercise 6 — Refactor a Pipeline with Mutable State

Given an `OrderState` with setters `setSubtotal`, `setDiscount`, `setTotal`. Redesign it into `Basket -> PricedBasket -> Receipt`, each stage returning a new object. Verify the input before and after the pipeline using value comparisons, not just reference identity.

### Exercise 7 — Immutability and Time

A function takes `Basket` but calls `Instant.now()` itself and adds the timestamp to `Receipt`. The same `Basket` produces different `Receipt`s. Fix this by passing `Instant` into a request or injecting `Clock`; test with a fixed instant and identify which parts still have side effects.

### Exercise 8 — Overflow and Validation

Test `Item` with `quantity=0`, `unitPriceCents=-1`, or blank name. Verify the constructor rejects them. Test `Math.multiplyExact` with two numbers whose product exceeds `long` limits; explain why overflow must not be turned into a seemingly valid negative total.

### Exercise 9 — Immutable Error Results

Define sealed `Outcome<T>` with `Success<T>` and `Failure<T>`. Write a stage checking a request; valid cases return `Success` containing an immutable value object, invalid cases return `Failure` describing the error. State the limitation: generic `T` could still be a mutable object if the caller passes one in.

### Exercise 10 — Evaluating Copy Costs

Suppose a `Basket` holds tens of thousands of `Item`s and `withAdded` is called 1,000 times. Analyze the O(n) copying cost per step; propose a builder for a batch of updates that then publishes a snapshot, or an appropriate persistent structure with structural sharing. Do not optimize by intuition: measure on the target workload.

### Exercise 11 — Parallel Stream and Sharing

Use `Basket` with a truly immutable `List<Item>` to compute the sum via `parallelStream().mapToLong(...).reduce(0L,Math::addExact)`. Compare with sequential execution on small valid data. Then write a callback updating a shared `ArrayList` and explain why **an immutable input List is not enough** to make that side effect safe.

## 17. Self-Check Questions

**1. What does “immutable object” mean?** Observable state per contract does not change after creation.

**2. Does a local `final List` variable make the List immutable?** No, `final` only prevents reassigning the reference.

**3. Does `record` guarantee all components are deeply immutable?** No; mutable Lists/Maps/arrays/objects must be handled separately.

**4. What does `List.copyOf` solve?** Creates an unmodifiable List with an appropriate structural snapshot, rejects nulls, does not deep-copy elements.

**5. How does `Collections.unmodifiableList` differ from `List.copyOf`?** The wrapper view can reflect backing mutations; `copyOf` creates a structural snapshot.

**6. What does a good stage do?** Takes data with a clear contract and returns a new result without mutating input when functional design requires it.

**7. Does `Function.andThen` guarantee immutability by itself?** No; model types and function bodies determine that.

**8. What invariants does `Item` have in the program?** Non-null/non-blank name, positive quantity, non-negative unit price.

**9. Why use `Math.multiplyExact`/`addExact`?** To detect overflow instead of silently wrapping the result.

**10. Does immutability equal a pure function?** No; a stage can still call I/O, clock, or mutate external state.

**11. Does immutability help concurrency?** Yes, by reducing shared mutable state risks when reading; it does not solve publication or side-effect issues by itself.

**12. Should you copy Lists at every single step?** Not necessarily; choose sensible snapshot/ownership points and evaluate cost.

## 18. Design Checklist Before Publishing a Result

1. Does the new result have a **domain type** that accurately represents the processing state?
2. Are there any remaining setters or public mutable fields allowing the result to be mutated after creation?
3. Which components are mutable objects (List, Map, array, Date, StringBuilder, domain objects)?
4. Did the constructor defensively copy components that need a snapshot?
5. Do getters accidentally return mutable internal arrays/collections?
6. Are returned collections guaranteed unmodifiable? Are nulls and mutable elements handled appropriately?
7. Is validation/invariant checking placed at the object-creation boundary?
8. Does the stage mutate inputs/sources or shared state outside the new object?
9. Does it depend on clock, random, I/O, or concurrently changing configuration? Can stable data be passed in the request?
10. Are overflow/units/rounding controlled for quantities and money?
11. When an exception occurs mid-pipeline, are previous objects still usable? Are there side effects needing compensation?
12. When sharing objects across threads, are components truly stable and properly published?
13. Does creating new objects cause excessive copying on large datasets? Is a batch builder or structural sharing needed?
14. Do tests verify **unchanged** inputs, correct outputs, validation, nulls, and blocked List mutation?

## 19. Summary and References

**Functional design often passes immutable values between steps: `Input -> Validated -> Priced -> Result`.** Each step reads a stable state and creates a new result object, rather than mutating a shared holder. This makes code easier to understand, easier to test, well-suited for composition, and reduces bugs caused by shared mutable state.

In Java 17, `record` is well-suited for modeling handoff data, but **records are not automatically deeply immutable**. Use compact constructors to validate and defensively copy Lists/Maps as needed; `List.copyOf` creates an unmodifiable structural snapshot without deep-copying elements, whereas `Collections.unmodifiableList` is a view that can reflect mutations from the backing source. For arrays, copy both on input and output if needed.

Immutability **does not automatically create pure functions or make the entire system thread-safe**: clock, I/O, databases, shared caches, exceptions, and safe publication still need explicit design. Do not copy blindly: when data is large, evaluate costs and choose the right ownership/snapshot boundaries, potentially using an internal mutable builder before publishing an immutable value. Most importantly, **previous step data must not be unexpectedly mutated when creating the next step's result**.

**Official references:** Java SE 17 Javadoc for `java.lang.Record`, `java.util.List.copyOf`, `java.util.Collections.unmodifiableList`, `java.util.function.Function.andThen`, `java.util.stream.Stream.toList`, and `java.lang.Math.addExact/multiplyExact`; Java Language Specification on records, final fields, and lambdas; Java documentation on immutable objects and safe publication.
