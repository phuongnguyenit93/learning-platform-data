# Do Not Treat Serialize-Then-Deserialize as the Default Copy Mechanism for Every Class

## 1. Distinguishing Object Copying from Java Serialization

A technique often called "deep copy via serialization" uses `ObjectOutputStream` to convert an object into a byte sequence, then uses `ObjectInputStream` to read that byte sequence back into an object. Conceptual flow:

```text
Original object → write ObjectOutputStream → byte[]
byte[] → read ObjectInputStream → restored object
```

For a graph composed of objects supporting Java Serialization and having no special replacement mechanism, this approach *can* produce new objects containing much of the same data as the original. However, the original purpose of Java Object Serialization is representing and restoring state under a **serialization protocol**, not providing a universal copy contract for every class.

To call an operation a "copy", you must clarify: must the new instance have a different reference, which fields are kept, which fields must be detached from the original, whether sharing relationships among fields are preserved, whether off-heap resources are shared or recreated, and whether class constructors/invariants are satisfied.

**Conclusion:** serialize-then-deserialize is not the default choice for every class. Treat it as a technique with many preconditions and limitations, not an automatic `deepCopy(Object)` function that is right in all cases.

## 2. The Serializable Requirement Applies to the Entire Graph

`java.io.Serializable` is a *marker interface*: it does not require a class to implement any methods. When `ObjectOutputStream.writeObject(root)` is called, the writer can follow reference fields of `root` to write objects in the graph.

If it encounters an object that does not support Serializable via a field that needs to be written, the process can throw `NotSerializableException`, even when the `root` class already `implements Serializable`.

```java
import java.io.Serializable;

// Illustrates two classes, not a standalone program.
final class Attachment {
    String location = "folder/item";
}
final class Report implements Serializable {
    private static final long serialVersionUID = 1L;
    Attachment attachment = new Attachment();
}
```

`Report` is Serializable, but `Attachment` is not. Serializing a `Report` containing `attachment` under default rules will fail. Adding `implements Serializable` to the root class does not automatically make referenced objects Serializable.

| Kind of state | Typical behavior during serialize/deserialize |
| --- | --- |
| Primitive field | Value is written and restored in serialized form. |
| Normal reference field | Referenced object must satisfy the corresponding serialization mechanism. |
| `transient` field | Skipped in default write form; upon reading back, usually receives default value unless custom restoration logic exists. |
| `static` field | Not instance state; does not create an independent static copy. |
| External resources | Sockets, threads, streams, locks, connections, transactions... are not automatically cloned in a valid business sense. |

Using `transient` to avoid write errors **is not equivalent** to a successful copy. If the field is a recomputable cache, losing it may be acceptable; if it is a dependency required for the object to work, the restored instance may lack critical state.

For ordinary Serializable classes, deserialization **does not invoke that class's constructor like `new`**. For a non-Serializable superclass, Java has a rule invoking the accessible no-arg constructor of the nearest non-Serializable superclass. Thus how fields and invariants are restored does not necessarily match a copy constructor.

## 3. Graph Copying: Preserving Repeated References and Cycles

Default serialization has a mechanism to track objects already seen in the stream:

```text
Original:
Container
 ├─ first ──┐
 └─ second ─┴──> Node A ─next─> Node A

Restored:
Container'
 ├─ first ──┐
 └─ second ─┴──> Node A' ─next─> Node A'
```

In an appropriately Serializable graph, `A'` is a different node from `A`, yet both `first` and `second` fields of the new container still point to **the same `A'`**; the `next` cycle can also be restored. This is a technical advantage over a naive recursive clone function that loses aliases or loops infinitely.

However, deep copying in business terms is not just "every object has a different reference": some objects need to remain shared, some resources must not be duplicated, and some IDs must be kept or newly minted. Moreover, classes with `readResolve`, `writeReplace`, `writeObject`, `readObject`, or `Externalizable` can actively alter the written/read form or the resulting object. `enum` also has special instance semantics. You cannot claim every round-trip returns a new independent object.

## 4. Complete Java 17 Example: What Is Preserved, What Is Lost

Create the file `SerializationCopyDemo.java`:

```java
import java.io.*;
import java.util.ArrayList;
import java.util.List;

public class SerializationCopyDemo {
    static final class Node implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        String title;
        List<String> tags = new ArrayList<>();
        Node next;
        transient String cache = "ready";

        Node(String title) {
            this.title = title;
        }
    }

    static final class Pair implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        Node left;
        Node right;

        Pair(Node value) {
            left = value;
            right = value;
        }
    }

    static Pair roundTrip(Pair value)
            throws IOException, ClassNotFoundException {
        byte[] data;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
            out.flush();
            data = bytes.toByteArray();
        }
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(data))) {
            return (Pair) in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Node n = new Node("Java");
        n.tags.add("core");
        n.next = n;

        Pair original = new Pair(n);
        Pair copied = roundTrip(original);

        System.out.println("different root: "
                + (original != copied));
        System.out.println("different child: "
                + (original.left != copied.left));
        System.out.println("alias kept: "
                + (copied.left == copied.right));
        System.out.println("cycle kept: "
                + (copied.left.next == copied.left));
        System.out.println("original cache: " + original.left.cache);
        System.out.println("copied cache: " + copied.left.cache);

        copied.left.tags.add("copy");
        System.out.println("original tags: " + original.left.tags);
        System.out.println("copied tags: " + copied.left.tags);
    }
}
```

Run with JDK 17 or higher:

```bash
javac SerializationCopyDemo.java
java SerializationCopyDemo
```

Stdout:

```text
different root: true
different child: true
alias kept: true
cycle kept: true
original cache: ready
copied cache: null
original tags: [core]
copied tags: [core, copy]
```

Explanation: `Pair` and `Node` in the restored graph are different instances from the original graph. However, both `left` and `right` fields in the new copy still share one new node, and `next` forms a cycle back to that same node. `tags` in the new graph is independent, so elements can be added without modifying the original `tags`.

The `cache` field is `transient`, so it is absent from the default written form. The `"ready"` field initializer of the Serializable class does not run like normal instance creation during reading, so the copy has `cache == null`. An object that looks like a "deep" copy can still **be missing data**.

The program only deserializes a byte sequence it just generated itself from known classes. Do not use this code as an API accepting serialized data from untrusted sources.

## 5. A Non-Serializable Field Causes Failure; `transient` Changes Copy Meaning

Add to another illustrative program:

```java
class NativeResource {
    String name = "R1";
}

class Job implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    NativeResource resource = new NativeResource();
}
```

The two classes above are illustrative, without `main`. `Job` implements Serializable, yet `resource` holds a non-Serializable `NativeResource`. If `new Job()` is written via `ObjectOutputStream.writeObject`, writing will throw `NotSerializableException`.

One might try replacing it with:

```java
transient NativeResource resource = new NativeResource();
```

The line above is an illustrative field declaration in `Job`. Then default writing skips the `resource` field. However, **the read-back copy no longer has a `resource` object**, and `Job`'s constructor does not automatically run again to create `new NativeResource()`. If `Job`'s methods need `resource`, they risk hitting `NullPointerException` or violating invariants, unless the class has carefully designed custom restoration rules.

A clearer option may be a copy constructor, a factory creating an independent `NativeResource` when needed, or disallowing copying when the resource has no safe duplication semantics. Do not use `transient` as a trick to make every class writable.

## 6. Why Can This Not Be Called a Deep Copy by Default?

Distinguish **copying Serializable state** from **copying under a business contract**.

1. **The graph may not be completely Serializable.** A single deeply nested non-Serializable element suffices to fail the write stream.
2. **Some fields are not written.** `transient` loses data by default; `static` is not copied per instance.
3. **Objects have custom serialization logic.** `readResolve` can return a shared instance, `readObject` can restore or alter state according to class logic, and hooks can affect how restoration behaves.
4. **Resources are not merely bytes.** File descriptors, connections, processing threads, locks, and handles outside the JVM need lifecycle policies, and cannot be cloned by restoring Java fields.
5. **Constructor invariants may differ.** Validation steps, registry registration, ID assignment, lock or cache initialization are usually performed in constructors/factories; serializers do not repeat those steps by default.
6. **Independence and sharing are business decisions.** A copy may need to create a separate list while sharing immutable objects; or detach a parent pointer while keeping alias relationships. A serializer mechanism does not understand each field's semantics on its own.
7. **State may be mutated concurrently.** If another thread mutates the object while writing, the application must ensure a consistent snapshot; serialization does not replace business-level synchronization.
8. **The format may become incompatible later.** Changes to class structure, serial form, or `serialVersionUID` can cause restoration to fail or produce data no longer valid.

Do not only test `copy != original`. A trustworthy copy must test whether editing mutable fields on the new instance affects the old one, alias and cycle relationships, all invariants, and required resources after copying.

## 7. Comparison with `clone()`, Copy Constructors, and Factories

| Copy method | Characteristics | Suitable when |
| --- | --- | --- |
| `super.clone()` via `Object.clone()` | Shallow-copies instance fields; child object references remain shared. | Clone API already has a clear contract; mutable fields can be handled manually. |
| Copy constructor `new Type(source)` | Constructor actively selects fields to copy, can assign new `final` fields and validate invariants. | Data structure is fairly clear, needing a transparent copy policy. |
| Factory `Type.copyOf(source)` | Can create snapshots, new objects, or reuse immutable objects per contract. | Want an API easy to evolve and control state. |
| Serialize → deserialize | Writes/reads graph per Java Serialization rules; can preserve aliases and cycles. | Only when graph fits, system actually needs serial form, data source is controlled, and cost is acceptable. |
| Immutable data | Can be safely shared without deep cloning. | All involved components are truly immutable. |

For simple cases, a copy constructor is usually easier to read:

```java
import java.util.ArrayList;
import java.util.List;

final class Profile {
    private final String name;
    private final List<String> labels;

    Profile(String name, List<String> labels) {
        this.name = name;
        this.labels = new ArrayList<>(labels);
    }

    Profile(Profile source) {
        this(source.name, source.labels);
    }
}
```

This is a class declaration without `main`. The copy constructor creates a **new list**; the elements are immutable `String`s and thus can be shared. If `labels` contains mutable objects, `new ArrayList<>(labels)` is still only a shallow copy of **elements**, requiring an additional policy to separate child objects.

If the copy needs to generate a new ID, open/close different resources, drop caches, or change environment details, express that explicitly in the constructor/factory. Such rules should not be hidden behind a generic serialize/deserialize utility.

## 8. Performance, Compatibility, and Security

### Execution Cost

A round-trip requires traversing the graph, encoding bytes, allocating buffers, and recreating objects from bytes. This can consume CPU, temporary memory, cause garbage-collection pressure, and execute serialization callbacks. One cannot conclude it is **always** slower than every copy constructor in every situation, yet it clearly performs extra steps beyond directly copying the needed data. For frequent copy operations or large graphs, consider another design and measure with appropriate benchmarks.

### Version Compatibility

`serialVersionUID` supports compatibility checks when reading data written by different versions of a class. It **does not guarantee** that all field changes, inheritance changes, or business invariants remain compatible. Incompatible changes can lead to `InvalidClassException` or restoring state that is incomplete/invalid under new requirements.

If a long-lived storage or exchange format is needed, design a DTO/schema, versioning, validation, and migration strategy appropriately. That is a different requirement from wanting an in-memory copy.

### Data Safety

`ObjectInputStream` should not be used to process Java serialized data from **untrusted sources**. The restoration mechanism can trigger logic of classes present in the system, and this byte format does not inherently provide encryption, authentication, or business validation. When Java Serialization must be maintained in legacy systems, restrict types/sizes and apply appropriate safeguards, such as object input filtering, source control, and post-read data validation. These measures do not make arbitrary external input safe.

**Do not add `implements Serializable` wholesale just to get a convenient copy helper.** Doing so expands responsibility over format, compatibility, and the serialized data processing surface.

## 9. Designing the Right Copy Contract for an Object Model

Before deciding on an implementation, answer:

- Must the copy have a **new identity**, or is returning the same old immutable object permitted?
- Which fields are **core values**, and which are merely caches/metadata/auxiliary resources?
- Should business IDs be preserved or newly issued?
- Do `List`, `Map`, array, and mutable child object fields need independence? To what depth?
- Must two fields currently pointing to one node continue pointing to **one new node** in the copy?
- Are there circular references? If copying the graph manually, use an identity-based mapping table from original nodes to copied nodes to avoid loops and preserve sharing relationships.
- Are there `final` fields, constructor invariants, locks, or resources that must be recreated via a factory?
- Can the object be mutated by another thread during copying? Is there a consistent snapshot mechanism yet?
- Do fields participating in `equals`/`hashCode` require immutability when the object is used as a key in a map/set?

Then test on the copy: check values, mutate mutable data on one side, check aliases and cycles, verify invariants, resources, and proper ownership closing/opening.

**Practical tip:** small, straightforward data usually fits a copy constructor/factory; immutable value objects rarely need deep copying; complex mutable graphs need a policy-driven copy method, potentially using an identity object map. Serialization may fit if its format and semantics are already an actual requirement, rather than as a default mechanism.

## 10. Common Misconceptions and Self-Check

| Misconception | Why it is incorrect |
| --- | --- |
| If the root class is Serializable, every field can be copied. | The graph may contain non-Serializable objects. |
| Using `transient` makes the copy equivalent to the original. | The field is skipped, potentially breaking invariants. |
| Deserialization always calls the Serializable class's constructor. | The restoration mechanism is not like ordinary `new`. |
| Every reference in the copy is independent. | Aliases and cycles may be preserved; some types have instance-replacement logic. |
| Serialization automatically copies sockets/locks/connections. | Resources need separate lifecycle contracts. |
| Having `serialVersionUID` ensures compatibility across all versions. | Classes can still change incompatibly or alter data meaning. |
| Deserializing arbitrary bytes is a harmless operation. | Untrusted serialized data must be avoided or handled under strict defensive policies. |
| Deep copy means copying everything. | Deep copy must be defined by which data needs independence and which relationships must be preserved. |

**Self-check questions:**

1. What problem will a `Report implements Serializable` containing a non-Serializable `Attachment` field encounter during `writeObject`?
2. Why can `transient` make the write succeed yet leave the read-back copy missing data?
3. If two fields point to the same node, does default serialize/deserialize necessarily split the two fields into two different nodes?
4. Why must both alias relationships and cycles be tested when copying a graph?
5. Why should you not copy a `Socket`, `Thread`, or database connection using serialization?
6. What benefits does a copy constructor bring when a class has many `final` fields or important validation logic?
7. When is sharing an immutable object better than creating a copy?
8. Why should `ObjectInputStream` not be used arbitrarily on externally supplied bytes?
9. After a copy, should an ID that must be unique in the system automatically be kept as-is?
10. What tests are needed to know a copy is truly independent on important mutable fields?

**Takeaway:** Java Serialization can write and restore a **Serializable graph**, yet is not a default copy contract for every class. `NotSerializableException`, `transient` fields, custom serialization mechanisms, external resources, version compatibility, cost, and security are all reasons to **choose the copy policy first** and then choose the technique. For many application classes, a copy constructor, factory, or immutable design is clearer and easier to control.
