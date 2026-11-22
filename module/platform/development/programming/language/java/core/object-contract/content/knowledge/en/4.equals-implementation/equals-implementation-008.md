# Do Not Mutate State or Depend on Time in `equals()`

## 1. Goal When Implementing `equals()`

When overriding `Object.equals(Object)`, treat this method as an **observation of the equality relation** between two objects: read the information needed for comparison, compute, and return a `boolean`. Calling `equals()` should not mutate observable state of the object or the system; the result should also not depend on the current time, call count, or external side factors unrelated to the values being compared.

This is closely tied to **consistency** in the `equals` contract: for two non-`null` references `x` and `y`, repeated calls to `x.equals(y)` must return the same `true` or the same `false`, **provided no information used in the comparison on the objects is modified**.

Three things must be distinguished:

1. **Contract requirement:** The conditional consistency stated above is a formal requirement of `Object.equals`. Reflexivity, symmetry, transitivity, and behavior with `null` must also be preserved.
2. **Design principle:** Avoiding side effects in `equals` is a strong practice to keep APIs safe and predictable; Java has no special statement that automatically forbids every side effect inside a method.
3. **Data stability:** If a field **used for comparison** actually changes, the result of `equals` can change with that field without automatically violating the conditional consistency statement. However, using an object with a mutable equality key in `HashMap`/`HashSet` very easily breaks lookups.

The lesson emphasizes two sources of risk to avoid: **`equals()` mutating state itself** and **`equals()` depending on time**.

## 2. Why Shouldn't `equals()` Have Side Effects?

A *side effect* is an action beyond producing the return value, such as:

- Incrementing a counter inside the object, flipping a `visited` flag, or updating `lastCheckedAt`.
- Writing or removing elements in a collection, mutating an observable cache, updating a database, sending notifications, or calling a write-capable API.
- Mutating shared (`static`) state, global variables, `ThreadLocal`, or the state of the other object being compared.

Even a side effect that does not immediately change the `equals` result causes surprises: reading data via `contains`, `remove`, `get`, or an equality check can end up modifying data. If the side effect impacts fields participating in `equals`/`hashCode`, subsequent calls can yield different results, or keys in hash structures can become unreachable as expected.

Example **not to write**:

```java
@Override
public boolean equals(Object other) {
    comparisons++; // Side effect: each comparison mutates state.
    if (this == other) {
        return true;
    }
    if (!(other instanceof Customer that)) {
        return false;
    }
    return id == that.id;
}
```

This is an **illustrative code snippet** residing in a class with fields `comparisons` and `id`, not a standalone compilable program. The `comparisons` field might not participate in the comparison, so the code *does not necessarily* violate formal consistency. Still, having `equals` increment `comparisons` remains a design that is hard to use safely; do not place business logic, write operations, or equality conditions based on comparison counts here.

If system metrics are needed, collect them at the caller layer or an external observability system; do not turn `equals` into a write operation on a value object.

## 3. Why Must Current Time Not Be Used to Decide Equality?

Implementations using `System.currentTimeMillis()`, `Instant.now()`, expiration timestamps, today/tomorrow, or a changing timer cause **the exact same two objects with the exact same data** to be considered equal at one moment and different at another.

Conceptually wrong example:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof SessionKey that)) {
        return false;
    }
    return token.equals(that.token)
            && System.currentTimeMillis() < expiresAtMillis
            && System.currentTimeMillis() < that.expiresAtMillis;
}
```

This is an **illustrative snippet** assuming fields `token` and `expiresAtMillis` in class `SessionKey`. With unchanged data, the result flips from `true` to `false` when time crosses the expiration boundary. The implementation also reads the clock twice, so the two reads can skew right on the boundary. Do not make *whether something is still valid* part of logical identity in `equals`.

Instead:

- Use `equals` to compare **stable identity/value**, such as `token` or the tuple `(tenantId, sessionId)`.
- Separate the time condition into a dedicated method like `isExpired(Clock clock)` or `isValidAt(Instant now)`. Time is an **explicit input** to the validity check.
- When comparing a point in time that is a **stored attribute value** (for example, a saved and immutable `createdAt`), comparing `createdAt` of two objects is completely different from querying `Instant.now()` inside `equals`. An immutable timestamp value can be part of equality if the domain model truly requires it.

Strictly speaking, `Object.equals`'s consistency statement is conditioned on the information used for comparison not changing. An external running clock changes the computed information; that is precisely why **equality must not be designed to depend on a clock**, even if arguing solely from contract wording is not enough to conclude every time-using example violates a specific clause.

## 4. Complete Example, Runnable with Java 17

The example has three object types:

- `StableKey`: compares based on `final` fields and produces no side effects.
- `CountingKey`: calling `equals` increments a counter inside the object (an example **not to use**).
- `TimedKey`: comparison depends on a simulated clock, allowing verification that the equality result changes over time without actually waiting.

Create the file **`EqualsPurityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class EqualsPurityDemo {
    static final class StableKey {
        private final String tenant;
        private final long id;

        StableKey(String tenant, long id) {
            this.tenant = tenant;
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof StableKey that)) {
                return false;
            }
            return id == that.id
                    && Objects.equals(tenant, that.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, id);
        }
    }

    static final class CountingKey {
        private final String code;
        private int comparisons;

        CountingKey(String code) {
            this.code = code;
        }

        int comparisonCount() {
            return comparisons;
        }

        @Override
        public boolean equals(Object other) {
            comparisons++; // DO NOT DO THIS: equals has a side effect.
            if (this == other) {
                return true;
            }
            if (!(other instanceof CountingKey that)) {
                return false;
            }
            return Objects.equals(code, that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    static final class TimedKey {
        private final String code;
        private final LongSupplier currentMillis;

        TimedKey(String code, LongSupplier currentMillis) {
            this.code = code;
            this.currentMillis = currentMillis;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof TimedKey that)) {
                return false;
            }
            return Objects.equals(code, that.code)
                    && currentMillis.getAsLong() < 1_000
                    && that.currentMillis.getAsLong() < 1_000;
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    public static void main(String[] args) {
        StableKey first = new StableKey("acme", 42);
        StableKey second = new StableKey("acme", 42);
        System.out.println("stable #1: " + first.equals(second));
        System.out.println("stable #2: " + first.equals(second));
        System.out.println("stable hash matches: "
                + (first.hashCode() == second.hashCode()));

        CountingKey counted = new CountingKey("A");
        System.out.println("count before: " + counted.comparisonCount());
        System.out.println("counted.equals(counted): "
                + counted.equals(counted));
        System.out.println("count after: " + counted.comparisonCount());

        AtomicLong fakeMillis = new AtomicLong(500);
        TimedKey left = new TimedKey("K", fakeMillis::get);
        TimedKey right = new TimedKey("K", fakeMillis::get);

        System.out.println("timed at 500: " + left.equals(right));

        Map<TimedKey, String> map = new HashMap<>();
        map.put(left, "found");
        System.out.println("map lookup at 500: " + map.get(right));

        fakeMillis.set(1_500);
        System.out.println("timed at 1500: " + left.equals(right));
        System.out.println("map lookup at 1500: " + map.get(right));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac --release 17 EqualsPurityDemo.java
java EqualsPurityDemo
```

Standard output (independent of wall-clock time because a fake clock was used):

```text
stable #1: true
stable #2: true
stable hash matches: true
count before: 0
counted.equals(counted): true
count after: 1
timed at 500: true
map lookup at 500: found
timed at 1500: false
map lookup at 1500: null
```

Explanation:

1. Two `StableKey` instances with the same `tenant` and `id` give a stable `true` result. `hashCode` is also based on these exact fields, ensuring objects considered equal have the same hash code.
2. `CountingKey.equals(counted)` returns `true` (reflexivity still holds) but increments `comparisons` from `0` to `1`. Thus **returning the right result does not mean the method has no side effects**.
3. `TimedKey` compares both `code` and the condition `currentMillis < 1_000`. When the fake clock moves from `500` to `1_500` without any field on either object being modified, `left.equals(right)` changes from `true` to `false`.
4. In this example, `HashMap` has `left` inserted as a key and uses `right` for lookup. At `500`, `right` is considered equal to `left`, so the value is found; at `1_500`, it is no longer considered equal, so the result is `null`. The hash code here remains the same; **the equality relation itself changing with the clock** causes the lookup result to change.
5. `left.equals(left)` is still `true` thanks to the `this == other` branch: this time-based example preserves reflexivity yet exposes **another** risk, where the comparison result between two objects changes over time. Passing one clause must not be equated with a reliable `equals` design.

`TimedKey` and `CountingKey` are only meant to demonstrate practices to avoid, not recommended implementations in application code.

## 5. Impact on `HashMap`, `HashSet`, and Other APIs

A `HashMap` uses `hashCode` to select a hash bucket and `equals` to determine equivalent keys when needed. `HashSet` relies on a similar idea. If `equals` depends on changing state, the following can occur:

- Inserting a key and later failing to find an equivalent key even though the entry was never actively removed.
- `contains`, `get`, and `remove` giving unexpected results at different times.
- Read operations becoming coupled with side effects: one comparison can alter data used by subsequent lookups.

Distinguish **stability of `equals`** from **stability of `hashCode`**. The two methods must align: when `a.equals(b)` is `true`, `a.hashCode() == b.hashCode()` must also be `true`. Yet having a stable `hashCode` alone still cannot save a clock-dependent `equals`, as shown in the `TimedKey` example.

For keys of `HashMap`/`HashSet`, the best practice is to use **immutable** identity attributes and use the same criteria in `equals`/`hashCode`. For objects with mutable data, be cautious when putting changeable fields into equality, especially after the object has been used as a key.

## 6. Proper Design: Separating Equality from Operational State

A class storing a token and an expiration timestamp may need both the concept of “same token” and “token still valid”. These two questions should have separate APIs.

Java 17 **illustrative code snippet** (`import` declarations must be added when placed in a standalone file):

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class SessionToken {
    private final String tokenId;
    private final Instant expiresAt;

    SessionToken(String tokenId, Instant expiresAt) {
        this.tokenId = Objects.requireNonNull(tokenId);
        this.expiresAt = Objects.requireNonNull(expiresAt);
    }

    boolean isExpired(Clock clock) {
        return !Instant.now(clock).isBefore(expiresAt);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SessionToken that)) {
            return false;
        }
        return tokenId.equals(that.tokenId);
    }

    @Override
    public int hashCode() {
        return tokenId.hashCode();
    }
}
```

In this example model, **equality is defined by `tokenId`**; `expiresAt` is not part of identity, so it does not appear in `equals`/`hashCode`. This is a business choice for the example, not a mandatory rule for every token. If the domain defines two token values as different when `expiresAt` differs, you can include the **stored `expiresAt` value** in both `equals` and `hashCode`, provided they are stable; still do not query the current clock inside `equals`.

The `isExpired(Clock clock)` method receives an explicit time source, easy to test with `Clock.fixed(...)`. Validity time can change over time, matching this method's responsibility; that change does not silently alter the key's equality relation.

Another choice for a value object containing only immutable data is a **Java record**:

```java
record CustomerKey(String tenantId, long customerId) {}
```

Java generates `equals`/`hashCode` based on the record components. This example works well because `String` and `long` are stable. However, **a record does not make every reference component deeply immutable**: if it contains an array or mutable object, you must still review the equality semantics and data stability.

## 7. Subtle Bugs to Avoid

### 7.1. Automatically normalizing data by assigning fields inside `equals`

Wrong approach: when comparing names, calling a setter to lowercase or trim `name` directly on the object. That turns `equals` into a data-mutating operation; if the field is used in `hashCode`, the hash code can also change.

Better approach: normalize in the constructor or at the data entry boundary, or compare using a local normalized result without writing back to the field. If normalization is locale-dependent, choose a clear rule suitable for the domain; do not rely on a mutable global default locale unintentionally.

### 7.2. Lazy initialization modifying fields participating in equality

For example, `equals` calls a getter that lazily initializes by updating an ID or timestamp. The first comparison can affect subsequent ones. Establish identity before using it in comparisons and ensure reading values does not itself alter the meaning of identity.

Not every internal cache necessarily breaks the contract, but it increases difficulty around side effects and thread safety. For foundational code, prefer a pure read-only comparison.

### 7.3. Depending on external values: random, configuration, database

Do not use the result of `Random.nextBoolean()`, configuration versions, network, current permissions, or database query results to decide whether two already created objects are equal. Those sources can change between two calls and turn a value check into operational state.

### 7.4. Mutable fields in an object currently used as a key

If `equals`/`hashCode` relies on a mutable field, after putting the object into a `HashMap`, mutating the field can cause lookups to fail. This is a problem even when `equals` **does not mutate** that field itself. Therefore, consider both **method side effects** and **immutability of the attributes used in comparison**.

### 7.5. Concurrency

An `equals` implementation reading multiple mutable fields while another thread modifies them can observe an inconsistent combination of data. Declaring `final` and designing immutable value objects simplifies this. If an object truly must be mutable, an appropriate synchronization/snapshot strategy is needed for the business requirements; merely adding `volatile` to individual fields does not automatically provide a consistent snapshot across multiple fields.

## 8. Checks During Review and Testing

For the same two objects whose comparison data does not change, you can test:

1. Call `a.equals(b)` multiple times and compare results; simultaneously check `a.equals(a)`, `a.equals(null)`, and the related equality clauses.
2. Snapshot the observable state of `a` and `b` before/after the call; ensure no field was modified unintentionally. Pay special attention to getters with lazy writes.
3. When the design has a `Clock`, fake clock, or time boundary tests, advance the time while **keeping identity data unchanged**; the `equals` result should not change.
4. If the class is used as a key, test `HashMap.put` then `get` with an equivalent object; re-run after operations that are not supposed to alter identity.
5. Check that `hashCode` always matches the fields `equals` uses, and key data does not change while residing in a hash structure.

Note: testing a few sample values does not prove every property absolutely. You also need to inspect the code paths to detect state writes, clock calls, or dependencies on external services.

## 9. Summary of Key Takeaways

- `equals` should be a **read-only operation with predictable results**; do not mutate the receiver object, the other object, or system state.
- Per the `Object.equals` contract, repeated comparisons must be consistent **when the information used for comparison does not change**.
- Do not use `Instant.now()`, `System.currentTimeMillis()`, randomness, call counts, or external service state to determine equality.
- “Do two values share the same identity?” and “Is that value still valid at this point in time?” are **two different responsibilities**; separate `equals` and time-checking methods.
- Use stable identity fields, and keep `equals`/`hashCode` criteria consistent, especially for keys in `HashMap`/`HashSet`.