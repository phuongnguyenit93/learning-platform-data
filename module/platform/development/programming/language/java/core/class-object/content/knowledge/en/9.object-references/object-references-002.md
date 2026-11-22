# Reference Diagrams When Declaring, Assigning, and Creating Objects in Java

## 1. Use Diagrams to Track the Object Graph, Not Just Learn Definitions

The specific goal of this lesson is to **redraw the arrows after each statement**. Treat variables, fields, and array slots as locations that can hold a reference; objects reside in the rest of the diagram. Only draw an additional object if an object creation operation succeeds; do not draw an additional one merely because of an assignment.

~~~java
Student first = new Student("Lan");
Student second = first;
~~~

This is a snippet assuming class Student has a constructor that takes a String.

~~~text
Reference-holding location     Object
first  ----------------┐
                       +----> Student A {name="Lan"}
second ----------------┘
~~~

Tracing procedure:

1. Mark the moment `new` executes to add an object.
2. Find the variable or slot receiving the new reference and redraw the **arrow**.
3. When encountering `alias.field = ...`, update the **object**; when encountering `alias = ...`, update the **reference variable**.
4. Predict `==`, null, and output from the diagram state at the right point in time.

Arrows are a semantic model, **not actual RAM addresses**. The following sections use the same approach for assignment chains, methods, arrays, and object lifecycles.

## 2. Three Easily Confused Operations: Declaration, Assignment, and Object Creation

The table below separates each operation and its result:

| Code | Operation | Creates a new `Student`? | Result |
| --- | --- | --- | --- |
| `Student s;` | Local variable declaration | No | `s` exists in scope but is not yet definitely assigned |
| `Student s = null;` | Declaration and `null` assignment | No | `s` does not point to any object |
| `s = new Student("A");` | Object creation and reference assignment | Yes | `s` points to the newly created object |
| `Student t = s;` | Copying the reference value | No | `t` and `s` point to the same object |
| `t = new Student("B");` | Creating a new object and reassigning `t` | Yes | `t` points to object B; `s` still points to object A |
| `s = t;` | Reassigning the reference | No | `s` and `t` both point to object B |
| `t = null;` | Clearing the reference in `t` | No | Only `t` becomes `null`; object B is not necessarily left without other references |

**In particular:** `Student s;` merely declares an unassigned **local variable**. You cannot read `s` before Java proves *definite assignment*. Inside a method:

```java
Student s;
// System.out.println(s); // If uncommented: compilation error.
s = new Student("Lan");
System.out.println(s != null); // true
```

This is an **illustrative code snippet** assuming `Student` is defined and has a `Student(String)` constructor; to run it, it must be placed in a valid program. Unlike a local variable, an **instance field** or **static field** with a reference type is given the default value `null` by Java when initialized according to the rules.

## 3. Diagram 1 — Variable Declaration Only, Without Creating an Object

Consider inside a method:

```java
Person p;
```

At this point:

```text
Method scope
┌───────────────────┐
│ p : Person        │
│ not definitely    │
│ assigned          │
└───────────────────┘

No Person object is created by this declaration statement.
```

You should not immediately draw `p ──> Person { ... }` because **there is no instance creation statement yet**. You should also not draw `p ──> null` for an **uninitialized local variable**, because `p` does not yet have a valid value to read. Java uses definite assignment checking to block reading before the variable is assigned.

If you write:

```java
Person p = null;
```

then the diagram is different:

```text
p : Person
  |
  +----> null (no Person object)
```

`null` is a special reference value representing **pointing to no object**. It is not an empty `Person`, nor is it an object with default fields.

### Distinguishing Default Fields from Local Variables

```java
class Holder {
    Person current;            // Instance field: defaults to null.
    static Person selected;    // Static field: defaults to null.
}
```

For a newly created `Holder`, `current` is initially `null` if no initializer/constructor assigns otherwise; `Holder.selected` also has the default value `null` before explicit static initialization steps. However, a local `Person p;` must be assigned before being read. These are three situations with **different initialization rules**, despite declaring the same `Person` type.

## 4. Diagram 2 — `new` Creates an Object and Returns a Reference

When you write:

```java
Person p = new Person("Mai");
```

picture two events:

1. The expression `new Person("Mai")` creates a new `Person` instance according to the class instance creation rules, including allocation, initialization steps, and the appropriate constructor call.
2. The result of the `new` expression is **a reference to the new instance**, which is assigned to the variable `p`.

```text
After new Person("Mai") completes:

Variable p                             Object A
┌───────────────────┐                  ┌──────────────────┐
│ p : Person  ──────┼─────────────────>│ Person           │
└───────────────────┘                  │ name = "Mai"     │
                                       └──────────────────┘
```

A **constructor** is not a method that returns `Person`. The `new Person(...)` expression itself produces a reference value that can be assigned; the constructor is called during the object construction process and has no return type.

In Java code, the variable name `p` is not embedded as an identity property of the object. After renaming the variable or assigning the object to another variable, **the object is still that exact same object**.

### `new` Differs from Field Declarations and Class Declarations

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }
}
```

Defining the `Person` class or the `name` field does not automatically create a `Person` object for each declaration line in the source code. An instance only appears when an appropriate instance creation operation takes place, such as `new Person("Mai")`. A class may have no instances yet during execution.

## 5. Diagram 3 — Assignment Between Two Reference Variables Creates an Alias

Suppose:

```java
Person first = new Person("Mai");
Person alias = first;
```

After the two statements:

```text
first ──────────┐
                ├──────> [Person A: name="Mai"]
alias ──────────┘
```

`alias` is a new variable, **not a new copy of `Person A`**. Both variables hold a reference to object A; that relationship is commonly called **aliasing**.

If `alias.setName("Lan")` is executed with an instance method that updates the field, both `first.getName()` and `alias.getName()` see `"Lan"` because they are accessing **the same object**. Updating through a reference does not mean Java automatically synchronizes two variables by name; the two variables are just pointing to the same place holding the object's state.

### Standalone Runnable Example: Aliasing Changes Shared State

Create the file **`AliasDemo.java`**:

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class AliasDemo {
    public static void main(String[] args) {
        Person first = new Person("Mai");
        Person second = first;

        second.rename("Lan");

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first == second);
    }
}
```

Compile/run with JDK 17+:

```bash
javac AliasDemo.java
java AliasDemo
```

Expected output:

```text
Lan
Lan
true
```

The `rename` method receives the object it is called on as `this`. `second.rename("Lan")` modifies the object that `second` points to, which is also `first`'s object. The `==` operator on two object references returns `true` when they both point to the exact same object.

## 6. Diagram 4 — Reassigning One Variable Does Not Change the Other Alias Variable

Continuing:

```java
Person first = new Person("Mai");
Person second = first;
second = new Person("Nam");
```

Before reassigning `second`:

```text
first ───────────┐
                 ├──> [Person A: "Mai"]
second ──────────┘
```

After `second = new Person("Nam")`:

```text
first ────────────────> [Person A: "Mai"]

second ───────────────> [Person B: "Nam"]
```

There are now **two different objects**. `second` switches to referencing object B, while `first` **still holds a reference to object A**. Java does not maintain a “permanent link” between two variables merely because they previously pointed to the same object.

When you write `second = first;` in the next step, it **only copies the reference** from `first` back to `second`; it does not create a new object and does not automatically destroy object B right at that statement. Object B may still have other references; even when none remain, garbage collection does not necessarily happen immediately.

### Changing Object State Differs from Reassigning a Variable

The following two statements have completely different effects:

- `second.rename("An");`: calls a method on **the object that `second` currently points to**, which may change the object's state.
- `second = first;`: changes **the reference value in variable `second`**; the contents of the two objects themselves are not automatically copied or modified.

This is the core distinction for understanding aliasing bugs and avoiding mispredicting data when a method/field receives a reference.

## 7. Multi-Step Example with Diagrams and Exact Output

Create the file **`ReferenceTimelineDemo.java`**:

```java
class Box {
    private final String id;
    private int value;

    Box(String id, int value) {
        this.id = id;
        this.value = value;
    }

    void add(int amount) {
        value += amount;
    }

    String describe() {
        return id + "=" + value;
    }
}

public class ReferenceTimelineDemo {
    public static void main(String[] args) {
        Box a = new Box("A", 10);
        Box b = a;

        b.add(5);
        System.out.println("1: " + a.describe());
        System.out.println("2: " + (a == b));

        b = new Box("B", 20);
        System.out.println("3: " + b.describe());
        System.out.println("4: " + (a == b));

        a = b;
        a.add(2);
        System.out.println("5: " + a.describe());
        System.out.println("6: " + b.describe());
        System.out.println("7: " + (a == b));
    }
}
```

Commands:

```bash
javac ReferenceTimelineDemo.java
java ReferenceTimelineDemo
```

Output:

```text
1: A=15
2: true
3: B=20
4: false
5: B=22
6: B=22
7: true
```

This can be traced using four states:

**State T1 — After declaration, creation, and alias assignment:**

```text
a ─────┐
       ├──> [Box A, value=10]
b ─────┘
```

**State T2 — After `b.add(5)`:**

```text
a ─────┐
       ├──> [Box A, value=15]
b ─────┘
```

Object A is modified; there is no new object. `a.describe()` returns `A=15`; `a == b` returns `true`.

**State T3 — After `b = new Box("B",20)`:**

```text
a ───────> [Box A, value=15]

b ───────> [Box B, value=20]
```

Object B is a new object; `a==b` becomes `false`. Object A is still pointed to by `a`.

**State T4 — After `a = b; a.add(2)`:**

```text
a ─────┐
       ├──> [Box B, value=22]
b ─────┘

[Box A, value=15]  (no longer pointed to by a or b)
```

`a = b` does not create a new object; both variables point to B. `a.add(2)` modifies B to 22. Therefore, both `a.describe()` and `b.describe()` return `B=22`. Box A may become unreachable from this program segment; you must not conclude that it is destroyed immediately, because garbage collection is decided by the JVM.

> **How to read the diagram:** Draw one box for **each actual object**, one label for **each reference variable**, and then update the arrows when an assignment occurs. Only update **the contents of an object box** when a state-modifying action occurs. Do not create an additional object box merely because an alias variable appears.

## 8. `null`: Has a Reference Value Without Pointing to an Object

Example:

```java
Box current = null;
```

Diagram:

```text
current : Box ──────> null

There is no Box object at the tip of the arrow.
```

Here, `current` **has been assigned** a valid value of the reference type. However, `current.describe()` will throw a `NullPointerException` when the instance method call requires a receiver object.

```java
class NullReferenceExample {
    static void show() {
        String name = null;
        System.out.println(name == null);  // true
        // System.out.println(name.length());
        // If run: NullPointerException because name does not point to a String object.
    }
}
```

This is a class declaration that can compile because the runtime-error statement has been commented out. The local variable `name` is assigned `null`, so it **does not violate definite assignment**; the risk lies in dereferencing a reference that points to no object.

### Distinguishing from the String `"null"`

`String a = null;` differs from `String b = "null";`:

```text
a ──────> null                  (no String object)
b ──────> String with content "null"
```

`a == null` is `true`, whereas `b == null` is `false`. Printing a null value by means of string concatenation may display the text `null` on the console, but it does not turn null into a String object.

## 9. `==` Checks for the Same Object; `equals` Checks According to the Class Contract

For references, `==` compares **reference identity**: do the two variables point to the same object? Meanwhile, `equals` is an instance method; if the class overrides it according to the contract, it can compare **meaningful content**.

Example with immutable objects:

```java
String one = new String("Java");
String two = new String("Java");

System.out.println(one == two);      // false
System.out.println(one.equals(two)); // true
```

This is a code snippet inside a method. The two `new String("Java")` expressions create two separate String objects according to the semantics of the `new` expression; they have the same content, but they are not the same object. `String.equals` compares character content, so it returns `true`.

Diagram:

```text
one ────> [String object #1: "Java"]

two ────> [String object #2: "Java"]
```

**Caution with String literals:** string literals may be interned, so `==` between literals does not prove content is compared properly in all situations. When comparing text, use `equals`, or `Objects.equals(a,b)` if you must handle the possibility of `null`.

### The Default `equals` Does Not Necessarily Compare Fields

A custom class that **does not override `equals`** inherits the implementation of `Object.equals`, which essentially compares identity. Therefore, two `new Box("A", 10)` instances with the same data will not necessarily have `equals` return `true`.

If you design a **value object** that needs to be compared by content, you must implement `equals` and `hashCode` consistently (or use a `record` when appropriate). This does not change the reference diagram; it changes **how content is compared via the API**.

## 10. Passing Objects to Methods: Java Always Passes Parameters by Value

This is a major source of confusion: Java is **pass-by-value**, even when the argument is a reference. When calling a method with a reference variable, Java **copies the reference value** into the method's local parameter.

This leads to two distinct consequences:

1. The method can use the parameter to **modify the contents of the shared object**, if the object is mutable and access permissions allow it.
2. The method **cannot change the value of the reference variable at the caller** merely by reassigning the local parameter.

### Diagram When Passing a Reference

```text
Before the call:
callerRef ─────────> [Box A, value=10]

During the call change(callerRef):
callerRef ─────────┐
                   ├──> [Box A, value=10]
parameter ─────────┘

After the statement parameter = new Box("B",20):
callerRef ─────────> [Box A, value=10]
parameter ─────────> [Box B, value=20]

Upon exiting the method:
Variable parameter goes out of scope; callerRef still points to Box A.
```

### Runnable Java 17+ Example

Create the file **`PassByValueReferenceDemo.java`**:

```java
class Cell {
    int number;

    Cell(int number) {
        this.number = number;
    }
}

public class PassByValueReferenceDemo {
    static void change(Cell parameter) {
        parameter.number += 3;
        parameter = new Cell(99);
        System.out.println("inside=" + parameter.number);
    }

    public static void main(String[] args) {
        Cell original = new Cell(2);
        change(original);
        System.out.println("outside=" + original.number);
    }
}
```

Compile/run:

```bash
javac PassByValueReferenceDemo.java
java PassByValueReferenceDemo
```

Output:

```text
inside=99
outside=5
```

At the beginning of `change`, the variables `parameter` and `original` both reference the `Cell(2)` object. The statement `parameter.number += 3` modifies the shared object to `5`. Next, `parameter = new Cell(99)` creates another object and **only reassigns the parameter variable**. Therefore, the method prints `inside=99`, while the caller still uses the first object with `number=5`.

**Do not call this “Java passes objects by reference” in the pass-by-reference sense:** the value passed is **a copy of the reference**. The method does not receive permission to directly modify the caller's `original` variable slot.

### How Can the Caller Receive a New Object?

The method can **return the reference**:

```java
static Cell replacement(int number) {
    return new Cell(number);
}
```

When the caller explicitly assigns `original = replacement(42);`, the variable at the caller changes its reference because **the caller performs the assignment**. The method does not automatically reassign the caller's variable.

## 11. Reference Diagrams with Fields Holding Other Objects

An object can contain a reference-type field pointing to another object, forming an **object graph**.

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Employee {
    String name;
    Address address;

    Employee(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
```

When executed:

```java
Address home = new Address("Da Nang");
Employee an = new Employee("An", home);
Employee binh = new Employee("Binh", home);
```

Diagram:

```text
home ───────────────────────────────┐
                                    v
                             [Address A]
                              city="Da Nang"
                                    ^
                                    |
an ──> [Employee An] ── address ────┤
                                    |
binh ─> [Employee Binh] ─ address ──┘
```

There are **two Employee objects** but **one shared Address object**. Therefore, if `home.city = "Hue";` is executed and the fields are accessible within the scope of the example, both `an.address.city` and `binh.address.city` yield `"Hue"`. However, if you write `an.address = new Address("Ha Noi");`, only Employee An's `address` field is assigned to the new Address; Employee Binh still points to Address A.

This is **illustrative code without its own `main`**. Sharing a mutable object easily creates side effects between application components. For data that needs to be immutable, you can use an immutable value object or a defensive copy mechanism when designing constructors/getters.

### Why Doesn't Aliasing Occur Only Between Local Variables?

Any location that stores a reference value — a local variable, field, static field, array element, or method parameter — can become a path to the same object. The diagram must depict **the exact locations holding references**, not only the variables written inside `main`.

## 12. Arrays Are Also Objects: Array Variables and Array Elements Play Different Roles

`int[] numbers = new int[3];` involves two concepts:

- `numbers` is a **reference variable** of type `int[]`.
- `new int[3]` is **an array object** containing three `int` elements, initially all equal to `0`.

```text
numbers ─────> [int[] object]
               index 0 = 0
               index 1 = 0
               index 2 = 0
```

If you write `int[] alias = numbers;`, both variables point to the same array. `alias[0] = 7;` will cause `numbers[0]` to become `7`. Creating `alias = new int[3];` will cause the two variables to point to two different array objects; the `numbers` array remains unchanged.

### Object Arrays Store References in Each Element

```java
Person[] people = new Person[2];
```

Diagram immediately after `new Person[2]`:

```text
people ─────> [Person[] array object]
               [0] ───> null
               [1] ───> null
```

Java **only creates the array object**; it does not call `new Person()` twice. Each element of type `Person` holds the default value `null` until assigned.

After writing `people[0] = new Person("Mai"); people[1] = people[0];`:

```text
people ─────> [Person[] array object]
               [0] ──────────┐
                             ├──> [Person A: "Mai"]
               [1] ──────────┘
```

Both array elements reference **one** Person object. Modifying the object through `people[1]` will be observable when reading through `people[0]`. If you assign `people[1] = new Person("Nam");`, the two elements again point to two objects.

### Standalone Example: Aliasing in Arrays

Create the file **`ArrayReferenceDemo.java`**:

```java
class Point {
    int x;

    Point(int x) {
        this.x = x;
    }
}

public class ArrayReferenceDemo {
    public static void main(String[] args) {
        Point[] points = new Point[2];
        System.out.println(points[0] == null);

        points[0] = new Point(4);
        points[1] = points[0];
        points[1].x += 3;

        System.out.println(points[0].x);
        System.out.println(points[0] == points[1]);

        points[1] = new Point(9);
        System.out.println(points[0].x);
        System.out.println(points[1].x);
    }
}
```

```bash
javac ArrayReferenceDemo.java
java ArrayReferenceDemo
```

```text
true
7
true
7
9
```

When both elements point to the same `Point`, updating `points[1].x` changes `points[0].x`. Assigning a `new Point(9)` to the second element replaces **the reference in the array slot**, without modifying the first object.

## 13. Static Fields Hold References Shared at the Class Level

A reference-type `static field` is a location storing a reference that belongs to **the class**, not tied individually to each object.

```java
class Registry {
    static Point current;
}
```

Initially, before any explicit assignment, `Registry.current` holds `null` by the default rules. After `Registry.current = new Point(10);`:

```text
Registry.current ──────────> [Point A: x=10]
```

If two local variables are both assigned from `Registry.current`, they can both point to `Point A`. Writing `Registry.current = new Point(20);` only replaces the reference stored in the static field; variables that previously copied the old reference **do not automatically switch** to the new object.

Example:

```java
Point old = Registry.current;
Registry.current = new Point(20);

// old still references Point A (x=10).
// Registry.current points to Point B (x=20).
```

The lines above are a code snippet inside a method, using the `Point` class illustrated in the previous section. You must distinguish “a shared data field” from “every variable that ever read that field is always updated”: **saving a copy of the reference** alters the subsequent reference paths.

In multithreaded programs, accessing a mutable static field also involves visibility/data races; a single-threaded reference diagram is not enough to prove concurrency safety.

## 14. References and Inheritance: Static Type Differs from Actual Class

A variable of a superclass or interface type can point to an object of a compatible subclass:

```java
Animal animal = new Dog();
```

In terms of a diagram:

```text
animal : Animal ───────> [Dog object]
                         kind = Dog
```

The variable `animal` **has the static type `Animal`**, while the runtime object is a `Dog`. This assignment is valid if `Dog` is a compatible subtype of `Animal`. However, changing the reference type **does not turn the Dog object into a new Animal object**.

This is an important point when reading a method call:

- The compiler determines which methods can be called based on the **static type** of the receiver expression.
- When an instance method has been overridden and can be dynamically dispatched, the runtime selects the implementation based on **the actual class of the receiver**.
- For field access, Java resolves the field according to the **static type** rules, without using dynamic dispatch for fields.

### Complete Example

Create the file **`ReferencePolymorphismDemo.java`**:

```java
class Animal {
    String speak() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "woof";
    }

    String fetch() {
        return "ball";
    }
}

public class ReferencePolymorphismDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        System.out.println(animal.speak());
        System.out.println(dog.fetch());
        System.out.println(animal == dog);
        System.out.println(animal instanceof Dog);
    }
}
```

```bash
javac ReferencePolymorphismDemo.java
java ReferencePolymorphismDemo
```

```text
woof
ball
true
true
```

`animal` and `dog` point to the same Dog object, so `animal == dog` is `true`. `animal.speak()` selects the overridden implementation in `Dog`, whereas `animal.fetch()` **does not compile** if added to the example because the static type `Animal` does not declare a `fetch()` method. `animal instanceof Dog` is `true` because the actual object is a `Dog`.

**No additional Dog object needs to be created** when assigning `Animal animal = dog;`; this operation merely copies a valid reference.

## 15. `final` on a Reference Variable Does Not Make the Object Immutable

The `final` keyword restricts **reassigning the variable**, rather than automatically making the object the variable points to immutable.

```java
final Point point = new Point(5);
point.x = 8;                 // Valid if field x allows writing.
// point = new Point(10);    // Error: cannot reassign a final variable.
```

This is a code snippet inside a method using the `Point` class from the array example. Diagram:

```text
point (final) ─────> [Point object]
                      x: 5 -> 8
```

The arrow from variable `point` cannot be reassigned to another object under the `final` rules; however, the object's state can change through this reference or another alias.

If a class needs to be **immutable**, you must design its fields, constructors, and reference exposure appropriately (for example, private final primitive fields, providing no setters, and defensive copies for mutable components). `final Point point` **is not enough** to guarantee that the Point object is immutable.

## 16. Reference Diagrams and Garbage Collection: Do Not Confuse “Losing an Alias” with “Immediate Object Destruction”

Consider:

```java
Box current = new Box("A", 1);
Box alias = current;

current = null;
```

Diagram:

```text
current ──────> null

alias ────────> [Box A, value=1]
```

Object A still has a **strong reference** from `alias`, so assigning `current = null` does not make the object immediately “disappear”. If afterward `alias = null;` and **there are no remaining strong reference paths from GC roots to object A**, the object may become **eligible for garbage collection**.

However:

- **Eligible** does not mean “collected immediately”.
- `System.gc()` does not guarantee that a specific object will be reclaimed at the moment you want.
- The JVM may optimize how it manages object lifecycles; standard Java code should not rely on a fixed time of object destruction.
- The state of “no longer having references from two local variables” is not enough to prove an object is unreachable if a static field, a field of another object, an array element, a thread, or another GC root still references it.
- A reference cycle (A points to B and B points to A) **does not necessarily prevent collection**, if neither is still reachable from GC roots; the Java garbage collector can handle unreachable cycles.

**Diagrams are a tool for reasoning about reachability**, not a snapshot of the actual JVM heap. You should not conclude precisely “at which statement the object is freed” solely based on a variable being assigned `null`.

### There Is No Direct Object Deletion Operation in Java

Java does not have `delete object;` like some manual memory management mechanisms in other languages. To release non-memory resources (files, sockets, connections), you must use the appropriate resource-closing API, such as `try-with-resources`; do not replace closing a resource with `reference = null`.

## 17. At What Level Should “Stack/Heap” Diagrams Be Understood?

Introductory materials often draw local variables on the **stack** and objects on the **heap**. This is a **useful simplified model to start with**, but it is not a guarantee that every reference variable resides at a fixed memory location or that every object always has a heap address observable by the program.

Java semantics guarantees relationships such as:

1. A reference value can point to an object or be `null`.
2. Assignment between two reference variables copies **the reference value**, without automatically cloning the object.
3. `new` creates an instance according to expression semantics, and the object has its own **identity**.
4. Two aliases can both observe state changes of a mutable object.
5. A method parameter receives **a copy of the reference value**.
6. The JVM manages object lifecycles and garbage collection, without exposing a direct deallocation operation.

Implementation details such as object headers, compressed oops, escape analysis, stack allocation optimization, or scalar replacement depend on the JVM and optimization mode. **Do not rely on those details to explain output** unless you are specifically studying JVM internals.

When drawing diagrams in exercises, you should label two regions:

```text
Reference-holding locations  Object graph (conceptual)
(local / field / array)      (no machine layout guaranteed)

local x ────────────────────> Object #1
field y ────────────────────> Object #2
array[0] ───────────────────> Object #1
```

This diagram is accurate regarding **aliasing** without making claims about the physical location of each variable/object.

## 18. Common Mistakes When Drawing or Explaining References

| Misconception | Correct Understanding to Use |
| --- | --- |
| “Declaring `Person p;` already creates a Person” | It only declares a local variable; no new object is created |
| “`Person p = null;` has an empty Person” | `null` points to no object |
| “`Person b = a;` creates a copy of the object” | It only copies the reference value; it typically creates an alias |
| “Renaming the variable renames the object” | An object has its own identity, not tied to the variable name |
| “Assigning `a = new Person(...)` updates all old aliases” | Only variable `a`'s value is reassigned |
| “`b.rename(...)` changes variable `b` to another object” | Usually it changes the receiver's state; you must read the method body |
| “Passing a reference to a method is pass-by-reference” | Java is pass-by-value: it copies the reference value |
| “A method assigning `parameter = new ...` changes the caller's variable” | No; it only reassigns the local parameter |
| “`a == b` compares content” | For references, `==` checks if they are the same object; `equals` depends on the class contract |
| “`new Person[3]` creates three Person objects” | It only creates an array object; the Person elements default to `null` |
| “`final` on a reference variable makes the object immutable” | `final` prevents reassigning the variable; the object can still be mutable |
| “`Base x = new Derived()` creates an extra Base object” | One Derived instance; the variable is assigned a reference of static type Base |
| “Both fields and local variables default to `null`” | Reference fields default to `null`; locals must be definitely assigned before reading |
| “Assigning `x = null` immediately triggers GC” | It only assigns the variable; GC is not guaranteed to run immediately |
| “Arrows are concrete pointer addresses” | They are a conceptual representation of references, not a memory-address API |
| “An object can only have one variable pointing to it” | Multiple local variables, fields, and array elements can reference it at once |
| “Two objects with equal fields are the same object” | Identity and content equality are two different relationships |
| “Creating a subclass object also creates an independent superclass object” | The superclass portion is initialized within the same subclass instance |

## 19. Self-Check by Scenario

**Question 1.** After `Student x;` in a method, is there a new `Student` object? Is reading `x` immediately valid?

*Answer:* There is no new object. `x` is a local variable not yet definitely assigned, so reading it immediately is a compilation error.

**Question 2.** Is `Student x = null;` different from `Student x;`?

*Answer:* Yes. `x = null` has assigned a special readable reference value; `Student x;` only declares an unassigned local variable.

**Question 3.** In `Point a = new Point(4); Point b = a;`, how many `Point` objects are created by the two statements?

*Answer:* One object. `b = a` only copies the reference and creates an alias.

**Question 4.** If afterward `b.x = 7;`, what is `a.x` equal to?

*Answer:* `7`, because `a` and `b` point to the same mutable Point object.

**Question 5.** If next `b = new Point(9);`, what are `a.x` and `b.x`?

*Answer:* `a.x == 7`, `b.x == 9`. There are two different Point objects.

**Question 6.** Given `Box first = new Box("A",1); Box second = first;`, if you write `first = null;`, does `second` become null?

*Answer:* No. `second` still holds a reference to the old object.

**Question 7.** Why is `new Person[3]` not equivalent to calling `new Person(...)` three times?

*Answer:* The first expression only creates one array object containing three `null` reference slots; the `Person` constructor has not been called for each element.

**Question 8.** If method `change(Cell p)` assigns `p = new Cell(99);`, does the `original` variable at the caller automatically point to Cell(99)?

*Answer:* No, because parameter `p` only receives a copy of the reference value. The caller must assign the result itself if it wants to change its reference.

**Question 9.** Does `Animal a = new Dog();` create two objects, Animal and Dog, or one?

*Answer:* One Dog object. Variable `a` has static type Animal, but points to the Dog object.

**Question 10.** Is `final Point p = new Point(1); p.x = 2;` invalid just because `p` is final?

*Answer:* No, if field `x` allows modification. `final` on `p` forbids reassigning variable `p`, not modifying the contents of the Point.

**Question 11.** Can two different `new String("Hi")` instances have `equals` evaluate to `true` while `==` evaluates to `false`?

*Answer:* Yes. The two objects differ in identity, yet have the same character content.

**Question 12.** Does setting the last variable holding a reference to an object to `null` guarantee that the object will be collected immediately?

*Answer:* No. Reachability also depends on other reference paths; even when eligible for GC, there is no guarantee of immediate collection.

**Question 13.** A `static Point current` already references object A; local `old = current`. After `current = new Point(8)`, which object does `old` reference?

*Answer:* Still A. The value copied into `old` does not automatically change when the static field `current` is reassigned.

**Question 14.** In the diagram `a ──> A` and `b ──> A`, if `b = a` executes once more, is there a new object?

*Answer:* No. `b` simply receives the reference value currently held in `a` again.

## 20. Procedure for Drawing Accurate Reference Diagrams

When working on Java exercises with multiple assignments and method calls, you should follow this order:

1. **List variables and reference-holding locations:** locals, parameters, fields, static fields, array slots. Note the **static type** of each variable.
2. **Mark unassigned variables:** for a local `Type x;`, write “not definitely assigned”; do not draw null on your own.
3. **For `new`, create a new object box:** give it a distinct label such as A, B, C; assign the fields after the initializer/constructor completes according to the scenario.
4. **For a reference assignment `left = right`, update the arrow of left:** do not automatically create a copy of the right-hand object.
5. **For `left.field = value` or a state-modifying instance method, update the contents of the receiver object:** if multiple aliases point to that object, all of them observe the same state when reading.
6. **When passing into a method, draw a new parameter variable pointing to the same object:** any reassignment of the parameter updates only the parameter's local arrow.
7. **For arrays or reference-type fields, add arrows from the slots/fields:** one object can be pointed to by multiple slots.
8. **For `null`, draw no target object:** if the code dereferences null, record the appropriate runtime error.
9. **For `==` on references, compare the two targets of the arrows:** same object → true; different objects → false (except in the case of null according to the rules).
10. **For `equals`, check the class contract rather than inferring from the identity diagram.**
11. **For `final`, lock reassignment of the reference variable/field; it does not automatically lock the object's state.**
12. **When an object loses an arrow, do not rush to label it “destroyed”:** analyze only reachability and GC eligibility, without guaranteeing collection timing.
13. **Cross-check output over time:** after each statement, record which object each variable points to, what values the fields hold, and which receiver each method executes on.

### Final Self-Practice Exercise

No need to run it right away; try drawing the diagram after each line on your own and then compare with the solution:

```java
class Node {
    int value;
    Node next;

    Node(int value) {
        this.value = value;
    }
}

// The statements below are inside a method:
Node a = new Node(1);
Node b = new Node(2);
a.next = b;
Node c = a;
b = new Node(3);
c.next.value += 5;
```

**Solution:**

```text
After the first two new statements:
a ─────> [Node A: value=1, next=null]
b ─────> [Node B: value=2, next=null]

After a.next = b:
a ─────> [Node A: value=1]
                     |
                     next ───> [Node B: value=2]
b ────────────────────────────────────^

After Node c = a:
a ──┐
    ├──> [Node A] ──next──> [Node B: value=2]
c ──┘                     ^
                          |
b ────────────────────────┘

After b = new Node(3):
a ──┐
    ├──> [Node A] ──next──> [Node B: value=2]
c ──┘
b ───────────────────────> [Node C: value=3]

After c.next.value += 5:
a ──┐
    ├──> [Node A] ──next──> [Node B: value=7]
c ──┘
b ───────────────────────> [Node C: value=3]
```

**Why does `Node B` still exist?** `b` has switched to Node C, but field `a.next` (also seen through `c.next`) still points to Node B. Therefore, `c.next.value += 5` modifies **Node B**, not Node C. As a result, `a.next.value == 7`, `b.value == 3`, and `a == c` is `true`.

---

**Remember:** **Declaring a variable does not create an object; `new` creates an object; assigning between reference variables only copies the reference.** Two aliases can both observe changes to a mutable object, whereas reassigning one alias does not make the other alias automatically switch targets. `null` means “no target object”; a method receives a copy of the reference value; `==` checks identity while `equals` depends on the class contract. Arrow diagrams are a model of **reference relationships**, not a guarantee about machine addresses or garbage collection timing.
