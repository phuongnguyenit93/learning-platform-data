# Default Values Before Field Initializers in Java

When Java creates an object or prepares a class for use, **fields have default values before their field initializer expressions are executed**. Therefore, two seemingly identical statements—“a field initially has the value 0” and “a field is assigned 0 by the programmer”—are not completely identical in terms of **timing** and **mechanism**.

Example:

~~~java
class Sensor {
    int count = 10;
    boolean active = true;
    String label = "READY";
}
~~~

When allocating a `Sensor` object, the instance fields initially receive **`0`**, **`false`**, and **`null`**, respectively. Only afterward, during object initialization, are the initializers `= 10`, `= true`, and `= "READY"` executed. For `static` fields, the step that sets default values takes place during **preparation** when the class is linked; static initializers then run during the **class initialization** phase.

For normal programs, the final state after the constructor completes is what the caller typically observes. However, this order can be observed when an initializer calls a method that reads a field whose turn for assignment has not yet come, or when a superclass constructor calls a method overridden by a subclass. Understanding this helps explain output, avoid mistakes when designing constructors, and distinguish between **fields**, **array elements**, and **local variables**.

This lesson belongs to **Java core - class-object**, section **Initialization Order**. The complete programs use Java 17+, with filenames, compile/run commands, and stdout for reference.

## 1. Three Points in Time to Distinguish

For an instance field with the initializer `int size = 12;`, distinguish between:

1. **Allocation and setting default values:** the field storage area of the new object is allocated; `size` initially receives `0`.
2. **Running the field initializer:** when it is the turn of the initializers in the class declaring the field, `size = 12` is executed.
3. **Running the constructor body:** the constructor may continue performing validation or other operations according to Java's rules; after initialization succeeds, the caller receives the object with its established state.

Simple model:

~~~text
new Sensor()
    |
    v
Allocate object
count = 0, active = false, label = null
    |
    v
Corresponding superclass constructor steps
    |
    v
Run instance field initializers / instance initializer blocks
count = 10, active = true, label = "READY"
    |
    v
Run Sensor constructor body
    |
    v
Object returned upon successful creation
~~~

This is a diagram for a simple class; constructor chaining via `this(...)` has its own rules and **does not repeatedly run instance initializers** after each delegation. For a subclass, the initialization order of each class follows the corresponding constructor chain, which is explained later.

**Important:** having a default value in the initial phase **does not guarantee that every ordinary piece of Java code is allowed to read that value before the initializer**. The language also has rules prohibiting certain forward references to fields and definite assignment rules for `final`.

## 2. Exact Table of Field Default Values

**Instance fields** and **static fields** are set to default values corresponding to their data types before the appropriate explicit initialization steps:

| Field type | Default value | Notes |
| --- | --- | --- |
| `byte` | `0` | 8-bit integer |
| `short` | `0` | 16-bit integer |
| `int` | `0` | 32-bit integer |
| `long` | `0L` | 64-bit integer |
| `float` | `+0.0f` | Positive floating-point zero |
| `double` | `+0.0d` | Positive floating-point zero |
| `boolean` | `false` | Not `null` |
| `char` | Character with code `U+0000` | Usually invisible when printed directly |
| Any reference type: `String`, object, array, wrapper, `List` | `null` | Does not automatically create an object/collection |

Two points that are easy to get wrong:

- **`String` does not default to the empty string `""`**. A field `String name;` will be `null` before an appropriate assignment occurs.
- **The field `int[] values;` defaults to `null`**, and does not automatically become an empty array. If initialized with `new int[3]`, that creates a new array object, and **the elements** of the array in turn have their own defaults (`0` for `int`).

The values above are specified by the language and do not depend on how a specific JVM places fields on the heap, in which memory area, or in which register.

## 3. Complete Program: Viewing Defaults Before Adding Explicit Initializers

Create the file **`DefaultFieldValuesDemo.java`**:

~~~java
class DefaultFields {
    byte small;
    short medium;
    int count;
    long total;
    float ratio;
    double average;
    boolean enabled;
    char symbol;
    String title;
    int[] numbers;

    String describe() {
        return "byte=" + small
                + ",short=" + medium
                + ",int=" + count
                + ",long=" + total
                + ",float=" + ratio
                + ",double=" + average
                + ",boolean=" + enabled
                + ",charCode=" + (int) symbol
                + ",ref=" + title
                + ",array=" + numbers;
    }
}

public class DefaultFieldValuesDemo {
    public static void main(String[] args) {
        DefaultFields fields = new DefaultFields();
        System.out.println(fields.describe());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DefaultFieldValuesDemo.java
java DefaultFieldValuesDemo
~~~

**Exact stdout:**

~~~text
byte=0,short=0,int=0,long=0,float=0.0,double=0.0,boolean=false,charCode=0,ref=null,array=null
~~~

**Explanation:** The `DefaultFields` class has no initializers on the declared fields. Java still sets default values, so there is no need to manually write `count = 0`, `enabled = false`, or `title = null` to avoid “reading garbage” as in some other languages.

The cast `(int) symbol` shows that the default character has code 0. If `symbol` were printed directly, the U+0000 character would usually not render as a recognizable symbol on the console.

**Do not take this as advice to always omit initializers.** `new ArrayList<>()`, or a required value such as an order ID or an `ACTIVE` status, should be explicitly set in the appropriate place; Java only guarantees default values at the language level, not that they satisfy **business invariants**.

## 4. Fields Differ from Local Variables: Locals Have No Readable Default

This is the most important point when comparing fields with variables inside a method.

For a field:

~~~java
class ReadableField {
    int number;

    int read() {
        return number; // Valid: number defaults to 0.
    }
}
~~~

For a local variable:

~~~java
class LocalExample {
    static void demo() {
        int number;
        // System.out.println(number); // Compile error: not definitely assigned.
        number = 5;
        System.out.println(number);
    }
}
~~~

Both classes are valid illustrative snippets because the intentionally erroneous line is commented out. **Local variables and parameters** follow their own definite assignment rules; a local variable that has not been definitely assigned cannot be read. Java **does not automatically give a local `int number;` a usable default value of 0**.

Method/constructor parameters receive argument values via pass-by-value; they are not newly allocated instance fields.

| Declaration location | Has usable default value? | Example |
| --- | --- | --- |
| Instance field `int x;` | Yes | `0` |
| Static field `static int x;` | Yes, in the type preparation mechanism | `0` |
| Element of `new int[3]` | Yes | Each element is `0` |
| Local `int x;` | **Cannot be read before definite assignment** | Rejected by compiler |
| Parameter `void f(int x)` | Receives value passed by caller | Does not automatically take 0 |

Do not infer from “Java has default values” that “every Java variable automatically has a readable default value”.

## 5. Arrays Also Receive Defaults, but at a Different Object Creation Stage

When writing `new int[3]`, Java creates an **array object** with three `int` elements defaulting to 0. If writing `new String[2]`, each element is a reference defaulting to `null`. This is **different** from an unassigned `int[]` reference field, which is `null`.

Create the file **`ArrayDefaultValuesDemo.java`**:

~~~java
import java.util.Arrays;

class Element {
    static {
        System.out.println("Element initialized");
    }

    Element() {
        System.out.println("Element constructed");
    }
}

public class ArrayDefaultValuesDemo {
    public static void main(String[] args) {
        int[] counts = new int[3];
        boolean[] checks = new boolean[2];
        String[] names = new String[2];

        System.out.println("counts=" + Arrays.toString(counts));
        System.out.println("checks=" + Arrays.toString(checks));
        System.out.println("names=" + Arrays.toString(names));

        Element[] elements = new Element[2];
        System.out.println("element slot=" + elements[0]);

        elements[0] = new Element();
        System.out.println("created=" + (elements[0] != null));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ArrayDefaultValuesDemo.java
java ArrayDefaultValuesDemo
~~~

**Stdout:**

~~~text
counts=[0, 0, 0]
checks=[false, false]
names=[null, null]
element slot=null
Element initialized
Element constructed
created=true
~~~

`new Element[2]` creates a **reference array**, not two `Element` objects, and does not automatically initialize the `Element` class simply because an array holds elements of that type. Only at `new Element()` in the example does the `Element` class require initialization, after which the constructor is called.

**Array element defaults** are a mechanism applied when creating an array object, which does not mean running initializers in the `Element` class. Likewise, an `int[]` array does not invoke a constructor for each integer.

## 6. `static` Fields: Defaults Are Set During Preparation

For a class with a static field:

~~~java
class GlobalConfig {
    static int retryCount = computeRetries();

    private static int computeRetries() {
        return 3;
    }
}
~~~

This is a valid illustrative class. When the class is **linked**, the **preparation** step prepares the storage for `retryCount` and gives it the default value `0`; `computeRetries()` **has not run yet during preparation alone**.

Only when the class is **initialized** is the call `computeRetries()` executed and the result assigned to `retryCount`. Reading `GlobalConfig.retryCount` from outside is an *active use* of a non-constant static field, so it normally **triggers initialization** before returning the value. Therefore, the caller typically reads 3 rather than seeing 0.

~~~text
Loading / linking:
    retryCount = 0          (preparation)
    DOES NOT call computeRetries()

Initialization of GlobalConfig:
    run computeRetries() -> 3
    retryCount = 3

After successful initialization:
    GlobalConfig.retryCount -> 3
~~~

This model helps explain why a static block can observe the default value of a **static field declared later in the source** in permitted situations, yet it does **not** mean that any earlier read of the field from another class will see 0.

## 7. Runnable Example: Static Initializer Reading a Later-Declared Field Through a Method

Create the file **`StaticFieldOrderDemo.java`**:

~~~java
class StaticSequence {
    static int first = calculateFirst();

    static int second = 42;

    static {
        System.out.println("block second=" + second);
    }

    private static int calculateFirst() {
        System.out.println("during: second=" + second);
        return second + 5;
    }
}

public class StaticFieldOrderDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("first=" + StaticSequence.first);
        System.out.println("second=" + StaticSequence.second);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticFieldOrderDemo.java
java StaticFieldOrderDemo
~~~

**Exact stdout:**

~~~text
before
during: second=0
block second=42
first=5
second=42
~~~

### Step-by-Step Explanation

1. `main` prints `before`.
2. Accessing `StaticSequence.first` requires initializing `StaticSequence`.
3. Before the initializers run, `first` and `second` already have the **default value 0** from the preparation step.
4. The initializer of `first` runs first and calls `calculateFirst()`.
5. `calculateFirst()` reads the field `second` via the method—at this moment the initializer `second = 42` **has not run yet**, so it prints `0` and returns `5`.
6. Java proceeds to the initializer `second = 42` and then runs the static block, printing `block second=42`.
7. `main` then prints `first=5` and `second=42`.

This is a **phenomenon where default values can be observed before initializers**. It is not a good design guarantee; if `first` genuinely needs `second = 42`, you should **place `second` before `first`**, compute via an appropriate constant, or separate the initialization logic clearly.

## 8. Instance Fields: Default Values Also Exist Before Initializers

For instance fields, the default-value mechanism occurs **each time a new object is allocated**. The initializers are executed in their corresponding textual order during the constructor execution of the declaring class.

Create the file **`InstanceFieldOrderDemo.java`**:

~~~java
class InstanceSequence {
    int first = calculateFirst();
    int second = 7;
    boolean ready = true;

    {
        System.out.println("block second=" + second
                + ", ready=" + ready);
    }

    private int calculateFirst() {
        System.out.println("during: second=" + second
                + ", ready=" + ready);
        return second + 5;
    }

    InstanceSequence() {
        System.out.println("constructor first=" + first
                + ", second=" + second
                + ", ready=" + ready);
    }
}

public class InstanceFieldOrderDemo {
    public static void main(String[] args) {
        System.out.println("before first");
        new InstanceSequence();
        System.out.println("before second");
        new InstanceSequence();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InstanceFieldOrderDemo.java
java InstanceFieldOrderDemo
~~~

**Stdout:**

~~~text
before first
during: second=0, ready=false
block second=7, ready=true
constructor first=5, second=7, ready=true
before second
during: second=0, ready=false
block second=7, ready=true
constructor first=5, second=7, ready=true
~~~

### Why Are 0 and false Read?

After the new object is allocated, its fields have already been set to their defaults, including `second=0` and `ready=false`. Java executes the initializer `first = calculateFirst()` **before** reaching the two initializers of `second` and `ready`. The method `calculateFirst()` therefore sees the default values and returns 5.

Once the initializers `second=7` and `ready=true` complete, the instance initializer block and the constructor body see the assigned values.

When creating the second object, the entire **instance initialization sequence** takes place on a new object, so the phenomenon repeats. This differs from static initialization, which is performed only per class at runtime when needed.

## 9. Source Order Rule: Field Initializers Interleaved with Initializer Blocks

Within a class, **instance field initializers** and **instance initializer blocks** are executed in the order they appear in the source, during that class's instance initialization phase. Similarly, **static field initializers** and **static initializer blocks** are executed in textual order when the class is initialized.

Example:

~~~java
class OrderSketch {
    static int s1 = markStatic("s1");
    static {
        System.out.println("static block");
    }
    static int s2 = markStatic("s2");

    int x1 = markInstance("x1");
    {
        System.out.println("instance block");
    }
    int x2 = markInstance("x2");

    static int markStatic(String name) {
        System.out.println(name);
        return 1;
    }

    int markInstance(String name) {
        System.out.println(name);
        return 1;
    }
}
~~~

This is a valid illustrative class (without `main`). When class initialization occurs, the static group runs in order: `s1`, static block, `s2`. When creating an object, after the relevant superclass steps, the instance group runs in the order `x1`, instance block, `x2`.

**There is no rule that “all field initializers run before all initializer blocks”.** They can be **interleaved** according to the source text. At the same time, static and instance are two separate schedules: `new OrderSketch()` a second time does not re-run the static group.

An instance field initializer can call an ordinary method; when the method reads a field declared later that has not yet been explicitly initialized, it can observe the default value as shown in the previous section.

## 10. Forward References: Not Every Way of Reading a Later Field Is Valid

Java has an **illegal forward reference** rule in [JLS §8.3.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3). If a field is referenced **by simple name** in an initializer of the same class before the appropriate declaration, the compiler may reject it.

Example that **intentionally does not compile**:

~~~java
class BadStaticForward {
    static int first = second; // illegal forward reference
    static int second = 9;
}

class BadInstanceForward {
    int first = second; // illegal forward reference
    int second = 9;
}
~~~

Do not interpret “fields have a default of 0” as “writing `first = second` before declaring `second` is always allowed”.

By contrast, in `StaticFieldOrderDemo`, the name `second` appears **inside the body of the method `calculateFirst()`**, rather than as a restricted direct simple-name reference in a field initializer. It is valid and can read 0 when the method is called too early.

Another way that the JLS does not prohibit under the **simple-name forward reference** rule is accessing via an explicitly qualified name, for example:

~~~java
class QualifiedStaticRead {
    static int before = QualifiedStaticRead.after;
    static int after = 9;
}

class QualifiedInstanceRead {
    int before = this.after;
    int after = 9;
}
~~~

Both classes above **compile**. Provided there are no other unusual assignments, `before` will be 0 because `after` has not yet reached its `= 9` initializer.

**Design warning:** being able to bypass the simple-name restriction does not mean you should intentionally rely on defaults in early references. Field order can be changed during refactoring and cause subtle bugs. A better approach is to **initialize dependencies before the fields that depend on them**.

## 11. Verifying with a Program: Qualified Forward Reference

Create the file **`QualifiedForwardReferenceDemo.java`**:

~~~java
class QualifiedStatic {
    static int early = QualifiedStatic.later;
    static int later = 11;
}

class QualifiedInstance {
    int early = this.later;
    int later = 22;
}

public class QualifiedForwardReferenceDemo {
    public static void main(String[] args) {
        System.out.println("static early=" + QualifiedStatic.early);
        System.out.println("static later=" + QualifiedStatic.later);

        QualifiedInstance item = new QualifiedInstance();
        System.out.println("instance early=" + item.early);
        System.out.println("instance later=" + item.later);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 QualifiedForwardReferenceDemo.java
java QualifiedForwardReferenceDemo
~~~

**Stdout:**

~~~text
static early=0
static later=11
instance early=0
instance later=22
~~~

### What Is Worth Remembering?

- Before the static field initializers of `QualifiedStatic`, static fields not yet explicitly assigned default to 0.
- `QualifiedStatic.early = QualifiedStatic.later` reads `later` while it is still 0 and stores that value in `early`.
- When `later = 11` runs, Java **does not automatically recompute** `early`. It remains 0.
- For the `QualifiedInstance` object, `this.later` also reads the default 0 during the turn of `early`'s initializer; only afterward does `later` receive 22.

This example is meant to **explain the mechanism**, not as a recommended pattern. In real systems, reverse the declaration order or compute the value at a point where all prerequisites are satisfied to avoid unintended reliance on default values.

## 12. With a Superclass: The Subclass Object Already Has Default Fields Before the Superclass Constructor

A more surprising mechanism: a subclass object is allocated with the instance fields of **both the superclass and the subclass** already set to default values. During initialization, the superclass constructor runs **before** the subclass's instance field initializers.

If the superclass constructor calls an **overridable** method, Java uses dynamic dispatch to invoke the overridden version in the subclass. Yet the subclass's fields may **still be at their default values**.

Create the file **`ConstructorDispatchDefaultDemo.java`**:

~~~java
class BaseStage {
    BaseStage() {
        System.out.println("base constructor");
        describe();
    }

    void describe() {
        System.out.println("base describe");
    }
}

class DerivedStage extends BaseStage {
    private int value = 10;
    private String label = "ready";
    private boolean finished = true;

    {
        System.out.println("derived initializer=" + value
                + "/" + label + "/" + finished);
    }

    DerivedStage() {
        System.out.println("derived constructor=" + value
                + "/" + label + "/" + finished);
    }

    @Override
    void describe() {
        System.out.println("override=" + value
                + "/" + label + "/" + finished);
    }
}

public class ConstructorDispatchDefaultDemo {
    public static void main(String[] args) {
        new DerivedStage();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ConstructorDispatchDefaultDemo.java
java ConstructorDispatchDefaultDemo
~~~

**Stdout:**

~~~text
base constructor
override=0/null/false
derived initializer=10/ready/true
derived constructor=10/ready/true
~~~

At the moment `BaseStage()` calls `describe()`, Java dispatches to `DerivedStage.describe()` because the actual object is of type `DerivedStage`. However, the subclass's initializers `value = 10`, `label = "ready"`, and `finished = true` **have not run yet**, so the method observes `0/null/false`.

After the superclass constructor completes, the subclass's initializers and initializer block run, and then the subclass constructor body prints the assigned values.

**Important design rule:** avoid calling **overridable** instance methods from a constructor, especially when a subclass has fields that depend on initializers. Also avoid letting `this` “escape” to callbacks or other threads before object initialization finishes.

## 13. Constructor Chaining Does Not Re-Run Defaults or Initializers for the Same Object

In a class with multiple constructors:

~~~java
class ChainSketch {
    int value = initialize();

    {
        System.out.println("instance block");
    }

    ChainSketch() {
        this("default");
        System.out.println("no-arg body");
    }

    ChainSketch(String name) {
        System.out.println("named body=" + name);
    }

    private int initialize() {
        System.out.println("field initializer");
        return 8;
    }
}
~~~

This is a valid illustrative class. The no-arg constructor calls `this("default")` to the one-argument constructor. The class's initializers run **only once per object** under the constructor chaining mechanism, rather than running separately once for each constructor body in the chain.

Create the file **`ConstructorChainOrderDemo.java`** with the full code:

~~~java
class ChainSample {
    int number = announce();

    {
        System.out.println("instance block");
    }

    ChainSample() {
        this("default");
        System.out.println("no-arg constructor");
    }

    ChainSample(String name) {
        System.out.println("named constructor=" + name
                + ", number=" + number);
    }

    private int announce() {
        System.out.println("field initializer");
        return 8;
    }
}

public class ConstructorChainOrderDemo {
    public static void main(String[] args) {
        new ChainSample();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorChainOrderDemo.java
java ConstructorChainOrderDemo
~~~

**Stdout:**

~~~text
field initializer
instance block
named constructor=default, number=8
no-arg constructor
~~~

Initially, the object is allocated and the field `number` has the default value 0, though **no code reads it at that stage**. After the relevant superclass constructor steps, the initializer sets `number=8` once; the constructor taking `name` runs, and finally the no-arg body runs.

**Do not infer that** each `this(...)` call allocates another object. It merely delegates initialization of **the same object** through another constructor in the class.

## 14. Distinguishing Class Initialization from Object Initialization

There are two separate timing systems:

| Characteristic | `static` field | Instance field |
| --- | --- | --- |
| Belongs to | Appropriate runtime class/interface | Each object |
| When defaults are set | Linking/preparation for the class or interface | During object allocation |
| When explicit field initializer executes | Class/interface initialization | Within each object's initialization sequence |
| Frequency after success | Once per initialized runtime class | Each new object |
| Is `this` available in initializer? | No | Yes, when in a valid instance context |
| Early value observation | Depends on static initialization order | Depends on object/superclass initialization order |

When writing:

~~~java
new Example();
new Example();
~~~

in a program with the corresponding `Example` definition, class initialization may occur before the first instantiation. Afterward, **both objects** still go through their instance default assignment, instance initializers, and constructors in turn.

**Loading and linking** are not two constructor calls. Class initialization also does not create an instance of the class just because it has a static block. An instance constructor is not automatically invoked by a static field initializer unless the initializer expression actually uses `new`.

## 15. Constant Variables: A Special Exception for `static final`

A field such as:

~~~java
static final int CAPACITY = 32;
static final String LABEL = "ready";
~~~

is a **constant variable** when it satisfies the type rule (`String` or primitive), is `final`, and has an initializer that is a **constant expression**. Java handles these fields differently from non-constant static fields:

- The JLS describes them as being assigned their constant values **before** ordinary static field initializers/static blocks are processed during class initialization.
- Bytecode uses the appropriate `ConstantValue` mechanism when applicable.
- A usage site may receive the value **inlined at compile time**; merely reading a constant variable from a client **does not require the declaring class to be initialized**.

Conversely:

~~~java
static final int COMPUTED = Integer.parseInt("32");
static final Integer WRAPPED = 32;
~~~

are not *constant variables* by the same definition: `COMPUTED` calls a method, while `WRAPPED` has reference type `Integer`, not `String`.

Do not conclude that “every static field defaults to 0 and a static block sees 0” for a **constant variable** field. The JLS guarantees separate handling for constant values; referencing a constant variable by simple name will not observe a default value before assignment.

## 16. Runnable Example: Constant vs. Non-Constant Fields

Create the file **`ConstantVersusRuntimeDemo.java`**:

~~~java
class StaticConstants {
    static final int CAPACITY = 32;
    static final String LABEL = "ready";
    static final int COMPUTED = calculate();

    static {
        System.out.println("StaticConstants block");
    }

    private static int calculate() {
        System.out.println("calculating");
        return 33;
    }
}

public class ConstantVersusRuntimeDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("capacity=" + StaticConstants.CAPACITY);
        System.out.println("label=" + StaticConstants.LABEL);
        System.out.println("computed=" + StaticConstants.COMPUTED);
        System.out.println("again=" + StaticConstants.COMPUTED);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ConstantVersusRuntimeDemo.java
java ConstantVersusRuntimeDemo
~~~

**Stdout:**

~~~text
begin
capacity=32
label=ready
calculating
StaticConstants block
computed=33
again=33
~~~

Reading `CAPACITY` and `LABEL` from the client does not trigger `calculate()` or the static block because they are constant variables. Only the first read of `COMPUTED` requires `StaticConstants` to be initialized, running the initializer that calls the method and then the static block.

**Limitation:** this conclusion relies on the **conditions for a constant variable**, not simply because of the word `final`. In complex cases, check whether the initializer expression is a constant expression according to the JLS.

## 17. `final` Fields Also Have Default Values at Allocation, but the Compiler Requires Assignment

Consider a **blank final instance field**:

~~~java
final class OrderId {
    private final String value;

    OrderId(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value không hợp lệ");
        }
        this.value = value;
    }

    String value() {
        return value;
    }
}
~~~

This is a valid illustrative class. At object allocation, the reference field has the default value `null` before the constructor runs. However, the compiler enforces **definite assignment**: on every constructor path that completes normally, a blank final instance field must have been properly assigned. You cannot omit `this.value = value;` and rely on the default `null`.

Similarly, a blank `static final` field must be properly assigned during the appropriate static initialization; it cannot simply “default to 0” and be considered to have fulfilled the `final` requirement.

**Distinction:**

- Default values are part of **storage initialization**.
- `final` and definite assignment are **compile-time constraints** on the permission and certainty of assignment.
- Business invariants such as a non-blank ID are **application rules** enforced by the constructor.

Do not rely on default values to intentionally leave a `final` field unassigned after object creation succeeds.

## 18. Why Seeing `null` in a Constructor Can Be Dangerous

A reference field `private Service service = createService();` has the default value `null` before `createService()` runs. If a callback or method is called too early during object initialization and attempts to use `service`, it can encounter a `NullPointerException`.

A particular risk example is a **superclass constructor calling an overridden method**, as in `ConstructorDispatchDefaultDemo`; the subclass's overridden method can observe the `null` field and attempt to call a method on that reference.

Safe strategies:

1. Avoid calling overridable methods from a constructor.
2. Do not register `this` anywhere that might call back into it before initialization is complete.
3. Compute required dependencies using local variables before storing them in fields.
4. Validate constructor parameters and necessary invariants.
5. Prefer `final` fields for stable references when design permits, though do not treat `final` as a cure-all.
6. Do not blindly add `if (service == null)` everywhere to mask a broken initialization order; fix the initialization architecture if the root cause is early exposure.

Java's guarantee that a field defaults to `null` **prevents uninitialized garbage data**, yet `null` itself can still be an unusable state from a business-logic perspective.

## 19. What Happens If an Error Occurs Before an Initializer Completes?

Default values do not guarantee that **every initializer completes successfully**.

For instance:

~~~java
class UnsafeInstance {
    int value = calculate();

    private int calculate() {
        throw new IllegalArgumentException("bad instance");
    }
}
~~~

If `new UnsafeInstance()` causes an initializer to throw an exception, the instantiation call does not return a completed instance to the caller. The class does not necessarily become unusable; the caller can try creating another object according to application policy if the underlying cause can change.

For static:

~~~java
class UnsafeStatic {
    static int value = calculate();

    private static int calculate() {
        throw new IllegalStateException("bad static");
    }
}
~~~

If an unhandled failure occurs during class initialization, the JVM has a mechanism to mark the class as having failed initialization. Subsequent uses of the class under the same runtime definition may fail rather than automatically re-running the static initializer from the beginning.

**Do not infer from “fields default to 0” that any use of a class after a failed static initializer returns 0.** Class initialization has a special failure mechanism; normal callers will see `ExceptionInInitializerError` or a corresponding error, and are not allowed to silently ignore the broken initialization and read an uninitialized field.

## 20. Static Forward Dependence and Cyclic References

A design to avoid is **cyclically dependent initializers**:

~~~java
class CyclicSketch {
    static int left = calculateLeft();
    static int right = calculateRight();

    private static int calculateLeft() {
        return right + 1;
    }

    private static int calculateRight() {
        return left + 1;
    }
}
~~~

This is a valid illustrative class. When the class is initialized:

1. `left` and `right` initially default to 0.
2. `left = calculateLeft()` sees `right=0`, so `left=1`.
3. `right = calculateRight()` sees `left=1`, so `right=2`.

The result is `left=1` and `right=2`, yet a reader can easily mistakenly think the two calculations form a system of equations solved simultaneously. Java **does not perform simultaneous mathematical solving** for field initializers; it executes a programmatic **assignment sequence**.

If the data truly has a bidirectional relationship:

- Choose a single root data source and derive the values from it.
- Move dependent conditions into a configuration-building step with validation.
- Avoid calling static methods from an initializer if those methods might inadvertently read state currently being initialized.
- Be careful when a static initializer creates an instance or triggers initialization of another class that also references back to it.

A similar situation can occur with instance field initializers; instead of letting them read each other in an arbitrary order, design dependencies in one clear direction.

## 21. Early `this` Escape and Multithreading

When a constructor hands `this` over to other code too early—such as registering a listener, running a callback, or letting another thread hold a reference—the object can be observed **before all instance initializer and constructor logic completes**. This does not violate the default-value rule, but it often violates the **invariants** expected by the class author.

In multithreaded programs, there is also the **memory visibility** aspect. The Java Memory Model specifies special guarantees for properly initializing `final` fields, but that does not mean a prematurely published reference is automatically safe.

Recommended organization:

~~~text
1. Validate required data.
2. Create the object and complete all initializers/constructors.
3. Do not allow callbacks or other threads to observe an incomplete "this".
4. Publish the reference through an appropriate mechanism.
5. If a mutable object is shared, use synchronization/atomic/ownership.
~~~

For static initialization, the JVM coordinates class initialization according to special rules. However, **mutable static fields can still suffer from data races after initialization**, for example a `static int counter` modified with `counter++` from multiple threads.

Remember that having default values on fields does not mean **multithreaded synchronization is solved**, since those requirements operate at a different level.

## 22. Common Misconceptions

| Misconception | Why it is incorrect | Correct understanding |
| --- | --- | --- |
| “Java only assigns a field when it reaches the initializer.” | The field already had a default value before that | The initializer can **replace** the default value |
| “A `String` field is automatically `""`.” | References default to `null` | You must assign an empty string if needed |
| “An `int[]` field is automatically an empty array.” | Reference fields default to `null` | `new int[0]` is a separate array creation |
| “A local `int x;` can automatically be read as 0.” | Locals must be definitely assigned | Assign before reading |
| “`static int x = f()` runs immediately during linking.” | Preparation does not run source initializers | `f()` runs during class initialization |
| “Every read of a static field returns the default first.” | Active use can trigger initialization | Clients usually see the post-init value |
| “A field declared later can always be read by simple name.” | Illegal forward reference | Follow JLS §8.3.3 |
| “Every forward read is an error.” | Method calls/qualified references have valid cases | However, they may read an unintended default |
| “`new T[5]` creates five `T` objects.” | Only creates a reference array | Slots default to `null` |
| “`static final` always just starts from 0.” | Constant variables receive special handling | Check constant expressions and the JLS |
| “The superclass constructor sees initialized subclass fields.” | Subclass initializers run later | Virtual dispatch may read defaults |
| “Each constructor in a `this(...)` chain re-runs initializers.” | An object passes through its initializers only once | Chaining does not allocate a new object |
| “`final` can be left at its default without assignment.” | Blank finals are subject to definite assignment | Must be properly assigned on normal completion paths |
| “Once an object has defaults, an NPE is impossible.” | The default for references is null | Must be initialized before use |
| “If static init fails, reading the field still yields the default value.” | The runtime has an initialization failure mechanism | Do not rely on failed initialization state |
| “Default initialization makes it thread-safe.” | Defaults do not imply atomicity/visibility | Design concurrency separately |

**Diagnostic question:** at the exact point in time being examined, has the field just received its **default value**, already been **assigned by an explicit initializer**, or is it still being read through a method running **too early**?

## 23. Step-by-Step Procedure for Solving Field Initialization Order Output Exercises

If a problem asks “what does the program print?”, do not try to guess from the order of `println` lines in isolation. Follow this procedure:

1. **Separate fields into static and instance**, noting clearly which class declares them.
2. For static fields, identify the **first active use** that requires class initialization; examine compile-time constant fields separately.
3. Before static initializers, mark ordinary static fields at their default values from preparation.
4. Execute **static field initializers and static blocks in source order** when the class is initialized, recording every time a method reads a later-declared field.
5. If creating an instance, model allocating **all instance fields at their default values** for the new object.
6. Follow the superclass then subclass constructor chain; check whether there is any **virtual dispatch** from the superclass constructor.
7. Execute each class's instance field initializers and initializer blocks in their corresponding order, and then run the constructor body.
8. If a constructor calls `this(...)`, **do not duplicate initializers** within the same object.
9. On each field assignment, update the value table; **do not automatically recompute** fields assigned earlier.
10. If you spot a direct simple-name forward reference or a missing assignment to a blank final field, identify a **compile error** instead of trying to compute stdout.
11. If an exception occurs in an initializer, analyze the **failure path** before continuing with any remaining steps.

Brief trace table for `StaticFieldOrderDemo`:

| Point in time | `first` | `second` |
| --- | ---: | ---: |
| After preparation | 0 | 0 |
| `calculateFirst()` reading `second` | Not yet assigned the result | 0 |
| After `first = calculateFirst()` | 5 | 0 |
| After `second = 42` | 5 | 42 |
| After static block | 5 | 42 |

Building a timeline table usually explains the output better than imagining Java “going back” to assign fields simultaneously.

## 24. Practice Exercises

**Question 1 — Default primitives.** A class has `int count;`, `boolean ready;`, and `char mark;`. After a valid `new` with no initializers, what values do the three fields hold?

**Question 2 — Default references.** Will `String title;` and `int[] scores;` be an empty string and an empty array, or `null`?

**Question 3 — Local variables.** Why is `int x; System.out.println(x);` invalid inside a method, whereas `class A { int x; }` allows reading `new A().x`?

**Question 4 — Instance order.** Given `int a = readB(); int b = 7;` where `readB()` returns `b+5`, what are the values of `a` and `b` after the constructor if there are no other assignments?

**Question 5 — Static order.** Given `static int first = readSecond(); static int second = 42;`, if `readSecond()` returns `second`, what is the value of `first` after class initialization?

**Question 6 — Forward references.** Why might `static int a = b; static int b=1;` fail to compile? Is `static int a = Name.b; static int b=1;` (inside class `Name`) the same?

**Question 7 — Arrays.** How many `Student` objects does `new Student[3]` create? What values do the three array elements hold?

**Question 8 — Superclass.** A superclass constructor calls an overridden method of the subclass, and that method reads the subclass field `String name = "An";`. What can that field be at that moment? How can this be prevented?

**Question 9 — Constructor chaining.** A no-arg constructor calls `this("x")`. How many times do the field initializers of that same class run for that object?

**Question 10 — Constant variables.** How do `static final int A=20;` and `static final int B=Integer.parseInt("20");` differ in whether reading them can trigger initialization?

**Question 11 — Blank finals.** Can you declare `final String code;` in a class and skip assigning it in every constructor because a reference field already defaults to null?

**Question 12 — Static failure.** A static initializer throws an unhandled exception. Is a subsequent read guaranteed to see the default 0?

**Question 13 — Field dependency.** If two static fields depend on each other through helper methods and read values before initializers run, does Java automatically solve a system of equations to produce the final values?

**Question 14 — Concurrency.** Do default values and JVM static initialization automatically make `counter++` on a static field safe across two threads?

### Answers and Solutions

1. `0`, `false`, character with code `U+0000`.
2. Both are `null` because they are reference fields; neither a `String` nor an array object has been created.
3. A local variable must be definitely assigned before being read; fields have default values due to object initialization semantics.
4. `a=5`, `b=7`: when `readB()` runs, `b` is still 0; assigning `b=7` afterward does not recompute `a`.
5. `first=0`, because `second` defaults to 0 when the helper is called; afterward `second` is assigned 42.
6. Direct simple-name forward references are subject to the JLS prohibition; a qualified name can be valid and in the example reads the default 0, though you should not rely on this trick.
7. No `Student` objects are created by the array alone; the three reference slots default to null.
8. It can be `null` because the subclass initializer has not run yet; do not call overridable methods from a superclass constructor.
9. Once for that object; constructor chaining does not create a new object and does not re-run all initializers at each `this` level.
10. `A` is a constant variable, so reading it alone does not require the class to be initialized; `B` is not a constant expression, so reading `B` will require initialization of the declaring class.
11. No. A blank final field must be properly assigned before every constructor finishes normally.
12. No. Failed class initialization has its own failure mechanism; there is no guarantee of returning a default value.
13. No. Java executes field initializers sequentially, using the state available at the time of reading; already-assigned values are not automatically recomputed.
14. No. Initialization guarantees and thread safety for subsequent mutable updates are two separate concerns.

## 25. Java 17 References

- [JLS §4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): default values of fields and array elements.
- [JLS §8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): instance/static field initializers and execution timing.
- [JLS §8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): illegal forward references and simple-name restrictions.
- [JLS §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance initializer blocks.
- [JLS §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static initializer blocks.
- [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use, constant fields, and static initialization order.
- [JLS §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object allocation, default values of instance fields, and constructor/initializer order.
- [JLS §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): differences regarding reading local variables and blank final fields.
- [JVMS §5.4.2 — Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): static fields are allocated and assigned defaults during linking.
- [JVMS §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): class initialization and the mechanism for assigning constant values.
- [JVMS §4.7.2 — ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2): representation of constants assigned before ordinary class initialization code.

**Conclusion:** Before explicit field initializers run, Java has already set **default values** for instance fields during object allocation and for static fields during class preparation. Initializers then **overwrite them in order**; reads that occur too early through methods, qualified forward references, or dynamic dispatch may observe 0/false/null. This rule **does not apply in the same way to local variables**, does not allow skipping definite assignment for blank `final` fields, and does not replace validation or concurrency safety. Good design makes dependencies explicit, initializes them in the proper order, and does not publish an object before it is complete.
