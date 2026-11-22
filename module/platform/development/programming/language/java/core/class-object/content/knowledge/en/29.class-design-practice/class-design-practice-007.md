# Experiments on Shared References, Pass-by-Value, and Copying in Java

## 1. Goal: Seeing What Is Actually Shared?

In Java, an object can be accessed through **multiple reference values**. Two variables with different names are not necessarily two objects. When passing a reference to a method, Java uses **pass-by-value**: the method receives a copy of the **reference value**, not a copy of the object. When copying a structure that contains references, the copy may own its own container but **still share the component objects**.

Four questions must be kept separate:

1. **How many objects are created?** Look at object/array creation operations and observed behavior; do not count variables as if counting objects.
2. **Which variables point to the same object?** Use identity `==` and reference diagrams to reason about it.
3. **What does the method receive?** A copy of a primitive value or a copy of a reference value.
4. **To what extent does copying go?** Only copy the reference, copy the container (shallow), also copy mutable children (deep by scope), or share because children are immutable?

A few foundational statements:

- `Employee b = a;` **does not copy the Employee object**.
- `b.setName(...)` can cause `a` to observe changes if `a == b`.
- `b = new Employee(...)` only **changes the reference of b**, not the reference of a.
- When calling `edit(employee)`, the parameter receives a **copy of the reference**, but can modify the caller's **object itself**.
- `new ArrayList<>(oldList)` creates a **separate list** but usually shares **the element objects**.
- `array.clone()` creates a separate array, but for an array containing references it only copies **reference elements**.
- `record` does not automatically deep-copy mutable array/list components.
- `Object.clone()` performs a **field-wise shallow copy** by default, not an automatic deep clone.
- A **deep copy** must clearly specify which objects are separated, which objects remain shared, how to handle aliases/cycles, and exclude resources that cannot be copied.

**Version:** Examples run standalone on Java 17+ using `javac` and `java`. Each program is a separate file; helper class names may overlap across examples because **all files are not combined into one package and compiled at the same time**.

## 2. Foundational Diagram: Reference Variables and Objects Are Two Different Things

Example:

```java
Book a = new Book("Java");
Book b = a;
```

This is an **illustrative code snippet** with a hypothetical Book class.

Diagram:

```text
Local variables       Object
    a ───────────┐
                 ├────────> Book { title = "Java" }
    b ───────────┘
```

There are two variables `a` and `b` but **one Book object** in this visualization. The statement `Book b = a` copies the reference value from a to b, without calling a new constructor.

Modifying the object through b:

```java
b.setTitle("Java 17");
```

will cause a to observe the same title because a and b point to the same object.

Reassigning b:

```java
b = new Book("Other");
```

causes b to reference a different object; a still points to the old Book. If the old object is still reachable through a, it does not disappear on its own.

**Note:** The arrows are only a logical model; they do not describe physical memory addresses or pointer arithmetic that Java allows a program to perform.

## 3. Experiment 1 — One Object, Two Names, State Changing Together

Create **`SharedReferenceDemo.java`**:

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

public class SharedReferenceDemo {
    public static void main(String[] args) {
        Counter original = new Counter(5);
        Counter alias = original;

        System.out.println(original == alias);

        alias.increment();

        System.out.println(original.value());
        System.out.println(alias.value());
    }
}
```

```bash
javac SharedReferenceDemo.java
java SharedReferenceDemo
```

```text
true
6
6
```

**Step-by-step explanation:**

1. `new Counter(5)` creates a Counter object.
2. `original` points to that object.
3. `alias = original` copies the reference value; it does **not** create a second Counter.
4. `original == alias` is true because they have the same identity.
5. `alias.increment()` mutates the Counter referenced by both names.
6. Both calls to `value()` read the same field and return 6.

### Experimental Conclusion

When multiple places hold the same mutable object, every place can observe side effects (according to appropriate access/concurrency rules). Therefore, API design must clearly state **ownership**, whether sharing mutable state is allowed, and who has permission to mutate.

## 4. Experiment 2 — Assigning a Reference Variable Differs from Modifying an Object

Create **`ReassignmentVersusMutationDemo.java`**:

```java
final class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class ReassignmentVersusMutationDemo {
    public static void main(String[] args) {
        Counter a = new Counter(2);
        Counter b = a;

        b.value = 7;
        System.out.println(a.value);

        b = new Counter(99);
        System.out.println(a.value);
        System.out.println(b.value);
        System.out.println(a == b);
    }
}
```

```bash
javac ReassignmentVersusMutationDemo.java
java ReassignmentVersusMutationDemo
```

```text
7
7
99
false
```

After `b.value = 7`, a shared object is mutated. After `b = new Counter(99)`, variable b is **assigned a new reference**; a's object still has value 7.

`b = a` is an operation that copies the **reference value**. It is not a **shallow copy of the object**; a typical shallow copy still needs to create a new object/container.

## 5. Experiment 3 — `null` Only Changes One Reference

Create **`NullAliasDemo.java`**:

```java
final class Note {
    final String text;

    Note(String text) {
        this.text = text;
    }
}

public class NullAliasDemo {
    public static void main(String[] args) {
        Note first = new Note("kept");
        Note second = first;

        first = null;

        System.out.println(first == null);
        System.out.println(second.text);
    }
}
```

```bash
javac NullAliasDemo.java
java NullAliasDemo
```

```text
true
kept
```

`first = null` does not "destroy" the Note object. `second` still references that object. Java does not call an immediate destructor at a null assignment and does not allow applications to proactively free object memory like `free()` in C.

**Do not add null assignments everywhere** with the expectation that GC will run immediately. Manage reference ownership of collections, static caches, and listeners according to their proper lifecycle.

## 6. What Does Pass-by-Value Mean?

Java is **pass-by-value** for all method arguments:

- Primitive `int`: copies the **numeric value**.
- Primitive `boolean`: copies the **boolean value**.
- Reference type: copies the **reference value** (pointing to some object or null).

A method has its **own parameter variable**. Reassigning the parameter does not reassign the argument variable on the calling side. However, if the parameter copies a reference pointing to the same mutable object, using the parameter to mutate the object will have an effect visible to the caller.

### Comparison Table

| Operation in method | Changes caller variable? | Can change object caller points to? |
| --- | --- | --- |
| `parameter = 42` with `int` | No | No object involved |
| `parameter = new Box(...)` | No | No, only assigns parameter |
| `parameter = null` | No | No |
| `parameter.value = 42` | No | Yes, if the same object |
| `parameter.add(...)` on List | No | Yes, if the same mutable List |
| `parameter[0] = 42` on array | No | Yes, if the same array |

**Do not call Java pass-by-reference** in the sense that a parameter variable is a direct alias to the **caller variable**. Both variables hold the same reference value at the time of the call, but they are **two different variables**.

## 7. Experiment 4 — Pass-by-Value with Primitives

Create **`PrimitivePassByValueDemo.java`**:

```java
public class PrimitivePassByValueDemo {
    static void update(int number) {
        number = 100;
        System.out.println("inside=" + number);
    }

    public static void main(String[] args) {
        int value = 5;

        update(value);

        System.out.println("outside=" + value);
    }
}
```

```bash
javac PrimitivePassByValueDemo.java
java PrimitivePassByValueDemo
```

```text
inside=100
outside=5
```

`number` is a local parameter whose initial value is copied from `value`. Assigning 100 to number does not touch the value variable in main.

This experiment usually does not cause confusion, but the same **copy argument value** rule applies to reference types.

## 8. Experiment 5 — Modifying an Object via a Parameter Is Visible to the Caller

Create **`MutableParameterDemo.java`**:

```java
final class Wallet {
    private int coins;

    Wallet(int coins) {
        this.coins = coins;
    }

    void add(int amount) {
        coins += amount;
    }

    int coins() {
        return coins;
    }
}

public class MutableParameterDemo {
    static void reward(Wallet wallet) {
        wallet.add(3);
        System.out.println("inside=" + wallet.coins());
    }

    public static void main(String[] args) {
        Wallet mine = new Wallet(5);

        reward(mine);

        System.out.println("outside=" + mine.coins());
    }
}
```

```bash
javac MutableParameterDemo.java
java MutableParameterDemo
```

```text
inside=8
outside=8
```

At the call `reward(mine)`, the parameter `wallet` holds a **copy of the reference** mine. Both reference the **same Wallet object**, so `wallet.add(3)` changes the state of the shared object.

**What does not happen:** The method does not change the **mine variable**. Before and after, the mine variable still points to the same Wallet object.

## 9. Experiment 6 — Reassigning a Parameter Does Not Change the Caller's Reference

Create **`ParameterRebindDemo.java`**:

```java
final class Wallet {
    int coins;

    Wallet(int coins) {
        this.coins = coins;
    }
}

public class ParameterRebindDemo {
    static void replace(Wallet parameter) {
        parameter = new Wallet(999);
        System.out.println("inside=" + parameter.coins);
    }

    public static void main(String[] args) {
        Wallet mine = new Wallet(5);

        replace(mine);

        System.out.println("outside=" + mine.coins);
    }
}
```

```bash
javac ParameterRebindDemo.java
java ParameterRebindDemo
```

```text
inside=999
outside=5
```

Diagram:

```text
Before:
mine      ──┐
parameter ──┴──> Wallet(5)

Inside replace after parameter = new Wallet(999):
mine      ─────> Wallet(5)
parameter ─────> Wallet(999)
```

Changing the value of the **parameter variable** does not change the mine variable. This is direct evidence that Java does not pass the caller variable by reference.

## 10. Experiment 7 — Both Mutating and Rebinding in the Same Method

Create **`MutateThenRebindDemo.java`**:

```java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class MutateThenRebindDemo {
    static void work(Box parameter) {
        parameter.value = 10;
        parameter = new Box(20);
        parameter.value = 30;

        System.out.println("method=" + parameter.value);
    }

    public static void main(String[] args) {
        Box box = new Box(1);

        work(box);

        System.out.println("caller=" + box.value);
    }
}
```

```bash
javac MutateThenRebindDemo.java
java MutateThenRebindDemo
```

```text
method=30
caller=10
```

Execution over time:

1. Initially, both `box` and `parameter` point to object A with value 1.
2. `parameter.value = 10` modifies **A**.
3. `parameter = new Box(20)` creates **B**, switching parameter to B.
4. `parameter.value = 30` only modifies **B**.
5. The caller still points to A with value 10.

**Problem-solving rule:** Whenever you encounter the `=` sign, check whether the left-hand side is a **reference variable** or an **object field**. The two types of assignment have different effects.

## 11. Experiment 8 — A `swap` Method Does Not Swap the Caller's Variables

Beginners often try:

```java
static void swap(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}
```

This method only swaps **two local parameters**. Create the verification program **`FailedSwapDemo.java`**:

```java
public class FailedSwapDemo {
    static void swap(StringBuilder a, StringBuilder b) {
        StringBuilder temp = a;
        a = b;
        b = temp;

        System.out.println("inside=" + a + "," + b);
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");

        swap(first, second);

        System.out.println("outside=" + first + "," + second);
    }
}
```

```bash
javac FailedSwapDemo.java
java FailedSwapDemo
```

```text
inside=B,A
outside=A,B
```

The caller variables `first`/`second` are not changed. If the caller wants to swap **references**, the swap operation must happen **at the caller**, or design a mutable holder/list and swap **the elements inside the holder** via the parameter reference.

There is no standard Java syntax for a method to accept a caller's local variable as a `ref parameter` and change the value of that variable itself.

## 12. Experiment 9 — Returning a New Reference for the Caller to Explicitly Assign

Create **`ReturnNewReferenceDemo.java`**:

```java
final class Ticket {
    final String code;

    Ticket(String code) {
        this.code = code;
    }
}

public class ReturnNewReferenceDemo {
    static Ticket replace(Ticket current) {
        return new Ticket(current.code + "-NEW");
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket("T1");

        Ticket updated = replace(ticket);

        System.out.println(ticket.code);
        System.out.println(updated.code);
        System.out.println(ticket == updated);

        ticket = updated;
        System.out.println(ticket.code);
    }
}
```

```bash
javac ReturnNewReferenceDemo.java
java ReturnNewReferenceDemo
```

```text
T1
T1-NEW
false
T1-NEW
```

Instead of trying to assign the caller variable from inside the method, the method **returns a new reference**. The caller decides whether to update its local variable using `ticket = updated`.

This is a common pattern when working with immutable value objects: create a new value and return it, rather than mutating the old object.

## 13. String Is Immutable: The Difference Between "Changing a Variable" and "Changing an Object"

Create **`StringReferenceDemo.java`**:

```java
public class StringReferenceDemo {
    static void append(String parameter) {
        parameter = parameter + "!";
        System.out.println("inside=" + parameter);
    }

    public static void main(String[] args) {
        String text = "Java";

        append(text);

        System.out.println("outside=" + text);
    }
}
```

```bash
javac StringReferenceDemo.java
java StringReferenceDemo
```

```text
inside=Java!
outside=Java
```

`String` is immutable; the concatenation expression produces a different String value (which may undergo internal optimization), and the assignment only changes the parameter. There is no mutation of the original String object's state.

Compare with `StringBuilder`, a mutable object, in the next experiment.

## 14. StringBuilder: A Reference Parameter Can Modify Contents

Create **`StringBuilderParameterDemo.java`**:

```java
public class StringBuilderParameterDemo {
    static void append(StringBuilder parameter) {
        parameter.append("!");
    }

    public static void main(String[] args) {
        StringBuilder builder =
                new StringBuilder("Java");

        append(builder);

        System.out.println(builder);
    }
}
```

```bash
javac StringBuilderParameterDemo.java
java StringBuilderParameterDemo
```

```text
Java!
```

The two experiments show that the effect also depends on **whether the object has mutable methods**. The pass-by-value rule **does not change** between String and StringBuilder.

**Do not infer that Java passes immutable types by value and mutable types by reference.** All arguments are always pass-by-value, though the copied content differs: either a primitive value or a reference value.

## 15. An Array Is an Object and Can Be Shared

An array has identity. Assigning another name to an array only copies the reference, just like a class instance.

Create **`SharedArrayDemo.java`**:

```java
import java.util.Arrays;

public class SharedArrayDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = first;

        second[1] = 99;

        System.out.println(Arrays.toString(first));
        System.out.println(first == second);
    }
}
```

```bash
javac SharedArrayDemo.java
java SharedArrayDemo
```

```text
[1, 99, 3]
true
```

`first` and `second` point to the same array. Assigning `second[1]` changes an **element of the array object**, so first observes the change.

**Unlike a primitive variable:** `int x = 1; int y = x; y = 9;` only changes variable y because the primitive value is copied directly.

## 16. Arrays Are Passed by Value, Yet Elements Can Still Be Modified

Create **`ArrayParameterDemo.java`**:

```java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void work(int[] values) {
        values[0] = 8;
        values = new int[] {100, 200};

        System.out.println(
                "inside=" + Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] input = {1, 2};

        work(input);

        System.out.println(
                "outside=" + Arrays.toString(input));
    }
}
```

```bash
javac ArrayParameterDemo.java
java ArrayParameterDemo
```

```text
inside=[100, 200]
outside=[8, 2]
```

`values[0] = 8` modifies the old array that input still references. `values = new int[]{...}` switches the **local parameter** to a new array, so it does not change the input reference.

The experiment combines both rules in a single scenario and is often a more reliable check of understanding than the theoretical question "Is Java pass-by-reference or pass-by-value?".

## 17. References in a List: Container Mutation and Element Mutation

A `List<Person>` consists of two layers of objects:

1. The **List object** containing references.
2. The **Person objects** that those references point to.

Create **`ListReferenceLayersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

public class ListReferenceLayersDemo {
    public static void main(String[] args) {
        Person person = new Person("An");
        List<Person> list = new ArrayList<>();
        list.add(person);

        person.name = "Binh";
        System.out.println(list.get(0).name);

        list.set(0, new Person("Chi"));
        System.out.println(person.name);
        System.out.println(list.get(0).name);
    }
}
```

```bash
javac ListReferenceLayersDemo.java
java ListReferenceLayersDemo
```

```text
Binh
Binh
Chi
```

Initially, the list element and the person variable both point to object A. `person.name = "Binh"` mutates A, so the list observes Binh.

After `list.set(0, new Person("Chi"))`, the list element points to object B. The person variable still points to A with name Binh.

**A single line of Java can change a container entry without changing the old object.** When analyzing aliasing, draw arrows from the list slot and from the local variable separately.

## 18. Three Easily Confused Levels: Alias, Shallow Copy, Deep Copy

Suppose an `Order` has a `List<Item>` field and each `Item` has mutable state.

| Operation | New Order/container object? | New Item objects? | Impact when an Item is modified |
| --- | --- | --- | --- |
| `b = a` | No | No | Same entire object graph |
| Shallow copy of Order | Yes, depending on how it is copied | Usually no | Same Item can see changes |
| Copy List with `new ArrayList<>(list)` | New List | No | Items are still shared |
| Policy-based deep copy | New Order/List | Yes for mutable Items needing separation | Item mutations are independent within the copy scope |
| Copy when Item is immutable | List can be new | Immutable Item can be shared | No Item state mutation to propagate |

**Do not use the word "copy" alone when the API can be misleading.** Clearly define at **what level** an independent copy is desired, whether shared immutable objects are preserved, and whether alias relationships in the graph are preserved.

## 19. First Copying Experiment — Assigning a Reference Does Not Create a Copy

Create **`AssignmentIsNotCopyDemo.java`**:

```java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class AssignmentIsNotCopyDemo {
    public static void main(String[] args) {
        Box original = new Box(10);
        Box assigned = original;

        assigned.value = 20;

        System.out.println(original == assigned);
        System.out.println(original.value);
    }
}
```

```bash
javac AssignmentIsNotCopyDemo.java
java AssignmentIsNotCopyDemo
```

```text
true
20
```

The name `assigned` does not turn it into a copy. There is no second `new Box(...)`, copy constructor, or factory creating a new instance.

**Checking via identity:** For an ordinary mutable class created independently, `original == copied` should be false if it is genuinely a new object. However, `== false` alone does not prove the copy is *deep*; nested references may still be shared.

## 20. Copy Constructor: Creating a Different Top-Level Object

Create **`SimpleCopyConstructorDemo.java`**:

```java
final class Point {
    int x;
    int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    Point(Point other) {
        this(other.x, other.y);
    }
}

public class SimpleCopyConstructorDemo {
    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point copy = new Point(original);

        copy.x = 9;

        System.out.println(original == copy);
        System.out.println(original.x);
        System.out.println(copy.x);
    }
}
```

```bash
javac SimpleCopyConstructorDemo.java
java SimpleCopyConstructorDemo
```

```text
false
2
9
```

`copy` is a different object from original. Because Point only stores two primitive fields, copying the field values is sufficient for independent state. For reference fields pointing to mutable nested objects, **copying reference fields** is usually only a shallow copy; we must examine further.

## 21. Shallow Copy Experiment — Two Owners, One Mutable Child

Create **`ShallowCopyDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

final class Customer {
    String name;
    Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    Customer(Customer other) {
        this.name = other.name;
        this.address = other.address;
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = new Customer(original);

        System.out.println(original == copy);
        System.out.println(
                original.address == copy.address);

        copy.name = "Binh";
        copy.address.city = "Da Nang";

        System.out.println(original.name);
        System.out.println(original.address.city);
    }
}
```

```bash
javac ShallowCopyDemo.java
java ShallowCopyDemo
```

```text
false
true
An
Da Nang
```

Explanation:

- `new Customer(original)` creates a new Customer, so `original == copy` is false.
- `this.address = other.address` copies the **reference** to the same Address, so identity is true.
- `copy.name = "Binh"` changes the reference field of the Customer copy. Original still has name An.
- `copy.address.city = "Da Nang"` mutates the **shared Address object**, so original sees the new city.

### Shallow Copy Diagram

```text
original Customer ──address──┐
                             ├──> Address("Hue" → "Da Nang")
copy Customer ──────address──┘

original.name → "An"
copy.name     → "Binh"
```

The top-level copy is independent, but the **mutable child is not yet independent**.

## 22. Deep Copy Experiment — Recreating the Mutable Child

Create **`DeepCopyDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address other) {
        this.city = other.city;
    }
}

final class Customer {
    String name;
    Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    static Customer deepCopy(Customer other) {
        return new Customer(
                other.name,
                new Address(other.address));
    }
}

public class DeepCopyDemo {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = Customer.deepCopy(original);

        System.out.println(original == copy);
        System.out.println(
                original.address == copy.address);

        copy.address.city = "Da Nang";

        System.out.println(original.address.city);
        System.out.println(copy.address.city);
    }
}
```

```bash
javac DeepCopyDemo.java
java DeepCopyDemo
```

```text
false
false
Hue
Da Nang
```

In this example, **both the top-level Customer and the mutable Address** are copied into new objects. The name field is an immutable String, so using the same String instance does not cause state to be mutated from the copy's side.

**A deep copy does not require creating a new instance of every immutable object.** The goal is **independence with respect to the mutable components required by the contract**, not endlessly recreating every object in the graph.

## 23. A Deep Copy Must Clearly Define Its Scope

A real-world entity may contain:

- Immutable `String` name.
- Mutable `List<Line>`.
- Mutable `byte[]`.
- A `Connection` or `Socket`.
- An immutable `CustomerId` value.
- A reference to a shared service/repository.
- A reference to a parent object, creating a cycle.

You cannot simply write "deep copy = new every field" for everything:

- A file/socket/DB connection **should not be copied** as a state value.
- Shared services usually need to preserve shared identity, not be duplicated.
- Cyclic graphs need to avoid infinite recursion.
- Multiple references to the same child may need to preserve the alias topology.
- A snapshot might only need immutable value data, without entity identity.

**Contract question:** "Which changes is the copy independent from? Which shared relationships need to be preserved? Which resources do not belong to the copy?" Answer these before choosing an algorithm.

## 24. Copying a Primitive Array Using `clone()`

For a primitive array, each element is a primitive value. `clone()` creates a new array, so modifying a primitive element in the copy does not affect the original.

Create **`PrimitiveArrayCloneDemo.java`**:

```java
import java.util.Arrays;

public class PrimitiveArrayCloneDemo {
    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        int[] copy = original.clone();

        copy[0] = 99;

        System.out.println(original == copy);
        System.out.println(Arrays.toString(original));
        System.out.println(Arrays.toString(copy));
    }
}
```

```bash
javac PrimitiveArrayCloneDemo.java
java PrimitiveArrayCloneDemo
```

```text
false
[1, 2, 3]
[99, 2, 3]
```

The array instances are different. For `int[]`, copying the primitive elements is sufficient to make the contents independent. You can use `Arrays.copyOf(original, original.length)`, `System.arraycopy` into a new array, or `clone()` depending on the context.

**Do not assume that every array clone is a deep copy** — an array of object references behaves differently.

## 25. An Object Array Clone Still Shares Elements

Create **`ObjectArrayCloneDemo.java`**:

```java
final class Item {
    String label;

    Item(String label) {
        this.label = label;
    }
}

public class ObjectArrayCloneDemo {
    public static void main(String[] args) {
        Item[] original = {
                new Item("A"),
                new Item("B")
        };
        Item[] copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original[0] == copy[0]);

        copy[0].label = "X";
        System.out.println(original[0].label);

        copy[0] = new Item("Y");
        System.out.println(original[0].label);
        System.out.println(copy[0].label);
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
X
X
Y
```

`original` and `copy` are **two arrays**. However, slot 0 initially holds a reference to the **same Item**. Thus `copy[0].label = "X"` mutates the shared Item. After `copy[0] = new Item("Y")`, only slot 0 of the copy array changes its reference; the original slot still points to the Item with label X.

**Look at the two layers:** changing an element field (object mutation) differs from changing an array slot (container mutation).

## 26. Multidimensional Arrays Are Arrays of Arrays

With `int[][]`, each row is also an array object. Calling `clone()` on the outer array only copies the **row references**, not the inner arrays.

Create **`TwoDimensionalArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class TwoDimensionalArrayCopyDemo {
    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3, 4}
        };
        int[][] shallow = original.clone();

        shallow[0][0] = 99;

        System.out.println(original == shallow);
        System.out.println(original[0] == shallow[0]);
        System.out.println(Arrays.deepToString(original));
    }
}
```

```bash
javac TwoDimensionalArrayCopyDemo.java
java TwoDimensionalArrayCopyDemo
```

```text
false
true
[[99, 2], [3, 4]]
```

Deep-copying a simple two-dimensional array structure requires copying **each row**; if the rows contain mutable object references, those elements also need to be copied according to policy.

## 27. Copying Each Row to Separate a Primitive Two-Dimensional Array

Create **`DeepPrimitiveMatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class DeepPrimitiveMatrixCopyDemo {
    static int[][] copyMatrix(int[][] source) {
        int[][] copy = new int[source.length][];

        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3, 4}
        };
        int[][] copy = copyMatrix(original);

        copy[0][0] = 99;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
        System.out.println(original[0] == copy[0]);
    }
}
```

```bash
javac DeepPrimitiveMatrixCopyDemo.java
java DeepPrimitiveMatrixCopyDemo
```

```text
[[1, 2], [3, 4]]
[[99, 2], [3, 4]]
false
```

The example assumes **every row is non-null**. For a jagged array with null rows, you must check before cloning. This produces an independent copy for primitive rows, though if two positions in the outer source point to **the same row**, this algorithm **does not preserve alias topology** because each position clones separately. This will be discussed in the graph section.

## 28. `new ArrayList<>(old)` Creates a New Container, Does Not Deep-Copy Elements

Create **`ListShallowCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Item {
    String name;

    Item(String name) {
        this.name = name;
    }
}

public class ListShallowCopyDemo {
    public static void main(String[] args) {
        List<Item> original = new ArrayList<>();
        original.add(new Item("Pen"));

        List<Item> copy = new ArrayList<>(original);

        System.out.println(original == copy);
        System.out.println(original.get(0) == copy.get(0));

        copy.get(0).name = "Pencil";
        System.out.println(original.get(0).name);

        copy.add(new Item("Book"));
        System.out.println(original.size());
        System.out.println(copy.size());
    }
}
```

```bash
javac ListShallowCopyDemo.java
java ListShallowCopyDemo
```

```text
false
true
Pencil
1
2
```

- **Container copy:** the new list can add/remove independently.
- **Element sharing:** the original mutable Item still has the same identity.
- `copy.add(...)` does not cause the original list to gain an element because the containers are separate.
- `copy.get(0).name = ...` causes original to observe the mutation because the Item is shared.

### When Is a Shallow List Copy Enough?

If the elements are Strings, enums, or value objects whose state is genuinely immutable, sharing elements can be safe. If the elements are mutable and the API promises an independent snapshot, you must copy the elements or convert to an immutable snapshot representation.

## 29. `List.copyOf` Differs from `new ArrayList<>(...)`

`List.copyOf(source)` returns an **unmodifiable list**, rejects null elements, and creates a snapshot of the sequence at the time of the call per the API. It **does not deep-copy mutable elements**.

Create **`ListCopyOfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Cell {
    int value;

    Cell(int value) {
        this.value = value;
    }
}

public class ListCopyOfDemo {
    public static void main(String[] args) {
        Cell cell = new Cell(1);
        List<Cell> source = new ArrayList<>();
        source.add(cell);

        List<Cell> snapshot = List.copyOf(source);

        source.add(new Cell(2));
        cell.value = 9;

        System.out.println(source.size());
        System.out.println(snapshot.size());
        System.out.println(snapshot.get(0).value);

        try {
            snapshot.add(new Cell(3));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac ListCopyOfDemo.java
java ListCopyOfDemo
```

```text
2
1
9
unmodifiable
```

The snapshot does not change when source adds an element. However, the snapshot still holds a reference to the Cell that was mutated from 1 to 9.

**The term "unmodifiable"** refers to the mutation API of the **list structure**; it does not make Cell immutable. Do not confuse this with a **deeply immutable object graph**.

## 30. `Collections.unmodifiableList` Is a View, Not an Independent Snapshot

Create **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        mutable.add("A");

        List<String> view =
                Collections.unmodifiableList(mutable);

        mutable.add("B");

        System.out.println(view.size());
        System.out.println(view.get(1));

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add through view");
        }
    }
}
```

```bash
javac UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

```text
2
B
cannot add through view
```

`view` does not allow adding through the view itself, yet it **reflects structural changes** from the mutable backing list.

Distinguish:

- `new ArrayList<>(source)` → separate mutable container, shared elements.
- `List.copyOf(source)` → unmodifiable snapshot container, shared elements; the implementation **may reuse** a source that is already suitably unmodifiable, so it does not guarantee `!=`.
- `Collections.unmodifiableList(source)` → unmodifiable **view** over source, reflecting changes to the backing list.

Choose based on the contract of the class owning the collection.

## 31. `subList` Is a View: Sharing the Backing List

Create **`SubListViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListViewDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C"));

        List<String> view = source.subList(1, 3);

        view.set(0, "X");

        System.out.println(source);
        System.out.println(view);
    }
}
```

```bash
javac SubListViewDemo.java
java SubListViewDemo
```

```text
[A, X, C]
[X, C]
```

`subList` typically returns a view over the backing list. `view.set(0, "X")` causes `source[1]` to change.

**Limitation:** Direct structural modifications on the backing list outside the view can cause the semantics of subList to become undefined according to the API; do not put them into examples that mechanically predict output. If you need an independent snapshot of the data slice, use `new ArrayList<>(source.subList(...))` or `List.copyOf(...)` depending on mutation rights, and additionally check whether the elements are mutable.

## 32. Copying a Map Also Has Two Layers

`new HashMap<>(old)` creates a new Map structure but does not create copies of mutable key/value objects.

Create **`MapShallowCopyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class Detail {
    int score;

    Detail(int score) {
        this.score = score;
    }
}

public class MapShallowCopyDemo {
    public static void main(String[] args) {
        Map<String, Detail> original = new HashMap<>();
        original.put("A", new Detail(1));

        Map<String, Detail> copy =
                new HashMap<>(original);

        copy.get("A").score = 7;

        System.out.println(original.get("A").score);
        System.out.println(original == copy);

        copy.remove("A");
        System.out.println(original.containsKey("A"));
    }
}
```

```bash
javac MapShallowCopyDemo.java
java MapShallowCopyDemo
```

```text
7
false
true
```

The Map containers are two objects, but the Detail value is shared. Removing an entry from copy does not remove the entry from original.

**Note on keys:** Mutable keys whose fields affecting `equals/hashCode` are changed can cause a Map/Set to behave incorrectly even without any copying. Designing immutable keys is a good priority for these kinds of APIs.

## 33. Records Do Not Automatically Deep-Copy Mutable Components

Records are well-suited as value-oriented data carriers, yet a record component of type `int[]` is still a reference to a mutable array.

Create **`RecordArraySharingDemo.java`**:

```java
import java.util.Arrays;

record Scores(int[] values) {
}

public class RecordArraySharingDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Scores scores = new Scores(input);

        input[0] = 9;
        System.out.println(
                Arrays.toString(scores.values()));

        scores.values()[1] = 8;
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac RecordArraySharingDemo.java
java RecordArraySharingDemo
```

```text
[9, 2]
[9, 8]
```

Record fields are assigned once, but `values` is a reference to a **mutable array**. A final reference does not make the array immutable. The compiler-generated accessor returns the same reference unless overridden. This is an **aliasing leak**, even though the record looks concise and has `final` fields.

### Equality of a Record Containing an Array

A record's generated `equals()` compares components according to record rules; for an array component, equality is **reference equality**, not deep contents. If value equality by elements is needed, you must design `equals/hashCode` consistently yourself, or choose an appropriate immutable representation.

## 34. Defensive Copying in a Record Constructor and Accessor

Create **`DefensiveRecordDemo.java`**:

```java
import java.util.Arrays;

record Scores(int[] values) {
    Scores {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    int sum() {
        int result = 0;
        for (int value : values) {
            result = Math.addExact(result, value);
        }
        return result;
    }
}

public class DefensiveRecordDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Scores scores = new Scores(input);

        input[0] = 9;
        int[] leaked = scores.values();
        leaked[1] = 8;

        System.out.println(scores.sum());
        System.out.println(
                Arrays.toString(scores.values()));
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac DefensiveRecordDemo.java
java DefensiveRecordDemo
```

```text
3
[1, 2]
[9, 2]
```

In the compact constructor, assigning `values = values.clone()` updates the formal parameter, and then the compiler assigns it to the corresponding record field after the compact constructor body according to Java rules. Overriding the accessor returns a copy so the caller cannot obtain the internal array and modify it.

**What remains unfixed:** If the generated `equals/hashCode` are used, the array component still has reference semantics. Defensive copies protect against mutation; they **do not automatically turn generated record equality into Arrays.equals**.

### When Content-Based equals/hashCode Is Needed

One approach is to use an immutable `List<Integer>` representation when the domain permits, or override `equals/hashCode` yourself based on `Arrays.equals/hashCode` while complying with the contract. Remember to keep both methods consistent if the record is used as a Map key.

## 35. Choosing an Immutable Representation Is Much Easier Than Manual Deep Copying

Create **`ImmutableSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record InvoiceSnapshot(List<String> items) {
    InvoiceSnapshot {
        items = List.copyOf(items);
    }
}

public class ImmutableSnapshotDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("Pen"));

        InvoiceSnapshot snapshot =
                new InvoiceSnapshot(source);

        source.add("Book");

        System.out.println(source.size());
        System.out.println(snapshot.items());
    }
}
```

```bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
```

```text
2
[Pen]
```

`String` is immutable and `List.copyOf` returns an unmodifiable snapshot, so the example creates a stable value snapshot structure. If items is a `List<MutableItem>`, `List.copyOf` is still shallow with respect to elements; the Item itself can be mutated.

**Design lesson:** Before writing deep-copy machinery, try choosing **immutable value objects and unmodifiable snapshots**. That reduces the number of aliasing paths that need to be managed.

## 36. Defensive Copy Constructor on Input and Output

A class holding a mutable array needs to control two boundaries:

1. **Constructor receiving an array**: if it stores the input directly, the caller can still modify the array.
2. **Getter returning an array**: if it returns the internal array directly, the caller can mutate the state.

Create **`DefensiveCopyClassDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Histogram {
    private final int[] buckets;

    Histogram(int[] buckets) {
        this.buckets =
                Objects.requireNonNull(buckets).clone();
    }

    Histogram(Histogram other) {
        this(other.buckets);
    }

    int[] buckets() {
        return buckets.clone();
    }

    int total() {
        int total = 0;
        for (int bucket : buckets) {
            total = Math.addExact(total, bucket);
        }
        return total;
    }
}

public class DefensiveCopyClassDemo {
    public static void main(String[] args) {
        int[] data = {2, 3};
        Histogram original = new Histogram(data);
        Histogram copy = new Histogram(original);

        data[0] = 100;
        int[] output = copy.buckets();
        output[1] = 99;

        System.out.println(original.total());
        System.out.println(copy.total());
        System.out.println(
                Arrays.toString(copy.buckets()));
    }
}
```

```bash
javac DefensiveCopyClassDemo.java
java DefensiveCopyClassDemo
```

```text
5
5
[2, 3]
```

The input array and output array are **not** aliases of the private buckets field. `Histogram(Histogram)` also creates its own array. This is an example with **clear copy semantics**.

**Note:** Defensive cloning is only shallow if the array contains mutable reference elements. `int[]` is primitive, so copying all elements is sufficient for this structure.

## 37. List of Mutable Children: Copying the Structure Is Not Enough

Create **`NestedListCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Task {
    String status;

    Task(String status) {
        this.status = status;
    }

    Task(Task source) {
        this.status = source.status;
    }
}

public class NestedListCopyDemo {
    static List<Task> copyTasks(List<Task> source) {
        List<Task> copied = new ArrayList<>();
        for (Task task : source) {
            copied.add(new Task(task));
        }
        return copied;
    }

    public static void main(String[] args) {
        List<Task> original = new ArrayList<>();
        original.add(new Task("NEW"));

        List<Task> copy = copyTasks(original);
        copy.get(0).status = "DONE";

        System.out.println(original.get(0).status);
        System.out.println(copy.get(0).status);
        System.out.println(
                original.get(0) == copy.get(0));
    }
}
```

```bash
javac NestedListCopyDemo.java
java NestedListCopyDemo
```

```text
NEW
DONE
false
```

`copyTasks` creates a new list **and** creates a new Task for each element. The status field is an immutable String, so copying the reference is sufficient.

### Cost

With many objects, deep copying increases allocations, CPU time, and memory footprint. Copy only the data that needs to be independent; do not deep-copy reflexively if shared immutable data or the ownership contract is already safe.

## 38. Alias Topology: Two Fields Pointing to the Same Child

A deep-copy routine can accidentally **break sharing relationships** inside the original graph.

Example:

```text
Original:
a ──────┐
        ├──> Child X
b ──────┘
```

If each field is cloned separately:

```text
Copied:
a ──────> Child X1
b ──────> Child X2
```

Now `copied.a == copied.b` is false, whereas original.a == original.b is true. If it matters in the domain that both fields refer to the exact same node (for example, a graph, owner-reference, or shared vertex), this copy **does not preserve semantics**.

A deep copy needs to determine **whether to preserve alias relations in the copy**. In graph cloning, a map from original identity to copied identity is typically required.

## 39. Experiment on Preserving Aliases in Deep-Copying a Cyclic Graph

Create **`CyclicGraphCopyDemo.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    String name;
    Node next;
    Node shared;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicGraphCopyDemo {
    static Node deepCopy(
            Node original, Map<Node, Node> copies) {
        if (original == null) {
            return null;
        }

        Node cached = copies.get(original);
        if (cached != null) {
            return cached;
        }

        Node copy = new Node(original.name);
        copies.put(original, copy);

        copy.next = deepCopy(original.next, copies);
        copy.shared = deepCopy(original.shared, copies);
        return copy;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;
        a.shared = b;

        Node copied = deepCopy(
                a, new IdentityHashMap<>());

        System.out.println(a == copied);
        System.out.println(a.next == copied.next);
        System.out.println(copied.next.next == copied);
        System.out.println(copied.next == copied.shared);

        copied.next.name = "B2";
        System.out.println(b.name);
        System.out.println(copied.next.name);
    }
}
```

```bash
javac CyclicGraphCopyDemo.java
java CyclicGraphCopyDemo
```

```text
false
false
true
true
B
B2
```

**Why use `IdentityHashMap`?** Graph copying must distinguish **object identity**, not merge two nodes simply because `equals()` is true. The map stores each original object → exactly one copied object.

**Why put before recursing?** When encountering the cycle a → b → a, the recursive call back to a will find the already stored copy; if not stored early, recursion can become infinite.

**Limitations:** This is a single-threaded illustrative graph copy; it does not handle concurrency, subclass types, custom resources, or extremely deep graphs that can cause a stack overflow. In a real system, the graph model and copy contract must be clearly specified.

## 40. `Object.clone()`: Shallow by Default with Many Constraints

`Object.clone()` is a protected method. Normally a class must implement `Cloneable` and override/publicize the method if it wants to expose a clone API to callers. The default implementation creates a **field-wise shallow copy** of the object; it does not invoke a copy constructor to clone nested children.

Create **`ShallowObjectCloneDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

final class Member implements Cloneable {
    String name;
    Address address;

    Member(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    @Override
    public Member clone() {
        try {
            return (Member) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class ShallowObjectCloneDemo {
    public static void main(String[] args) {
        Member original =
                new Member("An", new Address("Hue"));
        Member copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original.address == copy.address);

        copy.address.city = "Da Nang";
        System.out.println(original.address.city);
    }
}
```

```bash
javac ShallowObjectCloneDemo.java
java ShallowObjectCloneDemo
```

```text
false
true
Da Nang
```

**Key points:**

- The Member copy is different from original.
- Address still has the same identity because `super.clone()` copies the reference field.
- If a class does not implement Cloneable and calls `super.clone()`, it will normally encounter `CloneNotSupportedException`.
- `Cloneable` is a marker interface; by itself it does not declare a public `clone()` method.
- Do not assume Object.clone is a deep clone by default.
- With final/reference fields containing mutable objects, designing clone can be complex.

In many domain applications, a **copy constructor or a static factory with a name describing the contract** is often easier to read and validate than `Cloneable`.

## 41. Testing Array Clone and Object Clone: Same Name, Different Details

Array types in Java support public `clone()` and the result has the exact array type, yet:

- `int[].clone()` → copies primitive values, usually independent enough in terms of contents.
- `Item[].clone()` → copies reference elements; the Item objects are still shared.
- `int[][].clone()` → copies outer references; the inner arrays are still shared.

For a class implementing `Cloneable`, calling `super.clone()` also creates a shallow copy by fields.

**Do not use the word "clone" as proof of the copy depth.** You must examine the **component types and implementation**, not just the method name.

## 42. Copying via Serialization: Consider It, but Do Not Treat It as the Default

Some designs serialize an object graph and then deserialize it to obtain a copy. This approach can separate state according to representation, but it is not a guaranteed deep-copy primitive for every Java object:

- Every component must be compatible with the serialization mechanism.
- `transient` fields can be lost.
- Object identity/aliases follow the serialization mechanism's own rules.
- It can be expensive in CPU/memory.
- Constructors, validation, and security boundaries have special semantics.
- It is not a sensible strategy for connections, locks, threads, or external handles.
- Native Java serialization has many security issues when reading untrusted data.

**Practical recommendation:** Use a copy constructor/factory with a clear contract, immutable snapshots, or DTO mapping; only use serialization-based copying if the domain, security, and performance permit.

## 43. Equality `equals()` Differs from Identity `==`

Two objects can carry the same values yet have different identities.

Create **`EqualityVersusIdentityDemo.java`**:

```java
record Point(int x, int y) {
}

public class EqualityVersusIdentityDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
    }
}
```

```bash
javac EqualityVersusIdentityDemo.java
java EqualityVersusIdentityDemo
```

```text
false
true
true
```

`equals` returns true for two Point records with the same component values. `==` returns false between first and second because they are distinct objects. Alias is true because it is the same reference.

**When verifying deep-copy correctness**, both questions are needed:

1. Does the copy preserve value semantics?
2. Do the mutable objects that need to be independent have distinct identities?

Testing only `original.equals(copy)` can miss aliasing that causes a mutation leak.

## 44. Records Containing an Array: `equals` Can Be Surprising

Create **`RecordArrayEqualityDemo.java`**:

```java
record PackageData(int[] numbers) {
}

public class RecordArrayEqualityDemo {
    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};

        PackageData first = new PackageData(a);
        PackageData second = new PackageData(b);
        PackageData shared = new PackageData(a);

        System.out.println(first.equals(second));
        System.out.println(first.equals(shared));
    }
}
```

```bash
javac RecordArrayEqualityDemo.java
java RecordArrayEqualityDemo
```

```text
false
true
```

The two arrays a/b have the same contents but different identities; generated record equals handles the array component using reference equality. `first.equals(shared)` is true because it is the same array reference.

If the domain wants to compare array contents, you need a content-based representation or equals/hashCode method. **Do not assume** a record generates deep equals for nested arrays.

## 45. Pass-by-Value Does Not Guarantee Thread Safety

If two threads hold references to the same mutable object, pass-by-value does not prevent races. For example, `counter.value++` is not automatically atomic just because the reference value was copied when handed to another thread.

**Separate three design axes:**

- **Reference aliasing:** is the same object shared?
- **Mutability/ownership:** who is allowed to modify state?
- **Concurrency:** if multiple threads access it, are synchronization/happens-before and atomicity correct?

If a class needs concurrent shared mutable state, consider synchronization, locks, atomic types, or immutable messages according to the Java Memory Model. Copying an object into a snapshot can reduce sharing, but it does not solve all atomicity/visibility problems if the snapshot is created while the source is being modified without synchronization.

## 46. Simple Synchronization Experiment with a Shared AtomicInteger

Create **`SharedAtomicReferenceDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedAtomicReferenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(0);
        AtomicInteger alias = counter;

        Thread worker = new Thread(alias::incrementAndGet);
        worker.start();
        worker.join();

        System.out.println(counter == alias);
        System.out.println(counter.get());
    }
}
```

```bash
javac SharedAtomicReferenceDemo.java
java SharedAtomicReferenceDemo
```

```text
true
1
```

Both variables point to the same AtomicInteger. The worker calls an atomic increment; `join` waits for the work to complete, making the output deterministic. This illustrates aliasing in a concurrent scenario without a data race.

**Do not misinterpret the reverse:** `AtomicInteger` guarantees atomic operations per its contract, but it does **not** make every multi-step operation on other objects atomic.

## 47. API Design: Sharing a Reference Is a Public Decision

When a class receives a list/array, make an explicit decision:

| API contract | Common approach | Risks/characteristics |
| --- | --- | --- |
| Intentional shared mutable state | Store the same reference | External mutations affect the owner |
| Primitive array input snapshot | `input.clone()` | Separates array contents |
| Immutable-elements input snapshot | `List.copyOf(input)` | List snapshot; elements can be shared |
| Mutable-elements input snapshot | Copy each mutable element | Additional allocation; requires a deep policy |
| Live read-only view | `Collections.unmodifiableList(backing)` | Reflects backing changes |
| Return mutable independent copy | `new ArrayList<>(internal)` | Caller modifies its own structure; elements are shared |
| Return array safely | `internal.clone()` | With nested mutable elements, further handling is needed |
| Shared immutable value object | Return the same object | Safe if genuinely immutable and the contract fits |

An API does not have a single right choice for every situation. What matters is to **document and protect the appropriate invariant**.

## 48. Flawed API Design Experiment: Storing the Input Array Directly

Create **`LeakyArrayOwnerDemo.java`**:

```java
final class Settings {
    private final int[] limits;

    Settings(int[] limits) {
        this.limits = limits;
    }

    int firstLimit() {
        return limits[0];
    }
}

public class LeakyArrayOwnerDemo {
    public static void main(String[] args) {
        int[] input = {10};
        Settings settings = new Settings(input);

        input[0] = 99;

        System.out.println(settings.firstLimit());
    }
}
```

```bash
javac LeakyArrayOwnerDemo.java
java LeakyArrayOwnerDemo
```

```text
99
```

`final` only forbids reassigning the `limits` field reference; it does not forbid changing the array elements. The caller still holds the input reference, so it can mutate Settings' internal state without the class controlling it.

If Settings is responsible for maintaining an immutable snapshot, the constructor should clone the input and the accessor (if any) should also copy the output. If Settings **intentionally** shares a live configuration array, the design must clearly state the ownership/concurrency contract.

## 49. Fix Experiment: Input Copy, Output Copy, Mutation Test

Create **`SafeArrayOwnerDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Settings {
    private final int[] limits;

    Settings(int[] limits) {
        this.limits =
                Objects.requireNonNull(limits).clone();
    }

    int[] limits() {
        return limits.clone();
    }
}

public class SafeArrayOwnerDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Settings settings = new Settings(input);

        input[0] = 99;
        int[] received = settings.limits();
        received[1] = 77;

        System.out.println(
                Arrays.toString(settings.limits()));
        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(received));
    }
}
```

```bash
javac SafeArrayOwnerDemo.java
java SafeArrayOwnerDemo
```

```text
[10, 20]
[99, 20]
[10, 77]
```

Settings keeps its own array; both input and output are distinct arrays. External mutations do not affect the private limits.

**Essence:** Defensive copying is a way to enforce an **ownership boundary**, not merely a Java syntax technique.

## 50. Copying Cost: Do Not Copy "the Whole World"

Copying can:

- Create new allocations and increase GC pressure.
- Consume extra heap if the graph is large.
- Require handling cycles and aliases.
- Lose the meaning of entity identity.
- Produce an inconsistent snapshot if a mutable source is modified concurrently.
- Alter resource ownership/transaction semantics if handles are copied by mistake.
- Cause performance issues when copying repeatedly in a large loop.

### Options to Consider

1. **Immutable values:** Safe sharing, reduced copying.
2. **Defensive copy at the boundary:** Separate data only where ownership is transferred.
3. **Copy-on-write:** Copy only when mutation is needed according to an appropriate design.
4. **Persistent immutable collections:** Controlled sharing of immutable structures.
5. **DTO snapshots:** Copy only the data that needs to be published/recorded.
6. **Explicit mutable ownership:** Allow rule-governed sharing if genuinely needed.

**Do not deep-copy a connection, thread, lock, or service singleton like business data.** They have their own lifecycle and identity.

## 51. Timeline Experiment: Predict Then Verify Each Statement

Create **`ReferenceTimelineDemo.java`**:

```java
final class Data {
    int count;

    Data(int count) {
        this.count = count;
    }
}

public class ReferenceTimelineDemo {
    static void process(Data value) {
        value.count += 2;
        value = new Data(50);
        value.count++;
        System.out.println("process=" + value.count);
    }

    public static void main(String[] args) {
        Data a = new Data(3);
        Data b = a;
        process(b);

        System.out.println("a=" + a.count);

        b = new Data(8);
        b.count += 2;

        System.out.println("a=" + a.count);
        System.out.println("b=" + b.count);
        System.out.println("shared=" + (a == b));
    }
}
```

```bash
javac ReferenceTimelineDemo.java
java ReferenceTimelineDemo
```

```text
process=51
a=5
a=5
b=10
shared=false
```

Reasoning steps:

1. a/b both point to Data(3).
2. Method process receives a copy of reference b.
3. `value.count += 2` modifies object A to 5.
4. `value = new Data(50)` switches the parameter to a new object C.
5. `value.count++` makes C become 51.
6. Caller a/b still point to A(5).
7. `b = new Data(8)` switches caller variable b to a new object B; a is still A.
8. `b.count += 2` makes B become 10.
9. a != b because their identities differ.

If you can explain this example without relying on the claim "Java passes by reference", you have grasped the exact model.

## 52. Experiment Comparing Three Copy Modes from the Same Source

Create **`ThreeCopyModesDemo.java`**:

```java
final class Detail {
    int score;

    Detail(int score) {
        this.score = score;
    }

    Detail(Detail source) {
        this.score = source.score;
    }
}

final class Report {
    String label;
    Detail detail;

    Report(String label, Detail detail) {
        this.label = label;
        this.detail = detail;
    }

    static Report shallow(Report source) {
        return new Report(source.label, source.detail);
    }

    static Report deep(Report source) {
        return new Report(
                source.label, new Detail(source.detail));
    }
}

public class ThreeCopyModesDemo {
    public static void main(String[] args) {
        Report original =
                new Report("A", new Detail(1));
        Report alias = original;
        Report shallow = Report.shallow(original);
        Report deep = Report.deep(original);

        System.out.println(original == alias);
        System.out.println(original == shallow);
        System.out.println(original.detail == shallow.detail);
        System.out.println(original.detail == deep.detail);

        alias.label = "B";
        shallow.detail.score = 9;
        deep.detail.score = 7;

        System.out.println(original.label);
        System.out.println(original.detail.score);
        System.out.println(deep.detail.score);
    }
}
```

```bash
javac ThreeCopyModesDemo.java
java ThreeCopyModesDemo
```

```text
true
false
true
false
B
9
7
```

- **Alias:** same Report; changing label through alias changes original.
- **Shallow:** new Report but shared Detail; changing score through shallow affects original.
- **Deep within the scope of Detail:** both Report and Detail are new; changing score through deep does not affect original.

This is the most suitable composite example for contrasting the three concepts before using a library's copy API.

## 53. Self-Test 1 — Java Is Always Pass-by-Value

Create **`PassByValueSelfTest.java`**:

```java
final class Holder {
    int value;

    Holder(int value) {
        this.value = value;
    }
}

public class PassByValueSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void change(int primitive, Holder reference) {
        primitive = 99;
        reference.value = 7;
        reference = new Holder(100);

        check(primitive == 99, "local primitive");
        check(reference.value == 100, "local reference");
    }

    public static void main(String[] args) {
        int number = 1;
        Holder object = new Holder(2);

        change(number, object);

        check(number == 1, "caller primitive unchanged");
        check(object.value == 7, "shared object changed");

        System.out.println("pass-by-value PASS");
    }
}
```

```bash
javac PassByValueSelfTest.java
java PassByValueSelfTest
```

```text
pass-by-value PASS
```

The test simultaneously confirms: the primitive variable at the caller does not change, rebinding the reference parameter does not change the caller's reference, and the shared object is mutated through the parameter.

`check` throws AssertionError directly, without needing to enable JVM `-ea`.

## 54. Self-Test 2 — Shallow Copy and Deep Copy

Create **`CopySemanticsSelfTest.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address other) {
        city = other.city;
    }
}

final class Person {
    Address address;

    Person(Address address) {
        this.address = address;
    }

    static Person shallow(Person other) {
        return new Person(other.address);
    }

    static Person deep(Person other) {
        return new Person(new Address(other.address));
    }
}

public class CopySemanticsSelfTest {
    static void check(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Person original = new Person(new Address("Hue"));
        Person shallow = Person.shallow(original);
        Person deep = Person.deep(original);

        check(original != shallow, "shallow parent new");
        check(original.address == shallow.address,
                "shallow child shared");
        check(original != deep, "deep parent new");
        check(original.address != deep.address,
                "deep child independent");

        shallow.address.city = "Da Nang";
        check(original.address.city.equals("Da Nang"),
                "shallow mutation visible");

        deep.address.city = "Ha Noi";
        check(original.address.city.equals("Da Nang"),
                "deep mutation isolated");

        System.out.println("copy semantics PASS");
    }
}
```

```bash
javac CopySemanticsSelfTest.java
java CopySemanticsSelfTest
```

```text
copy semantics PASS
```

The self-test does not rely on GC or memory addresses. It verifies deterministic **identities and behaviors**. The deep copy is defined clearly enough for the small object graph here.

## 55. Self-Test 3 — Not Leaking a Mutable Array Through Constructor/Accessor

Create **`DefensiveCopySelfTest.java`**:

```java
import java.util.Arrays;

final class ImmutableScores {
    private final int[] scores;

    ImmutableScores(int[] scores) {
        this.scores = scores.clone();
    }

    int[] scores() {
        return scores.clone();
    }
}

public class DefensiveCopySelfTest {
    static void check(boolean value, String label) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        ImmutableScores holder = new ImmutableScores(input);

        input[0] = 99;
        int[] exposed = holder.scores();
        exposed[1] = 88;

        check(Arrays.equals(
                holder.scores(), new int[] {1, 2, 3}),
                "snapshot unchanged");

        System.out.println("defensive copy PASS");
    }
}
```

```bash
javac DefensiveCopySelfTest.java
java DefensiveCopySelfTest
```

```text
defensive copy PASS
```

The test uses `Arrays.equals` because it cares about the **contents** of the primitive arrays. Using `==` here would only check identity, not whether the three values are preserved.

## 56. Exercise 1 — Predict Reference Identity and Output

Given the program:

```java
final class Box {
    int n;

    Box(int n) {
        this.n = n;
    }
}

public class ExerciseOne {
    public static void main(String[] args) {
        Box a = new Box(1);
        Box b = a;
        Box c = new Box(1);

        b.n = 5;

        System.out.println(a.n);
        System.out.println(a == b);
        System.out.println(a == c);
    }
}
```

Save as **`ExerciseOne.java`**.

```bash
javac ExerciseOne.java
java ExerciseOne
```

```text
5
true
false
```

**Solution:** a/b both point to the first object; c is a different object even though the initial n is the same. Modifying through b makes a.n = 5.

## 57. Exercise 2 — Predict Array Parameter Rebinding

Save as **`ExerciseTwo.java`**:

```java
import java.util.Arrays;

public class ExerciseTwo {
    static void update(int[] values) {
        values[0] = 10;
        values = new int[] {20};
        System.out.println(Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] source = {1};
        update(source);
        System.out.println(Arrays.toString(source));
    }
}
```

```bash
javac ExerciseTwo.java
java ExerciseTwo
```

```text
[20]
[10]
```

**Solution:** The first operation mutates the shared array; assigning the parameter to a new array does not change the source reference at the caller.

## 58. Exercise 3 — Add a Copy Method for a List with Mutable Elements

Requirement: you have a `List<Task>`; each Task contains `String name` and mutable `int progress`. Write a method that returns an **independent list and independent Task objects**.

A runnable solution is **`ExerciseThree.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Task {
    String name;
    int progress;

    Task(String name, int progress) {
        this.name = name;
        this.progress = progress;
    }

    Task(Task source) {
        this(source.name, source.progress);
    }
}

public class ExerciseThree {
    static List<Task> deepCopy(List<Task> input) {
        List<Task> result = new ArrayList<>();

        for (Task task : input) {
            result.add(new Task(task));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Task> original =
                new ArrayList<>(List.of(new Task("A", 10)));

        List<Task> copied = deepCopy(original);
        copied.get(0).progress = 99;

        System.out.println(original.get(0).progress);
        System.out.println(copied.get(0).progress);
    }
}
```

```bash
javac ExerciseThree.java
java ExerciseThree
```

```text
10
99
```

**Limitations:** If the input list allows null elements, the example must define a policy for null before calling `new Task(task)`. If Task holds references to other mutable children, the copy constructor needs to be extended according to the contract.

## 59. Exercise 4 — Fix a Record with a Mutable Array

Given:

```java
record Palette(int[] rgb) {
}
```

The caller can modify `rgb` after the constructor or retrieve `palette.rgb()` and modify its contents. Requirement: keep a primitive array snapshot, validate for exactly three channels, and prevent modifying state through the accessor.

A solution:

```java
record Palette(int[] rgb) {
    Palette {
        if (rgb == null || rgb.length != 3) {
            throw new IllegalArgumentException("RGB length");
        }
        rgb = rgb.clone();
    }

    @Override
    public int[] rgb() {
        return rgb.clone();
    }
}
```

This is an **illustrative declaration snippet**; the two versions of Palette are before/after options **not declared in the same compilation unit**.

**Further:** Do the channels need to be in [0,255]? If so, validation is Palette's responsibility. Is equality needed by RGB content or by identity? If needed, override equals/hashCode correspondingly with Arrays.equals/Arrays.hashCode. Do not implicitly assume defensive copying automatically changes generated record equality.

## 60. Exercise 5 — Build a Graph Copy That Preserves Cycles

Given nodes A → B → A, copy them such that:

- A copy is different from A original.
- B copy is different from B original.
- A copy.next points to B copy.
- B copy.next points to A copy.
- If two references in source both point to B, the corresponding two references in copy must both point to B copy.

**Hint:** `IdentityHashMap<OriginalNode, CopiedNode>`, check the map first; create the copy and put it into the map **before** recursively copying children. The `CyclicGraphCopyDemo` experiment provides a complete runnable solution.

**Do not use HashMap just for convenience** if the nodes' equals could merge two instances with the same contents but different identities.

## 61. Common Mistakes

| Incorrect statement or code | Problem | Correct understanding/fix |
| --- | --- | --- |
| "Java pass-by-reference" | Parameter does not alias the caller variable | Java is pass-by-value of the reference value |
| `b = a` copies the object | Only copies the reference | Use new/copy constructor/factory |
| Mutating a parameter means changing the caller variable | Mutates the object, does not change the caller variable | Distinguish `p.field` and `p =` |
| Assigning parameter to a new object changes caller | Rebinds the local parameter | Return a new reference; caller explicitly assigns it |
| `swap(a,b)` swaps caller variables | Only swaps local params | Swap at the caller or via a mutable holder |
| An array is a primitive | An array is an object | Arrays have identity and can be aliased |
| `array.clone()` is always deep | Reference elements are still shared | Copy nested mutable elements if needed |
| `new ArrayList<>(old)` deep-copies | Only copies the structure | Copy element objects appropriately |
| `List.copyOf` makes elements immutable | Unmodifiable structure, shallow elements | Use immutable elements or deep snapshots |
| An unmodifiable view is a snapshot | View reflects backing updates | Use `List.copyOf`/copy the container |
| A `record` containing `int[]` is automatically immutable | Mutable array is shared | Use constructor/accessor defensive copies |
| Record arrays compare using deep equals automatically | Generated equals uses reference equality for arrays | Custom equals/hashCode or immutable representation |
| `Object.clone()` is a deep clone | super.clone is field-wise shallow | Use an explicit copy constructor/factory |
| Deep copy must clone singletons/sockets too | Resources/identity have their own contracts | Copy only the necessary value state |
| Deep copy always preserves graph topology | Naive recursion can duplicate a shared child | Use an identity map when needed |
| Cyclic graph copy uses plain recursion | Easily causes infinite stack overflow | Memoize the copy before recursing |
| `==` checks same value | For references, it checks identity | Use `equals` for value contracts |
| `equals` returning true proves deep copy | Nested objects may still be shared | Check nested identity and mutation isolation |
| A `final` reference makes an object immutable | Only prevents reassigning the field | Use defensive copies/immutable components |
| Assigning null frees the object immediately | There is no GC deadline | Manage owner/retention paths |
| Copying concurrent state always yields a consistent snapshot | Source can be modified between copy steps | Need a concurrency/snapshot policy |
| Shallow copy is always wrong | Can suffice with immutable children | Choose based on mutable graph and contract |
| Deep copy is always better | Increases cost and can break identity | Choose depth per requirements |
| `Arrays.equals` is the same as `==` | Compares contents vs. identity | Choose the right type of question |
| Same clone method name means same semantics | Contract depends on type and implementation | Check source/API documentation |

## 62. Practical Checklist Before Using Objects or Copy APIs

### A. References

- [ ] Have I distinguished between a reference variable and an object?
- [ ] Do I know that `a == b` checks identity, not value equality?
- [ ] Does the assignment `b = a` only copy the reference value?
- [ ] Could multiple fields/list slots point to the same mutable child?
- [ ] Have I drawn reference arrows in confusing places?

### B. Pass-by-Value

- [ ] Do I understand that both primitives and references **are pass-by-value**?
- [ ] Does reassigning a parameter only change the local parameter?
- [ ] Will modifying a mutable object through a parameter take effect through aliases?
- [ ] If wanting to change the caller's reference, should the method return a new object?
- [ ] Have I tried the mutate-then-rebind case?
- [ ] Am I avoiding the concept of "copying the whole object when passing an argument"?

### C. Copying

- [ ] Is this an alias assignment, container copy, or deep copy?
- [ ] If it is a primitive array, does clone provide the required independence?
- [ ] If it is an array of references, have the elements been copied?
- [ ] If it is a multidimensional array, have the necessary rows been copied?
- [ ] If it is a List/Map, have nested mutable objects been considered?
- [ ] Have I distinguished `List.copyOf` from an unmodifiable view?
- [ ] If using a record with a mutable component, are the constructor/accessor defensive?
- [ ] If using Object.clone, do I understand it is field-wise shallow by default?
- [ ] Does the deep-copied graph have cycles/aliases requiring IdentityHashMap?
- [ ] Are there any shared service/resource fields that must **not** be copied?
- [ ] Can an immutable value object be designed instead of deep-copy machinery?

### D. API Guarantees

- [ ] Who owns the state and modification rights?
- [ ] Does the constructor keep an input alias leading to an invariant leak?
- [ ] Does the accessor expose mutable internals?
- [ ] Do equality/hashCode match value/identity semantics?
- [ ] Which invariants does the copy preserve?
- [ ] Does the copy preserve alias topology when needed?
- [ ] Is the copy performed under appropriate synchronization if the source is concurrent?
- [ ] Are there tests for success/failure/mutation isolation rather than just copy result equals?
- [ ] Was the cost measured before copying a large graph in a hot loop?

## 63. Quick Review Questions with Answers

**1.** Does `Person b = a` create a new Person?

*No; it only copies the reference value.*

**2.** If `a == b` and `b.name = "X"`, does a see the new name?

*Yes, if the mutable field of the same object is modified and there is no concurrency visibility issue.*

**3.** Does `b = new Person()` change a?

*No; b is assigned a different reference.*

**4.** How does Java pass a primitive parameter?

*Copies the primitive value.*

**5.** How does Java pass a reference parameter?

*Copies the reference value, not the object.*

**6.** Can a method directly change the caller's local variable by assigning to a parameter?

*No.*

**7.** Can a method mutate the object the caller points to?

*Yes, if the parameter points to the same mutable object and the method has permission to mutate it.*

**8.** Why does a swap method not swap caller variables?

*Because it only reassigns the local parameters.*

**9.** Can an array passed into a method have its elements modified?

*Yes; the method receives a copy of the reference, yet it points to the same array object.*

**10.** Does `int[] copy = source.clone()` create a new array object?

*Yes.*

**11.** Does cloning an int[] make the primitive elements independent?

*Yes, because the element values are copied.*

**12.** Does cloning an Item[] create new Item objects?

*Not by default; the reference elements are copied.*

**13.** Does `new ArrayList<>(old)` create a new List?

*Yes.*

**14.** Are mutable object list elements deep-copied along with it?

*No.*

**15.** Does `List.copyOf` guarantee that mutable element objects cannot change?

*No.*

**16.** Is `Collections.unmodifiableList` a snapshot?

*No; it is a view of the backing list.*

**17.** Is a record with an `int[]` component automatically deeply immutable?

*No.*

**18.** Why is it necessary to clone the array in a record constructor and accessor?

*To prevent the caller from mutating the internal array via input/output aliases.*

**19.** Does defensive copying cause generated record equals to compare array contents?

*No.*

**20.** For two Point records with the same x/y instantiated separately, what is `==` normally?

*False, because of distinct object identities.*

**21.** Can `equals` be true even when `==` is false?

*Yes, under a value equality contract.*

**22.** What happens when a shallow-copied Customer has a shared Address reference?

*Mutations on Address through copy can affect original.*

**23.** In what way is a deep copy of Customer/Address better?

*It provides independent Address state within the scope of the contract.*

**24.** Does a deep copy always need to clone String?

*No; String is immutable and safe for sharing values.*

**25.** Why does graph copying need an identity map?

*To preserve alias relationships and prevent infinite recursion through cycles.*

**26.** Is `Object.clone()` shallow or deep by default?

*Field-wise shallow.*

**27.** Does `Cloneable` declare a public clone method itself?

*No; it is a marker interface.*

**28.** Is `System.gc()` necessary to verify copying correctness?

*No. Use deterministic identity and mutation tests.*

**29.** How does copying relate to encapsulation?

*Defensive copying helps a class maintain ownership and protect invariants at the boundary.*

**30.** If children are immutable, can a shallow container copy be sufficient?

*Yes, when the contract only requires structural independence.*

**31.** What happens if data is modified concurrently during copying?

*It can produce an inconsistent snapshot; synchronization or an immutable snapshot mechanism is needed.*

**32.** What is an accurate one-sentence summary of Java references?

*Variables hold reference values; multiple variables can point to the same object; methods always receive a copy of the argument value; shallow/deep copying must examine each layer of the object graph.*

## 64. Self-Check Exercise Without Running GC

Create a `Profile` class containing `String displayName` and `List<StringBuilder> notes`, then implement three versions:

1. **Reference alias:** `Profile b = a`.
2. **Shallow:** `new Profile(a.displayName, new ArrayList<>(a.notes))`.
3. **Deep within the StringBuilder scope:** Create a new List, with each new StringBuilder element created via the copy constructor `new StringBuilder(old.toString())`.

Then write tests for:

- `a == b` in alias.
- `a != shallow` yet `a.notes.get(0) == shallow.notes.get(0)`.
- `a != deep` and `a.notes.get(0) != deep.notes.get(0)`.
- `shallow.notes.get(0).append("!")` affects original.
- `deep.notes.get(0).append("!")` does not affect original.
- `shallow.notes.add(...)` does not give the original list a new element.
- Input null/empty list policy and ownership.
- If the list has **two slots pointing to the same StringBuilder**, does the deep copier preserve alias topology? Does it need to preserve it?

**Guided answer:** Alias preserves all identities. Shallow separates the container but shares elements. Deep separates elements according to policy; to preserve aliases when two original slots point to the same instance, a map from original element identity to copied element identity is needed, rather than creating a separate copy for each slot.

## 65. Official References

- *Java Language Specification, Java SE 17 — `15.12 Method Invocation Expressions*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12 — argument evaluation and invocation semantics.
- *Java Language Specification, Java SE 17 — `4 Types, Values, and Variables*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html — primitive/reference types and values.
- *Java Language Specification, Java SE 17 — `10 Arrays*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html — arrays are objects, clone, and elements.
- *Java SE 17 API — `java.lang.Object.clone`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone() — clone contract and `CloneNotSupportedException`.
- *Java SE 17 API — `java.util.List.copyOf`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection) — unmodifiable snapshot semantics.
- *Java SE 17 API — `java.util.IdentityHashMap`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html — key equality by object identity.
- *Java SE 17 API — `java.util.Arrays`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html — copyOf, equals, deepEquals, toString, deepToString.

---

**Final takeaway:** In Java, `b = a` with reference types only **copies the reference value**, allowing two variables to **share a mutable object**. Java is **always pass-by-value**: a parameter receives a copy of the primitive value or a copy of the reference value; therefore, **reassigning the parameter does not change the caller variable**, whereas **mutating a shared object through the parameter can change the state observed by the caller**. **Shallow copy** creates a new object/container but usually shares mutable children; **deep copy** must explicitly separate the mutable descendants belonging to the contract, and may need to preserve aliases/cycles with an identity map. Array clone, List copy, record, and Object.clone do not automatically have the same depth. Choose a copy policy based on **ownership, mutability, and invariants**, and verify using `==`, contents, and mutation isolation, instead of guessing from variable names or waiting for GC.
