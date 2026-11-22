# Object.clone() does not call the regular constructor

## 1. The most important mechanism of Object.clone()

When creating an object with `new`, Java runs the object initialization sequence according to language rules: invoking the appropriate constructor, executing instance initialization, and handling constructors up the inheritance chain. Conversely, **`java.lang.Object.clone()` creates a new object without calling the regular constructor of the cloned object's class**. Instance field initializers and instance initializer blocks are also not re-run for the copy created by `Object.clone()` itself.

Instead of re-running initialization logic, `Object.clone()` creates a new object of the same runtime class and **copies field values** from the original object as if by assignment. Primitive values are copied; reference fields have their **references** copied, without automatically creating copies of child objects.

The differences can be seen in the table:

| Action | Runs the new object's constructor? | How are fields handled? |
| --- | --- | --- |
| `new Example(...)` | Yes | According to the class's initializers and constructor |
| `super.clone()` reaching `Object.clone()` | **No** | Copies field values from the original object to the new object |
| Copy constructor `new Example(other)` | **Yes** | According to logic written by the developer inside the constructor |
| A `clone()` override calling `new Example(...)` itself | **Yes**, because the override calls `new` | Decided by the override's own implementation |

Read the statement "the constructor does not run" accurately: it refers to **the copy actually created by `Object.clone()`**. `clone()` is an overridable method; a custom implementation can certainly call a constructor explicitly. Do not infer that "every method named `clone` in every library never calls a constructor".

## 2. Why doesn't Java re-initialize the object from scratch?

The `Object.clone()` Javadoc describes the default operation conceptually:

1. Create a new instance belonging to **the same runtime class** as the original object.
2. Copy **the contents of each field** from the original object to the new instance, equivalent to assignment.
3. Do not recursively copy objects referenced by fields: this is a **shallow copy**.
4. Return the new object to the caller.

For example, an object has the fields:

```java
int id = 42;
String label = "A";
int[] scores = {10, 20};
```

When cloning with `Object.clone()`, the copy receives `id = 42`, receives a reference to the held `String`, and receives **the same reference** to the `scores` array. No constructor automatically creates a new array for the copy, even if the class constructor has normalization or defensive array-copying logic.

Therefore, if the constructor increments a counter, writes logs, registers the object with a manager, opens a connection, or allocates resources, those side effects **do not automatically happen a second time** when `Object.clone()` copies the object. A custom design is needed if the copy truly must be registered or allocated independent resources.

This does not mean **static initializers** are part of the cloning process. The class must be initialized under general rules before corresponding operations execute; `Object.clone()` does not re-run static initializers, constructors, or instance initializers for the copy. Do not use a constructor counter as an absolute instance count if the class allows cloning.

## 3. Java 17: proving constructors and instance initializers do not re-run

The example below has two counters: one for an **instance initializer block** and one for a **constructor**. Both increment when using `new`, but do not increment when calling `clone()` inheriting `Object.clone()` behavior.

```java
public class CloneConstructorDemo {
    static final class TrackedItem implements Cloneable {
        static int initializerRuns;
        static int constructorCalls;

        final int id;
        final int[] scores;

        {
            initializerRuns++;
        }

        TrackedItem(int id, int[] input) {
            constructorCalls++;
            this.id = id;
            this.scores = input.clone();
        }

        @Override
        public TrackedItem clone() {
            try {
                return (TrackedItem) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        TrackedItem original = new TrackedItem(7, new int[] {10, 20});
        System.out.println(TrackedItem.initializerRuns);
        System.out.println(TrackedItem.constructorCalls);

        TrackedItem copy = original.clone();
        System.out.println(TrackedItem.initializerRuns);
        System.out.println(TrackedItem.constructorCalls);

        System.out.println(original != copy);
        System.out.println(original.id == copy.id);
        System.out.println(original.scores == copy.scores);

        copy.scores[0] = 99;
        System.out.println(original.scores[0]);
    }
}
```

Save file `CloneConstructorDemo.java` and run:

```bash
javac CloneConstructorDemo.java
java CloneConstructorDemo
```

Exact output:

```text
1
1
1
1
true
true
true
99
```

Explanation:

1. `new TrackedItem(...)` runs the instance initializer and constructor, so both counters equal `1` respectively.
2. `original.clone()` calls `super.clone()` and reaches `Object.clone()`. After cloning, both counters **remain `1`**: no regular initializer or constructor ran again for the copy.
3. `original != copy` is `true`: there is a new object.
4. `original.id == copy.id` is `true`: the `int` value was copied.
5. `original.scores == copy.scores` is `true`: the `scores` field of both objects points to **the same array**.
6. Modifying `copy.scores[0]` changes `original.scores[0]` to `99`. This is a consequence of **shallow copy**, not running the constructor a second time.

The constructor cloned the input array to protect the original object from mutation through the `input` parameter. However, `Object.clone()` **does not re-run** that `input.clone()` step, so the copy still shares the original object's internal array.

## 4. Cloneable and access permissions of Object.clone()

`Object.clone()` has `protected` access scope and declares `throws CloneNotSupportedException`. Not every object can have `clone()` called publicly from code outside the class.

`java.lang.Cloneable` is a **marker interface**: it declares no `clone` method. It merely marks that instances of the class are allowed to be cloned using the `Object.clone()` mechanism. If the object does not implement `Cloneable`, calling `Object.clone()` raises `CloneNotSupportedException`. **Java arrays** are a convenient exception: array types implement `Cloneable` and have a public `clone()` operation.

For classes supporting cloning, the common pattern is:

```java
@Override
public MyType clone() {
    try {
        return (MyType) super.clone();
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
```

This is an illustrative snippet **inside class `MyType implements Cloneable`**, not a standalone file. It exposes the `clone` method publicly, uses a specific return type, and turns the checked exception into an unexpected error when the class has committed to supporting clone.

**Do not think that merely writing `implements Cloneable` automatically gives the class a public `clone()` method.** That interface declares no methods; if external code needs to call it, an appropriate public API is needed.

Example illustrating the error when `Cloneable` is not implemented:

```java
public class CloneableRequirementDemo {
    static final class NoCloneSupport {
        @Override
        public NoCloneSupport clone() throws CloneNotSupportedException {
            return (NoCloneSupport) super.clone();
        }
    }

    public static void main(String[] args) {
        try {
            new NoCloneSupport().clone();
            System.out.println("Unexpected success");
        } catch (CloneNotSupportedException ex) {
            System.out.println("CloneNotSupportedException");
        }
    }
}
```

Run `javac CloneableRequirementDemo.java` and `java CloneableRequirementDemo`:

```text
CloneNotSupportedException
```

Here the `clone()` method is public so it can be called, yet the instance is not `Cloneable`. Hence `Object.clone()` rejects cloning. An implementation that creates objects itself using `new` can choose different behavior, but that is the implementation's own decision, not `Object.clone()`'s default mechanism.

## 5. How does Object.clone() copy final fields?

When a constructor creates an object, it usually assigns `final` fields during initialization. In the first example, both `id` and `scores` are `final`.

When `Object.clone()` creates a copy, `final` fields also **receive copied values** from the original object. That does not mean a constructor was called implicitly, nor does it mean the class's Java code can reassign a `final` field after cloning.

- For `final int id`, the copy keeps the same integer `id`.
- For `final int[] scores`, the copy keeps **the same array reference**, even though that array remains mutable.
- If code wants to shallow-clone first and then replace `scores` with another array to achieve a deep copy, normally **it cannot reassign** a `final` field inside the `clone()` method as with a normal field.

Distinguish **finality of the reference variable** from **immutability of the referenced object**. `final` does not turn an `int[]` into an unmodifiable array.

If the data type truly needs `final` fields and deep defensive copying, a **copy constructor or static factory** usually makes the intent clearer than trying to adjust `final` fields after `super.clone()`.

## 6. Shallow copy is not the same as deep copy

`Object.clone()` by default copies field values at **one object layer**, without traversing the entire object graph.

| Field kind | After `Object.clone()` | Risk |
| --- | --- | --- |
| `int`, `boolean`, and other primitives | Value is copied | No shared mutable object from primitives alone |
| `String` | Reference is copied | Usually acceptable because `String` is immutable |
| `int[]` | Reference is copied | Both objects share the mutable array |
| `ArrayList<?>` | Reference is copied | Both objects share the same list |
| Mutable child object | Reference is copied | Mutating the child object may affect both |
| Immutable child object | Reference is copied | Usually safe to share under the type's contract |

"Deep copy" is not a single operation performed by `Object.clone()` by default. For complex object graphs, you must decide which parts must be independent, which parts are shared, how to handle reference cycles, and the nature of external resources.

A deep copy for an `int[]` field can be as simple as `array.clone()`. But for `List<MutableThing>`, `new ArrayList<>(list)` alone copies the list structure **without copying the element objects**.

### Overriding clone to additionally copy a mutable array

The following example uses a non-final array field to illustrate how overriding `clone()` actively creates an independent copy for the array.

```java
public class DeepCopyCloneDemo {
    static final class Sample implements Cloneable {
        private int[] values;

        Sample(int[] values) {
            this.values = values.clone();
        }

        @Override
        public Sample clone() {
            try {
                Sample copied = (Sample) super.clone();
                copied.values = values.clone();
                return copied;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        int first() {
            return values[0];
        }

        void changeFirst(int number) {
            values[0] = number;
        }

        boolean sharesArrayWith(Sample other) {
            return values == other.values;
        }
    }

    public static void main(String[] args) {
        Sample original = new Sample(new int[] {4, 5});
        Sample copied = original.clone();

        System.out.println(original != copied);
        System.out.println(original.sharesArrayWith(copied));

        copied.changeFirst(99);
        System.out.println(original.first());
        System.out.println(copied.first());
    }
}
```

Save as `DeepCopyCloneDemo.java` and run:

```bash
javac DeepCopyCloneDemo.java
java DeepCopyCloneDemo
```

Output:

```text
true
false
4
99
```

Here `super.clone()` still **does not call the constructor**. Then code in the override creates a new array via `values.clone()` and assigns it to the copy's mutable field. Thus both objects are independent with respect to the array.

Do not conclude that "overriding `clone` always creates a deep copy": this example only deepens **one one-dimensional primitive array field**. For nested structures, mutable elements, or special resources, further relationships must be considered.

## 7. Copy constructor: an option with a real constructor

If you want to explicitly run initialization logic and control `final` fields, you can design a **copy constructor**. It is not `Object.clone()`, but a regular `new` invocation:

```java
public class CopyConstructorDemo {
    static final class Snapshot {
        static int constructorCalls;
        final int[] samples;

        Snapshot(int[] samples) {
            constructorCalls++;
            this.samples = samples.clone();
        }

        Snapshot(Snapshot source) {
            this(source.samples);
        }
    }

    public static void main(String[] args) {
        Snapshot first = new Snapshot(new int[] {1, 2});
        Snapshot second = new Snapshot(first);

        System.out.println(Snapshot.constructorCalls);
        System.out.println(first != second);
        System.out.println(first.samples != second.samples);

        second.samples[0] = 9;
        System.out.println(first.samples[0]);
        System.out.println(second.samples[0]);
    }
}
```

Save `CopyConstructorDemo.java` and run:

```bash
javac CopyConstructorDemo.java
java CopyConstructorDemo
```

Output:

```text
2
true
true
1
9
```

The copy constructor calls another constructor via `this(source.samples)`, and the `samples.clone()` logic actually runs to keep separate arrays. Because `new` is used, the constructor counter increments twice for two objects. With `Object.clone()` in the first example, only the original object's constructor was called.

The advantage of this approach is that the copy creation process is explicit: choosing which fields to copy, which data to normalize, and how to assign `final` fields. The drawback is needing to define a policy for inherited classes or runtime subtypes if the class can be subclassed; a copy created by a class's copy constructor does not automatically guarantee preserving a child object's runtime class.

## 8. Java arrays have their own clone()

Every Java array supports `clone()` and returns a **new** array of the same type and length, copying first-level elements. This is a convenient special case that does not require the developer to write `implements Cloneable`.

```java
public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        int[] copied = source.clone();

        System.out.println(source != copied);
        System.out.println(source[0] == copied[0]);

        copied[0] = 8;
        System.out.println(source[0]);

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] outerCopy = matrix.clone();

        System.out.println(matrix != outerCopy);
        System.out.println(matrix[0] == outerCopy[0]);

        outerCopy[0][0] = 99;
        System.out.println(matrix[0][0]);
    }
}
```

Save `ArrayCloneDemo.java` and run:

```bash
javac ArrayCloneDemo.java
java ArrayCloneDemo
```

Output:

```text
true
true
1
true
true
99
```

An `int[]` array has primitive elements, so its clone creates a sufficiently independent copy for the integers inside. An `int[][]` array has outer-level elements that are references to sub-arrays. Cloning the outer array only copies those references; sub-arrays remain shared.

This is why **cloning a multi-dimensional array does not mean deep cloning all dimensions**.

## 9. Object.clone() and initialization invariants

Constructors often hold responsibilities beyond assigning field values:

- Checking `null` arguments, bounds, or data formatting.
- Normalizing and defensively copying mutable inputs.
- Incrementing counters, logging, or recording object creation.
- Assigning derived fields from input parameters.
- Registering the object with other components or allocating resources.

Because `Object.clone()` does not run the constructor, **none of the work above is automatically redone**. Existing field values are copied, but independent initialization side effects do not happen a second time.

This raises design questions:

1. If an object holds a file handle or socket, should the copy share the resource, hold a reference, or be disallowed from cloning?
2. If the constructor registers the object in a registry, should the clone register separately or be forbidden?
3. If a field is a mutable array defensively copied by the constructor, does clone need another copy to avoid aliasing?
4. If a "unique ID" is generated by the constructor, should the copy keep the same ID or need a new ID? The answer depends on *entity* vs. *value* semantics.
5. If a superclass defines `clone()` and a subclass adds mutable fields, has the subclass properly deep-copied the new state?

Do not assume that skipping the constructor makes every cloned object invalid. If the original object has valid state and the copy only needs the same field values, a shallow clone may fulfill the goal. **The issue is that the constructor's design responsibilities are not automatically re-executed.**

Do not use a constructor counter to "accurately count every existing instance" if object creation paths include `Object.clone()`. Also do not use cloning to bypass mandatory initialization/validation rules of the application.

## 10. Distinguishing formal requirements, recommendations, and implementation details

| Statement | Classification | Why |
| --- | --- | --- |
| "`Object.clone()` creates a new instance and copies field values from the original object." | **Method contract** | Directly described by the API |
| "`Object.clone()` does not run the regular constructor for the copy." | **Default mechanism behavior** | Copies fields instead of initializing via constructor |
| "Default cloning deep-copies every referenced object." | **False** | Default cloning is shallow copy |
| "A class wanting to use `Object.clone()` must implement `Cloneable`; otherwise `CloneNotSupportedException` occurs." | **Default mechanism contract** | `Cloneable` is a marker interface |
| "`Cloneable` provides a public `clone()` method out of the box." | **False** | The interface declares no `clone` |
| "Every `clone()` override never calls a constructor." | **False** | Custom overrides can call `new` |
| "Copying an object with mutable fields should consider defensive copying." | **Design recommendation** | Avoids unintended state sharing |
| "Merely calling `super.clone()` is always safe with sockets, threads, locks, and file handles." | **False** | Resources have distinct contracts and are not automatically copied with valid semantics |
| "Use a copy constructor/static factory when clear initialization or `final` fields are needed." | **Recommendation** | Usually makes invariants and copying policies easier to control |
| "`x.clone().equals(x)` must be true for every class." | **Not an absolute guarantee** | The `Object.clone` Javadoc presents this as a common intent, not an absolute requirement |
| "`Object.clone()` always preserves classloader order, address allocation, or identity hash value like the old object." | **No such guarantee** | JVM details are not part of the clone contract |

According to the `Object.clone()` Javadoc, `x.clone() != x` and the same runtime class are normally expected; statements like `x.clone().equals(x)` are presented at the level of expectation, not an absolute obligation for every `clone()` override implementation. More important when designing an API is documenting **the copying policy** of that specific class.

## 11. Common mistakes

**Mistake 1 — thinking clone re-runs the constructor.** Leads to wrong predictions about initializer/constructor call counts, object registration logic, copied arrays, or generated IDs. Remember that standard `Object.clone()` behavior is field copying.

**Mistake 2 — assuming final fields are not cloned.** `Object.clone()` copies final field values; it does not need to call the constructor to reassign them from source code. However, a final field holding a mutable reference can continue sharing the inner object.

**Mistake 3 — believing implementing Cloneable is enough for a public clone API.** `Cloneable` is just a marker; the class needs to expose a clone method itself if external callers need to use it.

**Mistake 4 — returning `super.clone()` and assuming it is a deep copy.** All referenced child objects may still be shared. For `List`, arrays, mutable objects, and external resources, the policy must be specified explicitly.

**Mistake 5 — cloning a two-dimensional array and thinking all rows were copied.** `matrix.clone()` only copies the outer array; sub-arrays still share references.

**Mistake 6 — copying resources without checking lifecycle.** File handles, locks, streams, or sockets may lack suitable copying semantics. Some types should provide a factory creating a new resource; some types should forbid cloning.

**Mistake 7 — using cloning to create a new entity yet accidentally keeping the original ID.** If IDs must be unique, preserving the identifier field via shallow clone can violate business requirements, even though `Object.clone` works exactly as documented by its API.

## 12. Self-practice questions

**Question 1.** A constructor increments `static int created` each time it runs. After one `new Item()` and one `super.clone()` creating a copy, how many times does `created` increment by default?

**Answer:** Once, assuming no override increments the counter itself or calls another constructor. `Object.clone()` does not run the regular constructor for the copy.

**Question 2.** A field `final int[] data` is in the original object. After `Object.clone()`, do the two objects hold two independent arrays?

**Answer:** No. Final fields are copied at the **reference** level, so by default they point to the same array. Final does not make array elements immutable.

**Question 3.** A class implements `Cloneable` without exposing public `clone()`. Is external code guaranteed to be able to call `instance.clone()`?

**Answer:** No. `Object.clone` is `protected` and `Cloneable` declares no public methods.

**Question 4.** In a `clone()` override, the author writes `return new MyType(this);`. Does the constructor run?

**Answer:** Yes. That is a `new` invocation inside a custom implementation; it is not `Object.clone()`'s object creation behavior.

**Question 5.** Why shouldn't shallow clone be used as a general solution for an object owning a socket?

**Answer:** The copy can share resource references and lifecycle management state. Copying field values does not create an independent socket or synchronize open/close rules.

**Question 6.** Does `int[][] copied = matrix.clone();` guarantee `matrix[0] != copied[0]`?

**Answer:** No. Cloning the outer array copies references to sub-arrays. Corresponding rows can still be the same object.

## 13. Remember

- **`Object.clone()` does not call the copy's regular constructor or instance initializers.** It creates a new instance and copies field values.
- **Shallow copy:** primitives are copied by value; reference fields keep the same pointed-to objects unless an override proactively copies more.
- `Cloneable` is a marker interface; `Object.clone` is `protected` and can throw `CloneNotSupportedException`.
- `final` fields are still copied by the clone mechanism; a final reference is not equivalent to deep immutability.
- A `clone()` override **can** invoke a constructor, factory, or deep-copy logic itself; one must read the specific implementation.
- Arrays have their own `clone()`; `int[]` copies numbers independently, `int[][]` only copies the outer array.
- Use a **copy constructor** or factory when explicit initialization and invariant control are needed, especially for objects with final fields or hard-to-copy resources.
- When building a copy API, clearly document which fields are shared, which are independent, and how IDs, registries, and resources are handled.

Official documentation references: [`Object.clone()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()), [`Cloneable` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html), [Java Language Specification — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html).