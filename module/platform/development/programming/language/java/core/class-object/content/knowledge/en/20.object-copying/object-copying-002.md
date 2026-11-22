# Shallow Copying and Sharing Component Objects in Java

## Learning Objectives

After this lesson, you will be able to:

- Explain what a **shallow copy** is: creating a new outer object/collection/array whose reference fields/reference elements may still point to **the exact same original component objects**.
- Distinguish among three cases: **reference assignment**, **shallow copy**, and **deep copy as needed**, identifying which objects are new and which objects are shared.
- Predict the effects of modifying the outer object, replacing the reference of a field/element, and mutating the state of a shared object.
- Understand the semantics of `Object.clone()`, the `Cloneable` interface, `super.clone()`, and why the default clone is essentially a field-by-field shallow copy; grasp the limitations of `clone()`.
- Use copy constructors, static factories, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(...)`, `List.copyOf`, and `Map.copyOf` without confusing a “new container” with “every element is also new”.
- Distinguish primitive elements from reference elements, single-level copies from nested arrays, and live unmodifiable views from snapshots.
- Recognize that immutable components such as `String` and immutable value records can usually **be shared safely**, without requiring unnecessary deep copying.
- Design defensive copies when accepting or returning mutable components, control ownership, and avoid breaking invariants or leaking state through aliases.
- Analyze the impact of shared mutable elements on `equals`/`hashCode`, hash collections, multi-threaded access, and resource lifecycles.
- Write standalone Java 17+ examples, compile and run them, read exact stdout, and test both identity and value equality.

## 1. Why Do We Need to Understand References Before Talking About “Copy”?

Java variables of reference types hold a **reference value** to an object and do not themselves contain a full copy of the object. When you write:

~~~java
Customer a = new Customer();
Customer b = a;
~~~

we do **not** create two Customer objects. `a` and `b` both reference the object created by that single `new`. Any method that mutates that object can be observed through both variables.

Diagram:

~~~text
a --------+
          |
          v
    [Customer object]
          ^
          |
b --------+
~~~

Conversely, if you create a new Customer object while passing the **same Address reference** into the constructor, the two Customer objects are distinct, **but the Address object is still shared**.

~~~text
a --> [Customer A] ----address----+
                                 |
                                 v
                              [Address]
                                 ^
                                 |
b --> [Customer B] ----address----+
~~~

This is the premise of shallow copying: **a new outer shell, while the referenced components inside may still be the original objects**.

### 1.1. Reference Assignment Is Not Shallow Copying

Three lines to distinguish:

~~~java
Person b = a;                  // Same Person object, no copy.
Person c = new Person(a);      // May be a shallow or deep copy depending on the constructor.
Person d = a.copy();           // Depends on the implementation of copy().
~~~

There is no naming rule for `copy` or constructor overloads that automatically produces a deep copy. **You must read the implementation and the contract documentation**.

### 1.2. What Is a Shallow Copy?

Given the class:

~~~java
class Employee {
    String name;
    Address address;
}
~~~

A shallow copy typically copies the values of the fields:

- `name`: the String reference is copied, but because String is immutable, sharing it can be safe.
- `address`: the Address reference is copied; if Address is mutable, both Employee objects see the same Address object.
- Primitive fields such as `int age`: the numeric value is copied, so changing `age` on the copy does not change `age` on the original.

It is not the case that **all referenced objects are newly copied** simply because the outer class creates a new instance.

## 2. First Program: Different Outer Shell, Same Inner Address

Save **`ShallowReferenceDemo.java`**:

~~~java
public class ShallowReferenceDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = city;
        }

        String city() {
            return city;
        }

        void move(String nextCity) {
            city = nextCity;
        }
    }

    static final class Employee {
        String name;
        Address address;
        int score;

        Employee(String name, Address address, int score) {
            this.name = name;
            this.address = address;
            this.score = score;
        }

        Employee shallowCopy() {
            return new Employee(name, address, score);
        }
    }

    public static void main(String[] args) {
        Employee original = new Employee(
                "Lan", new Address("Ha Noi"), 10);
        Employee copy = original.shallowCopy();

        System.out.println("same outer=" + (original == copy));
        System.out.println("same address=" +
                (original.address == copy.address));

        copy.name = "Minh";
        copy.score = 20;
        System.out.println("original data=" +
                original.name + "," + original.score);
        System.out.println("copy data=" +
                copy.name + "," + copy.score);

        copy.address.move("Hue");
        System.out.println("original city=" +
                original.address.city());
        System.out.println("copy city=" + copy.address.city());
    }
}
~~~

Run:

~~~bash
javac ShallowReferenceDemo.java
java ShallowReferenceDemo
~~~

Exact stdout:

~~~text
same outer=false
same address=true
original data=Lan,10
copy data=Minh,20
original city=Hue
copy city=Hue
~~~

**Analysis of each result:**

1. `original != copy`: `shallowCopy()` calls `new Employee(...)`, so there are two outer objects.
2. `original.address == copy.address`: the constructor receives and stores **the same Address reference value**.
3. `copy.name = "Minh"` replaces the **reference field name in copy**, without mutating original.name. String's immutability further keeps the result stable.
4. `copy.score = 20` changes the **primitive field in copy**, so original.score stays 10.
5. `copy.address.move("Hue")` mutates the shared Address object, so both Employees see Hue.

**Rule of thumb:** in a shallow copy, **reassigning a reference field in the copy** is different from **mutating the object that the reference field points to**.

## 3. Comparing the Three Models with Diagrams

### 3.1. No Copy: Alias Assignment

~~~text
original -------------------+
                            v
                         [Person]
                            ^
alias ----------------------+

original == alias           true
original.address == alias.address  true if same field on the same object
~~~

### 3.2. Shallow Copy: Different Outer, Shared Child

~~~text
original --> [Person 1] ---+
                          |
                          v
                        [Address]
                          ^
                          |
copy -----> [Person 2] ---+

original == copy           false
original.address == copy.address  true
~~~

### 3.3. Intentional Single-Level Component Deep Copy

~~~text
original --> [Person 1] --> [Address 1]
copy -----> [Person 2] --> [Address 2]

original == copy                  false
original.address == copy.address  false
~~~

This is “deep enough” for the Person→Address model **if Address does not hold other mutable nested references**. If Address also contains a mutable `List<Coordinate>` and the copy constructor only copies the list reference, separating Address does not yet guarantee that the entire graph is independent.

### 3.4. Change Prediction Table

| Operation | Alias only `b = a` | Outer shallow copy | Copy separating relevant components |
| --- | --- | --- | --- |
| `b.age = 20` on a primitive field | Same outer object → a.age changes | a.age does not change | a.age does not change |
| `b.address = new Address(...)` | a.address changes due to same outer | a.address keeps the old field reference | a.address keeps the old field reference |
| `b.address.setCity(...)` | a sees the change | a **may** see the change if sharing the same Address | a does not see the change if Address is separate |
| Modifying a nested mutable list item | Possibly same object graph | Can still see the change | Depends on the copy level of the nested item |
| Object creation cost | Creates no additional objects | Creates at least the outer object | May create outer + mutable child copies |

“Deep copy” **has no default depth**: you must decide which components are allowed to be shared and which components require independent ownership.

## 4. A Copy Constructor Can Be Written to Perform a Shallow Copy

Java **does not automatically provide a copy constructor** as a default object-copying operation. A programmer-declared constructor can copy fields one by one:

~~~java
class Invoice {
    private String number;
    private Customer customer;

    Invoice(Invoice source) {
        this.number = source.number;
        this.customer = source.customer;
    }
}
~~~

This is an **illustrative code snippet** in a context where a valid `Customer` class exists. `new Invoice(original)` creates a new Invoice object, but the `customer` field still points to the **same Customer** as original; therefore, this is a *shallow copy*. If Customer is mutable, modifying Customer through one Invoice can cause both to change in an observable way. The earlier Person–Address experiment already verified this through identity and mutation.

**A copy constructor does not promise a deep copy simply by its name**. It can be designed to validate, copy selectively, recompute derived values, or report an error; what matters is the **contract** it provides. When the goal is simply to understand shallow-copy state sharing, there is no need to repeat another multi-branch copy-constructor program and a deep-copy test here.

## 5. `Object.clone()` Is Another Path That Can Produce a Shallow Copy

`Object.clone()` is a `protected` method. By convention, an ordinary class that wants to use `super.clone()` needs `implements Cloneable`; `Cloneable` is a **marker interface** and does not itself declare a public `clone()`. With `Object.clone()`'s implementation, the new object is created via a field-wise copy mechanism and **reference fields still share the nested objects**.

Distinction:

| Copy path | New top-level object? | Are mutable children separated? |
| --- | --- | --- |
| `b = a` | No | No |
| `new Invoice(a)` with the constructor above | Yes | No |
| `super.clone()` on a Cloneable object under the default contract | Yes | No |
| Specialized factory/copy constructor | Depends on contract | Depends on contract |

`clone()` **does not invoke a constructor through the normal `new` object-creation path**, so invariants, `final` reference fields, resources, and inheritance may require special handling. In addition, a subclass can override `clone()` with a different policy; do not assume every method named `clone` is shallow. When you need the conditions and detailed comparisons for `Object.clone()`, examine its dedicated contract. The key point here is: **the root object may be new while mutable children are still shared**.

## 6. Caution When Cloning an Object with a final Reference Field

Suppose:

~~~java
class Folder {
    private final java.util.List<String> entries;

    Folder(java.util.List<String> entries) {
        this.entries = new java.util.ArrayList<>(entries);
    }
}
~~~

If you implement `clone()` yourself using `super.clone()`, the cloned Folder has its `entries` field referencing the same mutable list. Because the field is `final`, it normally cannot be reassigned to a mutable list copy in ordinary Java code inside the clone method.

This is one reason to prefer a **copy constructor or static factory** instead of forcing a class with a final mutable-reference field through `Object.clone`. Do not use reflection to bypass a final field in order to patch up a cloning design.

If the list contains only `String` elements and is stored as a truly unmodifiable snapshot, sharing that structure may already be safe; base the decision on ownership and mutability, not on a “clone everything” habit.

## 7. Arrays: `clone()` Creates a New Array, but Elements Can Be Shared

Every Java array supports `clone()`, returning a new array object with the same length and corresponding component type. From the perspective of the elements:

- Primitive array: each primitive value is copied.
- Reference array: each **reference value** is copied; element objects are not automatically cloned.
- Nested arrays: the outer array is cloned, while the subarrays remain the original objects unless copied separately.

### 7.1. Primitive Array

~~~java
int[] original = {1, 2, 3};
int[] copy = original.clone();

copy[0] = 9;
// original[0] is still 1.
~~~

Because the array component type is `int`, copying the elements already separates the values. For primitive-only arrays, a single level of cloning is usually enough to prevent a mutation in one array from affecting the other.

### 7.2. Reference Array

~~~java
Customer[] original = {someCustomer};
Customer[] copy = original.clone();

boolean sameArray = original == copy;           // false.
boolean sameItem = original[0] == copy[0];      // true.
~~~

Here `Customer` and `someCustomer` are illustrative placeholders that need to be declared. Assigning `copy[0] = new Customer(...)` replaces the element reference in copy without changing `original[0]`. However, calling `copy[0].setName(...)` before replacing the element will mutate the Customer object that original still points to.

## 8. Demo of Primitive Arrays and Reference Elements

Save **`ArrayShallowCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayShallowCopyDemo {
    static final class Cell {
        int value;

        Cell(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;

        System.out.println("int same array=" +
                (numbers == numberCopy));
        System.out.println("original int=" + numbers[0]);
        System.out.println("copied int=" + numberCopy[0]);

        Cell[] cells = {new Cell(5), new Cell(6)};
        Cell[] cellCopy = cells.clone();

        System.out.println("cell same array=" +
                (cells == cellCopy));
        System.out.println("cell same first object=" +
                (cells[0] == cellCopy[0]));

        cellCopy[0].value = 50;
        cellCopy[1] = new Cell(60);

        System.out.println("original contents=" +
                cells[0].value + "," + cells[1].value);
        System.out.println("copy contents=" +
                cellCopy[0].value + "," + cellCopy[1].value);
        System.out.println("primitive copy=" +
                Arrays.toString(numberCopy));
    }
}
~~~

Run:

~~~bash
javac ArrayShallowCopyDemo.java
java ArrayShallowCopyDemo
~~~

Output:

~~~text
int same array=false
original int=1
copied int=9
cell same array=false
cell same first object=true
original contents=50,6
copy contents=50,60
primitive copy=[9, 2]
~~~

**Two different mutations:**

- `cellCopy[0].value = 50` modifies the **shared** Cell object, so original sees 50.
- `cellCopy[1] = new Cell(60)` replaces the reference **in the copy array**; original keeps its reference to the old Cell(6).

You should not infer “because the array was cloned, each object inside the array was also cloned”.

### 8.1. What About `Arrays.copyOf`?

`Arrays.copyOf(source, source.length)` also creates a new array and copies the elements. For a reference array, the element references remain shared. It also allows choosing a different length; any extended portion is filled with the appropriate default values. It does not automatically create copies of each referenced object.

## 9. Two-Dimensional Arrays: Copying the Outer Rows Still Retains the Subarrays

Given:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};
int[][] shallow = matrix.clone();
~~~

`matrix != shallow`, but `matrix[0] == shallow[0]` because the **first-row int[]** is shared. `shallow[0][0] = 99` causes `matrix[0][0]` to change.

To separate the rows:

~~~java
int[][] separate = matrix.clone();
for (int i = 0; i < separate.length; i++) {
    separate[i] = matrix[i].clone();
}
~~~

This is a two-level copy for an int[][] graph that contains no self-references. For mutable object elements, deeper consideration is still needed.

### 9.1. Runnable Program

Save **`MatrixCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyRows(int[][] source) {
        int[][] result = source.clone();
        for (int i = 0; i < result.length; i++) {
            result[i] = source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3, 4}};
        int[][] shallow = first.clone();
        int[][] separate = copyRows(first);

        System.out.println("outer shared=" + (first == shallow));
        System.out.println("row shared=" +
                (first[0] == shallow[0]));
        System.out.println("deep row shared=" +
                (first[0] == separate[0]));

        shallow[0][0] = 9;

        System.out.println("original row=" +
                Arrays.toString(first[0]));
        System.out.println("shallow row=" +
                Arrays.toString(shallow[0]));
        System.out.println("separate row=" +
                Arrays.toString(separate[0]));
    }
}
~~~

Run:

~~~bash
javac MatrixCopyDemo.java
java MatrixCopyDemo
~~~

Output:

~~~text
outer shared=false
row shared=true
deep row shared=false
original row=[9, 2]
shallow row=[9, 2]
separate row=[1, 2]
~~~

With `int[][]`, each subarray holds primitive numbers, so cloning each subarray is enough for content independence. If a row is null, `source[i].clone()` will cause an NPE; the method here assumes every row is non-null and needs additional validation if used as a general-purpose API.

## 10. Collection Copy: `new ArrayList<>(source)`

When you write:

~~~java
List<Employee> copy = new ArrayList<>(original);
~~~

`copy` is a **new List object** whose element references are copied according to the iteration/order of source. It **does not call `new Employee` for each element**.

Consequences:

- `copy.add(newEmployee)` changes the structure of copy, and does not itself change original.
- `copy.remove(0)` removes the reference from copy, while the original list still keeps its old reference.
- `copy.get(0).setName(...)` mutates the **shared** Employee object, so both lists can see the new name.

### 10.1. Runnable Program

Save **`ListShallowCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListShallowCopyDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        void rename(String next) {
            name = next;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Item> original = new ArrayList<>();
        original.add(new Item("A"));

        List<Item> copy = new ArrayList<>(original);

        System.out.println("same list=" + (original == copy));
        System.out.println("same item=" +
                (original.get(0) == copy.get(0)));

        copy.get(0).rename("X");
        copy.add(new Item("B"));

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);

        copy.set(0, new Item("Y"));
        System.out.println("after replace original=" + original);
        System.out.println("after replace copy=" + copy);
    }
}
~~~

Run:

~~~bash
javac ListShallowCopyDemo.java
java ListShallowCopyDemo
~~~

Output:

~~~text
same list=false
same item=true
original=[X]
copy=[X, B]
after replace original=[X]
after replace copy=[Y, B]
~~~

**Explanation:**

- Both lists initially hold Item A.
- `rename("X")` modifies the shared Item → both lists print X.
- `copy.add(B)` only makes the copy list longer.
- `copy.set(0,new Item("Y"))` replaces the reference at index 0 in copy; original still keeps Item X.

This is an example you need to understand before using collection-copying APIs.

## 11. `List.copyOf`: Structural Snapshot Without Cloning Element Objects

`List.copyOf(source)` returns an **unmodifiable List** reflecting the contents/structure at creation time (in the typical case of a mutable source), but references to mutable elements can still be shared.

Two levels must be separated:

1. **Collection structure:** add/remove/set operations are not allowed through the unmodifiable list.
2. **Element object state:** if an element is mutable and another alias can modify it, reading through the snapshot can see the new value.

### 11.1. Demo of Snapshot and Component Alias

Save **`ListSnapshotSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListSnapshotSharingDemo {
    static final class Entry {
        String value;

        Entry(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static void main(String[] args) {
        Entry shared = new Entry("old");
        List<Entry> source = new ArrayList<>();
        source.add(shared);

        List<Entry> snapshot = List.copyOf(source);

        source.add(new Entry("second"));
        System.out.println("source size=" + source.size());
        System.out.println("snapshot size=" + snapshot.size());

        shared.value = "new";
        System.out.println("snapshot first=" + snapshot.get(0));

        try {
            snapshot.add(new Entry("third"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac ListSnapshotSharingDemo.java
java ListSnapshotSharingDemo
~~~

Output:

~~~text
source size=2
snapshot size=1
snapshot first=new
snapshot cannot add
~~~

The snapshot does not receive the second entry added afterward, but the shared component changes from old to new.

**Do not claim that `List.copyOf` creates a deep immutable object graph** when the elements have setters or expose mutable nested references.

### 11.2. Nulls and Instance Reuse

`List.copyOf` does not allow null elements according to its API. If the input is already an eligible unmodifiable list, the implementation **may reuse the list instance** rather than necessarily allocating a new outer list. Therefore, do not use `List.copyOf(source) != source` as a universal Java assertion.

If the requirement mandates a **new list object identity**, choose a construction API with an appropriate contract and still check element semantics. Typically, business requirements call for a **snapshot/unmodifiable** list rather than a different identity at all costs.

## 12. `Collections.unmodifiableList` Can Be Just a View

Unlike copying into a new list, `Collections.unmodifiableList(source)` creates an **unmodifiable view** of the backing list:

- Callers cannot modify the structure through the view.
- If other code still holds the mutable `source` and modifies it, the view reflects the changes.
- Element references are still shared.
- A view is not a “deep copy” or a “frozen snapshot”.

### 12.1. Program Contrasting a View and a List Copy

Save **`ViewVsCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> mutableCopy = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("mutable copy=" + mutableCopy);
        System.out.println("snapshot=" + snapshot);

        mutableCopy.add("C");
        System.out.println("copy after add=" + mutableCopy);

        try {
            view.add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("view cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac ViewVsCopyDemo.java
java ViewVsCopyDemo
~~~

Output:

~~~text
source=[A, B]
view=[A, B]
mutable copy=[A]
snapshot=[A]
copy after add=[A, C]
view cannot add
~~~

Here the elements are immutable `String` instances, so we only observe differences in the **structure of the lists**. With mutable element objects, the view, mutableCopy, and snapshot can all initially share the corresponding elements.

## 13. `Map.copyOf` and Map Copy Constructors Are Also Shallow Copies of Values

Similarly, `HashMap<>(sourceMap)` creates a new map containing the corresponding entry/key/value references. `Map.copyOf(sourceMap)` creates an unmodifiable map with the entries at copy time, but does not deep-copy mutable values.

Save **`MapShallowCopyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class MapShallowCopyDemo {
    static final class Setting {
        String text;

        Setting(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Setting value = new Setting("light");
        Map<String, Setting> original = new HashMap<>();
        original.put("theme", value);

        Map<String, Setting> copy = new HashMap<>(original);
        Map<String, Setting> snapshot = Map.copyOf(original);

        System.out.println("same map=" + (original == copy));
        System.out.println("same value=" +
                (original.get("theme") == copy.get("theme")));

        value.text = "dark";
        System.out.println("original theme=" +
                original.get("theme").text);
        System.out.println("copy theme=" +
                copy.get("theme").text);
        System.out.println("snapshot theme=" +
                snapshot.get("theme").text);

        copy.put("size", new Setting("large"));
        System.out.println("original entries=" + original.size());
        System.out.println("copy entries=" + copy.size());
    }
}
~~~

Run:

~~~bash
javac MapShallowCopyDemo.java
java MapShallowCopyDemo
~~~

Output:

~~~text
same map=false
same value=true
original theme=dark
copy theme=dark
snapshot theme=dark
original entries=1
copy entries=2
~~~

**Additional note on keys:** If a key is a mutable object and its `equals`/`hashCode` depends on mutable fields, both the original and shallow-copied maps can face lookup risks after mutation. `Map.copyOf` does not automatically turn mutable keys/values into immutable values.

With Map-copy APIs, you must consider the null policy: `Map.copyOf` does not accept null keys or values; you should not apply it in place of `new HashMap<>(source)` without checking the input contract.

## 14. When Is Sharing Elements Good?

Yes. With **immutable components**, copying references is safe with respect to mutation state.

For example, `record Coordinate(int x,int y)`, or `String`, `LocalDate`, `BigDecimal` with immutable value semantics. Two copied containers can share an immutable Coordinate object without worrying about Coordinate being modified in place.

### 14.1. Demo of Immutable Elements and Independent Containers

Save **`ImmutableComponentSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableComponentSharingDemo {
    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Coordinate point = new Coordinate(1, 2);
        List<Coordinate> original = new ArrayList<>();
        original.add(point);

        List<Coordinate> copy = new ArrayList<>(original);

        System.out.println("same list=" + (original == copy));
        System.out.println("same point=" +
                (original.get(0) == copy.get(0)));

        Coordinate moved = new Coordinate(9, 2);
        copy.set(0, moved);

        System.out.println("original point=" + original.get(0));
        System.out.println("copy point=" + copy.get(0));
        System.out.println("old point=" + point);
    }
}
~~~

Run:

~~~bash
javac ImmutableComponentSharingDemo.java
java ImmutableComponentSharingDemo
~~~

Output:

~~~text
same list=false
same point=true
original point=Coordinate[x=1, y=2]
copy point=Coordinate[x=9, y=2]
old point=Coordinate[x=1, y=2]
~~~

**Interpretation:**

- Initially, both lists hold the same immutable Coordinate instance.
- No operation exists to modify `x` on the record point itself.
- `copy.set(0,moved)` only changes the reference in the copy list; original still keeps the old point.
- This is a case where shallow copying is **sufficient and beneficial**: there is no need to deep-copy every Coordinate.

**Note:** if the record contains `int[]` or mutable List elements, inspect more deeply; the record keyword alone is not deep-immutable.

## 15. Defensive Copying at Both Input and Output Boundaries

Another issue: a class is not a copy itself, yet it wants to **protect its internal state** from external aliases. When a constructor accepts a mutable object and stores the reference directly, the client can mutate the internal state from the outside. When a getter returns a mutable field directly, the client again obtains an alias.

### 15.1. Anti-pattern

~~~java
class BadStore {
    private final int[] data;

    BadStore(int[] data) {
        this.data = data; // Accepts the input alias directly.
    }

    int[] getData() {
        return data; // Exposes the output alias.
    }
}
~~~

`final` does not protect array elements. Therefore, the caller can modify `input[0]` or `store.getData()[0]`.

### 15.2. Proper Defensive Copy Program for a Primitive Array

Save **`DefensiveArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class DefensiveArrayCopyDemo {
    static final class Values {
        private final int[] data;

        Values(int[] input) {
            data = input.clone();
        }

        int[] copyValues() {
            return data.clone();
        }

        int sum() {
            return Arrays.stream(data).sum();
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        Values values = new Values(input);

        input[0] = 99;
        int[] retrieved = values.copyValues();
        retrieved[1] = 88;

        System.out.println("input first=" + input[0]);
        System.out.println("retrieved second=" + retrieved[1]);
        System.out.println("stored sum=" + values.sum());
    }
}
~~~

Run:

~~~bash
javac DefensiveArrayCopyDemo.java
java DefensiveArrayCopyDemo
~~~

Output:

~~~text
input first=99
retrieved second=88
stored sum=6
~~~

Because `int[]` holds primitive values, cloning on input and output is sufficient to separate element modification rights in this example.

### 15.3. When Components Still Contain Mutable References

If a field is `List<MutableAddress>`, calling `List.copyOf` separates the list structure, but each MutableAddress can still be modified through an alias. For true independence:

1. Use an **immutable Address value type**, or
2. Copy the Address objects into a private representation and prevent getters from exposing mutable references, or
3. Clearly define that the API **allows shared ownership/mutation** (this is a different contract from an independent snapshot).

There is no single valid approach for every domain; what matters is that the client understands the semantics.

## 16. Deep Copy at the Appropriate Depth, Not Infinite Copying

For example, suppose a `Document` holds a list of paragraphs, and each paragraph holds an immutable String text. To take a snapshot independent of the mutable list:

- Create a new outer Document object.
- Create a new list structure/unmodifiable snapshot.
- Share the **immutable String values** inside.

There is no need to do `new String(existingString)` to go “deeper”. Those copies do not make String any safer against mutation.

If each paragraph is a MutableParagraph with a `setText` method, the copy needs to create new paragraph objects itself or convert them into immutable Paragraph values.

### 16.1. Demo of Copying a List of Mutable Elements into Immutable Snapshots

Save **`SelectiveDeepCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SelectiveDeepCopyDemo {
    static final class MutableLine {
        private String text;

        MutableLine(String text) {
            this.text = text;
        }

        void replace(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    record LineSnapshot(String text) {
    }

    static final class Report {
        private final List<LineSnapshot> lines;

        Report(List<MutableLine> source) {
            List<LineSnapshot> values = new ArrayList<>();
            for (MutableLine line : source) {
                values.add(new LineSnapshot(line.text()));
            }
            lines = List.copyOf(values);
        }

        List<LineSnapshot> lines() {
            return lines;
        }
    }

    public static void main(String[] args) {
        MutableLine first = new MutableLine("old");
        List<MutableLine> draft = new ArrayList<>();
        draft.add(first);

        Report report = new Report(draft);
        first.replace("new");
        draft.add(new MutableLine("extra"));

        System.out.println("draft first=" + first.text());
        System.out.println("draft size=" + draft.size());
        System.out.println("report first=" +
                report.lines().get(0).text());
        System.out.println("report size=" + report.lines().size());
    }
}
~~~

Run:

~~~bash
javac SelectiveDeepCopyDemo.java
java SelectiveDeepCopyDemo
~~~

Output:

~~~text
draft first=new
draft size=2
report first=old
report size=1
~~~

**Significance:** Report copies **the text values to preserve** from mutable inputs into immutable LineSnapshot records, and then creates an unmodifiable list. It does not try to clone every object in the system. This is how to deep-copy at the **right data boundary**.

If `MutableLine.text()` can change concurrently in another thread, the snapshot requires an appropriate consistency contract; copying alone does not automatically create an atomic snapshot of shared mutable state.

## 17. Shallow Copy in Records and Copy Factories

A record constructor simply receives and stores component values. A factory that constructs a new record using the old record's accessors can create a different outer record while keeping the same mutable component reference.

### 17.1. Demo of Record Shallow Copy

Save **`RecordShallowCopyDemo.java`**:

~~~java
public class RecordShallowCopyDemo {
    record Picture(String title, int[] pixels) {
    }

    public static void main(String[] args) {
        Picture first = new Picture("A", new int[] {1, 2});
        Picture second = new Picture(
                first.title(), first.pixels());

        System.out.println("same record=" + (first == second));
        System.out.println("same pixels=" +
                (first.pixels() == second.pixels()));

        second.pixels()[0] = 9;

        System.out.println("first pixel=" + first.pixels()[0]);
        System.out.println("second pixel=" + second.pixels()[0]);
        System.out.println("records equal=" + first.equals(second));
    }
}
~~~

Run:

~~~bash
javac RecordShallowCopyDemo.java
java RecordShallowCopyDemo
~~~

Output:

~~~text
same record=false
same pixels=true
first pixel=9
second pixel=9
records equal=true
~~~

The two record instances have distinct identities, yet both store a reference to the same pixel array and the same String title. Generated record equality is based on component values; for an array component, equality checks **array identity**, so these two records are equal. Modifying the array through the reference in the second record also affects the first record's array. If you want independent pixels, the constructor/accessor needs to defensively copy; if you want equality based on pixel contents, implement equals/hashCode manually with Arrays.equals/Arrays.hashCode.

Do not confuse record component **reference equality** with record outer **identity equality**. The generated methods have value/component-oriented semantics; for array components they do not automatically compare contents, but with the same array reference the components are equal.

If you want Picture to have **independent pixel data**, the constructor must clone the input and the accessor must return a copy, and if you want equality by pixel contents, override `equals`/`hashCode` consistently.

## 18. A Shallow Copy Does Not “Lock” the Previous Owner's Modification Rights

A very important ownership principle:

> If a mutable object is still referenced in two places, both places can potentially affect each other through that object's mutating API.

For example, copying a shopping cart structure while keeping mutable Product objects. When a Product's price changes, both cart copies can compute totals using the new price even though their item lists are independent.

Sometimes that is **intentional**: both carts need to see the same live Product catalog entry. However, if the goal is “price quoted at order time”, you should snapshot the price into a separate immutable `OrderLine`, rather than keeping a reference to the mutable Product.price to recalculate old invoices.

### 18.1. Common Contracts

- **Live shared reference:** multiple views intentionally look at the same current state; every mutation is observed.
- **Shallow snapshot:** the set of references is captured at time T, but the referenced objects can change state.
- **Value snapshot:** the business values to preserve are also copied/frozen.
- **Deep clone of owned graph:** creates copies of owned mutable objects, keeping them separate and preserving alias/cycle invariants when needed.

If an API only says “copy” without explaining the kind of copy, users can very easily misunderstand it.

## 19. Shallow Copy and `equals`/`hashCode`

A shallow copy does not guarantee:

- `original.equals(copy)` is true. That depends on the class's **equality definition**.
- `original.hashCode() == copy.hashCode()` if the class uses Object.identity semantics; if they are considered equal according to `equals`, then the Java contract requires equal hashes.
- `original == copy` is true; a copy constructor/clone normally creates a new outer object.
- Hash codes are stable when mutable fields/children participate in equality/hashing.

### 19.1. Dangerous Mutable Shared Keys

If two shallow copies share the same mutable key object that was inserted into a `HashMap`, modifying a field that participates in the key's `hashCode()` through one alias can cause lookups to fail. Having two outer map/list copies **does not fix** this risk.

Solution: choose a stable immutable key/ID, or copy the key value into an immutable representation before storing it.

### 19.2. What If the Child Is Immutable?

If the field is an immutable `record Key(String id)` and both outer copies share the Key reference, equality and hashing will not change due to mutation. There is no need to clone Key to achieve the same semantics.

## 20. Shallow Copy with Cyclic Graphs and Multiple Aliases

In a complex object graph:

~~~text
A.child ----> C
B.child ----> C

C.parent? --> A
~~~

Shallow-copying A into A2 typically copies the `A.child` reference to **C itself**. If C has a `parent` field pointing to A, A2 and C do not automatically become a consistently “copied” bidirectional graph.

This matters for:

- Parent–child backlinks.
- Doubly linked lists.
- Graph nodes with `prev`/`next`.
- Mutable aggregate roots whose children hold pointers back to the owner.
- Shared entities participating in multiple aggregates.

A proper deep graph copy must decide:

1. Which nodes should be copied?
2. Should nodes shared in the original remain shared in the copy?
3. Should back references point to the new owner or the old one?
4. Are there cycles?
5. Must the invariant “two edges point to the same object” be preserved in the copied graph?

### 20.1. Example Proving Backlinks Do Not Update Automatically

Save **`GraphShallowCopyDemo.java`**:

~~~java
public class GraphShallowCopyDemo {
    static final class Parent {
        String name;
        Child child;

        Parent(String name) {
            this.name = name;
        }

        Parent(Parent source) {
            this.name = source.name;
            this.child = source.child;
        }
    }

    static final class Child {
        Parent parent;
        String label;

        Child(String label, Parent parent) {
            this.label = label;
            this.parent = parent;
        }
    }

    public static void main(String[] args) {
        Parent original = new Parent("A");
        Child child = new Child("child", original);
        original.child = child;

        Parent copy = new Parent(original);

        System.out.println("same parent=" + (original == copy));
        System.out.println("same child=" +
                (original.child == copy.child));
        System.out.println("child points original=" +
                (copy.child.parent == original));
        System.out.println("child points copy=" +
                (copy.child.parent == copy));
    }
}
~~~

Run:

~~~bash
javac GraphShallowCopyDemo.java
java GraphShallowCopyDemo
~~~

Output:

~~~text
same parent=false
same child=true
child points original=true
child points copy=false
~~~

This is **not a bug in Java cloning**, but an inevitable consequence of copying only outer reference fields. If the application requires backlinks to follow the new parent, you need to build a separate graph copy and update the links consistently.

### 20.2. Deep-Copying a Graph Is Not Just Calling clone() Recursively

A naive recursive clone can loop infinitely on cycles or create multiple distinct copies of an originally shared node. For a general-purpose graph, you usually need an **identity-based original→copy map**, putting each copy into the map before copying references, and then building edges to preserve sharing/cycles as required.

There is no need to implement a complex graph-cloning algorithm for this lesson, but you need to understand why “shallow copy” is simple while “deep copy” depends on the entire graph's semantics.

## 21. Shared Mutable Components Across Multiple Threads

A new outer copy **does not** automatically isolate concurrent access to a nested mutable child. If Thread A modifies `copy.child.count` and Thread B reads `original.child.count`, the two threads are still accessing the **same Child object**, which can cause a data race without proper synchronization.

### 21.1. An Outer Snapshot Does Not Mean the Component Is Thread-Safe

~~~java
class Holder {
    final MutableCounter counter;

    Holder(MutableCounter counter) {
        this.counter = counter;
    }

    Holder copy() {
        return new Holder(counter);
    }
}
~~~

This is an illustrative snippet that requires an appropriate `MutableCounter`. Both Holder objects keep one Counter reference. `final` fixes the reference itself; it does **not** make Counter thread-safe.

If the component must share live state, use an appropriate thread-safe type (for example, `AtomicInteger` for a simple counter), proper locks/ownership, and correct publication rules. If you need an **unchanging** snapshot, copy the **counter value** into an immutable primitive/record instead of keeping a live AtomicInteger reference.

### 21.2. Demo Distinguishing a Shared Counter and a Snapshot Value

Save **`SharedComponentCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedComponentCounterDemo {
    static final class View {
        final AtomicInteger counter;

        View(AtomicInteger counter) {
            this.counter = counter;
        }

        View shallowCopy() {
            return new View(counter);
        }
    }

    record Snapshot(int count) {
    }

    public static void main(String[] args) {
        AtomicInteger shared = new AtomicInteger(5);
        View first = new View(shared);
        View second = first.shallowCopy();

        Snapshot snapshot = new Snapshot(shared.get());

        System.out.println("same counter=" +
                (first.counter == second.counter));
        System.out.println("snapshot before=" + snapshot.count());

        second.counter.incrementAndGet();

        System.out.println("first count=" + first.counter.get());
        System.out.println("second count=" + second.counter.get());
        System.out.println("snapshot after=" + snapshot.count());
    }
}
~~~

Run:

~~~bash
javac SharedComponentCounterDemo.java
java SharedComponentCounterDemo
~~~

Output:

~~~text
same counter=true
snapshot before=5
first count=6
second count=6
snapshot after=5
~~~

`AtomicInteger` is a shared mutable object with atomic operations for a counter use case. It is **not immutable**, whereas `Snapshot` is an immutable record holding the primitive value at creation time.

**Note:** the thread safety of AtomicInteger does not turn every multi-field or multi-counter invariant into an atomic transaction. If business logic needs to update multiple resources together, separate coordination is required.

## 22. Copying Objects with Resources Outside the JVM Heap

Objects such as `Socket`, `InputStream`, database `Connection`, file handles, or executors are not value objects that can be deep-copied at will.

If a shallow copy of a wrapper keeps the same reference to an `AutoCloseable` resource:

- Both wrappers may be using the **same resource**.
- One wrapper calling `close()` on the resource makes the remaining wrapper unable to use it as before.
- If both think they are the owner, they may close it twice or manage its lifecycle incorrectly.
- Cloning a connection does not mean automatically creating an independent network/database connection.

### 22.1. Demo of Shared Closeable Ownership

Save **`SharedResourceCopyDemo.java`**:

~~~java
public class SharedResourceCopyDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        String read() {
            return closed ? "closed" : "open";
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static final class Reader {
        private final Resource resource;

        Reader(Resource resource) {
            this.resource = resource;
        }

        Reader(Reader source) {
            this.resource = source.resource;
        }

        String status() {
            return resource.read();
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();
        Reader first = new Reader(resource);
        Reader second = new Reader(first);

        System.out.println("before first=" + first.status());
        System.out.println("before second=" + second.status());

        resource.close();

        System.out.println("after first=" + first.status());
        System.out.println("after second=" + second.status());
    }
}
~~~

Run:

~~~bash
javac SharedResourceCopyDemo.java
java SharedResourceCopyDemo
~~~

Output:

~~~text
before first=open
before second=open
after first=closed
after second=closed
~~~

**This is a simulated resource**, not a real file. It clarifies sharing a closeable reference. In a real system, resource ownership must be clearly designed: who creates it, who is allowed to borrow it, who closes it, whether close is idempotent, and whether copying the wrapper is permitted.

## 23. Why Is Serialization Not a Default Deep Copy Mechanism?

Some code copies an object by serializing and then deserializing it, or by converting it to JSON and reading it back. This should not be treated as a default “deep clone for every object” mechanism:

- Not all types are serializable.
- Transient fields, custom serialization, class versions, and security policies affect the result.
- Objects such as active connections, threads, locks, or native handles do not have value-copy semantics.
- JSON can lose type identity, cycles, and shared references depending on the codec/configuration.
- Serialization carries I/O/CPU overhead and security risks with untrusted input.

If the goal is to copy a few fields and simple mutable components, a copy constructor/static factory is usually clearer.

If you need to deep-copy a complex object graph with cycles, you should choose a deterministic snapshot/mapping model and test ownership/identity rather than relying on the “accidental” behavior of a serializer.

## 24. Null References When Copying

A shallow copy typically preserves `null` values:

~~~java
class Example {
    Object item;

    Example(Example source) {
        item = source.item; // If null, the copy is also null.
    }
}
~~~

There is no component object to clone when the reference is null. Deep-copy code such as `new Item(source.item)` must handle null or declare a non-null precondition.

A copy constructor for an immutable class can simply copy the immutable reference and null according to its contract. You should not create a new object just to “avoid null” if doing so changes the semantics.

## 25. Inheritance and Copyability

When a base class defines `clone` or a copy constructor, a subclass may add its own state; copying that only knows about base fields can omit subclass fields or produce an unexpected result type.

Scenarios:

- A copy constructor `Base(Base source)` typically creates a **Base object**, and does not automatically create the runtime subtype if a Child is passed.
- `super.clone()` can preserve the runtime class of the cloned object, but the subclass must protect its own state/invariants and mutable nested fields.
- Final/non-final fields, constructor validation, and resources require special semantics.
- If polymorphic copying is desired, a **clear API contract** on result type and component sharing is required, rather than guessing from the name `clone`.

For classes with complex invariants, many Java guidelines recommend preferring a **factory/copy constructor** over the `Cloneable` interface because it is easier to control behavior and test.

### 25.1. Do Not Use `Cloneable` to Represent Domain Equality

“Being cloneable” only means the ability to create a similar object; it does not mean that `equals` must be true, or that the two objects must share children, or that the copy has the same business identity. All of those are separate design decisions.

## 26. What Should a Copy Operation Guarantee?

A good API should clearly document:

- **Outer identity:** is the result a new object, or can it return `this` when immutable?
- **Component ownership:** which objects are copied, and which objects are shared?
- **Mutability:** may the caller modify the result? Does modification affect the source?
- **Depth:** is it a single-level copy, a subtree, or a bounded domain snapshot?
- **Aliasing:** are shared element objects preserved with the same identity?
- **Null/invariants:** what is the behavior for optional fields and invalid inputs?
- **Resources:** how are owned vs borrowed handles managed?
- **Concurrency:** must the input remain unmutated during copying?
- **Performance:** what is the copy complexity and intended purpose (snapshot, cache, undo, mutation isolation)?
- **Equality:** is the result guaranteed to satisfy `equals(source)`, and what about mutable/time-varying fields?

Names like `shallowCopy()` or `snapshot()` can help communicate the contract, but documentation and tests are still necessary.

## 27. Testing Shallow-Copy Semantics

A useful test suite:

1. **Different outer object:** `original != copy` if the API guarantees a new outer object.
2. **Expected child identity:** `original.child == copy.child` if the API guarantees shallow sharing.
3. **Primitive fields copied:** changing a primitive field in the copy does not change the original.
4. **Independent reference reassignment:** setting `copy.child = another` does not change `original.child` when the outer objects differ and the field is mutable.
5. **Shared child mutation:** mutate the shared child, and both outer objects read the new value.
6. **Structure copied:** `new ArrayList<>(source)` allows add/remove without affecting source.
7. **Element references shared:** the identities of the initial mutable elements match.
8. **Null:** null fields remain null according to the contract.
9. **Immutable child sharing:** sharing a reference to an immutable value does not cause mutation.
10. **Deep-copy requirement:** if independence is required, test both the input alias and getter alias, including nested levels.
11. **Graph invariant:** do backlinks/cycles satisfy the requirements?
12. **Resources:** does closing one wrapper affect another wrapper, and is that permitted behavior?
13. **Concurrency:** if mutable components are shared, is proper coordination in place?
14. **Collections equality/hashing:** avoid mutating mutable keys whose hash depends on state.
15. **Performance:** object count/copy cost suits the workload at larger scale.

**There is no need** to rely on the garbage collector to test shallow copying. Verify object identity `==` and API-visible state deterministically.

### 27.1. Test Program with Assertions Always Executed

Save **`ShallowCopyContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyContractTest {
    static final class Item {
        String value;

        Item(String value) {
            this.value = value;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Item> source = new ArrayList<>();
        Item shared = new Item("A");
        source.add(shared);

        List<Item> copy = new ArrayList<>(source);

        check(source != copy, "outer list must differ");
        check(source.get(0) == copy.get(0), "shared element");
        check(source.size() == 1, "source size");

        copy.add(new Item("B"));
        check(source.size() == 1, "structure independent");
        check(copy.size() == 2, "copy size");

        shared.value = "X";
        check("X".equals(source.get(0).value), "source sees child");
        check("X".equals(copy.get(0).value), "copy sees child");

        copy.set(0, new Item("Y"));
        check("X".equals(source.get(0).value),
                "reassignment does not change source item");

        System.out.println("all shallow-copy checks passed");
    }
}
~~~

Run:

~~~bash
javac ShallowCopyContractTest.java
java ShallowCopyContractTest
~~~

Output:

~~~text
all shallow-copy checks passed
~~~

The `check` method is used instead of Java `assert` because Java assertions are disabled by default unless `-ea` is enabled. In this example, violating the contract raises an AssertionError even when running `java ShallowCopyContractTest` normally.

## 28. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`b = a` is a shallow copy.” | That is only reference assignment; it does not create a new outer object. |
| “`new Class(source)` is automatically a deep copy.” | What a copy constructor does depends on its body. |
| “`super.clone()` automatically clones all child objects.” | Default is a field-by-field shallow copy; reference fields remain shared. |
| “`Cloneable` has a public clone method.” | Cloneable is a marker interface; it does not declare clone(). |
| “Clone invokes the constructor just like new.” | By its semantics, Object.clone does not run a normal constructor like new. |
| “A `final` field prevents the child object from being mutated.” | Final locks the reference field; it does not deep-freeze the referent. |
| “Cloning int[] and Item[] both separate element objects the same way.” | int values are separated; Item references remain shared. |
| “Cloning int[][] makes every row separate.” | Cloning the outer array still shares the subarrays. |
| “`new ArrayList<>(source)` clones each element.” | It only copies references; mutable elements are shared. |
| “`List.copyOf` deep-copies elements.” | It creates an unmodifiable structural snapshot, without cloning element objects. |
| “An unmodifiable view is a snapshot.” | The backing collection can still change. |
| “`Map.copyOf` makes mutable values immutable.” | Value references can still be shared and mutated. |
| “Shallow copying is always wrong.” | It can be appropriate and efficient if children are immutable or sharing is intentional. |
| “If two lists have different identities, all their elements are also different.” | No; outer identity and element identity are two separate levels. |
| “Replacing a reference in the copy also changes the original.” | No if the outer objects differ; **mutating a shared element** is what affects both. |
| “A record is always deep-immutable.” | A record has final component references, but arrays/mutable elements are still shared. |
| “Copying a parent automatically updates the child.parent backlink.” | No; dedicated graph-copy logic is required. |
| “A thread-safe outer list makes a shared mutable child automatically thread-safe.” | No; coordination for the child is still needed. |
| “Cloning a resource wrapper creates an independent resource.” | No; the resource reference may be shared and closing one affects the other. |
| “Serialization is always a safe deep clone.” | There are many limitations regarding types, graphs, resources, security, and performance. |
| “A shallow copy guarantees equals is true.” | Equality depends on the class; outer identity is usually different. |
| “To deep-copy, you must copy String too.” | String is immutable; copying it is usually unnecessary for mutation safety. |
| “Cloning an object frees old memory.” | GC and object lifetime are not determined by shallow copying. |

## 29. Self-Check Questions with Answers

**Question 1.** How many new Node objects does `Node b = a;` create?  
**Answer:** It creates no new objects; b holds the same reference as a.

**Question 2.** How many outer Employees does a shallow copy of Employee with an Address reference create?  
**Answer:** Two outer Employee objects (if the copy implementation creates a new one), while Address may be just one shared object.

**Question 3.** What does `copy.address == original.address` being true indicate?  
**Answer:** Both fields hold the same reference to a single Address object.

**Question 4.** Does `copy.name = "B"` necessarily change `original.name`?  
**Answer:** No, if copy has a different outer object and only copy's field reference is assigned.

**Question 5.** Can `copy.address.setCity("Hue")` change the result read from original?  
**Answer:** Yes, if the Address object is shared and the method mutates that state.

**Question 6.** Why is a primitive `int count` in the copy independent?  
**Answer:** A shallow copy copies the primitive value; there is no shared primitive object reference.

**Question 7.** Does `new ArrayList<>(old)` create a new instance of each Item?  
**Answer:** No; it creates a new list and copies the element references.

**Question 8.** If `copy.set(0,new Item("Y"))` is called, does the original list element change accordingly?  
**Answer:** No, because the list structures are distinct; original keeps the old Item.

**Question 9.** If `copy.get(0).rename(...)` is called before `set`, can original see the change?  
**Answer:** Yes, if they share the same Item reference.

**Question 10.** Is `List.copyOf` synonymous with deep clone?  
**Answer:** No, it is only a structural snapshot/unmodifiable list; element references may be shared.

**Question 11.** Does `Collections.unmodifiableList(source)` snapshot the contents when source is mutated?  
**Answer:** Not necessarily; it is typically a live view.

**Question 12.** Does `int[] copy = original.clone()` followed by modifying copy[0] change original[0]?  
**Answer:** No, clone creates a new primitive array with copied values.

**Question 13.** Does cloning `Item[]` create new Item objects?  
**Answer:** No; the references of the elements are copied.

**Question 14.** Why does `int[][] shallow = matrix.clone()` not yet separate each row?  
**Answer:** The outer matrix array is new, but references to the subarrays remain shared.

**Question 15.** Does `Cloneable` declare a public `clone()` method?  
**Answer:** No. It is a marker interface.

**Question 16.** How does `super.clone()` copy the field `Address address`?  
**Answer:** It copies the Address reference value, without deep-cloning Address.

**Question 17.** Why is a copy constructor usually more flexible than clone?  
**Answer:** It can validate, select which fields/components to copy, and control constructor/invariants and clear semantics.

**Question 18.** Does creating a new record from an old record with the same `int[]` component create a new array?  
**Answer:** No, if the component reference is passed as-is.

**Question 19.** Can two distinct record instances with the same array reference be equal according to the generated record equals?  
**Answer:** Yes, if the other component values are also equal; array components use identity semantics.

**Question 20.** Why is it unnecessary to clone String elements when copying List<String>?  
**Answer:** String is immutable, so sharing references is safe with respect to mutation of the String itself.

**Question 21.** If List<MutableItem> is copied and then an Item is mutated, what is the risk?  
**Answer:** Both source and copy can observe the mutation through the shared Item reference.

**Question 22.** Is copying a list of Product references suitable for preserving historical invoice prices?  
**Answer:** No, if Product.price is mutable and the quoted price must stay fixed; snapshot the price into an immutable OrderLine instead.

**Question 23.** Why does the child.parent backlink not automatically point to the shallow-copied Parent?  
**Answer:** Because child is the exact original object, and child's parent field has not been mutated or copied.

**Question 24.** When a graph has cycles, what easily happens if clone is called recursively unconditionally?  
**Answer:** Infinite recursion/StackOverflowError or breaking identity-sharing invariants; an identity map is needed when deep-copying a graph.

**Question 25.** If two copies hold the same AtomicInteger, does `incrementAndGet` affect what both read?  
**Answer:** Yes. AtomicInteger is a shared mutable object, even though its operations have atomic semantics.

**Question 26.** Does an immutable record `Snapshot(int count)` change when the original AtomicInteger increments?  
**Answer:** No; snapshot holds the primitive value captured at construction time.

**Question 27.** Does copying a wrapper containing a socket create a new connected socket?  
**Answer:** No. If the reference is shared, both wrappers use the same original resource.

**Question 28.** Does replacing the `copy.child` reference when the outer objects differ modify the original.child field?  
**Answer:** No, unless business code has another side effect; each outer object has its own field.

**Question 29.** To obtain an immutable Report from MutableLine, what is the solution?  
**Answer:** Copy the values to preserve into immutable LineSnapshot elements and separate the list structure.

**Question 30.** What should shallow-copy testing best rely on?  
**Answer:** Outer/component identity using `==`, controlled structural changes/mutations, and API-visible state, without relying on GC.

## 30. Copy API Implementation Checklist

- [ ] Clearly specify whether the copy is only an alias, a shallow copy, or a value snapshot/deep copy up to a defined depth.
- [ ] Confirm whether the outer object is created anew and what the result type is.
- [ ] List primitive fields and reference fields; which references are shared?
- [ ] For arrays: is it a primitive array, a reference array, or a nested array?
- [ ] For collections: is it a structural copy or an immutable snapshot? Are the elements mutable?
- [ ] For maps: are mutable keys/values and the hash contract stable?
- [ ] Do constructors and getters expose a mutable representation?
- [ ] Does an inner object have a backlink to its owner? Must the copy update the links?
- [ ] Are there graph cycles or multiple shared nodes whose identity must be preserved?
- [ ] If a child is an immutable value, can its reference be kept as-is?
- [ ] Are there resource handles whose ownership should not be cloned/copied?
- [ ] Are there thread-safety or safe-publication requirements when components are shared?
- [ ] Are there tests comparing original vs copy for identity and post-copy mutation?
- [ ] Have allocation count and copy cost been considered for the workload?

## 31. References

- Java Platform API Java SE 17, [`Object.clone()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()): field-by-field copying, object identity, and the clone contract.
- Java Platform API, [`Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): marker interface related to cloning.
- Java Language Specification Java SE 17, [`10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7): array clone semantics.
- Java Language Specification, [`15.10 — Array Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10): arrays and components.
- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference values.
- Java Platform API, [`Arrays.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): copying arrays.
- Java Platform API, [`ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)): a new list structure with the collection's elements.
- Java Platform API, [`List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot semantics.
- Java Platform API, [`Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map snapshot.
- Java Platform API, [`Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view of a backing list.
- Java Platform API, [`HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): equality/hashing and keys.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record component values and generated equality.
- Java Platform API, [`AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic shared mutable counter.

## Conclusion

**Shallow copying** creates a new outer object/container while **copying reference values**, without automatically creating copies of every component object. Therefore, `original != copy` can be true while `original.child == copy.child` is also true. Mutating the shared child causes both to see the change; reassigning the child reference of a distinct outer object does not necessarily affect the other outer object.

APIs such as `super.clone()`, `array.clone()`, `Arrays.copyOf`, `new ArrayList<>(source)`, and simple copy constructors can all produce a shallow copy. `List.copyOf`/`Map.copyOf` keep an unmodifiable structural snapshot without deep-copying mutable element values; `Collections.unmodifiableList` can be just a view of the backing list.

Choose **reference sharing when the child is immutable or live sharing is intentional**. If the caller requires an independent snapshot, copy mutable components at the appropriate boundary, protect constructor/getter aliases, and consider backlinks/cycles, resources, and concurrency. Evaluate copying through **identity + mutation tests**, not just by looking at a method name like `clone`/`copy`. A clear contract regarding **“what is newly created and what remains shared”** is the key to designing object copying properly.
