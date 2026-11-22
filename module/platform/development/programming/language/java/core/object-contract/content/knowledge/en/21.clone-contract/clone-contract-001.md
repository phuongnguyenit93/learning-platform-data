# clone() creates a copy and copying semantics depend on the class

## 1. What is Clone and what needs to be understood correctly?

In Java, **clone()** is commonly used to create a new object from the state of an existing object. However, the method name **does not guarantee a deep copy**: the new object may share arrays, lists, or child objects with the original object. The copy depth, rules for preserving business identity, resource lifecycle, and mutability of the two instances **depend on the contract of the specific class**.

For example, an object has **String name** and **int[] scores**. Name is an immutable String so its reference can be shared safely. Scores is a mutable array: if the copy points to the same array, modifying an element through the copy will cause the original to observe the change. If two objects are required to be independent regarding scores, the array needs to be copied separately.

Distinguish three concepts:

- **Shallow copy:** the outer object is a new instance, but reference fields usually continue pointing to the old child objects.
- **Deep copy:** mutable components that require independence also have copies created. The required depth depends on the data structure and the domain's sharing policy.
- **Immutable snapshot:** creates an unchangeable value to store state at a point in time, usually via a copy constructor or factory with appropriately copied/frozen data.

Clone does not necessarily mean immutable, nor does it mean a copy with the same business ID. Determine in advance **what is kept**, **what needs to be separated**, and **what must not be copied**.

## 2. How do Object.clone() and Cloneable actually work?

In **java.lang.Object** there is the method:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

This is an **API signature**, not a standalone Java program. Object.clone is designed to create a new object and copy instance field values in a **shallow** manner. Primitives have their values copied; reference fields receive the same reference value. It does not sequentially call clone on child objects.

**java.lang.Cloneable** is a **marker interface** that declares no methods. When an object does not implement Cloneable, calling Object.clone on it throws **CloneNotSupportedException**. A class that implements Cloneable still **does not automatically expose a public clone() method** for external code to call, because Object.clone has protected access. To provide a public API, a class usually overrides **public clone()**, and can return the class type itself thanks to covariant return types.

A common pattern:

~~~java
@Override
public Widget clone() {
    try {
        return (Widget) super.clone();
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
~~~

This is a **snippet inside the Widget class implementing Cloneable**, not a standalone runnable file. This pattern is suitable when the method calls Object.clone with the marker already guaranteed. Another API might declare **throws CloneNotSupportedException** instead of catching it.

### Conventions, not absolute guarantees

The Object.clone documentation describes properties **normally expected**:

~~~text
x.clone() != x
x.clone().getClass() == x.getClass()
x.clone().equals(x)
~~~

The lines above are **not three mandatory requirements for every clone() override**. For example, if a class has not overridden equals, two instances with different references can still return false according to Object.equals. A class copying a resource may intentionally assign a new ID, causing equals by ID to return false. The actual contract must be documented on that class.

## 3. Java 17 example: shallow copy causing array sharing

Create file **ShallowCloneDemo.java**:

~~~java
import java.util.Arrays;

public class ShallowCloneDemo {
    static final class Report implements Cloneable {
        private final String title;
        private int[] scores;

        Report(String title, int[] scores) {
            this.title = title;
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
    }

    public static void main(String[] args) {
        Report original = new Report("Daily", new int[]{10, 20});
        Report copy = original.clone();

        System.out.println("different object: " + (original != copy));
        System.out.println("same array: " +
            (original.scores == copy.scores));

        copy.scores[0] = 99;

        System.out.println("original: " +
            Arrays.toString(original.scores));
        System.out.println("copy: " +
            Arrays.toString(copy.scores));
        System.out.println("title: " + copy.title);
    }
}
~~~

Compile and run:

~~~bash
javac ShallowCloneDemo.java
java ShallowCloneDemo
~~~

Output:

~~~text
different object: true
same array: true
original: [99, 20]
copy: [99, 20]
title: Daily
~~~

Because **super.clone()** only copies the **scores** reference, original and copy hold the same array. Both pointing to String title is not an issue because String is immutable. But for the scores array, one change affected both.

This is a **shallow copy** example, not a compilation error. It is only unsuitable if the API promises independently separated data. Additionally, the constructor in the example keeps the input array reference as-is; the caller can modify the original array externally. If complete isolation from creation is desired, defensive copying is needed in the constructor as well.

## 4. Separating mutable fields after super.clone()

When a class has a one-dimensional primitive array, it can call super.clone to create the object and then replace the copy's array reference with a new array. Create file **IndependentCloneDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class IndependentCloneDemo {
    static final class Batch implements Cloneable {
        private final String id;
        private int[] values;

        Batch(String id, int[] values) {
            this.id = Objects.requireNonNull(id);
            this.values = Objects.requireNonNull(values).clone();
        }

        public int[] values() {
            return values.clone();
        }

        @Override
        public Batch clone() {
            try {
                Batch copy = (Batch) super.clone();
                copy.values = values.clone();
                return copy;
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Batch other
                && id.equals(other.id)
                && Arrays.equals(values, other.values);
        }

        @Override
        public int hashCode() {
            return 31 * id.hashCode() + Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        Batch original = new Batch("B-1", new int[]{3, 5});
        Batch copy = original.clone();

        System.out.println("different object: " + (original != copy));
        System.out.println("same array: " + (original.values == copy.values));
        System.out.println("equal before: " + original.equals(copy));
        System.out.println("same hash before: " +
            (original.hashCode() == copy.hashCode()));

        copy.values[0] = 8;

        System.out.println("original: " + Arrays.toString(original.values));
        System.out.println("copy: " + Arrays.toString(copy.values));
        System.out.println("equal after: " + original.equals(copy));
    }
}
~~~

Run:

~~~bash
javac IndependentCloneDemo.java
java IndependentCloneDemo
~~~

Output:

~~~text
different object: true
same array: false
equal before: true
same hash before: true
original: [3, 5]
copy: [8, 5]
equal after: false
~~~

Explanation: **clone()** creates a new Batch object, then clones the values array to separate mutable state. **id** is an immutable String so sharing is safe. Because Batch's equals is based on **id and array contents**, before modifying the copy, equals is true and hashCode values match; after the copy is modified, the two values differ.

The **values** field is not declared final because the assignment **copy.values = ...** after **super.clone()** must be valid. If you want the array field to be final and the value data immutable, a **copy constructor** is usually more convenient. Do not conclude that a single array clone is a "forever deep copy": when the structure adds nested mutable objects inside, this approach may no longer suffice.

## 5. What happens when not implementing Cloneable?

Create file **CloneMarkerDemo.java**:

~~~java
public class CloneMarkerDemo {
    static final class NoMarker {
        Object attemptClone() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    static final class WithMarker implements Cloneable {
        private final int code;

        WithMarker(int code) {
            this.code = code;
        }

        @Override
        public WithMarker clone() {
            try {
                return (WithMarker) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        try {
            new NoMarker().attemptClone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("without marker: " +
                ex.getClass().getSimpleName());
        }

        WithMarker first = new WithMarker(42);
        WithMarker copy = first.clone();

        System.out.println("new object: " + (first != copy));
        System.out.println("copied code: " + copy.code);
    }
}
~~~

Run:

~~~bash
javac CloneMarkerDemo.java
java CloneMarkerDemo
~~~

Output:

~~~text
without marker: CloneNotSupportedException
new object: true
copied code: 42
~~~

**NoMarker** can call protected Object.clone from a method of the class, but Object.clone rejects it because the object does not implement Cloneable. **WithMarker** has both the marker and a public override, so the caller can invoke it and receive a copy.

Note the **checked** nature of CloneNotSupportedException: a call with a throws signature must be caught or declared. When the class itself controls Cloneable, the pattern of catching the exception and throwing AssertionError can be used to expose a situation that violates the design invariant.

## 6. Object.clone does not call the constructor for the copy

With the Object.clone mechanism, the new object receives copied state without running the class constructor again. This is a fundamental difference from **new** or a copy constructor.

Create file **ConstructorCloneDemo.java**:

~~~java
public class ConstructorCloneDemo {
    private static int constructorCalls;

    static final class Ticket implements Cloneable {
        private final int number;

        Ticket(int number) {
            constructorCalls++;
            this.number = number;
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

    public static void main(String[] args) {
        Ticket first = new Ticket(7);
        Ticket copy = first.clone();

        System.out.println("constructor calls: " + constructorCalls);
        System.out.println("different object: " + (first != copy));
        System.out.println("number: " + copy.number);
    }
}
~~~

Run:

~~~bash
javac ConstructorCloneDemo.java
java ConstructorCloneDemo
~~~

Output:

~~~text
constructor calls: 1
different object: true
number: 7
~~~

This can bypass validation steps, listener registration, lock/resource creation, ID generation, or secondary field computation in the constructor. When a class has **invariants** depending on the constructor, clone must be designed so that the result is always valid. You cannot by default clone a socket, file handle, stream, thread, or database connection in the sense of creating an additional independent resource.

## 7. Cloning one-dimensional arrays and nested arrays

Java arrays support **clone()**. For **int[]**, the new array contains copied int values. For **StringBuilder[]**, the new array contains references back to the same StringBuilder objects. The outer array is newly created, but element objects are usually not cloned.

For **int[][]**, the outer array holds **int[]** references. Calling clone on the outer array does not copy each row.

Create file **MatrixCloneDemo.java**:

~~~java
import java.util.Arrays;

public class MatrixCloneDemo {
    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};
        int[][] shallow = original.clone();

        int[][] independent = new int[original.length][];
        for (int i = 0; i < original.length; i++) {
            independent[i] = original[i].clone();
        }

        System.out.println("same outer: " + (original == shallow));
        System.out.println("shared row: " + (original[0] == shallow[0]));

        shallow[0][0] = 9;
        System.out.println("original after shallow: " +
            Arrays.deepToString(original));

        independent[1][0] = 7;
        System.out.println("original after independent: " +
            Arrays.deepToString(original));
        System.out.println("independent snapshot: " +
            Arrays.deepToString(independent));
    }
}
~~~

Run:

~~~bash
javac MatrixCloneDemo.java
java MatrixCloneDemo
~~~

Output:

~~~text
same outer: false
shared row: true
original after shallow: [[9, 2], [3, 4]]
original after independent: [[9, 2], [3, 4]]
independent snapshot: [[1, 2], [7, 4]]
~~~

Independent copies each row **before** shallow modifies the initial data, so it preserves a snapshot of the initial values. If a row can be null, it must be handled before calling **original[i].clone()**. If inner elements are mutable objects rather than primitives, cloning each array level still leaves leaf objects shared.

**Arrays.copyOf** and **System.arraycopy** also copy elements without automatically cloning every element object. Choose the copying method based on the intended semantics, not based on the method name.

## 8. Cloning collections also requires checking specific class documentation

The **List**, **Set**, and **Map** interfaces are not required to provide clone. Some concrete classes, such as **ArrayList**, have a clone method that creates a **shallow copy** of the list structure. The elements remain references to the old objects.

Create file **ListCloneDemo.java**:

~~~java
import java.util.ArrayList;

public class ListCloneDemo {
    public static void main(String[] args) {
        ArrayList<StringBuilder> first = new ArrayList<>();
        first.add(new StringBuilder("A"));

        @SuppressWarnings("unchecked")
        ArrayList<StringBuilder> second =
            (ArrayList<StringBuilder>) first.clone();

        System.out.println("same list: " + (first == second));
        System.out.println("same element: " +
            (first.get(0) == second.get(0)));

        second.get(0).append("!");
        System.out.println("first value: " + first.get(0));
        System.out.println("second value: " + second.get(0));
    }
}
~~~

Run:

~~~bash
javac ListCloneDemo.java
java ListCloneDemo
~~~

Output:

~~~text
same list: false
same element: true
first value: A!
second value: A!
~~~

**new ArrayList<>(first)** also copies the structure without cloning each element. **List.copyOf(first)** creates a structurally unmodifiable list, yet mutable element objects remain shared. "Unmodifiable collection" is different from "completely immutable object graph".

## 9. Inheritance makes the clone contract more complex

A superclass can override clone and ensure its own fields are properly copied. However, when a subclass adds a mutable array or List, the copy created by inherited clone may still have the right **runtime type** while sharing the new field with the original.

If a subclass overrides clone:

- It must respect the copying mechanism designed by the superclass.
- It needs to handle new mutable fields if the contract requires independence.
- If clone calls **super.clone()**, one must distinguish between a superclass calling Object.clone and a superclass that already performs extra steps to clone its own fields.
- **Final fields** pointing to mutable objects make the "super.clone then reassign field" approach difficult to apply; a constructor/factory creating a new instance may be a more suitable design.
- With an open inheritance hierarchy, future subclasses may invalidate a previous copying contract.

Therefore, overriding **clone()** should be accompanied by **clear documentation on depth, runtime type, resource sharing, and subclass responsibilities**. If the inheritance hierarchy cannot be controlled, a dedicated copy API or an immutable final class is usually easier to verify.

## 10. Copy constructors and immutable types are other options

For new code, a **copy constructor** or **static copy factory** can express the exact components that must be copied, while allowing final fields to be set and normal validation to run.

Create file **CopyConstructorDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CopyConstructorDemo {
    static final class Snapshot {
        private final String id;
        private final List<String> tags;

        Snapshot(String id, List<String> tags) {
            this.id = Objects.requireNonNull(id);
            this.tags = List.copyOf(Objects.requireNonNull(tags));
        }

        Snapshot(Snapshot source) {
            this(source.id, source.tags);
        }

        List<String> tags() {
            return tags;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("READY"));
        Snapshot original = new Snapshot("S-1", input);
        Snapshot copy = new Snapshot(original);

        input.add("DONE");

        System.out.println("different object: " + (original != copy));
        System.out.println("original: " + original.tags());
        System.out.println("copy: " + copy.tags());

        try {
            copy.tags().add("LATER");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy list cannot be modified");
        }
    }
}
~~~

Run:

~~~bash
javac CopyConstructorDemo.java
java CopyConstructorDemo
~~~

Output:

~~~text
different object: true
original: [READY]
copy: [READY]
copy list cannot be modified
~~~

Here **List.copyOf** creates a structurally unmodifiable representation and the String elements are immutable. With **List<MutableItem>**, a List that disallows add/remove **can still observe changes inside MutableItem**. To achieve deep immutability, a separate design is required for the element type.

**Records** also generally do not need Cloneable. For a record containing immutable values like int, String, or Instant, a new value can be constructed using the canonical constructor:

~~~java
record Point(int x, int y) {}

Point p = new Point(1, 2);
Point q = new Point(p.x(), p.y());
~~~

This is an illustrative snippet, not a standalone program file. The two Points have equal values; for a record with arrays or mutable objects, the constructor/accessor/equals/hashCode must be designed consistently to preserve the value contract when copying.

## 11. Relationship among clone, equals, and hashCode

**clone()** handles how an object is created; **equals()** handles when two objects are equivalent; **hashCode()** must be consistent with equals. Do not infer one contract from another.

If a class uses **Object.equals** by identity, a newly cloned object copy may **not equal** the original object. If a class defines equals across all value fields and clone preserves those fields, the clone usually equals the original. When equals returns true, hashCode must be equal.

Do not use hashCode as a **unique ID** of an object or of a copy. HashCode is an int and can collide. If clone creates a new ID according to business logic, both equals and hashCode may change; that behavior must be part of the class contract rather than occurring implicitly.

For mutable objects used as HashMap/HashSet keys, modifying fields participating in equals/hashCode after insertion can cause lookup failures. Having an independent clone does not change the rule: **keys currently inside a hash structure must remain stable**.

## 12. Complex cloning of object graphs and resources

An object may reference multiple child objects sharing a single node; the graph may contain cycles. If true deep copying of the graph is required:

1. Need to determine which nodes are copied and which nodes are shared.
2. Need to preserve intentional aliasing relationships: if two fields point to the same node in the original graph, should they point to the same cloned node in the new graph?
3. For cycles A -> B -> A, already-copied nodes must be tracked to avoid infinite recursion.
4. Should maintain an original object -> cloned object mapping during graph traversal when structure preservation is needed.
5. Must have a separate policy for resources with identity and lifecycle: stream, lock, socket, thread, transaction, native handle, or listener.

These requirements cannot be solved simply by arbitrarily calling **clone()** recursively. Usually a copying algorithm tailored to the data model or a dedicated snapshot type is needed.

## 13. Common mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Thinking **implements Cloneable** auto-generates public clone | Caller has no public clone API | Override public clone or use a copy API |
| Only calling **super.clone()** with mutable fields | Two instances share child objects | Additionally copy fields that need independence |
| Cloning the outer array of a matrix | Rows remain shared | Copy each necessary level |
| Cloning ArrayList and thinking elements are also cloned | Changes to element objects appear in both lists | Copy elements according to the contract |
| Forgetting checked **CloneNotSupportedException** | Compilation error or awkward API | Catch exception or declare throws |
| Relying on the constructor in a cloned object | Invariants or resources are not re-established | Verify invariants and consider a copy constructor |
| Adding mutable fields in a subclass without updating clone | Copy shares the new state | Design and test each inheritance level |
| Using final with a field reassignment strategy after super.clone | Cannot reassign final fields normally | Constructor/factory creating a new copy |
| Claiming "deep immutable" after **List.copyOf** | Mutable leaf objects can still change | Copy/freeze element objects |
| Believing **clone.equals(original)** is always mandatory | Tests fail even when clone matches class contract | Check the class's equals criteria first |

## 14. Copying contract testing checklist

When a class allows cloning, the following tests should be present:

1. **Identity:** is the clone a new object as promised? If so, **original != copy**.
2. **Type:** does the copy have the right runtime class, especially with subclasses?
3. **Initial state:** meaningful data is preserved, except fields documented to be reset.
4. **Equals/hashCode:** if clone equals original then hashCode must match; do not automatically require equals true for all clone types.
5. **Modifying clone:** change each mutable field of the clone and observe the original.
6. **Modifying original:** verify whether the clone is affected on references that should be independent.
7. **Deep copying:** test nested arrays, Lists of mutable objects, shared nodes, null objects, and empty data.
8. **Constructor/invariant:** is the cloned object still valid, or is it missing locks/caches/resources created by the constructor?
9. **Inheritance:** do subclasses adding fields change the copying outcome?
10. **HashMap/HashSet:** do not modify fields participating in equals/hashCode of stored keys.
11. **Resource lifecycle:** do not accidentally duplicate or share resources allowed only single ownership.
12. **Business depth:** documentation and tests must jointly specify clearly what is shared and what is independent.

## 15. Choosing the right solution

| Situation | Usually reasonable choice |
| --- | --- |
| All state is primitive/immutable | Shallow copy may suffice; immutable values can even be shared |
| Has a mutable primitive array | Copy object + clone array; guard constructor/getter when needed |
| Multi-dimensional array | Copy each sub-array as needed |
| Collection with immutable elements | Copy collection or unmodifiable structure |
| Collection with mutable elements | Copy collection and each element per contract |
| Open inheritance tree, many subclasses | Establish copying mechanism at all levels or consider factory |
| Class with resources or complex constructor invariants | Dedicated copy API, copy constructor, or no copy support |
| Value type record/final immutable | Constructor, factory, or direct value usage |

**Remember:** **Object.clone()** gives a **shallow** copy when a class truly supports Cloneable, while the meaning of a usable copy in the application **is defined by the class itself**. When an object contains mutable state, inheritance, or lifecycle-bound resources, determine the copy depth and test independence. If that contract is hard to guarantee, a copy constructor, factory, or immutable model is usually easier to understand and safer.

References: [Object.clone in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()) and [Cloneable in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).
