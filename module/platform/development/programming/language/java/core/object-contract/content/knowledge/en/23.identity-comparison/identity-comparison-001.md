# When the Problem Requires Distinguishing Individual Instances Even with Equal Values

## 1. The problem to solve

In Java, two reference variables can point to **two different objects** that hold **the same logical value**. Some problems only care about content: two tickets with the same code are considered equivalent. Other problems, however, must distinguish the exact **individual instance created in memory**: the first ticket has already been processed, while the second has not, even though both share the same code.

The question to ask before choosing a comparison operation is:

- **Value equality:** are two objects considered equivalent according to business rules?
- **Reference identity:** do two references point to **the exact same object**?

These are two different relationships. `equals()` can be defined to treat two different objects as equal; that does not turn them into a single instance.

## 2. Distinguishing `==`, `equals()`, and hash code

| Tool | Meaning when used with objects | When appropriate |
| --- | --- | --- |
| `a == b` | Both references point to the same object, or both are `null`. | Need to identify **the exact instance**. |
| `a.equals(b)` | Equal according to how the class implements `equals`; may throw an error if `a == null`. | Need to compare **value/business semantics**. |
| `Objects.equals(a, b)` | Compares via `equals`, handling `null` safely. | Need value equality when either reference may be `null`. |
| `a.hashCode()` | Hash code following the `equals`–`hashCode` contract; may be overridden. | Working with value-based hash structures. |
| `System.identityHashCode(a)` | Default identity-based hash code, regardless of whether the class overrides `hashCode`. | Diagnostics/identity-based algorithms; **do not** use it alone to confirm the same object. |

For **primitive types** (`int`, `double`, `boolean`...), `==` compares primitive values; this lesson focuses on **object references**. `Object.equals` defaults to identity comparison, but many classes such as `String`, wrapper classes, and `record` use value equality. Therefore, you cannot infer the meaning of `equals` while ignoring the class's contract.

Important property: if `a == b`, then a valid call `a.equals(b)` must return `true` for an `equals` implementation that follows the standard contract. The converse is **not true**: `a.equals(b)` being `true` does not mean `a == b`.

## 3. Runnable example: two instances with the same value

Create the file **`IdentityComparisonDemo.java`**:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

record Ticket(String code) {}

public class IdentityComparisonDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("T-01");
        Ticket second = new Ticket("T-01");
        Ticket alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("alias == first: " + (alias == first));

        Map<Ticket, String> byValue = new HashMap<>();
        byValue.put(first, "first");
        byValue.put(second, "second");

        Map<Ticket, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "first");
        byIdentity.put(second, "second");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("HashMap get(first): " + byValue.get(first));
        System.out.println("IdentityHashMap size: " + byIdentity.size());
        System.out.println("IdentityHashMap get(first): " + byIdentity.get(first));
        System.out.println("IdentityHashMap get(second): " + byIdentity.get(second));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac IdentityComparisonDemo.java
java IdentityComparisonDemo
```

Output:

```text
first == second: false
first.equals(second): true
alias == first: true
HashMap size: 1
HashMap get(first): second
IdentityHashMap size: 2
IdentityHashMap get(first): first
IdentityHashMap get(second): second
```

Explanation:

1. Each `new Ticket(...)` creates a separate object, so `first == second` is `false`.
2. `record Ticket` generates `equals` based on the `code` component; having the same `"T-01"` makes `first.equals(second)` `true`.
3. `alias = first` only copies **the reference**; it does not create another object.
4. `HashMap` uses the key's `hashCode` and `equals`, so the `second` key replaces the value associated with the equivalent `first` key; one entry remains.
5. `IdentityHashMap` distinguishes `first` and `second` using `==`, so it stores two independent entries.

**Takeaway:** choose `HashMap` when "same ticket code" means one logical key; choose `IdentityHashMap` when "this exact ticket object" is the key.

## 4. Scenarios where identity is the right requirement

### 4.1. Tracking each instance during processing

Suppose a processing flow receives two event objects with the same `eventCode`. The system must mark **the object already traversed in the current run**, rather than merging all objects with the same code into one. An identity-based set is suitable for recording each individual instance:

```java
Set<Event> visited =
        Collections.newSetFromMap(new IdentityHashMap<Event, Boolean>());

visited.add(eventA);
boolean alreadyVisited = visited.contains(eventB);
```

The snippet above is **an illustrative excerpt only**, assuming the `Event` class and variables `eventA`, `eventB` are already declared; `java.util.Set`, `java.util.Collections`, and `java.util.IdentityHashMap` must be imported. If the two variables point to two different instances, `contains(eventB)` is `false` even if `eventA.equals(eventB)` returns `true`. If `eventB` is an alias of `eventA`, the result is `true`.

This is especially useful when traversing **an object graph with cycles**, detecting already visited objects and avoiding infinite loops. If you use `HashSet` while nodes that are different instances have equal `equals`, the algorithm may skip valid nodes.

### 4.2. Attaching temporary state to each object

For example, a structure checker, serializer, tracer, or debugger may want to attach states like `VISITING`, `VISITED` to **each individual object**. Two objects considered equal in value can still sit at different positions in the graph, have different child references, or go through different processing states. An identity map keeps state unambiguous.

### 4.3. Managing objects used as synchronization locks

The monitor of `synchronized (lock)` is tied to **the identity of the `lock` object**. Two different lock objects do not coordinate with each other just because `lockA.equals(lockB)` returns `true`. Threads protecting the same state region must use **the same lock instance** (typically a `private final Object lock = new Object();` field shared by the exact operations needing synchronization).

Do not create a new lock object with merely the same value for each call and assume they will exclude one another. Also avoid locking on string literals or public objects that other code might unintentionally share.

### 4.4. Distinguishing live objects with the same business key

Two objects describing "customer code 123" may be two data copies in memory. If you want to compare **which customer**, use a stable business identifier and an appropriate `equals` policy. If you want to ask **which variable is referencing the same object currently being manipulated**, use `==`. Identity in the JVM is not a long-term business identifier: reloading from a database, deserializing, or receiving a copy via an API usually produces a new instance.

## 5. Decision rules## 6. Decision rules

| Question/need | Choice | Reason |
| --- | --- | --- |
| "Do two `String` values have the same content?" | `equals` or `Objects.equals` | Content is the criterion. |
| "Is this the exact object currently held in memory?" | `==` | Requires the same instance. |
| "Do two records with the same business key represent one logical entity?" | Compare ID/value per domain contract | Reference identity does not persist across loads/copies. |
| "Has this exact object node already been visited in the graph?" | Identity-based set/map | Do not merge distinct nodes just because `equals` matches. |
| "Should the map group keys with equivalent values?" | `HashMap` | Based on `equals`/`hashCode`. |
| "Must the map store separate metadata per individual object?" | `IdentityHashMap` | Based on `==` for keys. |
| "Do two operations share the same synchronization monitor?" | Check for the same lock object | Monitors have per-instance identity. |

Quick self-check question: **If another object is created with `new` using the exact same content, should the requirement treat it as a separate item?** If yes, identity is likely needed within **the lifecycle scope of those objects**. If no, prefer value equality or a business ID.

## 6. Common pitfalls

### 7.1. Using `==` for `String` or wrappers

`String` has an interning mechanism; the compiler/JVM also has mechanisms to reuse certain objects. Therefore `==` can occasionally happen to be `true` for two equal values. That **does not guarantee** two strings with the same content will be the same instance:

```java
String x = new String("java");
String y = new String("java");

System.out.println(x == y);      // false
System.out.println(x.equals(y)); // true
```

This snippet is a statement-level standalone Java excerpt (it can be placed inside `main`). Avoid inferring value equality from boxed `Integer` caching behavior or the string pool. For string content, use `equals` or `Objects.equals`.

### 7.2. Assuming `identityHashCode` is a memory address or unique ID

`System.identityHashCode(obj)` **is not a memory address**, is not a stable ID across JVM runs, and **can collide** across two different objects. Therefore:

- `System.identityHashCode(a) == System.identityHashCode(b)` **does not prove** `a == b`.
- When direct identity comparison is needed, use `a == b`; when an identity-based data structure is needed, use a structure that genuinely supports identity.

Note that `System.identityHashCode(null)` returns `0`; this number is not a unique identifier either.

### 7.3. Assuming every `equals` is value equality

If a class does not override `Object.equals`, `equals` defaults to identity; in that case `a.equals(b)` and `a == b` yield the same result when `a` is non-null. However, a class may be changed to override `equals` later. Proactively choose the operator/library that reflects **algorithmic intent**, rather than relying on a class's accidental current behavior.

### 7.4. Using `IdentityHashMap` as a universal replacement for `HashMap`

`IdentityHashMap` is a specialized structure. It uses **reference equality for both keys and values** in relevant operations; this behavior differs from ordinary `Map` implementations and can produce surprising results when comparing maps/entries against structures using `equals`. There is no iteration order guarantee. It is also **not thread-safe**, and strong references in the map can keep objects alive longer if entries are not removed when no longer needed.

`IdentityHashMap` is appropriate for object graph topology/preservation and per-instance metadata; do not use it merely to avoid designing proper `equals`/`hashCode` for business keys.

### 7.5. Assuming JVM identity survives serialization or across services

An object that is copied, deserialized, or recreated in another JVM is usually a new instance. Reference comparison is only meaningful when references observe objects within the same running JVM. To link data across runs, databases, or networks, you need a **stable ID** defined by the application.

### 7.6. Confusing identity with current state

An object can change its mutable fields while remaining **the same instance** (`a == alias` stays `true`). Conversely, two immutable records can be equal for their entire lifetime yet remain **two instances**. Do not infer identity from whether values have changed. Using mutable keys in `HashMap` also introduces risk if fields participating in `hashCode` change after insertion; that is a hashing contract issue and should be distinguished from identity.

## 7. Design and testing checklist

1. Clearly state the criterion: "equal in data", "same business identifier", or "the exact same object in memory".
2. For value equality: define/verify consistent `equals` and `hashCode`; handle `null` with `Objects.equals` when needed.
3. For reference identity: use `==`, `IdentityHashMap`, or an identity-backed set; do not substitute identity hash code comparison.
4. Test at least three cases: **same reference**, **different instances where `equals` is `true`**, and **different values**. If `null` is possible, test `null` as well.
5. Review object lifecycles, entry count retained in the map, access threads, and synchronization needs; in-memory identity does not replace external business IDs.
6. When using an object as a lock, ensure all operations that need coordination reference **the exact same lock object**.

## 8. Self-check questions

**Scenario A:** `a` and `b` are two different instances of the same `record Product("P1")`. `a.equals(b)` returns `true`. If you want to send a notification only once per product code, should you use `HashSet` or an identity set?

**Answer:** `HashSet` is appropriate because the requirement groups by code/value, assuming `Product`'s `equals` rule matches the definition of duplicate product.

**Scenario B:** An object tree analyzer must record the path through two distinct nodes with the same name, and avoid revisiting the exact same already-visited node because the graph has cycles. Which type of visited set should be used?

**Answer:** An identity set is appropriate because each node is a specific object; two nodes with the same name still need independent traversal, while revisiting the same instance must be recognized.

**Scenario C:** Do two equal `System.identityHashCode` numbers allow concluding that two references point to the same object?

**Answer:** No. Hashes can collide; to conclude the same instance in the JVM, compare with `==`.

**Remember:** "Same value" answers **under what rule objects are considered equivalent**; "same identity" answers **whether it is the exact same existing instance**. The choice lies in the problem's requirements, not in how similar two objects look.