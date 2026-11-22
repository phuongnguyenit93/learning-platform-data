# Java Values, JVM References, and Physical Addresses: Concepts to Distinguish

## 1. Three Different Conceptual Layers

A common thinking mistake when learning the JVM is using the words **value**, **reference**, and **address** as if they were synonymous. They belong to different layers:

1. **Value in the Java language:** what an expression evaluates to or what a variable can store. A value can be a **primitive value** such as `int`, `boolean`, `double`, or a **reference value** such as a reference to a `String`, `Box`, or array; a reference variable can also hold `null`.
2. **Reference in the JVM model:** a value belonging to the reference category, used to denote an object/array that instructions and the runtime operate on. The specification defines the semantics of referencing, comparing, assigning, accessing, and throwing `NullPointerException`, **without forcing every JVM to implement references as raw machine pointers**.
3. **Memory address at the implementation and hardware layer:** where data is placed or mapped in the **process's virtual address space**, which may then be mapped by the operating system to physical pages. This detail depends on the JVM, JIT, garbage collector, operating system, and machine configuration. Standard Java **has no public API guaranteed to return the physical address of an object**.

Example:

~~~java
int age = 25;
String name = new String("JVM");
String alias = name;
~~~

- `age` holds the **primitive value** `25`.
- `name` holds a **reference value** to a `String` object.
- `alias = name` copies the **reference value**: the two variables refer to the same object, **without** copying the `String` object into a new object.
- No line allows inferring the "physical RAM address" of the `String` object. The `=` sign in Java denotes value assignment, not a promise that a memory location is fixed.

Keep one sentence as an anchor: **a reference is also a Java value, but a reference value is not a physical address that can be used like an integer**.

## 2. Primitive Values, Reference Values, and `null`

### 2.1. Primitive Types

Java has eight primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. A variable of a primitive type stores one value of that type according to Java rules. When assigning `int b = a;`, the program copies the current **numeric value**, so changing `b` does not change `a`.

Do not confuse **language-level type width** with **actual memory slot size**. For example, `int` is Java's 32-bit integer type, but how the JVM uses registers, local variable slots, alignment, and layout inside objects is an implementation matter. The JVM uses its own computational types on the operand stack; some operations on `byte`, `short`, `char`, `boolean` are performed via the `int` form according to the corresponding instructions. Do not deduce that "every Java variable always occupies exactly that many bytes of RAM at a fixed address".

### 2.2. Reference Types

In Java 17, **class**, **interface**, and **array** types are reference types. For example, `String`, `List<String>`, `int[]`, `Object`, and `Box` all belong to this group. A variable of a reference type holds a reference value to a type-compatible object, or `null`. Arrays **are objects**, including `int[]`: its elements are `int` values, while the `int[]` variable is a reference to the array object.

Separate the **declared type** from the **runtime type**:

~~~java
Object item = new StringBuilder("x");
~~~

The variable `item` has declared type `Object`, and its current value refers to an object whose runtime class is `StringBuilder`. `Object` does not mean the variable contains the entire object directly inside the variable slot.

### 2.3. `null` Is Not an Object

`null` is a special value that can be assigned to a reference variable. It indicates referring to no object; there is no class instance named `null`. Calling an instance method or accessing an instance field through a `null` value will cause a `NullPointerException` at the operation requiring dereference.

~~~java
String value = null;
System.out.println(value == null); // true
// value.length(); // if run: NullPointerException
~~~

Do not interpret `null` as "physical address 0" according to the Java standard. A JVM implementation may use a convenient internal representation for null, but the specification does not grant Java programs the right to manipulate that address.

## 3. The JVM Reference Model: A Semantic Contract, Not Pointer Arithmetic

The JVM specification classifies values into primitive and reference. A JVM reference value can denote an instance of a class, an instance of an array, or the special `null` value. Bytecode uses reference values in many operations such as:

| Instruction / instruction group | JVM semantics |
| --- | --- |
| `aconst_null` | Pushes `null` onto the operand stack |
| `new` | Creates a class instance, returning an uninitialized reference at the verification level until the constructor runs |
| `aload`, `astore` | Loads/stores a reference value via local variables |
| `getfield`, `putfield` | Reads/writes an instance field through an object reference |
| `aaload`, `aastore` | Reads/writes a reference element in a reference array |
| `if_acmpeq`, `if_acmpne` | Compares two reference values for whether they refer to the same object |
| `checkcast`, `instanceof` | Checks runtime type relationships based on the referenced object |

These are operations with **JVM-defined meaning**. They are not equivalent to adding/subtracting a number of bytes to a C-style pointer. Java also does not allow using `+ 8` on a reference to "move to the next field". Even `new` does not commit to a single machine instruction always allocating at a specific address: the JIT may optimize or the GC may change storage locations.

A class file describes value kinds using a **descriptor**, for example:

| Descriptor | Type or meaning |
| --- | --- |
| `I` | primitive `int` |
| `D` | primitive `double` |
| `Z` | primitive `boolean` |
| `Ljava/lang/String;` | reference to `java.lang.String` |
| `[I` | reference to an `int[]` array |
| `[Ljava/lang/String;` | reference to a `String[]` array |
| `(I)Ljava/lang/String;` | method taking `int`, returning `String` reference |

A descriptor expresses the **kind of value** according to the JVM binary contract, not which physical address an object resides at.

## 4. Value Assignment, Aliasing, and Java's Pass-by-Value Rule

Java **always passes arguments by value** (*pass-by-value*). The confusing point is that when an argument is a reference variable, **the value copied is the reference value itself**.

### 4.1. Primitive Variables: Copying the Value, Not Linking Two Variables

~~~java
int a = 10;
int b = a;
b = 20;
// a is still 10; b is 20
~~~

There is no hidden link causing a change to `b` to change `a`. Each variable represents a value location at the language level, even though the JVM/JIT may optimize the physical representation.

### 4.2. Reference Variables: Copying the Reference, Potentially Sharing the Same Object

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;

second.append("B");
// first.toString() and second.toString() are both "AB"
~~~

The two variables `first` and `second` refer to the same **mutable** `StringBuilder`. `append()` changes the state of the shared object. Writing `second = new StringBuilder("X");` only **reassigns the variable second** to a new object, without changing `first` or the old object.

~~~text
Conceptual representation, NOT a real address diagram:

Variable/slot first ───┐
                       ├────> Object A: StringBuilder("AB")
Variable/slot second ──┘

After second = new StringBuilder("X"):

first ─────────────────> Object A: StringBuilder("AB")
second ────────────────> Object B: StringBuilder("X")
~~~

Some objects such as `String` are immutable under the standard API: concatenation `s = s + "!"` semantically creates a new `String` result and reassigns the reference `s`; it does not edit the characters of the old object. Object immutability **does not turn a reference into a primitive**.

### 4.3. Method Parameters Also Receive a Copy of the Value

~~~java
static void mutate(Box parameter) {
    parameter.count++;           // writes state of shared object
    parameter = new Box(100);    // only changes local parameter variable
}
~~~

The first statement mutates the object visible to the caller; the second statement cannot change the reference variable in the caller. Therefore, saying "Java passes objects by reference" is misleading: **Java passes a copy of the reference value**, unlike pass-by-reference mechanisms that can change the caller's own variable.

## 5. Compilable and Runnable Java 17+ Example

Create a single file named `JvmValueReferenceDemo.java`:

~~~java
public class JvmValueReferenceDemo {
    static final class Box {
        int count;

        Box(int count) {
            this.count = count;
        }
    }

    static void incrementNumber(int value) {
        value++;
    }

    static void modifyAndReassign(Box parameter) {
        parameter.count++;
        parameter = new Box(99);
        parameter.count++;
    }

    public static void main(String[] args) {
        int original = 7;
        int copied = original;
        copied = 9;
        System.out.println("primitive values: " + original + ", " + copied);
        incrementNumber(original);
        System.out.println("primitive after call: " + original);

        Box first = new Box(10);
        Box alias = first;
        Box another = new Box(10);
        System.out.println("alias same object: " + (first == alias));
        System.out.println("another same object: " + (first == another));
        System.out.println("initial fields equal: " + (first.count == another.count));

        alias.count = 12;
        System.out.println("after alias writes: " + first.count);
        modifyAndReassign(first);
        System.out.println("after method call: " + first.count);
        System.out.println("other object: " + another.count);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 JvmValueReferenceDemo.java
java JvmValueReferenceDemo
~~~

**Exact stdout** of the program:

~~~text
primitive values: 7, 9
primitive after call: 7
alias same object: true
another same object: false
initial fields equal: true
after alias writes: 12
after method call: 13
other object: 10
~~~

Step-by-step explanation:

1. `copied` receives the numeric value 7 from `original`, but is independently changed to 9. `incrementNumber(original)` only increments the copy `value`, so `original` remains 7.
2. `first == alias` is `true` because both variables refer to the first Box object.
3. `first == another` is `false` because the two `new Box(10)` expressions create two distinct objects in terms of **identity**, even though both initially have `count = 10`.
4. Writing `alias.count = 12` modifies the shared object, so reading `first.count` sees 12.
5. The method receives a copy of the `first` reference. Incrementing `parameter.count` updates the first object to 13; reassigning `parameter = new Box(99)` only changes the local parameter. The `another` object remains 10.

The code and stdout above were verified with `javac --release 17` and run on JDK 21. No memory address is used to prove two references point to the same object: the `==` operator on references is sufficient for checking **identity**.

## 6. Object Identity, Logical Content, and Memory Address Are Three Separate Things

### 6.1. `==` and `equals()`

- For most primitives, `==` compares **values** (keep in mind special floating-point rules such as `NaN != NaN`).
- For two compatible reference expressions, `==` asks whether they are both `null` or refer to the **same object**, not what RAM coordinates the object sits at.
- `equals()` is a Java method: `Object.equals()` uses identity by default, but subclasses can override it to define **logical equality**. For example, `String.equals()` compares character content; `StringBuilder` does not override `equals()` to compare content.
- For arrays, `array1.equals(array2)` still defaults to identity comparison; to compare array elements, use `Arrays.equals` (or `Arrays.deepEquals` for appropriate nested structures).

~~~java
String a = new String("JVM");
String b = new String("JVM");
System.out.println(a == b);      // false: two separate objects
System.out.println(a.equals(b)); // true: equal content
~~~

**Do not compare String content with `==`.** String literals may be interned, causing two variables to happen to receive the same object; that result does not change the meaning of `==` as an identity check.

### 6.2. `hashCode()` and `System.identityHashCode()` Are Not Addresses

The default `Object.toString()` usually has the form `ClassName@hexCode`. The hex part is a representation of the identity hash code per `Object.toString()`'s implementation, **not a pointer or RAM address**. `System.identityHashCode(obj)` retrieves the identity-associated hash code according to the JVM mechanism without calling the class's overridden `hashCode()`, yet **it is not guaranteed unique**: two distinct objects can have the same hash code. The hash code can remain semantically stable even when the GC moves the object.

~~~java
Object a = new Object();
Object b = new Object();

System.out.println(a == b);                    // false
System.out.println(System.identityHashCode(a)); // an int, NOT an address
~~~

The numeric value of an identity hash code depends on the run/JVM, so **do not** write a fixed stdout for the hash code line. Do not use `hashCode()` or `toString()` to infer physical address, object size, or the order of objects in the heap.

### 6.3. Wrappers, Autoboxing, and "Value Objects"

Classes like `Integer`, `Long`, `Boolean` are **reference classes**, even though they wrap primitive values. For example, `Integer x = 100;` uses autoboxing; `x` is a reference variable pointing to a wrapper object. Some wrapper values are cached according to rules/implementations, so `x == y` can produce unexpected results if used to compare numbers. Use `equals()` or unbox to primitive properly when the goal is comparing **numeric values**.

A Java 17 `record` is still a **reference type with object identity**; words like "value-like" or "immutable" in API design do not automatically turn it into a primitive type. "Java value" in this article means a value at the language/JVM level, **not the name of a fixed object layout mechanism**.

## 7. Where Are Objects, Local Variables, and the Operand Stack Modeled?

In the JVM model, each thread has a stack containing **frames** for method invocations. Each frame has a local-variable array and an operand stack. A local slot or a position on the operand stack can hold a primitive value or a reference value depending on instruction/verifier rules. An instance field of an object can also hold a primitive or a reference; elements of a reference array hold reference values.

The **heap** is the shared runtime area where class instances and array objects are allocated at the JVM model level. However, statements like "primitives are always on the stack" or "references always live on the stack" are both **false**:

- A primitive can reside in a local variable, in a field of an object on the heap, or in an `int[]` element.
- A reference can reside in a local variable, on the operand stack, in an object field, in a static field, or in an `Object[]` element.
- A reference value may be kept in a CPU register or handled by the JIT using an internal representation depending on the moment.
- The JIT may inline methods, perform escape analysis, scalar replacement, or eliminate an unobservable allocation. Thus the model "every `new` creates a real object at an immediately measurable heap location" is not a physical guarantee in every run.

~~~text
Semantic model, does not describe bytes/offsets of a specific JVM:

Thread frame:                 Shared heap (model):
  local primitive n = 7
  local reference x ──────────> Object A:
  local reference y ──────────>   int count = 13
  local reference z ──────────> Object B:
                                  int count = 10

Another object or static field can store an additional reference to Object A.
~~~

The JVM garbage collector relies on **reachability** from roots and reference relationships (along with specific rules for reference types such as weak/soft/phantom when present) to manage objects. Objects that are no longer used or become unreachable **are not necessarily collected immediately**. `System.gc()` is only an implementation-dependent request/suggestion, not a mandatory command to free the exact object at the moment of the call.

### GC Moves Objects, Yet Identity Remains Identity

Many collectors are capable of **moving/compacting** objects to manage the heap. When an object is moved, the JVM and GC maintain the correctness of live references through internal mechanisms. Java code still observes the same object via `==`, instead of having to fix pointers manually. There are also collectors or phases that do not move objects; do not say "every GC always shifts the entire heap".

It follows that: even if the JVM uses a memory location to store an object at time T, one cannot assume that location stays the same at T+1. **Object identity is not identical to a byte location in RAM**.

## 8. Three Address Layers: JVM Reference, Virtual Address, and Physical Address

Distinguish clearly:

| Concept | Who defines and manages it? | Does standard Java manipulate it as an address number? |
| --- | --- | --- |
| **JVM reference value** | The JVM contract and the implementation's internal representation | **No**; Java uses object-style operations like dereference, method call, `==` |
| **Process virtual address** | CPU/OS with virtual memory mechanisms; used by JVM/native runtime for storage | No standard public Java API returns a stable virtual address of a managed object |
| **Physical memory address** | Operating system/hardware mapping virtual pages to physical memory (if resident) | **No**; certainly not the value of a reference variable |

Normally, native programs on modern OSes work with **virtual addresses**, not directly with physical RAM address numbers. The operating system can change mappings to physical pages, swap pages in/out, or use other memory management mechanisms. Even if there is a native pointer pointing to a memory region, it **does not automatically equate to a physical address**.

In some 64-bit HotSpot configurations, internal references may be represented using **compressed ordinary object pointers (compressed oops)** to reduce memory overhead. In other cases, a JVM may use different representations (e.g., direct addresses, encodings, handles/indirection). Details depend on version, JVM, GC, heap size, and configuration; **they are not part of the class-file/JLS contract**. Do not state "a Java reference is always exactly 4 bytes" or "always exactly 8 bytes".

A thought experiment: the machine can change the physical location of a RAM page; the GC can move the logical location of an object within process memory. All of this can happen while `referenceA == referenceB` remains `true` if both denote the same object. The JVM guarantees **reference semantics** to the program, not public exposure of physical layout.

### JNI, Direct Buffers, and Internal Tools Do Not Change the Java Contract

Java can interact with native memory via JNI or off-heap APIs like `ByteBuffer.allocateDirect()`. However, **native pointers, managed object references, and physical addresses** remain different things. A direct buffer may use memory outside the Java heap, but the `ByteBuffer` object that Java holds is still a managed object. Unsupported internal APIs like `sun.misc.Unsafe` are not a standard way to convert references into physical addresses, and depend on implementation/version.

One should also not rely on tricks to measure an "address" from `System.identityHashCode`, debug `toString`, or internal object layout information. Those values serve their own purposes and do not represent stable, portable pointers.

## 9. Java Memory Model: Visibility and Ordering Differ from Memory Location

When multiple threads share a reference, the Java Memory Model (JMM) focuses on **visibility, ordering, and happens-before**, not on rules about "which address gets written first". Having two threads hold a reference to the same object **does not automatically guarantee** that all reads/writes to mutable fields of that object are properly synchronized.

Example:

~~~java
final class State {
    int counter;
}

State shared = new State();
// Two threads both call shared.counter++ without synchronization:
// lost update is possible because the increment consists of multiple steps.
~~~

The snippet above is a **conceptual illustration**, not a standalone program. Even though both threads share the reference, `counter++` is not automatically atomic. `volatile` helps ensure certain visibility/ordering relationships for accesses to the corresponding field, yet `volatile int counter` still **does not make `counter++` atomic**. One can use `synchronized`, `AtomicInteger`, locks, or an appropriate ownership model.

Specifically: `volatile Box ref` is a volatile reference field; it has synchronization semantics when reading/writing **the `ref` variable itself**. It does not make every mutable field inside every object that `ref` ever points to thread-safe. One must examine how the object is published, updated, and read.

## 10. Practical Questions and Common Misconceptions

**Q: "Do Java objects live on the heap?"** In the **JVM execution model**, class instances and arrays are allocated on the heap. However, the JVM/JIT may optimize the physical representation or eliminate allocations if observable semantics do not change. Do not treat textbook heap/stack diagrams as exact address maps at every moment.

**Q: "Does variable `Object x` contain the entire object?"** No. The variable holds a reference value (or null), while the object's state is represented at runtime according to the JVM's mechanisms.

**Q: "Does assigning `y = x` copy the object?"** No if `x` is a reference: that copies the reference value. To get an independent object, you must explicitly create/copy via an API, choosing shallow or deep copy as needed.

**Q: "Does Java pass objects by reference?"** Java passes **reference values** via pass-by-value. A method can modify the state of the referenced object, but cannot reassign the caller's variable by assigning to the local parameter.

**Q: "Can `==` be used to tell if two objects are at the same address?"** `==` on references checks **object identity** according to Java/JVM. It can be used to determine whether two references denote the same object, but the result does not give the object's address.

**Q: "Is `hashCode()` the object's address?"** No. A hash code is a hash value serving the Java contract; the identity hash code is not guaranteed unique and is not an address. Do not use it as a global object ID in distributed systems or in place of an address.

**Q: "If GC moves an object, will all old references break?"** No. The JVM/GC must preserve the valid semantics of references that are still live. Normal Java code does not observe the process of updating internal pointer representations.

**Q: "Does the 64-bit `long` type mean 8 contiguous bytes on the stack?"** Java type width does not dictate all slot/frame/register/object layout choices. The JVM specification and implementation have their own rules; the JIT may optimize.

**Q: "Are references like C pointers, where you can add an offset?"** No. Java references do not support pointer arithmetic. If working with native/off-heap memory, dedicated APIs are required, along with attention to lifetime, bounds, thread safety, and portability.

**Q: "If two threads see the same reference, is there no longer a race?"** False. Identity/aliasing is different from JMM synchronization; mutable state still requires proper synchronization design.

## 11. Self-Check Exercises

1. After `int b = a` and `b++`, does `a` change? **No**, because the primitive value was copied.
2. After `Box b = a` and `b.count++`, can `a.count` change? **Yes**, when both refer to the same mutable object.
3. Inside a method, does assigning `parameter = new Box(...)` reassign the caller's variable? **No**, because the parameter is a copy of the reference value.
4. For two different `String` objects with the same content, what do `==` and `equals()` return? **`==` is false, `equals()` is true**, if created as two separate objects with `new String(...)`.
5. Can `System.identityHashCode(o)` be used to print the physical address? **No.**
6. When GC moves an object to another location, must comparing two references pointing to that same object change its result? **No**, the JVM preserves identity semantics.
7. Is `int[] data` a primitive or reference type? **A reference type to an array object**, while each element `data[i]` is a primitive `int`.
8. To fix a race condition on `shared.counter++`, is forcing two threads to hold the same reference sufficient? **No**; synchronization/atomicity must be handled.

## 12. Standard References for Deeper Study

- Java Virtual Machine Specification (Java SE 17), chapters **Run-Time Data Areas** and **Data Types**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html
- Java Language Specification (Java SE 17), section **Types, Values, and Variables**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html
- Java Language Specification, section **Method Invocation Expressions** (argument evaluation and passing): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2
- Java Language Specification, chapter **Threads and Locks** (JMM/happens-before): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Technical conclusion:** both primitive values and reference values are **values** processed by Java/JVM. A reference value carries the semantics of **referring to an object**, not a promise that RAM addresses can be read. Object identity, virtual/physical memory storage, JVM layout, and visibility between threads are distinct layers; distinguishing them helps avoid bugs related to aliasing, method parameters, object comparison, GC, and concurrent programming.