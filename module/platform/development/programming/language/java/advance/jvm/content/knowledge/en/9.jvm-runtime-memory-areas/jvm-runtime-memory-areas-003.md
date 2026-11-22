# JVM Heap: Where Objects and Arrays Are Stored, and the Difference Between Objects and Reference Variables

## Objectives

In the JVM execution model, the **heap** is a runtime data area shared among all threads, where **class instances and arrays** reside. However, a Java variable of a reference type such as `Person person` is not the `Person` object itself. The variable holds a **reference value**, which may point to an object or hold `null`. Reference variables can appear in local variables of a stack frame, in fields of another object, in static fields, or in elements of a reference array.

After this lesson, you will be able to:
- Clearly distinguish between **object/array**, **reference value**, and **reference variable**, without conflating the memory area of a variable with the memory area of an object.
- Understand the roles of the **heap**, **JVM stack/frame**, **local variables**, **static fields**, and the relationships among them.
- Describe `new`, field initialization, primitive/reference arrays, multidimensional arrays, aliasing, identity, and equality.
- Predict when assignment, method invocation, field modification, or variable reassignment changes observable state.
- Understand that Java **always passes arguments by value** — for reference parameters, the copy passed is the reference value.
- Accurately explain the relationship between **reachability** and garbage collection, without assuming that leaving scope or setting `null` immediately frees the heap.
- Distinguish **the model guaranteed by the JVMS** from implementation details/JIT optimizations such as escape analysis and scalar replacement.
- Use Java 17+ and `javap` to inspect this mechanism through runnable examples.

## 1. Overview Model: Heap, Stack Frame, and Reference Values

According to the Java Virtual Machine Specification (JVMS), the JVM has a **heap** shared among threads, containing **class instances and arrays**. Each thread has its own JVM stack, consisting of **frames** for methods currently being invoked; within a frame are **local variables** and an **operand stack**. Static fields themselves are associated with the runtime state of a class/interface, not with each created object.

Example:

~~~java
Person p = new Person("Lan");
~~~

This is an illustrative snippet, assuming a suitable `Person` class already exists. Semantically:

1. The expression `new Person("Lan")` creates a new `Person` instance, according to the JVM memory model.
2. The constructor initializes that instance's state; the string `"Lan"` is also a `String` object according to Java semantics, with its own literal/interning mechanism.
3. The value returned by the object creation expression is a **reference** to the instance.
4. The local variable `p` stores that **reference value**, not all the bytes of `Person` directly inside the variable.
5. If `p = null;` is executed afterward, the variable's value changes to null; **this does not mean the object is immediately deleted**.

Conceptual diagram:

~~~text
Thread A / JVM stack
  frame main()
  local variable "p"
        |
        | reference value
        v
            SHARED HEAP
        +-------------------+
        | Person instance   |
        | name ----+        |
        +----------|--------+
                   | reference
                   v
             +-------------+
             | String "Lan"|
             +-------------+

Thread B / JVM stack
  frame other()
  local variable "another" ----> (possibly the same Person instance)
~~~

The arrows represent **logical reference** relationships, **not** raw RAM addresses that the JVM is required to expose. An object can own primitive fields (storing primitive values) and reference fields (storing references to another object/array).

### Distinction Table

| Concept | Description | Example | Location in the Model |
| --- | --- | --- | --- |
| **Class instance** | An object with a class, identity, and instance fields | `new Person()` | Heap |
| **Array object** | An object with an array type, fixed length, and elements | `new int[3]` | Heap |
| **Local reference variable** | A slot containing a reference value or null | `Person p` in a method | Local variables of a frame |
| **Instance reference field** | A component of an object containing a reference | `person.address` | Inside the containing object |
| **Static reference field** | Runtime state of a class/interface containing a reference | `static Person current` | Belongs to runtime class; not an instance |
| **Reference-array element** | An element slot containing a reference/null | `people[0]` | Inside the array object |
| **Primitive local variable** | A slot containing a numeric/boolean/char value of the appropriate JVM type | `int count` | Local variables of a frame |
| **Primitive instance field** | A primitive value belonging to an object | `person.age` | Inside the object |
| **`null`** | A special reference value that refers to no object | `p = null` | Resides wherever a reference value is stored |

Do not assert that every Java variable always has an accessible “physical RAM cell”: the JVM/JIT is optimizing and may keep values in registers or eliminate certain unobservable storage. The table above is the **JVM semantic model**, not a guarantee about HotSpot's physical layout on every platform.

## 2. What Is the Heap? The Heap Is Not the JVM Stack

The **heap** is created by the JVM upon JVM startup. Threads within the same JVM share the heap according to the runtime model, and this area is the target of memory management/garbage collection. The JVMS does not mandate a specific GC algorithm, heap layout, generations, or allocation algorithm.

The **JVM stack** is a per-thread data area, with frames created/destroyed on method invocations/returns. A frame holds local variables and an operand stack, along with information necessary for the method. A **reference value in a frame** can point to an object residing on the heap.

Example:

~~~java
static int lengthOf(String text) {
    return text.length();
}
~~~

This is an illustrative method:
- The parameter `text` is a reference-typed local variable in the `lengthOf` frame.
- The value of `text` points to the String object provided by the caller (if not null).
- The call `text.length()` acts on the String instance through the reference; the JVM does not clone the String object just because it was passed as an argument.
- When the method finishes, the **frame is destroyed** according to the invocation model, but the String object is **not necessarily** destroyed: the caller or another object may still hold a reference to it.

Two statements that are often over-interpreted:
- “Local variables are on the stack, objects are on the heap” is a useful description for bytecode, **not** a promise by every JIT optimization regarding actual RAM location.
- “When a method ends, the object is reclaimed” is **false**: an object's lifetime depends on **reachability**, not solely on the scope of a single reference variable.

## 3. How Does a Reference Variable Differ from an Object?

Consider the following code:

~~~java
Box first = new Box(5);
Box second = first;
~~~

Suppose `Box` is a class with an instance field `int value`.

- `new Box(5)` creates **one** Box instance.
- `first` holds a reference to that instance.
- `second = first` **copies the reference value**; it does not allocate a new Box instance.
- Two different variables can point to the same object — this is called **aliasing**.

Diagram:

~~~text
first  -----+
            |
            +----> [Box object: value=5]
            |
second -----+
~~~

If `second.value = 12;` is executed, reading `first.value` will observe 12 in the normal sequential case: the two variables access the **same object**.

Conversely:

~~~java
Box a = new Box(5);
Box b = new Box(5);
~~~

creates two separate objects whose `value` fields are initially both 5. Two objects having identical state **do not necessarily have the same identity**. `a == b` returns false when two `new` expressions create two distinct objects.

### Reference Assignment Does Not Copy the Object

| Source Code | What Changes | Creates a New Object? |
| --- | --- | --- |
| `b = a;` | The reference value in variable `b` | No |
| `b = null;` | Variable `b` no longer references the object | No; nor does it destroy the object itself |
| `b = new Box(7);` | Creates a new Box, puts the new reference into `b` | Yes, per `new` expression semantics |
| `a.value = 10;` | The `value` field inside the object referenced by `a` | Not merely from assigning a primitive field |
| `a.child = b;` | The reference field `child` of object `a` points to `b`'s object | Does not create a copy of `b`'s object |
| `Box[] items = new Box[2];` | Creates an **array object** containing two reference elements defaulting to null | Yes, one array object; no Box element objects yet |

**Assigning a different reference** and **mutating an object's state** are two different actions. This is a key point when writing collections, APIs, and concurrent code.

## 4. Reference Values, null, and Equality

Java has **primitive values** and **reference values**. A reference value is a reference to an object/array or the `null` value.

~~~java
String text = null;
System.out.println(text == null); // true
~~~

This is a snippet inside a method. `null` is not a `Null` object created on the heap. Using null as the receiver of most field reads or method calls will result in a `NullPointerException`, for example:

~~~java
String text = null;
// text.length(); // Throws NullPointerException at runtime.
~~~

A reference can refer to an instance of a subclass, an object implementing an interface, or an array of a compatible type according to Java rules.

### Comparing Identity vs. Equality

- `a == b` with two **reference operands** checks whether they are the **same object reference** (or both null); it does not automatically compare field contents.
- `a.equals(b)` invokes a method, which can perform **content comparison** if the class overrides `equals` properly. If not overridden, `Object.equals` defaults to comparing by identity.
- `Objects.equals(a, b)` handles null safely and then uses `equals`; it is **not by default a deep comparison** of an object graph.
- `Arrays.equals(int[], int[])` or `Arrays.deepEquals(Object[], Object[])` have their own contracts; array objects generally do not override `Object.equals` to compare elements.
- `System.identityHashCode(object)` can assist in investigating identity, but it **does not guarantee every object has a distinct hash** and is not a heap address.

Example:

~~~java
String a = new String("hi");
String b = new String("hi");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

This is an illustrative snippet inside a method. The two `new String(...)` expressions create two String instances with different identities, but String overrides `equals` to compare content.

### Reference Equality with String Literals

Two literals with the same content `"java"` are interned according to String literal rules, so in a simple example:

~~~java
String first = "java";
String second = "java";
System.out.println(first == second); // true
~~~

Do not use that conclusion to infer that any two String objects with the same text are identity-equal: `new String("java")` creates a separate object. **The String intern pool is not a third kind of object outside the heap under a simple Java source rule**; the JVM still manages String objects according to runtime semantics. The intern/cache storage mechanism is an implementation and version detail.

## 5. Java 17+ Program: Aliasing, Rebinding, and Equality

Create the file **`HeapReferenceDemo.java`**:

~~~java
import java.util.Arrays;

public class HeapReferenceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 12;
    }

    static void rebind(Box box) {
        box = new Box(99);
    }

    public static void main(String[] args) {
        Box first = new Box(5);
        Box alias = first;
        Box other = new Box(5);

        System.out.println("sameRef=" + (first == alias));
        System.out.println("otherRef=" + (first == other));
        System.out.println("sameValue=" + (first.value == other.value));

        alias.value = 8;
        System.out.println("afterAlias=" + first.value);

        mutate(first);
        System.out.println("afterMutate=" + first.value);

        rebind(first);
        System.out.println("afterRebind=" + first.value);

        Box empty = null;
        System.out.println("isNull=" + (empty == null));

        int[] numbers = {1, 2, 3};
        int[] shared = numbers;
        shared[1] = 20;

        int[] copy = numbers.clone();
        copy[0] = 99;

        System.out.println("arraySame=" + (numbers == shared));
        System.out.println("cloneSame=" + (numbers == copy));
        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("copy=" + Arrays.toString(copy));
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac --release 17 HeapReferenceDemo.java
java HeapReferenceDemo
~~~

**Exact stdout:**

~~~text
sameRef=true
otherRef=false
sameValue=true
afterAlias=8
afterMutate=12
afterRebind=12
isNull=true
arraySame=true
cloneSame=false
numbers=[1, 20, 3]
copy=[99, 20, 3]
~~~

Explanation:

1. `alias = first` copies the reference, so `sameRef=true`.
2. `new Box(5)` in `other` creates a different object; the `value` fields are equal, but their identities differ.
3. `alias.value = 8` modifies the **shared object**, so reading from `first` returns 8.
4. `mutate(first)` receives a copy of the reference and modifies the object, so `first.value` becomes 12.
5. `rebind(first)` only changes the **local parameter variable `box`** inside the method; `first` in the caller still points to the old Box, whose value remains 12.
6. `empty = null` is unrelated to the identities of the other Boxes.
7. `shared = numbers` creates an alias to the same array; changing an element via `shared` changes `numbers`.
8. `numbers.clone()` creates a new array object; because the `int[]` array contains primitive values, the elements are copied by value. Changing `copy[0]` does not change `numbers[0]`.

**Deterministic scope:** the program executes sequentially and does not depend on GC timing or object addresses, so the printed output is stable under Java 17+.

## 6. Java Passes Arguments by Value, Even When They Are References

A misleading statement is “Java passes objects by reference”. The accurate way to put it:

> Java passes **the value of the argument expression** into the parameter. For a reference variable, the copied value is the **reference value** to the object; both the caller and callee can operate on the same object.

From this arise two phenomena:

~~~text
Caller: first ------> [Box value=5]

mutate(first):
  parameter box ----> same Box
  box.value = 12     -> modifies shared object

rebind(first):
  parameter box ----> same Box (initially)
  box = new Box(99)  -> only local box changes to a different object
  caller first -----> still points to the original Box
~~~

**It is not call-by-reference** in the sense that the callee can reassign the caller's original variable simply by assigning to the parameter. If the caller wants to change its reference variable, the method can return the new reference value and the caller can assign it itself:

~~~java
static Box replace(Box original) {
    return new Box(99);
}

// Inside a method:
first = replace(first);
~~~

This is an **illustrative** snippet that needs to be placed inside the same class that defines `Box`. The caller's variable only changes when it executes `first = ...` itself. Returning a reference does not copy the entire object.

### Example: `swap` Does Not Swap the Original Variables

~~~java
static void swap(Box a, Box b) {
    Box temp = a;
    a = b;
    b = temp;
}
~~~

This is an illustrative method. It swaps **two local reference values in `swap`'s frame**, without modifying the caller's two variables. If the goal is to swap the contents of the Boxes, one can mutate their fields (which changes object state), or the caller can swap its variables directly.

## 7. Arrays Are Objects on the Heap

Arrays in Java are not just a special chunk of data “outside the object system”; every array is an **object** with:
- A **runtime array class** matching its component type and dimensions.
- Its own **identity**.
- A fixed `length` after allocation.
- Elements holding primitive or reference values according to the component type.
- Elements initially receiving **default values**.
- The ability to be referenced by local variables, fields, or other arrays.

### Primitive Arrays

~~~java
int[] scores = new int[3];
System.out.println(scores.length);  // 3
System.out.println(scores[0]);      // 0
~~~

This is a snippet inside a method. `new int[3]` creates an array object containing three **int values** defaulting to 0; **it does not create three `Integer` objects**.

Examples:
- `new boolean[2]`: two `false` elements.
- `new double[2]`: two `+0.0d` elements.
- `new char[2]`: two NUL elements (code unit 0).

### Reference Arrays

~~~java
Box[] boxes = new Box[2];
System.out.println(boxes[0] == null); // true

boxes[0] = new Box(10);
boxes[1] = boxes[0];
System.out.println(boxes[0] == boxes[1]); // true
~~~

This is an illustrative snippet using the defined `Box` class, placed inside a method. `new Box[2]` **only creates an array containing two reference elements defaulting to null**. You must call `new Box(...)` separately if you want to create Box instances. Assigning the second element to the first creates **aliasing between two slots in an array**.

Diagram:

~~~text
boxes ------> [Box[] array length=2]
                   [0] ---+
                           +--> [Box value=10]
                   [1] ---+
~~~

Changing `boxes[0].value = 20` causes reading `boxes[1].value` to return 20, because it is the same object.

### Array Length and Data Size

- `array.length` has a fixed value for **that array object** after allocation.
- We can reassign the reference variable: `array = new int[10];` points to a new array object; it does not “grow” the old array itself.
- `new int[-1]` throws `NegativeArraySizeException`; no array is created.
- Accessing outside the range `0..length-1` throws `ArrayIndexOutOfBoundsException`.
- Accessing `arr.length` when `arr == null` throws `NullPointerException`.
- Array objects also have a type and members according to Java rules. `length` is not a user-defined mutable instance field; in bytecode it is read by the **`arraylength`** opcode, not a regular `getfield`.

## 8. Two-Dimensional Arrays Are Actually Arrays of Arrays

When writing:

~~~java
int[][] table = new int[2][3];
~~~

in the Java model, `table` references an **outer array** consisting of two references to **two inner `int[]` arrays**, each of length 3. Java supports uneven arrays (*jagged arrays*).

~~~text
table ---> int[][] outer array, length=2
                |
                +-- [0] ---> int[] length=3: [0, 0, 0]
                |
                +-- [1] ---> int[] length=3: [0, 0, 0]
~~~

There are **three array objects** semantically: one outer array and two inner arrays. One must not conclude with certainty that two-dimensional array data must lie in a contiguous rectangular matrix in physical addresses.

In particular:

~~~java
int[][] rows = new int[2][];
System.out.println(rows[0] == null); // true
rows[0] = new int[] {7};
rows[1] = new int[] {8, 9};
System.out.println(rows[0].length);  // 1
System.out.println(rows[1].length);  // 2
~~~

This is a snippet inside a method. `new int[2][]` only creates the **outer array**, without automatically allocating inner arrays. This approach creates an array of rows with different lengths.

### Array Covariance and Runtime Store Check

Reference arrays in Java are **covariant**. For example, `String[]` can be assigned to a variable of type `Object[]`:

~~~java
Object[] items = new String[1];
items[0] = "ok";
~~~

That is valid; however:

~~~java
Object[] items = new String[1];
// items[0] = Integer.valueOf(3); // ArrayStoreException at runtime.
~~~

This is an illustrative snippet, with the exception line commented out so as not to break a normally running program. Even though the **variable** is declared as `Object[]`, the **actual array object** has component type `String`. The JVM checks reference element assignment against the runtime array type, so attempting to store an Integer will throw `ArrayStoreException`.

Primitive arrays do not have similar covariance: `int[]` cannot be assigned to `Object[]`, even though `int[]` itself is an object and can be assigned to an `Object` variable.

## 9. Complete Java 17+ Example: Primitive, Reference, and Multidimensional Arrays

Create the file **`HeapArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class HeapArrayDemo {
    static final class Node {
        int number;

        Node(int number) {
            this.number = number;
        }
    }

    public static void main(String[] args) {
        int[] primitives = new int[3];
        Node[] references = new Node[2];

        System.out.println("primitiveDefault=" + primitives[1]);
        System.out.println("referenceDefault=" + (references[0] == null));

        Node node = new Node(6);
        references[0] = node;
        references[1] = node;
        references[0].number = 10;

        System.out.println("sameNode=" + (references[0] == references[1]));
        System.out.println("nodeValue=" + references[1].number);

        int[][] rows = new int[2][];
        System.out.println("unallocatedRow=" + (rows[0] == null));

        rows[0] = new int[] {7};
        rows[1] = new int[] {8, 9};
        System.out.println("rowSizes=" + rows[0].length + "," + rows[1].length);
        System.out.println("row0=" + Arrays.toString(rows[0]));

        Object[] covariant = new String[1];
        covariant[0] = "ok";

        try {
            covariant[0] = Integer.valueOf(3);
        } catch (ArrayStoreException expected) {
            System.out.println("storeCheck=ArrayStoreException");
        }
    }
}
~~~

Commands:

~~~bash
javac --release 17 HeapArrayDemo.java
java HeapArrayDemo
~~~

**Exact stdout:**

~~~text
primitiveDefault=0
referenceDefault=true
sameNode=true
nodeValue=10
unallocatedRow=true
rowSizes=1,2
row0=[7]
storeCheck=ArrayStoreException
~~~

Explanation:
- `new int[3]` allocates an array object with `int` elements defaulting to 0.
- `new Node[2]` allocates an array object with reference elements defaulting to null; only `new Node(6)` creates a Node instance.
- Two reference elements hold references to the same Node, so modifying via element 0 is visible via element 1.
- The outer array `new int[2][]` has null elements until inner arrays are assigned.
- The runtime type of `covariant` is `String[]` despite the variable type `Object[]`, so storing an Integer is blocked.

**Does not depend** on GC or JIT mode to produce the stdout above.

## 10. A `final` Variable Does Not Make the Object Immutable

A reference variable/field can be `final`, for example:

~~~java
final int[] numbers = {1, 2, 3};
numbers[0] = 99; // Valid.
// numbers = new int[3]; // Invalid: reassigning a final variable.
~~~

This is a snippet inside a method. `final` on a reference variable **prevents reassigning the variable itself**, not automatically guaranteeing that the object it references is immutable.

With a class:

~~~java
class Holder {
    final int[] data = new int[2];
}
~~~

Another variable/field can still hold a reference to the same array and modify its elements, unless designed defensively. To provide practical immutability, the entire design must be considered: defensive copies, APIs that do not expose mutable internals, immutable value types, and appropriate concurrency rules.

Similarly, `final Box box` can keep the reference stable, but `box.value` can still change if `Box` is a mutable type.

## 11. Copying Arrays and Copying Objects

**Copying a reference** ≠ **copying an object**. And **cloning an array** is usually a **shallow copy** for reference elements.

~~~java
Node[] original = {new Node(1)};
Node[] copy = original.clone();

System.out.println(original == copy);        // false
System.out.println(original[0] == copy[0]);  // true
~~~

This is a snippet with a `Node` class having a suitable constructor inside a method. `clone()` on an array creates a new array object and copies the element values. Because the element type is a reference, the copied value is the **reference to Node**, so both arrays point to the first Node.

To deep-copy an object graph, a domain-specific policy for copying the inner objects is needed. There is no default behavior where “calling clone or assigning” always deep-copies an entire reference tree. For graphs with cycles or shared subobjects, deep copying also requires rules for preserving or not preserving sharing and tracking identity.

### Difference Between `Arrays.copyOf` and Assignment

- `copied = original;` only aliases; it does not create a new array.
- `copied = Arrays.copyOf(original, original.length);` creates a new array (for an appropriate array type), but reference elements are still copied reference values.
- `copied = original.clone();` creates a new array with copied element values.
- `new int[10]` creates an array with default values; it does not copy old data unless elements are assigned/copied.

## 12. GC and Reachability: When Can an Object Be Reclaimed?

**Garbage collection (GC)** manages objects that are no longer needed based on *reachability*. An object can be reclaimed when it is no longer reachable from **GC roots** according to the VM's model/algorithm. The JVM **does not guarantee a specific point in time** at which an object's memory will be reclaimed.

Typical roots or sources holding references in JVM implementations include live references in thread stacks/frames, static fields reachable through runtime classes, JNI/native handles, and appropriate runtime structures. The exact root list and liveness algorithm belong to the VM/GC implementation; do not treat a simplified diagram as a mandatory specification for every collector.

Example:

~~~java
Box a = new Box(1);
Box b = a;            // Two references to the same object
a = null;             // b still points to Box.
b.value = 2;          // Box is still usable.
b = null;             // No more references through these two variables.
~~~

This is an illustrative snippet in a method. After `a = null`, the object is **still reachable through `b`**. After `b = null`, the object *may* become unreachable, **if no other references remain** and the JVM does not keep a reference live for an appropriate reason. One must not conclude that right at that semicolon, heap memory must immediately be returned to the operating system.

### Misconceptions About GC

- `reference = null` **does not directly invoke deallocation**; it only changes a reference variable/field.
- An object does not necessarily disappear when a local variable goes out of scope: the reference may have been stored in a static field, another object, an array, or elsewhere.
- An object still held in a source-level variable does not necessarily force the JVM to keep the object until the end of the method if the variable is no longer used in execution; GC/JIT can perform liveness analysis.
- Java does not guarantee the order or timing of finalization or GC; **do not design business logic around reclamation timing**.
- `System.gc()` is only a **request/hint** for GC depending on API/VM configuration, not a guarantee to immediately reclaim a specific object.
- Memory leaks can still occur in the sense of **references inadvertently keeping objects reachable**, such as unbounded static caches, accumulating collections, unregistered listeners, or long-lived thread-locals.

### `WeakReference` Is Not a Collection-Timing Measurement

`WeakReference<T>` allows weak references with specific semantics, but the time when the referent is cleared/collected is **non-deterministic**. Therefore, do not use:

~~~java
System.gc();
// System.out.println(weak.get() == null); // No guaranteed stdout result.
~~~

This is an illustrative snippet with the check line commented out. If you need to manage **resources outside the heap** such as sockets/files, use try-with-resources or an appropriate close API; **do not wait for GC** to close resources on time.

## 13. Object Graphs, Memory Regions, and Memory Leaks

Objects containing reference fields and reference arrays form a **reference graph** on the heap:

~~~text
GC root: static Registry
          |
          v
      [Registry object]
          |
          +--> list --------> [ArrayList backing array]
                                  |
                                  +--> entry0 -> [Session object]
                                  +--> entry1 -> [Session object]
                                  +--> entry2 -> [Session object]
~~~

If the application forgets to remove expired `Session` objects from the registry, those objects may remain reachable and GC cannot reclaim them as “garbage,” even though business logic no longer needs them. This is a **logical memory leak**.

Principles:
1. Identify **who owns** references to objects.
2. Avoid holding large objects in unbounded static caches.
3. Enforce eviction/TTL limits for caches and remove listeners/registrations when unused.
4. Inspect heap dumps with profilers/diagnostic tools when needed to find retainers and paths from GC roots.
5. Do not treat setting a local reference to null as a leak fix if long-lived references remain elsewhere.

For an inspection workflow, use real data (instance counts, retained heap, GC roots) rather than just looking at how many times `new` is called in source code.

## 14. JIT, Escape Analysis, and the Limits of “Objects Are Always on the Heap”

**At the JVM specification level**, the heap is the runtime area where class instances and arrays are semantically allocated. However, modern JVM implementations can optimize when the result **does not change observable behavior**.

Example:

~~~java
static int total(int a, int b) {
    Pair pair = new Pair(a, b);
    return pair.first + pair.second;
}

static final class Pair {
    final int first;
    final int second;

    Pair(int first, int second) {
        this.first = first;
        this.second = second;
    }
}
~~~

This is an **illustrative snippet to be placed inside a class**. In the Java model, `new Pair` creates an instance. A JVM JIT may perform escape analysis and eliminate physical object allocation via **scalar replacement**, because only the values of the two fields are needed for the result. However:
- **Do not assert** that the JIT is guaranteed to optimize this example on every run, JVM, configuration, or compilation tier.
- Optimizations must not break identity/equality or change observable side effects.
- Do not state with certainty that “the `Pair` object moves to the stack” just because of escape analysis. The JVM may eliminate the allocation, scalarize it, or use another strategy; “stack allocation” is not a mandatory public Java semantic.
- When an object escapes to another thread, is returned, or is used in a way where identity is observable, optimization conditions differ.

Therefore, the accurate educational statement is: **the JVM models class instances and arrays on the heap; actual physical storage is subject to valid optimizations**. Saying “every Java object must always occupy a separate block of heap RAM” is too rigid with respect to the JIT.

## 15. Static References Can Also Point to Objects on the Heap

Example:

~~~java
class AppState {
    static final int LIMIT = 100;
    static Box current = new Box(7);
}
~~~

This is an illustrative class. Distinguish:
- `LIMIT` is a static primitive field (and may be a constant variable), not an `Integer` heap object.
- `current` is a **static reference field** belonging to the runtime class.
- The expression `new Box(7)` creates a Box object semantically on the heap.
- The field `current` holds the reference value to the Box, not the entire Box object.
- If `current` continues to hold the reference to the Box, that object may remain reachable through static state, affecting its lifetime.

Which runtime data structures the JVM uses to manage static fields is an implementation detail. Do not treat a static variable as “an object residing on the heap” merely because the static field has a reference type.

### Object References Can Reside Inside the Heap

With:

~~~java
class Node {
    Node next;
    int value;
}
~~~

a `Node` object has a reference-typed field `next` **inside the `Node` object itself**; the `Node` object, in the JVM model, resides on the heap. Therefore, not **every reference** “resides on the stack.” Reference values can reside in object fields, array elements, static fields, or local frames.

## 16. Java Bytecode Related to the Heap and Reference Values

The Java compiler typically emits the following opcodes when creating/accessing objects and arrays:

| Opcode | Role | Java Example |
| --- | --- | --- |
| `new` | Create a class instance before constructor initialization completes | `new Box(5)` |
| `invokespecial` | Invoke the `<init>` constructor under corresponding rules | `new Box(5)` |
| `newarray` | Create a one-dimensional array of primitives | `new int[3]` |
| `anewarray` | Create an array of a reference component type | `new Box[2]` |
| `multianewarray` | Create a multidimensional array with specified dimensions | `new int[2][3]` |
| `aload` / `astore` | Load/store a **reference value** from/into a local variable | `Box b = ...` |
| `getfield` / `putfield` | Read/write an instance field by symbolic reference | `b.value` |
| `getstatic` / `putstatic` | Read/write a static field | `AppState.current` |
| `aaload` / `aastore` | Read/write reference elements in an array | `boxes[0]` |
| `iaload` / `iastore` | Read/write int elements in an array | `numbers[0]` |
| `arraylength` | Read the length of an array | `arr.length` |
| `if_acmpeq` / `if_acmpne` | Compare two reference values by identity | `a == b` |
| `ifnull` / `ifnonnull` | Check whether a reference is null | `b == null` |
| `checkcast` / `instanceof` | Check/cast a reference type per JVM rules | `(Box)obj`, `obj instanceof Box` |

An illustrative disassembly snippet:

~~~text
new           #7     // class Box
dup
iconst_5
invokespecial #9     // Box.<init>:(I)V
astore_1             // Store reference into local variable
aload_1              // Load reference from local variable
getfield      #12    // Box.value:I
~~~

The indices `#7/#9/#12` are **illustrative**, not fixed indices. The `new` instruction creates the instance; `dup` keeps an appropriate reference for the constructor call and assignment; `astore` stores the reference value in the slot, **without copying the Box object**.

For arrays:

~~~text
iconst_3
newarray int
astore_2

aload_2
iconst_0
iaload
~~~

This is also a bytecode diagram, not an exact dump. It shows that `newarray` creates the array object; `astore_2` only stores the reference; `iaload` reads the int element.

### Practicing with `javap`

After compiling the examples above:

~~~bash
javap -c -p HeapReferenceDemo
javap -c -p HeapArrayDemo
javap -v -p HeapReferenceDemo
~~~

Observe in `main`:
1. `new`/`invokespecial` instructions to create Box/Node.
2. `astore`/`aload` when assigning or passing reference values.
3. `getfield`/`putfield` when reading/writing primitive fields of Box/Node.
4. `newarray`, `anewarray`, and element load/store opcodes.
5. `if_acmp*` or `ifnull/ifnonnull` in reference checks.
6. Calls such as `Arrays.toString` or `PrintStream.println` use invoke opcodes; do not confuse them with field/array access instructions.

Do not force a “one Java expression = one JVM opcode” mapping: the compiler may constant-fold, use auxiliary instruction sequences, or the JIT may optimize at execution time. What the JVM must guarantee is the **semantics** of the program.

## 17. Heap Sizing, GC, and Diagnostic Tools

In common HotSpot/JDK distributions, you can configure heap limits with flags such as:
- `-Xms<size>`: initial heap size (depending on JVM implementation).
- `-Xmx<size>`: maximum heap size.
- `-Xlog:gc` or `-Xlog:gc*`: log GC activity (with unified logging in modern HotSpot/JDK).

Illustrative example (no fixed stdout because it depends on the collector and program):

~~~bash
java -Xms64m -Xmx256m -Xlog:gc -cp . HeapReferenceDemo
~~~

Additional monitoring information you can use:
- **JFR (Java Flight Recorder)** to inspect allocations and GC behavior.
- **JDK Mission Control** or a suitable profiler to view heap usage and retained objects.
- **jcmd** with diagnostic commands supported on a specific JVM; syntax/availability depends on version.
- **Heap dump** to investigate object graphs, classloaders, and paths to GC roots; be mindful of sensitive data in dumps.

Distinguish the following situations:
- `java.lang.OutOfMemoryError: Java heap space` usually indicates the heap could not allocate enough for a request at that moment, though the cause may be a constrained heap, an allocation peak, or objects held for too long.
- Not every `OutOfMemoryError` originates from the Java heap: native memory, metaspace, direct buffers, thread creation, etc. may be involved.
- Increasing `-Xmx` may mask the symptom rather than solve object retention/leaks; **retained heap** and reference paths should be measured.
- Memory “not dropping immediately on the OS” does not prove objects are still alive: the JVM may retain committed heap for reuse.

## 18. Common Misconceptions

| Statement | Accurate Understanding |
| --- | --- |
| “`Box a = new Box()` means the entire Box resides directly inside variable `a` on the stack.” | Variable `a` holds a **reference value**; the object is allocated under heap semantics. |
| “Assigning `b = a` creates a new Box copy.” | It only copies the reference; `a` and `b` can alias the same object. |
| “Java passes objects by reference, so the callee assigning the parameter changes the caller's variable.” | Java is **pass-by-value**; the callee only receives a copy of the reference. |
| “Two objects have equal fields, so `==` is true.” | `==` on references checks identity; logical equality must use an appropriate method. |
| “`new Box[5]` creates five Box instances.” | It only creates one array containing 5 references defaulting to null. |
| “Primitive arrays contain `Integer`/`Double` objects.” | `int[]` contains `int` values; `double[]` contains `double` values, without boxing each element. |
| “A 2D array is a single matrix object.” | In the Java model, it is an array of references to sub-arrays; row lengths can differ. |
| “`final Box b` makes the Box immutable.” | `final` prevents reassigning the variable/field; the Box itself may be mutable. |
| “Cloning a reference array deep-copies all objects.” | By default it shallow-copies element references. |
| “`reference = null` immediately frees the heap.” | It only changes the reference; GC decides when to reclaim based on reachability. |
| “Leaving a method destroys the object along with the frame.” | When the frame ends, the object may still be reachable from elsewhere. |
| “Every reference is always on the stack.” | Reference values can reside in fields, static fields, and array elements. |
| “Every physical object must be on the heap with a fixed address.” | JVM semantics place objects on the heap; JIT can optimize allocation/scalar replacement. |
| “A static reference in a class is the object it points to itself.” | The static field holds a reference; the referent is a separate object. |
| “A shared heap means multi-threaded object modification is always thread-safe.” | A shared heap does not guarantee atomicity/visibility; the Java Memory Model and proper synchronization are required. |
| “`System.gc()` guarantees the object disappears immediately.” | It is only a hint; GC timing is non-deterministic. |

## 19. Self-Check Questions

**Question 1.** `Box a = new Box(1); Box b = a;` — how many new Box instances are created?

**Answer:** **One**, from the expression `new Box(1)`. `b = a` only copies the reference value.

**Question 2.** If `b.value = 5`, what will `a.value` be in the example above?

**Answer:** **5**, because both variables reference the same Box object (when running sequentially, with no other modifications).

**Question 3.** Why does the method `rebind(Box b) { b = new Box(9); }` not change the caller's reference?

**Answer:** Java is pass-by-value: parameter `b` is only a **copy of the reference**. Reassigning the parameter does not change the source variable in the caller.

**Question 4.** Does `Box[] boxes = new Box[3];` create three Box objects?

**Answer:** **No.** It creates one `Box[]` array object with three element references defaulting to null.

**Question 5.** Does `int[] xs = new int[4];` contain four `Integer` objects?

**Answer:** **No.** It contains four primitive `int` values defaulting to 0.

**Question 6.** How many array objects does `int[][] grid = new int[2][3];` have under normal semantics?

**Answer:** **Three**: one outer array of length 2 and two inner `int` arrays of length 3.

**Question 7.** What about `int[][] grid = new int[2][];`?

**Answer:** Initially there is **one outer array**, its two reference elements are null, and there are no inner arrays yet.

**Question 8.** Do `a == b` and `a.equals(b)` have the same meaning for references?

**Answer:** No. `==` compares identity; `equals` is a method that can be overridden to compare content, depending on the class.

**Question 9.** Does setting variable `a = null` while `b` still points to the same object free the object?

**Answer:** No. The object is still reachable through `b`; even if no references remain, GC does not guarantee immediate reclamation.

**Question 10.** Which references can reside in the heap?

**Answer:** Reference values in **instance fields and reference-array elements** can reside inside heap objects. Not every reference resides only in stack frames.

**Question 11.** Does JIT scalar replacement make Java “have no heap anymore”?

**Answer:** No. The heap is part of the JVM model; optimizations are only performed when observable semantics are preserved, and there is no guarantee they apply to every object.

**Question 12.** What does `final int[] numbers` do?

**Answer:** It prevents reassigning the corresponding reference variable/field, but **does not prevent modifying the elements** of the array.

**Question 13.** Why can `Object[] objects = new String[1]` throw `ArrayStoreException`?

**Answer:** The actual runtime array object has component type `String`; the JVM checks element stores, rather than relying solely on the variable's declared `Object[]` type.

**Question 14.** Is a `static Box shared` variable a Box object placed inside the static field?

**Answer:** No. The static field stores a **reference value**. The referent Box object is a separate entity in the heap model.

**Question 15.** Does a heap shared among threads guarantee that `counter++` on an object's field executes atomically?

**Answer:** No. Read–modify–write operations require synchronization or atomic operations when concurrent updates occur.

## 20. Mental Map

~~~text
                    JVM RUNTIME DATA AREAS
                +----------------------------+
                | HEAP (shared by threads)   |
                |  - Class instances         |
                |  - Array objects           |
                |  - Object graphs           |
                +----------------------------+
                     ^                ^
                     |                |
       reference value                reference value
                     |                |
   +-----------------+----+       +---+------------------+
   | THREAD A / FRAME     |       | STATIC FIELD /      |
   | local variable       |       | INSTANCE REF FIELD  |
   | operand stack        |       | / ARRAY REF ELEMENT |
   +----------------------+       +----------------------+

new Box()       -> class instance on the heap (semantically)
new Box[3]      -> array object, three null refs
new int[3]      -> array object, three primitive ints 0
b = a           -> copy reference, DO NOT copy object
b.value = 10    -> mutate the object pointed to by the reference
method(b)       -> copy reference value into parameter
b = null        -> change reference, NOT immediate free
GC              -> based on reachability, not on a single semicolon
JIT             -> may optimize allocation, preserving semantics
~~~

**Conclusion:** **Objects/arrays** and **reference variables** are two separate concepts. The heap stores class instances and arrays in the JVM model; references can reside in local frames, fields, or array elements. Understanding aliasing, pass-by-value, identity, array semantics, and GC reachability helps explain Java behavior accurately and avoid memory design mistakes.

## Standard References

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [JVMS Java SE 21 — §2.5.2 Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.2).
- [JVMS Java SE 21 — §2.6 Frames](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 21 — §2.4 Reference Types and Values](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.4).
- [JVMS Java SE 21 — §6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JLS Java SE 21 — §4.3 Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.3).
- [JLS Java SE 21 — §10 Arrays](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html).
- [JLS Java SE 21 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9).
- [JLS Java SE 21 — §12.6 Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.6).
- [JDK 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
