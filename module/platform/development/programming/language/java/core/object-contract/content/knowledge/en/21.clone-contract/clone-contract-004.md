# `CloneNotSupportedException` when `Object.clone()` is not permitted

## Objectives

In Java, `Object.clone()` is a mechanism that supports creating object copies, but not every Java object can be cloned using this mechanism. If `Object.clone()` is called on an instance of a class **that does not implement `Cloneable`**, the method throws `CloneNotSupportedException`. To handle it properly, you need to understand the **runtime condition** of the clone mechanism, **method access permissions**, and **checked exceptions**.

After this lesson, you will:

- Explain accurately when `Object.clone()` throws `CloneNotSupportedException`.
- Understand why `Cloneable` is a marker interface and does not automatically provide a public `clone()` method.
- Write a class that calls `super.clone()` safely when `implements Cloneable` is present.
- Distinguish compile-time errors due to `protected` or checked exceptions from `CloneNotSupportedException` occurring at runtime.
- Analyze cases involving subclasses, arrays, shallow copies, and overridden `clone()` methods.
- Decide when to use a copy constructor or a `copy()` method instead of `Object.clone()`.

## 1. `Object.clone()` and the condition permitting copying

All regular Java classes inherit from `java.lang.Object` directly or indirectly. `Object` declares:

```java
protected Object clone() throws CloneNotSupportedException
```

There are three important factors:

1. **`protected`**: the default `clone()` method cannot be arbitrarily called on any object from external code. A class can override it to provide a `public` API.
2. **`throws CloneNotSupportedException`**: this is a **checked exception**. Code calling a method declared to potentially throw this exception must catch it or propagate it with `throws`, unless handled through another API that does not declare the exception.
3. **`Cloneable` condition at runtime**: when the `Object.clone()` implementation is actually used for an object lacking the `java.lang.Cloneable` marker, the call fails with `CloneNotSupportedException`.

The third condition applies based on the **actual runtime class of the object**. If an object inherits from a class that already implements `Cloneable`, it is also a `Cloneable` by interface inheritance.

### What is a marker interface?

`java.lang.Cloneable` is a **marker interface**, meaning it defines no methods. Writing:

```java
class Draft implements Cloneable {
    private int version;
}
```

makes an instance of `Draft` satisfy the signal recognized by `Object.clone()`. However, the line `implements Cloneable` alone **does not create a `public clone()` method in the class**. `clone()` remains the `protected` method inherited from `Object` if the class does not override it.

This distinguishes two questions:

- **Is the marker condition met for `Object.clone()` to support copying?** Yes if the runtime object is `Cloneable`.
- **Does the current calling code see a `clone()` method it can call?** Depends on access scope and how the class declares its API.

An object with the `Cloneable` marker that does not expose a public clone API may not allow calling `obj.clone()` from client code, even though the object itself is eligible when a valid method inside the class calls `super.clone()`.

## 2. Why is `CloneNotSupportedException` thrown?

The following example illustrates the exact failure case: class `Plain` **does not** implement `Cloneable` yet still declares a `public clone()` method and calls `super.clone()`.

```java
class Plain {
    private final int id;

    Plain(int id) {
        this.id = id;
    }

    @Override
    public Plain clone() throws CloneNotSupportedException {
        return (Plain) super.clone();
    }
}
```

The code above can **compile cleanly**: a class is permitted to override `Object.clone()` and call `super.clone()` from inside an instance method of the class itself. However:

```java
Plain original = new Plain(7);
Plain copy = original.clone(); // Throws CloneNotSupportedException at runtime
```

This is a snippet inside a method that handles or declares the checked exception. When calling `super.clone()`, the mechanism in `Object.clone()` checks the current object and sees that `Plain` does not implement `Cloneable`. Therefore, the exception is thrown **before a copy is returned**.

Distinguish clearly: declaring `clone()` as `public` here **is not** proof that the object is cloneable. Overriding only opens calling permission; the `Cloneable` marker is the signal used by `Object.clone()`.

### What does the exception mean?

`CloneNotSupportedException` is an exception class in `java.lang`, extending `Exception` and belonging to the checked exception group. It indicates that a clone operation was requested but is not supported by the mechanism in use.

With `Object.clone()`, the standard case is that the actual runtime class of the object does not implement `Cloneable`. However, a class that **overrides `clone()` itself** can still proactively throw the exception due to its own policy. One should not treat every occurrence of the exception as sole proof that the class definitely lacks the marker; check the stack trace and the executing implementation method.

## 3. Fixing the standard case: implement `Cloneable` and call `super.clone()`

A traditional clone pattern is:

```java
class CloneReady implements Cloneable {
    private final int id;

    CloneReady(int id) {
        this.id = id;
    }

    @Override
    public CloneReady clone() throws CloneNotSupportedException {
        return (CloneReady) super.clone();
    }
}
```

In this case:

- `implements Cloneable` supplies the marker for the runtime object.
- `@Override public CloneReady clone()` opens the public API and uses a **covariant return type** instead of `Object`.
- `super.clone()` uses `Object`'s copying mechanism. Since the instance is `Cloneable`, the operation is normally permitted.
- The cast `(CloneReady)` is valid for a copy of a `CloneReady` instance; the method returns the exact type to the caller.

Some classes may handle `CloneNotSupportedException` internally because they know the marker is always present by design. However, if the method still declares `throws` as in the example, client code must catch or declare the corresponding exception.

**Limitation:** `super.clone()` performs a **shallow copy** for reference fields: the original object and the copy have two distinct identities, yet some fields may point to the same child objects. The `Cloneable` marker does not automatically produce a "deep copy".

## 4. Complete Java 17+ program: failed clone, successful clone, and manual copy

Save the following file as `ClonePermissionDemo.java`:

```java
import java.util.Arrays;

public class ClonePermissionDemo {
    static final class Plain {
        private final int id;

        Plain(int id) {
            this.id = id;
        }

        @Override
        public Plain clone() throws CloneNotSupportedException {
            return (Plain) super.clone();
        }
    }

    static class CloneReady implements Cloneable {
        private final int id;
        private final int[] scores;

        CloneReady(int id, int[] scores) {
            this.id = id;
            this.scores = scores;
        }

        @Override
        public CloneReady clone() throws CloneNotSupportedException {
            return (CloneReady) super.clone();
        }

        int id() {
            return id;
        }

        int[] scores() {
            return scores;
        }
    }

    static final class Child extends CloneReady {
        Child(int id, int[] scores) {
            super(id, scores);
        }
    }

    static final class ManualCopy {
        private final int id;

        ManualCopy(int id) {
            this.id = id;
        }

        ManualCopy copy() {
            return new ManualCopy(id);
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Plain plain = new Plain(7);
        try {
            plain.clone();
            System.out.println("unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("plain rejected: "
                    + ex.getClass().getSimpleName());
        }

        CloneReady original = new CloneReady(11, new int[] {2, 3});
        CloneReady copy = original.clone();
        System.out.println("different instances: " + (original != copy));
        System.out.println("copied id: " + copy.id());
        System.out.println("same scores array: "
                + (original.scores() == copy.scores()));

        original.scores()[0] = 99;
        System.out.println("copy sees changed score: "
                + copy.scores()[0]);

        Child child = new Child(12, new int[] {4});
        CloneReady clonedChild = child.clone();
        System.out.println("child clone retains type: "
                + (clonedChild instanceof Child));

        int[] numbers = {5, 6};
        int[] numbersCopy = numbers.clone();
        System.out.println("array clone: "
                + (numbers != numbersCopy));
        System.out.println("array contents: "
                + Arrays.equals(numbers, numbersCopy));

        ManualCopy manual = new ManualCopy(15);
        ManualCopy manualCopy = manual.copy();
        System.out.println("manual copy works: "
                + (manual != manualCopy
                   && manual.id() == manualCopy.id()));
    }
}
```

Compile and run commands using JDK 17 or later:

```bash
javac ClonePermissionDemo.java
java ClonePermissionDemo
```

Expected output:

```text
plain rejected: CloneNotSupportedException
different instances: true
copied id: 11
same scores array: true
copy sees changed score: 99
child clone retains type: true
array clone: true
array contents: true
manual copy works: true
```

### Analysis of each result

- `Plain.clone()` calls `Object.clone()` when the instance does not implement `Cloneable`; the exception is caught so the program can continue.
- `CloneReady` implements the marker and has a valid clone method. `original != copy` is `true` because the copy is a new instance.
- `id` is an `int`, so the value 11 is copied into the new object.
- `scores` is `int[]`; `Object.clone()` copies the **reference** to the child array. Both instances hold the same array. When modifying `original.scores()[0]`, reading from `copy.scores()[0]` also sees 99.
- `Child` inherits from `CloneReady`, so the runtime `Child` object also implements `Cloneable`. `super.clone()` creates a copy preserving the actual runtime class `Child`, even though the method's declared return type is `CloneReady`.
- Java arrays have a built-in `clone()` mechanism; `numbers.clone()` creates a separate array with the same primitive elements.
- `ManualCopy` uses a constructor to create a new object. It does not need `implements Cloneable` because **it does not use `Object.clone()`**.

Note that this is an example for learning the mechanism, not a safe encapsulation model for mutable data: `CloneReady.scores()` returns the array reference directly. If the goal is an independent copy, an explicit copying policy for arrays/child objects is required.

## 5. Three easily confused cases: compile error, checked exception, and runtime exception

Not every situation involving the word `clone` leads to `CloneNotSupportedException` at runtime.

| Situation | Typical outcome | Cause |
| --- | --- | --- |
| Calling `new Plain(1).clone()`, where `Plain` has `public clone()` calling `super.clone()` without `Cloneable` | Throws `CloneNotSupportedException` at runtime | `Object.clone()` rejects the runtime object |
| Class only `implements Cloneable`, without opening `public clone()`, client code calls `instance.clone()` | Compile error due to access permissions | `Object.clone()` is still `protected` |
| Has `public clone() throws CloneNotSupportedException` but caller neither catches nor declares it | Compile error about checked exception | Java checks `throws` declarations |
| Class `implements Cloneable` and calls `super.clone()` validly | Creates a new object | Marker satisfies `Object.clone()`'s condition |
| Class uses `new` inside `copy()`, without calling `Object.clone()` | Creates a new object | Does not depend on the clone marker |
| An array calls `array.clone()` | Cloning is supported | Java arrays support clone by language mechanism |

### `protected` error differs from clone support exception

```java
class MarkerOnly implements Cloneable {
    private int value;
}

class Example {
    void demo() {
        MarkerOnly x = new MarkerOnly();
        // x.clone(); // Does NOT compile: Object.clone() is protected
    }
}
```

The illustration above has two classes and only serves to show access permissions. `implements Cloneable` does not automatically turn `clone()` into public.

### Checked exception must be handled

```java
// Placed inside a method that can call CloneReady.clone():
try {
    CloneReady cloned = original.clone();
    // Use cloned here.
} catch (CloneNotSupportedException ex) {
    throw new IllegalStateException("Unexpected clone failure", ex);
}
```

This is an illustrative snippet inside a method, with `original` of type `CloneReady` and `CloneReady` defined as in section 4. A class can choose to declare `throws CloneNotSupportedException` instead of `try/catch` if the API contract allows errors to be handled at an upper call level.

**Do not arbitrarily hide errors:** if the exception can actually occur due to a missing marker in the design, catching and returning `null` turns the error into another bug that is harder to detect. Choose an appropriate handling strategy: fix the contract, report the error, or use a dedicated copying mechanism.

## 6. `Cloneable` is evaluated by the actual runtime class

When calling `super.clone()`, the marker check is not merely based on the reference variable's name. It concerns the actual object being copied.

For example, if `Base implements Cloneable` and `Derived extends Base`, a `Derived` instance is still `Cloneable` even if the subclass declaration does not repeat the interface name. Conversely, if `Base` does not implement `Cloneable`, but `Derived` **does**, calling `Object.clone()` from an inherited method when executed on a `Derived` instance can be permitted.

Illustration:

```java
class Base {
    @Override
    public Base clone() throws CloneNotSupportedException {
        return (Base) super.clone();
    }
}

class Derived extends Base implements Cloneable {}

class Demo {
    static void check() throws CloneNotSupportedException {
        Base base = new Base();
        Derived derived = new Derived();

        // base.clone(); // Will throw CloneNotSupportedException if called
        Base copied = derived.clone(); // Succeeds: runtime type is Derived
        System.out.println(copied instanceof Derived); // true
    }
}
```

This is a standalone illustration of classes and a `check()` method; to run it, a `main` calling `Demo.check()` is needed. The rule shown here: **the Cloneable condition depends on the runtime class**, not just on the class declaring the `clone()` method.

It also shows that calling `super.clone()` **does not simply create `new Base()`**. When permitted, the resulting object preserves the actual runtime type.

## 7. If `Cloneable` is implemented, is every `clone()` guaranteed to succeed?

**There is no universal guarantee that every method named `clone()` on every class will succeed.** `Cloneable` is a special signal for the `Object.clone()` operation, but a class can override `clone()` and execute other logic, including rejecting cloning by its own policy.

For example, a class might decide not to support copying in its public API:

```java
class ForbiddenCopy implements Cloneable {
    @Override
    public ForbiddenCopy clone() throws CloneNotSupportedException {
        throw new CloneNotSupportedException("Copy forbidden by policy");
    }
}
```

When calling `new ForbiddenCopy().clone()`, the exception still occurs **even though the class implements `Cloneable`**, because the overriding method proactively throws the exception and does not call `Object.clone()`. That is the class's policy, distinct from `Object.clone()`'s marker check.

Some libraries also provide custom `clone()` implementations without calling `super.clone()`. In that case, the `Cloneable` marker is not the factor deciding all behavior. To determine the cause of an error, read the implementation and stack trace of the method actually being invoked.

## 8. Shallow clone is essential to understand before applying in production

Even when `Object.clone()` runs successfully, the result is not automatically a **deep copy**. By the default mechanism, primitive fields are copied by value; reference fields are copied by **reference**, without recursively cloning each child object.

```text
Original CloneReady        Copied CloneReady
  id = 11                    id = 11
  scores ──────┐             scores ──────┐
               │                          │
               └────► int[] {2, 3} ◄──────┘

Two different CloneReady instances; only one scores array.
```

This is why the example in section 4 prints:

```text
same scores array: true
copy sees changed score: 99
```

When an independent copy is required, the class can copy mutable fields after `super.clone()` or use a copy constructor to create copies of mutable fields. For example, the following approach is often easy to read when fields have simple structures:

```java
final class DataSnapshot {
    private final int[] values;

    DataSnapshot(int[] values) {
        this.values = values.clone();
    }

    DataSnapshot copy() {
        return new DataSnapshot(values);
    }

    int[] values() {
        return values.clone();
    }
}
```

This snippet illustrates a class not using `Object.clone()`: the constructor and accessor copy the array to avoid sharing the mutable array externally. For a graph containing complex objects or reference cycles, a deep copying policy must be designed specifically.

### Why doesn't array `clone()` throw `CloneNotSupportedException`?

Java arrays support cloning and have an appropriate `clone()` method provided by the language. Arrays are `Cloneable`, so `array.clone()` creates a new array. Primitive-type elements are copied by value; for object arrays, element references are copied, so the copy is still a shallow copy at the level of element references.

```java
StringBuilder[] builders = {new StringBuilder("A")};
StringBuilder[] copied = builders.clone();

System.out.println(builders != copied);       // true
System.out.println(builders[0] == copied[0]); // true
```

These lines are inside a method. The outer array is cloned into a new object, yet both arrays hold references to the same `StringBuilder`.

## 9. Designing a copy API when you do not want to rely on `Object.clone()`

`Cloneable` and `Object.clone()` are long-standing mechanisms in Java, but they are not always the best choice for a business model. Other common alternatives:

**Copy constructor:**

```java
final class PointData {
    private final int x;
    private final int y;

    PointData(int x, int y) {
        this.x = x;
        this.y = y;
    }

    PointData(PointData source) {
        this(source.x, source.y);
    }
}
```

**Factory or `copy()` method** with an explicit name:

```java
final class UserSettings {
    private final String theme;

    UserSettings(String theme) {
        this.theme = theme;
    }

    UserSettings copy() {
        return new UserSettings(theme);
    }
}
```

The two snippets above are standalone class declarations as examples. Both techniques work without `implements Cloneable`. They allow constructors to check invariants, decide deep/shallow copying, and design a clear API for callers.

With a **truly immutable record** containing immutable values, sometimes no copy needs to be created: the same data can already be reused by design. If a record contains mutable child objects like arrays, separate defensive copying must be considered. You should not force `Object.clone()` just because you want to "copy something".

These alternatives do not change the cause of `CloneNotSupportedException`: the exception still occurs if you actually invoke `Object.clone()` with an object that does not meet the marker condition.

## 10. Common mistakes

1. **Forgetting `implements Cloneable` while still calling `super.clone()`.** The class may compile, but `Object.clone()` will throw `CloneNotSupportedException` when the runtime object lacks the marker.
2. **Thinking `implements Cloneable` automatically creates `public clone()`.** Incorrect; `Cloneable` declares no methods. Without overriding, the method inherited from `Object` remains `protected`.
3. **Confusing access errors with clone support exceptions.** A call blocked by `protected` fails at compile time, rather than waiting until runtime to throw `CloneNotSupportedException`.
4. **Failing to catch or declare the checked exception.** If the `clone()` signature declares `throws CloneNotSupportedException`, callers must handle it per Java rules.
5. **Assuming a subclass that does not write `implements Cloneable` itself is guaranteed to fail cloning.** The marker is inherited through the type hierarchy.
6. **Assuming an overridden `clone()` method cannot reject cloning when the class is `Cloneable`.** A class can define its own policy and throw an exception.
7. **Assuming a successful clone is a deep copy.** `Object.clone()` copies shallowly; references to mutable objects may still be shared.
8. **Catching the exception and ignoring it or returning `null`.** This hides the cause and may cause `NullPointerException` later. Fix the contract or establish a clear handling strategy.
9. **Using clone when you just need a new object from known data.** A copy constructor or factory is usually simpler and avoids marker/checked exception requirements.
10. **Assuming every method named `clone()` calls `Object.clone()`.** Inspect the overriding code; a method may construct a new object itself or reject without calling `super.clone()`.

## 11. Self-check exercises

### Question 1 — Predict the cause

Given the snippet:

```java
class Document {
    @Override
    public Document clone() throws CloneNotSupportedException {
        return (Document) super.clone();
    }
}
```

When calling `new Document().clone()` inside a valid `try/catch`, what is the result?

**Answer:** `CloneNotSupportedException` because `Document` does not implement `Cloneable` yet calls `Object.clone()`.

### Question 2 — Marker without a public API

```java
class Document implements Cloneable {
    private String text;
}
```

Can client code in a class without `protected` access call `document.clone()` directly?

**Answer:** No. `Cloneable` does not declare a public `clone()` method. The class needs to expose a public copying API or provide another method.

### Question 3 — Subclass

```java
class Parent implements Cloneable {
    @Override
    public Parent clone() throws CloneNotSupportedException {
        return (Parent) super.clone();
    }
}

class Child extends Parent {}
```

If `Child child = new Child();`, can calling `Parent p = child.clone();` succeed, and what is `p instanceof Child`?

**Answer:** Yes, because `Child` inherits the `Cloneable` marker and the public clone method. `p instanceof Child` is `true` because `Object.clone()` preserves the exact runtime class.

### Question 4 — Copying by custom policy

If a class does not want mutable objects to be shared after copying, is adding `implements Cloneable` alone enough?

**Answer:** Not yet. You need to control copying of mutable reference fields, use clone/copy constructors with defensive copying, or a deep-copy approach designed for the specific data structure.

## Remember

`CloneNotSupportedException` occurs in the typical case when **`Object.clone()` is asked to copy a runtime object that does not implement `Cloneable`**. `Cloneable` is a marker interface and does not provide `public clone()` out of the box; the original `Object.clone()` method is `protected` and declares a checked exception. To expose a clone API using the default mechanism, a class needs to support the marker and usually overrides `clone()` to validly call `super.clone()`. After a successful clone, remember it may still be a shallow copy; when an explicit copying policy is needed, a copy constructor or `copy()` is a suitable alternative.