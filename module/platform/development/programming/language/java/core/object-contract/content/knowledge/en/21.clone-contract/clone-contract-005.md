# `super.clone()` shallow-copies fields in Java

## 1. What does `super.clone()` do?

In Java, `java.lang.Object` defines the method `protected Object clone() throws CloneNotSupportedException`. A class can override `clone()` and call `super.clone()` to create a new object whose initial state is copied from the calling object. If the call chain reaches `Object.clone()`'s implementation, this operation performs a **shallow copy** of the fields.

Imagine a `Document` object with the following fields:

```text
Document original
├── title = "Java"           (String reference)
├── version = 1              (int)
└── tags ──────────────┐
                       ▼
                ArrayList ["core"]

Document clone (after super.clone)
├── title = "Java"           (same original String reference)
├── version = 1              (copy of int value)
└── tags ──────────────┘     (same ArrayList object)
```

`original` and `clone` are **two different `Document` objects** (`original != clone`), yet the `tags` field of both points to **the same** `ArrayList`.

- **Primitive fields** (`int`, `long`, `boolean`, ...): the value is copied into the new object's field; reassigning the field on one copy does not change the other copy's field.
- **Reference fields** (`String`, `List`, array, business object, ...): copies the **reference value**, without automatically creating a new child object. Both copies can point to the same child object.
- **`static` fields** belong to the class, not the state of individual instances; `clone` does not create independent copies of these fields.
- **`final` fields** also have their values copied. If it is a reference to a mutable object, `final` does not separate the child object.
- **The constructor of the cloned class is not re-run** by the `Object.clone()` mechanism; state is created by copying fields, not by initializing an instance through a regular constructor.

Thus, `super.clone()` does not mean "copy the entire object graph". It only creates a new object shell with matching field values when the call reaches `Object`'s default clone mechanism.

## 2. Conditions to call `super.clone()`

`Object.clone()` is a `protected` method, so a subclass can call `super.clone()` inside its own implementation. However, if the actual object **does not implement the `Cloneable` interface**, `Object.clone()`'s implementation will throw `CloneNotSupportedException` (Java arrays have their own cloning mechanism).

```java
class Example implements Cloneable {
    @Override
    public Example clone() {
        try {
            return (Example) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

This is a complete class declaration without `main`. Points to understand:

1. `Cloneable` is a **marker interface** in `java.lang` and does not declare a `clone()` method. `implements Cloneable` does not automatically generate a public `clone()` API for callers to use.
2. The class proactively overrides `clone()` as `public` if users should be able to call it. Widening access from `protected` to `public` is valid.
3. Returning `Example` instead of `Object` is a valid **covariant return type**, saving callers from casting the result. The `(Example)` cast inside is necessary because `super.clone()` has declared return type `Object`.
4. `super.clone()` is called inside `try` because `Object.clone()`'s signature declares the checked exception `CloneNotSupportedException`.
5. For class `Example` implementing `Cloneable` and using the default mechanism, that error is abnormal; the code converts it to `AssertionError` to indicate a broken design assumption. Another class may also expose `throws CloneNotSupportedException` depending on its API.

Do not confuse **having declared `Cloneable`** with **already having a complete, business-correct copying API**. `Cloneable` only enables `Object`'s clone mechanism; separating mutable data, validating invariants, and handling inter-field relationships remain the class's responsibility.

## 3. Common contract: distinct identity but matching starting state

If `x.clone()` is designed according to the common convention:

- The copy usually has a **runtime class matching the original**.
- The copy is usually a distinct object: `x.clone() != x`.
- In many value classes, right after cloning, `x.clone().equals(x)` is often `true`, but this is **not an absolute guarantee** for every data type or every custom override.

The reason is that a class can define `equals()` by **identity** (default `Object.equals`), in which case two objects with different references are not equal. There may also be classes overriding `clone()` with special rules. Therefore, **clone and equals are two different contracts**; one must not deduce that clone necessarily makes `equals` return `true`.

If `Object.clone()` is reached, the new object has the same **runtime class** as the original and fields are copied via the default mechanism. `super.clone()` does not slice off subclass state: a valid call on a subclass object will copy instance fields belonging to both the superclass and the subclass. However, if a superclass **overrides `clone()`**, then the subclass's `super.clone()` call enters that superclass override, which may have additional logic; do not assume every `super.clone()` goes straight to `Object.clone()`.

## 4. Java 17 example: shallow copy sharing a list

Create standalone file `CloneShallowDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CloneShallowDemo {
    static final class Document implements Cloneable {
        private String title;
        private List<String> tags;

        Document(String title, List<String> tags) {
            this.title = title;
            this.tags = new ArrayList<>(tags);
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        Document detachedCopy() {
            Document copy = clone();
            copy.tags = new ArrayList<>(tags);
            return copy;
        }

        void addTag(String value) {
            tags.add(value);
        }

        void rename(String value) {
            title = value;
        }
    }

    public static void main(String[] args) {
        Document original = new Document("Java", List.of("core"));
        Document shallow = original.clone();

        System.out.println("different objects: " + (original != shallow));
        System.out.println("shared tags: "
                + (original.tags == shallow.tags));

        shallow.rename("Spring");
        System.out.println("original title: " + original.title);

        shallow.addTag("concurrency");
        System.out.println("original tags after shallow: "
                + original.tags);

        Document detached = original.detachedCopy();
        System.out.println("detached tags: "
                + (original.tags != detached.tags));

        detached.addTag("collections");
        System.out.println("original tags after detached: "
                + original.tags);
        System.out.println("detached tags after edit: "
                + detached.tags);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CloneShallowDemo.java
java CloneShallowDemo
```

Stdout:

```text
different objects: true
shared tags: true
original title: Java
original tags after shallow: [core, concurrency]
detached tags: true
original tags after detached: [core, concurrency]
detached tags after edit: [core, concurrency, collections]
```

### Why is the output like this?

1. `original.clone()` creates a new `Document`, so `original != shallow` is `true`.
2. `original.tags == shallow.tags` is `true`: both fields hold the same reference to the `ArrayList` due to shallow cloning.
3. Calling `shallow.rename("Spring")` only reassigns the `title` field of **the shallow copy**; the `title` field in `original` remains `"Java"`. `String` is also immutable, so there is no issue of modifying shared string contents.
4. Calling `shallow.addTag("concurrency")` mutates the very `ArrayList` object shared by both copies, so the original also sees the new element.
5. `detachedCopy()` starts with a shallow copy, then replaces `copy.tags` with `new ArrayList<>(tags)`. Now the copy has an **independent list**. Adding `"collections"` only affects `detached`'s list.

**Limitation of `new ArrayList<>(tags)`:** this is only a shallow copy at the **list level**. In the example, elements are immutable `String`s, so it suffices to separate mutable state. If the list contains mutable objects such as `Address` with setters, both lists can still hold **the same `Address` instances**; to separate all state, each element must be copied according to an explicit policy.

## 5. Shallow copy, deep copy, and how many levels to separate

### Shallow copy

`super.clone()` copies instance fields once:

```text
A ── address ──> Address { city = "Hue" }
B ── address ──┘
```

`A` and `B` are two separate instances, but modifying `address.city` through one side is visible through the other.

### Deep copy

If the business domain requires **no sharing of mutable state**, the necessary new child objects must be created:

```text
A ── address ──> Address { city = "Hue" }
B ── address ──> Address { city = "Hue" }  (separate instance)
```

There is no single universal "deep copy" depth: one must determine which components are allowed to be shared. Immutable objects like `String` can usually be shared safely; entities with shared identity, caches, or object links may have different rules. For object graphs with cycles, the deep copy process needs to track visited objects to avoid infinite recursion and preserve sharing relationships accurately.

### Shallow copy followed by separating individual fields

For reassignable fields, code typically looks like:

```java
@Override
public MyType clone() {
    try {
        MyType copy = (MyType) super.clone();
        copy.mutableList = new ArrayList<>(mutableList);
        copy.numbers = numbers.clone();
        return copy;
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
```

The snippet above is an **illustrative template** for a class `MyType implements Cloneable` with suitable `mutableList` and `numbers` fields. It is not a standalone program and may still need to copy mutable objects inside `mutableList`.

If the reference fields needing separation are declared `final`, we cannot simply reassign `copy.mutableList` inside `clone`. In that case, designing with a **copy constructor** or a factory creating a new object is usually clearer and allows initializing `final` fields in accordance with desired invariants.

## 6. Cloning arrays: creates a new array without automatically cloning each element

Java arrays support `clone()` even though the author does not declare `implements Cloneable`; every array has its own clone method returning the corresponding array type. It also performs a **shallow copy**.

- For `int[]`, `clone()` creates a new array containing copied numbers. Modifying an element of the copy does not modify the original array.
- For `String[]`, `clone()` creates a new array, though the elements are copied `String` references; `String` is immutable, so sharing strings is generally safe.
- For `Person[]`, `clone()` creates a new array, but each initial element can still point to the exact old `Person` objects. Modifying a `Person` object through the copy will be visible through the original.
- For `int[][]`, `clone()` on the outer array only creates a **new outer array**; each `int[]` row remains a shared reference. To be independent at both levels, each row must be cloned.

A second standalone program clarifies the `Cloneable` condition, constructors, and arrays.

Create file `CloneMechanicsDemo.java`:

```java
public class CloneMechanicsDemo {
    static final class Unmarked {
        Object attempt() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    static final class Counted implements Cloneable {
        static int created;

        Counted() {
            created++;
        }

        @Override
        public Counted clone() {
            try {
                return (Counted) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        try {
            new Unmarked().attempt();
            System.out.println("unmarked allowed: true");
        } catch (CloneNotSupportedException ex) {
            System.out.println("unmarked rejected: true");
        }

        Counted original = new Counted();
        Counted copied = original.clone();
        System.out.println("constructor count: " + Counted.created);
        System.out.println("different Counted: " + (original != copied));
        System.out.println("same runtime class: "
                + (original.getClass() == copied.getClass()));

        int[][] source = {{1, 2}, {3}};
        int[][] outer = source.clone();
        System.out.println("new outer array: " + (source != outer));
        System.out.println("shared first row: "
                + (source[0] == outer[0]));

        outer[0][0] = 99;
        System.out.println("source first number: " + source[0][0]);

        int[][] detached = source.clone();
        for (int i = 0; i < detached.length; i++) {
            detached[i] = source[i].clone();
        }
        detached[0][0] = 7;
        System.out.println("source after row copies: "
                + source[0][0]);
        System.out.println("detached after row copies: "
                + detached[0][0]);
    }
}
```

Compile and run:

```bash
javac CloneMechanicsDemo.java
java CloneMechanicsDemo
```

Stdout:

```text
unmarked rejected: true
constructor count: 1
different Counted: true
same runtime class: true
new outer array: true
shared first row: true
source first number: 99
source after row copies: 99
detached after row copies: 7
```

Explanation:

- `Unmarked` does not implement `Cloneable`, so `Object.clone()` from `attempt()` throws `CloneNotSupportedException`.
- One `Counted` object is created by the regular constructor. Calling `clone()` does not invoke the constructor again, so `created` remains `1`.
- `source.clone()` returns a new outer array, yet `source[0] == outer[0]` remains true. Assigning `outer[0][0] = 99` actually modifies the row shared with the source array.
- At the `detached` step, each `int[]` row is also cloned. Therefore, assigning `detached[0][0] = 7` does not alter `source[0][0]`.

The example assumes no `null` rows when cloning each row. If the structure is a jagged array allowing `null` rows, you must guard `source[i] == null` before calling `clone()`. If elements are mutable objects instead of `int`, cloning two array levels still does not equal deep copying each element object.

## 7. Relationship with inheritance and overriding `clone()`

If a superclass `Base` has an inherited clone mechanism and a subclass `Derived` adds new fields, calling `Object.clone()` on a `Derived` instance copies instance fields of **the entire `Derived` object**, including both superclass and subclass fields. However, copying the subclass's additional references is still only a shallow copy.

Template example:

```java
class Base implements Cloneable {
    int id;

    @Override
    public Base clone() {
        try {
            return (Base) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class Derived extends Base {
    java.util.ArrayList<String> notes = new java.util.ArrayList<>();

    @Override
    public Derived clone() {
        Derived copy = (Derived) super.clone();
        copy.notes = new java.util.ArrayList<>(notes);
        return copy;
    }
}
```

These are **class declarations that can be placed in the same Java file** (without `main`), illustrating the parent level shallow-copying first and the child level separating its own `notes` field.

Important points:

1. `super.clone()` in `Derived` invokes `Base`'s `clone` version; that version in turn calls `Object.clone()`.
2. `Base.clone()` returns `Base` as its declared type, but the actual cloned object is `Derived` when the original receiver is `Derived`. The `(Derived)` cast is valid under the designed mechanism.
3. Then `Derived.clone()` additionally copies `notes` because this field references mutable data. Without this step, the original and the clone would share the same list.
4. If there are multiple subclasses across multiple levels, each level may have to take responsibility for mutable resources added at that level. Clear conventions must be kept; cloning in arbitrarily extensible hierarchies can be hard to maintain.

Do not assume calling `super.clone()` at every level suffices to handle invariants or internal resources properly. If a superclass has complex relational state, subclasses unfamiliar with the superclass's clone contract can produce invalid copies.

## 8. Pitfalls with `final`, resources, and object links

### `final` fields do not guarantee deep copy

```java
private final java.util.List<String> tags;
```

A class with the field above cannot reassign `copy.tags = new ArrayList<>(tags)` inside a standard `clone` method. Both copies created via shallow clone still point to the same list; declaring `final` alone **does not make the list immutable**. If the design requires a separate list, a copy constructor can properly initialize the new `final` field.

### OS resources should not be copied blindly

Objects holding a `FileInputStream`, socket, lock, transaction, thread, or native handle cannot by default make sense when merely copying fields. A shallow clone can cause two copies to hold the same resource, leading to double-close, concurrent writes, wrong ownership, or violated invariants.

Explicitly define the required behavior: do not support clone, create a new independent resource via a factory, or copy only transferable configuration data. For `AutoCloseable` resources, lifecycle management mechanisms like `try-with-resources` still need separate design.

### Links between fields and between objects

Suppose `left` and `right` of the original both reference the same child object, or a child object points back to the parent. Deep copying is not merely calling `clone` independently for each field: it may need to preserve **shared relationships** (`left == right`) and update back-pointers to the right new copy.

For graphs with cycles, recursive cloning without tracking already-created objects can loop infinitely. This is why a copy constructor/factory with explicit rules on identity, links, and invariants is often more suitable for models with rich relationships.

## 9. When to use `clone()` vs. other copying approaches?

| Approach | Advantages | Limitations / conditions |
| --- | --- | --- |
| `super.clone()` + adjust mutable fields | Can reuse default field copying without passing every simple field again. | Easy to miss mutable references; hard to handle `final`, inheritance, constructor invariants, and resources. |
| Copy constructor `new Type(source)` | Has full control to create new state, assign `final` fields, selectively copy, and check invariants. | Must proactively list data to copy; must define subclass handling. |
| Factory `Type.copyOf(source)` | API can state copying policy clearly, sometimes reusing valid immutable objects. | Must have clear contract on sharing/copying and return type. |
| Immutable type / record | Rarely needs defensive copying when all components and nested data are truly immutable. | A record can contain mutable components; shallow immutability is not automatically deep immutability. |
| Manual component/graph copying | Explicit control over isolation depth, ownership, and cycle handling. | Can take effort and require intermediate maps to preserve identity relationships. |

For new data types, Java does not mandate using `Cloneable` to support copying. A copy constructor or factory is usually easier to explain and test. If `clone` is used for legacy API compatibility or because a class already has a clear clone contract, all reference fields must be inspected carefully.

Note that `clone` is not a serialization mechanism, does not re-run constructors to enforce initialization constraints, and is not automatically a thread-safe solution. If an object is being mutated concurrently during cloning, synchronization or a consistent snapshot must be designed.

## 10. Common mistakes and verification checklist

| Common mistake | Consequence | Solution |
| --- | --- | --- |
| Assuming `super.clone()` is a deep copy. | Both objects still share lists, arrays, or mutable objects. | Explicitly identify which fields need new child instances. |
| Only writing `implements Cloneable` and calling `obj.clone()` outside the class. | Interface declares no public clone; code may fail to compile. | Provide a public `clone` method or another copy API. |
| Forgetting `Cloneable` while calling `Object.clone()`. | `CloneNotSupportedException`. | Adhere to the Cloneable mechanism or drop clone and use a factory/copy constructor. |
| Thinking the clone is initialized via constructor. | May skip invariant-setup logic in the constructor. | Review invariants; consider explicit constructor initialization. |
| Using `new ArrayList<>(oldList)` and believing mutable elements were cloned. | New list, yet elements remain shared. | Copy each element when needed. |
| Cloning `int[][]` once to separate every row. | New outer array, yet `int[]` rows remain shared. | Clone each row in addition to cloning the outer array. |
| Trying to assign a `final` field of the clone after `super.clone()`. | Compile error; cannot reassign final inside normal clone. | Use a constructor/factory creating a new object. |
| Cloning an object with socket/stream/lock without defining ownership. | Two copies may share resources unintentionally. | Design resource lifecycle; consider forbidding clone. |
| Assuming `clone.equals(original)` is always true. | False when `equals` compares identity or the class has custom rules. | Verify the `equals` contract of the specific data type. |

Checklist before implementing clone:

1. Does the instance to clone implement `Cloneable` as required by `Object.clone`?
2. Does the clone API have appropriate access scope and return type for callers?
3. Does the new object have the right runtime type and essential field values?
4. Which mutable reference fields, multi-dimensional arrays, collections, or child objects are currently shared?
5. Do any `final` fields or constructor invariants make post-clone mutation unsuitable?
6. Does copying preserve internal links, aliases, and back-pointers if the model requires it?
7. Are there non-copyable resources such as streams, sockets, locks, native handles, or external state?
8. If the copy is used in hash-based collections, are fields participating in `equals/hashCode` stable and contract-compliant?
9. Can copying run concurrently with mutating the original object? If so, has a consistent snapshot been designed?
10. Would a copy constructor or factory convey copying semantics more clearly and be easier to maintain?

### Self-practice questions

1. After `B b = (B) a.clone()`, why can `a != b` hold while `a.list == b.list` is still `true`?
2. If a clone contains `int age` and `List<String> tags`, what is the difference between modifying `age` and adding an element to `tags`?
3. Why does `Cloneable` not have a `clone` method to call directly via a variable of type `Cloneable`?
4. Why is `new ArrayList<>(tags)` not yet a deep copy if `tags` contains mutable objects?
5. If an `int[][]` is cloned using only `source.clone()`, what is independent and what remains shared?
6. Why is `final List<String>` hard to handle if you want to separate the list by reassigning after `super.clone()`?
7. Why does cloning an object holding a socket or input stream require a special ownership policy?
8. Can a class not support clone yet still provide a valid `copy()` method? Give an example of how.

**Remember:** When reaching `Object.clone()`, `super.clone()` creates a **new instance** and **shallow-copies fields**: primitive data is copied, while references still point to the same child objects. To give a copy independent mutable state, separate the necessary components or create a new copy via a copy constructor/factory with a clear contract.