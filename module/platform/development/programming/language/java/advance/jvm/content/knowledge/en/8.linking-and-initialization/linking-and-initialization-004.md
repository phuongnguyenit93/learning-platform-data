# Preparation: Creating Static Fields and Setting Default Values in the JVM

## Objectives

In the lifecycle of a class or interface, **preparation** is a phase belonging to **linking**. In this step, the JVM creates the state for the **static fields** of the class/interface and sets them to their **type-specific default values**. Preparation does not execute the Java instructions used to initialize fields to the values written by the programmer in the source code.

This lesson helps you:
- Distinguish **loading, verification, preparation, resolution, and initialization**.
- List the default values of all primitive/reference static field types, including non-floating-point numbers and `char`.
- Explain why `static int x = 10` still has the default value **0** when preparation completes.
- Distinguish `<clinit>`, `ConstantValue`, inline compile-time constants, and operations that trigger initialization.
- Analyze cases where 0/null values can be observed while the static initializer is running, without mistakenly thinking that Java code runs during preparation.
- Try Java 17+ examples, use `javap -c -v -p` to inspect the class file, and identify initialization code.
- Avoid confusing static state with instance fields, array elements, and local variables.

## 1. Position of preparation in the class lifecycle

An overview diagram according to the JVMS:

~~~text
             Binary representation of class / interface
                           |
                           v
                         LOADING
                 Create runtime class/interface
                           |
                           v
                         LINKING
                           |
                 +---------+---------+
                 |         |         |
           Verification  Preparation  Resolution
                           |
                 Static fields receive
                 DEFAULT values
                           |
                           v
                     INITIALIZATION
             ConstantValue if present
             and run <clinit> per rules
                           |
                           v
                        EXECUTION
~~~

The diagram describes the concepts; it does **not** require resolution of all symbolic references to complete before initialization. The JVM may resolve eagerly or on demand, within the limits permitted by the specification. What is clearly guaranteed: **preparation must complete before initialization** of the class/interface.

| Phase | Typical work | Not synonymous with |
| --- | --- | --- |
| Loading | Create runtime class/interface from class/JAR data or other sources | All statements in the static block have run |
| Verification | Verify bytecode and valid type constraints | Running Java business logic |
| **Preparation** | Create static fields, set default values, check certain loading constraints | Running the expression `= 5` or a constructor |
| Resolution | Resolve symbolic references to classes/fields/methods... | Automatically invoking all related static initializers |
| Initialization | Execute the class initialization procedure, including `ConstantValue` and `<clinit>` if present | Simply setting 0 for static fields |

According to **JVMS `5.4.2**, preparation can occur after the class/interface has been created and must finish before initialization. From normal Java code, there is no universal API to pause the preparation process at an exact point and then arbitrarily read static fields without being subject to class initialization rules.

## 2. What does preparation do?

Suppose:

~~~java
class Profile {
    static int visits = 10;
    static boolean ready;
    static String title = "Java";
    static Object resource = new Object();
}
~~~

This is an **illustrative class**, without a `main` method yet. When preparation of `Profile` completes, the semantics of the static fields are:

| Static field | Value after preparation | What will initialization code do? |
| --- | --- | --- |
| `visits` | `0` | Assign to `10` |
| `ready` | `false` | Has no initializer, so it remains false if not assigned afterward |
| `title` | `null` | Assign the String reference corresponding to `"Java"` |
| `resource` | `null` | Execute the expression `new Object()`, then assign the reference |

**No** new `Object` instance is created just because `resource` has a reference type. During preparation, a reference field defaults to `null`. Executing `new Object()` belongs to **initialization**, not preparation.

The JVM does not need to run a bytecode sequence like `putstatic Profile.visits` with the value 0 for each field during preparation. This is a linking operation of the VM; therefore, not seeing "default assignment code" in `javap -c` is completely normal.

### What does the phrase "creating static fields" mean?

It means the VM prepares the **static field state of the runtime class/interface**. The JVMS specifies the semantic result, **without requiring** the physical location or memory layout to be identical across all JVMs. Avoid unsubstantiated claims such as "all static fields in every JVM version are always located at a fixed address in Metaspace".

Fields are created per **declaring class/interface**. Two class loaders can define two different runtime types even if they have the same binary name, and each such runtime type has its **own static state**. Static does not mean "one single variable for all class loaders in the process".

## 3. Complete table of default values

| Field type | Declaration example | Default value |
| --- | --- | --- |
| `byte` | `static byte b;` | `0` |
| `short` | `static short s;` | `0` |
| `int` | `static int i;` | `0` |
| `long` | `static long l;` | `0L` |
| `float` | `static float f;` | `+0.0f` |
| `double` | `static double d;` | `+0.0d` |
| `char` | `static char ch;` | NUL, code point `0` (`'\u0000'`) |
| `boolean` | `static boolean ok;` | `false` |
| Class/interface reference | `static String str;` | `null` |
| Array reference | `static int[] data;` | `null` |
| Reference to user-defined object | `static Worker worker;` | `null` |

Common points of confusion:

- `char` receives **code unit 0**, different from the digit character `'0'` (code unit 48) and different from whitespace.
- `float` and `double` default to **positive 0**, not NaN, infinity, or negative 0.
- `String` defaults to **null**, not the empty string `""`.
- Array references default to **null**, not a zero-length array.
- Integer numeric fields all have the numeric value 0; `boolean` is false, not a created `Boolean.FALSE` object.
- The table above describes the state **after preparation**; a field may continue to hold that value after initialization if there is no assignment replacing it.

### Static fields are not local variables

Example:

~~~java
class Example {
    static int shared;

    void work() {
        int local;
        // System.out.println(local); // Invalid: local has not been assigned.
        System.out.println(shared);    // Valid: static field has default 0.
    }
}
~~~

This is illustrative class code, not a standalone program. Java requires **definite assignment** for local variables before reading them. Fields are part of the state assigned default values by the VM according to field rules; do not confuse the two mechanisms.

## 4. Preparation is completely different from initialization

Compare:

~~~java
class ClockState {
    static int ticks = 15;

    static {
        System.out.println("static block");
    }
}
~~~

During preparation, `ticks` has default `0`. When initialization executes, the expression `ticks = 15` and the static block run in the appropriate source-code order. The Java compiler usually emits bytecode in the **`<clinit>`** method:

~~~text
bipush        15
putstatic     #N    // ClockState.ticks:I
getstatic     #M    // java/lang/System.out
ldc           #K    // "static block"
invokevirtual #P    // java/io/PrintStream.println
return
~~~

This is **illustrative bytecode**, not output guaranteed to have the same `#N`/`#M` indices on every compiler. Seeing `putstatic` used to assign 15 means there is **explicit initialization logic**. Preparation already created the field and default value beforehand; it does not need to run this code.

| Question | Preparation | Initialization |
| --- | --- | --- |
| Does the field `static int x = 15` have state yet? | Yes, default 0 | Assigns x to 15 |
| Does the JVM run an `initializeX()` method? | No | Yes if an explicit initializer requires it |
| Does the static block run? | No | Yes |
| Does `<clinit>` run? | No | Yes if the class has one and needs to run |
| Does the reference field `= new Object()` have an object yet? | No, default null | Constructor/new runs according to the initializer |
| Is `ConstantValue` involved? | Does not assign that value in preparation per JVMS 21 | Assigned during the initialization procedure, **before** `<clinit>` |

We must distinguish the **order of components in the specification** from the moment an application thread can observe them. It does not mean a statement outside the class can actively read a static field between the two phases without triggering initialization.

## 5. Java 17+ example observing the effect of default values

The following complete example helps observe the default value of a field **while the initializer is running**, before a subsequent initializer is executed. It does not make the JVM execute Java code during preparation.

Create the file **`PreparationDemo.java`**:

~~~java
public class PreparationDemo {
    static class State {
        static boolean enabled;
        static long requests;
        static double ratio;
        static char letter;
        static Object object;

        static int first = readLater();
        static int later = 21;
        static final int CONSTANT = 7;

        static int readLater() {
            System.out.println("during init: later=" + later);
            return later + 1;
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("first=" + State.first);
        System.out.println("enabled=" + State.enabled);
        System.out.println("requests=" + State.requests);
        System.out.println("ratio=" + State.ratio);
        System.out.println("letterCode=" + (int) State.letter);
        System.out.println("object=" + State.object);
        System.out.println("later=" + State.later);
        System.out.println("constant=" + State.CONSTANT);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 PreparationDemo.java
java PreparationDemo
~~~

**Exact stdout:**

~~~text
start
during init: later=0
first=1
enabled=false
requests=0
ratio=0.0
letterCode=0
object=null
later=21
constant=7
~~~

Detailed explanation:

1. The outer class `PreparationDemo` is initialized when the launcher invokes `main`. The nested class `State` has its own initialization lifecycle.
2. The line `start` is printed before the program needs the value of `State.first`.
3. Reading `State.first` via static field access triggers initialization of `State` according to JVM rules, after preparation of `State` has completed.
4. After preparation, `State.first = 0` and `State.later = 0`. The other fields have false/0/+0.0/NUL/null as shown in the table.
5. Inside `<clinit>`, the initializer **`first = readLater()`** runs **before** the initializer `later = 21`. The `readLater()` method reads `later` which is currently 0, prints `during init: later=0`, and returns 1.
6. At that point `first` is assigned 1. Next, `later` is assigned 21.
7. After initialization completes, the reads in `main` produce `first=1` and `later=21`.
8. `CONSTANT = 7` is a compile-time constant variable. The compiler may **inline the value 7** into the caller; the line printing constant does not prove there is a `getstatic State.CONSTANT` at runtime.

**Why use the `readLater()` method?** Java forbids certain **illegal forward references** in field initializers when directly accessing a field declared later by its simple name. Placing the read inside a valid method is a compilable way to demonstrate this. Even though the JVMS guarantees default values, the **Java compiler still has rules regarding forward references** that must be obeyed.

### Accurate phrasing

Do not say "preparation runs `readLater()`". The accurate statement is: **preparation sets `later` to 0; then initialization runs `readLater()` before assigning 21, so the method sees 0**.

This also explains why seeing 0 is not enough to know that the class *is currently* in preparation: a field can have the value 0 before its initializer assigns it or because it has no initializer at all, even after the class has finished initializing.

## 6. ConstantValue: distinguishing from default value

A common knowledge trap is saying "`static final` has its value right in preparation". To be accurate according to **JVMS Java SE 17 §5.4.2, §5.5, and §4.7.2**:

- **Preparation** creates static fields and assigns default values.
- **Initialization** assigns the value of the **`ConstantValue`** attribute to eligible `static final` fields, **before invoking the `<clinit>` method**.
- Then the static initialization code in `<clinit>` (if present) executes the remaining initializers.

Example:

~~~java
class Sample {
    static final int LIMIT = 10;
    static final String LABEL = "ok";
    static int counter = 5;
    static final Integer BOXED = Integer.valueOf(6);
}
~~~

This is an illustrative class. Meaning of each field:

| Field | Default from preparation | Can it have `ConstantValue`? | How it gets its declared value |
| --- | --- | --- | --- |
| `LIMIT` | 0 | Yes, `int 10` | ConstantValue assigned during initialization |
| `LABEL` | null | Yes, `String ok` | ConstantValue assigned during initialization |
| `counter` | 0 | No just because of a literal initializer, since it is not final | `<clinit>` assigns 5 via `putstatic` |
| `BOXED` | null | No per primitive/String constant variable rules | `<clinit>` calls `Integer.valueOf` then assigns |

### Runnable example to view the attribute

Create **`ConstantValueDemo.java`**:

~~~java
public class ConstantValueDemo {
    static final int LIMIT = 100;
    static final String LABEL = "ready";

    static int dynamic = 23;
    static final Integer BOXED = Integer.valueOf(7);

    static {
        System.out.println("initialized");
    }

    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println("label=" + LABEL);
        System.out.println("dynamic=" + dynamic);
        System.out.println("boxed=" + BOXED);
    }
}
~~~

Commands:

~~~bash
javac --release 17 ConstantValueDemo.java
java ConstantValueDemo
javap -v -p ConstantValueDemo
javap -c -p ConstantValueDemo
~~~

**Program stdout:**

~~~text
initialized
limit=100
label=ready
dynamic=23
boxed=7
~~~

When reading `javap -v`, look for:
- `LIMIT`: flags `ACC_STATIC, ACC_FINAL`, descriptor `I`, attribute **`ConstantValue: int 100`**.
- `LABEL`: descriptor `Ljava/lang/String;` and attribute **`ConstantValue: String ready`**.
- `dynamic`: does not have `ConstantValue` just because the initializer is 23; usually assigned via `putstatic` in `<clinit>`.
- `BOXED`: initialized by calling `Integer.valueOf(7)` in `<clinit>`, does not automatically create an Integer object in preparation.

**Note:** compile-time constants can be **inlined into the caller** by the compiler. An external class that only reads `Sample.LIMIT` may not emit `getstatic` and may not trigger initialization of `Sample` because the value is already in the caller itself. If you change the constant value in a library without recompiling the caller, the caller may still retain the old value.

Do not use the printing of `LIMIT=100` to deduce that it was assigned during preparation; the specification clearly defines the boundary for ConstantValue assignment.

## 7. Code in `<clinit>` and execution order

The Java compiler can synthesize **static field initializers** and **static initialization blocks** into the special method `<clinit>` in source order. Example:

~~~java
class Steps {
    static int first = log("first", 1);

    static {
        System.out.println("block");
    }

    static int second = log("second", 2);

    static int log(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

This is an illustrative class without `main()`. When initialization of `Steps` is triggered and proceeds normally, the side effects appear:

~~~text
first
block
second
~~~

Preparation already created both `first` and `second` with default 0 **before** these printed lines; it did not execute `log` or `println`.

Not every class has `<clinit>` in the compiled file. If there is no static initialization bytecode that needs to run, the compiler may omit emitting that method. **Not seeing `<clinit>` does not prove that preparation was skipped**.

### Classes and interfaces

Interfaces also have static fields. In Java source, interface fields are implicitly **`public static final`**, but the initializer can be a method call and **not a compile-time constant**:

~~~java
interface FeatureFlags {
    int FAST_LIMIT = 64;
    String JAVA_VERSION = System.getProperty("java.version");
}
~~~

This is an illustrative interface. Static fields are prepared before initialization. `FAST_LIMIT` can use `ConstantValue`, whereas `JAVA_VERSION` needs executable code during interface initialization. Interfaces have their own initialization trigger rules; creating an object implementing an interface does not simply mean "initialize all related interfaces immediately".

## 8. Static field, instance field, array element, and local variable

**Preparation is an operation on static fields of a class/interface**, not an allocation/default-setting mechanism for all data in a program.

| Data kind | Source of default value | Example |
| --- | --- | --- |
| **Static field** | Preparation of the declaring class/interface | `static int total;` → 0 |
| **Instance field** | Object creation, before constructor/instance initialization | `int age;` on each new object → 0 |
| **Array element** | Array creation, each element is assigned a default | `new int[3]` → 0,0,0 |
| **Local variable** | Java requires definite assignment before reading; cannot automatically read an arbitrary default value | `int x; println(x);` compile-time error |

Complete example **`DefaultKindsDemo.java`**:

~~~java
import java.util.Arrays;

public class DefaultKindsDemo {
    static int shared;
    int perObject;

    public static void main(String[] args) {
        DefaultKindsDemo first = new DefaultKindsDemo();
        DefaultKindsDemo second = new DefaultKindsDemo();
        int[] numbers = new int[3];

        first.perObject = 5;

        System.out.println("shared=" + shared);
        System.out.println("first=" + first.perObject);
        System.out.println("second=" + second.perObject);
        System.out.println("array=" + Arrays.toString(numbers));
    }
}
~~~

Run:

~~~bash
javac --release 17 DefaultKindsDemo.java
java DefaultKindsDemo
~~~

**Exact stdout:**

~~~text
shared=0
first=5
second=0
array=[0, 0, 0]
~~~

`shared` is a prepared static field, the two `perObject` fields belong to two different objects, and the three array elements are defaulted when the array is allocated. All of them can show the number 0, but **not all of them are consequences of class preparation**.

## 9. Which class type does the JVM associate preparation with?

The runtime identity of a class/interface is not based solely on the class name string in source: the JVM distinguishes by **binary name + defining class loader**. Two different defining loaders can create two runtime classes with the same binary name, with different static states:

~~~text
com.example.Config defined by Loader A
  -> static counter A
  -> preparation A / initialization A

com.example.Config defined by Loader B
  -> static counter B
  -> preparation B / initialization B
~~~

This is a conceptual diagram. Therefore, saying "a static variable always has only one copy across the entire JVM" is inaccurate for applications using plugin class loaders or module layers.

### Loading constraints during preparation

In addition to assigning default values, **JVMS `5.4.2** imposes **loading constraints** when processing certain method overriding/selection cases whose type signatures involve different class loaders.

The goal is to maintain type identity and safe method linking. If a constraint is violated, the JVM may throw **`LinkageError`**, causing preparation/linking to fail. Preparation should not be treated as just a loop setting zeros that can never be involved in type/linking errors.

**Not synonymous with resolution**: resolution resolves symbolic references to classes/fields/methods and other entities according to its own rules. It can be performed eagerly or on demand; preparation must complete before initialization.

## 10. Operations that trigger initialization

Java code normally cannot observe a field in the state between preparation and initialization because operations that use the class or static field can **trigger initialization**. Some common triggers:
- `new SomeClass()` (creating an instance).
- Reading a static field via `getstatic` or writing via `putstatic` according to JVM rules.
- Calling a static method via `invokestatic`.
- Certain reflection or method-handle actions specified to trigger initialization.
- An initialized class may require its superclass or relevant superinterfaces to be initialized according to the rules.

Not every operation that "mentions the class name" triggers initialization:
- Taking a class literal `SomeClass.class` does not simply run the static block just because the class name is mentioned.
- Compile-time constants can be inlined, without needing to read the field at runtime.
- `Class.forName(className, false, loader)` allows obtaining the Class without requesting initialization from that call; however, that **does not mean you can read a static field via reflection while bypassing initialization rules**.

**Important:** a class can be loaded/linked before its initializer runs; do not equate "the JVM knows about the class" with "all static initializers have completed".

## 11. What happens when multiple threads use a class simultaneously?

The JVM has rules to synchronize the initialization process to handle multiple concurrent threads. One thread may be running `<clinit>`, and another thread requesting initialization of the same class must follow the JVM's waiting/ordering mechanism. If the initializing thread itself indirectly requests the same class, there are rules to recognize **initialization in progress**.

An initializer reading another field too early may see the **default** value or a partially assigned value in the initialization chain. You should not use "the time between preparation and initialization" as a thread communication mechanism. Instead, structure initialization without circular dependencies or use a clear coordination mechanism.

**Illustrative** example of a circular dependency:

~~~java
class A {
    static int x = B.y + 1;
}

class B {
    static int y = A.x + 1;
}
~~~

These are two class declarations, without `main`. If A and B have a circular dependency when initialized, one side reading the other's static field before the corresponding initializer runs can cause it to see the default 0. Depending on the trigger and execution order, the final result may differ from expectations if you assume all fields already have their final values.

### Preparation does not replace thread safety

Preparation sets `static int counter` to 0; it does **not** make `counter++` atomic. Later on, multiple threads performing concurrent read-modify-write must use appropriate synchronization tools if correctness is needed, such as `AtomicInteger` or a synchronized block per the application design.

## 12. Using javap to see the difference

For the compiled file from the `PreparationDemo.java` example:

~~~bash
javap -v -p 'PreparationDemo$State'
javap -c -p 'PreparationDemo$State'
~~~

**In Windows cmd.exe**, you can use the expression `PreparationDemo$State` according to the appropriate shell syntax; in PowerShell, single quotes as above prevent the shell from interpreting the `$` sign. The examples above assume the class file has been compiled in the current directory.

When reading the output:
1. The field declaration of the nested class contains `ACC_STATIC`; identify the name, descriptor, and flags.
2. `first` and `later` have descriptor `I` (int); the other fields have descriptors `Z`, `J`, `D`, `C`, or reference types.
3. In `<clinit>`, look for the instruction calling `readLater()`, `putstatic ...first:I`, loading the value 21, and then `putstatic ...later:I`.
4. The `CONSTANT` field may have a `ConstantValue` attribute because it is a compile-time constant.
5. There is no `putstatic` instruction assigning the initial 0 to **every** field; default values belong to preparation, not Java bytecode that must exist in `<clinit>`.
6. Bytecode index `#N` may differ across compilers and JDK versions. Do not hardcode them in interpretations.

A class file diagram:

~~~text
field_info later:
  access_flags: ACC_STATIC
  descriptor:   I

Preparation:
  later = 0          (VM operation)

Initialization:
  <clinit>:
    bipush 21
    putstatic #N      // later:I
~~~

This is a diagram combining class file information and runtime operations, **not** an exact binary dump of the entire class.

## 13. Common errors and misconceptions

| Claim or symptom | Accurate analysis |
| --- | --- |
| "`static int x = 10` is assigned 10 in preparation." | Preparation sets 0; the explicit initializer 10 belongs to initialization. |
| "Every reference field has an object pre-created." | The default is `null`; constructors/arrays are only allocated when code executes. |
| "`static final int X=10` is definitely assigned in preparation." | According to JVMS 21, `ConstantValue` is assigned during the initialization procedure before `<clinit>`. |
| "A field value of 0 proves the JVM is in preparation." | No. A field can remain 0 even after initialization or be read before its initializer in `<clinit>`. |
| "Not seeing `<clinit>` means preparation did not happen." | False. Preparation is something the VM does, not a Java method required to appear in the class file. |
| "A static object field always has a single copy in the entire JVM." | Each **runtime class** has its own static state; different class loaders can define different classes. |
| "`Class.forName(name,false,loader)` allows reading static values before initialization." | Does not by itself provide the ability to bypass initialization rules when reading a static field. |
| "Default values of instances/arrays are also caused by class preparation." | False: instances/arrays receive defaults at object/array creation time. |
| "Preparation never has errors." | Loading constraints in preparation can fail, causing `LinkageError`. |
| "Initialization failing means preparation has not been done." | False: preparation must complete before initialization. |
| "A `volatile` field is prepared so `x++` is atomic." | False: volatile is semantics about memory visibility/order, it does not turn read-modify-write into an atomic operation. |
| "A loaded class means it is initialized." | False: loading/linking and initialization are separate steps. |

### When errors occur

**`VerifyError`** is usually related to verification, **`ClassFormatError`** to class file format, **`NoSuchFieldError`** to field resolution, while **`ExceptionInInitializerError`** usually originates from code running during class initialization. Do not attribute all class lifecycle errors to preparation.

When diagnosing, check:
1. Is the code loading, linking, or running a static initializer?
2. Does the error have a cause from `<clinit>`?
3. Which class and dependency/JAR was actually loaded by the loader?
4. Is there an initializer reading a field declared later or a circular dependency between classes?
5. Was the field's descriptor/static modifier changed between build and runtime?
6. Could the compiler have inlined a compile-time constant?

## 14. Self-check questions

**1.** Is preparation part of loading, linking, or initialization?

**Answer:** It is a step of **linking**; it must complete before initialization.

**2.** After preparation, what value does `static int count = 5;` have?

**Answer:** **0**. The assignment of 5 belongs to initialization.

**3.** Does `static String name;` default to the empty string?

**Answer:** No. It is `null`.

**4.** Is `static char letter;` the digit character 0 or code unit 0?

**Answer:** Code unit **0** (NUL, `'\u0000'`), not `'0'`.

**5.** Why did `State.readLater()` in the example see `later=0`?

**Answer:** Preparation had set the default 0. The method was executed **during initialization**, before the assignment statement `later = 21`.

**6.** Is `ConstantValue` of `static final int LIMIT` assigned in preparation or initialization according to JVMS 21?

**Answer:** During **initialization**, before the invocation of `<clinit>`.

**7.** Does reading a constant variable from a caller guarantee that the declaring class is initialized?

**Answer:** No. The compiler can inline the value, without needing `getstatic`.

**8.** How do a static field and an instance field differ in when they receive their default values?

**Answer:** A static field receives its default during class/interface preparation; an instance field receives its default when the object is allocated, before constructor logic.

**9.** Do two class loaders defining the same class name necessarily share static fields?

**Answer:** No. They can create different runtime classes, each with its own state.

**10.** Why should preparation not be thought of as running a series of compiler-generated `putstatic 0` instructions?

**Answer:** Preparation is performed by the JVM as a linking step, without requiring explicit Java bytecode to run.

**11.** Does preparation involve loading constraints?

**Answer:** Yes. JVMS `5.4.2 specifies constraints related to overriding/selection; violations can cause `LinkageError`.

**12.** If no static initializer is seen in the class file, does the class not need preparation?

**Answer:** False. Preparation still occurs according to the lifecycle mechanism, even if there is no `<clinit>` code to run.

## 15. Summary

~~~text
Class / interface has been loaded
                |
                v
              LINKING
  +-------------+-------------+
  |             |             |
Verify      PREPARATION     Resolution
                |
                +-- create static fields
                +-- assign DEFAULT VALUES
                |    primitive numeric 0
                |    boolean false
                |    char NUL
                |    references null
                +-- necessary loading constraints
                |
                v
           INITIALIZATION
     ConstantValue (if present)
     then <clinit> (if present)
     static initializers / static blocks
                |
                v
       Class initialized

Instance field default: at object creation
Array element default: at array creation
Local variable: definite assignment
~~~

**Conclusion:** Preparation is **not** the phase that executes Java source initializers. It creates the static state for a class/interface with **default** values, before initialization. Separating this process from `ConstantValue`, `<clinit>`, object creation, and constant inlining is the foundation for understanding the JVM lifecycle accurately according to the specification.

## Official documentation

- [JVMS Java SE 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2).
- [JVMS Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).
- [JVMS Java SE 17 — 4.7.2 ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2).
- [JVMS Java SE 17 — 2.3 Primitive Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.3).
- [JVMS Java SE 17 — 2.4 Reference Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.4).
- [JLS Java SE 17 — 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
- [JLS Java SE 17 — 8.3.3 Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3).
- [JDK 17 — javap Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
