# Distinguishing Identity Hash Code from a Unique Identifier in Java

## 1. Problem: the same object or the same code?

In Java, **object identity** answers the question "do two variables currently point to the exact same instance in the JVM?". Meanwhile, **value equality** answers the question "are two objects considered equivalent according to business rules or state?". An **identity hash code** is merely a hash number associated with object identity; it is **not a unique identifier**.

For example, two different `Person` objects may have the same name and customer code and be evaluated as equal by `equals()`; they are still two separate instances. Conversely, two variables pointing to the same instance always share the same identity, regardless of whether that instance's data changes.

## 2. Distinguishing the tools

| Tool | What question does it answer? | Key points to remember |
| --- | --- | --- |
| `a == b` (for reference variables) | Is it the same object? | Compares references; it is the direct identity check. |
| `a.equals(b)` | Are they equal under the class's rules? | May be overridden to compare values; `Object.equals()` defaults to identity. |
| `a.hashCode()` | What hash value does the class provide? | May be overridden; serves hash structures and obeys the `equals()`/`hashCode()` contract. |
| `System.identityHashCode(a)` | What is the hash code under `Object`'s default mechanism? | Ignores any `hashCode()` override; returns `int`, and can collide. |
| Business ID or storage ID | Which entity can be referenced across time/systems? | Must be designed and enforced for uniqueness, e.g., DB primary key/UUID. |

`System.identityHashCode(x)` returns the value that the default implementation of `Object.hashCode()` would return for that object, **even when the class has overridden `hashCode()`**. For `x == null`, the method returns `0`. Meanwhile, `Objects.hashCode(x)` (if used) calls `x.hashCode()` when `x` is non-null, so it does not substitute for an identity hash code.

### Important logical properties

- If `a == b`, then `System.identityHashCode(a) == System.identityHashCode(b)`.
- If two identity hash codes are **different** within the same execution, the two references cannot point to the same object.
- If two identity hash codes are **equal**, **you cannot conclude** `a == b`: different objects can still experience hash collisions (*collision*).
- If `a.equals(b)` is `true`, the `hashCode()` contract requires `a.hashCode() == b.hashCode()`, but **does not require** their identity hash codes to be equal.
- `a.hashCode() == b.hashCode()` is not enough to conclude `a.equals(b)` or `a == b`.

An identity hash code has type `int` (32 bits, at most `2^32` bit patterns), so it cannot guarantee a distinct value for every object in all situations. The Java specification only aims for distinct instances to receive distinct hash codes **to the extent reasonably practical**, without promising zero collisions. This number must not be treated as a memory address, object creation sequence number, or durable ID: the JVM may choose how to compute it, GC may move objects, and values have no stability guarantee across runs or across JVMs.

## 3. Runnable example with Java 17+

The `Ticket` class intentionally defines equality by `code`, so two different instances still compare equal via `equals()`. We contrast `HashMap` (relying on `equals()`/`hashCode()`) with `IdentityHashMap` (relying on `==` and identity hash code).

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashCodeDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Ticket ticket && code.equals(ticket.code));
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("T-01");
        Ticket second = new Ticket("T-01");
        Ticket alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first == alias: " + (first == alias));
        System.out.println("value hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("alias identity hashes equal: "
                + (System.identityHashCode(first) == System.identityHashCode(alias)));

        Map<Ticket, String> byValue = new HashMap<>();
        byValue.put(first, "one");
        byValue.put(second, "two");

        Map<Ticket, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "one");
        byIdentity.put(second, "two");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("IdentityHashMap size: " + byIdentity.size());
        System.out.println("identityHashCode(null): " + System.identityHashCode(null));
    }
}
```

Save the file as `IdentityHashCodeDemo.java`, compile, and run:

```bash
javac -encoding UTF-8 IdentityHashCodeDemo.java
java IdentityHashCodeDemo
```

Deterministic output:

```text
first == second: false
first.equals(second): true
first == alias: true
value hashes equal: true
alias identity hashes equal: true
HashMap size: 1
IdentityHashMap size: 2
identityHashCode(null): 0
```

**Explanation:** `first` and `second` are two different objects despite having the same `code`; hence `==` returns `false` while `equals()` returns `true`. The two variables `first`/`alias` point to the same object, so their identity hash codes are equal. `HashMap` merges the two value-equivalent keys into one entry; `IdentityHashMap` keeps both keys because their references differ. **The example intentionally neither prints nor assumes** that `System.identityHashCode(first)` differs from `System.identityHashCode(second)`; such an assumption would fail on a collision.

## 4. Why can't a hash prove uniqueness?

A hash function maps a vast set of possible objects into a finite set of numeric values. The fact that a code looks random or rarely collides does not make it unique. Both `HashMap` and `IdentityHashMap` must handle keys with the same hash: the hash locates a bucket/slot, while the key comparison confirms which key is the target. In particular, `IdentityHashMap` uses **reference** comparison even if two keys share the same identity hash code.

Do not write identity conditions like `System.identityHashCode(a) == System.identityHashCode(b)`; use `a == b`. Also do not store identity hash codes as database primary keys, cross-run cache keys, user-visible IDs, long-term audit log trace codes, or IDs passed between services.

### Is `ClassName@hex` in logs a unique ID?

No. The default implementation of `Object.toString()` concatenates the class name, `@`, and the hex representation of `hashCode()`. That hex part is a **hash code**, not a uniqueness guarantee; if a class overrides `hashCode()` without overriding `toString()`, the hex part even reflects the overridden `hashCode()` method. A string like `Ticket@1a2b3c` is insufficient to uniquely identify an object system-wide.

## 5. When to use what?

| Need | Appropriate approach |
| --- | --- |
| Check whether two variables currently point to the exact same instance | `a == b` |
| Check whether two values/entities are business-equivalent | Implement consistent `equals()` and `hashCode()`; use `Objects.equals(a, b)` when `null`-safety is needed. |
| Group and look up by value | `HashMap`, `HashSet` with the `equals()`/`hashCode()` contract. |
| Track nodes in an object graph, handle aliases/cycles per instance | `IdentityHashMap` or `Collections.newSetFromMap(new IdentityHashMap<>())`. |
| Attach a diagnostic hash label to a live object | `System.identityHashCode(obj)`, typically alongside run context and `==` checks when needed. |
| Identify entities across restarts, DB, or network | Durably stored business ID; e.g., DB primary key with `UNIQUE`/`PRIMARY KEY` constraint, or an issued and managed UUID. |

`UUID.randomUUID()` generates random UUIDs with an extremely low collision probability in practice, **not a mathematical proof that collisions can never happen**. If business rules require strict uniqueness, enforce a uniqueness constraint in storage and handle conflicts. Two different Java objects representing the same database record can carry **the same business ID** while still having `a != b` under reference comparison.

## 6. Common mistakes and how to avoid them

1. **Confusing identity hash code with a memory address.** Java does not promise the hash code is an address, nor that an object's address stays fixed under GC.
2. **Using matching hashes to conclude the same object.** Collisions are valid; use `==` to check identity.
3. **Using `hashCode()` for long-term identification.** Overrides, new runs, and collisions all make hash codes unsuitable as durable IDs.
4. **Comparing objects with equal data using `==`.** `==` can return `false` even when `equals()` returns `true`; pick the comparison matching your goal.
5. **Assuming every distinct object has a distinct identity hash.** No such guarantee exists; `IdentityHashMap` keeps separate keys thanks to reference checks.
6. **Misusing `IdentityHashMap` for business data.** This map intentionally uses identity instead of value equality, so results can be counterintuitive when queried with `equals`-equal keys.

## 7. Self-check

- Can two variables with the same reference have different identity hash codes in one run? **No**.
- Can two different instances have colliding identity hash codes? **Yes**, because hash codes can collide.
- Can two objects that are equal under `equals()` have different identity hash codes? **Yes**.
- Should `System.identityHashCode()` be used as a unique order ID? **No**; use an ID issued and uniqueness-validated by the storage system.

**Remember:** *Identity* is confirmed by having the same reference (`==`); *identity hash code* is a hash number supporting identity-based mechanisms; a *unique identifier* is an identifier defined and maintained by system design.

## References

- [Java SE 17 — `System.identityHashCode(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))
- [Java SE 17 — `Object.hashCode()` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode())
- [Java SE 17 — `IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)