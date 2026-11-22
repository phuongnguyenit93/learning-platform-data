# Validating Invariants After Restoring Objects in Java Serialization

## 1. Why Validate Invariants *After* Deserialization?

An **invariant** is a condition that must always hold true for a valid object throughout its lifetime. For example:

- A numeric range must satisfy `0 <= start <= end`.
- An account cannot have a `null` or blank identifier.
- A member list must have size equal to `expectedCount`; no element may be `null`.
- An appointment must have `startTime` before `endTime`.
- A graph of multiple objects must keep parent, child, and back-reference links consistent.
- Internal collections must not be externally mutated if the class contract requires immutability.

**Serialization** turns object state into a byte stream. **Deserialization** via `ObjectInputStream.readObject()` reconstructs the object from that stream. An easily overlooked fact: for classes that simply implement `Serializable`, normal restoration **does not invoke the constructor of the Serializable class itself**, so invariant checks that only exist in the constructor can be bypassed.

For example, the constructor enforces `start <= end`, yet an old stream, corrupted file, or intentionally altered stream might carry `start=20` and `end=10`. If the application accepts the data without checking, it introduces an **object in an invalid state** into system logic.

This is why Java provides validation checkpoints such as `private readObject(...)`, `ObjectInputValidation.validateObject()`, `readObjectNoData()`, along with structural strategies like **serialization proxies** and **serializable records**.

Lesson objective: know **which invariants to check, when to check them, what exception to throw, and why some checks must wait until the entire object graph is restored**.

## 2. How Does Deserialization Proceed?

For a regular Serializable class:

~~~text
ObjectInputStream.readObject()
            |
            v
Read class descriptor / state in the stream
            |
            v
Instantiate object to restore (DOES NOT call Serializable class constructor)
            |
            v
Restore fields; if private readObject exists,
run readObject and defaultReadObject/readFields if used
            |
            v
Complete the object graph currently being read
            |
            v
Run registered ObjectInputValidation (if any)
            |
            v
Return valid object to caller or throw exception
~~~

This diagram is simplified and omits full details of handles, back-references, `readResolve`, inheritance, and exceptions. Still, it highlights:

1. **Constructors guard object creation via `new`, which is insufficient for Serializable deserialization.**
2. `defaultReadObject()` restores non-static/non-transient fields by default; doing so **does not automatically invoke custom class validators**.
3. `readObject()` is the hook for checking **local state immediately after the class's fields are restored**.
4. `ObjectInputValidation` is an additional hook when checks must **wait until the entire graph has been restored** before top-level `readObject()` returns.
5. If validation fails, **reject the stream with `InvalidObjectException`** rather than silently continuing with a bad object.

### Why Isn't the Serializable Class's Constructor Called?

Java Object Serialization has a mechanism to reconstruct fields from the stream. The no-arg constructor of the **nearest superclass that does not implement Serializable** may be called per serialization rules, but the Serializable class's own constructor will not run as in a normal `new` call.

Thus the following statements:

~~~java
public Range(int start, int end) {
    if (start > end) throw new IllegalArgumentException();
    this.start = start;
    this.end = end;
}
~~~

are **illustrative code**, protecting only the constructor creation path. They do not prove every `Range` object returned by `ObjectInputStream.readObject()` is valid.

**Important exception:** Serializable **records** in Java 17 are restored via a special mechanism that invokes their **canonical constructor**; see Section 10. Do not mechanically apply ordinary Serializable class constructor rules to records.

## 3. Identify Invariants Before Choosing a Hook

Conditions to validate can be split into two groups.

| Group | Example | Appropriate Validation Site |
|---|---|---|
| **Local invariant** of a single object | `start >= 0` and `start <= end`, non-`null` ID | Inside `readObject` right after `defaultReadObject` |
| **Graph-wide / cross-object invariant** | Consistent parent-child links, member count matches total after restoration | `ObjectInputValidation` registered from `readObject` |
| **Custom-formatted input** | Two fields written explicitly in `writeObject` | Inside `readObject` after reading all custom data |
| **Old stream / missing class data** | Class was inserted into hierarchy without stream data for it | `readObjectNoData`, restore safe state or reject |
| **Immutable object with strict constructor** | Value object with final fields, defensive copies | Serialization proxy or record, depending on contract |

**Invariant scope** determines validation timing:

- Do not use a graph-wide validator to replace early **local checks**, if dangerous local state could be used while the graph is still being built.
- Do not apply a cross-object relationship check **too early** if the related objects have not finished restoring or if there are cycles/back-references.
- Both kinds must avoid triggering **irreversible side effects** while the object is not yet verified valid.

## 4. The Private readObject Hook: Checking Fields Immediately After Restoration

A Serializable class can define a method with the exact signature:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate the restored fields.
}
~~~

Essential notes:

- The method must be **private**, **non-static**, return `void`, and take `ObjectInputStream`. It is not an override of a public interface method.
- `in.defaultReadObject()` loads the class's serializable fields by name. If the class has a custom format, `readObject()` can use `readFields()` or read custom values in the exact order written.
- Inside a custom `readObject()`, **do not call both `defaultReadObject()` and `readFields()` to read the same data twice**.
- Validate after all required data is available; if invalid, throw `InvalidObjectException`.
- Do not swallow `IOException`/`ClassNotFoundException` and return an object in an uncertain state.

### Invariant Example: Non-Negative Numeric Range

~~~java
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
~~~

This is **class-level illustrative code**, requiring `import java.io.*`. The constructor guards `new` instantiation, while `readObject` guards restoring fields directly from a stream.

Why is `InvalidObjectException` better than `IllegalArgumentException`? Because it is an `ObjectStreamException`/`IOException` subclass specifically designed for when a restored object **fails validation**, letting callers clearly identify deserialization failures.

**Do not silently fix `end = start` just to mask corrupted data** unless the contract allows it. If the problem genuinely has a legacy data migration/normalization policy, define explicit conversion rules rather than turning every invalid stream into a seemingly valid object.

## 5. Why Is ObjectInputValidation Needed for Object Graphs?

In graphs with **cycles/cross-references**, reading one object's fields does not mean all referenced objects have finished establishing their state. A child may point back to a parent, or multiple parts may reference an object while it is still being deserialized.

For relationships like `parent.children.contains(child)` and `child.parent == parent`, checking inside `parent.readObject()` can be premature in certain graph shapes, or trigger dangerous secondary actions.

Java provides:

~~~java
public interface ObjectInputValidation {
    void validateObject() throws InvalidObjectException;
}
~~~

and `ObjectInputStream.registerValidation(ObjectInputValidation obj, int priority)` to register a callback **inside a class's readObject while the stream is reading the object**. The callback runs **after the object graph has been restored**, yet **before the object is returned to the caller** of the corresponding read.

Conceptual usage:

~~~java
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
~~~

This is **illustrative code**: the class must implement `Serializable, ObjectInputValidation`; `graphRelationshipIsValid()` is domain logic to implement, not a JDK API.

### Validation Priority

`registerValidation(obj, priority)` takes an integer priority:

- **Higher priorities run before** lower priorities.
- For **equal priorities**, callback order is **unspecified**.
- Use `0` when no ordering requirement exists.
- The callback may throw `InvalidObjectException`; when validation fails, reading the object fails.

**Do not design invariants relying on callback order within the same priority.** Inside one callback, check every condition it is responsible for; do not assume another callback has already patched data beforehand without an explicit dependency.

### When Can registerValidation Be Called?

Register only when `ObjectInputStream` is in the proper deserialization phase (normally from the class's `readObject`). Calling `registerValidation` outside that context can throw `NotActiveException`. If the callback object is `null`, Javadoc specifies `InvalidObjectException`.

**Do not manually invoke `validateObject()` on other classes while the graph is still assembling** to "check early" without knowing the state of related references.

## 6. Complete Java 17+ Program: Two Ways to Reject Bad Objects

This example tests:

1. `Range` performing local validation in `readObject`.
2. `Roster` validating state after the entire graph is restored via `ObjectInputValidation`.
3. Both valid and corrupted-state objects are serialized to `byte[]` and then deserialized.
4. Statements intentionally corrupting fields live only inside the **outer demo class** to synthesize test data; that is not a state-mutation pattern for production.

**File: `InvariantDemo.java`**

~~~java
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
        broken.end = 1; // Only the outer test intentionally breaks private state.
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
~~~

Run with JDK 17 or later:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

**Stdout verified on JDK:**

~~~text
range=4..9
rangeRejected=true
roster=[Ada, Bob]
rosterRejected=true
~~~

Explanation:

- `new Range(4,9)` is valid; deserialization runs `Range.readObject` and preserves the invariant, printing `4..9`.
- `broken.end = 1` is possible only because `Range` is a nested class of `InvariantDemo`; an enclosing class has access to private fields of its nested classes. This is a way to **deliberately synthesize an invalid serialized fixture in tests**, not a field setter in a production API. The constructor still checks validity, yet the serialized bytes contain altered state.
- On `load(save(broken))`, `defaultReadObject` loads `start=4`, `end=1` and the validator throws `InvalidObjectException`; the output is `rangeRejected=true`.
- A valid `Roster` has 2 names and `expectedCount=2`. Once deserialization completes the graph, `validateObject` checks count and each name, then uses `List.copyOf` for a list that cannot be modified via the List API.
- `badRoster.expectedCount=3` makes the serializable data inconsistent with the list, so the callback rejects it and prints `rosterRejected=true`.

**Demo quality note:** In this example, the `Roster` constructor only copies the list without validating each name is non-null/non-blank, keeping focus on the post-deserialization callback. **A production class must check invariants on all object creation paths**, including constructors, factories, setters or mutation APIs, and the deserialization path. A shared domain validation helper can be reused instead of duplicating rules.

### Why Not Patch Individual Bytes of a Serialized Stream to Test Invalid Cases?

Unit tests verifying invariants must supply streams containing bad state. Corrupting a private field in a fixture **in the same nest** as in this demo is more controllable than patching bytes at magic offsets in serialized binaries. Never use hardcoded offsets assuming Java Serialization's binary format for a class stays identical across versions.

## 7. Checking Nulls, Ranges, Collections, and Linked Objects

Categories of invariants often needing validation:

| Object | Invariant | Possible Stream Defect |
|---|---|---|
| `Range` | `start >= 0`, `end >= start` | Negative start, end smaller than start |
| `Account` | `accountId != null`, non-blank | Null or empty ID |
| `Order` | `items != null`, valid items | Missing field or null list |
| `Roster` | `expectedCount == names.size()` | Mismatched count |
| `Schedule` | `start.isBefore(end)` | Reversed or null timestamps |
| `GraphNode` | Matching parent-child links | Inconsistent back-reference |
| `CacheConfig` | Positive timeout, memory budget in bounds | Negative or huge field |

Checking only that the container is non-null is insufficient. You must validate **every element** as well as constraints on total counts/uniqueness:

~~~java
if (members == null) {
    throw new InvalidObjectException("members missing");
}
for (Member member : members) {
    if (member == null || member.id() == null) {
        throw new InvalidObjectException("Invalid member");
    }
}
~~~

This is illustrative code: `Member` is an application-defined type with an `id()` method, not a JDK class.

### Arithmetic Checks to Prevent Overflow

Example of a non-negative total invariant:

~~~java
long total;
try {
    total = Math.addExact(unitPrice, tax);
} catch (ArithmeticException overflow) {
    throw new InvalidObjectException("Total overflow");
}
if (unitPrice < 0 || tax < 0 || total > maxAllowed) {
    throw new InvalidObjectException("Invalid total");
}
~~~

The `long` variables are existing data from the object; this snippet is illustrative. Do not compute `int sum = a + b` and then check `sum >= 0` without accounting for **integer overflow**. With stream-supplied data, array sizes, list lengths, and nested object counts must also be bounded across multiple layers.

### Do Not Trust Derived or Cached State Fields

If a class serializes both `items` and `cachedTotal`, a stream could supply a `cachedTotal` that disagrees with `items`. Two approaches:

- **Do not serialize derived fields:** mark them `transient` and **recompute** them from source data after restoration.
- If cached metadata must be stored, **re-verify** it against actual data before use or discard the cache and recompute per policy.

Never use an unverified `cachedTotal` to allocate memory, charge fees, or grant permissions.

## 8. When Graphs Have Cycles and Aliasing

An object can be referenced multiple times in different places, and objects can form reference cycles:

~~~text
Parent P ------> Child C
     ^                |
     |                |
     +----------------+
      C.parent == P
~~~

Inside `P.readObject`, `C` might not yet be fully constructed at every point where custom code runs, especially when the graph has cycles/back-references. Hence checking `C.parent == P` or `P.children.contains(C)` is usually better suited to **`ObjectInputValidation` after graph completion** rather than an overly eager callback.

Pseudocode example:

~~~java
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
~~~

This is **non-standalone pseudocode**: `Node`, `children`, and `parent` belong to the application's own model. If using `List.copyOf(children)`, watch out for aliasing and avoid mutating the object graph into inconsistency; copying a list does not deep-clone the `Node` instances inside.

### Avoid Calling Overridable Methods on `this` During Deserialization

During `readObject`, the object may be in an incomplete state. Calling an overridable method lets a subclass run on uninitialized fields and can leak the `this` reference. Use internal validation, private/final methods with limited effects, and avoid registering `this` in global registries, dispatching events, starting threads, or invoking external callbacks before validity is confirmed.

## 9. Missing Data During Class Evolution: readFields and readObjectNoData

Serialized data may have been created by an older version of a class. In Java Serialization, `serialVersionUID` aids compatible version identification, **not automatic domain invariant enforcement**.

### 9.1. New Field Absent from the Stream

If a new version adds `requiredName` while an old stream lacks that field, default reading sets reference fields to `null` and primitives to 0/false. The program must decide whether migration is valid.

Instead of `defaultReadObject()`, you can use `ObjectInputStream.GetField`:

~~~java
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
~~~

This snippet illustrates a Serializable class with field `String name`; `readFields()` and `defaultReadObject()` are **two mutually exclusive alternatives**—do not call both to read the same data. Use `defaulted("name")` when you need to distinguish a truly absent field from a field present with a default value. `serialVersionUID` must still match your compatibility policy.

### 9.2. readObjectNoData()

A Serializable class can declare:

~~~java
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException(
            "Serialized stream lacks required class data");
}
~~~

This hook is used when a stream **lacks data for a class in the hierarchy** (for instance, compatible hierarchy changes, or an incomplete/anomalous source), which differs from a single field of the class being absent.

Some classes can re-establish valid defaults in this hook; if invariants cannot be guaranteed, **rejecting** is the right choice. Never guess values for missing security info, prices, permissions, or identifiers.

## 10. Immutable Objects: Defensive Copies, Serialization Proxies, and Records

### 10.1. Prevent Mutable Data from Breaking Invariants Later

Validating a `List` inside a validator is one step; however, if the object retains a reference to a mutable collection that another caller can modify, the invariant will be broken after deserialization.

Example:

~~~java
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (names == null || names.stream().anyMatch(
            n -> n == null || n.isBlank())) {
        throw new InvalidObjectException("Invalid names");
    }
    names = List.copyOf(names);
}
~~~

This is illustrative. `List.copyOf` returns a list unmodifiable via the List API and helps create a **defensive snapshot** of the collection. Yet **mutable elements** inside still require control: `List.copyOf` is a **shallow copy**, not a deep clone of the object graph.

For Serializable classes with `final` fields aiming to maintain strict representation invariants, mutating fields inside `readObject` is not always ideal. A serialization proxy can be chosen instead.

### 10.2. Serialization Proxy Pattern

Idea: the critical class itself is never deserialized directly. It serializes a **proxy** containing only permitted data; the proxy's `readResolve` constructs a new object **through an invariant-enforcing constructor/factory**.

~~~text
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
~~~

When following this pattern, the original class's `readObject` method typically **always throws InvalidObjectException** to forbid direct restoration of a non-proxy serialized form. The proxy's `readResolve` handles replacement; ensure all logical creation paths pass through the constructor/factory. This pattern has overhead and specific limits regarding subclasses/cycles, so apply it per domain needs rather than blindly to every class.

### 10.3. Serializable Records in Java 17

Serializable records are restored **via their canonical constructor** under a dedicated serialization mechanism. Therefore, checks in the canonical constructor can serve as a validation gate directly upon restoration.

~~~java
record Score(int value) implements Serializable {
    Score {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("Score out of range");
        }
    }
}
~~~

This is an **illustrative class snippet**, requiring `java.io.Serializable`. If domain errors should surface at deserialization level, callers must understand exceptions may be wrapped per record serialization mechanics and handle them appropriately, rather than assuming an ordinary `readObject` hook runs for records. For records, custom serialization methods like `readObject`/`writeObject` have different semantics from traditional Serializable classes; consult the record serialization specification instead of copying ordinary class templates verbatim.

## 11. Do Not Treat Invariant Validation as the Sole Security Solution

`InvalidObjectException` blocks an **invalid object state** before that object is returned to the caller. Yet it does not make deserializing untrusted bytes safe:

- **Gadget chains:** during deserialization, code of chosen types can execute **before the target class's validator completes**.
- **DoS / object bombs:** a graph can be deeply nested, contain excessive objects or huge arrays, or burn CPU before validation runs.
- **Early side effects:** `readObject` hooks on nested child classes can perform dangerous actions before `ObjectInputValidation` callbacks.
- **Class evolution:** types and fields in the stream can differ from what the application assumed, even if `serialVersionUID` passes.

**Principle:** Avoid deserializing Java native objects from untrusted sources whenever a safer data format option exists. If Java Serialization must be used, apply **`ObjectInputFilter`** to restrict classes/resources, authenticate sources, bound bytes/depth/references/arrays, and permit only audited classes. Filters help shrink the attack surface **before/during reading**, while invariant validators enforce domain rules **after fields/graphs are constructed**.

### Conceptual Filter Policy Example

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=200;maxarray=1000;" +
                "maxbytes=100000;com.example.model.*;!*");
in.setObjectInputFilter(filter);
Object obj = in.readObject();
~~~

This is **illustrative code**: `in` is an `ObjectInputStream`, `com.example.model` is just an example package, and the filter must permit **other required component types** matching the real object graph format. Do not copy a policy verbatim into production without verifying every type to be restored. Filters do not validate domain fields and do not replace `InvalidObjectException`.

### Never Return Half an Object Graph to the Caller

If a validator throws, discard the read session and byte stream per error-handling policy. Do not reuse objects temporarily placed into a global cache during restoration, as they may hold unvalidated state. Avoid registering external callbacks/events before validation succeeds.

## 12. Unit Testing Invariants in Real Environments

Testing only "serialize then deserialize with the exact current class" is insufficient; that usually exercises the **happy path** and misses constructor-bypass bugs.

A test suite should cover:

1. **Valid round-trip:** serialize then restore successfully, verifying invariants hold.
2. **Invalid numeric fields:** negative start, end less than start, reversed timestamps.
3. **Nullable fields:** null name/ID/collection, null/blank elements, missing data.
4. **Cross-field:** mismatched totals, illegally overlapping ranges, invalid enum combinations.
5. **Cross-object/cycle:** unsynchronized parent-child references or abnormal aliasing.
6. **Old-version data:** newly required field missing; `readObjectNoData` hook on hierarchy changes.
7. **Oversized object graph:** size/depth limits enforced by filter/quota without waiting for callbacks.
8. **Defensive copy:** after restoration, try mutating collections exposed by APIs and verify the object keeps its invariant.
9. **Exact exception:** expect `InvalidObjectException` (or the matching contract error) for invalid paths, rejecting silent fallbacks.
10. **Resource lifecycle:** `ObjectInputStream`/underlying streams closed properly on exception, leaking no file descriptors.

### Assertion Example Without Depending on Raw Stream Bytes

~~~java
byte[] payload = save(new Range(4, 9));
Range restored = (Range) load(payload);
// Test restored.start == 4 && restored.end == 9.

Range malformed = new Range(4, 9);
// Only test code in the same nest may deliberately change private field:
malformed.end = 1;

// Test expects load(save(malformed)) throws InvalidObjectException.
~~~

This snippet uses helpers and nested classes from `InvariantDemo` in Section 6; it is not standalone code. Never **patch bytes at magic offsets** assuming the binary serialization format stays identical across builds/versions. Use legacy-version fixtures or serialization proxy fixtures to produce malformed data sources in a controlled way.

## 13. Common Mistakes

1. **"The constructor validates, so deserialization is always safe."** False for ordinary Serializable classes; the class's own constructor does not run like `new`.
2. **"`defaultReadObject()` automatically checks all invariants."** False; it mainly restores default fields.
3. **"`readObject()` must be public so Java can call it."** False; the standard hook has a special private signature.
4. **"Just throwing `IllegalArgumentException` is enough."** `InvalidObjectException` expresses restoration data failure more clearly; callers need the right exception type.
5. **"Only check `field != null`."** Wrong if there are range, ordering, uniqueness, checksum, cardinality, or cross-object constraints.
6. **"Linked objects are always complete when `parent.readObject` runs."** Do not assume this in graphs with cycles and back-references.
7. **"`ObjectInputValidation` runs immediately upon registration."** False; the callback executes after graph restoration per contract.
8. **"Callbacks with the same priority have a fixed order."** False; ordering is unspecified.
9. **"You can call `registerValidation` at any time."** False; it may only be used during an active object-reading context.
10. **"Validating once keeps invariants forever."** False if the object has mutable fields, aliasing, and unchecked setters.
11. **"`List.copyOf` deep-clones the entire graph."** False; it is a shallow snapshot of the collection—mutable elements can still be mutated.
12. **"`serialVersionUID` is a security check."** False; it does not authenticate sources or domain data.
13. **"`ObjectInputFilter` replaces `readObject` validators."** False; filters primarily restrict object types and resources, not all inter-field relationships.
14. **"`readObjectNoData` applies whenever any field is missing."** False; it handles absent class data in a hierarchy, distinct from `GetField.defaulted`.
15. **"`readObject` on Serializable classes always calls the constructor."** False; however, Serializable records have their own restoration flow via the canonical constructor.
16. **"When validation fails, just patch the state and continue."** Without explicit migration rules, you must reject the data.
17. **"Data being deserialized can register itself into a global cache right away."** Dangerous because the object is not yet verified.
18. **"Deserializing from any source is safe as long as we catch `IOException`."** False; validation does not block gadgets/DoS occurring before the callback.

## 14. Self-Check Knowledge Questions

**Question 1:** Why can a deserialized object end up with `start > end` even though the `Range(int start, int end)` constructor validates inputs?

**Answer:** Standard `Serializable` restores fields from the byte stream without invoking the Serializable class's own constructor, so invariants must be checked in a deserialization hook.

**Question 2:** Inside `private readObject`, should `defaultReadObject()` be called before or after checking `start` and `end`?

**Answer:** Before. Fields must be restored first so you have the actual data to validate. Without a custom format, `defaultReadObject` loads the class's serializable fields.

**Question 3:** When should you use `ObjectInputValidation` instead of validating solely in `readObject`?

**Answer:** When invariants depend on the graph or other objects that may not have finished restoring while `readObject` is running. Register the validator from `readObject` to receive a callback after graph restoration.

**Question 4:** Why shouldn't priority `0` be used to order two dependent validations?

**Answer:** Java does not guarantee callback ordering for identical priorities. When dependencies exist, design explicit priority levels or combine dependent checks into one consistent point.

**Question 5:** If an old stream lacks a newly required `String name` field, how can you detect it?

**Answer:** You can use `readFields()` and `GetField.defaulted("name")`, or detect a `null` value after `defaultReadObject` per policy. Never treat `null` as valid if the field is required.

**Question 6:** Does `ObjectInputFilter` replace checking `expectedCount == names.size()`?

**Answer:** No. Filters restrict classes/graphs/resources, while domain invariants must be checked in `readObject` or `ObjectInputValidation`.

**Question 7:** An immutable object has been restored and its list validated. Does `List.copyOf` make every member inside immutable?

**Answer:** No. It creates an unmodifiable snapshot of the collection, but elements themselves may still be mutable. Deep defensive copies or immutable element types are needed if the invariant demands it.

### Official Documentation (Java 17)

- [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html)
- [ObjectInputStream: defaultReadObject, readFields, registerValidation, setObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputValidation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputValidation.html)
- [InvalidObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html)
- [Java Object Serialization Specification — Serializable Objects](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html)
- [Record Serialization (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serialization-records.html)
