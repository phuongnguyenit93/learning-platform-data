# Choosing Constructors, Factories, or Pre-Designed Update APIs for `final` Fields

In Java, a `final` field is assigned during valid initialization and cannot be **reassigned by ordinary Java code** after the object has been constructed. In Reflection, finding a `Field` and calling `setAccessible(true)` does not mean modifying that field is always permitted, safe, or preserves correct program behavior.

For **`final` fields**, the preferred approach is designing an explicit state lifecycle: use a **constructor** to pass values at initialization, a **static factory** or **builder** when semantically meaningful object creation is needed, and a **pre-designed update API** when data must change. An update API can produce **a new immutable object** or modify a field intentionally designed to be mutable. There is no need to mutate `final` fields via Reflection to achieve these goals.

## 1. What `final` Guarantees and Does Not Guarantee

```java
final class Account {
    private final String id;
    private final int points;

    Account(String id, int points) {
        this.id = id;
        this.points = points;
    }
}
```

`id` and `points` receive their values when the object is created. Afterward, ordinary Java code cannot assign `account.points = 20`. To represent an account with new points, create another `Account` via an official API, or choose a mutable design from the beginning.

Distinguish three key points:

- **Final field:** cannot be reassigned by ordinary Java code after initialization.
- **Final reference:** locks the reference, without automatically making the referenced object immutable. For instance, `final List<String> tags` can still reference a modifiable list.
- **Immutable object:** requires designing all state not to change after initialization: appropriate fields, not exposing mutable state, validating inputs, and defensive copying if needed. `List.copyOf(input)` blocks structural modification via the list API, though if elements themselves are mutable, each element must also be considered.

A `static final` field normally holds a constant or shared reference; it is not the place for continuously updated configuration. Records in Java 17 use `private final` fields for each record component; to obtain new component values, you normally create a new record.

## 2. Choosing an Approach Based on Needs

| Situation | Solution | Characteristics |
| --- | --- | --- |
| Values are known when the object is created | Constructor | Sets fields once and validates from the start |
| Multiple initialization ways or clear domain names | Static factory | Methods such as `register`, `of`, `from` return properly initialized objects |
| Many options, error-prone parameters | Builder | Collects temporary configuration, then calls `build()` to create the complete object |
| One value in an immutable object needs to change | Copy/wither | `withName` or `withPoints` returns a new object without modifying the old one |
| The object is designed to be mutable | Dedicated update method | Only changes non-`final` fields and always checks invariants |
| Updating an immutable snapshot shared by multiple threads | Safe reference replacement | E.g., `AtomicReference`, locking, or a synchronized holder |
| Initializing from JSON, DB, or a framework | Supported constructor/record/factory/builder binding | Data flows through object-creation APIs honoring the contract |
| Wanting to modify `private final` via Reflection | Revisit lifecycle and API | Avoids bypassing immutability and JVM/module constraints |

**Principle:** If data is **input at creation time**, pass it to a constructor/factory/builder. If data is a **new immutable snapshot**, create a new object. If an object has **intentionally mutable state**, use a controlled update method.

## 3. Constructors: Initializing Complete Data and Protecting Invariants

Constructors can encapsulate rules such as non-empty identifiers, positive quantities, non-negative prices, and statuses consistent with delivery dates. Placing these checks at a single initialization entry point prevents "half-constructed" objects.

```java
public final class Ticket {
    private final String code;
    private final int seats;

    public Ticket(String code, int seats) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }
        this.code = code;
        this.seats = seats;
    }

    public String code() { return code; }
    public int seats() { return seats; }
}
```

This is an **illustrative class**, without a `main`. If the seat count needs to change, do not look up `Ticket.seats` via Reflection and force an assignment. Design a way to create a new `Ticket` with a different seat count, or create a mutable ticket type with an explicit update API if business requirements genuinely call for editing the same instance.

A well-written constructor must also avoid letting `this` escape before initialization completes. Mutable data passed into a constructor may need defensive copying so callers cannot silently mutate the object's state later.

## 4. Static Factories and Builders: Creating Objects with Domain Meaning

A static factory can use a `private` constructor so every creation path enforces the same set of invariants. Example:

```java
// Illustrative snippet inside the Customer class:
public static Customer register(String id, String name) {
    return new Customer(id, name, 0);
}

public static Customer restore(String id, String name, int points) {
    return new Customer(id, name, points);
}
```

This is not a standalone runnable program because it depends on `Customer`'s constructor. The name `register` expresses the rule that new customers start with 0 points; `restore` illustrates restoring from data with existing points. The shared constructor must still validate `id`, `name`, and `points`.

A static factory is **not required** to return a new instance in every library: some factories cache or return existing instances. If identity matters, read the contract. Factories are preferred when they clarify initialization intent better than overloaded constructors, not merely to rename `new`.

For objects with many optional parameters, a builder collects choices and then calls `build()`. The builder can be mutable while preparing, yet **the output object** is still created once with `final` fields.

```text
Builder receives choices (temporary state)
                ↓
build() validates business conditions
                ↓
Constructor/factory creates complete object
                ↓
Object has final fields ready for use
```

If an object has only 2–3 clear parameters, a simple constructor or factory is usually enough; do not add an unnecessary builder.

## 5. Pre-Designed Update APIs

### 5.1. Copy/wither: changing state while preserving the old object

An immutable `Customer` can provide:

```java
// Illustrative snippet inside the Customer class:
public Customer withDisplayName(String newName) {
    return new Customer(id, newName, points);
}
```

After `Customer newer = old.withDisplayName("Binh");`, `old` is unchanged; the variable `newer` points to a new instance. Ignoring the return value retains no state change.

Records are well suited for snapshots:

```java
public record Configuration(String environment, int timeoutSeconds) {
    public Configuration {
        if (environment == null || environment.isBlank()) {
            throw new IllegalArgumentException("environment is required");
        }
        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }

    public Configuration withTimeoutSeconds(int seconds) {
        return new Configuration(environment, seconds);
    }
}
```

This is a standalone illustrative record without a `main`. The `withTimeoutSeconds` method creates a new `Configuration` through the canonical constructor and validates the new value. Records are not automatically deeply immutable if a component points to a mutable object; record design must still account for that.

### 5.2. Update methods: only for state intentionally allowed to be mutable

Not every object needs to be immutable. For example, a cart with `final id` and `int quantity` can expose `changeQuantity(int)` to edit quantity while validating that it is greater than 0. Identity stays fixed; quantity changes per business rules. This is why you **should not strip `final` from all fields** just to have setters.

If multiple threads concurrently update a mutable object, thread safety and cross-field consistency must be addressed. A simple setter or adding `volatile` to one field does not automatically make an entire business operation atomic.

## 6. Complete Java 17+ Example

Save the file as **`FinalFieldDesignDemo.java`**. The program demonstrates a factory, immutable copy, record, update method, and snapshot replacement via `AtomicReference`.

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public class FinalFieldDesignDemo {
    public static void main(String[] args) {
        Customer original = Customer.register("C-01", "An");
        Customer renamed = original.withDisplayName("Binh");
        Customer rewarded = renamed.withPoints(25);

        System.out.println("original=" + original);
        System.out.println("renamed=" + renamed);
        System.out.println("rewarded=" + rewarded);

        Configuration config = new Configuration("prod", 10);
        Configuration next = config.withTimeoutSeconds(20);
        System.out.println("config=" + config);
        System.out.println("next=" + next);

        MutableCart cart = new MutableCart("cart-7", 1);
        cart.changeQuantity(3);
        System.out.println("cart=" + cart);

        AtomicReference<Configuration> current =
                new AtomicReference<>(config);
        current.updateAndGet(old -> old.withTimeoutSeconds(30));
        System.out.println("published=" + current.get());
        System.out.println("sourceStill=" + config);
    }

    static final class Customer {
        private final String id;
        private final String displayName;
        private final int points;

        private Customer(String id, String name, int points) {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(name, "name");
            if (id.isBlank() || name.isBlank() || points < 0) {
                throw new IllegalArgumentException("invalid customer");
            }
            this.id = id;
            this.displayName = name;
            this.points = points;
        }

        static Customer register(String id, String name) {
            return new Customer(id, name, 0);
        }

        Customer withDisplayName(String newName) {
            return new Customer(id, newName, points);
        }

        Customer withPoints(int newPoints) {
            return new Customer(id, displayName, newPoints);
        }

        @Override
        public String toString() {
            return "Customer[id=" + id
                    + ", displayName=" + displayName
                    + ", points=" + points + "]";
        }
    }

    record Configuration(String environment, int timeoutSeconds) {
        Configuration {
            Objects.requireNonNull(environment, "environment");
            if (environment.isBlank() || timeoutSeconds <= 0) {
                throw new IllegalArgumentException("invalid configuration");
            }
        }

        Configuration withTimeoutSeconds(int seconds) {
            return new Configuration(environment, seconds);
        }
    }

    static final class MutableCart {
        private final String id;
        private int quantity;

        MutableCart(String id, int quantity) {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            this.id = id;
            changeQuantity(quantity);
        }

        void changeQuantity(int newQuantity) {
            if (newQuantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            this.quantity = newQuantity;
        }

        @Override
        public String toString() {
            return "MutableCart[id=" + id
                    + ", quantity=" + quantity + "]";
        }
    }
}
```

Compile/run from the directory containing the file:

```bash
javac FinalFieldDesignDemo.java
java FinalFieldDesignDemo
```

Stdout output:

```text
original=Customer[id=C-01, displayName=An, points=0]
renamed=Customer[id=C-01, displayName=Binh, points=0]
rewarded=Customer[id=C-01, displayName=Binh, points=25]
config=Configuration[environment=prod, timeoutSeconds=10]
next=Configuration[environment=prod, timeoutSeconds=20]
cart=MutableCart[id=cart-7, quantity=3]
published=Configuration[environment=prod, timeoutSeconds=30]
sourceStill=Configuration[environment=prod, timeoutSeconds=10]
```

Notable points: `Customer.register` sets initial values via the private constructor; `withDisplayName` and `withPoints` return new objects while `original` stays intact. Record `Configuration` is copied with a new timeout. `MutableCart` updates the `quantity` field through a validating API while keeping `id` `final`.

`AtomicReference.updateAndGet` atomically replaces the reference with a new snapshot, **without modifying `final` fields in the old snapshot**. The update lambda should be side-effect-free because under contention between threads it may be invoked multiple times. The example runs on a single thread, so the output above is deterministic.

## 7. Why Avoid Forcing Assignment to `final` Fields via Reflection?

A program snippet can inspect metadata:

```java
java.lang.reflect.Field field =
        Customer.class.getDeclaredField("points");
boolean isFinal = java.lang.reflect.Modifier.isFinal(
        field.getModifiers());
System.out.println(isFinal); // true
```

This is an **illustrative snippet**, not standalone: it must be placed in a context that has the `Customer` class and handles `NoSuchFieldException`. Detecting the `final` modifier does not mean "can be safely modified".

Barriers include:

1. **Access control and JPMS.** `getDeclaredField` finds metadata of a `private` field, but `Field.set` is also subject to permission checks. `setAccessible(true)` enables bypassing checks only when permitted by the JVM/module; a named module that has not opened its package to the caller may cause `InaccessibleObjectException` or make `trySetAccessible()` return `false`.
2. **Not all final fields can be written.** Groups that cannot be modified through this Reflection mechanism include `static final`, final fields in records, and final fields of hidden classes. Do not assume enabling access override is enough.
3. **Java Memory Model and invariants.** Final fields involve special initialization guarantees when an object is properly constructed. Forcing edits after an object has been published can break invariants and lead to unexpected observations by threads or JVM-optimized code. Succeeding in one test does not constitute a supported API across all runtimes.
4. **Maintenance and encapsulation.** Code depending on `private` field names breaks easily when refactoring, upgrading libraries, changing JDK versions, or restructuring modules; constructor/factory/update APIs express contracts much more clearly.

Newer JDK versions may tighten deep reflection operations on final fields beyond Java 17. Therefore, practical examples prioritize ordinary Java APIs rather than relying on mutating final fields via Reflection.

## 8. Applying This with Frameworks, Storage, and Existing Data

When loading from JSON, a database, a configuration file, or a framework, do not assume "create an empty object and assign private final fields via Reflection". Depending on the framework and version, you can use:

- **Constructor binding** for immutable classes; the mapper passes data into a validating constructor.
- **Record binding** when the library supports record components and canonical constructors.
- **Static factories or builders** if the framework supports configuring creation paths.
- **Domain APIs** to update mutable entities while preserving invariants; for immutable objects, create a new instance and persist/replace that instance.

Do not assume every serializer/ORM supports the same mode; consult the framework's documentation and verify with real data-mapping tests. When updating a database, you must also handle concurrency, transactions, versioning, caching, or identity per your real architecture. Creating a new object in memory **does not automatically** replace the old object in collections, databases, or references already held by other components.

For immutable configuration read concurrently by multiple threads, a holder with `AtomicReference<Configuration>` or appropriate synchronization is the way to replace snapshots. Threads holding references to an old snapshot keep reading the old value; callers wishing to see the new snapshot must re-read from the holder. This consistency contract must be stated explicitly.

## 9. Common Mistakes

| Mistake | Better approach |
| --- | --- |
| No setter for `final`, so using `Field.set` | Use a constructor/factory/copy API, or design a genuinely mutable field with an update method |
| Writing a setter intending to reassign a `final` field | Java does not permit reassigning this way; return a new object if immutable |
| Calling `old.withPoints(10)` but discarding the return value | Store `newState = old.withPoints(10)` and replace references where needed |
| Assuming `final List` means an immutable list | Use defensive copying and check element mutability |
| Assuming `setAccessible(true)` definitely writes `static final` or record fields | These are explicit categories of restricted final fields |
| Removing `final` from the entire class so a framework can instantiate it | Check constructor/record/factory/builder binding support first |
| Factory does not validate while constructor validates differently | Centralize invariants in a shared initialization path |
| Multiple threads update the same mutable object with only a plain setter added | Choose appropriate synchronization/atomic/transaction mechanisms; check multi-field operations |
| Replacing an immutable instance while forgetting to update cache/repository/state holder | Publish and store the new instance reference per the system contract |

## 10. Decision Checklist When Facing a "Modify Final Field" Request

1. **Is this initialization data?** If yes, pass it through a constructor, factory, or builder before publishing the object.
2. **Must the old object remain untouched?** For immutable snapshots, choose `withXxx`/copy and use the new object. For mutable domain types, consider an explicit update method.
3. **What are the invariants?** Define validity conditions for both initialization and update data.
4. **Is it shared across threads or persisted in a database/cache?** Define a consistent mechanism for publishing/persisting the new state.
5. **Does the framework already support an official initialization path?** Look for constructor/record/factory/builder binding before relying on private fields.
6. **Is Reflection being used solely to work around a design flaw?** If so, fix the API in the domain layer or integration adapter instead of intervening in final fields.

**Remember:** `final` defines the assignment boundary in an object's lifecycle. Constructors/factories/builders establish initial state; copy/withers produce new immutable state; conditional update APIs manage mutable state. Reflection can provide metadata, but should not be the application's mechanism for updating `final` fields.
