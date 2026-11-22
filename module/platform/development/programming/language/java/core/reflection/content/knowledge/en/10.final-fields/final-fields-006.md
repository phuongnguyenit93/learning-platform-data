# Do Not Treat Field Mutation as a Substitute for Constructors and Object Immutability

## 1. Nature of the Problem

In Java Reflection, `Field` lets you observe field metadata and, in permitted cases, modify a value with `Field.set(Object, Object)`. However, **writing a field after an object has already been created is not equivalent to initializing the object through a constructor**. A constructor is where data validation rules, normalization, defensive copying, and establishing a consistent state are centralized before the object is published for use.

Imagine an order with `amountCents >= 0`, a non-empty order ID, and a fixed list of products. If someone uses Reflection to write `amountCents = -100` directly onto an already-constructed object, they can violate the invariant even though the field is declared `private final`. If the internal list is modified without going through validation, related rules may also cease to hold.

This lesson answers practical questions:

- What guarantees does a constructor establish that `Field.set(...)` does not automatically provide?
- Does `final` mean complete immutability? Under what circumstances can a final field be modified via Reflection?
- Why does "calling Reflection successfully" not prove an object is validly initialized or safe across multiple threads?
- How should data be changed while still preserving invariants?

**Working principle:** create valid objects via constructors/factories/builders, then use controlled APIs for permitted state changes; for immutable objects, create a **new instance** instead of intervening in old fields.

## 2. Three Concepts to Distinguish

### 2.1. Constructors establish invariants

An **invariant** is a condition that every object in a valid usable state must satisfy. For example, for `Receipt`:

- `orderId` must not be `null` or empty.
- `totalCents` must be non-negative.
- `items` must contain at least one item.
- The item list must not be altered unintentionally after the object is created.

The constructor can check all these conditions **before returning the object to the caller**. Afterward, methods or factories of the class can maintain the same rules when data needs to change.

### 2.2. `final` protects variable/field assignment, not automatically the entire object graph

For `private final int totalCents`, ordinary Java requires the field to be assigned during valid initialization and prevents ordinary Java methods from reassigning it later.

For `private final List<String> items`, `final` **only fixes the reference** to the `List` object; it does not automatically lock the contents of the list. If an `ArrayList` is accepted from a caller and kept as the exact same reference, the caller can still add/remove elements even though the field holding it is `final`.

Object-level immutability also requires: not exposing mutable references, defensive copying on input/output, validating all input data, and ensuring no update method breaks invariants.

### 2.3. `Field.set` is a low-level operation on state

`Field.set(receiver, value)` checks field metadata, receiver, access permissions, and value/type assignability. It **does not re-invoke the receiver's constructor**, does not automatically apply business rules, does not trigger custom validators, and does not perform defensive copying as intended by the class design.

Even when a write is accepted by Java Reflection, the new value may still render the object invalid according to the domain. Thus, *technical manipulability* does not mean *valid modification under the object model*.

## 3. Java 17+ Program: Preserving Invariants with Constructors and Creating New Instances

Save the following code into **`FinalFieldGuidanceDemo.java`**. This is a standalone program using only the Java standard library:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;

public class FinalFieldGuidanceDemo {
    static final class Receipt {
        private final String orderId;
        private final List<String> items;
        private final int totalCents;

        Receipt(String orderId, List<String> items, int totalCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            if (items == null || items.isEmpty()) {
                throw new IllegalArgumentException("items must not be empty");
            }
            if (totalCents < 0) {
                throw new IllegalArgumentException("totalCents must be >= 0");
            }
            this.orderId = orderId;
            this.items = List.copyOf(items);
            this.totalCents = totalCents;
        }

        Receipt withTotal(int nextTotalCents) {
            return new Receipt(orderId, items, nextTotalCents);
        }

        String summary() {
            return orderId + " | " + items + " | " + totalCents;
        }
    }

    public static void main(String[] args) throws NoSuchFieldException {
        List<String> supplied = new ArrayList<>(List.of("Book"));
        Receipt original = new Receipt("ORD-1", supplied, 1200);

        supplied.add("Pen"); // Does not modify the list inside Receipt.
        System.out.println("Original: " + original.summary());

        Receipt updated = original.withTotal(1500);
        System.out.println("Updated: " + updated.summary());
        System.out.println("Original remains: " + original.summary());

        Field totalField = Receipt.class.getDeclaredField("totalCents");
        System.out.println("Declared final: "
                + Modifier.isFinal(totalField.getModifiers()));

        try {
            new Receipt("ORD-2", List.of("Pen"), -50);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid total: rejected");
        }

        try {
            original.items.add("Tape");
        } catch (UnsupportedOperationException e) {
            System.out.println("Mutating items: rejected");
        }
    }
}
```

Run in the directory containing the file:

```bash
javac --release 17 FinalFieldGuidanceDemo.java
java FinalFieldGuidanceDemo
```

Expected output:

```text
Original: ORD-1 | [Book] | 1200
Updated: ORD-1 | [Book] | 1500
Original remains: ORD-1 | [Book] | 1200
Declared final: true
Invalid total: rejected
Mutating items: rejected
```

**Significance of the example:**

1. The constructor validates the order ID, list, and total amount. Negative values are rejected at creation time, so no valid instance with `totalCents < 0` exists through normal initialization paths.
2. `List.copyOf(items)` creates storage that cannot be modified via add/remove operations, protecting against changes from the caller-supplied list. With `String` elements, which are already immutable, this defense is sufficient for the example. With elements that are objects with mutable state, an appropriate deep-copy policy/immutability design is also needed.
3. `withTotal(...)` constructs a **new** `Receipt` via the constructor, so all invariants continue to be checked. `original` remains unchanged; `updated` has the new value.
4. `getDeclaredField("totalCents")` and `Modifier.isFinal(...)` read **metadata**, without intervening in data. The field is `private final`, yet the program can still inspect its metadata.
5. Calling `original.items.add(...)` is blocked by the immutable list. Within the program, the enclosing class is allowed to access private members of a nested class under nestmate rules; external callers should not directly touch this private field.

**Design takeaway:** if there is a business requirement to change the total amount, the API decision is `withTotal(...)` or an update method with validation, not calling `Field.set(...)` directly from calling code.

## 4. Mechanism of `final` and Reflection on Java 17–21

### 4.1. When can `Field.set(...)` modify a final field?

According to the contract of `java.lang.reflect.Field.set` in Java 17/21, writing a `final` field via Reflection is permitted only under narrow conditions: disabling access checks for the `Field` via `setAccessible(true)` has **succeeded**, the field is **not static**, and the declaring class is **not a hidden class or record class**. Otherwise, `set` throws `IllegalAccessException`. Moreover, `setAccessible(true)` itself may not be permitted due to package/module boundaries.

| Field type | Practical meaning |
| --- | --- |
| `private final int n` in an ordinary instance class | May be allowed to be written by Reflection **if** suppression is valid and other API conditions are met; not the way to edit domain objects |
| `static final int N` | Cannot use `Field.set` to write like an instance final field; even suppression does not grant write access for static final |
| Record component (`record Receipt(...)`) | Final fields of a record belong to the group disallowed from writing via `Field.set` |
| Final field declared in a hidden class | Also belongs to the group disallowed from writing via `Field.set` |
| Non-final instance field | Writable if receiver, value type, and access permissions match; can still break invariants if bypassing the API |

One must neither conclude "`private final` can never be modified by Reflection" nor conclude "`setAccessible(true)` will always modify everything". Both statements are wrong about the scope.

### 4.2. **Anti-pattern** example: bypassing validation

The following snippet only illustrates the problem; **it is not code to run for updating objects in an application**. Assume we are inside `main` of the program in section 3 and have the variable `original`:

```java
Field f = Receipt.class.getDeclaredField("totalCents");

// Only when permitted by access/module rules; may be rejected.
if (f.trySetAccessible()) {
    // Anti-pattern: bypasses validation in the Receipt constructor.
    f.set(original, -100);
}
```

If the write command actually succeeds in an environment supporting this case, the data can violate `totalCents >= 0`. In particular, **do not rely on subsequent getters/instructions to prove that all sites observe the new value**, because optimizations for `final` cause post-initialization modification to have unpredictable consequences.

Do not confuse `trySetAccessible()` returning `true` with the field having been written successfully: it only indicates that the attempt to enable suppression succeeded, while `Field.set(...)` can still fail on final, receiver, or data-type conditions.

### 4.3. `setAccessible` and JPMS are not mechanisms to turn a closed API into a public one

With named modules (JPMS), deep reflection permission also depends on whether the package is opened via `opens` to the calling module. `exports` supports accessing public APIs under normal conditions, but does not by itself permit editing private final fields. Many framework libraries must explicitly configure `opens` if they genuinely require deep reflection.

Even when deep reflection permission exists, **modifying fields by bypassing the constructor is still not automatically valid** in terms of business logic and concurrency safety.

## 5. Why Do Constructors Have Special Significance in the Java Memory Model?

The Java Language Specification (JLS §17.5) defines **final field semantics** for properly initialized final fields. When a constructor completes, a **freeze action** associated with final fields helps support observing properly initialized values under the conditions specified by the memory model. Basic usage rules:

1. Assign final fields during valid initialization.
2. Do not leak the `this` reference to other threads/objects **before the constructor finishes**.
3. After initialization, do not treat final fields as storage for state that needs continuous mutation.

This is one reason `final` supports thread-safe immutable class design. However, **final-field guarantees are not magic that makes every multi-threaded object thread-safe**. If a final field points to a mutable object, subsequent changes on the referenced object must still follow separate synchronization rules.

### 5.1. Post-constructor reflective writes have special and restricted semantics

JLS §17.5.3 acknowledges a few special cases such as deserialization/reconstruction that must adjust final fields after object creation. The model makes sense only within a narrow scope:

- The object is in an internal reconstruction phase, **not yet published to other components/threads**.
- All final-field updates complete before any part reads those fields.
- Only afterward is the completed object exposed to the system.

The JLS describes freezing after modifying final fields via certain special mechanisms, but also warns that subsequent reads can be optimized/reordered in unpredictable ways if used arbitrarily. **Do not infer that writing via Reflection after an object is widely used has the same semantics as assignment inside a constructor.**

### 5.2. Why shouldn't final fields of an already-published object be modified?

If an object has already been shared across multiple threads, or code has already read its final value, and then one thread uses Reflection to rewrite the final field, other threads/code may have retained or been compiler-optimized around the old value. Observed results may not match expectations; this is why Java APIs warn that using Reflection to modify final fields outside reconstruction can yield unpredictable results.

This **cannot be fixed merely by arbitrarily adding `volatile` or calling `synchronized`** after bypassing; the right model is preventing immutable entities from being modified after they are in use. If data needs to change frequently, use synchronized mutable state and design a proper API from the start, or replace the entire reference to a new immutable object via safe publication.

## 6. Object Immutability Is More Than Marking All Fields `final`

### 6.1. Final fields holding mutable references

Anti-pattern:

```java
final class BadCart {
    private final java.util.List<String> products;

    BadCart(java.util.List<String> products) {
        this.products = products; // Keeps the caller's mutable alias.
    }

    java.util.List<String> products() {
        return products; // Exposes the mutable alias outside.
    }
}
```

This declaration lets callers modify the list passed in or the list returned, causing contents to change even though `products` is `final`. Fix this with `List.copyOf(products)` when appropriate (noting shallow copy) and avoid returning mutable structures modifiable from outside.

### 6.2. Cross-field invariants

For a range `start <= end`, directly updating individual fields cannot be considered equivalent to creating a valid object. Example:

```java
public record Range(int start, int end) {
    public Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    public Range withEnd(int newEnd) {
        return new Range(start, newEnd);
    }
}
```

This is a **standalone declaration** for `Range.java` in Java 17+. The record's compact canonical constructor always checks the `start <= end` relation. `withEnd` creates a new record and re-validates. Record component fields are final and do not belong to the group that `Field.set` is allowed to write.

For objects with multiple interdependent fields, update code must handle both invariants and intermediate states. With immutable data, creating a new instance often eliminates observable "half-updated" states.

## 7. Comparison of Data-Modification Approaches

| Need | Suitable approach | Why |
| --- | --- | --- |
| Creating an instance initially | Constructor/factory/builder with validation | Ensures a valid object before returning it |
| Adjusting a value on an immutable object | `withX(...)` or factory returning a new instance | Preserves checks, keeps the old object stable |
| Changing state of a mutable object | Business method with validation and synchronization when needed | Preserves invariants and controls concurrency |
| Displaying/reading metadata | `Field.getName`, `getType`, `getModifiers`, `getDeclaringClass` | Analyzes structure without altering data |
| Reading a field when permitted | `Field.get(receiver)` | Observes data only; must still respect access permissions |
| Specialized object-reconstruction framework | Purpose-built serialization mechanism, with lifecycle and visibility rules | Uses low-level mutation only before publishing the object and within runtime limits |
| Directly modifying a private final field of a running object | Avoid; redesign the update API | Risks breaking invariants and final-field semantics |

**Note:** not every Reflection operation is dangerous or discouraged. Reading metadata, dependency injection, or deserialization has legitimate scope when following API/runtime contracts. The specific lesson here is not replacing the initialization lifecycle and immutability rules with free-form field mutation.

## 8. Conceptual Mistakes and Consequences

| Wrong assumption | Accurate correction |
| --- | --- |
| "If `Field.set` succeeds, the object is valid." | Reflection does not automatically run constructor/business-method validation |
| "If all fields are `final`, the object is definitely immutable." | Inner mutable objects, aliases, and leaking `this` can break safety |
| "`setAccessible(true)` always bypasses all access permissions." | JPMS, field category, record/hidden class, and runtime limits can block it |
| "`final` always makes a field unmodifiable by Reflection." | Certain instance final fields in ordinary classes may be writable under narrow conditions |
| "Modifying a final field after sharing an object will be seen by all threads like a `volatile` update." | Final-field semantics and JIT optimizations do not permit that assumption |
| "Serialization needs Reflection, so domain updates should also mutate fields." | Reconstructing an object before publication has a very different lifecycle from mutating an in-use object |
| "To tweak an immutable property, mutate the old field to save allocation." | Use a new valid object and manage publishing the new reference |
| "A constructor that assigns fields is enough; no cross-field checks needed." | Constructors must verify required invariants, including relationships between fields |

## 9. Decision Process When Facing a "Modify Field" Requirement

**Step 1:** Determine whether the field is instance or static, `final` or mutable, and belongs to an ordinary class, record, or hidden class.

**Step 2:** Determine whether the requirement is reading metadata, reading values, reconstructing an object from stored data, or **performing a business update on an existing object**. These are distinct goals.

**Step 3:** For business updates, look for a constructor/factory, getter, `withX`, or update method designed for invariants. If none exists, design an appropriate API and add validation; do not let callers arbitrarily write to private fields.

**Step 4:** If the data holds mutable references, check defensive copying and aliasing. If multiple threads can access the object, determine the publication and state-synchronization mechanism.

**Step 5:** Only when building specialized reconstruction/deserialization tools should low-level field mutation be considered; read the `Field.set` contract of the target JDK, module restrictions, final-field conditions, and the "before publication" lifecycle. Do not generalize from a single test run or a specific JVM.

## 10. Self-Check Questions

1. Does `private final List<String> items` guarantee callers cannot alter the contents of `items`? Why?
2. `Receipt`'s constructor rejects `totalCents < 0`. If other code directly writes the field to `-100`, does the invariant still hold?
3. Why can Java Reflection locate a private final field with `getDeclaredField` without necessarily being able to write it with `set`?
4. Do `static final`, record components, and ordinary-class instance final fields have the same writability via `Field.set`?
5. Why can using Reflection to modify a final field after an object is already in use by threads not be treated as a normal update?
6. If `Receipt`'s `totalCents` needs to be changed validly, what approach is used in the standalone runnable program?

**Answers:** (1) No; `final` only fixes the reference, so mutable aliases must be prevented; (2) No; (3) Metadata lookup and write-permission checking are two separate stages; (4) No; (5) Final-field/JMM semantics and optimizations allow unexpected observed results; (6) `original.withTotal(newTotal)` creates a new `Receipt` via the constructor.

## 11. Conclusion and Technical References

**Constructors and factories are the boundary that creates valid state; `final` supports stable state design; Reflection is a tool for accessing metadata and fields under strict rules.** The fact that a final instance field can be modified in special cases does not make `Field.set` a replacement for constructors or a way to edit immutable objects. Always preserve invariants, control aliases, and respect the object-publication lifecycle before considering low-level field mutation.

Official specification references:

- [Java SE 21 – `java.lang.reflect.Field.set`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)): field write conditions and limits for final fields.
- [Java Language Specification 17 – `17.5 final Field Semantics`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): meaning of final fields in the Java Memory Model.
- [JLS §17.5.3 – Subsequent Modification of final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5.3): specialized reconstruction cases and risks when modifying final fields after the constructor.
