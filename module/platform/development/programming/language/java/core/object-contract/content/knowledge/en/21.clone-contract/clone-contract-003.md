# `Cloneable` is a marker interface and does not declare a `clone()` method itself

In Java, the names `Cloneable` and `clone()` look very similar but belong to **two different places**:

- `java.lang.Cloneable` is a **marker interface**: an empty interface used to mark that an object permits the `Object.clone()` mechanism to create a field-by-field copy (*field-for-field copy*).
- `clone()` is a method declared in `java.lang.Object`, with the original form `protected Object clone() throws CloneNotSupportedException`. **There is no `clone()` method declared in `Cloneable`.**

Merely writing `implements Cloneable` **does not auto-generate a `public clone()` method**, does not widen the access scope of `Object.clone()`, and does not guarantee that code outside the class can call `object.clone()`. To provide a copying API for callers of the class, a developer usually has to **override `clone()`**, specify the return type and access level, and decide how to handle mutable state.

## 1. What is a marker interface?

A marker interface is an interface with no abstract methods to implement; having a type `implement` that interface provides **marking information** for another mechanism to inspect. For `Cloneable`, this signal is used by `Object.clone()`.

You can visualize it simply:

~~~java
// For structural understanding only; do not redeclare java.lang.Cloneable.
public interface Cloneable {
    // No clone() method.
}
~~~

The code above is an **illustrative model**, not an interface to create in a project. Java already includes `java.lang.Cloneable`.

Example of a class carrying only the marker:

~~~java
final class MarkerOnly implements Cloneable {
    private int value = 10;
}
~~~

This class is valid; it **does not** have to implement the body of any method from `Cloneable` because the interface requires no methods. However, the following snippet in a normal calling class will not compile:

~~~java
MarkerOnly value = new MarkerOnly();
value.clone(); // Access error: Object.clone() is still protected.
~~~

Note: the snippet above is only an **intentionally invalid code fragment** to explain access scope, not to be merged into a runnable example. The keyword `implements Cloneable` is not like a promise that the class already has a `public clone()` API.

### Comparison table

| Component | Where is it declared? | Role | Can it be called directly from external code? |
| --- | --- | --- | --- |
| `Cloneable` | `java.lang.Cloneable` interface | Marks compatibility with the `Object.clone()` mechanism | No method to call |
| `Object.clone()` | `java.lang.Object` class | Performs a field-by-field copy when conditions permit | Usually **no**, because it is `protected` |
| `public MyType clone()` | Overridden by your class | Provides a copy API with an explicit return type | **Yes**, if the class itself exposes the method publicly |
| Copy constructor/factory | Designed by the class, e.g., `new MyType(original)` | Explicit copying approach, not relying on the marker | Yes, according to the declared access level |

**Marker vs. functionality:** the `Cloneable` marker affects how **the `Object.clone()` implementation** checks an object, but it does not add a method to the interface for callers to invoke.

## 2. What is the signature and access scope of `Object.clone()`?

In Java 17, the declaration of the original method is:

~~~java
protected Object clone() throws CloneNotSupportedException
~~~

There are four points to distinguish:

1. `protected`: the original method is not a public API that can be arbitrarily called on any `Object`. Java's `protected` access rules also involve packages and inheritance relationships; one should not assume that just because a class is `Cloneable`, arbitrary external code can call `clone()`.
2. `Object`: the return type of the original method is very broad. When overriding, a class can use a **covariant return type**, such as `public Account clone()`.
3. `throws CloneNotSupportedException`: this is a checked exception of the original method. An override can continue declaring this exception, or narrow/omit the checked exception in its public signature.
4. `Object.clone()` is an **instance** method; it copies the current object, rather than being a static factory located in `Cloneable`.

When a class overrides the original method to expose the API publicly:

~~~java
final class Account implements Cloneable {
    private final String id;

    Account(String id) {
        this.id = id;
    }

    @Override
    public Account clone() {
        try {
            return (Account) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

This is an **illustrative class that can compile in an appropriate program**, assuming the `id` key is checked to be non-`null` at the business layer. `@Override` lets the compiler verify that the method overrides `Object.clone()`; `public` opens calling permission; `Account` is the specific return type. Because class `Account` is `final` and implements `Cloneable`, calling `super.clone()` normally does not throw `CloneNotSupportedException`; the `AssertionError` branch only signals an abnormal violation of this assumption.

It is not strictly necessary to use this exact pattern: a class can define a copy constructor or a `copy()` method; and a `clone()` override can also use its own copying approach without calling `super.clone()`. Therefore, **`Cloneable` is a signal for the `Object.clone()` mechanism**, not a general rule that every method named `clone` must have the marker.

## 3. What does the marker enable when calling `super.clone()`?

The `Object.clone()` mechanism has notable steps/characteristics:

- When called on an instance whose runtime type **does not implement `Cloneable`**, the implementation of `Object.clone()` throws `CloneNotSupportedException`.
- When the marker condition is satisfied, `Object.clone()` creates another object of the **same runtime class** and copies existing field contents by assignment; it does not sequentially invoke constructors to re-initialize fields as creating an object with `new` does.
- Primitive-type fields (`int`, `double`, `boolean`, ...) receive copies of their values.
- Reference-type fields (`List`, arrays, mutable objects, ...) receive **copies of references**. Two different objects may still point to the same child object.
- This is a **shallow copy**. It does not automatically copy the entire object structure recursively.

For example, after `super.clone()` executes, the source object and the copied object may be two distinct `Bag` instances, yet their `items` fields both point to **the same `ArrayList`**. If one side modifies that list, the other observes the changed contents.

### What if there is no marker?

Example:

~~~java
final class NotMarked {
    @Override
    public NotMarked clone() throws CloneNotSupportedException {
        return (NotMarked) super.clone();
    }
}
~~~

This is an illustrative class independent of the `Account` example. It **has a public `clone()`** and properly overrides `Object.clone()`, yet it does not `implement Cloneable`. Because the method delegates to `super.clone()`, the call will throw `CloneNotSupportedException` on a `NotMarked` instance.

This shows that **overriding the method** and **adding the marker** are two separate actions: for an implementation based on `Object.clone()`, both appropriate access permission and the marker condition are needed.

Distinguish further: if a class implements `clone()` itself using `new NotMarked(...)` without **calling `Object.clone()`**, it can create a copy itself without needing the marker. Therefore, the statement "if a class does not implement `Cloneable`, it can never have a copy method" is an overgeneralization. What `Object` specifies is the behavior of **`Object.clone()` itself**.

## 4. Runnable Java 17 example: marker, protected, checked exception, and shallow copy

Create file **`CloneableMarkerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CloneableMarkerDemo {

    // Has marker but does not expose clone() publicly.
    static final class MarkerOnly implements Cloneable {
        private final int value = 7;
    }

    // Exposes clone() publicly but has no marker:
    // super.clone() will throw CloneNotSupportedException.
    static final class NotMarked {
        @Override
        public NotMarked clone() throws CloneNotSupportedException {
            return (NotMarked) super.clone();
        }
    }

    // Primitive field: shallow copy is sufficient for this example.
    static final class Point implements Cloneable {
        private final int x;

        Point(int x) {
            this.x = x;
        }

        @Override
        public Point clone() {
            try {
                return (Point) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    // Reference field is a mutable list.
    static final class Bag implements Cloneable {
        private final List<String> items;

        Bag(List<String> input) {
            this.items = new ArrayList<>(input);
        }

        @Override
        public Bag clone() {
            try {
                return (Bag) super.clone(); // Shallow copy.
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        Bag copyWithSeparateList() {
            return new Bag(items); // Create a separate list via constructor.
        }
    }

    public static void main(String[] args) {
        MarkerOnly marker = new MarkerOnly();
        System.out.println("marker present: "
                + (marker instanceof Cloneable));
        System.out.println("Cloneable declared methods: "
                + Cloneable.class.getDeclaredMethods().length);

        try {
            new NotMarked().clone();
        } catch (CloneNotSupportedException e) {
            System.out.println("not marked: "
                    + e.getClass().getSimpleName());
        }

        Point point = new Point(7);
        Point pointCopy = point.clone();
        System.out.println("point distinct: " + (point != pointCopy));
        System.out.println("point x equal: " + (point.x == pointCopy.x));
        System.out.println("point equals copy: " + point.equals(pointCopy));

        Bag original = new Bag(List.of("A"));
        Bag shallow = original.clone();
        Bag separate = original.copyWithSeparateList();

        System.out.println("shallow distinct bag: "
                + (original != shallow));
        System.out.println("shallow shares list: "
                + (original.items == shallow.items));
        System.out.println("separate shares list: "
                + (original.items == separate.items));

        original.items.add("B");
        System.out.println("shallow items: " + shallow.items);
        System.out.println("separate items: " + separate.items);

        int[] numbers = {1, 2};
        int[] numbersCopy = numbers.clone();
        System.out.println("array distinct: " + (numbers != numbersCopy));
        System.out.println("array same contents: "
                + Arrays.equals(numbers, numbersCopy));

        int[][] matrix = {{1, 2}};
        int[][] matrixCopy = matrix.clone();
        System.out.println("inner array shared: "
                + (matrix[0] == matrixCopy[0]));
    }
}
~~~

Compile/run in the directory containing the file (JDK 17 or later):

~~~bash
javac CloneableMarkerDemo.java
java CloneableMarkerDemo
~~~

**Expected output:**

~~~text
marker present: true
Cloneable declared methods: 0
not marked: CloneNotSupportedException
point distinct: true
point x equal: true
point equals copy: false
shallow distinct bag: true
shallow shares list: true
separate shares list: false
shallow items: [A, B]
separate items: [A]
array distinct: true
array same contents: true
inner array shared: true
~~~

Explanation by group:

1. `MarkerOnly` implements the marker, but the `Cloneable` interface has **0 declared methods**. The program does not call `marker.clone()`, because `Object.clone()` remains `protected` in this case.
2. `NotMarked` has a public override yet calls `super.clone()` without the marker, so it receives the checked exception `CloneNotSupportedException`.
3. `Point.clone()` uses `super.clone()` to create a new instance. The two `x` values are equal because the primitive type is copied by value. However, `point.equals(pointCopy)` is `false`, because class `Point` **does not override `equals()`**, thus inheriting identity-based equality from `Object`.
4. `Bag.clone()` creates a different `Bag` object but **with the same `items`** (shallow copy). Meanwhile, `copyWithSeparateList()` uses the constructor to create another `ArrayList`. When modifying the source list, the shallow copy sees `[A, B]` while the copy with a separate list keeps `[A]`.
5. `int[].clone()` creates a different one-dimensional array with the same primitive elements. `int[][].clone()` only creates a different **outer array**; the inner sub-arrays are still shared.

In the example, `Bag` only contains `String` (immutable), so copying the `ArrayList` separately suffices to isolate string addition/removal operations. If the list contains mutable objects, `new ArrayList<>(items)` still only copies **the list structure**, not each element itself.

## 5. Why doesn't `Cloneable reference = ...` have `clone()`?

Because `Cloneable` is empty, a variable declared with static type `Cloneable` has no `clone()` method in the interface's API set:

~~~java
Cloneable value = new Point(7);

// value.clone(); // Does not compile: Cloneable does not declare clone().
~~~

This is an illustrative snippet using the `Point` type from the previous program. Even when the runtime instance is a `Point` that already has `public Point clone()`, the **static type** of variable `value` does not allow calling `value.clone()`. One can call `((Point) value).clone()` when the runtime type is known for certain and the design permits, but casting should not be relied upon as a general copying mechanism.

To design a generic API so clients can invoke copying without knowing the concrete class, declare **a separate interface with an explicit copy method**:

~~~java
interface Copyable<T> {
    T copy();
}
~~~

This is an illustrative interface. Implementing classes decide the semantics of `copy()` themselves (shallow copy, structural copy, or creating a new value object) and document it clearly. **Do not** confuse a custom `Copyable<T>` interface with `java.lang.Cloneable`.

## 6. Role of `@Override`, return type, and exceptions

Overriding accurately is just as important as with other `Object` methods:

~~~java
@Override
public Point clone() {
    try {
        return (Point) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
~~~

- `@Override` ensures the compiler recognizes this as an override of `Object.clone()`, not an accidental overload with added parameters.
- `public` widens access scope from `protected`; an override cannot narrow visibility compared to the parent method.
- `Point` is a covariant return type compatible with `Object`, saving clients from casting after calling `point.clone()`.
- Not declaring the checked exception in the override is valid: an overriding method is allowed to omit `throws CloneNotSupportedException`. Only when calling `super.clone()` inside the method body is it necessary to handle the exception declared by the original method.
- `super.clone()` creates a shallow copy via inheritance mechanics; it **does not call `Point()`** to re-run normal initialization logic.

If a class is **not `final`**, subclasses and inheritance conventions must be examined carefully. `super.clone()` uses the instance's runtime type and can copy subclass fields under the same shallow rules. A subclass containing mutable resources or complex business invariants may need to adjust sub-structures after copying. You should not arbitrarily extend cloning across an inheritance hierarchy without clearly designing who is responsible for copying each level.

## 7. Shallow copy, deep copy, and alternatives

| Approach | What is newly created? | Points to note |
| --- | --- | --- |
| `super.clone()` on a valid class | Outer instance and copies of field values; reference fields keep original references | **Shallow copy**, may share child objects |
| `array.clone()` | A new array at the outer level | Multi-dimensional arrays still share sub-arrays |
| `new ArrayList<>(oldList)` | New list structure | Element objects in both lists may still share references |
| Copy constructor `new Type(original)` | According to constructor logic defined by the developer | Can proactively deep-copy certain fields and keep immutable fields |
| Static factory `Type.copyOf(original)` | According to the defined factory contract | The name `copyOf` does not automatically guarantee the copy is always a distinct instance |
| Immutable object design | Immutable state can be safely shared | Reduces need for cloning; must ensure immutability in sub-structures too |

**Deep copy** is not a built-in switch of `Cloneable`. To deep copy an object graph containing arrays, lists, maps, and nested objects, you must define how to duplicate each component that needs separation. You must consider aliasing (two paths in the object graph pointing to the same object), cycles (circular references), resources outside the JVM (sockets/file handles), and business invariants. Going completely deep is sometimes infeasible or misses the goal.

If a data type contains mostly immutable values like `String`, `LocalDate`, or records made entirely of immutable components, a **copy constructor/factory** is usually easier to understand than `Cloneable`. For immutable objects, creating a separate copy may be unnecessary because both sides can safely share the same immutable data.

## 8. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "`implements Cloneable` automatically provides `public clone()`." | `Cloneable` declares no methods; `Object.clone()` is inherently `protected` |
| "Interface `Cloneable` defines `clone()`." | `clone()` is declared in `Object` |
| "Just call `clone()` through a `Cloneable` variable." | Static type `Cloneable` has no `clone()` API |
| "Overriding `clone()` and calling `super.clone()` is enough for every class." | May need to copy mutable state separately to avoid unintended sharing |
| "Without implementing `Cloneable`, any custom method named `clone` fails." | Only the `Object.clone()` mechanism checks the marker; manual copying approaches can differ |
| "`clone()` always makes `clone.equals(original)` `true`." | Not mandatory; for example, default `Point` compares identity and returns `false` |
| "Clone re-calls the constructor like `new`." | `Object.clone()` copies field state, without running constructors via normal initialization flow |
| "`int[][]` gets cloned completely down to every row." | `matrix.clone()` only duplicates the outer array |
| "Copying a list deep-copies every element." | `new ArrayList<>(...)` is a copy of the list structure; mutable elements may be shared |

## 9. Self-check questions

1. **How many methods does `Cloneable` declare?** — Zero methods; it is a marker interface.
2. **If a class `implements Cloneable` without overriding `clone()`, is it guaranteed that external clients can call it?** — No. `Object.clone()` still has `protected` access.
3. **Who performs the field copying if you write `return (Type) super.clone();`?** — The implementation of `Object.clone()`.
4. **What happens if `super.clone()` is called on a runtime class that does not implement `Cloneable`?** — `CloneNotSupportedException`.
5. **When a field is `List<String>`, does `super.clone()` automatically create a new list?** — No; both objects share the list reference unless the override/copying approach replaces it.
6. **Why does an `int[][]` array still share rows after `clone()`?** — Because the outer array is shallow-copied, and each of its elements is a sub-array reference.
7. **If an easy-to-call copying API is needed, what should be done?** — Expose a method/copy constructor/factory with a clear contract, decide copy depth based on the data; only choose `Cloneable`/`Object.clone()` when you clearly understand its behavior and limitations.

**Remember:** `Cloneable` is only a **signal for the `Object.clone()` mechanism**. It does not define a method in the interface, does not automatically make `clone()` public, and does not automatically provide a deep copy. Distinguish three questions: **does the object have the marker?**, **which copy method do clients have permission to call?**, and **which parts of the data are actually duplicated?**

### Source references

- [Java SE 17 — Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html)
- [Java SE 17 — Object.clone()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone())
- [Java Language Specification 17 — Array Members `10.7`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7)