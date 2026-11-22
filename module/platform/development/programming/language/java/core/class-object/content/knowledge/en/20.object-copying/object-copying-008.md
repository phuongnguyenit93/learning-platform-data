# Experiments on Modifying the Original, Copy, and Nested Components in Java

## 1. Learning Objectives and Questions to Prove

When creating a copy in Java, the important question is not only **“has a new object been created?”**, but also:

- If you **modify the original**, does the copy change as well?
- If you **modify the copy**, does the original change as well?
- If you modify **nested components** such as an array, a list, an address, or a mutable element, what happens in each instance?
- If both instances contain the same child object, is that safe sharing (immutable) or an aliasing bug (mutable)?
- Which check allows **concluding with evidence** instead of only looking at `==`, `equals()`, or identical initial contents?

This lesson uses **standalone compilable/runnable Java 17+ experiments**. Each example clearly distinguishes *input*, *copy operation*, *modification*, *observed values*, and *conclusion*. Non-standalone code is explicitly noted as an illustrative snippet.

> **Verification principle:** `original != copy` only proves that **the two outermost objects have different identities**. It **does not prove** that child objects such as `address`, `items`, `scores`, or `items.get(0)` are also independent.

## 2. Three Concepts to Distinguish Before Experimenting

| Concept | How It Is Done | What Is Guaranteed |
| --- | --- | --- |
| **Reference assignment / alias** | `B b = a;` | `a` and `b` point to the same object; no copy has been created yet |
| **Shallow copying (*shallow*)** | `super.clone()`, copying some reference fields, cloning the outer container | A new object or container, but it may keep references to the old mutable objects |
| **Contract-based deep copying (*deep copy*)** | Actively copying the mutable components that need to be separated | Mutation paths that the contract requires to be independent no longer cause the two instances to affect each other |

“Deep copy” does not necessarily mean recreating **every** immutable object:

- Sharing a `String` is safe for its content value, because String is immutable.
- Sharing `List.copyOf(...)` of Strings can be safe when the snapshot is not altered by a backing mutable source.
- Sharing a mutable `ArrayList` or `StringBuilder` can cause the original and the copy to affect each other.
- Two graphs with cycles or shared children need a separate **copy topology policy**, not just successive `clone()` calls.

For each data type, **the depth level must be defined by observable behavior**. Otherwise, the term “deep” is very easily overused.

## 3. Reading an Object Graph Diagram: Which Point Is Shared?

Suppose `Customer` holds a mutable `Address`:

```text
original Customer A
    name = "An"
    address ───────┐
                   ├──> Address X { city = "Hue" }
copy Customer B    │
    name = "An"     │
    address ───────┘
```

This is a **shallow copy** on the `address` field.

After:

```java
original.address.setCity("Da Nang");
```

the city seen by `copy.address` also changes, because **both point to Address X**.

The desired deep copy will create:

```text
original Customer A --address--> Address X { city = "Hue" }
copy Customer B     --address--> Address Y { city = "Hue" }

X != Y
```

At this point, mutating X does not mutate Y. The diagrams are models of **reference semantics**, not claims about physical stack/heap locations or JVM layout.

## 4. Experiment 1: The Assignment `b = a` Is Not Copying

Create the file **`ReferenceAliasExperiment.java`**:

```java
final class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class ReferenceAliasExperiment {
    public static void main(String[] args) {
        Counter original = new Counter(10);
        Counter alias = original;

        System.out.println(original == alias);

        alias.increment();
        System.out.println("original=" + original.value());

        original.increment();
        System.out.println("alias=" + alias.value());
    }
}
```

```bash
javac ReferenceAliasExperiment.java
java ReferenceAliasExperiment
```

**Standard output:**

```text
true
original=11
alias=12
```

**Conclusion:** No new object was created. `original` and `alias` point to the same Counter. All mutations are observed on the same state.

**To avoid misconceptions:** Java passes parameter values by value (*pass-by-value*), including reference values. Passing a reference to a method does not automatically clone the object; if the method mutates the object through the reference, the caller can still see the change.

## 5. Experiment 2: Two Independent Objects with Only a Primitive Field

Create **`PrimitiveFieldCopyExperiment.java`**:

```java
final class Score {
    private int value;

    Score(int value) {
        this.value = value;
    }

    Score(Score source) {
        this.value = source.value;
    }

    void set(int next) {
        value = next;
    }

    int get() {
        return value;
    }
}

public class PrimitiveFieldCopyExperiment {
    public static void main(String[] args) {
        Score original = new Score(10);
        Score copy = new Score(original);

        System.out.println(original == copy);
        System.out.println("start=" + original.get() + "," + copy.get());

        original.set(20);
        System.out.println("change original=" +
                original.get() + "," + copy.get());

        copy.set(30);
        System.out.println("change copy=" +
                original.get() + "," + copy.get());
    }
}
```

```bash
javac PrimitiveFieldCopyExperiment.java
java PrimitiveFieldCopyExperiment
```

```text
false
start=10,10
change original=20,10
change copy=20,30
```

Here, the copy constructor creates `new Score(...)` and assigns the `int` value. The two objects have their own separate instance state, so changing the primitive field in either instance only changes that instance.

**Do not overgeneralize:** For a reference field, the statement `this.child = source.child` **does not create a new child object**. Therefore, a copy constructor that works correctly for primitives can become a shallow copy if a mutable reference field is added without updating the copy logic.

## 6. Experiment 3: Replacing an Outermost Field Differs from Modifying a Child Object

We intentionally copy `Customer` **shallowly** on the `Address` field. To see the two layers of independence/sharing, Customer has its own mutable `name`; Address has a mutable `city`.

Create **`ShallowAddressExperiment.java`**:

```java
final class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    void moveTo(String nextCity) {
        city = nextCity;
    }

    String city() {
        return city;
    }
}

final class Customer {
    private String name;
    private final Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    Customer(Customer source) {
        this.name = source.name;
        this.address = source.address; // Shallow copy.
    }

    void rename(String nextName) {
        name = nextName;
    }

    void move(String nextCity) {
        address.moveTo(nextCity);
    }

    String describe() {
        return name + "@" + address.city();
    }
}

public class ShallowAddressExperiment {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = new Customer(original);

        System.out.println("same customer=" + (original == copy));
        System.out.println("start=" + original.describe() +
                " | " + copy.describe());

        original.rename("Binh");
        System.out.println("rename original=" + original.describe() +
                " | " + copy.describe());

        copy.move("Da Nang");
        System.out.println("move copy=" + original.describe() +
                " | " + copy.describe());
    }
}
```

```bash
javac ShallowAddressExperiment.java
java ShallowAddressExperiment
```

```text
same customer=false
start=An@Hue | An@Hue
rename original=Binh@Hue | An@Hue
move copy=Binh@Da Nang | An@Da Nang
```

### Result Analysis

- The two Customer objects have **different identities**.
- `name` is a reference field to a String. Reassigning `original.name` does not modify the String, but replaces the reference in the original Customer, so `copy.name` remains `"An"`.
- `address` in both Customers points to **the same Address object**.
- `copy.move(...)` mutates the shared Address, causing **both original and copy** to see `"Da Nang"`.

This is the **core lesson**: the same copy can be independent at **one level** and shared at a **deeper level**. Do not just test an outermost setter and conclude “this is already a deep copy”.

## 7. Experiment 4: Modifying Either the Original or Copy Does Not Propagate If Address Is Copied Properly

We modify the copy constructor to create a new Address using a **copy constructor dedicated to the component**. At the same time, the Customer constructor breaks the input alias to take ownership of its own Address.

Create **`DeepAddressExperiment.java`**:

```java
final class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address source) {
        this.city = source.city;
    }

    void moveTo(String nextCity) {
        city = nextCity;
    }

    String city() {
        return city;
    }
}

final class Customer {
    private final String name;
    private final Address address;

    Customer(String name, Address input) {
        this.name = name;
        this.address = new Address(input);
    }

    Customer(Customer source) {
        this.name = source.name;
        this.address = new Address(source.address);
    }

    void move(String city) {
        address.moveTo(city);
    }

    String describe() {
        return name + "@" + address.city();
    }
}

public class DeepAddressExperiment {
    public static void main(String[] args) {
        Address input = new Address("Hue");
        Customer original = new Customer("An", input);
        Customer copy = new Customer(original);

        input.moveTo("Can Tho");
        System.out.println("after input=" + original.describe() +
                " | " + copy.describe());

        original.move("Da Nang");
        System.out.println("after original=" + original.describe() +
                " | " + copy.describe());

        copy.move("Ha Noi");
        System.out.println("after copy=" + original.describe() +
                " | " + copy.describe());
    }
}
```

```bash
javac DeepAddressExperiment.java
java DeepAddressExperiment
```

```text
after input=An@Hue | An@Hue
after original=An@Da Nang | An@Hue
after copy=An@Da Nang | An@Ha Noi
```

**Three isolation tests:**

1. Mutate `input` after creating Customer: it does not change Customer's internal Address, because the constructor breaks the alias.
2. Mutate the original's Address: the copy does not change.
3. Mutate the copy's Address: the original does not change.

**Note:** Customer in the example is still a mutable class because it has `move`. “Deep copy” does not mean “immutable”: the two instances can both be **mutable yet independent**.

## 8. Trace Table to Classify Results Correctly

Given an object with a mutable root and mutable component:

| Operation | Complete alias | Shallow root copy | Deep-enough copy |
| --- | --- | --- | --- |
| `original == copy` | true | false | false |
| Modify primitive field of original | Copy sees the change (same root) | Copy usually does not change | Copy does not change |
| Modify primitive field of copy | Original sees the change | Original does not change | Original does not change |
| Modify mutable child via original | Copy sees the change | Copy sees the change if child is shared | Copy does not change |
| Modify mutable child via copy | Original sees the change | Original sees the change if child is shared | Original does not change |
| Mutate constructor input retained externally | Depends on input alias | Depends on constructor copy | Does not change if constructor snapshots properly |

The table describes common cases for the example. **“Deep-enough” must be tied to the actual state graph**: if there are shared mutable grandchildren, the row at that level needs additional checking.

To write tests, do not only verify `original != copy`. Try **every mutation direction**, at **every mutable level**, and observe **both instances**.

## 9. Experiment 5: One-Dimensional Primitive Arrays

An `int[]` array is a mutable object; however, its `int` elements are primitive values. Calling `clone()` on an array creates **a new array object** and copies the values.

Create **`OneDimensionalArrayExperiment.java`**:

```java
import java.util.Arrays;

public class OneDimensionalArrayExperiment {
    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        int[] alias = original;
        int[] copied = original.clone();

        System.out.println("alias=" + (original == alias));
        System.out.println("copy=" + (original == copied));

        original[0] = 9;
        System.out.println("after original=" +
                Arrays.toString(original) + " | " +
                Arrays.toString(copied));

        copied[1] = 8;
        System.out.println("after copy=" +
                Arrays.toString(original) + " | " +
                Arrays.toString(copied));
    }
}
```

```bash
javac OneDimensionalArrayExperiment.java
java OneDimensionalArrayExperiment
```

```text
alias=true
copy=false
after original=[9, 2, 3] | [1, 2, 3]
after copy=[9, 2, 3] | [1, 8, 3]
```

`int[]` has no mutable object elements inside, so structural cloning separates the entire state of the array in this experiment. `Arrays.copyOf(original, original.length)` can also create a new array with the corresponding values.

**Do not confuse:** By default, `Object.clone()` on a class holding an `int[]` field only copies the **reference field**, which differs from **calling `clone()` on the `int[]` array itself**.

## 10. Experiment 6: 2D Array with Shared Nested Elements

`int[][]` is an outer array containing **references to inner `int[]` arrays**. Cloning the outer array is only a shallow copy.

Create **`TwoDimensionalArrayExperiment.java`**:

```java
import java.util.Arrays;

public class TwoDimensionalArrayExperiment {
    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3}};
        int[][] copied = original.clone();

        System.out.println("outer shared=" + (original == copied));
        System.out.println("row shared=" + (original[0] == copied[0]));

        original[0][0] = 9;
        System.out.println("mutate original child=" +
                Arrays.deepToString(copied));

        copied[1][0] = 8;
        System.out.println("mutate copy child=" +
                Arrays.deepToString(original));

        original[0] = new int[] {7, 7};
        System.out.println("replace original row=" +
                Arrays.deepToString(original) + " | " +
                Arrays.deepToString(copied));
    }
}
```

```bash
javac TwoDimensionalArrayExperiment.java
java TwoDimensionalArrayExperiment
```

```text
outer shared=false
row shared=true
mutate original child=[[9, 2], [3]]
mutate copy child=[[9, 2], [8]]
replace original row=[[7, 7], [8]] | [[9, 2], [8]]
```

**Why is the last test important?**

- Initially, `original[0]` and `copied[0]` point to the same inner array.
- `original[0][0]=9` mutates the shared inner array.
- However, `original[0] = new int[]{7,7}` replaces **the reference slot of the outer original**, without mutating the old inner array.
- Because the two outer arrays have different identities, replacing the row reference in original **does not change the corresponding slot in copied**.

This is an exact example of the difference between **replacing the reference to a child** and **modifying state inside the child**.

## 11. Experiment 7: Deep Copying a 2D Array by Cloning Each Row

Create **`DeepMatrixCopyExperiment.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class DeepMatrixCopyExperiment {
    static int[][] deepCopy(int[][] input) {
        Objects.requireNonNull(input);
        int[][] result = new int[input.length][];

        for (int i = 0; i < input.length; i++) {
            result[i] =
                    Objects.requireNonNull(input[i]).clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3}};
        int[][] copied = deepCopy(original);

        System.out.println(original == copied);
        System.out.println(original[0] == copied[0]);

        original[0][0] = 99;
        copied[1][0] = 88;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copied));
    }
}
```

```bash
javac DeepMatrixCopyExperiment.java
java DeepMatrixCopyExperiment
```

```text
false
false
[[99, 2], [3]]
[[1, 2], [88]]
```

The `deepCopy` method creates a separate outer array and separate inner arrays. For `int[][]`, this is a sufficient deep copy for primitive elements.

**Do not apply blindly to `MutableThing[][]`:** cloning each row still only copies references to mutable elements. To separate all mutable state according to the contract, you also have to copy each mutable element or use an immutable representation.

## 12. Experiment 8: Object Array — Different Outer Array but Same Element

Create **`MutableElementArrayExperiment.java`**:

```java
public class MutableElementArrayExperiment {
    public static void main(String[] args) {
        StringBuilder originalText =
                new StringBuilder("A");
        StringBuilder[] original = {originalText};
        StringBuilder[] copied = original.clone();

        System.out.println("outer=" + (original == copied));
        System.out.println("element=" +
                (original[0] == copied[0]));

        copied[0].append("B");
        System.out.println("original element=" + original[0]);

        original[0] = new StringBuilder("C");
        System.out.println("original replaced=" + original[0]);
        System.out.println("copy retained=" + copied[0]);
    }
}
```

```bash
javac MutableElementArrayExperiment.java
java MutableElementArrayExperiment
```

```text
outer=false
element=true
original element=AB
original replaced=C
copy retained=AB
```

- `copied[0].append("B")` mutates the **shared StringBuilder**; original sees AB.
- `original[0] = new StringBuilder("C")` only replaces an **array slot in original**; copied still points to the old builder AB.

If you need a **snapshot of the text content** instead of sharing the mutable builder, you can convert each StringBuilder to an immutable `String` when copying. A call to `StringBuilder.toString()` creates a separate String representation per the API, ensuring subsequent `append` calls do not change the text snapshot.

## 13. Experiment 9: Deep Copying Object Array Contents via Value Snapshot

Create **`TextSnapshotExperiment.java`**:

```java
import java.util.Arrays;

public class TextSnapshotExperiment {
    static String[] snapshot(StringBuilder[] input) {
        String[] output = new String[input.length];
        for (int i = 0; i < input.length; i++) {
            output[i] = input[i].toString();
        }
        return output;
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");
        StringBuilder[] original = {first, second};

        String[] copiedText = snapshot(original);
        first.append("1");
        second.append("2");

        System.out.println("original=" +
                Arrays.toString(original));
        System.out.println("snapshot=" +
                Arrays.toString(copiedText));

        copiedText[0] = "X";
        System.out.println("original after slot=" +
                Arrays.toString(original));
    }
}
```

```bash
javac TextSnapshotExperiment.java
java TextSnapshotExperiment
```

```text
original=[A1, B2]
snapshot=[A, B]
original after slot=[A1, B2]
```

This is a **representation-converting copy** from a mutable `StringBuilder[]` to a `String[]` containing immutable values. It does not preserve the element type; this can be the right choice when the goal is a data snapshot, though it is not a generic clone of every StringBuilder.

**Limitation:** If builders are being modified concurrently while calling `toString()`, ownership/synchronization must be managed; the example runs sequentially and does not by itself guarantee an atomic snapshot across multiple mutable components.

## 14. Experiment 10: Copying the Outer `ArrayList` Still Shares Elements

Create **`ShallowListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowListExperiment {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> original =
                new ArrayList<>(List.of(item));
        List<StringBuilder> copied =
                new ArrayList<>(original);

        System.out.println(original == copied);
        System.out.println(original.get(0) == copied.get(0));

        original.add(new StringBuilder("B"));
        System.out.println("sizes=" +
                original.size() + "," + copied.size());

        copied.get(0).append("X");
        System.out.println("original child=" + original.get(0));
        System.out.println("copy child=" + copied.get(0));
    }
}
```

```bash
javac ShallowListExperiment.java
java ShallowListExperiment
```

```text
false
true
sizes=2,1
original child=AX
copy child=AX
```

**Two levels in the experiment:**

1. `new ArrayList<>(original)` creates a new list structure; `original.add(...)` does not make the copied list longer.
2. Both lists still point to **the same first StringBuilder element**; mutating the element from copied is visible in original.

**Do not conclude solely from `sizes=2,1`** that all elements have been deep copied. You need to test the element's mutator and compare `original.get(i)==copied.get(i)` when element identity matters.

## 15. Experiment 11: `List.copyOf` Only Locks the Structure, Not the Elements

Create **`CopyOfListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CopyOfListExperiment {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> snapshot = List.copyOf(source);
        source.add(new StringBuilder("B"));

        System.out.println("sizes=" +
                source.size() + "," + snapshot.size());

        item.append("X");
        System.out.println("nested=" + snapshot.get(0));

        try {
            snapshot.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("structure locked");
        }
    }
}
```

```bash
javac CopyOfListExperiment.java
java CopyOfListExperiment
```

```text
sizes=2,1
nested=AX
structure locked
```

`List.copyOf` creates an unmodifiable list with a snapshot structure when the input is a mutable `ArrayList`; it **does not deep-copy `StringBuilder` elements**.

For `List<String>`, because String is immutable, `List.copyOf` can be an effective solution to hold an immutable collection value. For `List<Mutable>`, achieving deeper independence requires copying/converting each mutable element.

**Lesson:** “Cannot call `add`” does not prove that the **nested contents** cannot change.

## 16. Experiment 12: An Unmodifiable View Differs from a Snapshot

Create **`UnmodifiableViewExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewExperiment {
    public static void main(String[] args) {
        List<String> original =
                new ArrayList<>(List.of("A"));

        List<String> view =
                Collections.unmodifiableList(original);
        List<String> snapshot =
                List.copyOf(original);

        original.add("B");

        System.out.println("original=" + original);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view rejects add");
        }
    }
}
```

```bash
javac UnmodifiableViewExperiment.java
java UnmodifiableViewExperiment
```

```text
original=[A, B]
view=[A, B]
snapshot=[A]
view rejects add
```

- `Collections.unmodifiableList(original)` prevents mutation **through the view**, but still reflects changes to the backing list made via the original reference.
- `List.copyOf(original)` creates a corresponding snapshot structure at the time of the call (with a mutable ArrayList input).
- Neither makes mutable element objects themselves immutable if the element type is something other than String.

**Do not test `List.of(...) == List.of(...)` or `List.copyOf(existing) != existing` as an identity guarantee.** Those value-based collection factory outputs do not guarantee a specific reuse/allocation strategy; verify semantics using contents and mutation behavior.

## 17. Experiment 13: Nested Lists — Two-Level Shallow

Create **`NestedListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedListExperiment {
    public static void main(String[] args) {
        List<String> students =
                new ArrayList<>(List.of("An"));

        List<List<String>> original =
                new ArrayList<>();
        original.add(students);

        List<List<String>> copied =
                new ArrayList<>(original);

        System.out.println("outer=" + (original == copied));
        System.out.println("inner=" +
                (original.get(0) == copied.get(0)));

        students.add("Binh");
        System.out.println("after inner mutation=" + copied);

        original.add(new ArrayList<>(List.of("Chi")));
        System.out.println("outer sizes=" +
                original.size() + "," + copied.size());
    }
}
```

```bash
javac NestedListExperiment.java
java NestedListExperiment
```

```text
outer=false
inner=true
after inner mutation=[[An, Binh]]
outer sizes=2,1
```

Copying only the outer `List<List<String>>` leaves inner lists shared. Mutating `students` propagates to copied. However, adding a new **inner-list reference to the original outer** does not change the size of the copied outer.

**This is a pattern to spot in JSON-like data**: a Map containing a List, a List containing a Map, graph nodes with child lists, DTOs containing nested structures. Every mutable level must be accounted for in the copy policy.

## 18. Experiment 14: Deep-Enough Copying for `List<List<String>>`

Create **`DeepNestedListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepNestedListExperiment {
    static List<List<String>> deepSnapshot(
            List<List<String>> source) {
        List<List<String>> copied =
                new ArrayList<>();

        for (List<String> inner : source) {
            copied.add(List.copyOf(inner));
        }

        return List.copyOf(copied);
    }

    public static void main(String[] args) {
        List<String> students =
                new ArrayList<>(List.of("An"));
        List<List<String>> original =
                new ArrayList<>();
        original.add(students);

        List<List<String>> copy = deepSnapshot(original);

        students.add("Binh");
        original.add(new ArrayList<>(List.of("Chi")));

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);

        try {
            copy.get(0).add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("inner snapshot locked");
        }
    }
}
```

```bash
javac DeepNestedListExperiment.java
java DeepNestedListExperiment
```

```text
original=[[An, Binh], [Chi]]
copy=[[An]]
inner snapshot locked
```

Why is this sufficient for this scenario?

- Each inner list is turned into an unmodifiable snapshot by `List.copyOf`.
- The outer list has its structure locked by `List.copyOf`.
- The elements are immutable `String` objects.
- Modifying the external source as well as the inner lists does not propagate to copy.

**Limitation:** If the inner list contains `StringBuilder` instead of String, an additional step is needed to copy/convert each element. The “deep” problem must be tied to the **types of mutable leaves**, not stop at generic depth 2.

## 19. Experiment 15: Map Structure Is Copied but Value Objects Are Still Shared

Create **`ShallowMapExperiment.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class ShallowMapExperiment {
    public static void main(String[] args) {
        StringBuilder value = new StringBuilder("A");
        Map<String, StringBuilder> original =
                new HashMap<>();
        original.put("x", value);

        Map<String, StringBuilder> copied =
                new HashMap<>(original);

        System.out.println(original == copied);
        System.out.println(original.get("x") == copied.get("x"));

        original.put("y", new StringBuilder("B"));
        System.out.println("sizes=" +
                original.size() + "," + copied.size());

        copied.get("x").append("X");
        System.out.println("original value=" + original.get("x"));
        System.out.println("copy value=" + copied.get("x"));
    }
}
```

```bash
javac ShallowMapExperiment.java
java ShallowMapExperiment
```

```text
false
true
sizes=2,1
original value=AX
copy value=AX
```

The HashMap copy constructor creates a **new map container**, but key/value references are transferred into the corresponding mappings without automatically copying the StringBuilder. Therefore:

- Mutate original's map structure: copied has its own structure.
- Mutate the shared StringBuilder value: both original and copy observe it.

**Avoid directly printing an entire Map with multiple entries as sample stdout if iteration order is not guaranteed.** Here, we print booleans, sizes, and one specific key so the output is deterministic.

## 20. Experiment 16: Deep Snapshot for Mutable Map Values

Create **`DeepMapExperiment.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class DeepMapExperiment {
    static Map<String, String> snapshot(
            Map<String, StringBuilder> input) {
        Map<String, String> result = new HashMap<>();

        for (Map.Entry<String, StringBuilder> e :
                input.entrySet()) {
            result.put(e.getKey(), e.getValue().toString());
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        StringBuilder value = new StringBuilder("A");
        Map<String, StringBuilder> original =
                new HashMap<>();
        original.put("x", value);

        Map<String, String> copy = snapshot(original);

        value.append("B");
        original.put("y", new StringBuilder("C"));

        System.out.println("original x=" + original.get("x"));
        System.out.println("copy x=" + copy.get("x"));
        System.out.println("copy has y=" + copy.containsKey("y"));

        try {
            copy.put("z", "D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy locked");
        }
    }
}
```

```bash
javac DeepMapExperiment.java
java DeepMapExperiment
```

```text
original x=AB
copy x=A
copy has y=false
copy locked
```

Changing the representation from mutable StringBuilder values to immutable String values breaks mutable aliases. The snapshot Map structure does not contain keys added later and does not allow mutating mappings through result.

**Remember:** `Map.copyOf` forbids null keys/values; if the domain allows null, a different copy policy is needed. If keys are mutable objects instead of String, the key-copy/equality contract must also be examined.

## 21. Experiment 17: Two Copies Sharing a Component Across Different Branches

Sometimes an alias is not in a field with the same name. Two objects can reference the same component through different graph branches.

Suppose:

```text
Order A ---> customer ---> Address X
Order B ---> shipping ---> Address X
```

A copy operation that only copies Order while keeping customer/shipping addresses by reference can create a **cross-branch shared alias**. When Order B updates shipping Address X, Order A sees the change in its customer address.

**Therefore, graph testing must identify reachable mutable objects**, rather than just looking at field names. An ownership table is helpful:

| Object | Referenced by | Mutable? | Copy policy |
| --- | --- | --- | --- |
| `Order` root | separate original/copy | Possibly | New root |
| `Address` | customer/shipping | Yes | New component or intentional sharing |
| `String` city | Address | No | Can be shared |
| `List<LineItem>` | Order | Possibly | New list/snapshot |
| `LineItem` | List | Depends on type | Copy if mutable |

If sharing is **intentional** (for example, a shared service/cache/collaborator), do not call it a deep copy of state if the API does not promise independence for that component.

## 22. Experiment 18: `Object.clone()` Copies the Root but Retains the Array Field

`Object.clone()` is commonly called inside a public override, with a class that implements `Cloneable`. The base implementation creates a **shallow field-for-field copy**.

Create **`ShallowObjectCloneExperiment.java`**:

```java
import java.util.Arrays;

final class Snapshot implements Cloneable {
    private final int[] data;

    Snapshot(int[] input) {
        data = input.clone();
    }

    void setAt(int index, int value) {
        data[index] = value;
    }

    @Override
    public Snapshot clone() {
        try {
            return (Snapshot) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(data);
    }
}

public class ShallowObjectCloneExperiment {
    public static void main(String[] args) {
        Snapshot original =
                new Snapshot(new int[] {1, 2});
        Snapshot copy = original.clone();

        System.out.println("root=" + (original == copy));

        original.setAt(0, 9);
        System.out.println("after original=" +
                original + " | " + copy);

        copy.setAt(1, 8);
        System.out.println("after copy=" +
                original + " | " + copy);
    }
}
```

```bash
javac ShallowObjectCloneExperiment.java
java ShallowObjectCloneExperiment
```

```text
root=false
after original=[9, 2] | [9, 2]
after copy=[9, 8] | [9, 8]
```

**Conclusion:** The original and cloned Snapshot are two different objects, but they hold the same `data` array reference copied from the source. Having Snapshot's constructor copy the input array **does not make `super.clone()` automatically perform a deep copy**.

Note: `Cloneable` is only a marker interface; it **does not declare a public `clone()`**. `Object.clone()` is protected and has a checked exception. The example provides a public override so the caller can invoke it.

## 23. Experiment 19: Deep Clone Replacing a Mutable Field After `super.clone()`

If the mutable field is **not final**, the override can:

1. Call `super.clone()` to create a shallow root.
2. Assign a separate component copy to the clone.
3. Return the cloned root once finished.

Create **`DeepObjectCloneExperiment.java`**:

```java
import java.util.Arrays;

final class Snapshot implements Cloneable {
    private int[] data;

    Snapshot(int[] input) {
        data = input.clone();
    }

    void setAt(int index, int value) {
        data[index] = value;
    }

    @Override
    public Snapshot clone() {
        try {
            Snapshot copy = (Snapshot) super.clone();
            copy.data = data.clone();
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(data);
    }
}

public class DeepObjectCloneExperiment {
    public static void main(String[] args) {
        Snapshot original =
                new Snapshot(new int[] {1, 2});
        Snapshot copy = original.clone();

        original.setAt(0, 9);
        copy.setAt(1, 8);

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac DeepObjectCloneExperiment.java
java DeepObjectCloneExperiment
```

```text
original=[9, 2]
copy=[1, 8]
```

Here, `copy.data = data.clone()` creates an independent array, so mutations in either direction do not propagate.

**The `final` aspect:** If `private final int[] data` is declared, the assignment `copy.data = ...` inside the clone override is illegal. You can choose a **copy constructor** or another copy implementation using `new`, where the constructor is allowed to initialize final fields, instead of clone-and-patch.

**The security/lifecycle aspect:** Do not publish the cloned object to another thread or registry before finishing updating the necessary references.

## 24. Experiment 20: Explicit Copy Constructor with a `final` Field

Create **`FinalFieldCopyExperiment.java`**:

```java
import java.util.Arrays;

final class Data {
    private final int[] values;

    Data(int[] values) {
        this.values = values.clone();
    }

    Data(Data source) {
        this.values = source.values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class FinalFieldCopyExperiment {
    public static void main(String[] args) {
        Data original = new Data(new int[] {1, 2});
        Data copy = new Data(original);

        original.setAt(0, 9);
        copy.setAt(1, 8);

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac FinalFieldCopyExperiment.java
java FinalFieldCopyExperiment
```

```text
original=[9, 2]
copy=[1, 8]
```

`private final int[] values` keeps the reference from being reassigned after construction, but **Data is still a mutable class** due to `setAt`. The two instances are independent only because each constructor creates its own array.

**Do not confuse:** “Successful deep copy” does not mean “an immutable copy”. If immutability is desired, in addition to defensive copying, you must also not expose mutators and not leak the internal array reference.

## 25. Experiment 21: Constructors Do Not Run on the `Object.clone()` Path

This difference is very useful for reasoning about validations/side effects when copying.

Create **`CloneVsConstructorExperiment.java`**:

```java
final class Ticket implements Cloneable {
    private static int constructorCalls;

    private final int number;

    Ticket(int number) {
        constructorCalls++;
        this.number = number;
    }

    Ticket copy() {
        return new Ticket(number);
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    static int calls() {
        return constructorCalls;
    }
}

public class CloneVsConstructorExperiment {
    public static void main(String[] args) {
        Ticket original = new Ticket(7);
        System.out.println("after original=" + Ticket.calls());

        Ticket cloned = original.clone();
        System.out.println("after clone=" + Ticket.calls());

        Ticket copied = original.copy();
        System.out.println("after copy=" + Ticket.calls());

        System.out.println(original == cloned);
        System.out.println(original == copied);
    }
}
```

```bash
javac CloneVsConstructorExperiment.java
java CloneVsConstructorExperiment
```

```text
after original=1
after clone=1
after copy=2
false
false
```

`Object.clone()` creates a new object without running the Ticket constructor; `copy()` calls `new Ticket(...)`, so the counter increases.

**Do not claim that every method named `clone()` skips the constructor**: a custom override writing `return new Ticket(...);` will invoke the constructor. The conclusion here holds for **the `super.clone()`/Object.clone()` path**.

If a class's constructor performs validation or resource allocation, you must examine the clone contract carefully: field-for-field cloning does not re-execute those steps by default.

## 26. Experiment 22: Copying a Record Containing an Array Is Not Automatically Deep

A record in Java 17 has final component fields, yet an array component **remains mutable**.

Create **`RecordArrayAliasExperiment.java`**:

```java
import java.util.Arrays;

record Measurements(int[] values) {
}

public class RecordArrayAliasExperiment {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Measurements original = new Measurements(source);
        Measurements copied = new Measurements(
                original.values());

        System.out.println(original == copied);
        System.out.println(
                original.values() == copied.values());

        source[0] = 9;
        System.out.println("original=" +
                Arrays.toString(original.values()));
        System.out.println("copy=" +
                Arrays.toString(copied.values()));

        copied.values()[1] = 8;
        System.out.println("source=" +
                Arrays.toString(source));
    }
}
```

```bash
javac RecordArrayAliasExperiment.java
java RecordArrayAliasExperiment
```

```text
false
true
original=[9, 2]
copy=[9, 2]
source=[9, 8]
```

The two record instances have different identities but hold the same `source` array. There is no defensive copying in the record's canonical constructor or generated accessor. A final field in a record only fixes the reference; it does not lock the array elements.

**How to fix:** Have the compact constructor clone the array, write a custom accessor that returns a clone, and, if value equality based on array contents is needed, override `equals`/`hashCode` accordingly. Record-generated equals for an array component does not automatically deep-compare contents.

## 27. Experiment 23: A Record with Defensive Copying at Both Boundaries

Create **`SafeRecordCopyExperiment.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeMeasurements(int[] values) {
    SafeMeasurements {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    public int at(int index) {
        return values[index];
    }
}

public class SafeRecordCopyExperiment {
    public static void main(String[] args) {
        int[] source = {1, 2};

        SafeMeasurements original =
                new SafeMeasurements(source);
        SafeMeasurements copied =
                new SafeMeasurements(original.values());

        source[0] = 9;
        int[] returned = copied.values();
        returned[1] = 8;

        System.out.println("original=" +
                Arrays.toString(original.values()));
        System.out.println("copy=" +
                Arrays.toString(copied.values()));
        System.out.println(original.at(0));
    }
}
```

```bash
javac SafeRecordCopyExperiment.java
java SafeRecordCopyExperiment
```

```text
original=[1, 2]
copy=[1, 2]
1
```

- The compact constructor replaces the parameter with `values.clone()` before the field is initialized according to record rules.
- The accessor returns a clone, without exposing the internal array.
- The two record instances hold separate mutable arrays; an external source cannot mutate internal state.

**Warning:** A record's generated `equals`/`hashCode` still relies on array component identity semantics and does not automatically compare values `[1,2]`. **Immutability** and **logical equality** are two contracts that must be verified separately.

## 28. Experiment 24: Copying Can Lose the Subtype If the Parent Class Constructor Is Called

When `source` has a subclass as its runtime class, a copy constructor on the parent class using `new Base(source)` **always creates a Base instance** and does not automatically preserve subclass fields.

Create **`SubtypeCopyExperiment.java`**:

```java
class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    Animal(Animal source) {
        this.name = source.name;
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

public class SubtypeCopyExperiment {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copied = new Animal(original);

        System.out.println(original.getClass().getSimpleName());
        System.out.println(copied.getClass().getSimpleName());
        System.out.println(original.name().equals(copied.name()));
    }
}
```

```bash
javac SubtypeCopyExperiment.java
java SubtypeCopyExperiment
```

```text
Dog
Animal
true
```

**Conclusion:** The copy constructor copied the `name` field according to the Animal contract, but did not preserve the runtime subtype Dog/breed. If the API promises a polymorphic copy, you can define `abstract Base copy()` and let each concrete subclass copy itself.

Conversely, `Object.clone()` under its field-copy contract typically creates an object of **the same runtime class as source**, but remains shallow with respect to nested mutable fields. **Subtype preservation does not prove deep copying.**

## 29. Experiment 25: Polymorphic Copy Without `Cloneable`

Create **`PolymorphicCopyExperiment.java`**:

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

public class PolymorphicCopyExperiment {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = original.copy();

        System.out.println(original == copy);
        System.out.println(copy.getClass().getSimpleName());

        if (copy instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac PolymorphicCopyExperiment.java
java PolymorphicCopyExperiment
```

```text
false
Dog
Collie
```

Here `copy()` is a polymorphic method override with a covariant return type Dog. It calls the constructor normally and preserves the subtype because **the Dog class actively builds a Dog copy**.

An interface `Copyable<T> { T copy(); }` can also establish a similar contract. This is an **application-defined API**, not something automatically provided by the `Cloneable` marker.

For a subclass with new mutable fields, that class must itself enforce the copy policy for each field.

## 30. Experiment 26: Deep Copying a Cyclic Graph

Deep copying complex graphs must handle **cycles** and **shared identity topology**. You cannot simply recurse with `new Node(copy(next))` without remembering visited objects: a graph with a cycle can cause infinite recursion.

We use `IdentityHashMap<Node,Node>` because keys must be distinguished by **reference identity itself**, independent of any `equals()` implementation.

Create **`CyclicGraphCopyExperiment.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicGraphCopyExperiment {
    static Node copyGraph(Node source, Map<Node, Node> seen) {
        if (source == null) {
            return null;
        }

        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }

        Node copy = new Node(source.name);
        seen.put(source, copy);
        copy.next = copyGraph(source.next, seen);
        return copy;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        Node copy = copyGraph(a, new IdentityHashMap<>());

        System.out.println(copy != a);
        System.out.println(copy.next != b);
        System.out.println(copy.next.next == copy);
        System.out.println(a.next.next == a);
        System.out.println(copy.name + copy.next.name);
    }
}
```

```bash
javac CyclicGraphCopyExperiment.java
java CyclicGraphCopyExperiment
```

```text
true
true
true
true
AB
```

**How the algorithm preserves the cycle:**

1. Create a copy of Node A.
2. Record the mapping `A_original -> A_copy` **before** copying `next`.
3. Move to B, create a copy of B, and record the mapping.
4. B.next points back to A_original; the map already has A_copy, so it is reused.
5. The resulting copied graph has A_copy↔B_copy, separated from A_original↔B_original.

This is an example with a **mutable link field `next`** to wire up the graph in two phases. For a graph with `final` links or strict constructor invariants, a different construction strategy is needed, as fields cannot be assigned after the constructor as in the example.

## 31. Experiment 27: Preserving Sharing in a Graph Without Duplicating Shared Branches

The original graph may have **a child shared by two fields**:

```text
root.left ──┐
            ├──> Child X
root.right ─┘
```

If the child is copied twice, the result no longer preserves the `copy.left == copy.right` relationship. This can violate the contract when sharing is part of the semantics.

Create **`SharedGraphCopyExperiment.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String id;
    Node left;
    Node right;

    Node(String id) {
        this.id = id;
    }
}

public class SharedGraphCopyExperiment {
    static Node copy(Node source, Map<Node, Node> visited) {
        if (source == null) {
            return null;
        }
        Node existing = visited.get(source);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(source.id);
        visited.put(source, result);
        result.left = copy(source.left, visited);
        result.right = copy(source.right, visited);
        return result;
    }

    public static void main(String[] args) {
        Node shared = new Node("X");
        Node root = new Node("root");
        root.left = shared;
        root.right = shared;

        Node duplicate = copy(root, new IdentityHashMap<>());

        System.out.println(root.left == root.right);
        System.out.println(duplicate.left == duplicate.right);
        System.out.println(duplicate.left != shared);
        System.out.println(duplicate.id);
    }
}
```

```bash
javac SharedGraphCopyExperiment.java
java SharedGraphCopyExperiment
```

```text
true
true
true
root
```

The map helps the clone preserve **the same sharing topology** while simultaneously creating distinct mutable Node instances compared to source. This is a deeper problem than copying a simple `int[][]`.

**Do not casually use `HashMap<Node,Node>` if `Node.equals()` can consider two nodes with different identities to be equal.** In graph copying where tracking must be by **instance identity**, `IdentityHashMap` expresses the intent clearly.

## 32. Why Are `equals()` and `hashCode()` Not Sufficient Proof of a Deep Copy?

A value class can override equals to compare contents. Two objects equal by value can still share a mutable array:

```java
System.out.println(original.equals(copy)); // May be true.
System.out.println(original == copy);       // May be false.
```

These two lines are an **illustrative snippet**; the result depends on the class implementation.

Therefore, you need to check **at least three axes**:

1. **Root identity**: new object or alias?
2. **Logical equality/state**: are the initial contents equivalent?
3. **Mutation isolation**: does modifying original/copy/nested objects propagate?

Hash code also does not prove deep copy: two unequal objects can have colliding hashes, and two equal objects must have the same hash if the contract holds, yet the hash says nothing about whether component references are shared.

### Suggested Checklist

```text
Check A: original != copy (if the API promises a new instance)
Check B: same initial logical values
Check C: mutate original root field; copy unaffected
Check D: mutate copy root field; original unaffected
Check E: mutate original mutable child; copy unaffected
Check F: mutate copy mutable child; original unaffected
Check G: mutate original nested grandchild; copy unaffected
Check H: mutate constructor input retained by caller
Check I: mutate getter-returned mutable data
```

C/G/H/I may not apply when a class has all immutable components or getters only provide value queries. **Test according to the contract**; do not force a single checklist template onto every type of object.

## 33. Experiment 28: Automatically Reporting PASS/FAIL with Java `AssertionError`

An experimental program should check **meaningful** conditions and report FAIL immediately if wrong, instead of only printing a few values for the reader to guess.

Create **`CopyIsolationSelfTest.java`**:

```java
import java.util.Arrays;

final class Payload {
    private final int[] values;

    Payload(int[] input) {
        values = input.clone();
    }

    Payload(Payload source) {
        values = source.values.clone();
    }

    void set(int index, int value) {
        values[index] = value;
    }

    int[] snapshot() {
        return values.clone();
    }
}

public class CopyIsolationSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2};
        Payload original = new Payload(input);
        Payload copy = new Payload(original);

        check(original != copy, "root identity");

        input[0] = 99;
        check(Arrays.equals(original.snapshot(),
                new int[] {1, 2}), "input alias");

        original.set(0, 9);
        check(copy.snapshot()[0] == 1,
                "original -> copy isolation");

        copy.set(1, 8);
        check(original.snapshot()[1] == 2,
                "copy -> original isolation");

        int[] external = copy.snapshot();
        external[0] = 77;
        check(copy.snapshot()[0] == 1,
                "getter alias isolation");

        System.out.println("copy isolation PASS");
    }
}
```

```bash
javac CopyIsolationSelfTest.java
java CopyIsolationSelfTest
```

```text
copy isolation PASS
```

Here, the assertions do not depend on the JVM `-ea` flag because the helper explicitly throws `AssertionError`. The targeted checks:

- Different root identity.
- Constructor does not leak an alias to input.
- Bidirectional mutations do not propagate.
- Getter returns a snapshot separating the mutable reference.

**Limitation:** The self-test only covers `Payload` having a single `int[]`. If a `List<MutableItem>` is added in a future version, tests for the nested list/elements must be added.

## 34. Experiment 29: Writing a Result Table by Time Point

In a review, instead of labeling “shallow”/“deep” by intuition alone, build a table showing state **before and after each modification**.

For example, with `ShallowAddressExperiment`:

| Time Point | Operation | Original | Copy | Observation |
| --- | --- | --- | --- | --- |
| T0 | Just copied | `An@Hue` | `An@Hue` | Same contents |
| T1 | Rename original | `Binh@Hue` | `An@Hue` | Separate root field |
| T2 | Move copy's address | `Binh@Da Nang` | `An@Da Nang` | Nested mutable child shared |

With `DeepAddressExperiment`:

| Time Point | Operation | Original | Copy | Observation |
| --- | --- | --- | --- | --- |
| T0 | Just copied | `An@Hue` | `An@Hue` | Same contents |
| T1 | Mutate original address | `An@Da Nang` | `An@Hue` | Separate child objects |
| T2 | Mutate copy address | `An@Da Nang` | `An@Ha Noi` | Independent in the reverse direction too |

**High-reliability experimental method:** each experiment starts from a known state; clearly records each mutation; checks root, child, and, where applicable, grandchild; avoids mixing multiple actions without marking time points.

## 35. When Should References Be Intentionally Shared in a Copy?

Not every shared reference is a bug.

**Common safe sharing:**

- `String`, `Integer`, `LocalDate`, `Instant`, and other immutable values.
- An immutable collection snapshot with all immutable elements.
- A stateless service/shared collaborator by contract.
- A persistent immutable data structure with structural sharing.

**Sharing that requires careful analysis:**

- Mutable caches or memoization.
- `ArrayList`/`HashMap`/arrays.
- `StringBuilder`, `Date`.
- Resource handles such as sockets, streams, database connections.
- Objects containing callbacks or threads.
- A mutable entity with its own business identity.

If the copy only holds a reference to an immutable component, the data remains independent in observable state. If the copy holds a reference to a live resource, “modifying” or closing the resource in one wrapper can break the other wrapper — dedicated resource ownership rules are required rather than just talking about deep/shallow.

## 36. Experimenting with Copying via Constructor vs `Object.clone()`

| Difference | Copy constructor using `new` | Override based on `super.clone()` |
| --- | --- | --- |
| Runs a new constructor | Yes | No under the Object.clone mechanism |
| Definite assignment for `final` fields | Follows constructor flow | Final fields are copied field-for-field |
| Copies mutable references | Depends on code; can actively copy | Shallow by default |
| Re-runs validation | Yes if constructor calls validation logic | Does not automatically run constructor validations |
| Public API | Can be explicit `new T(source)` | Object.clone is protected, needs an exposed override |
| Checked exception | Follows constructor policy | Base declares `CloneNotSupportedException` |
| Runtime subtype | `new Base(source)` creates Base | Object.clone creates the same runtime class as source |
| Mutation isolation testing | Needed | Needed |
| Ease of auditing nested copy | Usually explicit per field | Requires reading the override/hierarchy |
| With a mutable `final` field | Can assign a defensive copy in the constructor | Hard to clone-and-patch a final field |

**Do not conclude that clone is “good/bad” solely from the table.** If code needs to clone a legacy API, understand its contract clearly and write corresponding tests. When designing a new Java API with mutable nested state and invariants, an explicit copy usually makes it easier to express the policy.

## 37. Specific Warning About Constructor Input Being Modified Concurrently

The experiments above **run sequentially**: the input arrays/lists remain stable while the constructor or copy method reads/copies them.

If another thread modifies source concurrently while copying:

- Inconsistent data across fields/elements may occur.
- With non-concurrent-safe mutable collections, the iterator/copy can fail or observe a race according to the API.
- If validation happens before copying, source can change between the two steps.
- `final` fields on the result do not automatically turn taking a snapshot from source into an atomic operation.

**Safe approach:** establish ownership or a synchronization protocol; ensure source state stays stable during the snapshot; validate **the stored snapshot itself**. If a concurrent snapshot is required, choose a concurrent data structure/API with an explicit contract.

Do not use a stress test run a few times without seeing errors to “prove” thread safety. This lesson focuses on the alias graph logic of a sequential snapshot.

## 38. Warning About Copying Objects with Resources, IDs, or Lifecycles

An object may hold:

- Session ID / database-generated ID.
- Creation timestamp.
- File/socket/stream handle.
- A thread/lock/callback.
- Registry membership or external lease.

Copying all fields via Object.clone can accidentally **retain the same ID or resource handle**. However, a copy constructor can also cause bugs if the author deliberately copies it incorrectly.

Before copying, determine:

1. Which fields must be kept unchanged?
2. Which fields must generate a new ID?
3. Which resources are shared, and which must be newly opened or must not be copied?
4. Who has the authority to `close`?
5. Is it necessary to preserve the subtype and invariants of the class hierarchy?
6. Are there external side effects from the constructor/factory?
7. Does copying mean taking a “value” snapshot or creating a new business entity?

If there are no sensible copy semantics for a live object, you can **forbid copying** and only copy the immutable configuration separately.

## 39. Common Mistakes in Experiments

| Mistake | Why It Is Wrong | How to Check/Fix |
| --- | --- | --- |
| “`b=a` is a copy” | Both references point to the same root | Print `a==b` and mutate |
| “`a!=b` proves a deep copy” | A nested child may still be shared | Check `a.child==b.child` and mutate |
| “Initial fields are identical so they are independent” | Same values say nothing about aliases | Modify mutable fields in both directions |
| “Modifying a root field does not propagate so it is deep” | Mutable children may still be shared | Mutate child/grandchild |
| “Array `clone()` is always deep” | Object arrays and 2D arrays are shallow on references | Check inner array/element identity |
| “New ArrayList copy also clones elements” | It only copies the structure | Mutate a StringBuilder element |
| “List.copyOf makes mutable elements immutable” | Structure is unmodifiable, elements may remain mutable | Mutate an element alias |
| “unmodifiableList is a snapshot” | The view sees backing changes | Mutate the source list |
| “Getter returns a copy so constructor has no alias” | An input alias may still be retained | Mutate the original input |
| “Constructor copies so getter has no alias” | Getter may return an internal mutable reference | Mutate the getter result |
| “A final field makes an array immutable” | final only fixes the reference | Mutate `array[i]` |
| “Record automatically deep-copies arrays” | Record constructor/accessor retains aliases by default | Mutate input and accessor |
| “record equals compares array contents” | Array components use identity equality | Custom Arrays.equals/hash |
| “`Object.clone()` invokes the constructor again” | Object.clone skips the constructor | Counter experiment |
| “Cloneable automatically provides a public clone” | Marker interface has no method | Public override or copy method |
| “copy constructor preserves runtime subtype” | `new Base` creates Base | Polymorphic copy |
| “Preserving subtype means deep copy” | Mutable descendant fields may still be shared | Audit per-subclass fields |
| “Two equal hashCodes mean one object” | Collisions are valid | Use `==` for identity |
| “Two objects that are equals cannot share mutable refs” | Equality and alias isolation are different | Mutate nested state |
| “Copying a graph only needs recursion” | Infinite cycles / shared topology lost | IdentityHashMap visited |
| “Deep copy always creates every immutable object anew” | Sharing immutable state can be safe | Define by observable state |
| “HashMap/HashSet toString order is always fixed” | No general guarantee | Check deterministic size/key/value |
| “Passing a stress test once proves thread-safety” | Races are timing-dependent | Synchronization/ownership protocol |
| “Cloning a live resource creates a new handle automatically” | Field copying usually keeps the reference | Resource-specific contract |

## 40. Practice Exercises with Answers

**Question 1.** `Box b=a;` after `b.set(10)`, does a change?

*Answer:* Yes, if the setter mutates the object itself and both references point to that same object. There is no copy.

**Question 2.** If a copy constructor only copies primitive fields, is `original != copy` true and does modifying either side propagate?

*Answer:* The two roots have different identities; with separate instance primitive fields, modifying one side does not change the other.

**Question 3.** Two Customer objects are different but share a mutable Address. Does modifying Customer.name necessarily propagate?

*Answer:* No, if each Customer holds a separate name reference field; reassigning the name field does not change Address. However, mutating the shared Address does propagate.

**Question 4.** Why is `int[] cloned = original.clone()` independent in its one-dimensional contents?

*Answer:* Clone creates a new array and copies primitive values into separate slots.

**Question 5.** Why is `int[][] cloned = original.clone()` still shallow?

*Answer:* The inner arrays are copied as references without creating new inner arrays.

**Question 6.** When a `StringBuilder[]` is cloned, can calling `cloned[0].append("X")` change original?

*Answer:* Yes, if element 0 is still the same StringBuilder instance.

**Question 7.** Does `new ArrayList<>(other)` create a new list object? Does it clone element objects?

*Answer:* Yes, it creates a new list structure; it does not automatically clone element objects.

**Question 8.** Does `Collections.unmodifiableList(source)` prevent `source.add(...)`?

*Answer:* No. It is an unmodifiable view; the backing source remains mutable.

**Question 9.** Does `List.copyOf(mutableArrayList)` snapshot the list structure?

*Answer:* Yes, according to its semantics for a mutable source; however, it does not deep-copy mutable elements.

**Question 10.** When using `Map.copyOf` where map values are mutable lists, is that already a deep copy?

*Answer:* Not yet. Each nested mutable list/value must be copied appropriately.

**Question 11.** If original and copy share the same String reference, is the deep copy wrong?

*Answer:* Not necessarily. String is immutable; sharing can be safe if the copy contract allows it.

**Question 12.** Does `super.clone()` call the constructor of the class being cloned?

*Answer:* Not under the Object.clone mechanism. An override that uses `new` itself will call the constructor.

**Question 13.** Can `private final int[] data` be patched to a new array after `super.clone()`?

*Answer:* Not via an ordinary assignment inside the clone method; a copy constructor can initialize the final field appropriately.

**Question 14.** Why is checking `original.equals(copy)` not enough to prove a deep copy?

*Answer:* Equality is defined by the class and can return true even while sharing mutable references.

**Question 15.** What if a copy must preserve the runtime subtype when source has declared type Animal and actual type Dog?

*Answer:* Use a polymorphic copy method or an appropriate clone contract; `new Animal(source)` only creates an Animal.

**Question 16.** What risk does recursive copying of a graph A→B→A without a visited map pose?

*Answer:* Infinite recursion loop or stack overflow.

**Question 17.** Why should the visited map in graph copying check identity instead of value equals?

*Answer:* Two nodes can be equal by value yet have different identities; deep copy topology needs to distinguish actual instances.

**Question 18.** If two branches point to the same child in source, must sharing necessarily be preserved in copy?

*Answer:* It depends on the contract. If topology preservation is required, copy should share the cloned child across both branches rather than cloning into two independent children.

**Question 19.** Does a clone of an object holding a Socket automatically create a different Socket?

*Answer:* Not by default. Shallow field copying keeps the same Socket reference; a resource-specific factory/ownership rule is required.

**Question 20.** Is testing mutation in just one direction, original→copy, sufficient?

*Answer:* No. You also need to mutate copy→original and nested components, plus input/getter aliases depending on the API.

## 41. Experimental Checklist Before Drawing Conclusions

- [ ] Have you distinguished reference assignment from object copying?
- [ ] Have you checked root identity using `==` when the contract promises a new copy?
- [ ] Have you recorded the logical data of both instances **before modifying**?
- [ ] Have you modified a root field of original and read copy?
- [ ] Have you modified a root field of copy and read original?
- [ ] Have you modified a mutable child via original?
- [ ] Have you modified a mutable child via copy?
- [ ] Have you checked grandchild/nested list/array if present?
- [ ] Have you checked child reference identity when useful?
- [ ] Have you distinguished replacing a reference slot from mutating the referenced object?
- [ ] If copying a 2D array, have you checked both outer and inner arrays?
- [ ] If copying an object array, have you considered mutable elements?
- [ ] If copying a collection, have you distinguished structure sharing from element sharing?
- [ ] If using `List.copyOf`/`Map.copyOf`, have you considered nested mutable components?
- [ ] If using an unmodifiable view, have you tested mutating the backing collection?
- [ ] If the class accepts mutable input, have you tried modifying the input after the constructor?
- [ ] If the class returns mutable data, have you tried modifying the getter output?
- [ ] If using `Object.clone()`, have you verified the marker/access/method contract?
- [ ] Have you checked Object.clone shallowness and constructor-bypass when they affect logic?
- [ ] Is there a mutable `final` field that makes clone-and-patch harder?
- [ ] Is there a requirement to preserve runtime subtype?
- [ ] Is there a requirement to preserve graph cycles or shared topology?
- [ ] Are there resources, IDs, or external lifecycles unsuitable for field copying?
- [ ] Have you avoided relying on raw hash values or unordered collection iteration?
- [ ] Is there a self-test `check` method that throws an exception on failure?
- [ ] Have you clearly defined which sharing of immutable components is **allowed**?
- [ ] Have you defined ownership/synchronization when copying concurrently mutated data?
- [ ] Do the Java 17+ examples have matching filenames and public classes, `javac`/`java` commands, and stdout?

---

**Final takeaway:** To know whether a copy is independent or not, **you must experiment with mutating state in both directions and at every relevant mutable level**. `original != copy` only proves that the root objects are different; a shallow copy can still share an array, list, map, or a mutable element. Observe separately **replacing an outermost field**, **mutating a container**, and **mutating a nested element/child**, then test **input aliases and getter aliases**. For simple data, a copy constructor, `array.clone()`, or `Arrays.copyOf` may suffice; for 2D arrays, nested collections, and graphs with cycles/sharing, depth and topology must be clearly defined. `Object.clone()` is shallow by default and does not run the constructor; explicit copying expresses the copy depth more clearly when there are mutable state and invariants. **A correct copy is one that fulfills a verified observable contract — not just a copy labeled “deep”.**
