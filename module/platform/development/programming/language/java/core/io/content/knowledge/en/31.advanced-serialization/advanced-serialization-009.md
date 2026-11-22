# Validating Invariants After Object Deserialization in Java Serialization

## 1. Why Must Invariants Be Checked *After* Deserialization?

An **invariant** is a condition that must always hold true for a valid object throughout its lifetime. Examples:

- A numeric range must satisfy `0 <= start <= end`.
- An account cannot have a `null` or blank identifier.
- A member list must have size equal to `expectedCount`, with no `null` elements.
- An appointment must have `startTime` before `endTime`.
- A multi-object graph must preserve consistent parent-child and back-reference links.
- Internal collections must not be externally mutable if the class contract requires immutability.

**Serialization** turns object state into a byte stream. **Deserialization** via `ObjectInputStream.readObject()` reconstructs objects from that stream. An easily overlooked detail: for a class merely implementing `Serializable`, normal restoration **does not invoke the Serializable class's own constructor**, so invariant checks placed solely in constructors can be bypassed.

For example, a constructor enforces `start <= end`, yet an old stream, corrupted file, or tampered stream can carry `start=20` and `end=10`. If the application accepts the data unchecked, it introduces **an object in an invalid state** into system logic.

This is why Java provides validation points such as `private readObject(...)`, `ObjectInputValidation.validateObject()`, and `readObjectNoData()`, along with structural strategies like the **serialization proxy** and **serializable record**.

Goal of this lesson: know **which invariants to check, when to check them, what exception to throw, and why certain checks must wait until the entire object graph finishes restoring**.

## 2. How Does Deserialization Proceed?

For a typical Serializable class:

```text
ObjectInputStream.readObject()
            |
            v
Read class descriptor / state from stream
            |
            v
Allocate object for restoration (does NOT call Serializable class constructor)
            |
            v
Restore fields; if private readObject exists,
execute readObject and defaultReadObject/readFields if used
            |
            v
Complete the object graph being read
            |
            v
Run registered ObjectInputValidation (if any)
            |
            v
Return valid object to caller or throw exception
```

This diagram is simplified and omits every detail of handles, back-references, `readResolve`, inheritance, and exceptions. Still, it highlights:

1. **Constructors guard objects created via `new`, which is insufficient for Serializable deserialization**.
2. `defaultReadObject()` restores non-static/non-transient fields by default rules; it **does not automatically invoke custom class validators**.
3. `readObject()` is the hook for checking **local state immediately after the class's fields are restored**.
4. `ObjectInputValidation` is an additional hook when checks must **wait until the full graph is restored** before the top-level `readObject()` returns.
5. If checks fail, **reject the stream with `InvalidObjectException`** rather than silently using a broken object.

### Why Is the Serializable Class's Constructor Not Called?

Java Object Serialization reconstructs fields from the stream directly. The no-arg constructor of the **first non-Serializable superclass** may run per serialization rules, yet the Serializable class's own constructor does not execute as in normal `new` instantiation.

Consequently, these statements:

```java
public Range(int start, int end) {
    if (start > end) throw new IllegalArgumentException();
    this.start = start;
    this.end = end;
}
```

are **illustrative code** guarding only constructor-based instantiation. They are not sufficient to prove every `Range` returned by `ObjectInputStream.readObject()` is valid.

**Important exception:** Serializable **records** in Java 17 use a specialized restoration path that invokes the **canonical constructor**; see Section 10. Do not mechanically apply normal Serializable-class constructor rules to records.

## 3. Identify Invariants Before Choosing a Hook

Conditions to check fall into two groups.

| Category | Examples | Appropriate Validation Site |
|---|---|---|
| **Local invariant** of one object | `start >= 0` and `start <= end`, non-`null` ID | Inside `readObject` immediately after `defaultReadObject` |
| **Whole-graph / cross-object invariant** | Consistent parent-child links, member count matching restored totals | `ObjectInputValidation` registered from `readObject` |
| **Custom format inputs** | Two fields written manually in `writeObject` | Inside `readObject` after reading all custom data |
| **Legacy stream / missing class data** | Class added to hierarchy while stream lacks its data | `readObjectNoData`, restoring safe state or rejecting |
| **Immutable object with strict constructor** | Value object with final fields, defensive copies | Serialization proxy or record, per contract |

**Invariant scope** determines validation timing:

- Do not use a whole-graph validator to replace every **early local check**, if dangerous local state could be used while the graph is still assembling.
- Do not run a cross-object check **too early** if related objects are not yet fully restored or involve cycles/back-references.
- Both categories must avoid **irreversible side effects** while the object has not yet been proven valid.

## 4. The private readObject Hook: Validating Fields Right After Restoration

A Serializable class can define the method with exact signature:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate the newly restored fields.
}
```

Essential notes:

- The method must be **private**, **non-static**, return `void`, and take `ObjectInputStream`. It does not override a public interface method.
- `in.defaultReadObject()` loads the class's serializable fields by name. If the class has a custom format, `readObject()` can use `readFields()` or read custom values in the exact written order.
- Inside a custom `readObject()`, **never call both `defaultReadObject()` and `readFields()` to read the same data twice**.
- Validate once all required data is available; if invalid, throw `InvalidObjectException`.
- Never swallow `IOException`/`ClassNotFoundException` and return an object in an indeterminate state.

### Invariant Example: Non-Negative Range

```java
final class Range implements Serializable {
    private static final long serialVersionUID = 1L;

    private int start;
    private int end;

    Range(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.start = start;
        this.end = end;
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (start < 0 || end < start) {
            throw new InvalidObjectException("Invalid range");
        }
    }
}
```

This is **class-level illustrative code** requiring `java.io.*` imports. The constructor guards instantiation via `new`, while `readObject` guards direct field restoration from a stream.

Why is `InvalidObjectException` better than `IllegalArgumentException`? Because it is an `ObjectStreamException`/`IOException` subclass specifically designed for when a restored object **fails validation**, letting callers clearly identify deserialization errors.

**Do not silently clamp `end = start` just to mask corrupted data** unless the contract explicitly permits it. If your domain genuinely has a legacy data migration/normalization policy, define explicit conversion rules rather than turning every invalid stream into a seemingly valid object.

## 5. Why Is ObjectInputValidation Needed for Object Graphs?

In graphs with **cycles/cross-references**, reading one object's fields does not mean every referenced object has finished initializing its state. A child may point back to a parent, or multiple parts may reference an object while it is still mid-deserialization.

For relationships like `parent.children.contains(child)` and `child.parent == parent`, checking inside `parent.readObject()` can be premature in certain graph shapes or trigger risky side effects.

Java provides:

```java
public interface ObjectInputValidation {
    void validateObject() throws InvalidObjectException;
}
```

and `ObjectInputStream.registerValidation(ObjectInputValidation obj, int priority)` to register a callback **inside a class's `readObject` while the stream is reading an object**. The callback executes **after the object graph is restored**, yet **before the object is returned to the caller** of the corresponding read.

Conceptual usage:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    in.registerValidation(this, 0);
}

@Override
public void validateObject() throws InvalidObjectException {
    if (!graphRelationshipIsValid()) {
        throw new InvalidObjectException("Inconsistent object graph");
    }
}
```

This is **illustrative code**: the class must implement `Serializable, ObjectInputValidation`; `graphRelationshipIsValid()` is domain logic you implement, not a JDK API.

### Validation Priority

`registerValidation(obj, priority)` takes an integer priority:

- **Higher priorities execute before** lower priorities.
- For **equal priorities**, callback execution order is **unspecified**.
- Use `0` when no ordering is needed.
- Callbacks may throw `InvalidObjectException`; when validation fails, reading the object fails.

**Do not design invariants relying on callback order within the same priority.** Inside each callback, check all conditions you own; do not assume another callback already repaired data beforehand unless an explicit priority dependency exists.

### When Can registerValidation Be Called?

Only register while `ObjectInputStream` is in an active deserialization phase (typically from a class's `readObject`). Calling `registerValidation` outside that context can throw `NotActiveException`. If the callback object is `null`, Javadoc specifies `InvalidObjectException`.

**Do not manually call `validateObject()` on other classes while the graph is still building** to "validate early" before referenced state is known.

## 6. Complete Java 17+ Program: Two Ways to Reject Invalid Objects

This example tests:

1. `Range` validating locally inside `readObject`.
2. `Roster` validating state after the entire graph is restored via `ObjectInputValidation`.
3. Both valid and corrupted-state objects are serialized to `byte[]` and tested through deserialization.
4. The statements intentionally corrupting fields live only in the **outer demo class** to fabricate test data; that is not a technique for mutating state in production.

**File: `InvariantDemo.java`**

```java
import java.io.*;
import java.util.*;

public class InvariantDemo {
    static final class Range implements Serializable {
        private static final long serialVersionUID = 1L;
        private int start;
        private int end;

        Range(int start, int end) {
            if (start < 0 || end < start) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.start = start;
            this.end = end;
        }

        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            if (start < 0 || end < start) {
                throw new InvalidObjectException("Invalid range");
            }
        }

        @Override
        public String toString() {
            return start + ".." + end;
        }
    }

    static final class Roster
            implements Serializable, ObjectInputValidation {
        private static final long serialVersionUID = 1L;
        private List<String> names;
        private int expectedCount;

        Roster(List<String> names) {
            this.names = new ArrayList<>(names);
            this.expectedCount = names.size();
        }

        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            in.registerValidation(this, 0);
        }

        @Override
        public void validateObject() throws InvalidObjectException {
            if (names == null || names.size() != expectedCount) {
                throw new InvalidObjectException("Invalid roster count");
            }
            for (String name : names) {
                if (name == null || name.isBlank()) {
                    throw new InvalidObjectException("Invalid roster member");
                }
            }
            names = List.copyOf(names);
        }

        @Override
        public String toString() {
            return names.toString();
        }
    }

    static byte[] save(Object object) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(object);
        }
        return bytes.toByteArray();
    }

    static Object load(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Range good = (Range) load(save(new Range(4, 9)));
        System.out.println("range=" + good);

        Range broken = new Range(4, 9);
        broken.end = 1; // Only outer test intentionally corrupts private state.
        try {
            load(save(broken));
            System.out.println("rangeRejected=false");
        } catch (InvalidObjectException expected) {
            System.out.println("rangeRejected=true");
        }

        Roster roster = (Roster) load(
                save(new Roster(List.of("Ada", "Bob"))));
        System.out.println("roster=" + roster);

        Roster badRoster = new Roster(List.of("Ada", "Bob"));
        badRoster.expectedCount = 3; // Test-only malformed state.
        try {
            load(save(badRoster));
            System.out.println("rosterRejected=false");
        } catch (InvalidObjectException expected) {
            System.out.println("rosterRejected=true");
        }
    }
}
```

Run on JDK 17 or newer:

```bash
javac InvariantDemo.java
java InvariantDemo
```

**Stdout verified on JDK:**

```text
range=4..9
rangeRejected=true
roster=[Ada, Bob]
rosterRejected=true
```

Explanation:

- `new Range(4,9)` is valid; deserialization runs `Range.readObject`, preserves the invariant, and prints `4..9`.
- `broken.end = 1` works only because `Range` is a nested class of `InvariantDemo`; the enclosing class can access private fields of a nested class. This is a way to **deliberately craft an invalid serialized fixture in tests**, not a field setter in a production API. The original constructor still validates, yet the serialized bytes hold altered state.
- On `load(save(broken))`, `defaultReadObject` loads `start=4`, `end=1` and the validator throws `InvalidObjectException`; output is `rangeRejected=true`.
- Valid `Roster` has 2 names and `expectedCount=2`. Once deserialization completes the graph, `validateObject` checks the count and each name, then applies `List.copyOf` to yield an unmodifiable list.
- `badRoster.expectedCount=3` makes the serialized data inconsistent with the list, so the callback rejects it and prints `rosterRejected=true`.

**Note on demo quality:** In the example, `Roster`'s constructor only copies the list without validating each name is non-null/blank, keeping focus on the post-deserialization callback. **A production class must enforce invariants on all object creation paths**, including constructors, factories, setters or mutation APIs, and deserialization paths. Reuse a shared domain validation helper rather than duplicating rules across sites.

### Why Not Patch Individual Bytes in the Serialized Stream to Test Invalid Data?

Unit tests verifying invariants need streams containing bad state. Corrupting a private field in a fixture **within the same nest** as shown in the demo is far more maintainable than patching magic byte offsets in a serialized binary. Never use fixed byte offsets assuming a class's Java Serialization binary layout stays identical across builds or versions.

## 7. Validating Nulls, Ranges, Collections, and Linked Objects

Common invariant groups to validate:

| Object | Invariant | Possible Error from Stream |
|---|---|---|
| `Range` | `start >= 0`, `end >= start` | Negative start, end smaller than start |
| `Account` | `accountId != null`, non-blank | Null or empty ID |
| `Order` | `items != null`, valid items | Missing field or null list |
| `Roster` | `expectedCount == names.size()` | Count mismatch |
| `Schedule` | `start.isBefore(end)` | Reversed timestamps or null |
| `GraphNode` | Consistent parent-child links | Inconsistent back-reference |
| `CacheConfig` | Positive timeout, bounded memory budget | Negative or excessive field values |

Checking only that a container is non-null is insufficient. Validate **every element** as well as aggregate count and uniqueness constraints:

```java
if (members == null) {
    throw new InvalidObjectException("members missing");
}
for (Member member : members) {
    if (member == null || member.id() == null) {
        throw new InvalidObjectException("Invalid member");
    }
}
```

This is illustrative code: `Member` is an application-defined type with an `id()` method, not a JDK class.

### Overflow-Safe Arithmetic Checks

Example of a non-negative total amount invariant:

```java
long total;
try {
    total = Math.addExact(unitPrice, tax);
} catch (ArithmeticException overflow) {
    throw new InvalidObjectException("Total overflow");
}
if (unitPrice < 0 || tax < 0 || total > maxAllowed) {
    throw new InvalidObjectException("Invalid total");
}
```

The `long` variables represent existing object data; the snippet is purely illustrative. Never compute `int sum = a + b` and check `sum >= 0` without accounting for **integer overflow**. With stream-supplied data, array sizes, list lengths, and nested object counts must also be bounded at multiple layers.

### Do Not Trust Derived or Cached State Fields

If a class serializes both `items` and `cachedTotal`, a stream could supply a `cachedTotal` that disagrees with `items`. Two approaches:

- **Do not serialize derived fields:** mark them `transient` and **recompute** them from source data after restoration.
- If cached metadata must be stored, **re-verify** it against actual data before use, or discard and recompute per policy.

Never use an unverified `cachedTotal` to allocate memory, charge payments, or grant permissions.

## 8. When Graphs Have Cycles and Aliasing

An object may reference the same instance in multiple places, and objects may form link cycles:

```text
Parent P ------> Child C
     ^                |
     |                |
     +----------------+
      C.parent == P
```

Inside `P.readObject`, `C` may not yet be fully constructed at every point where custom code runs, especially in graphs with cycles/back-references. Therefore, checking `C.parent == P` or `P.children.contains(C)` usually fits **`ObjectInputValidation` after graph completion** better than eager early checks.

Pseudocode example:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    in.registerValidation(this, 0);
}

@Override
public void validateObject() throws InvalidObjectException {
    if (children == null) {
        throw new InvalidObjectException("Missing children");
    }
    for (Node child : children) {
        if (child == null || child.parent != this) {
            throw new InvalidObjectException("Broken bidirectional link");
        }
    }
}
```

This is **non-standalone pseudocode**: `Node`, `children`, and `parent` belong to an application's custom model. When using `List.copyOf(children)`, watch out for aliasing and avoid mutating an object graph into an inconsistent state; copying the list does not deep-clone the `Node` elements inside.

### Avoid Calling Overridable Methods on `this` During Deserialization

During `readObject`, the object may be in a partially initialized state. Calling an overridable method can dispatch to a subclass touching uninitialized fields and leak `this`. Prefer internal validation using private/final methods with limited side effects, and avoid registering `this` in a global registry, dispatching events, spawning threads, or calling external callbacks before validation succeeds.

## 9. Missing Data During Class Evolution: readFields and readObjectNoData

Serialized data may have been written by an older version of a class. In Java Serialization, `serialVersionUID` helps verify version compatibility, **not automatically enforce domain invariants**.

### 9.1. New Field Absent from the Stream

If a new version adds `requiredName` that old streams lack, default reading assigns `null` to reference fields and `0`/`false` to primitives. Your program must decide whether a valid migration exists.

Instead of `defaultReadObject()`, you can use `ObjectInputStream.GetField`:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();
    if (fields.defaulted("name")) {
        throw new InvalidObjectException("Required name missing");
    }

    String name = (String) fields.get("name", null);
    if (name == null || name.isBlank()) {
        throw new InvalidObjectException("Invalid name");
    }
    this.name = name;
}
```

This snippet illustrates a Serializable class with field `String name`; `readFields()` and `defaultReadObject()` are **mutually exclusive alternatives**—never call both to load the same field data. Use `defaulted("name")` when you must distinguish a genuinely missing field from a field present with a default value. `serialVersionUID` must still align with your compatibility policy.

### 9.2. readObjectNoData()

A Serializable class can declare:

```java
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException(
            "Serialized stream lacks required class data");
}
```

This hook applies when a stream **lacks corresponding data for a class in the hierarchy** (for instance, compatible hierarchy changes, or an incomplete/anomalous source), distinct from a single field of the class being absent.

Some classes can safely re-establish valid defaults inside this hook; if invariants cannot be guaranteed, **rejecting** is the right choice. Never guess missing values for security credentials, prices, permissions, or identifiers.

## 10. Immutable Objects: Defensive Copies, Serialization Proxies, and Records

### 10.1. Prevent Mutable Data from Breaking Invariants Later

Validating a `List` inside a validator is one step; however, if the object retains a reference to a mutable collection modifiable elsewhere, invariants can break after deserialization.

Example:

```java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (names == null || names.stream().anyMatch(
            n -> n == null || n.isBlank())) {
        throw new InvalidObjectException("Invalid names");
    }
    names = List.copyOf(names);
}
```

This is illustrative. `List.copyOf` returns an unmodifiable list view/copy and produces a **defensive snapshot** of the collection. Still, **mutable elements** inside must be controlled: `List.copyOf` is a **shallow copy** and does not deep-clone the object graph.

For Serializable classes with `final` fields aiming to maintain strict representation invariants, mutating fields inside `readObject` is not always ideal. A serialization proxy can be a better fit.

### 10.2. Serialization Proxy Pattern

Idea: the critical class itself is never deserialized directly. It serializes a **proxy** holding only permitted data; the proxy's `readResolve` constructs the real object **via an invariant-enforcing constructor or factory**.

```text
Valid ValueObject
    |
    | writeReplace()
    v
SerializationProxy(data primitives / stable values)
    |
    | byte stream
    v
SerializationProxy is deserialized
    |
    | readResolve() -> new ValueObject(validated data)
    v
Valid ValueObject or InvalidObjectException
```

Under this pattern, the original class's `readObject` usually **unconditionally throws `InvalidObjectException`** to forbid restoring directly without going through the proxy. The proxy's `readResolve` supplies the replacement object, routing every logical instantiation path through the constructor/factory. This pattern adds overhead and has limitations with subclasses and cycles, so apply it thoughtfully by domain rather than blindly to every class.

### 10.3. Serializable Records in Java 17

Serializable records are restored **via their canonical constructor** under specialized serialization rules. Validation inside the canonical constructor therefore acts as a gatekeeper right at restoration time.

```java
record Score(int value) implements Serializable {
    Score {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("Score out of range");
        }
    }
}
```

This is an **illustrative class snippet** requiring `java.io.Serializable`. To return domain errors at deserialization time, callers should understand how exceptions can be wrapped by record serialization and handle them appropriately rather than assuming a regular `readObject` hook runs for records. For records, custom serialization methods like `readObject`/`writeObject` behave differently from traditional Serializable classes; consult the record serialization specification instead of copying standard-class patterns.

## 11. Never Treat Invariant Validation as Your Sole Security Solution

`InvalidObjectException` stops an **invalid object state** before it reaches the caller. However, it does not make deserializing untrusted bytes safe:

- **Gadget chains:** during deserialization, code in chosen classes can run **before the target class's validator even finishes**.
- **DoS / object bombs:** graphs can be extraordinarily deep, hold vast object counts, allocate huge arrays, or burn CPU before validation is reached.
- **Early side effects:** nested classes' `readObject` hooks can perform dangerous actions prior to `ObjectInputValidation` callbacks.
- **Class evolution:** types and fields in a stream may differ from application assumptions even when `serialVersionUID` passes.

**Principle:** Avoid deserializing Java native objects from untrusted sources whenever a safer data format is available. When Java Serialization is unavoidable, configure **`ObjectInputFilter`** to restrict classes and resources, authenticate sources, bound bytes/depth/references/arrays, and permit only audited classes. Filters shrink the attack surface **before and during reading**, whereas invariant validators guard domain rules **after fields/graphs are constructed**.

### Conceptual Filter Policy Example

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=200;maxarray=1000;" +
                "maxbytes=100000;com.example.model.*;!*");
in.setObjectInputFilter(filter);
Object obj = in.readObject();
```

This is **illustrative code**: `in` is an `ObjectInputStream`, `com.example.model` is just an example package, and the filter must allow **all other required component types** present in real object graphs. Never copy a policy straight to production without auditing the exact types restored. Filters do not verify domain fields and do not replace `InvalidObjectException`.

### Never Return Half an Object Graph to the Caller

If a validator throws an error, discard the read session and byte stream per your error-handling policy. Do not keep objects temporarily placed into a global cache during restoration, as they may hold unvalidated state. Avoid external registrations or event callbacks before validation completes.

## 12. Unit Testing Invariants in Real Environments

Testing only "serialize then deserialize with the exact current class" is insufficient; that covers only the **happy path** and misses constructor-bypass bugs.

A test suite should cover:

1. **Valid round-trip:** serialize and restore cleanly while preserving invariants.
2. **Invalid numeric fields:** negative start, end less than start, reversed timestamps.
3. **Nullable fields:** null name/ID/collection, null/blank elements, missing fields.
4. **Cross-field checks:** mismatched totals, illegally overlapping ranges, invalid enum combinations.
5. **Cross-object/cycle checks:** inconsistent parent-child links or unexpected aliasing.
6. **Legacy-version data:** newly required fields absent; `readObjectNoData` hook on hierarchy changes.
7. **Oversized object graphs:** cap size/depth via filters/quotas without waiting for callbacks.
8. **Defensive copies:** after restoration, attempt mutating collections returned by APIs and verify invariants hold.
9. **Exact exceptions:** expect `InvalidObjectException` (or the documented contract exception) on invalid paths, never silent fallbacks.
10. **Resource lifecycle:** `ObjectInputStream`/underlying streams close properly on exceptions without leaking file descriptors.

### Assertion Example Without Depending on Stream Bytes

```java
byte[] payload = save(new Range(4, 9));
Range restored = (Range) load(payload);
// Assert restored.start == 4 && restored.end == 9.

Range malformed = new Range(4, 9);
// Only test code in the same nest may deliberately change private field:
malformed.end = 1;

// Assert load(save(malformed)) throws InvalidObjectException.
```

This snippet uses the helpers and nested class from `InvariantDemo` in Section 6, not standalone code. Never **patch bytes at magic offsets** assuming the binary serialization layout remains identical across builds/versions. Use legacy-version fixtures or serialization-proxy fixtures to generate invalid inputs cleanly.

## 13. Common Mistakes

1. **"The constructor already validates, so deserialization is always safe."** False for regular Serializable classes; the class's own constructor does not run like `new`.
2. **"`defaultReadObject()` checks all invariants automatically."** False; it primarily restores default fields.
3. **"`readObject()` must be public so Java can call it."** False; the standard hook has a special `private` signature.
4. **"Just throwing `IllegalArgumentException` is enough."** `InvalidObjectException` expresses data-restoration failures clearly so callers can identify them properly.
5. **"Only checking `field != null` is enough."** False when range, ordering, uniqueness, checksum, cardinality, or cross-object rules exist.
6. **"Linked objects are always complete when `parent.readObject` runs."** Do not assume that in graphs with cycles and back-references.
7. **"`ObjectInputValidation` runs immediately upon registration."** False; callbacks run after the graph is restored per contract.
8. **"Callbacks with the same priority run in a fixed order."** False; order is not guaranteed.
9. **"You can call `registerValidation` anytime."** False; it is valid only during an active object-reading context.
10. **"Validating once preserves invariants forever."** False if the object exposes mutable fields, aliasing, or unchecked setters.
11. **"`List.copyOf` deep-clones the entire graph."** False; it is a shallow snapshot of the collection—mutable elements can still change.
12. **"`serialVersionUID` is a security check."** False; it neither authenticates sources nor validates domain data.
13. **"`ObjectInputFilter` replaces `readObject` validators."** False; filters constrain object types and resources, not cross-field domain rules.
14. **"`readObjectNoData` applies whenever a single field is missing."** False; it handles missing class data in a hierarchy, distinct from `GetField.defaulted`.
15. **"`readObject` of a Serializable class always runs a constructor."** False; though Serializable records have their own restoration path via the canonical constructor.
16. **"When validation fails, just patch the state and continue."** Without explicit migration rules, invalid data must be rejected.
17. **"Objects being deserialized can immediately register themselves in a global cache."** Dangerous because the object is not yet verified.
18. **"Deserialization from any source is safe as long as I catch `IOException`."** False; validation does not block gadgets or DoS occurring before callbacks run.

## 14. Self-Check Questions

**Question 1:** Why can a deserialized object still have `start > end` even though the `Range(int start, int end)` constructor validates its inputs?

**Answer:** Regular `Serializable` restoration populates fields from the byte stream without invoking the Serializable class's own constructor, so validation must be enforced in deserialization hooks.

**Question 2:** Inside `private readObject`, should `defaultReadObject()` be called before or after validating `start` and `end`?

**Answer:** Before. Fields must be restored first so the values exist to validate. Without a custom format, `defaultReadObject` loads the class's serializable fields.

**Question 3:** When should you use `ObjectInputValidation` instead of checking solely inside `readObject`?

**Answer:** When invariants span a graph or other objects that may still be mid-restoration while `readObject` is running. Register a validator from `readObject` to receive a callback after the graph is restored.

**Question 4:** Why should two dependent validations not share priority `0` to impose execution order?

**Answer:** Java makes no ordering guarantees among callbacks with equal priority. When ordering matters, assign deliberate priorities or consolidate dependent checks in one place.

**Question 5:** If an old stream lacks a newly required `String name` field, how can you detect it?

**Answer:** Use `readFields()` and `GetField.defaulted("name")`, or check for null after `defaultReadObject` depending on policy. Never treat null as valid when the field is mandatory.

**Question 6:** Does `ObjectInputFilter` replace checking `expectedCount == names.size()`?

**Answer:** No. Filters constrain classes/graphs/resources, while domain invariants must be checked in `readObject` or `ObjectInputValidation`.

**Question 7:** An immutable object was restored and its list validated. Does `List.copyOf` make every inner member immutable?

**Answer:** No. It creates an unmodifiable snapshot of the collection, yet elements may still be mutable. Use deep defensive copies or immutable element types when invariants require it.

### Official Documentation (Java 17)

- [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html)
- [ObjectInputStream: defaultReadObject, readFields, registerValidation, setObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputValidation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputValidation.html)
- [InvalidObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html)
- [Java Object Serialization Specification — Serializable Objects](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html)
- [Record Serialization (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serialization-records.html)
