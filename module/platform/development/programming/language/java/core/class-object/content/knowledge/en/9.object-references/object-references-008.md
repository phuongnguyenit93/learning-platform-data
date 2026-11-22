# Object Arrays: Creating a Reference Array and Creating Each Element in Java

## 1. Two Different Kinds of Objects: Array Objects and Element Objects

In Java, **an array is an object**. When declaring an array of a class, for example `Student[]`, the array does not contain `Student` objects directly in the language model; it contains **elements that are reference values**. Each element can reference a `Student` object or be `null`.

The following two expressions are **fundamentally different**:

```java
Student[] students = new Student[3];
Student one = new Student("An");
```

This is an **illustrative code snippet**; assume the `Student` class has a constructor that takes a `String`.

- `new Student[3]` creates **one array object** with three reference slots, each initially **`null`**. It does **not** call `new Student()` and does **not** create three `Student` objects.
- `new Student("An")` creates **one `Student` object** (then initialized according to the corresponding constructor); the expression's value is a reference to that object.
- `students` is a variable referencing the **array object**.
- `students[0]` is **a slot of the array object** storing a `Student` reference value. Initially, the slot's value is `null`; you can assign a reference to a specific `Student` into it.

**Diagram immediately after `new Student[3]`:**

```text
students : Student[]
       |
       v
  +---------------------------+
  | Student[] array (length 3)|
  +---------------------------+
  | [0] ----> null            |
  | [1] ----> null            |
  | [2] ----> null            |
  +---------------------------+

Number of Student objects created by the line new Student[3]: 0
Number of array objects created by that line: 1
```

**Diagram after creating one element:**

```java
students[0] = new Student("An");
```

```text
students
    |
    v
  +----------------------+
  | Student[] (length 3) |
  | [0] -----------------------+----> Student A { name="An" }
  | [1] ---> null       |     |
  | [2] ---> null       |     |
  +----------------------+     |
                               +--- 1 new Student object
```

The figures are **conceptual reference diagrams**, not descriptions of machine memory addresses or a fixed physical JVM representation.

> **First takeaway:** creating a *reference array* and creating the *object referenced by each element* are **two separate operations**. For arrays of classes, interfaces, or other reference types, do not infer that the number of array elements is the number of component objects created.

## 2. Syntax for Declaration, Allocation, and Element Assignment

Common declaration forms:

```java
Student[] first;
Student second[];
Student[] third = new Student[3];
```

Both `Student[] first` and `Student second[]` forms are supported by Java, but **`Student[]` is usually easier to read** because the square brackets are placed next to the type. These are declaration fragments used within an appropriate scope and do not contain the `Student` definition.

Distinguish between three actions:

| Statement | Meaning | Creates an array object? | Creates a Student object? |
| --- | --- | --- | --- |
| `Student[] a;` | Declares only an array-typed local variable | No | No |
| `Student[] a = null;` | Declares and assigns the value null | No | No |
| `Student[] a = new Student[3];` | Creates an array of length 3 with null slots | **Yes: 1** | No |
| `a[0] = new Student("An");` | Creates a Student and assigns the reference into slot 0 | Does not create a new array | **Yes: 1** |
| `a[1] = a[0];` | Copies the reference from slot 0 into slot 1 | No | No |
| `a = new Student[5];` | Creates another array and reassigns variable `a` | **Yes: 1 new array** | No |
| `a[2] = null;` | Sets slot 2 to null | No | No |

**Subtle point:** `Student[] a;`, if it is a **local variable**, must be *definitely assigned* before being read. If it is an instance field or static field, it has a default value of `null` according to field initialization rules. In contrast, **the elements** of `new Student[3]` are already defaulted to `null` as soon as the array is created.

Code illustrating a compile-time error:

```java
// Inside a method:
Student[] local;
// System.out.println(local.length); // Error: local has not been assigned.
local = new Student[3];
System.out.println(local.length);      // Valid, prints 3.
```

An array variable of type `Student[]` is **not** a `Student`. You cannot call an instance method of `Student` directly on the entire array:

```java
// students.getName(); // Invalid if getName() is a method of Student.
students[0].getName(); // Syntactically valid if students[0] is non-null.
```

The valid line at the end can still throw `NullPointerException` when the element is `null`.

## 3. First Standalone Runnable Program: Counting Constructor Calls

Create the file **`StudentArrayBasicsDemo.java`** and run it with JDK 17+:

```java
class Student {
    private final String name;
    private static int created;

    Student(String name) {
        this.name = name;
        created++;
    }

    String getName() {
        return name;
    }

    static int getCreated() {
        return created;
    }
}

public class StudentArrayBasicsDemo {
    public static void main(String[] args) {
        Student[] students = new Student[3];

        System.out.println("array length=" + students.length);
        System.out.println("created=" + Student.getCreated());
        System.out.println("first null=" + (students[0] == null));

        students[0] = new Student("An");
        students[1] = new Student("Binh");
        students[2] = new Student("Chi");

        System.out.println("created=" + Student.getCreated());

        for (int i = 0; i < students.length; i++) {
            System.out.println(i + ": " + students[i].getName());
        }
    }
}
```

Compile and run:

```bash
javac StudentArrayBasicsDemo.java
java StudentArrayBasicsDemo
```

**Exact standard output:**

```text
array length=3
created=0
first null=true
created=3
0: An
1: Binh
2: Chi
```

Step-by-step explanation:

1. `new Student[3]` creates an array object with three `null` elements; no statement has called the `Student(String)` constructor yet, so `Student.getCreated()` returns `0`.
2. The three `students[i] = new Student(...)` statements execute three separate `new Student` expressions, creating three distinct `Student` objects; the constructor is called three times, so the `created` counter becomes `3`.
3. Each array element holds a reference to its corresponding object, so after the slots have been validly assigned, `students[i].getName()` calls the method on each object.
4. `students.length` is a **special field of the array** representing its length; `Student.getCreated()` is a static method declared by the Student class itself. The array length and the number of Student objects actually created **are not required to be equal**.

In Java, an array has a fixed length. You can **change the reference value inside each slot**, but you cannot change the value of `students.length` from 3 to 5.

## 4. Each Slot Defaults to null: Common Dereference Error

Example:

```java
Student[] students = new Student[2];
// System.out.println(students[0].getName());
```

After `new Student[2]`, `students` is **not null**, but `students[0]` and `students[1]` are **both null**. If you uncomment the second line and run it, the instance method call on `students[0]` will throw `NullPointerException`.

Three situations must be distinguished:

| Expression | State | Result/consequence |
| --- | --- | --- |
| `students == null` | Checks whether the **array variable** points to an array object | If true, `length` or `[i]` cannot be accessed yet |
| `students[0] == null` | Checks whether the **0th element** points to a Student object | If true, cannot call a Student instance method through that slot |
| `students[0].getName()` | Accesses the Student object through slot 0 | Requires a valid array variable and element, with the index within bounds |

An array that has been created **does not guarantee that each element has also been created**.

### Standalone Runnable Example: Checking for null in the Right Place

File **`ArrayNullDemo.java`**:

```java
class Entry {
    private final String text;

    Entry(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ArrayNullDemo {
    public static void main(String[] args) {
        Entry[] entries = new Entry[2];

        System.out.println(entries == null);
        System.out.println(entries[0] == null);

        entries[1] = new Entry("Ready");

        for (int i = 0; i < entries.length; i++) {
            if (entries[i] == null) {
                System.out.println(i + ": empty");
            } else {
                System.out.println(i + ": " + entries[i].text());
            }
        }

        try {
            entries[0].text();
        } catch (NullPointerException ex) {
            System.out.println("cannot call on null element");
        }
    }
}
```

Commands:

```bash
javac ArrayNullDemo.java
java ArrayNullDemo
```

```text
false
true
0: empty
1: Ready
cannot call on null element
```

**Reading the output:**

- `entries` points to an array object, so `entries == null` is `false`.
- `entries[0]` has not been assigned a Student/Entry object, so it remains `null`.
- `entries[1]` is initialized with `new Entry("Ready")`, allowing `text()` to be called.
- The `try/catch` block intentionally makes a call on a null slot to demonstrate the runtime error and catch it; the program does not print a stack trace because the exception is handled in the example.

The safe practical approach is to **ensure that all slots to be used have been initialized**, or **check for null explicitly** if the array is designed to allow empty slots. You should not use `try/catch NullPointerException` as a normal control-flow strategy.

## 5. Using a `for` Loop to Create Each Object Separately

When you need an array whose elements are all non-null, **create a separate object for each index**:

```java
Student[] students = new Student[3];

for (int i = 0; i < students.length; i++) {
    students[i] = new Student("S" + (i + 1));
}
```

Conceptual result:

```text
students ──> Student[] length=3
               [0] ─────> Student A {name="S1"}
               [1] ─────> Student B {name="S2"}
               [2] ─────> Student C {name="S3"}

A, B, and C are three objects with distinct identities.
```

Each loop iteration has a fresh `new Student(...)`, so the newly created object differs from those created by previous iterations. This is different from having only a single `new` and copying the same reference into multiple slots.

### Standalone Example Illustrating Identity

File **`IndependentElementsDemo.java`**:

```java
class Item {
    private String label;

    Item(String label) {
        this.label = label;
    }

    void rename(String next) {
        label = next;
    }

    String label() {
        return label;
    }
}

public class IndependentElementsDemo {
    public static void main(String[] args) {
        Item[] items = new Item[3];

        for (int i = 0; i < items.length; i++) {
            items[i] = new Item("item-" + i);
        }

        items[0].rename("changed");

        System.out.println(items[0].label());
        System.out.println(items[1].label());
        System.out.println(items[0] == items[1]);
        System.out.println(items[1] == items[2]);
    }
}
```

```bash
javac IndependentElementsDemo.java
java IndependentElementsDemo
```

```text
changed
item-1
false
false
```

Here every slot is assigned by **a `new Item(...)` statement in each iteration**; therefore, changing the label of the object at index 0 does not affect the object at index 1. The two `==` comparisons return `false` because the references at different indices point to different objects.

### Using `Arrays.setAll` When Creating Based on Index

Java provides the `java.util.Arrays.setAll` utility to assign each slot with the result of a function of the index:

```java
Student[] students = new Student[3];
java.util.Arrays.setAll(students, i -> new Student("S" + i));
```

This is a **valid code fragment inside a method**, assuming the `Student` class has a matching constructor. `setAll` calls the generator for each index, so the `new` expression inside the lambda creates a separate object each time. Note that the generator can return `null` or the same object if you write it that way; **`setAll` does not guarantee uniqueness on its own**. A regular `for` loop is easier to understand in the early stages of learning about references.

## 6. A Very Common Mistake: `Arrays.fill` Populates Multiple Slots with Only One Object

For reference arrays, `Arrays.fill` assigns **the same reference value** into the slots; it does not call the constructor multiple times on its own.

Create the file **`FillAliasDemo.java`**:

```java
import java.util.Arrays;

class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class FillAliasDemo {
    public static void main(String[] args) {
        Counter[] counters = new Counter[3];

        Arrays.fill(counters, new Counter(5));

        System.out.println(counters[0] == counters[1]);
        System.out.println(counters[1] == counters[2]);

        counters[2].value += 7;

        System.out.println(counters[0].value);
        System.out.println(counters[1].value);
        System.out.println(counters[2].value);
    }
}
```

```bash
javac FillAliasDemo.java
java FillAliasDemo
```

**Output:**

```text
true
true
12
12
12
```

Explanation:

1. `new Counter[3]` creates an array with three null slots.
2. In the call `Arrays.fill(counters, new Counter(5))`, the **argument expression** `new Counter(5)` is evaluated once to create **one Counter object**.
3. `fill` copies that same object reference into all three slots. Therefore, `counters[0] == counters[1] == counters[2]` in the sense that every pair references the same object.
4. The statement `counters[2].value += 7` changes **the single shared object** from 5 to 12; reading through slots 0, 1, and 2 all sees 12.

**Diagram:**

```text
counters ───> Counter[] length=3
                [0] ─────────┐
                [1] ─────────┼──> Counter A {value=12}
                [2] ─────────┘
```

If you need **three independent objects**, use a loop with `new Counter(5)` **inside the loop body**, or `Arrays.setAll(counters, i -> new Counter(5))`. `Arrays.fill` is only appropriate when you genuinely want every element to receive **the same value**, such as an immutable shared object or an intentional shared sentinel.

## 7. Assigning a Slot, Mutating Object State, and Reassigning the Array Variable

The following three statements affect **three different locations**:

```java
Item[] items = new Item[2];
items[0] = new Item("A");
Item[] aliasArray = items;

items[0].rename("B");            // Modifies the Item object at slot 0.
items[0] = new Item("C");        // Replaces the reference inside slot 0.
items = new Item[2];             // Replaces the reference in the items variable.
```

This is an **illustrative code fragment** assuming the `Item` class from the previous example.

Stage-by-stage diagram:

```text
1) After items[0] = new Item("A"):
items ─┐
       ├──> Array X: [0] ───> Item A {label="A"}, [1] ───> null
aliasArray ─┘

2) After items[0].rename("B"):
items ─┐
       ├──> Array X: [0] ───> Item A {label="B"}, [1] ───> null
aliasArray ─┘

3) After items[0] = new Item("C"):
items ─┐
       ├──> Array X: [0] ───> Item C {label="C"}, [1] ───> null
aliasArray ─┘

4) After items = new Item[2]:
items ───────────────> Array Y: [0]=null, [1]=null
aliasArray ──────────> Array X: [0] ───> Item C, [1]=null
```

**Distinguishing two levels of aliasing:**

- **Aliasing to the array:** `items` and `aliasArray` used to point to **the same Array X**, so replacing a slot of Array X via `items[0] = ...` can also be observed through `aliasArray[0]`.
- **Aliasing to an element:** two slots can both point to the same **Item object**, as in the `Arrays.fill` example. Changing the **state of the Item** through one slot will be observed through the other slot.
- **Reassigning the array variable:** `items = new Item[2]` does not switch `aliasArray` to Array Y because the assignment only changes the value of the `items` variable.

When drawing a diagram, you should draw both **the variable referencing the array** and **the arrow from each slot to the element object**; drawing only one level of arrows often leads to misunderstanding.

## 8. Initializing Directly in Array Syntax: Each `new` Creates Its Own Object

If you know the number of elements and their data in advance, you can create the array along with its elements using an **array initializer**:

```java
Student[] students = {
    new Student("An"),
    new Student("Binh"),
    new Student("Chi")
};
```

This shorthand syntax creates **one array object** and **three Student objects** (because there are three `new Student(...)` expressions).

In an expression rather than a declaration context, you can use the full form:

```java
Student[] students = new Student[] {
    new Student("An"),
    null,
    new Student("Chi")
};
```

This case creates one array object and **only two Student objects**, while the element at index 1 is `null`. The `{...}` syntax in an array declaration has its own usage scope; in contexts where a full expression is required (such as a method argument), write `new Student[] { ... }`.

### An Array Initializer Can Also Contain Aliases

```java
Student shared = new Student("Shared");
Student[] students = {shared, shared};
```

This syntax **does not create two Student objects**. There is one `new Student`, and both slots store a reference to that same object. The number of elements = 2, while the number of element objects created in the code snippet is only 1.

### A Complete Output Example

File **`ArrayInitializerDemo.java`**:

```java
class Label {
    private final String text;

    Label(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ArrayInitializerDemo {
    public static void main(String[] args) {
        Label shared = new Label("S");
        Label[] labels = {
            new Label("A"),
            shared,
            shared,
            null
        };

        System.out.println(labels.length);
        System.out.println(labels[0].text());
        System.out.println(labels[1] == labels[2]);
        System.out.println(labels[3] == null);
    }
}
```

```bash
javac ArrayInitializerDemo.java
java ArrayInitializerDemo
```

```text
4
A
true
true
```

The array has **four reference elements**, but the code creates only two `Label` objects: one `shared` object and one `"A"` object. Slots 1 and 2 both reference `shared`, and slot 3 is null.

## 9. Index Access and the `length` Property

Java arrays are indexed starting from **0**:

```text
Student[] array = new Student[4]

Valid indices:  0     1     2     3
               |     |     |     |
Slot:         null  null  null  null
```

For an array of length `n`, valid indices are `0` through `n - 1`. The length is read via `array.length`, **not** `array.length()`.

```java
Student[] students = new Student[4];

System.out.println(students.length); // 4
// students[4] = new Student("X");
// If run: ArrayIndexOutOfBoundsException.
```

This code snippet can be placed inside a method; the line causing a runtime error is commented out. In an array of length 4, index 4 is outside the range 0..3.

If the length used to create an array is negative:

```java
int count = -1;
// Student[] students = new Student[count];
// If run: NegativeArraySizeException.
```

**A zero-length array is also valid:**

```java
Student[] empty = new Student[0];
System.out.println(empty.length); // 0
```

There are no element slots and no `Student` objects are created, yet the expression `new Student[0]` still creates an **array object** with length 0. The expression `empty[0]` will exceed the index bounds.

### Be Careful with `array == null`

`Student[] students = null;` has no array object, so `students.length` will throw `NullPointerException`. In contrast, `Student[] students = new Student[0];` has a valid array object, `students.length == 0`, and can be handled as an empty array.

## 10. The for-each Loop: Reading Each Reference, Not Modifying Slots by Reassigning the Loop Variable

The enhanced `for` syntax is very convenient when you only need to **read/process** already-initialized elements:

```java
for (Student student : students) {
    if (student != null) {
        System.out.println(student.getName());
    }
}
```

Each iteration assigns the current **element value** to a **local variable** `student`. If you reassign this variable, **the array slot does not change**.

Create the file **`ForEachReferenceDemo.java`**:

```java
class Badge {
    String name;

    Badge(String name) {
        this.name = name;
    }
}

public class ForEachReferenceDemo {
    public static void main(String[] args) {
        Badge[] badges = {
            new Badge("A"),
            new Badge("B")
        };

        for (Badge badge : badges) {
            badge = new Badge("X");
        }

        System.out.println(badges[0].name);
        System.out.println(badges[1].name);

        for (Badge badge : badges) {
            badge.name = "changed";
        }

        System.out.println(badges[0].name);
        System.out.println(badges[1].name);
    }
}
```

```bash
javac ForEachReferenceDemo.java
java ForEachReferenceDemo
```

**Output:**

```text
A
B
changed
changed
```

Explanation:

- In the first loop, `badge = new Badge("X")` only reassigns the **local loop variable**. The slots `badges[0]` and `badges[1]` still hold their original references, so after the first loop it still prints `A` and `B`. The two `Badge("X")` objects created inside the loop are not stored in the array.
- In the second loop, `badge.name = "changed"` **modifies a field of the object** referenced by the `badge` variable. This is the same object whose reference is held by the array slot, so the change is observed after the loop.

To **replace array elements** with new objects, use an index-based `for` loop:

```java
for (int i = 0; i < badges.length; i++) {
    badges[i] = new Badge("X" + i);
}
```

This is an illustrative code snippet; it **actually overwrites each slot**.

## 11. Passing an Array to a Method: Still Pass-by-Value

Java always passes arguments by **value**, including parameters of array types. When calling a method with `Student[]`, Java copies the **reference to the array object** into the parameter.

A method can:

1. **Write to a slot** of the array object referenced by both the caller and the callee.
2. **Modify an element object** that a slot points to.
3. **Reassign the array parameter variable** to a new array, though this operation **does not make the caller's variable change its reference**.

File **`ArrayParameterDemo.java`**:

```java
class Score {
    int value;

    Score(int value) {
        this.value = value;
    }
}

public class ArrayParameterDemo {
    static void modify(Score[] parameter) {
        parameter[0].value += 4;
        parameter[1] = new Score(9);
        parameter = new Score[] {new Score(100)};
        System.out.println("inside length=" + parameter.length);
    }

    public static void main(String[] args) {
        Score[] scores = {new Score(1), new Score(2)};
        modify(scores);

        System.out.println("outside length=" + scores.length);
        System.out.println("first=" + scores[0].value);
        System.out.println("second=" + scores[1].value);
    }
}
```

```bash
javac ArrayParameterDemo.java
java ArrayParameterDemo
```

```text
inside length=1
outside length=2
first=5
second=9
```

Diagram during the call to `modify`:

```text
Initially:
scores ────────┐
               ├──> Array A: [0] -> Score(1), [1] -> Score(2)
parameter ─────┘

After parameter[0].value += 4:
scores ────────┐
               ├──> Array A: [0] -> Score(5), [1] -> Score(2)
parameter ─────┘

After parameter[1] = new Score(9):
scores ────────┐
               ├──> Array A: [0] -> Score(5), [1] -> Score(9)
parameter ─────┘

After parameter = new Score[]{new Score(100)}:
scores ─────────> Array A: [0] -> Score(5), [1] -> Score(9)
parameter ──────> Array B: [0] -> Score(100)
```

The statement `parameter = ...` only changes the reference of the **local parameter**, without changing the value of the `scores` variable in the caller. Before that, however, modifying the slot and the element state of **Array A** remains in effect after the method returns.

If you want a method to replace the caller's array, **return the new array reference** and let the caller assign it: `scores = replacement(scores);`. Do not say that Java uses "pass-by-reference" for arrays in the sense of allowing the callee to reassign the caller's variable.

## 12. Copying Reference Arrays: `clone` and `Arrays.copyOf` Are Shallow Copies

To create **another array object** while keeping the same element objects, you can use `clone()` or `Arrays.copyOf(...)`.

```java
Student[] original = {new Student("An"), new Student("Binh")};
Student[] copied = original.clone();
```

Diagram:

```text
original ──> Array A
               [0] ──────────┐
               [1] ───────┐  |
                            |  |
copied ────> Array B        |  |
               [0] ────────+--+--> Student #0 ("An")
               [1] ────────+------> Student #1 ("Binh")
```

**Exact meaning:**

- `original != copied` is `true` because there are **two array objects**.
- `original[0] == copied[0]` is `true` because the elements in both arrays still reference the same Student object.
- `copied[0] = new Student("Chi")` only replaces slot 0 of **Array B**; slot 0 of Array A is not reassigned.
- If `Student` is mutable and `copied[0].rename(...)` is called before replacing the slot, the shared object can change and be observed through `original[0]`.
- Using `Arrays.copyOf(original, original.length)` also creates a **shallow array copy** with copied element references.

### Standalone Program Comparing a Shallow Copy

File **`ShallowCopyDemo.java`**:

```java
import java.util.Arrays;

class Note {
    String text;

    Note(String text) {
        this.text = text;
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        Note[] original = {new Note("A"), new Note("B")};
        Note[] copied = Arrays.copyOf(original, original.length);

        System.out.println(original == copied);
        System.out.println(original[0] == copied[0]);

        copied[0].text = "changed";
        copied[1] = new Note("C");

        System.out.println(original[0].text);
        System.out.println(original[1].text);
        System.out.println(copied[1].text);
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
changed
B
C
```

The reason `original[0].text` also becomes `changed` is that both slots at index 0 point to **the same Note object**. Conversely, replacing `copied[1]` with a new Note only replaces the slot of the copied array, so `original[1].text` remains `B`.

### When Is a Deep Copy Needed?

If you want two arrays to have **independent element objects**, you must copy the elements according to the class's contract:

```java
Note[] deep = new Note[original.length];

for (int i = 0; i < original.length; i++) {
    Note source = original[i];
    deep[i] = source == null ? null : new Note(source.text);
}
```

This is a **code fragment** using `Note` from the example above. Each slot with a non-null source creates a new `Note`. However, a **true deep copy** depends on the object's structure: if a `Note` also holds a field referencing another mutable object, copying only `text` may not be sufficient for a complex graph. A copy constructor or copying mechanism suited to each class's invariants and sharing policy is required.

## 13. Multidimensional Object Arrays: Two Array Levels Before Element Objects

In Java, `Student[][]` is **an array of references to `Student[]` arrays**. A multidimensional array is not an indivisible "matrix" object; each row is a separate array object.

### Creating Both Dimensions

```java
Student[][] classes = new Student[2][3];
```

This expression creates:

- **One outer array** of length 2.
- **Two inner arrays**, each of length 3.
- **No Student objects**. The six `Student` slots inside the rows remain `null`.

Diagram:

```text
classes : Student[][]
   |
   v
Outer array (length 2)
   [0] ──> Row 0: [null] [null] [null]
   [1] ──> Row 1: [null] [null] [null]

Created: 1 outer array + 2 inner arrays
Not yet created: any Student objects
```

To create Student objects:

```java
for (int row = 0; row < classes.length; row++) {
    for (int col = 0; col < classes[row].length; col++) {
        classes[row][col] = new Student("S" + row + col);
    }
}
```

With this loop, the six slots are assigned six references to six new Student objects.

### Creating the Outer Array First, with Rows Still null

```java
Student[][] groups = new Student[2][];
```

In this case, **only the outer array exists**, and `groups[0]` and `groups[1]` default to `null`; there are no inner arrays yet.

```text
groups ──> Outer Student[][] length=2
             [0] ----> null (no row array yet)
             [1] ----> null (no row array yet)
```

You must create each row before using `groups[row][col]`:

```java
groups[0] = new Student[1];
groups[1] = new Student[3];

groups[0][0] = new Student("Solo");
groups[1][2] = new Student("Third");
```

This is a **jagged array** with row 0 of length 1 and row 1 of length 3. All other slots that have not been assigned an object remain `null`.

### Standalone Program: Distinguishing Null Rows from Null Elements

File **`TwoDimensionalStudentDemo.java`**:

```java
class Student {
    private final String name;

    Student(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class TwoDimensionalStudentDemo {
    public static void main(String[] args) {
        Student[][] groups = new Student[2][];

        System.out.println(groups.length);
        System.out.println(groups[0] == null);

        groups[0] = new Student[2];
        groups[1] = new Student[1];

        System.out.println(groups[0][0] == null);

        groups[0][0] = new Student("Mai");
        groups[0][1] = new Student("Nam");
        groups[1][0] = new Student("Lan");

        System.out.println(groups[0].length);
        System.out.println(groups[1].length);
        System.out.println(groups[0][0].name());
        System.out.println(groups[1][0].name());
    }
}
```

```bash
javac TwoDimensionalStudentDemo.java
java TwoDimensionalStudentDemo
```

```text
2
true
true
2
1
Mai
Lan
```

At `new Student[2][]`, only the outer array exists, so `groups[0] == null` is `true`. After `groups[0] = new Student[2]`, row 0 exists, but the slot `groups[0][0]` is still null. Only `new Student("Mai")` creates the Student object for that slot.

**Two different kinds of NPE to distinguish:**

- `groups[0] == null` and calling `groups[0].length` → there is no **inner array** to access.
- `groups[0] != null` but `groups[0][0] == null` and calling `groups[0][0].name()` → there is a row array, but the **Student object** is missing.

## 14. Object Arrays with Interfaces, Inheritance, and Polymorphism

Reference-type arrays are not limited to a single concrete class. An array declared with an **interface** or **superclass** type can hold references to objects whose runtime types are compatible.

File **`PolymorphicArrayDemo.java`**:

```java
interface Animal {
    String sound();
}

class Dog implements Animal {
    @Override
    public String sound() {
        return "woof";
    }
}

class Cat implements Animal {
    @Override
    public String sound() {
        return "meow";
    }
}

public class PolymorphicArrayDemo {
    public static void main(String[] args) {
        Animal[] animals = new Animal[3];

        animals[0] = new Dog();
        animals[1] = new Cat();
        animals[2] = new Dog();

        for (Animal animal : animals) {
            System.out.println(animal.sound());
        }
    }
}
```

```bash
javac PolymorphicArrayDemo.java
java PolymorphicArrayDemo
```

```text
woof
meow
woof
```

Points to distinguish:

- `new Animal[3]` is valid because it is creating **a reference array of interface type Animal**, not attempting `new Animal()`.
- `new Animal()` by itself is **invalid** because an interface cannot be instantiated directly.
- The three slots receive references to two `Dog` objects and one `Cat` object created separately.
- `animal.sound()` is an instance method call through the interface. Java selects the implementation according to the **runtime type of the receiving object** when the method is overridden/implemented; therefore, the same array can hold polymorphic behavior.
- If a slot is null, `animal.sound()` has no receiver and throws `NullPointerException`. You need to check for null or ensure complete initialization.

The `Animal` variables only hold a reference with **static type `Animal`**; they do not create an extra Animal wrapper layer or copy Dog/Cat.

## 15. Arrays Are Covariant: `ArrayStoreException` When Runtime Types Do Not Match

Java arrays of reference types are **covariant**. For example, a `String[]` can be used where the static type is `Object[]`, because `String` is a subtype of `Object`:

```java
String[] names = new String[2];
Object[] objects = names;
```

This does not create a new array object: `names` and `objects` are two variables pointing to **the same String[] array object**.

However, the runtime array type is still `String[]`. If an `Integer` is assigned into a slot through the `Object[]` variable, **the JVM blocks it at runtime** with `ArrayStoreException`.

File **`ArrayCovarianceDemo.java`**:

```java
public class ArrayCovarianceDemo {
    public static void main(String[] args) {
        String[] strings = new String[2];
        Object[] objects = strings;

        objects[0] = "Java";
        System.out.println(strings[0]);
        System.out.println(objects == strings);

        try {
            objects[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("wrong runtime element type");
        }

        System.out.println(strings[1] == null);
    }
}
```

```bash
javac ArrayCovarianceDemo.java
java ArrayCovarianceDemo
```

```text
Java
true
wrong runtime element type
true
```

Explanation: the static type `Object[]` allows the compiler to accept assigning an `Integer` in the example, but the actual array object is `String[]`. The runtime checks the **component type** and rejects storing the Integer. The slot `strings[1]` remains `null` after the assignment fails.

**Practical implication:** arrays of classes/interfaces have their element type checked at both **compile time** and **runtime**. Using generic collections such as `List<String>` generally avoids some of these covariance risks at compile time, though generics and arrays still have different rules; you should not use `Object[]` casts indiscriminately.

### Primitive Arrays Differ from Reference Arrays

`int[]` contains **primitive `int` values** in its slots, not `Integer` references. `Integer[]`, on the other hand, contains **references to Integer objects or null**. Java does not automatically turn `int[]` into `Integer[]` via boxing:

```java
int[] primitive = new int[2];       // [0,0]
Integer[] boxed = new Integer[2];   // [null,null]
```

The two array kinds have different element semantics and runtime types. In particular, `boxed[0]++` while the slot is still null can cause `NullPointerException` due to unboxing `null`, whereas `primitive[0]++` is a normal primitive increment.

## 16. `final` on Array Variables and Array Elements

If an array variable is declared `final`, it cannot be **reassigned** after being validly initialized, but **the slots can still be modified**:

```java
final Student[] students = new Student[2];

students[0] = new Student("A");
students[0] = new Student("B"); // Valid: replaces the slot.

// students = new Student[3];   // Error: reassigns a final variable.
```

`final` here protects **the arrow from the `students` variable to the array object**; it does not lock the slots inside the array object, nor does it automatically make the element objects immutable.

If you need to share data safely, consider:

- Providing read-only getters instead of directly returning an internal mutable array.
- Copying the array when receiving/returning data if you want to prevent the caller from modifying **the slots** of the internal array.
- If the element objects are also mutable, considering a defensive copy of **each element** or designing immutable elements.
- If using the array in multithreaded code, you need to add appropriate synchronization/access-coordination mechanisms; `final` alone does not guarantee that all mutations of slots and objects are safe.

## 17. Printing Arrays for Easy Observation: Do Not Rely on Arbitrary Addresses

If you write `System.out.println(students)` for a `Student[]`, Java uses the default text representation of the **array object** rather than automatically printing the list of student names. The default text value typically carries type and hash information, and is not stable enough to use as sample output.

Instead:

```java
System.out.println(java.util.Arrays.toString(students));
```

`Arrays.toString` iterates through the slots and builds a string of the form `[element0, element1, ...]`, calling `String.valueOf` appropriately on the references (including `null`). If an element is a custom object that has not overridden `toString()`, the string may still contain an unattractive default representation. Override `toString()` or use a loop calling getters when you want meaningful output.

File **`ArrayToStringDemo.java`**:

```java
import java.util.Arrays;

class User {
    private final String name;

    User(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return name;
    }
}

public class ArrayToStringDemo {
    public static void main(String[] args) {
        User[] users = {
            new User("An"),
            null,
            new User("Binh")
        };

        System.out.println(Arrays.toString(users));
        System.out.println(users.length);
    }
}
```

```bash
javac ArrayToStringDemo.java
java ArrayToStringDemo
```

```text
[An, null, Binh]
3
```

There are three slots, but only two `User` objects are created in the initializer. `Arrays.toString` does not automatically create missing element objects; it simply represents a null slot with the text `null` when building the result string.

For multidimensional arrays, `Arrays.deepToString` is generally more useful than `Arrays.toString` because it recursively represents nested arrays; caution is still needed if the object graph contains complex cycles.

## 18. When Should Slots Be Left `null`, and When Should All Be Initialized?

Having all elements initially `null` **is not an error by itself**. Correctness depends on the **design contract** of the array:

| Purpose | Appropriate strategy | Notes |
| --- | --- | --- |
| Need exactly `n` independent objects ready to use | Loop creating `new Element(...)` for each index | Cost of creating all objects; valid input data required |
| Slot represents "no data yet" | Leave as `null` and check before use | Avoid unchecked null dereferencing |
| Array is only used as a reference container populated gradually | `new Element[n]`, then assign each slot when data arrives | Track which slots are valid |
| Need to use the same sentinel object at every position | `Arrays.fill` with an immutable/shared sentinel | Reference sharing must be intentional |
| Want to copy the list of positions while keeping the same elements | `array.clone()` or `Arrays.copyOf` | This is a **shallow copy** |
| Want every element independent from the source | Create each new element object according to the copy contract | Can be expensive; avoid copying invariants incorrectly |
| Number of elements grows and shrinks frequently | Consider `ArrayList<Element>` | ArrayList still holds **references** and does not create element objects on its own |

There is no single strategy for every problem. For example, a system maintaining a cache may intentionally leave slots empty; whereas a student list requiring all `n` students needs every slot initialized/validated.

### Arrays Have a Fixed Size and Do Not Have `add()` Like `ArrayList`

`Student[] students = new Student[3]` has three slots; you can fill or replace those slots, but you cannot "append" a fourth element to that same array object with `students.add(...)`. If you need a larger array, create a new array and copy the references, or use an appropriate collection. Note that `ArrayList<Student>` also **does not automatically call `new Student(...)`** when creating the list; it only holds the object references that you actively add.

## 19. Common Mistakes When Learning Object Arrays

| Misconception | Correct understanding |
| --- | --- |
| "`new Student[3]` calls the Student constructor three times" | No: it only creates one array object with three null references |
| "`Student[]` directly contains three Student objects" | It contains **references** that can point to Student objects |
| "If the array is non-null, every element is non-null" | The array object exists, yet the slots can still be null |
| "`new Student[n]` means the same as repeating `new Student()` n times" | You must write a loop/initializer with separate `new Student(...)` calls |
| "`Arrays.fill(a, new Student(...))` creates n Students" | It evaluates one object as an argument and copies the same reference into the slots |
| "`a[0] = a[1]` copies the object" | It copies the reference, which can create an alias to the object |
| "`a[0].rename(...)` replaces the slot with a new object" | This is a method call on the object currently referenced by the slot |
| "`a[0] = new Student(...)` renames the old object" | It replaces the reference in the slot; the old object may still have other aliases |
| "`for (Student s : a) s = new Student(...)` fills the array" | Only reassigns the local variable `s`; to replace a slot, assign `a[i]` |
| "`a.clone()` clones all the Student objects" | It only clones the array object and copies the references |
| "`new Student[2][]` already has two row arrays" | Only the outer array exists; both row slots default to null |
| "`new Student[2][3]` already has six Students" | Outer + inner arrays exist, but the six Student slots are null |
| "`Student[]` cannot hold subtype instances" | It can store compatible subtypes according to type rules |
| "`Object[] x = new String[2]; x[0]=42` is safe" | The runtime array type is String[], so `ArrayStoreException` is thrown |
| "`int[]` and `Integer[]` are the same" | Primitive values differ from reference slots; `Integer[]` defaults to null |
| "`final Student[]` forbids changing elements" | It forbids reassigning the final variable, not changing the slots |
| "`array.length()` like `String.length()`" | Arrays use the `length` field; String uses the `length()` method |
| "Passing an array to a method is pass-by-reference" | Java is pass-by-value: a copy of the reference value to the array |
| "A null element is an empty Student object" | null means there is no target object |
| "Printing an array with println automatically outputs every element's name" | Use `Arrays.toString` or a loop + `toString`/getter |

## 20. Self-Check with Answers

**Question 1.** How many Student objects and how many array objects does `Student[] students = new Student[5];` create?

*Answer:* **0 Student objects**, **1 array object** of length 5 with five `null` slots.

**Question 2.** After the statement above, what does `students.length` return? What value does `students[0]` have?

*Answer:* `students.length == 5`; `students[0] == null` is true.

**Question 3.** How many Student objects have been created by `students[0] = new Student("An"); students[1] = students[0];`?

*Answer:* One Student object. Both slots 0 and 1 reference that same object.

**Question 4.** If `students[1].rename("Mai")` is called on a mutable Student, can `students[0]` observe the change?

*Answer:* Yes, because both slots point to the same object. The condition is that `rename` actually mutates the object's state rather than creating another object.

**Question 5.** Afterward, does `students[1] = new Student("Binh");` modify the reference in `students[0]`?

*Answer:* No. Slot 1 is assigned to a new object; slot 0 still points to the previous object.

**Question 6.** How many Student objects does `Arrays.fill(students, new Student("X"))` on an array of length 5 create from that new expression?

*Answer:* One. `fill` assigns the same reference into all five slots.

**Question 7.** If you want five independent objects with equal content, how should you write it?

*Answer:* A loop `for (int i=0;i<students.length;i++) students[i]=new Student("X");` to execute `new` five times, or a generator that genuinely creates a new object for each index.

**Question 8.** How many inner row arrays does `Student[][] table = new Student[2][];` have?

*Answer:* No row arrays yet; only an outer array of length 2, with both row slots `null`.

**Question 9.** How many Student objects does `Student[][] table = new Student[2][3];` have?

*Answer:* No Student objects. There is one outer array and two inner arrays with a total of six Student slots that are currently null.

**Question 10.** Why does `for (Student s : students) s = new Student("X");` fail to repopulate the elements?

*Answer:* `s` is a local variable that receives a copy of the reference from each slot; assigning `s` does not update the corresponding slot.

**Question 11.** Does `Student[] copy = students.clone();` guarantee `copy[0] != students[0]`?

*Answer:* No. `copy` is a different array object, but `copy[0]` and `students[0]` still hold the same reference at the time of copying, unless the data in the slots was already different by design.

**Question 12.** With `Object[] values = new String[2]; values[0] = Integer.valueOf(7);`, what error occurs?

*Answer:* `ArrayStoreException` at runtime because the actual array object is `String[]` and does not allow storing an Integer in the slot.

**Question 13.** Is `final Student[] items = new Student[2]; items[0]=new Student("A");` valid?

*Answer:* Yes. `final` forbids reassigning the `items` variable, not modifying array elements.

**Question 14.** Does `Student[] items = null; System.out.println(items.length);` create an array object or return 0?

*Answer:* It does not create an array object; accessing `length` through a `null` reference throws `NullPointerException`. Only `new Student[0]` creates a valid empty array with `length == 0`.

**Question 15.** If a method has parameter `Student[] p` and writes `p = new Student[10];`, does the array variable in the caller automatically change to the new array?

*Answer:* No. `p` is a copy of the reference value. The caller must receive a returned result and explicitly assign it if it wants to change the caller's variable.

## 21. Final Practice Exercise: Tracing Arrays and Two Levels of Aliasing

Read line by line, draw the arrows, and try to predict the output before looking at the solution.

Create the file **`ObjectArrayTraceDemo.java`**:

```java
class Node {
    int number;

    Node(int number) {
        this.number = number;
    }
}

public class ObjectArrayTraceDemo {
    public static void main(String[] args) {
        Node[] first = new Node[2];
        first[0] = new Node(1);
        first[1] = first[0];

        Node[] second = first;
        second[0].number += 4;

        first[1] = new Node(9);

        System.out.println(first == second);
        System.out.println(first[0] == first[1]);
        System.out.println(second[0].number);
        System.out.println(second[1].number);

        second = first.clone();
        second[0] = new Node(7);

        System.out.println(first == second);
        System.out.println(first[0].number);
        System.out.println(second[0].number);
        System.out.println(first[1] == second[1]);
    }
}
```

```bash
javac ObjectArrayTraceDemo.java
java ObjectArrayTraceDemo
```

**Result:**

```text
true
false
5
9
false
5
7
true
```

**Diagram-based solution:**

After `first[1] = first[0]`:

```text
first ──> Array A
            [0] ─────┐
            [1] ─────┴──> Node X {number=1}
```

After `Node[] second = first; second[0].number += 4`:

```text
first  ──┐
         ├──> Array A
second ──┘      [0] ────┐
                       ├──> Node X {number=5}
                 [1] ───┘
```

After `first[1] = new Node(9)`:

```text
first  ──┐
         ├──> Array A
second ──┘      [0] ─────────> Node X {number=5}
                 [1] ─────────> Node Y {number=9}
```

Because `first` and `second` still both point to Array A, `first == second` is true. Slot 0 and slot 1 now point to two different Nodes, so `first[0] == first[1]` is false. Reading through `second[0]` and `second[1]` returns 5 and 9, respectively.

After `second = first.clone()`:

```text
first  ──> Array A              second ──> Array B
            [0] ──┐                          [0] ──┐
                  ├──> Node X {number=5}           ┘ (same Node X)
            [1] ──┐                          [1] ──┐
                  ├──> Node Y {number=9}           ┘ (same Node Y)
```

After `second[0] = new Node(7)`:

```text
first  ──> Array A             second ──> Array B
            [0] ──> Node X {5}             [0] ──> Node Z {7}
            [1] ─────┐                     [1] ────┐
                     └──> Node Y {9} <─────────────┘
```

Now `first == second` is false because there are two array objects. `first[0].number` is still 5, `second[0].number` is 7, yet `first[1] == second[1]` remains true because `clone()` only copies the element references.

### Checklist Before Running Code with Object Arrays

1. Have you distinguished the **array variable** from the **array object** and **element objects**?
2. Does `new Element[n]` only create the array, or are there also `new Element(...)` expressions for each slot?
3. Which slots are still `null`? Does the code check for null before calling a method or reading a field?
4. Does each slot need an independent object, or is an object intentionally shared?
5. Is `Arrays.fill` used with a mutable object, causing all slots to become unintended aliases?
6. Is a for-each loop used to reassign the loop variable under the mistaken belief that it replaces the slot?
7. Do you understand the difference between **replacing the reference in a slot** and **mutating the object's state through a slot**?
8. When copying an array, have you distinguished between **shallow copy** and **deep copy**?
9. With `Element[][]`, have the **row arrays** been created before accessing `[row][col]`?
10. Have you properly considered `length`, valid indices, `ArrayIndexOutOfBoundsException`, and `null` at each level?
11. If using a supertype array, do you understand runtime component types and `ArrayStoreException`?
12. When passing an array into a method, have you remembered Java's **pass-by-value of references**?

---

**Takeaway:** `new Student[3]` creates **one array with three reference slots currently null**, not three Student objects. To have an object in a slot, you must assign **a reference to an existing object** or create an object with `new Student(...)` for that slot. Multiple slots can point to the same object, so state changes through one slot are observed through its aliases; conversely, reassigning one slot does not automatically change other slots. Arrays are fixed-length objects, passed by value of the reference, can be shallow-copied, and have their own type/index/null checks. Clearly distinguishing **array object, element reference, and element object** helps you read every diagram accurately and avoid most mistakes when using object arrays in Java.
