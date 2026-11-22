# `Object.clone()` has `protected` access in Java

`clone()` is a method declared by `java.lang.Object`, but unlike `equals()`, `hashCode()`, and `toString()`, **`Object.clone()` has `protected` access**, not `public`. This directly affects which classes are allowed to call the method, how to build a copying API for external callers, and why an object that `implements Cloneable` still might not be able to have `.clone()` called on it from client code.

This lesson explains **two independent conditions**: *compile-time access permission* and *runtime cloneability*. It is also necessary to understand that `Object.clone()` creates a shallow copy, arrays have special rules, and in many cases a **copy constructor** or **factory method** is easier to maintain.

## 1. Signature and meaning of `Object.clone()`

In the `Object` API, the equivalent signature is:

```java
protected native Object clone()
        throws CloneNotSupportedException;
```

`native` is a declaration detail of common JDK implementations; the contract focus here is `protected`, return type `Object`, and checked exception `CloneNotSupportedException`.

According to the contract of `Object.clone()`:

- If the executing object's class **does not implement `java.lang.Cloneable`**, the default invocation throws `CloneNotSupportedException`.
- If the object supports default cloning, the method creates a new object of the same runtime class and copies the values of the original object's fields. Reference fields **still point to the same referenced objects**: this is a **shallow copy**.
- Creating this copy **does not call the constructor of the cloned class** the way initializing a new instance with `new` does.
- `Object.clone()` returns `Object`. An overriding class can use a **covariant return type** to return a more specific type, such as `AccountKey clone()`.

Some common expectations are `x.clone() != x`, `x.clone().getClass() == x.getClass()`, and `x.clone().equals(x)`; however, those are not laws applicable to **every** custom clone implementation. The important part is that a type can provide a specific copying contract, and users need to know what it copies.

`Object.clone()` differs from `Object.equals()` in two aspects: access level (`protected` instead of `public`) and a checked exception. It also differs from a copy constructor, whose signature and copying policy are designed by the class itself.

## 2. Where does `protected` allow calling `clone()`?

In Java, a `protected` member can be accessed from **classes in the same package as the declaring class**, and from **subclasses in a different package**, though the case of a subclass in another package is also subject to conditions on access context/receiver expression type.

`Object` is declared in `java.lang`. Application code usually does not belong to `java.lang`, so it cannot arbitrarily call `Object.clone()` on an arbitrary variable:

```java
Object obj = new Object();
// obj.clone(); // COMPILE ERROR: clone() has protected access in Object.
```

This is a **non-standalone illustrative snippet**; the erroneous line is placed in a comment to distinguish it from valid Java code. Every Java class inheriting from `Object` **does not mean any piece of code can call `clone()` on every object**.

Inside a subclass of `Object`, calling `super.clone()` **inside the body of a method of the subclass itself** can be valid in terms of access permission:

```java
class Draft implements Cloneable {
    public Draft copy() throws CloneNotSupportedException {
        return (Draft) super.clone();
    }
}
```

This is a **class declaration snippet**, compilable when placed in an appropriate Java file. The line `super.clone()` is allowed because the method is written inside the subclass; the `implements Cloneable` marker enables default cloning to succeed at runtime.

### 2.1. Override as `public` if you want to expose the clone operation publicly

Example:

```java
final class Document implements Cloneable {
    @Override
    public Document clone() {
        try {
            return (Document) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

This is a **declaration fragment**, not a program with `main`. `Document.clone()` is declared `public`, so other code can call the method on expressions with static type `Document`. The class is marked `Cloneable`, so with an unchanged structure, `super.clone()` throwing `CloneNotSupportedException` is an abnormal situation and is converted into `AssertionError`.

**Important note:** compile-time access checking is based on the **static type of the calling expression**. If you write:

```java
Document doc = new Document();
Document copy = doc.clone();  // Valid: Document.clone() is public.

Object obj = doc;
// obj.clone();               // Invalid: Object.clone() is protected.
Document copy2 = ((Document) obj).clone(); // Valid after cast.
```

All three lines above are an **illustrative snippet**; to run standalone they need to be wrapped in `main` alongside the `Document` declaration. Even though `obj` points to `Document`, a variable with static type `Object` does not make `Object.clone()` public.

**Cannot reduce visibility when overriding:** if a superclass has already declared `public clone()`, a subclass overriding it must continue declaring it `public`. Conversely, Java allows overriding a `protected` method as `public`, as in the example above.

### 2.2. Two packages and an easily confused access rule

Suppose class `LibraryItem` is in package `library`:

```java
// File library/LibraryItem.java
package library;

public class LibraryItem implements Cloneable {
    @Override
    protected LibraryItem clone()
            throws CloneNotSupportedException {
        return (LibraryItem) super.clone();
    }
}
```

And the calling code is in package `app`:

```java
// File app/UseItem.java
package app;
import library.LibraryItem;

public class UseItem {
    public static void main(String[] args) throws Exception {
        LibraryItem item = new LibraryItem();
        // item.clone(); // ERROR: protected, different package.
    }
}
```

These are **two illustrative files following the exact paths**, in which the error-causing statement is commented out. From `app`, even though `LibraryItem` implements `Cloneable`, calling `item.clone()` is still invalid because `clone()` is only `protected`.

A subclass of `LibraryItem` in package `app` can call `super.clone()` **inside a method of the subclass itself**. However, one should not generalize that access permission into arbitrarily calling `clone()` on another `LibraryItem` variable in the same `app` package. For a protected member originally declared in another package, Java restricts access through the receiver expression, in addition to requiring the calling class to be an appropriate subclass.

For a public API that needs copying, the common solution is to **expose an explicit `public` method** on the type or use a copy constructor/factory instead of forcing client code to rely on protected rules.

## 3. `Cloneable` does not declare a `clone()` method

`java.lang.Cloneable` is a **marker interface**: it has no `clone()` method to call. It informs `Object.clone()` that the object permits the default clone operation.

Distinguish:

| Question | Deciding mechanism |
| --- | --- |
| Can `x.clone()` be called from this source code location? | **Java access rules**, static type of `x`, whether the method has been overridden as public |
| Does `super.clone()` throw `CloneNotSupportedException`? | Whether the runtime object implements `Cloneable` (or the class has a custom clone method with a different contract) |
| How are values copied? | The `Object.clone()` contract is **shallow copy**; an overriding class can proactively copy more |
| What is the declared return type of the copy? | The return type of the clone method can be `Object` or a more specific type via covariant return |

Merely writing:

```java
class MarkerOnly implements Cloneable {
    private int value;
}
```

does not create a **public `clone()`**. Code in another package cannot write `new MarkerOnly().clone()` solely because of `implements Cloneable`. The `Cloneable` interface has no method named `clone()` to guarantee a public calling interface.

Conversely, a class can write `public T copy()` itself using a constructor to create a copy **without** implementing `Cloneable`. Therefore, avoid equating "having a copy API" with "permitting `Object.clone()`".

## 4. Java 17+ program distinguishing access permission and runtime cloneability

Create file **`CloneAccessDemo.java`**:

```java
public class CloneAccessDemo {
    static final class WithoutMarker {
        private final int id;

        WithoutMarker(int id) {
            this.id = id;
        }

        WithoutMarker copyUsingSuper()
                throws CloneNotSupportedException {
            return (WithoutMarker) super.clone();
        }
    }

    static final class WithMarker implements Cloneable {
        private final int id;

        WithMarker(int id) {
            this.id = id;
        }

        @Override
        public WithMarker clone() {
            try {
                return (WithMarker) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        WithoutMarker a = new WithoutMarker(7);
        try {
            a.copyUsingSuper();
            System.out.println("unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("without marker: not supported");
        }

        WithMarker original = new WithMarker(42);
        WithMarker copy = original.clone();

        System.out.println("same instance: "
                + (original == copy));
        System.out.println("same id: "
                + (original.id() == copy.id()));
        System.out.println("copy class: "
                + copy.getClass().getSimpleName());
    }
}
```

Compile and run:

```bash
javac CloneAccessDemo.java
java CloneAccessDemo
```

Stdout:

```text
without marker: not supported
same instance: false
same id: true
copy class: WithMarker
```

**Explanation:**

1. `WithoutMarker.copyUsingSuper()` is inside a subclass of `Object`, so `super.clone()` is **valid at compile time**, but the instance **does not implement `Cloneable`**, so `Object.clone()` throws `CloneNotSupportedException`.
2. `WithMarker` implements `Cloneable` and overrides `clone()` as `public`: code in `main` can call it, resulting in a different instance while preserving the `id` field.
3. The return type is `WithMarker`, not `Object`, thanks to **covariant return type**, so the caller does not need to cast.
4. `getSimpleName()` is used to display the resulting type; this is not independent proof that the copy deep-copied reference fields.

The code above solves **two different problems**: calling permission is widened by a `public` override; `super.clone()` works thanks to the `Cloneable` marker.

## 5. `Object.clone()` performs a shallow copy

When copying fields by default, primitive variables have their **values** copied; whereas reference-type fields have their **references** copied. This leads to the original and the clone holding the same mutable child object.

Create file **`ShallowCloneDemo.java`**:

```java
public class ShallowCloneDemo {
    static final class Report implements Cloneable {
        private final String name;
        private int[] scores;

        Report(String name, int[] scores) {
            this.name = name;
            this.scores = scores;
        }

        @Override
        public Report clone() {
            try {
                return (Report) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int[] scores() {
            return scores;
        }
    }

    public static void main(String[] args) {
        Report first = new Report("Q1", new int[] {2, 4});
        Report second = first.clone();

        System.out.println("same report: "
                + (first == second));
        System.out.println("same scores array: "
                + (first.scores() == second.scores()));

        second.scores()[0] = 9;
        System.out.println("first score: "
                + first.scores()[0]);

        int[][] grid = {{1, 2}, {3}};
        int[][] gridCopy = grid.clone();

        System.out.println("same outer array: "
                + (grid == gridCopy));
        System.out.println("same inner row: "
                + (grid[0] == gridCopy[0]));
    }
}
```

Run:

```bash
javac ShallowCloneDemo.java
java ShallowCloneDemo
```

Output:

```text
same report: false
same scores array: true
first score: 9
same outer array: false
same inner row: true
```

`Report.clone()` creates a new `Report` object, but `scores` of both instances point to **the same `int[]` array**. Therefore, modifying the array via `second` is visible through `first`.

**Special point about arrays:** Java arrays provide a **public** `clone()` operation even though `Object.clone()` is `protected`; the copy is a new array of the same runtime type. A one-dimensional primitive array copies primitive values so it is independent in element contents. However, `int[][]` is an array of `int[]` elements: `grid.clone()` only copies the outer array, **the rows remain shared references**. Arrays also implement `Cloneable` and `Serializable`; no manual override is needed.

Note that the `Report` example intentionally exposes the mutable array via `scores()` to demonstrate shallow copy. This is not recommended data encapsulation design for every application.

## 6. If mutable data needs to be separated, clone must have a clear copying policy

A class containing a mutable array can override `clone()` to clone the child array after calling `super.clone()`. Create file **`IndependentCloneDemo.java`**:

```java
public class IndependentCloneDemo {
    static final class ScoreCard implements Cloneable {
        private int[] scores;

        ScoreCard(int[] input) {
            scores = input.clone();
        }

        int get(int index) {
            return scores[index];
        }

        void set(int index, int value) {
            scores[index] = value;
        }

        @Override
        public ScoreCard clone() {
            try {
                ScoreCard copy = (ScoreCard) super.clone();
                copy.scores = scores.clone();
                return copy;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        ScoreCard original = new ScoreCard(new int[] {2, 4});
        ScoreCard copied = original.clone();

        copied.set(0, 99);
        System.out.println("original score: " + original.get(0));
        System.out.println("copied score: " + copied.get(0));
        System.out.println("same instance: "
                + (original == copied));
    }
}
```

Commands:

```bash
javac IndependentCloneDemo.java
java IndependentCloneDemo
```

Stdout:

```text
original score: 2
copied score: 99
same instance: false
```

Here the class copies the input array to avoid unintended sharing, and then `clone()` additionally copies the `scores` array. The clone and the original can be modified independently.

**Limitations to understand:**

- For an array containing **mutable objects**, calling `array.clone()` only separates the outer array; the elements remain the same references. To deep copy, you must define how to copy **each element** appropriately for the business semantics.
- For a `final` reference field, you cannot reassign it to a separate copy inside `clone()` such as `copy.scores = ...` if `scores` is `final`. Forcing a deep clone design onto a complex immutable object may be unsuitable; usually a copy constructor/factory should be chosen.
- For resources such as locks, sockets, threads, file handles, or database connections, **you must not by default copy references** or assume the object can be duplicated. An ownership and resource lifecycle policy must be defined.
- If an object has invariants that need to be established in the constructor, `Object.clone()` does not run the constructor so it may not be appropriate for re-initializing those invariants.

Distinguish **deep copy** and **immutability**: a value object referencing only truly immutable components can use shallow copy while remaining semantically safe, because shared components cannot be modified. It is not necessary to deep-copy every field.

## 7. Checked exception and signature when overriding

`Object.clone()` declares `throws CloneNotSupportedException`. When overriding, a subclass has three common options:

1. **Keep the checked exception** if you want callers to handle the case where cloning is not possible.
2. **Do not declare the checked exception** when the class proactively implements `Cloneable` and `super.clone()` is expected to always succeed by the current design; catch and convert it to `AssertionError` as in the example.
3. **Do not use `Object.clone()`** and expose a different copying operation (`copy()` or a copy constructor), depending on the API intent.

An override cannot broaden the set of checked exceptions compared to the parent method; it can narrow or omit the checked exception declaration. `@Override` helps the compiler verify the exact signature. **Throwing `CloneNotSupportedException` is a mechanism of `Object.clone()`**, not a protected access error: access errors are usually detected **at compile time**.

In an inheritance hierarchy, `super.clone()` calls the clone implementation of the nearest superclass; if the superclass overrides clone and adds behavior, the result depends on that contract. Whether a subclass clones properly also depends on the field structure and invariants of each class in the inheritance chain.

## 8. When should you use a copy constructor or `copy()`?

`Cloneable`/`Object.clone()` has several awkward points:

- The `Cloneable` interface does not provide a `public clone()` method in its contract.
- `Object.clone()` is `protected`, requiring an override or another public method for external callers to use.
- Default cloning is shallow; with nested data, you must define the depth and handle resources yourself.
- `Object.clone()` does not call constructors the way normal instance creation does, which can conflict with invariants and initialization policies.
- An inheritance hierarchy containing both mutable and final fields can make it difficult to consistently define extensible cloning.

A copy constructor helps you proactively choose which fields are copied, how new data is created, how invariants are checked, and how to name it:

```java
final class Labels {
    private final String[] values;

    Labels(String[] input) {
        values = input.clone();
    }

    Labels(Labels other) {
        this(other.values);
    }

    String[] valuesCopy() {
        return values.clone();
    }
}
```

This is a **class declaration fragment**, not a program with `main`. Inputs are assumed non-`null`; if the API permits null, checks or a normalization policy need to be added. For a `String[]` array (immutable `String` elements), cloning the array suffices to separate element slot mutability. When elements are mutable objects, further copying rules are needed.

A copy constructor can call the regular constructor, validating invariants along the exact same path. However, a copy constructor also does not automatically create a deep copy if it merely assigns shared references; **copy depth must be designed** in any API.

If an object is truly **immutable**, returning the same instance in a method defined to obtain an immutable value may be a reasonable policy, though one should not assume that is the default behavior of `Object.clone()`.

## 9. Process for choosing a copy API for a new class

**Step 1 — Determine the copying need.** Does the caller need a different instance or just an equivalent value? Is child data allowed to be shared?

**Step 2 — Determine accessibility.** Is calling code in another package? If exposing a clone API, override as `public` and consider a specific return type.

**Step 3 — Choose to support `Cloneable` intentionally.** Mark `implements Cloneable` if the class intends to call `Object.clone()`; having only the marker interface is not enough to expose clone publicly.

**Step 4 — Choose copy depth.** Data consisting only of primitives and immutable values can accept shallow copy; mutable arrays/lists/maps or resources require explicit copy/share/reject decisions.

**Step 5 — Check invariants, superclasses, and subclasses.** Each class on the inheritance chain may have state needing handling. `final` fields, constructors, and clone access permissions must be considered together.

**Step 6 — Check exceptions and public API contract.** If you do not want callers handling checked exceptions, only remove `throws CloneNotSupportedException` when there is a reasonable handling plan in the override.

**Step 7 — Evaluate copy constructor or factory.** If cloning requires many complex initialization operations, an intentional copy method is usually easier to test and maintain.

## 10. Common mistakes

| Statement or coding style | Problem | Appropriate approach |
| --- | --- | --- |
| "Every object can call `.clone()`." | `Object.clone()` is `protected` | Only call according to access rules, or provide a `public` API |
| "`implements Cloneable` creates a public `clone()`." | `Cloneable` is a marker interface, declaring no methods | Override `public clone()` if needed |
| "`super.clone()` compiles so it will succeed at runtime." | Not implementing `Cloneable` can throw a checked exception | Ensure both calling permission and the marker |
| "Calling `obj.clone()` works because runtime type has public clone." | Static type `Object` makes only protected `Object.clone()` visible | Use an appropriate API type or controlled cast |
| "Cloning a record/object with an array is a deep clone." | `Object.clone()` copies references | Copy mutable components when needed |
| "Two-dimensional array `clone()` copies every row." | Only copies the outer array | Copy each row if independence is desired |
| "Clone calls the constructor so invariants re-initialize automatically." | Object.clone does not go through normal constructors | Choose a copying mechanism that allows invariant validation |
| "Using clone is best for every object." | Hard to determine deep/shallow, resource lifecycle, and inheritance | Consider copy constructor/factory |
| "`CloneNotSupportedException` is a protected error." | It is a runtime exception from the clone operation, not a compile-time access error | Distinguish the two phases |
| "Copying a `final` reference guarantees independence." | The referenced inner object may still be mutable | Check deep immutability or copy intentionally |

## 11. Code review checklist

- [ ] Is there a clear distinction between **`protected` access scope** and the **`Cloneable` condition**?
- [ ] Can callers in other packages access the public method intended for copying?
- [ ] Does the `clone()` override have the right signature, return type, and access level?
- [ ] Is `super.clone()` used in a place valid under Java access rules?
- [ ] If `CloneNotSupportedException` can occur, is the handling policy clear?
- [ ] Has the copy depth been determined for each primitive field, array, collection, mutable object, and resource?
- [ ] For multi-dimensional arrays, are rows still shared after `clone()`? Does that match requirements?
- [ ] Are constructors/invariants, `final` fields, and superclass contracts respected?
- [ ] Are there tests verifying that the original and clone are different instances and for independent mutations when needed?
- [ ] Should `copy()` or a copy constructor be used to make the API clearer?

**Remember:** `Object.clone()` is **`protected`**, and `Cloneable` is only a sign of default clone support. To let external callers perform copying, a class usually needs to expose a `public` API with a clear depth and exception contract. `super.clone()` primarily creates a **shallow copy**; if data contains mutable components, the design must decide precisely which parts are shared and which parts are duplicated.
