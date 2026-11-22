# Comparing Explicit Copying with `Object.clone()` in Java

## 1. Objectives and Key Conclusions

In Java, **object copying** means creating a new object from the information of an existing object. However, “creating a new object” does not specify the **degree of state independence**: two objects can still share the same arrays, lists, or mutable components.

Two common approaches:

- **Explicit copying**: defining your own copy constructor, static copy factory, or `copy()` method; using `new` and actively choosing fields, validations, shallow/deep copying, and the resulting contract.
- **`Object.clone()`**: a built-in mechanism in `java.lang.Object`. If the runtime object supports `Cloneable` per the contract, the base implementation of `clone()` creates a new object by **copying the fields**, which defaults to a **shallow copy**. The constructor does not run in the usual way of creating an object with `new`.

Both approaches can create a **new object identity**; however, they differ in API, accessibility, exceptions, constructors/invariants, inheritance, and how mutable components are handled.

> **Basic recommendation:** For a class you design yourself, especially with invariants, `final` fields, or mutable nested objects, **an explicit copy constructor/static factory is usually easier to read, verify, and maintain**. `clone()` still needs to be understood and used properly when an API or hierarchy already specifies a clone contract.

This lesson focuses on **comparing explicit copying with `Object.clone()`**, without equating copying with reference assignment, serialization, conversion, or Java garbage collection.

## 2. Reference Assignment Is Not Object Copying

First, identify accurately what is being copied.

```java
Box first = new Box(10);
Box alias = first;
```

`alias = first` only copies the **reference value**. There is no `new`, no constructor call, and no second Box object created.

Diagram:

```text
first ─────┐
           ├────> Box object X { value: 10 }
alias ─────┘
```

If `alias` changes the mutable state of object X, `first` sees that change.

For a copy that creates a new object:

```java
Box copy = new Box(first.value());
```

the diagram is:

```text
first ─────────> Box object X { value: 10 }
copy  ─────────> Box object Y { value: 10 }
```

`first == copy` is false if there are two separate objects; however, `first.value()==copy.value()` is true.

**Distinction:** “same data” does not mean “same object”; “different objects” also **does not guarantee that all child objects are different** if there is a shallow copy.

## 3. First Example: Creating an Explicit Copy with a Constructor

Create the file **`ExplicitCopyBasicsDemo.java`**:

```java
final class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    Box(Box source) {
        this.value = source.value;
    }

    int value() {
        return value;
    }

    void change(int value) {
        this.value = value;
    }
}

public class ExplicitCopyBasicsDemo {
    public static void main(String[] args) {
        Box original = new Box(10);
        Box copy = new Box(original);

        System.out.println(original == copy);
        System.out.println(original.value() == copy.value());

        copy.change(20);

        System.out.println("original=" + original.value());
        System.out.println("copy=" + copy.value());
    }
}
```

Run with JDK 17+:

```bash
javac ExplicitCopyBasicsDemo.java
java ExplicitCopyBasicsDemo
```

**Standard output:**

```text
false
true
original=10
copy=20
```

The `Box(Box source)` constructor is a **copy constructor**: it takes a source object and uses `new Box(original)` to create a new object.

Because `value` is a primitive `int`, assigning the field value to the other field is sufficient. Afterward, `copy.change(20)` does not change `original.value`.

**Key point:** The body of the copy constructor clearly shows **which fields are being copied** and according to which strategy. For fields of mutable reference types, you must actively decide whether to share or deep-copy them.

## 4. What Is `Object.clone()`?

The root class `java.lang.Object` defines a method with the conceptual signature:

```java
protected native Object clone() throws CloneNotSupportedException;
```

This is an **API signature for learning**, not a standalone class source.

Important characteristics:

1. `clone()` in Object has **`protected`** accessibility, not public.
2. The method returns `Object` per its declaration in Object; subclasses can **override it with a covariant return type** such as `Ticket`.
3. `Object.clone()` can throw the checked exception `CloneNotSupportedException`.
4. The runtime object must satisfy the `Cloneable` marker contract for Object's base implementation to allow normal cloning; otherwise, it throws an exception.
5. The copy created by Object's implementation has its **field values copied**; it is a **shallow copy** for reference fields.
6. The constructor of the cloned object is **not called** following the `new ClassName(...)` procedure.
7. Subclasses can override `clone()` to handle additional fields or mutable references, but must manage the contract carefully.

**Do not assume** that every object in Java has a public `clone()`. The method exists in Object, yet it is protected, and not every runtime class is permitted to be cloned using the base implementation.

## 5. `Cloneable` Is a Marker Interface, Not an Interface with `clone()`

`java.lang.Cloneable` is a **marker interface**: it signals to `Object.clone()` that a class instance permits field-for-field cloning.

Common point of confusion:

```java
class Ticket implements Cloneable {
}
```

`Ticket` is marked Cloneable, but this line **does not automatically generate a public `Ticket.clone()` method**. The `Cloneable` interface **does not declare** a `clone()` method for callers to invoke through a variable of type Cloneable.

Therefore:

```java
// Cloneable marker = new Ticket();
// marker.clone(); // Invalid: Cloneable does not have a public clone().
```

When a class wants to allow external code to copy it, it usually must **override `clone()` and widen access to `public`**, or provide another copy method.

**Distinguish between two things:**

- `implements Cloneable`: allows the `Object.clone()` path to work when called properly.
- `public clone()`: the API provided by the class itself so callers can invoke the clone method.

There is no special `implements Cloneable` syntax that automatically calls constructors or deep-copies nested objects for you.

## 6. A Properly Working Public `clone()`

Create **`BasicCloneDemo.java`**:

```java
final class Ticket implements Cloneable {
    private int number;

    Ticket(int number) {
        this.number = number;
    }

    int number() {
        return number;
    }

    void renumber(int next) {
        number = next;
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class BasicCloneDemo {
    public static void main(String[] args) {
        Ticket original = new Ticket(10);
        Ticket copied = original.clone();

        System.out.println(original == copied);
        System.out.println(original.number() == copied.number());

        copied.renumber(20);

        System.out.println("original=" + original.number());
        System.out.println("copied=" + copied.number());
    }
}
```

```bash
javac BasicCloneDemo.java
java BasicCloneDemo
```

```text
false
true
original=10
copied=20
```

### Explanation

- The runtime class Ticket implements Cloneable, so `super.clone()` is permitted to create a field-for-field copy of Ticket.
- `super.clone()` has compile-time return type `Object`, so the `(Ticket)` cast is valid under the clone contract in this case.
- The override uses the covariant return type `Ticket`, saving callers from having to cast.
- The override does not declare a checked exception; it handles `CloneNotSupportedException` with an `AssertionError` because the final class Ticket guarantees the marker contract itself.
- `number` is a primitive, so original and copied have separate `int` values.
- Because the class has no mutable reference fields, a shallow copy is sufficient for the example state.

**Do not mechanically apply this approach to catching `CloneNotSupportedException` to every hierarchy.** If a superclass has a special clone policy or code may fail to satisfy the marker contract, error handling needs to rely on that contract.

## 7. What If `Cloneable` Is Not Implemented?

A class can override `clone()` and make it public, but if `super.clone()` is used on an instance that **does not implement Cloneable**, `Object.clone()` will throw `CloneNotSupportedException`.

Create **`CloneWithoutMarkerDemo.java`**:

```java
class Plain {
    @Override
    public Plain clone() throws CloneNotSupportedException {
        return (Plain) super.clone();
    }
}

public class CloneWithoutMarkerDemo {
    public static void main(String[] args) {
        Plain source = new Plain();

        try {
            source.clone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("clone rejected");
        }
    }
}
```

```bash
javac CloneWithoutMarkerDemo.java
java CloneWithoutMarkerDemo
```

```text
clone rejected
```

Here, the `Plain.clone()` method **can be called from a caller** because it is public, but the internal `super.clone()` call is rejected because Plain does not implement Cloneable.

**Do not confuse compile-time with runtime:** With `Object obj = new Object()`, `obj.clone()` is not permitted from an arbitrary caller because Object's method is protected; that is an **accessibility** issue. In the Plain example, the caller can invoke the public override, yet it fails at runtime because of the **Cloneable marker**.

You can write an explicit copy method for `Plain` without needing Cloneable:

```java
Plain copy() {
    return new Plain();
}
```

This is an illustrative method snippet and does not imply that copying data is complete when Plain has additional fields; its purpose is to show that the constructor-copy approach does not rely on the marker contract.

## 8. Does the Constructor Run When Calling `Object.clone()`?

This is a major difference between `new` and `Object.clone()`.

Explicit copying using:

```java
new Ticket(source.number())
```

is a normal constructor invocation, so the constructors/initializers needed for the new object are executed.

The `super.clone()` path based on `Object.clone()` creates an object via the clone mechanism **without executing the constructor of the class being cloned**.

Create **`CloneConstructorDemo.java`**:

```java
final class Stamp implements Cloneable {
    static int constructorCalls;

    private final int value;

    Stamp(int value) {
        constructorCalls++;
        this.value = value;
    }

    Stamp copy() {
        return new Stamp(value);
    }

    @Override
    public Stamp clone() {
        try {
            return (Stamp) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CloneConstructorDemo {
    public static void main(String[] args) {
        Stamp source = new Stamp(5);
        System.out.println("after source=" + Stamp.constructorCalls);

        Stamp cloned = source.clone();
        System.out.println("after clone=" + Stamp.constructorCalls);

        Stamp copied = source.copy();
        System.out.println("after copy=" + Stamp.constructorCalls);

        System.out.println(source == cloned);
        System.out.println(source == copied);
    }
}
```

```bash
javac CloneConstructorDemo.java
java CloneConstructorDemo
```

```text
after source=1
after clone=1
after copy=2
false
false
```

**Important observations:**

- `new Stamp(5)` calls the constructor once.
- `source.clone()` calls the Object.clone path but does **not** call `Stamp(int)`, so the counter does not increment.
- `source.copy()` calls `new Stamp(value)`; the counter increments.
- Both return an object with a different identity from source.
- The final primitive `value` in the cloned Stamp has its value copied as part of the field-copy operation, not reassigned by the constructor.

### Design Implications

If the constructor generates a new ID, increments a counter, validates, registers a listener, allocates a resource, or records an audit entry, clone can **bypass** those side effects. This may or may not fit the domain's definition of “copy”.

For example, should the ID of two copies remain the same or be generated anew? There is no universal answer: that is a business policy that **explicit copying makes clearer**.

## 9. What Is `Object.clone()` Shallow Copying?

An object has fields:

```java
class Report {
    int version;
    String title;
    int[] counts;
}
```

Suppose `Report` implements Cloneable and validly overrides clone to call `super.clone()`.

Field-for-field copy means:

- `version` is a primitive: the numeric value is copied.
- `title` is a reference to an immutable String: the reference is copied; sharing a String is usually safe.
- `counts` is a reference to a **mutable array**: the reference is copied, so clone and source point to the same array.

Diagram:

```text
source Report S --counts--+
                          +----> int[] X [1, 2]
clone  Report C --counts--+

source != clone
source.counts == clone.counts
```

This is a **shallow copy**. The copy has a new identity, but **the object graph behind the fields has not been separated**.

**Do not interpret shallow copy as “copying half of the object”**. All field values are copied; for reference values, copying the reference means the referenced object is still shared.

## 10. Demonstrating Shallow Copy with an Array

Create **`ShallowCloneArrayDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private final int[] values;

    Scores(int[] values) {
        this.values = values.clone();
    }

    int[] snapshot() {
        return values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public Scores clone() {
        try {
            return (Scores) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class ShallowCloneArrayDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores cloned = original.clone();

        System.out.println(original == cloned);
        System.out.println(original);

        cloned.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("cloned=" + cloned);
    }
}
```

```bash
javac ShallowCloneArrayDemo.java
java ShallowCloneArrayDemo
```

```text
false
[1, 2]
original=[99, 2]
cloned=[99, 2]
```

Even though the constructor cloned the input array, **`Object.clone()` still copies the `values` reference in a shallow manner**. Both Scores objects point to the same internal array after cloning.

- The final field `values` prevents **reassigning to a new array** via normal assignment after initialization.
- It does not make the array slots immutable.
- Because `clone()` currently only calls super.clone, modifying the internal array via the `setAt` method on one copy also affects the other.

This is why you cannot conclude “copying was used in the constructor, so Object.clone is definitely a deep copy”.

## 11. Arrays in Java Have Their Own `clone()`

Array objects are a useful special case.

Java arrays support a public `clone()` and implement `Cloneable`. When calling:

```java
int[] source = {1, 2, 3};
int[] copy = source.clone();
```

`copy` is **a new array object** of the same type/length as source with its elements copied. For a one-dimensional primitive array, this is **a complete copy of the contents** because the elements are primitive values.

File **`ArrayCloneDemo.java`**:

```java
import java.util.Arrays;

public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        int[] copy = source.clone();

        System.out.println(source == copy);
        System.out.println(Arrays.equals(source, copy));

        copy[0] = 99;

        System.out.println(Arrays.toString(source));
        System.out.println(Arrays.toString(copy));
    }
}
```

```bash
javac ArrayCloneDemo.java
java ArrayCloneDemo
```

```text
false
true
[1, 2, 3]
[99, 2, 3]
```

**Note:** `array.clone()` is language/JVM support for arrays; it does not mean the `clone()` method on every class instance is public. Cloning an `int[]` also does not require you to write `implements Cloneable` in Java code.

The `Arrays.copyOf(...)` and `System.arraycopy(...)` methods can also copy array elements, with their own contracts/range rules. They are other explicit options for copying arrays.

## 12. Arrays of References and Multidimensional Arrays Are Still Shallow-Copied

With `StringBuilder[]`, cloning creates a new array, but **the elements are references to the same StringBuilder objects**.

Create **`ObjectArrayCloneDemo.java`**:

```java
public class ObjectArrayCloneDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        StringBuilder[] source = {builder};
        StringBuilder[] copy = source.clone();

        System.out.println(source == copy);
        System.out.println(source[0] == copy[0]);

        copy[0].append("B");

        System.out.println(source[0]);
        System.out.println(copy[0]);
    }
}
```

```bash
javac ObjectArrayCloneDemo.java
java ObjectArrayCloneDemo
```

```text
false
true
AB
AB
```

Similarly, `int[][]` is an array containing **references to `int[]` rows**. `source.clone()` only creates a new outer array; the inner arrays are still shared.

File **`MatrixShallowCloneDemo.java`**:

```java
import java.util.Arrays;

public class MatrixShallowCloneDemo {
    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3}};
        int[][] copy = source.clone();

        System.out.println(source != copy);
        System.out.println(source[0] == copy[0]);

        copy[0][0] = 99;

        System.out.println(Arrays.deepToString(source));
        System.out.println(Arrays.deepToString(copy));
    }
}
```

```bash
javac MatrixShallowCloneDemo.java
java MatrixShallowCloneDemo
```

```text
true
true
[[99, 2], [3]]
[[99, 2], [3]]
```

To copy the data graph more deeply, you must copy each mutable component or switch to an appropriate immutable representation.

## 13. Explicit Copying for an Object with a Mutable Array

In the copy constructor, you can write explicitly:

```java
this.values = source.values.clone();
```

whereas Object.clone by default only copies the `values` reference.

Create **`DeepCopyConstructorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Scores {
    private final int[] values;

    Scores(int[] input) {
        values = Objects.requireNonNull(input).clone();
    }

    Scores(Scores source) {
        this.values = source.values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class DeepCopyConstructorDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores copied = new Scores(original);

        copied.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("copied=" + copied);
        System.out.println(original == copied);
    }
}
```

```bash
javac DeepCopyConstructorDemo.java
java DeepCopyConstructorDemo
```

```text
original=[1, 2]
copied=[99, 2]
false
```

**Advantages of the explicit approach:**

- You can keep `private final int[] values` and still create **a separate array per instance**.
- Validation/normalization is placed in the constructors according to the contract.
- Reviewers immediately see that the nested array is copied.
- There is no need to use `Cloneable`/`CloneNotSupportedException` or override special methods.
- The constructor actually runs, so field initialization rules are checked by the compiler.

In a complex class, the copy constructor can **delegate to the standard constructor** to reuse validation:

```java
Scores(Scores source) {
    this(source.values);
}
```

This snippet is an alternative to the previous copy constructor: the `Scores(int[])` constructor already clones the input, so calling `this(source.values)` performs that constructor's copy and validation. Do not place **both** copy constructors with the same signature in the same class.

## 14. Copying with a Static Factory: An API with Clear Naming

Another option is to provide:

```java
static Order copyOf(Order source) {
    return new Order(source.id(), source.items());
}
```

This is an **illustrative snippet** assuming `Order` has a corresponding constructor and accessors; the constructor needs to manage mutable collections itself so they are copied properly.

A static factory can carry a name that communicates policy:

- `copyOf(source)`: creates an equivalent value according to API conventions.
- `deepCopyOf(source)`: emphasizes that mutable components are separated.
- `from(source)`: indicates a conversion/snapshot when the domain type differs.
- `withName(newName)` on an immutable value class: creates another value instead of mutating the original.
- `snapshotOf(source)`: emphasizes capturing a stable state.

**Do not name it “deepCopy” if it only copies the outer container and keeps aliases to nested mutable elements.** The name is only useful when the code actually fulfills the contract.

### Factory Copy Program

File **`CopyFactoryDemo.java`**:

```java
import java.util.List;

final class Basket {
    private final List<String> items;

    private Basket(List<String> items) {
        this.items = List.copyOf(items);
    }

    static Basket of(List<String> items) {
        return new Basket(items);
    }

    static Basket copyOf(Basket source) {
        return new Basket(source.items);
    }

    List<String> items() {
        return items;
    }
}

public class CopyFactoryDemo {
    public static void main(String[] args) {
        Basket original = Basket.of(List.of("A", "B"));
        Basket copy = Basket.copyOf(original);

        System.out.println(original == copy);
        System.out.println(original.items().equals(copy.items()));
        System.out.println(copy.items());
    }
}
```

```bash
javac CopyFactoryDemo.java
java CopyFactoryDemo
```

```text
false
true
[A, B]
```

The factory calls `new Basket(...)`, so it definitely creates a new Basket instance. `List.copyOf` protects the list structure and the String elements, which are already immutable; it can safely share an **immutable list object reference**. It is not required for every nested reference to be different for two Basket objects to have independent state.

**Note on naming:** Some JDK factory methods named `copyOf` can **return the input itself** if the type/contract allows it. In this specific Basket class, the code uses `new`, so **source and result have different identities**. Do not infer an identity rule solely from the name `copyOf` across all APIs.

## 15. General Comparison: Explicit Copying vs. `Object.clone()`

| Aspect | Explicit copy constructor / factory | Override calling `Object.clone()` |
| --- | --- | --- |
| Common syntax | `new Person(other)` / `Person.copyOf(other)` | `other.clone()` if method is exposed |
| Relies on `Cloneable` | No | Yes, when using the Object.clone implementation |
| Constructor runs for new object | **Yes**, if using `new` | **No**, under the Object.clone mechanism |
| Field and invariant checks | Explicitly controlled by the copy code | Initial field-for-field copy; override must handle it |
| Copying primitive fields | By value | By value |
| Copying immutable references | Can be shared safely | Copies the reference |
| Copying mutable references | Can actively clone/copy | Shares references by default |
| Checked exception | Depends on constructor/factory contract | Base method declares `CloneNotSupportedException` |
| Accessibility | Decided by the class's API | Object.clone is `protected`; usually requires a public override |
| Return type | Explicitly designed type | Object base; covariant override allowed |
| Inheritance / subtypes | Copy constructor on base needs attention to runtime type | Object.clone creates the same runtime class in the field-copy path |
| `final` mutable reference field | Constructor can assign a new defensive copy | Clone copies the final reference field; cannot be reassigned after normal clone |
| Field schema changes | Must update manual copy properly | Field-for-field automatically includes new field value, though it may share a new mutable field |
| Debugging/tracing | Validations and constructor side effects are clearly visible | Clone can bypass constructors and side effects |
| Hierarchy coupling | Can be lower if the class is final | Must consider inherited clone contracts |
| Recommendation for new APIs | Usually easier to maintain | Use when required by contract/legacy/API or in controlled cases |

**Be careful with the word “deep”:** A copy constructor is not automatically a deep copy. It is only deep for the parts you **actually copy**. Likewise, clone is not always only shallow if a subclass **has overridden it to deep-copy**; it is `Object.clone`'s default that is shallow.

## 16. A `final` Field Creates an Important Decision When Deep-Cloning

Suppose:

```java
final class Data implements Cloneable {
    private final int[] values;

    // ...
}
```

`super.clone()` creates a new Data object whose `values` field points to the **same array** as source.

To deep-clone, we want:

```java
Data copied = (Data) super.clone();
copied.values = values.clone(); // Invalid: values is final.
```

This is a **compile-time error illustration snippet**, not code to copy into a program. A `final` field cannot be reassigned here.

There are several design options:

1. **Prefer a copy constructor**: `new Data(source.values)`; the constructor can assign the cloned array to the final field.
2. If you must use `clone()`, you can implement the override **by calling a new constructor** instead of `super.clone()`, though then the contract, inheritance, and constructor side effects differ from field-for-field clone. The name clone must be explained.
3. Only for a class without the corresponding final constraint can an override calling super.clone and then replacing the mutable field reference with a new one in the cloned object be appropriate.
4. If the component is actually immutable, sharing the reference is safe; there is no need to deep-copy just to change identity.

**Conclusion:** `final` fields are very useful for immutable design; explicit copying generally harmonizes better with final-field initialization than clone-and-patch.

## 17. Overriding `clone` to Copy a Mutable Array When the Field Is Not Final

A classic clone pattern is to call `super.clone()`, then replace the mutable references. This requires the field to be reassignable in the cloned instance.

Create **`DeepCloneOverrideDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private int[] values;

    Scores(int[] input) {
        values = input.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public Scores clone() {
        try {
            Scores copy = (Scores) super.clone();
            copy.values = values.clone();
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class DeepCloneOverrideDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores clone = original.clone();

        clone.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("clone=" + clone);
    }
}
```

```bash
javac DeepCloneOverrideDemo.java
java DeepCloneOverrideDemo
```

```text
original=[1, 2]
clone=[99, 2]
```

In the override:

1. `super.clone()` creates the initial shallow copy.
2. `copy.values = values.clone()` replaces the referenced array in the cloned instance with a new array.
3. Returns a copy with independent state at the mutable array layer.

**However, this is not a general solution for every object graph**. If fields contain arrays of mutable objects, nested collections, cycles, or shared aliases, you must copy the corresponding layers. In addition, clone-and-patch creates an intermediate object with shared field references while the method is executing; do not publish the cloned object before patching is complete.

## 18. Can `clone()` Be Overridden Without Using `super.clone()`?

In terms of Java, a class can define a public method named `clone()` that creates an object via a constructor without calling Object.clone. For example:

```java
@Override
public Scores clone() {
    return new Scores(values);
}
```

This is an **alternative approach** for a class with a `Scores(int[])` constructor and a `values` field; do not combine it into the example class in section 17 without adjusting it and choosing a single implementation.

For a `final` class with well-known state, that method can guarantee a deep copy and keep `final` fields if the constructor is designed properly.

However, you need to distinguish:

- This is an **overriding method named clone** with an explicit implementation using `new`.
- It **does not have the constructor-bypass behavior** of `Object.clone()`.
- With open subclassing, hardcoding creation of a superclass instance in `clone()` can cause subtype preservation issues.
- You should not say “every call to a method named clone is guaranteed not to run a constructor”; that is true for the **Object.clone implementation**, not for arbitrary overrides that use `new`.

This is why, when an API is not yet constrained by the name clone, a `copy()` name or a copy constructor with a clear contract usually causes fewer misunderstandings.

## 19. Cases Where Shallow Copying Is Completely Reasonable

A shallow copy is not inherently a bug. It can be correct when shared references point to **immutable values** or an intentionally shared collaborator.

For example:

```java
final class Label implements Cloneable {
    private final String text;

    Label(String text) {
        this.text = text;
    }

    @Override
    public Label clone() {
        try {
            return (Label) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    String text() {
        return text;
    }
}
```

This is a valid class declaration, without `main` yet. Because `String` is immutable, having source and clone point to the same String object does not cause observable state to change.

Similarly, a copy constructor can be written as:

```java
Label(Label source) {
    this.text = source.text;
}
```

if explicit copying is desired.

**Check:** ask “through what path can the shared references be mutated?” rather than merely asking “is any reference shared?”. Sharing immutable components is usually safe and saves memory.

## 20. Inheritance: Copying the Superclass Can Lose the Subtype

A traditional copy constructor has a limitation: `new Base(source)` **always creates a Base**, and does not automatically preserve the runtime subtype when source is a Derived.

Create **`CopyConstructorSlicingDemo.java`**:

```java
class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    Animal(Animal other) {
        this.name = other.name;
    }

    String name() {
        return name;
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

public class CopyConstructorSlicingDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = new Animal(original);

        System.out.println(original.getClass().getSimpleName());
        System.out.println(copy.getClass().getSimpleName());
        System.out.println(original.name().equals(copy.name()));
    }
}
```

```bash
javac CopyConstructorSlicingDemo.java
java CopyConstructorSlicingDemo
```

```text
Dog
Animal
true
```

**Note:** This is not “Java automatically slicing object bytes” in the C++ sense; it is simply that the expression `new Animal(original)` **creates a new Animal instance**, because the constructor specifies the Animal type. `Dog.breed` does not exist in the Animal copy.

Therefore, a base class's copy constructor/factory needs to clearly define:

- Is it intentionally creating a Base value?
- Or does it need to preserve the runtime subtype and all subclass state?
- If preserving the subtype, is a **virtual copy/polymorphic factory** needed on the hierarchy?

Do not claim that every `Base copy = new Base(subclassInstance)` is a complete copy of the subclass.

## 21. `Object.clone()` Has the Advantage of Preserving the Runtime Class

When executed via the field-copy mechanism of `Object.clone()`, the clone is created with the **same runtime class** as the source object. This is an important difference from `new Base(source)`.

Create **`CloneSubclassDemo.java`**:

```java
class Animal implements Cloneable {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    @Override
    public Animal clone() {
        try {
            return (Animal) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

public class CloneSubclassDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal clone = original.clone();

        System.out.println(original == clone);
        System.out.println(clone.getClass().getSimpleName());
        System.out.println(clone.name());

        if (clone instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac CloneSubclassDemo.java
java CloneSubclassDemo
```

```text
false
Dog
Milo
Collie
```

Because `Dog` inherits the Cloneable marker through Animal, Object.clone can create a clone of **runtime class Dog** even though the public override method is defined in Animal.

However, **do not confuse subtype preserved with deep copy guaranteed**:

- If Dog later adds a mutable `List`, the inherited shallow clone will keep a shared reference unless the class/hierarchy is updated.
- A subclass can override clone with a different contract, posing a risk if the hierarchy is not designed for extensible cloning.
- The return type of `Animal.clone()` is still Animal, even though the runtime cloned object may be Dog; the caller needs to check the type/abstraction when using Dog-specific behavior.

## 22. Inheritance and Mutable Fields: Every Subclass Must Review the Clone Contract

Suppose:

```java
class Base implements Cloneable {
    private final String id;

    Base(String id) {
        this.id = id;
    }

    @Override
    public Base clone() {
        try {
            return (Base) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

Today Base only holds an immutable String, so shallow cloning is sufficient. Tomorrow, if a subclass adds:

```java
private final java.util.List<String> mutableNotes =
        new java.util.ArrayList<>();
```

then the inherited clone will copy the reference to the same mutable list object; moreover, the final field prevents normal “clone and reassign” behavior.

**Code review lesson:** “The superclass has a clone method” does not mean “every future subclass will automatically deep-copy properly”. A hierarchy with mutable fields and a clone contract needs to specify how cloning is extended, or use composition/explicit copying per type.

### Why Is `Cloneable` Not an Ideal “Polymorphic Copy Pattern”?

A marker interface does not promise a public `clone()` signature or return type. A caller holding a variable of type `Cloneable` **cannot call clone as it would call a method on a copy interface**.

If an application wants explicit polymorphic copying, it can design an interface containing **its own method**:

```java
interface Copyable<T> {
    T copy();
}
```

Then each concrete class implements `copy` with the proper semantics. This is an API designed by the programmer; Java does not automatically infer a “deep” contract from that generic interface.

## 23. Creating an Explicit Polymorphic Copy Method

One solution for a hierarchy that wants to preserve the runtime subtype is for **each class to implement `copy()` appropriately**.

File **`PolymorphicCopyDemo.java`**:

```java
abstract class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract Animal copy();
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    @Override
    Dog copy() {
        return new Dog(name(), breed);
    }

    String breed() {
        return breed;
    }
}

public class PolymorphicCopyDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = original.copy();

        System.out.println(original == copy);
        System.out.println(copy.getClass().getSimpleName());
        System.out.println(copy.name());

        if (copy instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac PolymorphicCopyDemo.java
java PolymorphicCopyDemo
```

```text
false
Dog
Milo
Collie
```

- `Animal` defines the abstract method `copy()`, without requiring Cloneable.
- `Dog.copy()` uses a constructor and returns Dog (covariant return type).
- When called via an `Animal` reference, runtime dispatch goes to Dog, returning **the exact subtype**.
- When adding a new subclass, that class must provide its corresponding copy implementation.

The trade-off: the hierarchy designer is responsible for cloning/copying all fields and nested objects. However, the contract can be named, tested, and extended explicitly.

## 24. Explicitly Copying a Multidimensional Array

A deep-enough copy for `int[][]` needs to copy **the outer array and each inner `int[]`**, not just the outer clone.

File **`ExplicitMatrixCopyDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Matrix {
    private final int[][] rows;

    Matrix(int[][] source) {
        Objects.requireNonNull(source);
        rows = copyRows(source);
    }

    Matrix(Matrix source) {
        rows = copyRows(source.rows);
    }

    private static int[][] copyRows(int[][] source) {
        int[][] copied = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copied[i] = Objects.requireNonNull(source[i]).clone();
        }
        return copied;
    }

    void set(int row, int column, int value) {
        rows[row][column] = value;
    }

    @Override
    public String toString() {
        return Arrays.deepToString(rows);
    }
}

public class ExplicitMatrixCopyDemo {
    public static void main(String[] args) {
        Matrix source = new Matrix(new int[][] {
                {1, 2}, {3}
        });

        Matrix copy = new Matrix(source);
        copy.set(0, 0, 99);

        System.out.println(source);
        System.out.println(copy);
    }
}
```

```bash
javac ExplicitMatrixCopyDemo.java
java ExplicitMatrixCopyDemo
```

```text
[[1, 2], [3]]
[[99, 2], [3]]
```

`copyRows` creates a new outer array and clones each inner primitive array. For jagged arrays, the length of each row is preserved.

**Do not call this a deep copy of every object graph**; it is only a deep-enough copy for the `int[][]` shape. With `MutableElement[][]`, cloning the inner arrays still shares MutableElement objects.

## 25. `ArrayList.clone()` and `List.copyOf`: Understanding Their Contracts Too

Some Java collections have their own clone method, yet the contract may **only shallow-clone the structure**.

For example, `ArrayList.clone()` returns a copy of the list structure, but **does not clone each element**.

File **`ArrayListCloneDemo.java`**:

```java
import java.util.ArrayList;

public class ArrayListCloneDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        ArrayList<StringBuilder> source = new ArrayList<>();
        source.add(builder);

        @SuppressWarnings("unchecked")
        ArrayList<StringBuilder> copied =
                (ArrayList<StringBuilder>) source.clone();

        System.out.println(source == copied);
        System.out.println(source.get(0) == copied.get(0));

        builder.append("B");
        System.out.println(source.get(0));
        System.out.println(copied.get(0));
    }
}
```

```bash
javac ArrayListCloneDemo.java
java ArrayListCloneDemo
```

```text
false
true
AB
AB
```

**QA note:** `ArrayList.clone()` is a concrete public method of ArrayList and returns `Object` per the API override in this class, so a cast is required. The generic element type is not fully runtime-checked due to type erasure; the example uses `@SuppressWarnings("unchecked")` on the local declaration so it can compile, while the application must still guarantee type safety.

If the goal is an immutable snapshot of `List<String>`, `List.copyOf(source)` is usually clearer. If the goal is a mutable structural copy, `new ArrayList<>(source)` is easier to read. Both are still **shallow with respect to the elements**.

## 26. Copy Constructor for a Collection Containing Mutable Elements

Applying `List.copyOf` to a `List<StringBuilder>` does not deep-freeze the StringBuilder objects. If you need a text snapshot, convert them to Strings.

File **`CopyMutableElementsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> input) {
        Objects.requireNonNull(input);
        List<String> copied = new ArrayList<>();

        for (StringBuilder builder : input) {
            copied.add(Objects.requireNonNull(builder).toString());
        }

        lines = List.copyOf(copied);
    }

    Notes(Notes source) {
        lines = List.copyOf(source.lines);
    }

    List<String> lines() {
        return lines;
    }
}

public class CopyMutableElementsDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        Notes original = new Notes(List.of(builder));
        Notes copy = new Notes(original);

        builder.append("B");

        System.out.println("original=" + original.lines());
        System.out.println("copy=" + copy.lines());
        System.out.println(original == copy);
    }
}
```

```bash
javac CopyMutableElementsDemo.java
java CopyMutableElementsDemo
```

```text
original=[A]
copy=[A]
false
```

In the first constructor, `StringBuilder.toString()` creates immutable text snapshots; `List.copyOf` locks the list structure. The copy constructor of Notes can **share the immutable elements** and even the underlying immutable list object while still keeping observable state independent.

**What matters is that there are no remaining mutable aliases**, not that every reference in the graph must be different.

## 27. Constructors and Invariants: Copy Can Validate, Clone Can Bypass

Suppose a class has constraints:

- Non-negative quantity.
- Code must not be blank.
- Two fields must be consistent, for example `start <= end`.
- Array/list contains no nulls or out-of-range values.

With a copy constructor, we can:

```java
Range(Range source) {
    this(source.start, source.end);
}
```

and use the `Range(int start, int end)` constructor to check the invariant. This is an illustrative snippet, assuming the Range class defines the appropriate fields and constructor.

With `Object.clone()`, constructors do not run, so **validation code in the constructor does not automatically run again**. If the runtime state is consistently protected and non-mutable, a field copy may still be valid. However, if the class allows state changes or depends on external resources, you must not assume that clone is valid in every case.

### Example of a Factory Actively Creating a New Identity

A `Session` object has a session ID, creation timestamp, and connection handle. “Copying” may need to:

1. Retain the configuration.
2. Generate a new session ID.
3. Not copy the open connection.
4. Have clear resource ownership.
5. Report an error if creating the new session fails.

A dedicated copy factory such as `Session.fromConfig(original.config())` makes this policy clearer than field-for-field cloning. This is a **design** illustration, not runnable source code; semantics differ depending on the system.

## 28. Resource Issues: Cloning a Handle Does Not Create an Independent Resource

Objects such as `InputStream`, `Socket`, `Connection`, `Thread`, locks, or file handles have specialized lifecycles.

If a class holds:

```java
private final java.io.InputStream stream;
```

a shallow clone will hold the **same stream reference**. It does not open another stream and does not guarantee that the two objects have independent rights to close the stream.

Even “deep-copying an open socket” has no general meaning: you must specify whether copying should share the connection, open a new connection, or prohibit copying.

**Good design approach:** separate **immutable configuration/value state** from the **resource-bearing live object**, and then allow copying the configuration via a factory if appropriate. Do not apply field-for-field cloning to resource wrappers just because the method is available.

### Ownership Must Be Defined

A getter/copy method that returns a new object does not necessarily have the right to call `close()` on a shared resource. If two wrappers both hold a closable resource, closing it from one wrapper can break the other wrapper. The copy policy must define who owns it, who closes it, when, and whether it can be shared.

## 29. Copy and Equality: Equal in Value Does Not Necessarily Mean Different in Business Semantics

Two independent concepts:

- **Identity:** `source == copy` can be false when creating a new instance.
- **Logical equality:** `source.equals(copy)` can be true or false depending on the class.
- **State independence:** does mutating the copy change the source?
- **Subtype preservation:** does the copy have the same runtime class as the source?
- **Resource independence:** does the copy independently own external resources?

A copy constructor can create an object with a different identity yet use the default Object.equals, so `equals` is false. An immutable value class can define equals by value, so copy equals source is true. A factory named `copyOf` can return the existing reference when the contract permits; you should not infer identity solely from the API name.

### Four Separate QA Criteria

| Criterion | Test question |
| --- | --- |
| Identity | `source == copied`? What result does the contract promise? |
| Value equality | `source.equals(copied)`? Do they have the same logical data? |
| Mutation isolation | Does modifying a mutable component of the copy affect the source? |
| Runtime type | `source.getClass()==copied.getClass()`? Does it need to be guaranteed? |

Do not infer “`equals` is true → already deep-copied” or “`==` is false → no aliases remain”. Those two assertions are not sufficient.

## 30. `Object.clone()` and `CloneNotSupportedException`: Designing a Public API

`Object.clone()` declares checked `CloneNotSupportedException`. A public override can:

**Keep the checked exception** if the contract wants the caller to handle it:

```java
@Override
public MyType clone() throws CloneNotSupportedException {
    return (MyType) super.clone();
}
```

This is an **illustrative method snippet** assuming the class `MyType` implements Cloneable and inherits Object.clone appropriately.

**Or handle it internally** as in `BasicCloneDemo`, if the class has sufficient guarantees that the Object.clone path will not be rejected.

Java rules for overriding methods:

- An override cannot declare **broader** checked exceptions than the corresponding superclass method.
- It can use a covariant return type (for example, `MyType` instead of Object).
- It cannot reduce access below `protected` compared to Object.clone; a public override is appropriate when you want a public API.
- `@Override` helps the compiler verify that the method actually overrides.
- If the return type is wrong or the class does not yet comply with the clone contract, compilation/runtime can fail.

**Do not write code assuming every subclass of Cloneable automatically has a public clone.** The marker interface does not declare a clone method.

## 31. Types That Usually Do Not Need `clone()`

If a class is an **immutable value object**, returning the existing object is sometimes enough: there is no mutable state to separate. For example, `String` is immutable, so there is no need to create a new String to avoid mutation of string contents.

If a class is a **final value object** containing primitives and immutable components, a static factory or constructor can reuse the object if the API allows it; or return a new copy if the identity contract requires it. Do not force cloning just to always change the reference.

If a class has a **mutable array/list**, define a specific shallow/deep policy. If a class represents a **resource/session**, you usually need a factory that creates a new resource or prohibit copying.

These are choices about semantics, not a rule that “no immutable class may be cloned”.

## 32. Deep Copying with Cyclic Reference Graphs

Deep copying a graph with cycles and shared references is harder than a simple chain of `new` calls:

```text
Node A ----next----> Node B
   ^                   |
   +------next---------+
```

If copying recursively with:

```java
new Node(copy(node.next))
```

without tracking already-copied objects, traversal can loop infinitely through the cycle.

In addition to cycles, a graph can have **sharing**:

```text
A.left  ──┐
          ├──> Shared Child X
A.right ──┘
```

If a child is copied twice without following a policy, the clone can end up with two children instead of preserving the required alias structure.

A deliberate deep-copy algorithm can use an `IdentityHashMap<Original, Copy>` to record already-processed objects by **reference identity**, and then:

1. Allocate the copy object for the current node.
2. Record it in the identity map **before recursing into children**.
3. Copy references/connections according to the map.
4. Preserve cycles and shared topology according to the contract.

That is an **algorithmic model**, not an implementation applicable to every class. You need to check whether constructor invariants, final fields, and wiring order allow building the graph in two phases. Usually, designing an immutable graph representation/serialization with a clear schema is easier to verify than “deep-cloning any arbitrary Object”.

## 33. Serialization Does Not Automatically Mean `clone()` or a Copy Constructor

You can serialize and then deserialize to build a new object graph in some situations, but that is a different mechanism with its own contract and limitations:

- Not every object implements Serializable.
- Transient data, custom hooks, identity sharing, and version compatibility need to be handled.
- You should not use a serialization round-trip as the default clone solution merely to avoid writing copy code.
- In particular, deserializing untrusted data carries security risks and requires an appropriate API/filter/policy.

**Do not confuse:** Object.clone does not use Java serialization; a copy constructor does not require serialization; `Cloneable` and `Serializable` are two different interfaces.

## 34. Performance: `clone` Is Not Faster or More Correct by Default

Performance evaluation needs to be based on the **specific workload and implementation**, without attaching absolute labels.

- Shallow Object.clone can avoid running the constructor, yet fails to perform necessary validations/deep copying.
- A copy constructor may do more work because it creates nested copies or normalizes data according to the domain; that can be a **correctness requirement**, not “pointlessly slow”.
- For primitive arrays, `clone()` and `Arrays.copyOf` are both effective options depending on the workload; only proper benchmarking can yield a conclusion.
- JIT, escape analysis, GC, heap size, object graph, and reuse of immutable components all affect the numbers.
- A “fast” choice that keeps an incorrect mutable alias can cause bugs more severe than allocation overhead.

**Prioritize correctness:** determine copy depth, identity, invariants, and ownership first. Only then benchmark if performance becomes an actual requirement.

## 35. Self-Test Comparing the Same Input Under Both Mechanisms

Create **`CopyComparisonSelfTest.java`**:

```java
import java.util.Arrays;

final class Payload implements Cloneable {
    private int[] bytes;

    Payload(int[] input) {
        bytes = input.clone();
    }

    Payload(Payload source) {
        bytes = source.bytes.clone();
    }

    void write(int index, int value) {
        bytes[index] = value;
    }

    int at(int index) {
        return bytes[index];
    }

    @Override
    public Payload clone() {
        try {
            return (Payload) super.clone(); // Shallow by default.
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CopyComparisonSelfTest {
    static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        Payload original = new Payload(new int[] {1, 2});
        Payload shallow = original.clone();
        Payload deep = new Payload(original);

        check(original != shallow, "clone identity");
        check(original != deep, "copy identity");

        shallow.write(0, 99);
        check(original.at(0) == 99, "shallow shares array");
        check(deep.at(0) == 1, "deep isolates array");

        deep.write(1, 77);
        check(original.at(1) == 2, "deep independent");

        System.out.println("shallow original=" + original.at(0));
        System.out.println("deep first=" + deep.at(0));
        System.out.println("deep second=" + deep.at(1));
        System.out.println("copy checks passed");
    }
}
```

```bash
javac CopyComparisonSelfTest.java
java CopyComparisonSelfTest
```

```text
shallow original=99
deep first=1
deep second=77
copy checks passed
```

This is a test that **intentionally demonstrates a shallow alias**. It does not mean clone is always wrong: what semantics the Payload class promises determines whether the array should be shared. The `clone()` name in the example is used with default Object.clone behavior to show the difference.

Importing `java.util.Arrays` is not needed in this working code; Java permits unused imports. This is a self-test via main, not a full JUnit suite.

## 36. Checklist for Verifying That a Copy Follows Its Contract

When reviewing a `copy()` method, copy constructor, or `clone()`, ask:

- [ ] Does it **create a new object** or only assign a reference?
- [ ] Does the API promise that source and copy must have different identities?
- [ ] Which logical values must be preserved?
- [ ] Which primitive fields are copied directly?
- [ ] Which references to immutable objects are allowed to be shared?
- [ ] Do mutable arrays and collections need a structural copy?
- [ ] Do mutable inner elements need to be deep-copied/converted?
- [ ] Do getters on source/copy expose internal mutable references?
- [ ] Does mutating the copy change the source?
- [ ] Does mutating the source change the copy?
- [ ] Does it properly copy final fields and respect constructor invariants?
- [ ] If using Object.clone, does the runtime type implement Cloneable?
- [ ] Is there a public override if callers need to invoke clone from outside?
- [ ] Is CloneNotSupportedException handled according to the contract?
- [ ] Is the Cloneable marker distinguished from the clone API method?
- [ ] Is it understood that Object.clone does not call a constructor for the cloned object?
- [ ] Is a new ID/timestamp/resource needed instead of copying the raw field?
- [ ] Does the runtime subtype need to be preserved?
- [ ] With inheritance, do new subclasses add mutable fields?
- [ ] Do shared references/cycles in the object graph need to be preserved?
- [ ] Are there external resources that cannot be copied field-for-field?
- [ ] Could another thread mutate the source while copying is in progress?
- [ ] If the copy is used as a key, are equals/hashCode stable according to the contract?
- [ ] Do tests avoid relying on raw object hash values or allocation optimizations?
- [ ] Do runnable examples have filenames matching the public class, valid `javac`/`java` commands, and stable stdout?

## 37. Common Mistakes

| Misconception | Reality | How to handle |
| --- | --- | --- |
| `b=a` copies the object | Only copies the reference | Use a constructor/factory/clone with a contract to create a new object |
| `Object.clone` is always public | Object.clone is protected | Provide a public override if you want to expose it |
| `implements Cloneable` automatically generates a `clone()` method | Cloneable is an empty marker | Declare a public copy/clone method |
| `Object.clone` always succeeds | Can throw CloneNotSupportedException | Check the marker/hierarchy contract |
| `clone` always deep-copies | Object.clone defaults to shallow | Copy mutable fields or use a constructor |
| Two clones with different identities mean all fields are independent | Mutable refs may still be shared | Test nested aliases |
| `array.clone()` clones every element object | Only copies element references | Copy/convert mutable elements |
| `matrix.clone()` is enough for a 2D matrix | Inner arrays are shared | Copy each inner row |
| A copy constructor is always deep | Only as deep as the written logic | Audit fields/nested references |
| A `final` reference makes an array immutable | Array slots are mutable | Use defensive copying or an immutable representation |
| You can reassign a `final` field after super.clone | Final does not allow reassignment that way | Use a copy constructor or change the model |
| `clone()` never calls a constructor | Only true for the Object.clone mechanism as described | Distinguish arbitrary overrides |
| `new Base(subtype)` preserves the runtime subtype | Creates a new Base | Use polymorphic copy if needed |
| Clone preserving subtype means nested mutable state is cloned | Only preserves the runtime class | Audit each subclass's fields |
| A shared mutable list is a deep copy | Same elements, possibly the same container | Copy the structure and mutable leaves |
| `ArrayList.clone` deep-copies elements | Shallow structural copy | Perform explicit deep copy if needed |
| `Cloneable` can be used like `Copyable.copy()` | Marker has no clone method | Create a copy interface with a method |
| Copying a connection wrapper creates a new socket | Shallow copy only keeps the handle reference | Use resource-specific factory/ownership |
| Equal hashes prove the copy is the same object | Hash collisions are valid | Use `==` or the class contract |
| “Fastest copy” is always optimal | No benchmark/context | Correctness first, measure later |
| Serialize-deserialize is always a safe deep clone | Not every type supports it, many risks | Use a copy API with a clear schema/contract |

## 38. Self-Practice Questions with Answers

**Question 1.** Does `Box b=a;` create a new Box object?

*Answer:* No; it only assigns an alias reference.

**Question 2.** Which access modifier does `Object.clone()` declare?

*Answer:* `protected`. To allow external callers to access it, the class usually needs a public override.

**Question 3.** Does the `Cloneable` interface have a `clone()` method?

*Answer:* No. It is a marker interface.

**Question 4.** What happens when calling `super.clone()` on an instance that does not implement Cloneable in an ordinary class?

*Answer:* The Object.clone implementation rejects it with `CloneNotSupportedException`.

**Question 5.** Is `Object.clone()` deep or shallow by default?

*Answer:* Shallow field-for-field copy: primitive values are copied, and reference values have their references copied.

**Question 6.** Does cloning an object run the constructor of the new object?

*Answer:* The `Object.clone()` mechanism does not run a constructor; an override that explicitly uses `new` does.

**Question 7.** With `int[] a={1,2}; int[] b=a.clone();`, after `b[0]=9`, what is `a[0]`?

*Answer:* Still 1, because cloning a primitive array creates separate slots.

**Question 8.** Does cloning a `StringBuilder[]` clone the StringBuilder elements?

*Answer:* No, array clone copies references.

**Question 9.** Does `int[][] matrix.clone()` copy each inner row?

*Answer:* No. It only clones the outer array.

**Question 10.** Why does `private final int[] values` cause difficulty during a deep clone-and-patch?

*Answer:* A final field cannot be reassigned to the cloned array inside an ordinary clone method after super.clone; a copy constructor can initialize the final field directly when creating the instance.

**Question 11.** Does a copy constructor automatically guarantee a deep copy?

*Answer:* No. It only performs the copying operations written in the code.

**Question 12.** If source is a subclass Dog and you call `new Animal(source)`, what type is the result?

*Answer:* An Animal instance, unless a constructor/factory explicitly creates the subtype in another way.

**Question 13.** What runtime class does `Object.clone()` normally create?

*Answer:* The same runtime class as the source under the normal field-for-field Object.clone mechanism.

**Question 14.** Should `super.clone()` be used for a resource wrapper containing a Socket?

*Answer:* Not by default; you must define resource ownership and connection semantics. A shallow clone could share the same socket.

**Question 15.** Does an immutable class holding only Strings need to deep-copy the Strings?

*Answer:* Usually not; Strings are immutable, so sharing references is safe with respect to content.

**Question 16.** Can you define a `Copyable<T>` interface with `T copy()` to support polymorphic copies?

*Answer:* Yes. That is an application-designed contract, not an automatic mechanism from Cloneable.

**Question 17.** Does `ArrayList.clone()` deep-copy its elements?

*Answer:* No. It performs a shallow copy of the list structure per the API.

**Question 18.** If a copy constructor creates a new object yet `equals` is false, is the copy wrong?

*Answer:* Not necessarily. The class may use default identity equality; verify the copy contract and observable state separately.

**Question 19.** Do two objects with the same hash codes necessarily have the same reference?

*Answer:* No. Hash collisions are valid.

**Question 20.** If the source graph has cycles or a shared child, what else does deep copying need?

*Answer:* A graph-copy policy and a mechanism to record already-copied nodes, typically by reference identity, to handle cycles/sharing.

---

**Final takeaway:** **Explicit copying** using a copy constructor, factory, or `copy()` method lets you decide on constructor validation, fields, copy depth, `final` handling, subtypes, and resource ownership yourself. **`Object.clone()`** is a protected method on Object with a `Cloneable` contract and checked exception; the base implementation creates a **shallow field copy** **without calling a constructor**. Arrays have a public `clone()`, yet it is also shallow when elements are references; multidimensional arrays need their inner arrays copied. Whichever approach you choose, verify **object identity, state equality, mutable alias isolation, runtime subtype, and resource lifecycle** as separate criteria. For new Java code requiring maintainability and clear invariants, **explicit copying is usually the easier option to reason about**; use clone when you genuinely understand and need its contract.
