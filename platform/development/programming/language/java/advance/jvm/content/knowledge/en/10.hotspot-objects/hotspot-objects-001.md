# Object Creation Sequence in HotSpot: Allocation, Default Values, and Constructor Execution

## Objectives

The expression `new Person("Lan")` contains several distinct operations: checking and initializing the class if needed, allocating an **instance** with enough space for all fields, setting them to **default values**, evaluating the constructor arguments, and then invoking the special method **`<init>`**. A constructor is not a memory allocation function: when the constructor begins running, the instance and its default fields already exist semantically.

After this lesson you will be able to:
- Describe the class instance creation sequence according to **JLS `15.9.4, `12.5** and the **`new`** instruction according to the JVMS.
- Distinguish between **`<clinit>` of a class** and **`<init>` of each instance**, default fields, and explicit initializers.
- Understand the order of superclass/subclass constructors, `this(...)`, `super(...)`, field initializers, instance initializer blocks, and constructor bodies.
- Explain why a superclass constructor can see a subclass field as 0/null even though the source declares a different value.
- Recognize **HotSpot**-specific allocation mechanisms such as TLAB, fast/slow allocation paths, zeroing, object headers, alignment, compressed oops, and the impact of JIT.
- Distinguish creating an object with `new` from creating an array via `newarray`, `anewarray`, and `multianewarray`.
- Read bytecode with `javap`, and explain `new`, `dup`, `invokespecial`, and the risks of constructor failure or publishing `this` too early.

## 1. Object creation sequence according to Java and JVM semantics

A Java expression:

~~~java
Person person = new Person("Lan");
~~~

This is an illustrative snippet; it requires a `Person` class and a matching constructor to compile.

Conceptual diagram:

~~~text
new Person("Lan")
      |
      v
Resolve class; class initialization if not yet performed
      |
      v
Allocate class instance (including fields of superclasses)
      |
      v
Set default values for ALL instance fields
      |
      v
Evaluate constructor arguments from left to right
      |
      v
Run instance initialization method <init>:
  constructor chain -> superclass first, subclass later
  field initializers and instance blocks of each class
  statements in constructor body
      |
      v
If successful -> return reference to the new object
If error -> complete abruptly / throw exception
~~~

**Important order:** according to **JLS `15.9.4**, for an ordinary class instance creation expression, the step of **allocating and setting default fields occurs before evaluating the actual constructor arguments**. Arguments are evaluated **from left to right** before the selected constructor is invoked. For qualified inner-class creation, the qualifying expression must also be evaluated first, according to its own rules.

The `new` bytecode requires the class to be resolved/initialized according to the JVMS if necessary before continuing to create the instance. When the class has already been initialized previously, the JVM **does not re-run the class initializer** for each `new` operation.

Comparison table:

| Operation | What does the JVM/JLS guarantee? | What can the HotSpot implementation do? |
| --- | --- | --- |
| Class resolution/initialization | A valid class is resolved and initialized when needed per `new` rules | Check class metadata, class-init fast path |
| Allocation | A semantically new instance, containing inherited/declared instance fields | Fast allocation from TLAB or take the slow path |
| Default initialization | Integer 0, boolean false, floating-point +0.0, char NUL, reference null | Zeroing / utilize an already zeroed region |
| Object metadata | The VM knows the runtime type/identity to operate on the instance | Write header, Klass metadata, align according to configuration |
| Constructor | Run the `<init>` chain and initializers in the exact order | Interpreter/JIT, may inline calls |
| Expression result | Reference if completed successfully | Reference representation decided by the VM |

The diagram is a **semantic model**, not a mandatory list of CPU instructions; the optimizer is only allowed to change how it is executed as long as it does not violate observable Java behavior.

## 2. Class initialization differs from instance initialization

**`<clinit>`** is the special method for **class/interface initialization**, related to static initializers. **`<init>`** is the JVM name for **constructors/instance initialization methods**. They do not replace each other.

~~~java
class Counter {
    static int total = 10;
    int value = 5;

    Counter() {
        total++;
    }
}
~~~

This is an illustrative class, without `main`. If `Counter` has not been initialized yet, the first `new Counter()` can trigger the class initialization process so that the static field `total` receives the value 10. Thereafter, **each** time a Counter instance is created:
1. The object receives the default `value=0` after allocation.
2. The initializer `value=5` and the constructor body run, incrementing `total`.
3. The class initializer **does not run again** for the second instance.

| Term | Description | Frequency according to semantics |
| --- | --- | --- |
| **Class preparation** | During linking, creating static fields and default values | Once per runtime class/interface being linked |
| **Class initialization** | Assigning ConstantValue and running `<clinit>` if present | According to class-init rules, not per object |
| **Object allocation** | Creating a new instance | Per `new` evaluation semantically |
| **Object default initialization** | Setting all instance fields to defaults | For the new instance |
| **Instance initialization** | Constructor `<init>` chain and field/block initializers | For the instance being created |

Do not confuse **class preparation** (creating static fields of a class) with allocating **instance fields** of an object.

## 3. Default values precede explicit field initializers

When allocating an instance, the JVM creates state comprising all instance fields belonging to the created class and its superclasses, including hidden fields. They receive default values, not the values declared in source after the `=` sign.

| Instance field | Default after allocation |
| --- | --- |
| `byte`, `short`, `int`, `long` | 0 matching the type |
| `float` | +0.0f |
| `double` | +0.0d |
| `boolean` | false |
| `char` | NUL, code unit 0 (`'\u0000'`) |
| `String`, class/interface reference | null |
| `int[]` or reference to an array | null |

Example:

~~~java
class Data {
    int count = 7;
    String label = "ready";
    int[] numbers = new int[3];
}
~~~

This is an illustrative class. **Immediately after object allocation** and before explicit instance initializers: `count=0`, `label=null`, `numbers=null`. After the initializers execute in the constructor chain: `count=7`, `label` points to the String, `numbers` points to a new array with three int elements equal to 0.

`javac` does not need to generate bytecode assigning 0/null to each field. The operation guaranteeing default values is performed by the VM. The value `'\u0000'` is different from the digit character `'0'`; a null reference is also different from an empty String object.

### Hidden fields do not disappear

~~~java
class A { int id = 1; }
class B extends A { int id = 2; }
~~~

A Class B instance has **both A.id and B.id** as two separate fields. Each field receives the default 0 upon allocation, and then the initializer of the declaring class runs along the constructor chain. This is field *hiding*, not field overriding.

## 4. Constructor chain: superclasses first, subclass later

For Java 17 and normal constructors, the initialization progression means:

~~~text
Object.<init>()
       |
       v
Base instance field initializers + instance blocks
       |
       v
Base constructor body
       |
       v
Derived instance field initializers + instance blocks
       |
       v
Derived constructor body
~~~

Field initializers and instance initializer blocks of **the same class** are executed in the **order they appear in the source**. A constructor can call `this(...)` to delegate to another constructor in the same class or `super(...)` to call a superclass constructor. If no explicit invocation is written, the compiler inserts a call to the default superclass constructor according to Java rules when valid.

**Important:** Java 17 requires an explicit constructor invocation like `this(...)`/`super(...)` at the beginning of the corresponding constructor according to this version's rules; do not mix more flexible syntax from future JDKs into Java 17 examples.

### Runnable program: observing a subclass field still at default

Create **`CreationOrderDemo.java`**:

~~~java
public class CreationOrderDemo {
    static int trace(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }

    static class Base {
        int baseValue = trace("Base.field", 10);

        {
            System.out.println("Base.block=" + baseValue);
        }

        Base() {
            System.out.println(
                    "Base.constructor childValue=" +
                    ((Child) this).childValue);
        }
    }

    static final class Child extends Base {
        static {
            System.out.println("Child.<clinit>");
        }

        int childValue = trace("Child.field", 20);

        {
            System.out.println("Child.block=" + childValue);
        }

        Child() {
            System.out.println("Child.constructor=" + childValue);
        }
    }

    public static void main(String[] args) {
        System.out.println("main");
        Child c = new Child();
        System.out.println("after=" + c.baseValue + "," + c.childValue);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 CreationOrderDemo.java
java CreationOrderDemo
~~~

**Exact stdout:**

~~~text
main
Child.<clinit>
Base.field=10
Base.block=10
Base.constructor childValue=0
Child.field=20
Child.block=20
Child.constructor=20
after=10,20
~~~

**Explanation:**
1. `main` of the outer class prints `main`. When the JVM needs to create the first Child, Child's static initializer prints `Child.<clinit>`.
2. The Child instance is created with both `Base.baseValue` **and** `Child.childValue` already present, both equal to 0.
3. The Child constructor leads to the Base constructor. After the `Object.<init>` call, the Base initializer assigns 10 and prints the two corresponding lines.
4. **Inside the Base constructor body**, the Child field initializer has not run yet, so `((Child)this).childValue` is still 0.
5. After the Base constructor completes, the Child initializer assigns 20, the block prints 20, and the Child constructor body prints 20.
6. After the entire chain, the expression `new Child()` returns the reference; the last line prints `after=10,20`.

The cast in the example is safe because the object is actually a Child. However, **a superclass constructor reading subclass state** is a design pattern that should not be abused. In particular, calling an overridable method from a superclass constructor can dispatch to the subclass method before subclass fields are initialized, leading to seeing 0/null or causing a `NullPointerException`.

### Virtual dispatch still works inside a constructor

~~~java
class Parent {
    Parent() {
        onReady();
    }

    void onReady() {}
}

class Child extends Parent {
    String name = "ready";

    @Override
    void onReady() {
        System.out.println(name);
    }
}
~~~

This is an **illustrative class**. When creating Child, `Parent()` can call the overridden method `Child.onReady()` before `Child.name` is assigned "ready", because the object already has runtime type Child. In that case it can print `null`. Do not call overridable methods from a base constructor unless you truly understand and control the consequences.

## 5. Calling `this(...)` does not create an extra object

Constructor delegation to an overload is not a new `new` expression and does not cause the class's field initializers to run repeatedly.

Create the file **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static class Parent {
        Parent() {
            System.out.println("Parent()");
        }
    }

    static final class Child extends Parent {
        int value = initializeValue();

        {
            System.out.println("Child.block");
        }

        Child() {
            this(7);
            System.out.println("Child()");
        }

        Child(int requested) {
            System.out.println("Child(int)=" + requested);
        }

        int initializeValue() {
            System.out.println("Child.field");
            return 2;
        }
    }

    public static void main(String[] args) {
        Child c = new Child();
        System.out.println("value=" + c.value);
    }
}
~~~

Run:

~~~bash
javac --release 17 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

**Exact stdout:**

~~~text
Parent()
Child.field
Child.block
Child(int)=7
Child()
value=2
~~~

`Child()` delegates to `Child(int)`. The target constructor handles the superclass chain; then the Child field initializer/block is executed **once**, after which the `Child(int)` body runs, and finally execution returns to the remainder of `Child()`. No additional Child instance is allocated due to `this(7)`.

## 6. Bytecode of object creation: `new` does not directly run `<init>`

Example of a method in a class (illustrative snippet):

~~~java
static Box create() {
    return new Box(5);
}
~~~

Suppose there is a Box class with a constructor taking an int. The bytecode from `javac` typically looks like:

~~~text
new           #N   // class Box
dup
iconst_5
invokespecial #M   // Method Box."<init>":(I)V
areturn
~~~

This is an **illustrative pattern**, not an exact dump with mandatory offsets/indices. Operand stack model:

| Instruction | Stack after instruction (bottom to top) |
| --- | --- |
| `new #N` | `[uninitializedRef]` |
| `dup` | `[uninitializedRef, uninitializedRef]` |
| `iconst_5` | `[uninitializedRef, uninitializedRef, 5]` |
| `invokespecial #M` | `[initializedRef]` if constructor succeeds |
| `areturn` | Return reference to caller |

The `new` instruction uses a constant pool entry identifying the class being created, which can trigger class resolution/initialization if needed. `invokespecial` invokes the instance initialization method `<init>`, with a receiver and arguments of matching types.

**The verifier distinguishes an uninitialized reference from a reference that has completed its constructor** to prevent arbitrary bytecode from using the object before it is initialized. Even though the object already has storage, one cannot assume every bytecode operation is valid on a receiver that has not yet called `<init>`.

### Verifying with javap

After compiling:

~~~bash
javap -c -p CreationOrderDemo
javap -c -p 'CreationOrderDemo$Base'
javap -c -p 'CreationOrderDemo$Child'
javap -v -p 'CreationOrderDemo$Child'
~~~

Observations:
- `main` contains `new`, `dup`, `invokespecial <init>` when creating Child.
- `Child.<init>` calls `Base.<init>` before assignments to `childValue`.
- `Base.<init>` calls `Object.<init>`, followed by the `baseValue` initializer, the instance block, and the constructor body.
- `Child.<clinit>` contains the static block, separate from `Child.<init>`.
- The `putfield` instructions assigning 10/20 come from **explicit field initializers**; there are no compiler-generated instructions assigning default 0s.

The `#N` indices, bytecode offsets, and string concatenation in print statements may differ across compilers/JDKs. On Windows cmd.exe you can use class names containing `$` directly; on Bash/PowerShell, single quotes as in the example prevent the shell from interpreting special characters.

## 7. HotSpot-specific allocation mechanisms: TLAB and slow path

A **Thread-Local Allocation Buffer (TLAB)** is a region **inside the heap** that HotSpot can use for fast object allocation by a single thread. Having "thread-local" in the name **does not mean the object is on the thread stack**; an object allocated into a TLAB is still a heap object and can be shared afterwards.

Diagram:

~~~text
Java heap / allocation region
    |
    +-- TLAB thread A: [start ... top ---> ... end]
    |
    +-- TLAB thread B: [start ... top ---> ... end]
    |
    +-- shared / slow allocation path if needed
~~~

The fast allocation path can:
1. Determine the instance size after accounting for header, fields, and alignment.
2. Check whether `top + size` still fits within the TLAB's limit.
3. If sufficient, bump-pointer advance top and obtain the region for the object.
4. Prepare the header and default fields according to semantics.
5. Then execute instance constructor initialization.

If there is no suitable TLAB, the object is too large, or the current region is insufficient, HotSpot takes the **slow path** to try refilling the TLAB, allocating via another path, or triggering GC activities; if it fails, it may throw `OutOfMemoryError`.

Do not claim that **every** HotSpot object is allocated from Eden/TLAB or that every GC uses the same strategy. The collector, architecture, JVM flags, size class, and JDK version determine the details.

### Zeroing is not running the constructor

One way to implement default fields is **zeroing memory**; the JVM can also use an already zeroed region or optimize away unnecessary default writes. However, the Java result must be equivalent to fields having default values **before** any code is allowed to observe them.

**The header is not all zero bits:** the object header needs to store runtime information. Therefore, saying "the JVM zeroes every byte of the object, including the header, before running code" as an invariant rule is inaccurate.

## 8. Object header, field layout, and alignment

HotSpot typically has to manage:
- Metadata in the **object header** about object state/lock/GC according to the active mode.
- Runtime type information via **Klass metadata/pointer** or a corresponding encoding.
- **Instance fields** of the class and superclasses.
- **Padding/alignment** to satisfy allocation constraints.
- For arrays, **array length** information and the region containing elements.

Illustrative diagram:

~~~text
[header / runtime metadata]
[Klass information if layout requires it]
[instance fields of superclasses and current class]
[padding / alignment if any]
~~~

This is **not an absolute layout**. Header size, field positions, compressed object pointers (compressed oops), compressed class pointers, and forms of **compact object headers** depend on HotSpot version/options/platform. Do not teach as fixed rules that "every object has a 12-byte header" or "a reference is always a raw 64-bit machine address."

A class with only `byte value` does not mean the actual object occupies exactly 1 byte; there is also the header, padding, and inheritance. To measure the actual heap layout on a specific JDK, you can use a tool such as Java Object Layout/JOL of the appropriate version, noting the environment and JVM flags. Measurement results are **not** part of the Java Language Specification.

## 9. Evaluating constructor arguments and errors between steps

According to JLS `15.9.4, **allocation of a class instance takes place before arguments are evaluated** (for an ordinary class instance creation expression). Arguments are then evaluated from left to right.

Create the file **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int value(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Point {
        Point(int x, int y) {
            System.out.println("constructor=" + x + "," + y);
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        new Point(value("arg1", 1), value("arg2", 2));
        System.out.println("end");
    }
}
~~~

Run:

~~~bash
javac --release 17 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

**Exact stdout:**

~~~text
begin
arg1
arg2
constructor=1,2
end
~~~

Stdout illustrates the order of **side effects in argument evaluation and the constructor body**. It does not directly measure when the VM allocates memory because normal allocation prints nothing. If the first argument throws an exception, subsequent arguments are not evaluated and the constructor body does not run; the `new` expression does not return normally.

**OutOfMemoryError:** if allocation cannot be performed, the expression can throw OOME. The JLS specifies checking OOME before evaluating the arguments of class instance creation. One should not use an out-of-heap experiment as a test with stable stdout because OOME and GC depend on runtime/memory pressure.

## 10. When a constructor throws an exception

A constructor can complete abruptly after having performed some side effects. In that case, the `new` expression **does not return a reference normally**, yet there is no mechanism to "roll back all side effects."

Create the file **`ConstructorFailureDemo.java`**:

~~~java
public class ConstructorFailureDemo {
    static int attempts;

    static class Fragile {
        int value = 5;

        Fragile() {
            attempts++;
            System.out.println("constructor value=" + value);
            throw new IllegalStateException("failed");
        }
    }

    public static void main(String[] args) {
        try {
            Fragile f = new Fragile();
            System.out.println(f.value);
        } catch (IllegalStateException expected) {
            System.out.println("caught=" + expected.getMessage());
        }

        System.out.println("attempts=" + attempts);
    }
}
~~~

Run:

~~~bash
javac --release 17 ConstructorFailureDemo.java
java ConstructorFailureDemo
~~~

**Exact stdout:**

~~~text
constructor value=5
caught=failed
attempts=1
~~~

The field initializer `value=5` ran before the constructor body. The constructor incremented the static counter and then threw an exception; the `new` result completed abruptly, while `attempts=1` proves the side effect is not automatically undone. If no reference escaped, the unneeded object can be reclaimed by GC at a time decided by the VM.

### Avoid letting `this` escape from the constructor

~~~java
class UnsafePublication {
    static UnsafePublication leaked;
    final String label;

    UnsafePublication() {
        leaked = this;
        label = "ready";
    }
}
~~~

This is an **anti-pattern example**, not a recommendation. Placing `this` into a static field, listener, another thread, or a shared collection before the constructor completes can allow the object to be observed in a partially initialized state and create Java Memory Model risks, especially when publication lacks synchronization.

**Rule:** complete the constructor before publishing the reference; use an appropriate safe publication mechanism such as synchronized/volatile/concurrent collections or a thread-safe factory. Do not call virtual overridable methods from a constructor if that method needs initialized subclass state.

## 11. Arrays: allocation and default elements, without running element constructors

| Java source | Common JVM opcode | Behavior |
| --- | --- | --- |
| `new int[3]` | `newarray int` | One int[] object, three primitive values 0 |
| `new Item[2]` | `anewarray Item` | One Item[] object, two null references |
| `new int[2][3]` | `multianewarray [[I, 2` | Outer array and inner arrays of the specified dimensions |
| `new int[2][]` | `anewarray [I` or equivalent instruction | Outer array, two null slots |

Arrays are objects on the heap according to the JVM. However, **`new Item[2]` does not call the Item constructor twice**, because the elements initially are only null reference values.

Runnable example **`ArrayBirthDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayBirthDemo {
    static final class Item {
        int count = 7;
    }

    public static void main(String[] args) {
        int[] numbers = new int[3];
        Item[] items = new Item[2];
        int[][] matrix = new int[2][3];

        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("items[0]=" + items[0]);
        System.out.println("matrixRows=" + matrix.length);
        System.out.println("matrixCols=" + matrix[0].length);

        items[0] = new Item();
        System.out.println("itemCount=" + items[0].count);
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 ArrayBirthDemo.java
java ArrayBirthDemo
~~~

**Exact stdout:**

~~~text
numbers=[0, 0, 0]
items[0]=null
matrixRows=2
matrixCols=3
itemCount=7
~~~

**Arrays have their own error rules:** a negative dimension causes `NegativeArraySizeException`; insufficient memory can cause OOME. The evaluation order of array dimension expressions in JLS `15.10.2 **differs** from the allocation/argument order of class instance creation in `15.9.4; do not apply one formula to both.

## 12. JIT escape analysis, GC, and reference values

At the Java level, `new` creates a semantically new class instance. However, the HotSpot JIT can optimize **physical object allocation** when it proves the object does not escape and this transformation preserves all observable behavior.

~~~java
static int total(int a, int b) {
    Pair p = new Pair(a, b);
    return p.first + p.second;
}
~~~

This is an illustrative snippet; it requires a `Pair` class with appropriate fields. The JVM can use **scalar replacement** to replace the object with individual field values if conditions are suitable. One cannot claim that every `new` instruction is guaranteed to have a separate block of heap RAM on every JIT run; conversely, one also cannot claim that **every small object is allocated on the stack**.

When a method finishes:
- The frame/local variables may cease to exist according to the stack model.
- The object can still be reachable from the caller, static fields, other objects, or appropriate GC roots.
- GC can reclaim objects that are no longer reachable **at an unspecified time**, not necessarily right when the constructor/method body returns.
- A TLAB is a heap region supporting allocation, **not a mechanism that automatically cleans up all objects when a thread dies**.

An object that has completed its constructor also needs to be **safely published** if shared across other threads. Default initialization and constructor completion do not make every concurrent operation thread-safe.

## 13. Common mistakes and how to analyze them

| Symptom / claim | Accurate analysis |
| --- | --- |
| “`new` itself is the constructor.” | `new` allocates the object; `invokespecial <init>` is used for instance initialization. |
| “Field `int x=7` gets 7 immediately during allocation.” | Default 0 comes first; the field initializer assigns 7 during the constructor chain. |
| “Child field must be 20 while Base constructor is running.” | Child's explicit initializer has not run yet; Base can observe the default 0. |
| “Constructor calling `this(...)` means a second object is created.” | Delegation on the same object; there is no second `new` just because of `this(...)`. |
| “Static block runs every time an instance is created.” | Class initializer follows class lifecycle rules, not per object. |
| “The header of every HotSpot object has a fixed size.” | Depends on JVM version/flags/architecture; compact headers may exist. |
| “TLAB is thread stack allocation.” | TLAB is on the heap; objects can escape and outlive the thread. |
| “Whenever there is `new`, you will definitely see an allocation in the profiler.” | The JIT can eliminate allocations that are not observable. |
| “If a constructor throws an exception, all side effects roll back.” | Side effects do not roll back automatically; `new` completes abruptly. |
| “Array reference slots automatically create class elements.” | Reference elements receive null; element objects must be created separately. |
| “An uninitialized class will run the constructor before the static initializer.” | Class initialization, if needed, is guaranteed per `new` rules before instance creation. |
| “`new int[-1]` calls an array constructor.” | There is no such Java array constructor; NegativeArraySizeException. |
| “An object is naturally thread-safe because memory was zeroed.” | Default values do not guarantee safe publication/thread-safety. |

### Diagnostic roadmap for object creation errors

1. **Resolution/loading:** Is the class in the right JAR/module, class loader, and binary compatible?
2. **Class initialization:** Did a static initializer throw an exception? Check `ExceptionInInitializerError` and its cause.
3. **Allocation:** Insufficient heap/GC pressure, `OutOfMemoryError`? Measure instead of guessing.
4. **Argument evaluation:** Did an actual argument throw an exception before the constructor body?
5. **Constructor chain:** Did an exception occur in a superclass initializer, instance initializer, or constructor body?
6. **Publication:** Was the object leaked early/shared between threads without happens-before?
7. **Performance:** Are you measuring JIT warmup/GC/TLAB or allocation logic? Avoid generalizing one profiler result to every JDK.

## 14. Self-check questions

**Question 1.** When do instance fields receive default values?

**Answer:** After allocation, **before** constructor argument evaluation and constructor initialization according to JLS `15.9.4 for ordinary class instance creation.

**Question 2.** Does `new` directly execute `<init>`?

**Answer:** No; in the class file, `new` creates an uninitialized object reference, and then the compiler uses `invokespecial` to invoke `<init>`.

**Question 3.** Why does the Base constructor read `Child.childValue` as 0?

**Answer:** The entire object already has default values, but the explicit Child field initializer has not run yet.

**Question 4.** Does `this(7)` in a constructor allocate a new object?

**Answer:** No. It delegates to an overloaded constructor on **the same instance**.

**Question 5.** How do `<clinit>` and `<init>` differ?

**Answer:** `<clinit>` initializes class/static state; `<init>` initializes each object through the constructor chain.

**Question 6.** Is a TLAB located on the stack or the heap?

**Answer:** Heap; it is a thread-local allocation region of HotSpot, not synonymous with stack space.

**Question 7.** Can we state that an object header is always 12/16 bytes?

**Answer:** No. Layout/header depends on HotSpot version, architecture, flags, and header format.

**Question 8.** How many Item objects does `new Item[3]` create?

**Answer:** It creates zero Item instances; it only creates one Item[] array object with three null reference elements.

**Question 9.** Does a failed constructor return a reference via the `new` expression normally?

**Answer:** No; the expression completes abruptly, the exception propagates out, and side effects that already occurred do not automatically roll back.

**Question 10.** Does finishing object creation mean all other threads always see the final fields?

**Answer:** No. Safe publication and Java Memory Model rules are required; avoid this-escape.

**Question 11.** Why can the compiler/JIT eliminate an allocation while Java semantics remain correct?

**Answer:** When the object does not escape and the optimization preserves all observable behavior, the JIT can scalar-replace/eliminate the physical allocation.

**Question 12.** What is the argument evaluation order of a constructor?

**Answer:** Left to right, after allocation for an ordinary class instance creation expression according to the JLS.

## 15. Memory map

~~~text
JAVA SOURCE                JVM / HOTSPOT
new Type(args)
      |
      +--> Resolve class, class initialization if needed
      |
      +--> Allocate instance  (HotSpot: TLAB or slow path)
      |
      +--> Default fields     (0, false, NUL, +0.0, null)
      |
      +--> Evaluate args      (left to right)
      |
      +--> invokespecial <init>
              |
              +-- Object/superclass constructor chain
              +-- superclass initializers / constructor body
              +-- subclass initializers / constructor body
              |
              v
          Success? -- YES --> return reference to instance
                   -- NO  --> exception, no normal result

Class init: <clinit>, not per-object constructor
Arrays: newarray / anewarray / multianewarray
TLAB: heap allocation fast path, NOT thread stack
JIT: may eliminate physical allocation, but must preserve semantics
~~~

**Conclusion:** instance creation has two distinct parts: **allocation + default initialization** managed by the JVM and **constructor initialization** executed by `<init>` code. The superclass constructor runs before the subclass's initialization, so it can encounter default values while the object is still under construction. Understanding TLAB, object headers, and JIT helps distinguish Java's guarantees from HotSpot's internal optimizations.

## Official documentation

- [JLS Java SE 17 — `15.9.4 Run-Time Evaluation of Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.4).
- [JLS Java SE 17 — `12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5).
- [JVMS Java SE 17 — `6.5 new](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.new).
- [JVMS Java SE 17 — `2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3).
- [JVMS Java SE 17 — `2.9.1 Instance Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9.1).
- [JVMS Java SE 17 — `4.10.2.4 Newly Created Objects](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10.2.4).
- [OpenJDK HotSpot source — oop.hpp (implementation details)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/oop.hpp).
- [JDK 17 — javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
