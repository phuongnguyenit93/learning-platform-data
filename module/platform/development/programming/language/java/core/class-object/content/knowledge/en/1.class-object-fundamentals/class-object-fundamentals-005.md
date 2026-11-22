# One Class Creates Multiple Objects with Independent State

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a **class** as a blueprint defining data/behavior from an **object/instance** as an entity created from that class.
- Explain why two successful instantiations with `new` create two distinct objects, each holding the values of its own **instance fields**.
- Distinguish creating a new object from assigning an additional **reference** to an existing object.
- Recognize `static` fields, shared member objects, and cases where the states of two objects affect each other.
- Verify independence with runnable Java examples and apply encapsulation to manage state.

## 1. What Does One Class, Multiple Objects Mean?

A **class** describes the data fields, constructors, and methods that instances of that type can use. An **object** is a concrete instance of the class, with its own state at a given point in time.

For example, the `Counter` class specifies that each counter has a `name` and a `value`. We can create counter A and counter B from the same class without writing two different class definitions. Both call the same `increment()` method code, but the method operates on the object receiving the call:

- `a.increment()` modifies the `value` field belonging to the object referenced by `a`.
- `b.increment()` modifies the `value` field belonging to the object referenced by `b`.
- When `a` and `b` reference two different objects and do not share mutable data, updating A does not change the value of B.

**Important condition:** "Independent state" refers to the state region that genuinely belongs to each individual object, especially primitive-type instance fields or separate member objects. It does not mean that all objects in a program are completely unable to share data.

## 2. Complete Example: Two Independent Counters

Save the program as **`CounterDemo.java`**:

~~~java
public class CounterDemo {
    static final class Counter {
        private final String name; // Belongs to each Counter
        private int value;         // Belongs to each Counter, defaults to 0

        private static int totalCreated; // Shared across the Counter class

        Counter(String name) {
            this.name = name;
            totalCreated++;
        }

        void increment() {
            value++;
        }

        String name() {
            return name;
        }

        int value() {
            return value;
        }

        static int totalCreated() {
            return totalCreated;
        }
    }

    public static void main(String[] args) {
        Counter a = new Counter("A");
        Counter b = new Counter("B");

        a.increment();
        a.increment();
        b.increment();

        System.out.println("a = " + a.name() + ":" + a.value());
        System.out.println("b = " + b.name() + ":" + b.value());
        System.out.println("created = " + Counter.totalCreated());
        System.out.println("a == b: " + (a == b));

        Counter alias = a;
        alias.increment();
        System.out.println("a after alias: " + a.value());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CounterDemo.java
java CounterDemo
~~~

Expected output of the program:

~~~text
a = A:2
b = B:1
created = 2
a == b: false
a after alias: 3
~~~

**Step-by-step analysis:**

1. `new Counter("A")` creates the first object; `new Counter("B")` creates the second object. The two variables `a` and `b` hold two different references.
2. Each object has its own `name` and `value` fields. Two calls to `a.increment()` raise A to 2; one call to `b.increment()` raises B to 1.
3. `totalCreated` is declared `static`, so there is no separate copy of `totalCreated` for A and B. The constructor increments the same class field; after two creations, the value is 2.
4. `a == b` is `false` because these are two references to two different objects.
5. `Counter alias = a` **does not create a third counter**. `alias` and `a` both reference object A; calling `alias.increment()` makes `a.value()` become 3. The `totalCreated` variable remains 2.

At the point after the first three `increment()` calls, this can be visualized as:

~~~text
Reference variables             Two Counter objects
a --------------------------->  #1 { name: "A", value: 2 }
b --------------------------->  #2 { name: "B", value: 1 }

Counter.totalCreated = 2        (class field)
~~~

After the statement `Counter alias = a`, both variables `a` and `alias` point to object #1. The diagram above is a **conceptual model**, not a guarantee of physical layout in JVM memory.

## 3. How Do Instance Fields and Class Fields Differ?

| Criterion | Instance field (without `static`) | Class field (with `static`) |
| --- | --- | --- |
| Associated with | Each created object | The class within the loaded class context |
| Number of state copies | Each object has its own corresponding field | One class field shared within that context |
| Typical access | `object.field` or via an object method | `ClassName.field` or via a `static` method |
| Changing the value | Changes only the field on the target object | Objects sharing/accessing the class state will see the change |
| Example | `private int value;` | `private static int totalCreated;` |

In the example, Java executes the `increment()` code according to the object currently receiving the call; the expression `value++` is equivalent to operating on `this.value`. It is the same method, but `this` differs between `a.increment()` and `b.increment()`.

The initial value of an `int` instance field is `0` if the constructor does not assign another value. Primitive-type fields also have their own default values (for example, `boolean` is `false`); reference fields default to `null`. **Local variables** must be assigned before being read and do not automatically follow the field default-value rules.

Declaring `final` on a field such as `private final String name` means the field can only be assigned according to initialization rules and cannot be reassigned after the object has been initialized; it does not make the entire object immutable. In the example, `value` can still be incremented.

**Limitation note:** Instances can still encounter other shared state, such as `static` variables, caches, or shared services passed into them. In addition, updating `totalCreated++` in the example is only meant to illustrate class state in a single-threaded program; if multiple threads create objects concurrently, this increment does not guarantee atomicity.

## 4. `new` Creates Objects; Reference Assignment Does Not Create Objects

Consider these three statements:

~~~java
Counter a = new Counter("A");
Counter b = new Counter("B");
Counter c = a;
~~~

This is an illustrative snippet using the `Counter` class from the previous example, not a standalone program. After the three statements execute successfully:

- There are **two** `Counter` objects: one for A, one for B.
- There are **three reference variables**: `a`, `b`, `c`.
- `a == c` is `true` because they reference the same object A; `a == b` is `false`.
- Modifying the object through `c` is also observed through `a`; modifying the object through `b` does not directly affect A.

In Java, a variable of a class type holds a **reference value**, not the entire object. Assigning `c = a` copies the reference value; it does not automatically create a copy of the object. Passing a reference to a method parameter also passes a **copy of the reference value**, because Java always passes parameters by value. The method can modify the object that the reference points to, but reassigning the parameter variable does not change the external reference variable to a new object.

Two objects with the same field contents can still be two different objects. For references, the `==` operator checks whether they point to the same object; `equals()` represents the equality relation defined by the class (by default, inherited from `Object`, it is based on reference identity). Do not use `==` to conclude that two objects have identical data.

## 5. Why Can Two Different Objects Still Affect Each Other?

Instance fields are separate data storage locations, but the **value of a reference field** can point to the same mutable object. For example, two different profiles both hold a reference to an `ArrayList`. When one profile adds an element to the shared list, the other profile sees the new element.

Save the following code in **`SharedStateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SharedStateDemo {
    static final class UnsafeProfile {
        private final List<String> tags;

        UnsafeProfile(List<String> tags) {
            this.tags = tags; // Keeps the caller's reference
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        List<String> tags() {
            return List.copyOf(tags);
        }
    }

    static final class SafeProfile {
        private final List<String> tags;

        SafeProfile(List<String> tags) {
            this.tags = new ArrayList<>(tags); // Creates a separate list
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        List<String> tags() {
            return List.copyOf(tags); // Returns an unmodifiable snapshot
        }
    }

    public static void main(String[] args) {
        List<String> shared = new ArrayList<>();
        UnsafeProfile p1 = new UnsafeProfile(shared);
        UnsafeProfile p2 = new UnsafeProfile(shared);

        p1.addTag("java");
        System.out.println("unsafe p2: " + p2.tags());

        SafeProfile safe1 = new SafeProfile(shared);
        SafeProfile safe2 = new SafeProfile(shared);
        safe1.addTag("oop");

        System.out.println("safe1: " + safe1.tags());
        System.out.println("safe2: " + safe2.tags());
    }
}
~~~

Run:

~~~bash
javac SharedStateDemo.java
java SharedStateDemo
~~~

Output:

~~~text
unsafe p2: [java]
safe1: [java, oop]
safe2: [java]
~~~

In the two `UnsafeProfile` objects, the `tags` fields are **two separate fields**, yet both contain the **same reference** to one `ArrayList`. The list state is therefore shared. In `SafeProfile`, the constructor copies the elements into a new `ArrayList`. Modifying the list inside `safe1` does not propagate to `safe2`. The `tags()` method returns a list that cannot be modified directly.

Copying via `new ArrayList<>(tags)` is a **shallow copy**: the new list still holds references to the original elements. In the example, the elements are immutable `String` objects, so this is sufficient to illustrate separating the list state. If the elements are mutable objects, the two lists can still share those elements; when deep isolation is needed, copying each element according to an appropriate data contract must be considered.

**Distinction:** Two objects pointing to the same `String` do not cause content-mutation issues because `String` is immutable. Conversely, `final List<String> tags` only prevents reassigning the `tags` reference; it does not by itself prevent `tags.add(...)`.

## 6. Designing Objects with Independent State

When an object needs to manage its own data, consider these steps:

1. **Place per-instance state into instance fields**, such as the `balance` of each account or the `quantity` of each shopping cart. Only use `static` for state that truly belongs to the class or is intentionally shared.
2. **Initialize via constructors** so each object receives valid initial values. Use `this.field` when needed to distinguish a field from a parameter of the same name.
3. **Encapsulate state** with `private` fields and behavior-representing methods (`deposit`, `increment`, `addItem`) to control update conditions. Only expose getters/setters when appropriate for the design.
4. **Control references to mutable data**: create new data structures in constructors, make defensive copies when receiving/returning data, or design immutable types if required.
5. **Test with at least two objects**: capture the state of B, modify A, and verify that B has not changed; also test the case where two variables reference the same object to understand the difference.

Here is a test example following the "A changes, B stays unchanged" mindset, assuming the `Counter` class from `CounterDemo` is used:

~~~java
Counter a = new Counter("A");
Counter b = new Counter("B");
a.increment();

if (a.value() != 1 || b.value() != 0) {
    throw new AssertionError("Two counters must have independent values");
}
~~~

This check snippet is an example to insert inside a method that can access `Counter`, not a standalone runnable Java file. Unlike Java's `assert` statement, which can be disabled by default if `-ea` is not enabled, throwing `AssertionError` here does not depend on the assertion-enabling flag.

## 7. Common Pitfalls and How to Recognize Them

| Misconception | Correct fact to remember |
| --- | --- |
| "A class has only one object." | Multiple objects can be instantiated from the same class. Each successful `new` creates a new object. |
| "Two variables of the same type always hold two different objects." | Two variables can hold the same reference; `b = a` does not create a new object. |
| "Every field in a class has its own separate copy." | `static` fields belong to class state and are shared within the corresponding class-loading context. |
| "Two different objects cannot affect each other." | They can reference the same mutable child object or share `static` state/shared services. |
| "Declaring `final` makes a list immutable." | `final` locks reassignment of the reference field; it does not freeze the referenced object. |
| "Copying a list performs a deep copy." | `new ArrayList<>(old)` creates a new list but still shares the reference-type elements. |
| "`a == b` compares the contents of two objects." | For reference variables, `==` compares object identity; `equals()` can be defined to compare contents. |

## 8. Self-Check

**Question 1.** If you create `Counter x = new Counter("X"); Counter y = new Counter("Y");` and only call `x.increment()`, what is `y.value()`?  
**Answer:** `0`, because `y` holds a different object with its own unincremented `value` field.

**Question 2.** If you then run `Counter z = x; z.increment();`, how many new objects are created and what is `x.value()`?  
**Answer:** No additional objects are created; `z` is simply an alias for `x`. `x.value()` becomes `2`.

**Question 3.** Two different objects both hold a mutable `List`. If only one object is updated, does the other always remain independent?  
**Answer:** No. If they point to the same `List`, modifying the list will be observable from both. To separate their state, you need to create a separate copy of the list or use an appropriate immutable design.

**Question 4.** Why does `Counter.totalCreated()` increase when creating both A and B, while `a.value()` and `b.value()` do not automatically increment each other?  
**Answer:** `totalCreated` is a shared `static` field, whereas `value` is an instance field belonging to each `Counter`.

**Remember:** A class can produce multiple objects; each object has its own instance fields. However, the independence of the **entire state** also depends on whether those fields reference shared mutable data, and whether the class uses `static` state or shared resources.
