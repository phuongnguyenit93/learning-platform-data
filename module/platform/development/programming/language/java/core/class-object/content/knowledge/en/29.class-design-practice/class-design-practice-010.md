# Common Mistakes Checklist and Class Design Self-Evaluation Criteria — Java 17

## 1. Goal: Check *design*, not just syntax

A Java class can compile, pass a few basic examples, and still have a poor design: allowing invalid states to be created, leaking internal lists, misusing `static`, having inconsistent `equals/hashCode`, being hard to test, or relying on the garbage collector to close resources. Conversely, a class with more lines of code is sometimes easier to use and safer if it clearly expresses its **responsibilities, invariants, ownership, and API contract**.

This README provides a **practical catalog of mistakes** and a **set of class design self-evaluation criteria** for Java 17. Each category includes identifying symptoms, causes, consequences, fixes, and, where appropriate, a standalone Java program to verify.

After studying this, you can:

- Identify whether a class has **one clear purpose**, who owns the data, and which invariants must always hold.
- Distinguish the **public API** from implementation details, and choose appropriate access modifiers.
- Evaluate constructors/factories: validation, default state, initialization errors, and not leaking `this`.
- Control mutability, aliasing, defensive copies, and avoid exposing internal collections/arrays.
- Choose the right semantics for `equals`, `hashCode`, identity, `toString`, and map keys.
- Evaluate inheritance, composition, polymorphism, `final`, `sealed`, `record`, `enum`.
- Recognize `static` mistakes, shared mutable state, and concurrency issues.
- Check generic type safety, exception policies, and `AutoCloseable` resources.
- Turn vague feedback like "bad class" into **evidence-based criteria, ways to test, and an order of priority**.

**Scope:** Java Core class/object and design review practice. Examples use **Java 17**. No frameworks or build tools outside the JDK are assumed; some integration patterns are explicitly marked as snippets.

## 2. A five-question review template

For any class, read in this order:

1. **Role:** does the class represent a value, entity, service, resource owner, utility, or a group of constants?
2. **Invariant:** which states must never occur, both after the constructor and after every public method?
3. **API boundary:** what can the caller see/call, and is there any path that alters state contrary to intent?
4. **Relationships:** what types does the class depend on, do extends/implements satisfy a true *is-a* relationship, and are there reference cycles, global state, or unclear ownership?
5. **Evidence:** are there tests for success, invalid inputs, mutation, equality, failure paths, concurrent access, and resource cleanup where relevant?

A valuable review must pinpoint **the code causing the flaw** and **the violated behavior**, rather than merely criticizing the class for being too long or having many getters.

## 3. Categorizing mistakes for prioritization

| Mistake Category | Example | Suggested Priority |
| --- | --- | --- |
| Correctness defects | Can create `Account(-10)`; unvalidated NEW→SHIPPED transition | Critical |
| Exposed state/ownership | Returning the owner's mutable list/array; client modifies data | Critical/High |
| Equality/hash contract | Mutable HashMap key, non-symmetric equals | High |
| Concurrency | `count++` on a shared object, check-then-act race | High if multithreaded |
| Resource lifetime | Socket/stream not closed properly on error paths | High |
| API/encapsulation | Public mutable field, unchecked public setter | High/Medium |
| Abstraction | Inheritance violates is-a, subclass has to throw unsupported | High/Medium |
| Maintainability | "God class", multiple reasons to change, hard-coded dependency | Medium |
| Syntax/style | Confusing names, duplicated code, inconsistent formatting | Low/Medium |

**Do not turn these priorities into rigid rules.** A public field may be an intentional data-carrier API, and a class with many lines can still have a single coherent responsibility. Classification must be based on invariants and actual impact.

## 4. Mistake 1 — Public mutable fields break encapsulation

Symptom:

```java
class Account {
    public long balance;
    public String id;
}
```

Callers can assign `balance=-1` and `id=null` without validation. A class used as an entity with the invariant "non-negative balance" cannot protect itself.

**Fix:** keep fields `private`, define operations with business meaning, and validate on every mutation path:

```java
final class Account {
    private final String id;
    private long balance;

    Account(String id, long initial) {
        if (id == null || id.isBlank() || initial < 0) {
            throw new IllegalArgumentException("invalid");
        }
        this.id = id;
        balance = initial;
    }

    void deposit(long amount) {
        if (amount <= 0) throw new IllegalArgumentException("amount");
        balance = Math.addExact(balance, amount);
    }

    long balance() { return balance; }
}
```

This is a **snippet** illustrating the API, not yet a standalone runnable program.

### How to self-check

Ask: "Is there any valid statement from outside the class that can break an invariant without going through controlled methods?" If yes, the class has an encapsulation flaw.

## 5. Runnable: Private fields and methods preserving invariants

Save **`EncapsulationDemo.java`**:

```java
final class Wallet {
    private long cents;

    Wallet(long cents) {
        if (cents < 0) throw new IllegalArgumentException("negative");
        this.cents = cents;
    }

    void add(long value) {
        if (value <= 0) throw new IllegalArgumentException("amount");
        cents = Math.addExact(cents, value);
    }

    long cents() { return cents; }
}

public class EncapsulationDemo {
    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.add(25);
        System.out.println(wallet.cents());

        try {
            wallet.add(-1);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
        System.out.println(wallet.cents());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
```

Stdout:

```text
125
amount
125
```

The invalid operation is rejected without corrupting the valid state.

## 6. Mistake 2 — Constructor does not create a valid object

Symptoms:
- The constructor allows `null` in a required field.
- Setters are called after `new` to "complete" the object.
- Min/max bounds and relationships between fields are not validated.
- There are multiple constructors with different validation rules.
- The constructor throws an exception after already registering `this` with a singleton/listener.

Example of a broken contract:

```java
class Range {
    int start;
    int end;
    Range(int start, int end) {
        this.start = start;
        this.end = end; // start > end is possible.
    }
}
```

An invariant must hold from **successful construction**. If the class is mutable, every operation must also preserve the invariant after mutation.

**Fix:** validate before publishing the reference; avoid letting `this` escape from the constructor (starting a thread, callback registries, dangerous calls to overridable methods). If there are multiple ways to construct the object, centralize invariants in the core constructor/factory.

## 7. Runnable: Constructor preserving invariants

Save **`ConstructorInvariantDemo.java`**:

```java
record Range(int from, int to) {
    Range {
        if (from > to) {
            throw new IllegalArgumentException("from > to");
        }
    }

    int length() { return to - from; }
}

public class ConstructorInvariantDemo {
    public static void main(String[] args) {
        Range range = new Range(2, 7);
        System.out.println(range.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorInvariantDemo.java
java ConstructorInvariantDemo
```

Stdout:

```text
5
from > to
```

A record compact constructor also needs validation; record syntax does **not** automatically check business rules.

## 8. Mistake 3 — Getters/setters are not always a good API

An `Order` class with only `setStatus`, `setTotal`, and `setPaidAt` can allow callers to create a "PAID but paidAt null" state.

A behavior-oriented API:

```java
order.pay(receipt);
order.cancel(reason);
```

is clearer if these operations validate transitions and update related fields as a single unit.

### Criteria

- How many setters exist solely for framework binding?
- Must the caller invoke a specific **order of setters** to avoid an invalid intermediate state?
- Can the operations be named in business terms?
- Could a data carrier/DTO object simply be a record instead of a class full of setters?
- If the object needs mutable state, are mutations properly grouped by transactional boundaries?

Not every setter is bad: a `PointEditor#setZoom` in a UI can be completely reasonable. The problem is **setters that open a path to violating invariants**.

## 9. Mistake 4 — Exposing a mutable collection through an accessor

Wrong:

```java
class Team {
    private final List<String> members = new ArrayList<>();
    List<String> members() { return members; }
}
```

Callers can call `team.members().clear()`, bypassing the class's intended control over membership.

Options:
- Return a snapshot `List.copyOf(members)`.
- Return an unmodifiable view if you **intentionally** want callers to observe future changes without modifying through the view.
- Return a stream/iterator with clear semantics if appropriate.
- Expose `addMember/removeMember` operations to preserve invariants.
- For records/value objects, defensively copy both **input** and **output** as appropriate for the data type.

**Note:** `Collections.unmodifiableList(source)` is a view that can reflect changes to the source; `List.copyOf(source)` is an unmodifiable shallow snapshot. If the elements are mutable, neither **deep-copies elements**.

## 10. Runnable: Copy preventing caller mutation

Save **`DefensiveListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Team {
    private final List<String> members = new ArrayList<>();

    void add(String member) {
        if (member == null || member.isBlank()) {
            throw new IllegalArgumentException("member");
        }
        members.add(member);
    }

    List<String> members() {
        return List.copyOf(members);
    }
}

public class DefensiveListDemo {
    public static void main(String[] args) {
        Team team = new Team();
        team.add("An");
        List<String> snapshot = team.members();

        team.add("Binh");

        System.out.println(snapshot);
        System.out.println(team.members());

        try {
            snapshot.add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DefensiveListDemo.java
java DefensiveListDemo
```

Stdout:

```text
[An]
[An, Binh]
unmodifiable
```

The snapshot behavior is very clear: the previous value does not update automatically when the owner changes.

## 11. Mistake 5 — Thinking `final`/`record` automatically makes an object immutable

Three misconceptions:
- `final class`: only prevents subclasses; it does **not** require instance fields to be final.
- `final List<String> field`: only prevents reassigning the field; it does **not** forbid `field.add(...)`.
- `record Holder(List<String> items)`: the component field is final, but the list can be mutable.

For value objects, you must check **all paths for mutable aliases**. If using arrays, clone the input/output; if using collections, copy at the appropriate level; if elements are mutable, use immutable values or an appropriate deep-copy strategy.

### Self-evaluation criteria

1. Does the object still have observable state that can change after construction?
2. Does the caller retain a reference to a mutable input?
3. Does an accessor return internal state directly?
4. Do generated `equals/hashCode` depend on mutable state?
5. If deep immutability is required, is there a test modifying a nested element after construction?

## 12. Runnable: Record with a mutable component and fixing it

Save **`RecordAliasingReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeTeam(List<String> members) { }

record SafeTeam(List<String> members) {
    SafeTeam {
        members = List.copyOf(members);
    }
}

public class RecordAliasingReviewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        UnsafeTeam unsafe = new UnsafeTeam(source);
        SafeTeam safe = new SafeTeam(source);

        source.add("B");

        System.out.println(unsafe.members());
        System.out.println(safe.members());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RecordAliasingReviewDemo.java
java RecordAliasingReviewDemo
```

Stdout:

```text
[A, B]
[A]
```

`SafeTeam` is safe for a list of immutable Strings as intended by the example; for a list of mutable elements, `List.copyOf` still performs only a shallow copy.

## 13. Mistake 6 — Returning a mutable array directly

Arrays are mutable objects, and Java has no `Collections.unmodifiableArray`. For `byte[]`/`int[]` stored in a value object:
- The constructor should `clone()` the input array.
- The accessor returns `clone()` if the data needs to be exposed.
- Equality/hashCode must be considered: record-generated equality on an array component defaults to **array reference** equality, not deep-content equality.
- If content-based value semantics are needed, `Arrays.equals` and `Arrays.hashCode` must be consistent.

**Anti-pattern:** `record Packet(byte[] payload){}` and assuming Packet is deeply immutable and that `new Packet(new byte[]{1}).equals(new Packet(new byte[]{1}))` is true.

## 14. Runnable: Immutable wrapper around an array

Save **`ArrayValueReviewDemo.java`**:

```java
import java.util.Arrays;

final class Bytes {
    private final byte[] data;

    Bytes(byte[] data) {
        this.data = data.clone();
    }

    byte[] toArray() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes that
                && Arrays.equals(data, that.data);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(data);
    }
}

public class ArrayValueReviewDemo {
    public static void main(String[] args) {
        byte[] raw = {1, 2};
        Bytes a = new Bytes(raw);
        Bytes b = new Bytes(new byte[]{1, 2});

        raw[0] = 9;
        byte[] detached = a.toArray();
        detached[1] = 8;

        System.out.println(Arrays.toString(a.toArray()));
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ArrayValueReviewDemo.java
java ArrayValueReviewDemo
```

Stdout:

```text
[1, 2]
true
true
```

The object hides its representation and defines content-based value equality; the code is longer than a record, but more faithful to the contract when the underlying data is a mutable array.

## 15. Mistake 7 — Inconsistent `equals` and `hashCode`

A mandatory rule of the Java `Object` contract:

> If `a.equals(b)` is true, `a.hashCode() == b.hashCode()` must be true.

The converse is **not required**: having the same hash does not imply equality.

Common mistakes:
- Overriding `equals` while forgetting `hashCode`.
- Using different fields for equals and hash.
- Non-symmetric equals due to inheritance and carelessly designed `instanceof`/`getClass`.
- Using mutable fields for hashing and then mutating the object while it is a key in a HashMap/HashSet.
- `equals` throwing an exception for `null` or a different type instead of returning false according to the proper contract.

For immutable **value objects**, a record can provide appropriate generated equality **if all components have the right equality semantics**.

## 16. Runnable: Record equality and HashSet

Save **`EqualityContractDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) { }

public class EqualityContractDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);

        Set<Point> points = new HashSet<>();
        points.add(first);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(points.contains(second));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EqualityContractDemo.java
java EqualityContractDemo
```

Stdout:

```text
false
true
true
```

A record was chosen because **coordinates** are a value, not because every class should automatically define equality by its fields.

## 17. Mistake 8 — Entity identity equated with all fields

A `Customer` with a stable business ID and a mutable address should not necessarily define equality across the address as well. If you write `equals/hashCode` over all fields:
- Updating the address changes equality/hash.
- The entity can "change identity" inside a Set.
- Two different customers with the same name/address could be treated as one.
- When ORM proxies/lifecycles are involved, how equality is defined requires checking the framework contract even more carefully.

**Ask:** Does "same entity" mean the same object reference, the same generated ID, the same natural key, or the same entire state snapshot?

- **Entity:** usually has a stable business identity; the equality policy should be clearly documented.
- **Value:** equality by data; a record may be appropriate.
- **DTO snapshot:** can define equality by components, not directly replacing entity identity.
- **Enum:** identity by constants; `==` is appropriate.

### Do not assume every entity must override equals by ID

If the ID is assigned by the database *after* the object is created, equality by ID requires carefully handling `null` and transient instances. You may choose identity-based semantics depending on the layer. What matters is **consistency across the lifecycle**.

## 18. Mistake 9 — Mutable keys break lookup in HashMap

If a field participating in `hashCode` changes after the object is used as a Map key, lookups can fail. The issue lies in the hash-based container's invariant, not that "HashMap is broken".

Anti-pattern snippet:

```java
class MutableKey {
    String code;
    // equals/hashCode uses code...
}
Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey();
key.code = "A";
map.put(key, "value");
key.code = "B"; // Violates hash stability of a key currently in the map.
```

**Fix:** use an immutable record/class as the key, or an unchanging stable ID; do not mutate the identity/equality fields of an object while it is in a hash collection.

## 19. Runnable: Stable key using a record

Save **`StableMapKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

record OrderKey(String tenant, String number) { }

public class StableMapKeyDemo {
    public static void main(String[] args) {
        Map<OrderKey, String> orders = new HashMap<>();
        orders.put(new OrderKey("VN", "100"), "PAID");

        System.out.println(
                orders.get(new OrderKey("VN", "100")));
        System.out.println(
                orders.containsKey(new OrderKey("VN", "999")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StableMapKeyDemo.java
java StableMapKeyDemo
```

Stdout:

```text
PAID
false
```

The record components here are immutable Strings. Using the record as a key is safe because equality/hash is stable based on data, with no mutation API.

## 20. Mistake 10 — `toString()` exposes secrets or traverses too large a graph

`toString` is commonly used for debugging and logs, but it can cause:
- Exposure of passwords, tokens, session cookies, or unmasked account numbers.
- Exposure of PII when the object is logged automatically.
- Pulling an entire object graph into a huge string.
- Infinite recursion/stack overflow with cyclic references if written carelessly.
- Calling getters that cause side effects/I/O.

**Record-generated toString** exposes component names/values; therefore, a record containing `password`/`apiKey` can leak sensitive information when logged. Do not use records "for free" for secrets while forgetting about exposure.

### How to fix

- Print only safe identifiers and metadata.
- Redact/mask credentials.
- Limit the length of collections/text.
- Do not call business methods with side effects from `toString`.
- For security logs, use selective structured logging fields instead of logging the entire object.

## 21. Runnable: Redacting in `toString`

Save **`SafeToStringDemo.java`**:

```java
final class ApiCredential {
    private final String label;
    private final String secret;

    ApiCredential(String label, String secret) {
        this.label = label;
        this.secret = secret;
    }

    String secret() {
        return secret;
    }

    @Override
    public String toString() {
        return "ApiCredential[label=" + label
                + ",secret=<redacted>]";
    }
}

public class SafeToStringDemo {
    public static void main(String[] args) {
        ApiCredential key = new ApiCredential("service", "TOP-SECRET");
        System.out.println(key);
        System.out.println(key.secret().length());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
```

Stdout:

```text
ApiCredential[label=service,secret=<redacted>]
10
```

The last line only illustrates that the internal API still holds the data; do not treat the secret getter as an API that should be public. For real secrets, consider not retaining them longer than necessary and avoid writing sensitive lengths/metadata to logs.

## 22. Mistake 11 — Using `static` for per-object state

Flawed modeling:

```java
class Session {
    static String currentUser;
}
```

If multiple `Session` objects are independent, the static field is shared across all instances, causing one session to overwrite another.

`static` is appropriate for:
- Constants that are truly independent of instances.
- Stateless utility methods.
- Factories.
- Shared registries with clearly designed ownership/concurrency (use with caution).

It is **not** appropriate just because "you want all methods to easily access this variable".

### Comparison

- `private String userId;`: state of each individual Session object.
- `private static final int DEFAULT_TIMEOUT = 30;`: constant of the type.
- `private static final Map<...> CACHE = ...`: shared mutable graph requiring clear eviction, thread safety, and lifecycle.

## 23. Runnable: Unintentionally shared static state

Save **`StaticStatePitfallDemo.java`**:

```java
final class BadSession {
    static String user;
    BadSession(String name) { user = name; }
}

final class GoodSession {
    private final String user;
    GoodSession(String name) { user = name; }
    String user() { return user; }
}

public class StaticStatePitfallDemo {
    public static void main(String[] args) {
        BadSession a = new BadSession("An");
        BadSession b = new BadSession("Binh");

        System.out.println(a.user);
        System.out.println(b.user);

        GoodSession c = new GoodSession("An");
        GoodSession d = new GoodSession("Binh");

        System.out.println(c.user());
        System.out.println(d.user());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticStatePitfallDemo.java
java StaticStatePitfallDemo
```

Stdout:

```text
Binh
Binh
An
Binh
```

In Java, accessing static members via an instance is permitted but misleading and can generate a compiler warning; in production, use `BadSession.user` to make shared state explicit.

## 24. Mistake 12 — Shared mutable state without a concurrency strategy

`counter++` is **not** an atomic operation for shared increments because it is read-modify-write. `volatile int counter` helps with visibility, **not** with turning `counter++` into an atomic increment.

Strategy depends on the use case:
- Thread confinement (one object per thread).
- Immutable snapshots.
- `synchronized`/locks.
- `AtomicInteger` or concurrent collections.
- Database transactions/optimistic locking for persistence.

Do not choose a strategy based on "make all shared fields volatile"; first determine **which invariants require atomicity**, operation boundaries, and consistency requirements.

## 25. Runnable: AtomicInteger for a shared counter

Save **`AtomicCounterDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class Hits {
    private final AtomicInteger count = new AtomicInteger();

    int hit() {
        return count.incrementAndGet();
    }

    int count() {
        return count.get();
    }
}

public class AtomicCounterDemo {
    public static void main(String[] args) {
        Hits hits = new Hits();

        hits.hit();
        hits.hit();

        System.out.println(hits.count());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AtomicCounterDemo.java
java AtomicCounterDemo
```

Stdout:

```text
2
```

This example only confirms that the counter operation is atomic via `AtomicInteger`; for workflows involving multiple fields, a single atomic integer is not enough to preserve multi-field invariants.

## 26. Mistake 13 — Inheriting just to reuse a few lines of code

A subclass must fulfill the superclass's contract. If you design:

```java
class Rectangle {
    void setWidth(int width) { ... }
    void setHeight(int height) { ... }
}

class Square extends Rectangle {
    // Overriding setters can break the caller's expectations about width/height.
}
```

this is a **pseudocode snippet** illustrating the Liskov substitution problem, not a runnable program.

If the client expects changing width not to alter height, while Square must keep both sides equal, the subclass can violate Rectangle's contract.

**Design mistake:** using `extends` because two classes share similar data/methods, rather than because the subclass is **truly substitutable** for the superclass in all valid contexts.

### Replace with composition or a common interface

```java
interface Shape {
    int area();
}

final class Square implements Shape { ... }
final class Rectangle implements Shape { ... }
```

A shared calculator/dependency can be extracted into a helper or collaborator. Inheritance is only worth using when there is a stable *is-a contract*.

## 27. Runnable: Polymorphism through an interface

Save **`CompositionVsInheritanceDemo.java`**:

```java
interface Shape {
    int area();
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

record Square(int side) implements Shape {
    @Override
    public int area() {
        return side * side;
    }
}

public class CompositionVsInheritanceDemo {
    public static void main(String[] args) {
        Shape a = new Rectangle(3, 4);
        Shape b = new Square(5);

        System.out.println(a.area());
        System.out.println(b.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CompositionVsInheritanceDemo.java
java CompositionVsInheritanceDemo
```

Stdout:

```text
12
25
```

Both records implement the same **behavior contract** without forcing a Square extends Rectangle relationship.

## 28. Mistake 14 — Class allowing uncontrolled subclassing

When a public class is not final, a client can subclass it (if constructors/visibility allow). If the superclass:
- Calls an overridable method in its constructor;
- Relies on a private invariant that a subclass could break through overrides;
- Defines `equals` while a subclass adds state that affects equality;
- Does not document rules for overriding;

then the inheritance API becomes very difficult to maintain.

### Ask yourself

- Was the class **intentionally designed to be extended**?
- Do methods allowed to be overridden have a documented contract?
- If extension is not needed, can `final` be used?
- If you want to whitelist subtypes in Java 17, are `sealed`/`permits` appropriate?
- Would an interface + composition convey the extension point more clearly?

**Do not apply `final` blindly** when a framework genuinely requires proxies/subclasses; check the framework's contract/version first.

## 29. Mistake 15 — Calling an overridable method in a constructor

In Java, dynamic dispatch can invoke a subclass override **before the subclass has finished initializing its fields**. This is a subtle bug.

Anti-pattern:

```java
class Base {
    Base() {
        hook(); // Dynamic dispatch inside the constructor.
    }

    void hook() { }
}

class Child extends Base {
    private final String value = "ready";

    @Override
    void hook() {
        // Can observe value before it is initialized.
    }
}
```

**Fix:** the constructor should only use safe private/final helpers, or construct the object completely first and then invoke a controlled lifecycle method if the API truly needs one. Do not publish `this` inside the constructor to external callbacks.

## 30. Runnable: Dynamic dispatch during construction

Save **`ConstructorDispatchPitfallDemo.java`**:

```java
class Base {
    Base() {
        show();
    }

    void show() {
        System.out.println("base");
    }
}

final class Child extends Base {
    private final String message = "ready";

    @Override
    void show() {
        System.out.println(message);
    }
}

public class ConstructorDispatchPitfallDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ConstructorDispatchPitfallDemo.java
java ConstructorDispatchPitfallDemo
```

Stdout:

```text
null
ready
```

Inside the `Base` constructor, dynamic dispatch calls Child.show **before the Child instance field initializer runs**. After construction, the field is "ready".

## 31. Mistake 16 — Confusing overloading, overriding, and static hiding

Compile-time/runtime mistakes often stem from:
- Confusing a method overload `print(Object)` with an override `print(String)`.
- Assuming static methods are dynamically dispatched like instance methods.
- Mistakenly thinking private methods can be overridden.
- Omitting `@Override`, so signature mismatches are not caught quickly.
- Neglecting checked exception/return type/covariance rules.

### Quick checklist

- **Overloading**: same name, different parameter list; the compiler chooses based on static types, conversions, and applicability.
- **Overriding**: a subclass provides an implementation for an overridable inherited instance method; runtime dispatch follows the object's class.
- **Static hiding**: the method is chosen based on the compile-time reference type, without dynamic dispatch like an instance override.
- **`@Override`**: the compiler checks the annotation, helping catch cases of "thought it was an override, but it's actually an overload".

## 32. Runnable: Overload vs. override

Save **`OverrideVsOverloadDemo.java`**:

```java
class Parent {
    String action(Object value) {
        return "parent:Object";
    }
}

final class Child extends Parent {
    @Override
    String action(Object value) {
        return "child:Object";
    }

    String action(String value) {
        return "child:String";
    }
}

public class OverrideVsOverloadDemo {
    public static void main(String[] args) {
        Parent parent = new Child();
        Child child = new Child();

        System.out.println(parent.action("A"));
        System.out.println(child.action("A"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OverrideVsOverloadDemo.java
java OverrideVsOverloadDemo
```

Stdout:

```text
child:Object
child:String
```

Overload resolution relies on the static type (`Parent` only has action(Object)); the instance override body still dispatches to Child.action(Object).

## 33. Mistake 17 — Class with too many responsibilities (*God class*)

Symptoms of an `OrderManager` that simultaneously:
- Validates orders;
- Queries the database;
- Calls the payment gateway;
- Renders HTML;
- Sends emails;
- Calculates VAT;
- Writes system logs;
- Maintains a cache;
- Manages a thread pool.

This can be a **reasonable application coordination point** if it only performs orchestration. However, if all the low-level implementation logic resides inside one class, it has **many reasons to change** and is hard to test in isolation.

### Evaluating via change drivers

Ask "which independent groups of changes force this file to be modified?"
- Currency policies;
- HTML templates;
- Payment provider API;
- Database schema;
- Email provider;
- Workflow state machine.

If these changes force modifications to a single class, consider splitting out **cohesive collaborators** by responsibility. Do not take splitting to the extreme of one class per method; abstractions must genuinely reduce coupling.

## 34. Mistake 18 — Hard-coded dependencies prevent unit testing

Anti-pattern:

```java
class ReportService {
    void publish() {
        new RealEmailClient().send(...);
    }
}
```

Production code and the integration dependency are hard-wired inside the method. A test trying to verify that "publish calls send" has to hit the network or resort to complex monkey patching.

### Constructor injection

```java
interface Notifier {
    void send(String message);
}

final class ReportService {
    private final Notifier notifier;

    ReportService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void publish() {
        notifier.send("report-ready");
    }
}
```

This is a valid **snippet** within scope/class declarations. By receiving the dependency through the constructor, tests can use a fake in-memory notifier without needing a DI framework.

## 35. Runnable: Constructor injection and a fake dependency

Save **`DependencyInjectionDemo.java`**:

```java
interface Notifier {
    void send(String message);
}

final class RecordingNotifier implements Notifier {
    private String last;

    @Override
    public void send(String message) {
        last = message;
    }

    String last() {
        return last;
    }
}

final class ReportService {
    private final Notifier notifier;

    ReportService(Notifier notifier) {
        this.notifier = java.util.Objects.requireNonNull(notifier);
    }

    void publish() {
        notifier.send("ready");
    }
}

public class DependencyInjectionDemo {
    public static void main(String[] args) {
        RecordingNotifier fake = new RecordingNotifier();
        ReportService service = new ReportService(fake);

        service.publish();

        System.out.println(fake.last());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DependencyInjectionDemo.java
java DependencyInjectionDemo
```

Stdout:

```text
ready
```

Testability is high because the service depends on an **interface contract**, rather than creating a hidden external dependency itself.

## 36. Mistake 19 — Excessive getters leading to *feature envy* / long call chains

The expression:

```java
order.getCustomer().getAddress().getCountry().getTaxZone()
```

shows that the caller knows many internal details of the graph. Not every method chain is wrong; reading an immutable DTO graph can be completely reasonable. However, if the caller also **deeply mutates** state:
- Encapsulation is weak;
- A change in internal layout breaks many callers;
- Invariants become scattered;
- Null handling spreads everywhere.

Behavior can be moved back to the owner:

```java
order.taxZone();
order.calculateTax(policy);
```

or to a dedicated service if the operation goes beyond Order's responsibility.

**A good criterion:** who has enough data and business context to preserve the invariant? Place the behavior there instead of moving all logic out into a giant utility/service.

## 37. Mistake 20 — Using raw generic types and unchecked casts

Wrong:

```java
List values = new ArrayList();
values.add("A");
values.add(123);
```

With a raw `List`, the compiler loses type checks; consumers can encounter a `ClassCastException`.

Correct when the element type is known:

```java
List<String> values = new ArrayList<>();
values.add("A");
```

Evaluate:
- Are raw types present solely because of legacy code?
- Does `@SuppressWarnings("unchecked")` hide the problem instead of isolating and validating it?
- Can generic bounds/parameters express the contract more clearly?
- Is `List<?>` appropriate when only reading objects from the list?
- Is there unchecked heap pollution from varargs/arrays?

**The diamond `<>` is not a raw type.** `new ArrayList<>()` still uses type inference; `new ArrayList()` is the raw constructor usage.

## 38. Runnable: Diamond and type safety

Save **`GenericApiReviewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericApiReviewDemo {
    static int totalLength(List<String> words) {
        int sum = 0;
        for (String word : words) {
            sum += word.length();
        }
        return sum;
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("17");

        System.out.println(totalLength(words));
    }
}
```

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 GenericApiReviewDemo.java
java GenericApiReviewDemo
```

Stdout:

```text
6
```

A parameterized API prevents callers from inserting an Integer into the list through normal compile-time checked operations.

## 39. Mistake 21 — Excessive nulls and invalid sentinel states

Symptoms:
- A getter returns `null` without documenting it.
- The constructor succeeds with a required field set to null, forcing every method to check it again.
- Using `-1` everywhere to mean "no value yet".
- An enum has `UNKNOWN`, `NONE`, `UNSET`, and `NOT_APPLICABLE` with overlapping meanings.
- Catching an exception and returning null, hiding the cause of failure.

### Fixes

- Validate required constructor parameters with `Objects.requireNonNull`.
- Use empty collections instead of null if that is a reasonable contract.
- For a value that **may be absent**, consider `Optional<T>` at the return boundary, without overusing it for every field.
- For multiple success/failure result types with distinct payloads, consider a sealed interface + record variants.
- If null is a valid value, document it clearly (and handle it in code/tests).

## 40. Runnable: Optional at the return boundary

Save **`OptionalReturnDemo.java`**:

```java
import java.util.Map;
import java.util.Optional;

final class Directory {
    private final Map<String, String> names =
            Map.of("a", "An");

    Optional<String> lookup(String id) {
        return Optional.ofNullable(names.get(id));
    }
}

public class OptionalReturnDemo {
    public static void main(String[] args) {
        Directory directory = new Directory();

        System.out.println(directory.lookup("a").orElse("missing"));
        System.out.println(directory.lookup("b").orElse("missing"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OptionalReturnDemo.java
java OptionalReturnDemo
```

Stdout:

```text
An
missing
```

`Optional` makes the caller handle the absent-value case without relying on an undocumented null. Do not use Optional to replace every kind of error that needs diagnostics.

## 41. Mistake 22 — Overly broad catches, swallowing errors, or converting to fake state

`catch (Exception ignored) { }` can keep the class "working" while holding invalid state and hiding the root cause.

Evaluate:
- Can the method recover here?
- Does the exception represent a **programming error** or an **expected business validation**?
- If recovery is not possible, should it propagate with appropriate context?
- Does cleanup run when an error occurs?
- Is the same exception logged multiple times across every layer (log spam)?
- Does a thrown exception contain secrets/PII?

### Choosing checked vs. unchecked according to contract

There is no single rule that "all domain errors are checked" or "all errors are unchecked". In Java Core, checked exceptions indicate that the caller is typically expected to handle/declare them; unchecked exceptions are used for certain programming errors/invalid arguments. What matters is that the API is documented and consistent.

## 42. Mistake 23 — Resource not closed in the proper scope

Objects managing an `InputStream`, `Socket`, JDBC `Connection`, or native handle should not rely on GC/`finalize()`.

Pattern:

```java
try (InputStream stream = Files.newInputStream(path)) {
    // consume(stream)
}
```

This is a snippet assuming appropriate imports/path and IOException handling.

Review:
- Who owns the resource?
- Is `close()` called on both success and error paths?
- Is there any constructor acquisition failure?
- Does the `AutoCloseable` implementation have a clear lifecycle?
- Does a borrower accidentally close the owner's resource?
- Are multiple resources closed in the right dependency order?
- If `Cleaner` is used, is it only as a backstop rather than replacing explicit close?

In Java 17, `Object.finalize()` has been deprecated since Java 9; **do not use it for resource management**. `try-with-resources` provides deterministic closing according to Java control flow and handles suppressed exceptions.

## 43. Runnable: Closing even when the body fails

Save **`ResourceOwnershipDemo.java`**:

```java
final class Handle implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("close");
    }

    void work() {
        System.out.println("work");
    }
}

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        try (Handle handle = new Handle()) {
            handle.work();
            throw new IllegalStateException("failed");
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceOwnershipDemo.java
java ResourceOwnershipDemo
```

Stdout:

```text
work
close
failed
```

There is no System.gc(), sleep, or finalize hook; cleanup happens upon exiting the scope.

## 44. Mistake 24 — Setting a `ThreadLocal` without cleaning it up in a thread pool

`ThreadLocal<T>` helps store thread-specific state, but a worker thread may serve multiple requests. If context is `set` without calling `remove`:
- The next request may see stale state.
- References are retained beyond their business lifetime.
- Memory leaks or classloader retention can occur depending on the runtime.

Use:

```java
CONTEXT.set(requestId);
try {
    process();
} finally {
    CONTEXT.remove();
}
```

**Snippet**, assuming CONTEXT/process are already defined. ThreadLocal does not automatically reset per task. If there is cross-thread async execution, context must be passed appropriately; ThreadLocal does not automatically propagate to every thread.

## 45. Mistake 25 — Missing defensive state for concurrent snapshots

A class has:

```java
private int x;
private int y;

Point snapshot() {
    return new Point(x, y);
}
```

If writers update x/y without synchronization, snapshot can observe a pair of values that do not belong to the same logical update. An immutable `Point` record does **not** automatically make reads from a mutable owner consistent.

Solutions depend on the invariant:
- Protect both updates and snapshots with the same lock.
- Store an immutable State record in a `volatile`/AtomicReference and **swap the entire state**.
- Transactions at the persistence boundary.
- Thread confinement.

**Review mindset:** check the **atomicity of multi-field invariants**, not merely whether each individual field is volatile/final.

## 46. Runnable: AtomicReference holding an immutable snapshot

Save **`AtomicSnapshotDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;

record Position(int x, int y) { }

final class Tracker {
    private final AtomicReference<Position> current =
            new AtomicReference<>(new Position(0, 0));

    void move(int dx, int dy) {
        current.updateAndGet(old ->
                new Position(old.x() + dx, old.y() + dy));
    }

    Position snapshot() {
        return current.get();
    }
}

public class AtomicSnapshotDemo {
    public static void main(String[] args) {
        Tracker tracker = new Tracker();
        Position before = tracker.snapshot();

        tracker.move(2, 3);

        System.out.println(before);
        System.out.println(tracker.snapshot());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AtomicSnapshotDemo.java
java AtomicSnapshotDemo
```

Stdout:

```text
Position[x=0, y=0]
Position[x=2, y=3]
```

The update replaces **a single reference to an immutable record**. The `before` snapshot preserves the old pair; there is no half-updated x/y state inside a Position object.

## 47. Mistake 26 — Choosing the wrong construct among mutable class, immutable class, record, or enum

Comparisons during a review:
- **Entity with an ID and mutable state** → a mutable class or intentionally designed immutable entity snapshots; do not pick a record just because it has 3 fields.
- **Value object with few components and value-based equality** → a record if deep immutability/data semantics fit.
- **Value object needing to hide an array/representation or needing custom equality** → an immutable class may be better.
- **Fixed set of symbols** → enum; avoid storing ordinal as a persistent database ID.
- **Variant types with different payloads** → sealed interface + records/final classes.
- **Resource owner with a close lifecycle** → a class with an explicit AutoCloseable; do not treat records as default resource managers.

### Closing question

"**In what ways could a new caller misuse this type even though the code compiles?**" Good language constructs should make the wrong usage harder or have the compiler reject it whenever possible.

## 48. Mistake 27 — `enum` containing mutable shared state

Enum constants are predefined instances. If:

```java
enum Mode {
    ACTIVE;
    int count;
}
```

then `Mode.ACTIVE.count` is **shared state on the constant**, not per user/request. In a multithreaded server, there is also a risk of data races.

**Good design:** Enums describe stable kinds/statuses, while per-request state lives in a separate object. If a durable external code is needed, declare a `private final String code` field and map bidirectionally; do not use `ordinal()` as a persistent ID.

## 49. Runnable: Separating enum and record into two distinct roles

Save **`EnumRoleDemo.java`**:

```java
enum Status {
    NEW, PAID
}

record OrderView(String id, Status status) { }

public class EnumRoleDemo {
    public static void main(String[] args) {
        OrderView first = new OrderView("O1", Status.NEW);
        OrderView second = new OrderView("O2", Status.PAID);

        System.out.println(first.status());
        System.out.println(second.id());
        System.out.println(first.status() == Status.NEW);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumRoleDemo.java
java EnumRoleDemo
```

Stdout:

```text
NEW
O2
true
```

`Status` represents fixed symbols; `OrderView` represents independent data values.

## 50. Mistake 28 — Visibility that is too wide or too narrow

Review:
- Which public classes/members actually need to be called by callers?
- Does a public field turn an implementation detail into an external contract?
- Is package-private sufficient for collaborating types within the package?
- Is `protected` genuinely an extension point, or just there so tests can call it?
- Do private helpers properly encapsulate invariants?
- Do Java named modules have appropriate exported packages/open reflective access?

**Remember:** `public` does not mean every module on the module path can access it when the package is not exported from a named module. `protected` has access rules tied to subclasses/packages, not "public to all subclasses regardless of context".

### A good principle

**Expose the minimal API surface needed**, then expand it when a real need arises, instead of making everything public and having to maintain compatibility forever.

## 51. Mistake 29 — `sealed` hierarchy does not match extension intent

Java 17 sealed hierarchy:
- `sealed Parent permits A, B` controls **direct** subtypes.
- A direct child class chooses `final`, `sealed`, or `non-sealed`.
- A direct subinterface of a sealed interface chooses `sealed` or `non-sealed` (interfaces cannot be final).
- `non-sealed` opens a branch to ordinary descendants; it does not automatically list all descendant classes of the root in permits.
- Records are implicitly final and can implement a sealed interface.
- In a named module, permitted direct types must be in the same module; in an unnamed module, in the same package.

**Design mistake:** wanting a "closed domain", yet marking a child `non-sealed` just to fix a compile error. That branch can then be extended unintentionally.

Choose final leaves for terminal variants, sealed intermediates for controlled subgroups, and non-sealed only when you truly want an extension point.

## 52. Runnable: Designing a closed hierarchy

Save **`SealedReviewDemo.java`**:

```java
sealed interface Result permits Success, Failure { }

record Success(String data) implements Result { }

record Failure(String reason) implements Result { }

public class SealedReviewDemo {
    static String describe(Result result) {
        if (result instanceof Success ok) {
            return "ok:" + ok.data();
        }
        if (result instanceof Failure fail) {
            return "error:" + fail.reason();
        }
        throw new IllegalStateException("unhandled");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("A")));
        System.out.println(describe(new Failure("bad")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedReviewDemo.java
java SealedReviewDemo
```

Stdout:

```text
ok:A
error:bad
```

`instanceof` pattern matching is a standard Java 17 feature. Do not use pattern matching `switch` over sealed types as a non-preview Java 17 example: that feature was not yet finalized in Java 17.

## 53. Mistake 30 — Missing error contract and side-effect ordering

If a public method:
1. Deducts money,
2. Calls a remote API,
3. Records an event,
4. Only then validates the input,

then if validation or the remote call fails, state may have been left partially modified.

**Review:**
- Validate early what can be validated.
- Design transactions/rollbacks/compensation for side effects.
- No public method should leave the object in an invariant-violating state when an exception is thrown.
- If a step fails after a mutation, is there an appropriate recovery/atomicity mechanism?
- Make naming/documentation for partial success/failure clear.
- Do not expect a Java `try/finally` block to automatically roll back database/business actions.

This is a class design flaw *at the behavior boundary*, not just exception-handling syntax.

## 54. Mistake 31 — Turning a value object into an unnecessary global singleton

A small immutable configuration/value can be shared, but do not assume that every value with identical contents must be a JVM-wide singleton object.

Use a singleton when:
- There is strictly one **service/registry** per application scope;
- Lifecycle and dependency context are clear;
- Concurrency and testing are not compromised.

Avoid singletons when:
- Data depends on user/tenant/request;
- Test cases need isolated state;
- The app has multiple environments/class loaders;
- A mutable singleton retains unrelated data across tests.

**A singleton is an ownership/lifecycle decision**, not a trick to avoid object allocation.

## 55. Mistake 32 — Using inheritance instead of a dependency/interface

A `ReportService extends DatabaseClient` is usually questionable if ReportService is not truly "a kind of DatabaseClient". It merely **uses** a database client; it is not itself a database client.

Consider instead:

```java
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
```

**Snippet:** ReportRepository must be declared in an appropriate place. This relationship is **has-a/dependency**. Constructor injection makes testing fake implementations easier and avoids exposing the entire inherited API of DatabaseClient on ReportService's public surface.

## 56. Mistake 33 — Too many boolean flags in a constructor

`new Policy(true,false,true,false)` is hard to read and easy to transpose by mistake. If the flags have domain meaning:
- Use an enum for finite choices;
- Use records holding options;
- Use named factories;
- Use a builder if there are many optional attributes;
- Split contrasting modes into separate types if they have different invariants.

For example, replace:

```java
new ExportJob(true, false);
```

with:

```java
new ExportJob(OutputFormat.CSV, Compression.NONE);
```

These are **snippets**, without full definitions of ExportJob/OutputFormat/Compression.

### Do not overuse builders

A simple `Point(int x,int y)` record does not need a 300-line builder. Builders exist to reduce ambiguity/configuration complexity, not as a quality metric on their own.

## 57. Mistake 34 — Copy/pasting an algorithm across multiple classes

When multiple classes duplicate the same validation or calculation:
- One copy gets fixed while another is forgotten.
- Business rules diverge.
- Tests fail to cover all variants.
- A change in rounding/policy becomes a production bug.

**Fix:** abstract only when the logic **truly shares the same semantics and the same reason to change**. A shared helper/service/value object may be appropriate. Do not force two algorithms from different domains into one utility just because they share a few if lines.

## 58. Mistake 35 — Unstable constants or magic values

`if (status == 3)` or `if (timeout > 5000)` does not convey meaning to the caller. A constant:

```java
private static final int MAX_RETRIES = 3;
```

can improve readability. If the set of choices is finite, an `enum` may be appropriate. If timeout measures duration, using `Duration` lets the type express the unit:

```java
private static final Duration TIMEOUT =
        Duration.ofSeconds(5);
```

**Snippet:** `java.time.Duration` requires an import or qualified name.

Avoid placing unrelated constants into a giant global `Constants` class; constants should live close to the logic that owns them.

## 59. Mistake 36 — Class/method names that do not express behavior

Names like `Data`, `Util`, `Manager`, and `Process` are not automatically wrong, but they often obscure responsibility. Review:
- Does the `save` method store to memory, disk, or remotely?
- Does `update` mutate the receiver or return a copy?
- Does `get` perform I/O, throw, or have any notable side effect?
- Does `isValid` mutate state?
- Is `close` idempotent/thread-safe, and what is its exception contract?

Prefer names consistent with the **observable contract**. Do not name a method `getBalance` if it both reads and resets the balance; do not call a method `immutableCopy` if it returns a live mutable view.

## 60. Mistake 37 — Public constructor lets callers bypass factory invariants

Sometimes a factory needs to:
- Normalize input.
- Return a cached value or subtype.
- Select an appropriate implementation.
- Return `Optional/Result` when creation fails.
- Hide the internal representation.

If both a public constructor and a factory exist, callers can bypass the normalization performed by the factory if the constructor does not validate.

**Principle:** whether using a constructor or a factory, **every successful object creation path must preserve invariants**. A factory cannot compensate for a public constructor that easily creates invalid state.

## 61. Runnable: Named factory with explicit validation

Save **`FactoryInvariantDemo.java`**:

```java
final class Email {
    private final String value;

    private Email(String value) {
        this.value = value;
    }

    static Email of(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("null");
        }
        String cleaned = raw.strip();
        if (cleaned.isBlank() || !cleaned.contains("@")) {
            throw new IllegalArgumentException("invalid email");
        }
        return new Email(cleaned);
    }

    String value() { return value; }
}

public class FactoryInvariantDemo {
    public static void main(String[] args) {
        Email email = Email.of("  a@b.test  ");
        System.out.println(email.value());

        try {
            Email.of("bad");
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FactoryInvariantDemo.java
java FactoryInvariantDemo
```

Stdout:

```text
a@b.test
invalid email
```

This is **minimal validation to illustrate a factory**, not a validator for all email addresses per Internet standards. Production requires an explicit policy and may require verification outside the application.

## 62. Mistake 38 — Throwing generic exceptions that hide context

`throw new RuntimeException("error")` everywhere makes it hard for callers to decide on recovery. Choose the appropriate exception type:
- `IllegalArgumentException` for an argument violating the contract;
- `IllegalStateException` when the receiver's state does not permit the operation;
- Checked `IOException` for I/O failures per the API;
- A custom exception if the caller needs to distinguish a domain failure (do not create them unnecessarily).

Do not throw an exception from a getter for a normal "absent" state, unless that is an explicit part of the contract. At the same time, do not return null to hide a network exception.

### Error messages

Include the invariant name or information that is safe to log, and avoid putting raw secrets into exception messages.

## 63. Mistake 39 — Failing to evaluate compatibility before changing a class

A change that looks like "cleanup" can break clients:
- Adding `final` prevents existing subclasses.
- Changing a public constructor to private.
- Converting a class to a record changes accessor names/serialization behavior.
- Changing `equals/hashCode` alters Map/Set semantics.
- Changing an enum constant name, ordinal, or external wire code.
- Changing a mutable getter to a snapshot alters behavior for code relying on a live view.
- Changing a checked exception to unchecked or vice versa.

Review a change to the **public API** by asking: "Do existing callers still compile? What about runtime/binary compatibility? Can previously persisted data still be read properly?"

Compatibility is not guaranteed just because internal unit tests are passing.

## 64. Practice — reviewing a class with multiple mistakes

Consider this anti-pattern **intentionally poorly designed snippet**:

```java
class ShoppingCart {
    public static java.util.List<String> items =
            new java.util.ArrayList<>();

    public int totalCents;

    public ShoppingCart(int total) {
        totalCents = total;
    }

    public void setTotalCents(int value) {
        totalCents = value;
    }

    public java.util.List<String> getItems() {
        return items;
    }
}
```

Problems:
1. `items` is static → all carts share the same items, contradicting the intent of per-cart isolation.
2. `items` is public mutable → any caller can mutate it without control.
3. `totalCents` is public mutable → bypasses all validation.
4. The constructor allows a negative total.
5. The setter allows a negative total.
6. `getItems` exposes the internal collection.
7. There is no `addItem` operation enforcing invariants/price rules.
8. Manually changing total can cause it to diverge from the sum of line items.
9. There is no business ID/ownership contract if the cart is an entity.
10. There are no tests for independent instances.

**Simply turning it into a record is not the answer**: if the cart must update items across a workflow, a mutable class with encapsulated operations is more appropriate.

## 65. Refactoring to a cart with clear operations

A compact design for the demo: items consist of positive unit prices in cents. The total is computed from the items, without storing a separate field that can go out of sync.

Save **`ShoppingCartRefactorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class ShoppingCart {
    private final List<Long> itemPrices = new ArrayList<>();

    void addPrice(long cents) {
        if (cents <= 0) {
            throw new IllegalArgumentException("price");
        }
        itemPrices.add(cents);
    }

    List<Long> itemPrices() {
        return List.copyOf(itemPrices);
    }

    long totalCents() {
        long total = 0;
        for (long price : itemPrices) {
            total = Math.addExact(total, price);
        }
        return total;
    }
}

public class ShoppingCartRefactorDemo {
    public static void main(String[] args) {
        ShoppingCart first = new ShoppingCart();
        ShoppingCart second = new ShoppingCart();

        first.addPrice(200);
        first.addPrice(300);
        second.addPrice(50);

        System.out.println(first.totalCents());
        System.out.println(second.totalCents());
        System.out.println(first.itemPrices());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ShoppingCartRefactorDemo.java
java ShoppingCartRefactorDemo
```

Stdout:

```text
500
50
[200, 300]
```

This class is still mutable because items change. It has no shared static list, no public total field, and does not allow callers to modify the internal list directly.

### What further improvements are needed for production?

- Replace Long prices with an immutable `CartLine(productId, quantity, unitPrice)`.
- Distinguish currencies, taxes/discounts/rounding.
- Define a business ID/aggregate lifecycle.
- Consider concurrency/transactions and pricing policy.
- Ensure callers cannot bypass rules through persistence/deserialization.

The main point is that **refactoring starts with invariants**, not with a syntax makeover.

## 66. Class design interview checklist — 12 core criteria

Score each item **0, 1, or 2**:

| # | Criterion | 0 — clear defect | 1 — needs improvement | 2 — clear and verifiable |
| --- | --- | --- | --- | --- |
| 1 | Responsibility/cohesion | Multiple unrelated tasks | Slightly blurry boundaries | One coherent purpose |
| 2 | Encapsulation/API | Public mutable internals | Minor exposure | Small surface, protects state |
| 3 | Invariants | Easy to create/mutate invalid state | Some unchecked paths | Every path preserves invariants |
| 4 | Constructors/factories | Incomplete initialization | Scattered validation | Successful creation yields a valid object |
| 5 | Mutability/ownership | Uncontrolled aliases | A few mutable boundaries | Clear owner/copy policy |
| 6 | Equality/identity | Contradictory/mutable hash | Undocumented semantics | Matches domain, with tests |
| 7 | Dependencies/coupling | Hard-coded and cyclic dependencies | Some tight coupling remains | Interfaces/composition where useful |
| 8 | Inheritance/polymorphism | Violates is-a/contract | Ambiguous extension policy | Clear substitutability |
| 9 | Error handling | Swallows errors/partial state | Incomplete diagnostics | Clear failure contract and cleanup |
| 10 | Concurrency/lifecycle | Race/resource leak | Not thoroughly tested | Strategy fits workload |
| 11 | Testability | Needs network/global state to unit test | Partially fakeable | Deterministic unit tests |
| 12 | Compatibility/docs | Fragile API, hidden contract | Missing docs/tests | Constraints/changes documented |

**Maximum total: 24 points.**

Rating scale as an *internal suggestion* (not an official Java standard):
- **21–24:** good design within the evaluated scope; integration tests and security review are still needed.
- **17–20:** fairly solid; prioritize 1–2 notable gaps.
- **12–16:** needs a clear improvement plan before expanding/exposing the public API.
- **0–11:** high risk; revisit abstractions/invariants before adding features.

**Blocking conditions (gates):** even with 22 points, do not approve if there is a critical flaw in invariants, unauthorized state mutation, data exposure, a dangerous race condition, or resource ownership. The score is a communication tool, not a replacement for severity/critical review.

## 67. How to score properly: evidence instead of gut feeling

Each score should include:
- **Source location:** specific method/constructor/field.
- **Reproduction condition:** input/call sequence causing the issue.
- **Violated invariant:** what becomes invalid?
- **Impact:** data corruption, security, concurrency, resource, maintainability.
- **Recommendation:** smallest change that protects the contract.
- **Test:** a test that fails before and passes after refactoring when feasible.

Example:
- **Not good:** "Poor design because it uses public fields."
- **Good:** "`Wallet.balance` is public, so callers can assign -1 without going through `deposit/withdraw`; the `balance>=0` invariant is broken. Recommend a private field + validated methods, and add an invalid mutation test."

The goal of a review is to establish a clear path to fix issues, avoiding subjectivity.

## 68. Scoring an example class

For the `ShoppingCart` anti-pattern above, suppose you have the following evidence:
- Responsibility: 1/2 — handles the cart but stores total separately from items.
- Encapsulation: 0/2 — public static mutable list/public total.
- Invariants: 0/2 — negative total is accepted.
- Construction: 0/2 — constructor does not validate.
- Ownership: 0/2 — list is shared application-wide.
- Equality/identity: 1/2 — no clear contract yet.
- Dependencies: 2/2 — no hard-coded external dependencies in the demo.
- Inheritance: 1/2 — open class without a clear extension contract.
- Error handling: 0/2 — does not report invalid input.
- Concurrency/lifecycle: 0/2 — mutable static ArrayList has shared races.
- Testability: 1/2 — testable, but static state leaks across tests.
- Compatibility/docs: 0/2 — no API contract.

**Illustrative total: 6/24**. This is just an example scored against the stated evidence, not a fixed score for every class named ShoppingCart.

After refactoring, **re-score based on behavior/tests**; do not raise the score merely because the class gained private/final keywords.

## 69. Quick pre-commit checklist

- [ ] Class name and primary responsibility can be described in one sentence.
- [ ] The public API exposes only what callers need.
- [ ] No public mutable fields except for a verified design reason.
- [ ] Constructors/factories produce a valid object or throw an exception.
- [ ] Does not publish `this` prematurely; does not call dangerous overridable methods in the constructor.
- [ ] Every state-changing method preserves invariants.
- [ ] Ownership of collections/arrays/references is clearly defined.
- [ ] Defensive copy of mutable input/output when the API promises an immutable snapshot.
- [ ] `final`/record/enum is not mistaken for deep immutability.
- [ ] `equals/hashCode` matches the identity/value contract.
- [ ] Hash fields are not mutated while the object is used as a Set/Map key.
- [ ] `toString`/logs do not leak secrets.
- [ ] No unintended global static mutable state.
- [ ] Has a concurrency strategy if shared mutable state is accessed by multiple threads.
- [ ] Inheritance has a clear is-a/substitution relationship; otherwise, use composition.
- [ ] Override/overload are clearly distinguished; `@Override` is used.
- [ ] Sealed/final/non-sealed extension policy matches intent.
- [ ] Generics use parameterized types, avoiding raw/unchecked code.
- [ ] Null/invalid inputs have a clear contract, without swallowing exceptions.
- [ ] Resource owners close via AutoCloseable/try-with-resources.
- [ ] ThreadLocal/listener/registry registrations are cleaned up.
- [ ] Dependencies can be faked/tested when involving I/O.
- [ ] Behavior tests cover both happy paths and boundary/failure cases.
- [ ] API/documentation/serialization compatibility is checked when refactoring.

## 70. Extended checklist for public API reviews

### API surface
- [ ] Every public/protected method has a reason to exist.
- [ ] Does not force consumers to know internal fields to perform business operations.
- [ ] Method names reflect mutation, I/O, ownership, and exception semantics.
- [ ] Package/module visibility is appropriate, without unconditionally opening packages for reflection.
- [ ] Does not tie the public API to a concrete implementation when an interface suffices.

### Construction
- [ ] Overloads do not create confusing ambiguity.
- [ ] No partially valid instance after a constructor succeeds.
- [ ] Null/empty/range/cross-field rules are validated.
- [ ] Constructor failure leaves no resource leaks.
- [ ] Does not start threads, register listeners, or publish `this` prematurely.

### State and immutability
- [ ] State can only change through a controlled API.
- [ ] Snapshots vs. live views are clearly named/documented.
- [ ] Mutable nested objects are handled to a sufficient depth.
- [ ] If records contain arrays/lists/BigDecimal, equality semantics match the domain.
- [ ] If using a final class, do not confuse final with immutable/thread-safe.

### Identity, equality, collections
- [ ] Entity ID is distinguished from object identity and value equality when needed.
- [ ] `equals` has appropriate reflexive/symmetric/transitive/consistent/null behavior.
- [ ] `hashCode` is consistent with equals and stable across usage.
- [ ] Mutable hashing keys are not used in maps.
- [ ] Enum codes use an external stable mapping, not the default ordinal.

### Behavior and error paths
- [ ] Operations are placed close to the owner of the invariant.
- [ ] Exceptions have clear types/causes, without swallowing them.
- [ ] Multi-step updates have a transaction/compensation strategy.
- [ ] Does not return success when a critical step fails.
- [ ] Cleanup runs on every exit path.

### Concurrency
- [ ] Is the object shared or thread-confined?
- [ ] Visibility and atomicity are distinct requirements.
- [ ] The locking strategy does not introduce obvious deadlocks.
- [ ] Avoids calling back into external code while holding a coarse lock whenever possible.
- [ ] Multi-field snapshots maintain appropriate consistency.
- [ ] ThreadLocal/context cleanup occurs per request/task.

### Security, operations, testing
- [ ] Does not log unnecessary secrets/PII.
- [ ] All untrusted inputs are validated at the boundary.
- [ ] Resources are not retained too long by caches/registries.
- [ ] Metrics/logging are sufficient for debugging without leaking data.
- [ ] Dependencies can be faked in unit tests.
- [ ] Negative tests and regression tests are present.
- [ ] Changes to public contracts have a migration path.

## 71. Exercise 1 — finding ways to break an invariant

```java
class Temperature {
    public int celsius;
    Temperature(int celsius) { this.celsius = celsius; }
}
```

**Prompt:** assuming a business range of `-50..100`, point out the flaws and fix them.

**Answer:** The constructor does not validate; the public mutable field lets clients bypass validation. Make the field private, and validate in the constructor and every mutating operation; if mutation is not needed, use an immutable class/record with compact validation.

## 72. Exercise 2 — aliasing through a getter

```java
class Labels {
    private final List<String> labels = new ArrayList<>();
    List<String> getLabels() { return labels; }
}
```

**Answer:** Exposes a mutable list. If the contract is a read-only snapshot, return `List.copyOf(labels)`; if callers need to mutate, define operations and test invariants.

## 73. Exercise 3 — record containing a mutable array

```java
record Token(byte[] bytes) { }
```

**Answer:** Not deeply immutable; the accessor returns the array; default equality of an array component does not compare contents. If content-based value semantics are required, use an immutable wrapper + clone + Arrays.equals/hashCode, or customize the record very carefully.

## 74. Exercise 4 — mutable map key

A class has `equals/hashCode` using `name`, yet has `setName`; the object is used as a key.

**Answer:** Risk of unstable lookups when name changes. Use an immutable name/key or a stable ID independent of mutation.

## 75. Exercise 5 — constructor calling an override

The Base constructor calls `render()`; the Child override uses a final field initializer.

**Answer:** The override can observe the default field value because Child has not yet been initialized. Remove dynamic dispatch from the constructor or design a post-construction lifecycle.

## 76. Exercise 6 — static for request data

`static String lastUserId` is placed inside a Request object.

**Answer:** State is shared; another request can overwrite it. Use an instance field or an explicit request context, and test two independent instances.

## 77. Exercise 7 — raw List

`List data = new ArrayList();` and callers add both String/Integer.

**Answer:** The raw type loses generic type safety; use `List<String> data = new ArrayList<>()` or an appropriate wildcard/abstraction.

## 78. Exercise 8 — wrong inheritance

`EmailService extends DatabaseConnection` to reuse `execute`.

**Answer:** Not an is-a relationship; use dependency/composition `EmailService(DatabaseClient client)`.

## 79. Exercise 9 — scattered validation logic

Each setter checks part of the state, yet callers must invoke them in the right order.

**Answer:** The constructor/factory accepts all required state; operations transition state as business units. Avoid invalid intermediate externally observable states.

## 80. Exercise 10 — enum ordinal stored in a database

Adding an enum constant in the middle causes old records to be read incorrectly.

**Answer:** Use a stable explicit code and a migration mapping for legacy ordinal data.

## 81. Exercise 11 — singleton polluting tests

A mutable singleton cache retains records from a previous test case.

**Answer:** Define its lifecycle and reset/eviction; better yet, inject a cache per test/service scope or use immutable settings. Do not let test execution order dictate outcomes.

## 82. Exercise 12 — resources and GC

A class closes a socket in `finalize()`.

**Answer:** Use AutoCloseable/try-with-resources with a clear owner. In Java 17, finalize has been deprecated since Java 9, and GC timing does not guarantee timely resource release.

## 83. Exercise 13 — List.copyOf with mutable elements

`record Snapshot(List<MutableOrder> orders)` uses List.copyOf.

**Answer:** It only snapshots the structure; the MutableOrder elements can still mutate. Convert them to immutable OrderView elements or apply an appropriate copy strategy.

## 84. Exercise 14 — swallowed exception

`try { send(); } catch(Exception ignored) {}` and then returning success.

**Answer:** The method reports success even though the operation may have failed. Establish a result/exception contract, retry/compensate when appropriate, and log context without exposing secrets.

## 85. Exercise 15 — object identity vs. business ID

Two `Customer` objects have the same name but different customer IDs.

**Answer:** Do not use name equality as entity identity. Consider a stable business ID/lifecycle, and avoid autogenerated equals across all mutable fields.

## 86. Exercise 16 — enum shared mutable field

`enum Flag { ACTIVE; int lastOrderId; }`.

**Answer:** lastOrderId is shared application-wide on a single enum constant; move per-order data into the order's class/record.

## 87. Exercise 17 — lock and callback

A class holds a synchronized lock and invokes arbitrary listener code.

**Answer:** Prone to deadlock/reentrancy/latency if the callback blocks or calls back into the class. Consider snapshotting listeners under the lock and invoking them outside the lock per contract; design clear concurrency boundaries.

## 88. Exercise 18 — confusing constructor overload

`new RetryPolicy(3, true, false)`.

**Answer:** The booleans are hard to understand. Use a named factory/builder or enum options with clear semantics, without overusing builders when there are only 2 simple parameters.

## 89. Exercise 19 — record DTO containing a password

`record LoginRequest(String username, String password)` is logged directly via `logger.info("{}", request)`.

**Answer:** Generated toString can expose the password. Redact/sanitize logs, avoid logging the raw request, and define a safe representation if needed.

## 90. Exercise 20 — large class

An OrderManager contains the payment client, SQL, email templates, product pricing, and receipt renderer.

**Answer:** Look at change drivers; extract collaborators by cohesive responsibility while keeping a reasonable orchestration layer. Do not create new classes merely to reduce line count.

## 91. True/False Quiz

1. Compiling code means invariants are preserved.
2. `private` fields help restrict access paths, but do not guarantee invariants on their own.
3. A `final class` cannot have mutable instance fields.
4. A `record` automatically deep-copies List/array components.
5. `List.copyOf` creates an unmodifiable shallow snapshot.
6. Overriding equals while forgetting hashCode can cause bugs in a HashSet.
7. Two instances that are equal by value always have the same reference identity.
8. Using a HashMap key with mutable hash fields is risky.
9. A `static` field belongs to each individual instance of a class.
10. `volatile count++` guarantees an atomic increment.
11. Composition is generally appropriate when the relationship is has-a.
12. Calling an overridable method in a superclass constructor can run before child initialization.
13. `@Override` lets the compiler verify override intent.
14. Using raw types provides stronger type safety than the diamond operator.
15. `try-with-resources` ensures close is called even on exception paths.
16. Java 17 `instanceof` pattern matching is stable.
17. Java 17 pattern switch on a sealed class is a standard non-preview feature by default.
18. Enum constants can hold mutable shared fields if declared in code.
19. A high checklist score is always enough to approve code even when a critical security flaw exists.
20. A good review must point out the code, the invariant, the impact, and the test.

**Answers:** 1 false; 2 true; 3 false; 4 false; 5 true; 6 true; 7 false; 8 true; 9 false; 10 false; 11 true; 12 true; 13 true; 14 false; 15 true; 16 true; 17 false; 18 true; 19 false; 20 true.

## 92. Scored self-evaluation exercise

**Prompt:** A `UserSettings` class has the following characteristics:
- `public static Map<String,String> values`.
- Constructor does not validate null.
- Getter returns the map directly.
- The `save()` method opens a file itself without closing the stream.
- `equals` compares the entire map; `hashCode` uses identity from Object.
- `toString` prints the API token as well.
- Tests only cover a single-user, single-thread case.

**Task:** Identify at least six mistakes, prioritize them, and propose solutions.

**Suggested answer:**
1. Shared static mutable map breaks user isolation (Critical).
2. Public map lets callers bypass validation (High).
3. Unvalidated null input (High if required).
4. Getter returns the internal map (High).
5. File stream is not closed (High).
6. Inconsistent equals/hashCode (High).
7. toString leaks the token (Critical security).
8. Tests lack isolation/multiple users/concurrency/failure cases (High).
9. The boundary of responsibility between storage and in-memory settings is unclear; consider extracting a repository (Medium).

**Approach:** an immutable `SettingsSnapshot` value with validated copies; a per-user owner object; an injected repository/serializer; try-with-resources; safe logging; a stable equality policy; and tests for negative/cross-user/error paths.

## 93. A 15-minute review workflow (suggested)

**Minutes 1–3: Read the API and role**
- Read the class declaration, constructors, and public methods.
- Write one sentence: "This class is responsible for ...".
- Classify it as a mutable entity/value/data carrier/resource/service/enum symbol.

**Minutes 4–7: Look for ways to break invariants**
- Public fields/setters;
- Nullable required fields;
- Aliasing via arrays/collections;
- Constructor escape;
- Multi-step state transitions.

**Minutes 8–11: Relationships and runtime**
- Identity, equals/hash;
- Inheritance/composition;
- Static/shared state;
- Concurrency/resource ownership;
- Exception paths.

**Minutes 12–15: Score and recommend**
- Score the 12 criteria 0–2;
- Call out the top 1–3 risks;
- Write a reproduction test;
- Propose a small, well-scoped refactor;
- Note compatibility risks if it is a public API.

The timing is only a guide for organizing a quick review; a security-sensitive class or core library class may require significantly longer investigation.

## 94. What is "good design" in Java?

It is not:
- Having lots of interfaces, design patterns, or getters;
- Having as few lines as possible;
- Making every class final, immutable, a record, or an enum;
- Never using static anywhere;
- Using a dependency injection framework for every constructor;
- Getting a high checklist score while lacking tests.

It usually is:
- **An understandable purpose** and coherent responsibility;
- **Invariants protected** right from construction;
- **A public API that is hard to misuse** with a clearly described contract;
- **Appropriate semantics** for identity/value/mutability/lifecycle;
- **Appropriate dependencies**, avoiding unnecessary coupling;
- **Planned failure paths and concurrency**;
- **Sufficient test evidence** for important behavior;
- **Easy to change safely** without breaking unrelated clients.

**Quality is fitness for actual requirements**, not the number of `final` or `private` keywords or the count of design patterns.

## 95. Conclusion: using the rubric to improve a class step by step

A good Java 17 class can be:
- A mutable aggregate maintaining business identity and state transitions;
- An immutable value class wrapping an array/special representation;
- A record describing value components with validation and defensive copies;
- An enum exposing finite states/codes;
- A service depending on collaborators through interfaces;
- An AutoCloseable wrapper responsible for explicit resource release.

No single choice is always right. **The most common mistake is failing to state the contract clearly and leaving callers to guess randomly.** Check what the object promises, try to break those promises with invalid inputs/aliases/overrides/concurrency, and adjust the API so invariants are preserved in the right place.

**Three final questions before approving:**

1. Can a caller create or put the object into an **invalid** state through a valid API path?
2. When code fails or runs concurrently, does the object still **uphold its contract** and clean up resources properly?
3. Can a maintainer unfamiliar with the implementation **understand, test, and modify** the class without guessing its semantics?

If all three can be answered with **code, tests, and the API contract**, the design has a trustworthy foundation.

## 96. Official Java SE 17 References

- **JLS `8 — Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- **JLS `8.10 — Record Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- **JLS `8.9 — Enum Classes**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.1.1.2 — sealed/final class modifiers**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **JLS `15.12 — Method Invocation Expressions**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12
- **Java SE 17 `Object.equals/hashCode/toString` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- **Java SE 17 `List.copyOf` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **Java SE 17 `AutoCloseable` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **Java SE 17 `AtomicReference` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- **Java SE 17 `Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
