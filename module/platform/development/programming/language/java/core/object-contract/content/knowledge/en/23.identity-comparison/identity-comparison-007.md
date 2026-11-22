# Value-Based Objects and Why Not to Rely on Instance Identity in Java

In Java, two reference variables can point to **two different objects** yet describe **the same value**. For *value-based* classes, the difference in which object was allocated, reused, or shared is not something a program should rely on. What matters is **the value according to the class's contract**.

This lesson falls under the **identity comparison** topic of Java Core: recognizing when value comparison must be used and why identity-based checks can break logic, synchronization locks, or data structures.

## 1. Distinguishing reference identity and value equality

Consider two object-typed references:

- `a == b`, when both operands are **references**, asks whether they point to **the exact same object** at that moment. This is identity comparison (*reference identity*).
- `a.equals(b)` asks whether they are **equal under the class's `equals` contract**. For value-based classes, this contract is based on value.
- `Objects.equals(a, b)` performs `equals` comparison with `null` handling: `true` if both are `null`, `false` if only one is `null`.
- `System.identityHashCode(a)` provides a hash code tied to reference identity, **not** a substitute for `a.hashCode()` when identifying a value.

For example, October 23, 2026 is **a calendar date value**. Two calls to `LocalDate.of(2026, 10, 23)` represent the same date, even though how the JVM represents and manages the returned objects may differ. Hence, the business question is *is it the same date?*; the right check is `equals`.

> Distinction to note: in Java 17, many value-based instances are still normal reference objects at the JVM level. The *value-based* concept does not mean every `==` is a compile error or that the class never had physical identity. It means **application code must not treat that identity as part of its value-handling contract**.

## 2. What is a value-based class?

According to Java SE 17 documentation, a value-based class has these core characteristics:

1. It is a `final` class, not designed for arbitrary subclassing; instance fields are declared `final`. Fields may reference mutable objects, so immutability must be understood according to each API's exact contract.
2. `equals`, `hashCode`, and `toString` are computed solely from appropriate value state, not from object identity.
3. The class's methods treat two instances that are equal under `equals` as **freely substitutable** (*freely substitutable*) for the behavior guaranteed by the class.
4. The class itself does not use an instance's monitor as a synchronization mechanism.
5. It provides no public constructor implying "each creation is guaranteed a new identity"; accessible constructors are absent or marked deprecated.
6. Factories do not promise to always return a new object or always return an existing object: for the same value, independent creations **may** receive the same reference or different references.

Familiar examples in Java 17 include `java.time.LocalDate`, `java.time.Instant`, `java.util.Optional`, and primitive wrapper classes such as `java.lang.Integer`. Always consult a specific class's Javadoc to confirm whether it is documented as *value-based*.

**Design consequence:** An API is allowed to substitute one instance for another with the same value without changing guaranteed behavior. API consumers should not demand a stable or unique identity per factory call.

## 3. Why can't `==` be the criterion for value?

Suppose:

```java
LocalDate first  = LocalDate.of(2026, 10, 23);
LocalDate second = LocalDate.of(2026, 10, 23);

// Correct: check for the same date value.
boolean sameDate = first.equals(second);

// Contractually wrong: relies on how the two references are represented.
boolean sameReference = (first == second);
```

The variable `sameDate` fits the problem; `sameReference` merely observes an implementation detail. You must not infer that for a value-based class, `==` is *always* `true` or *always* `false` when two values are equal.

Primitive wrapper classes also easily cause misconceptions:

```java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);
boolean equalValue = x.equals(y); // true
boolean sameObject = (x == y);    // Do not use to infer numeric equality.
```

Factories may cache or reuse instances depending on value and implementation. Observing `==` in one environment is not a guarantee for future environments or versions.

**Note on autoboxing:** `Integer a == Integer b` compares references because both sides are objects; `int a == int b` compares numeric values; `int a == Integer b` typically unboxes `b` and compares numerically, and can throw `NullPointerException` if `b` is `null`. Always examine **the actual types of both operands**, not just the `==` symbol.

## 4. Runnable Java 17 example: comparison, Set, and Map

Save the following to the file `ValueBasedDemo.java`:

```java
import java.time.LocalDate;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class ValueBasedDemo {
    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.of(2026, 10, 23);

        System.out.println("LocalDate.equals: " + first.equals(second));

        Set<LocalDate> days = new HashSet<>();
        days.add(first);
        days.add(second);
        System.out.println("Distinct day values: " + days.size());

        Map<LocalDate, String> descriptions = new HashMap<>();
        descriptions.put(first, "study day");
        System.out.println("Lookup with equal key: " + descriptions.get(second));

        Optional<String> one = Optional.of("Java");
        Optional<String> two = Optional.of("Java");
        System.out.println("Optional.equals: " + one.equals(two));

        Integer x = Integer.valueOf(1000);
        Integer y = Integer.valueOf(1000);
        System.out.println("Integer.equals: " + x.equals(y));

        System.out.println("Null-safe equals: " + Objects.equals(null, null));
    }
}
```

Run with JDK 17 or later:

```bash
javac ValueBasedDemo.java
java ValueBasedDemo
```

Standard output:

```text
LocalDate.equals: true
Distinct day values: 1
Lookup with equal key: study day
Optional.equals: true
Integer.equals: true
Null-safe equals: true
```

Explanation:

- `LocalDate.equals` checks the date; both instances represent the same date so they are equal.
- `HashSet` relies on `equals` and `hashCode`, so it does not keep two elements equivalent in date value.
- `HashMap` retrieves data using a key with a different reference that is equal under `equals` and has a matching `hashCode`.
- Two `Optional` instances containing the same string have equal `equals`; `Optional.empty()` must also be checked via APIs like `isEmpty()`, not by relying on `==`.
- `Integer.equals` expresses equality of boxed numeric values. The example intentionally avoids printing `first == second` or `x == y` because they yield no useful value conclusion.

## 5. Identity-sensitive operations to avoid

| Operation | Problem when used with value-based objects | Alternative |
| --- | --- | --- |
| `a == b` or `a != b` to compare values | Actually checks reference equality; factories do not promise allocation/reuse behavior | `a.equals(b)`, `Objects.equals(a, b)`, or domain comparison APIs |
| `System.identityHashCode(a)` as a value key | Based on identity, not the value contract | `a.hashCode()` alongside `equals()`; or use `a` directly as a `HashMap` key |
| `IdentityHashMap<ValueType, ...>` | The map uses `==` for keys so two equivalent values are not necessarily treated as one key | `HashMap` / `ConcurrentHashMap` when keys are values |
| `synchronized (value)`, `value.wait()`, `value.notify()` | Monitors belong to specific instances, easily shared unintentionally or changed across Java versions | Private `Object` lock or `java.util.concurrent` synchronization utilities |
| Using object count / allocation identity as a business signal | Cache optimizations, factories, or runtime characteristics can alter representation | Store an explicit business domain ID if entity identification is needed |

An `IdentityHashMap` can be completely appropriate when you intentionally track **the identity of ordinary objects** (for example, object-graph traversal). The problem here is using it to represent **a value-based map** for value-based classes.

Do not use `WeakReference` or instance-specific storage/tracking mechanisms to manufacture an identity guarantee for a value. Weak-reference lifecycles and value lifecycles are two different concepts; choose keys/identifiers suited to the goal.

## 6. Especially dangerous: using a value-based object as a `synchronized` lock

The code below is an **illustrative anti-pattern**, not a usage recommendation:

```java
// Suppose day is a LocalDate.
synchronized (day) {
    // Avoid synchronizing on a value-based object.
}
```

There are two opposite yet very real risks:

1. If two parties handle the same date value yet receive **different references**, they will lock **two different monitors**, failing to protect the same resource.
2. If a factory shares references, **unrelated** code may accidentally lock on the same monitor, causing contention or deadlock.

Since JDK 16, JEP 390 adds `javac` warnings for synchronizing on JDK-recognized value-based classes. You can use `-Xlint:synchronization` to request this diagnostic during review. Warnings are bug-finding tools; code emitting no warning **does not prove** its locking is correct (for instance, if the object is held in an `Object`-typed variable). Some JDKs support the runtime diagnostic option `-XX:DiagnoseSyncOnValueBasedClasses`; this is a HotSpot/JDK-dependent option, not a design solution.

When you need a monitor to protect private state, use a lock object with clear ownership:

```java
// Illustrative snippet as a member inside a state-managing class.
private final Object lock = new Object();

void updateState() {
    synchronized (lock) {
        // Read/write protected state.
    }
}
```

If you need synchronization around a shared *business* key across multiple threads, choose a concurrent data structure that manages locking/atomicity by **key value**, such as `ConcurrentHashMap.compute(...)`. Do not substitute `synchronized (LocalDate.of(...))` expecting all threads to be serialized.

## 7. Applied example: safely counting tasks by date

Scenario: callers may create `LocalDate` instances with different references but the same date; all tasks on that date must increment the same counter. The following program uses key equality and a concurrent structure:

```java
import java.time.LocalDate;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class DailyCountDemo {
    private static final ConcurrentHashMap<LocalDate, AtomicInteger> COUNTS =
            new ConcurrentHashMap<>();

    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.of(2026, 10, 23);

        COUNTS.computeIfAbsent(first, k -> new AtomicInteger()).incrementAndGet();
        COUNTS.computeIfAbsent(second, k -> new AtomicInteger()).incrementAndGet();

        System.out.println("Count: " + COUNTS.get(first).get());
        System.out.println("Distinct date keys: " + COUNTS.size());
    }
}
```

Save as `DailyCountDemo.java` and run:

```bash
javac DailyCountDemo.java
java DailyCountDemo
```

Output:

```text
Count: 2
Distinct date keys: 1
```

`computeIfAbsent` selects/stores one counter per **key value**, while `AtomicInteger.incrementAndGet()` updates the counter atomically. This is the right approach under concurrent access; there is no assumption about whether two `LocalDate.of` calls return the same object. In real applications, manage map size/lifecycle appropriately for the number of dates retained.

## 8. When is identity comparison still right?

There is no rule saying Java must eliminate `==` for objects altogether. What matters is **comparison intent**:

- For **primitives** `int`, `long`, `boolean`..., `==` is value comparison per the operator's rules.
- For **enums**, `==` is the common way to compare enum constants, because each constant is a fixed instance managed by the language.
- For **ordinary objects** with identity semantics (same entity / a graph node / a tracked instance), `==` can be a deliberate choice.
- For **value-based classes**, compare value relationships with `equals` or specialized domain APIs; do not use identity as evidence that two values are equal or unequal.
- A user-declared `record` has `equals/hashCode` based on its components, yet **does not automatically become a Java Platform value-based class** in the sense of JDK documentation. Do not equate "immutable", "record", or "value object" in domain design with the technical label *value-based class*.

When you need to distinguish *two business entities* that happen to share identical attributes (for example, two separate orders with the same total amount), store a separate entity ID; when you need to compare *a value* (a date, duration, boxed number), use the value contract. Do not derive business IDs from object addresses or identity hash codes.

## 9. Common mistakes and self-checks

**Mistake 1: "I tested locally and `==` was true."** A single execution only proves two references happened to coincide at that moment. Results can be affected by caches, factories, environments, or implementation changes. Write tests using `equals` and behavior, not `assertSame` / `assertNotSame` for value-based objects.

**Mistake 2: "Same value means `synchronized(value)` locks the same resource."** Value equality does not guarantee a shared monitor; conversely, object sharing can create unintended lock coupling. Choose private locks or concurrency utilities.

**Mistake 3: "If there's `hashCode()`, using `identityHashCode()` works too."** A value-based class's `hashCode` serves the `equals/hashCode` contract; `identityHashCode` follows identity. Do not mix these two frames of reference when using sets or maps.

**Mistake 4: "Any immutable class is JDK-declared value-based."** Immutability is one property; the value-based contract also involves factories, identity, and free substitutability. Check the Javadoc before applying the conclusion to a class.

**Code review checklist:** If logic checks `==`, chooses `IdentityHashMap` keys, uses `identityHashCode`, `synchronized` monitors, or weak references on an object representing a value, ask: *Do I truly need instance identity or do I need the value?* If you need the value, switch to `equals/hashCode` or the appropriate business API; if you need identity, pick an entity/ID with an explicit identity contract.

## 10. Summary and official references

**Principle to remember:** For value-based classes, **two instances with the same value must be treated equivalently according to the class's contract**. Whatever identity the JVM exposes in a single run is a detail you should not depend on to decide comparisons, grouping, locking, or entity identification.

Official references:

- [Java SE 17 — Value-based Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/doc-files/ValueBased.html): definition and identity-sensitive operations to avoid.
- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): emphasizes that equal instances are substitutable and not for synchronization.
- [OpenJDK JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390): warnings regarding synchronization and guidance to avoid identity dependence.