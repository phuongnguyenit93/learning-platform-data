# Predicting Results Using Class-Load Traces and Static Initializer Execution Order

## 1. Goal: Looking at Java code and accurately predicting which line appears first

When reading a program with multiple classes, inheritance, interfaces, static fields, and static blocks, the log output order is often guessed wrong because the reader conflates three different things:

1. **Loading:** The JVM obtains the runtime representation of a class/interface from an appropriate source of class bytes.
2. **Linking:** The class undergoes *verification*, *preparation*, and resolution of symbolic references according to VM rules.
3. **Initialization:** The JVM executes the static field initializers and static blocks belonging to the class/interface requested for initialization (usually via the special method `<clinit>`).

A **class-load trace** and a **trace printed from a static initializer** measure different events. A log line reporting that a class has been loaded **does not mean** its static block has run. Conversely, when a static initializer has executed successfully, that class must have been loaded and verified/prepared beforehand, but class loading could have taken place long before the print point.

The goal of this lesson is to build a **repeatable result-prediction process**, without relying on the subjective loading order of a specific HotSpot version.

### A thought example

~~~text
In the JAR there are: Main.class, Parent.class, Child.class, Helper.class.

class+load log:
  Parent loaded
  Child loaded

Stdout from Java:
  PARENT_INIT
  CHILD_INIT

From the two "loaded" lines, one cannot deduce that:
- each class is initialized immediately upon being loaded;
- the JVM has loaded every class in the JAR;
- Helper has definitely not been loaded;
- Parent and Child print immediately one after the other, with no other runtime events.
~~~

**Golden rule when doing stdout prediction exercises:** only list lines produced by **Java code requested to execute** according to the ordering relationships guaranteed by Java/JVM. If VM logging is enabled, keep a separate analysis column/line for runtime logs; do not mix configuration-dependent JVM logs with the program's deterministic stdout.

## 2. The class initialization model to know by heart

Class initialization has two questions:

- **Who triggers it?** Actions considered *active use* according to JLS/JVMS.
- **Who must run first?** The superclass, certain superinterfaces, and then the static initialization logic of the requested class.

Overview diagram for **the first active use of a class C**:

~~~text
Code performs active use of C
         |
         v
Has C already been initialized successfully?
  +------+- Yes ----> use immediately, do not run <clinit> again
  |
  No
  |
  v
Ensure appropriate loading, verification, preparation
         |
         v
Coordinate initialization across threads
         |
         v
Initialize superclass and superinterfaces that have
default methods in the order specified by the specification
         |
         v
Execute static field initializers / static blocks
of C itself in textual order
         |
         v
Mark as initialized successfully, continue active use
~~~

**This is a semantic model**; it does not promise that all substeps of linking only occur after active use begins: the JVM may load/resolve eagerly within the bounds of the specification. If the class is currently being initialized by **the current thread itself** and is encountered again along a circular initialization path, the VM has its own handling rules; the default values section in section 9 is a point that easily causes surprises.

## 3. When is a class/interface initialized?

Typical scenarios with Java 17:

| Source or runtime action | Triggers initialization of the specified type? | Note |
| --- | --- | --- |
| `new Widget()` | **Yes** for `Widget` when not yet initialized | Initialization completes according to rules before the constructor body executes |
| `Widget.staticMethod()` | **Yes** for the class/interface that actually declares the static method | A static method does not need an instance |
| Reading `Widget.nonConstantStatic` | **Yes** for the class/interface that actually declares the field | The type name in syntax is not necessarily where the **field is declared** |
| Assigning `Widget.staticField = value` | **Yes** according to active-use rules | Before the first write, the appropriate class state is required |
| `Widget.class` | **Not solely because of the class literal** | May need to load/resolve the type, but initialization is not required |
| `Class.forName(name)` | **Yes** via the single-parameter overload when the class is found | Requires initialization |
| `Class.forName(name, false, loader)` | **Does not require initialization** | May load/link the class; `false` does not forbid loading |
| `loader.loadClass(name)` | Typically **does not** require initialization on its own | A custom loader may have its own side effects |
| `new Widget[3]` | **Does not** initialize the component class just by creating an array | Creates an **array**, not three `Widget` instances |
| Reading `static final int X = 7` which is a compile-time constant variable | **Not solely because of this read** | The compiler can inline the literal into the caller |
| Reading `static final Integer X = 7` | **Yes** (not a primitive/String constant variable per JLS) | `Integer` is a reference; not a compile-time constant expression of an allowed type |
| Running the initial `main` class | **Yes** for the startup class | JDK classes needed for startup have also been / are being initialized |

**Note:** **loading or linking** a class may eagerly happen earlier in an implementation; the table above only classifies **whether initialization is required** by the action under consideration. If a class has already been initialized by a previous operation, a new use **does not print the static block again**.

### 3.1. Distinguishing a compile-time constant from a regular final value

~~~java
class Config {
    static {
        System.out.println("CONFIG_INIT");
    }

    static final int LIMIT = 7;
    static final String NAME = "JAVA";
    static final Integer BOXED = Integer.valueOf(7);
    static final int COMPUTED = Integer.parseInt("7");
}
~~~

- `Config.LIMIT` and `Config.NAME` can be inlined into the caller as compile-time constants, so reading them **does not** by itself initialize Config.
- `Config.BOXED` and `Config.COMPUTED` are not *constant variables* by JLS definition even though declared `static final`. Reading them requires accessing the static field at runtime, so it can trigger Config initialization if it has not happened yet.
- **Final does not mean constant variable.** The key conditions are primitive or String type, `final`, and the initializer being a valid **constant expression**.
- If a caller has already been compiled with `LIMIT = 7`, replacing the Config binary with `LIMIT = 9` without rebuilding the caller may cause the caller to still use the old literal due to constant inlining.

The Config example above is only an illustrative snippet without `main`; see the full program in section 7 for exact printed output.

## 4. Predicting the order of static fields and static blocks in a class

**Static variable initializers** and **static initializer blocks** are executed in textual order at the declaration level when the class is initialized. The JVM performs preparation first, causing some static fields to start at their **default values** (for example, `int` is 0; reference is null), and then initialization logic assigns values according to source semantics.

~~~java
class Order {
    static int first = print("FIRST_FIELD", 10);

    static {
        System.out.println("FIRST_BLOCK");
    }

    static int second = print("SECOND_FIELD", first + 1);

    static {
        System.out.println("SECOND_BLOCK");
    }

    static int print(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }
}
~~~

This is an illustrative snippet **without main**. The first time `Order` is actually initialized, the order of lines produced by Order's code is:

~~~text
FIRST_FIELD=10
FIRST_BLOCK
SECOND_FIELD=11
SECOND_BLOCK
~~~

Not every static initializer has a println, so a class can be initialized without any line appearing on stdout. When predicting, do not use “nothing printed” as proof that it has not been initialized.

### Static initialization differs from a constructor

- Static field initializers and static blocks run according to the **class** lifecycle.
- **Constructors** and instance field initializers run when an **object** is created; they can run multiple times for multiple instances.
- When creating an object of a subclass, the superclass must be initialized according to the rules before the subclass, but the **superclass constructor** is a different phase that happens when instance construction is executed.
- If the class has already been initialized beforehand, creating a second instance **does not run `<clinit>` again**; the relevant constructors still execute for the new instance.

How to predict: write two separate tables, one for **class initialization** and one for **object construction**. Then merge them according to the active-use points.

## 5. Inheritance: superclass is initialized before subclass

Given:

~~~java
class Parent {
    static { System.out.println("PARENT_INIT"); }
    Parent() { System.out.println("PARENT_CTOR"); }
}
class Child extends Parent {
    static { System.out.println("CHILD_INIT"); }
    Child() { System.out.println("CHILD_CTOR"); }
}
~~~

When the code executes `new Child()` for the first time, the semantic sequence produced by the program will be:

~~~text
PARENT_INIT
CHILD_INIT
PARENT_CTOR
CHILD_CTOR
~~~

Explanation:

1. Initialize **class** Parent before Child.
2. Initialize **class** Child after Parent.
3. Begin **instance initialization/constructor** for Child, first the parts of the superclass object/constructor Parent according to the rules.
4. After the Parent constructor, the Child constructor completes.

**Do not equate** `PARENT_INIT` with `PARENT_CTOR`. One is a static initializer with a class lifecycle; the other is a constructor with an instance lifecycle. If you create Child a second time after both classes have been initialized, the second time normally only prints:

~~~text
PARENT_CTOR
CHILD_CTOR
~~~

The two snippets above are models based on illustrative source; the program in section 6 has complete runnable code and verified output.

### A field declared in the superclass even when written via Subclass

~~~java
class Base {
    static int value = trace("BASE", 123);
}
class Sub extends Base {
    static { System.out.println("SUB"); }
}
~~~

This snippet illustrates the idea. If a Java expression uses `Sub.value`, **the field is actually declared in Base**, so the active-use rule triggers **Base** initialization, not necessarily initializing Sub. The compiler may emit `getstatic` referencing the field resolved to Base. To ensure Sub is initialized, an actual active use of Sub is needed, such as `new Sub()` or calling a static method declared by Sub.

This explains multiple-choice questions where the name `Sub` clearly appears in the source, yet stdout does not contain `"SUB"`.

## 6. Java 17 lab: a single run with superclass, interfaces, constants, and constructors

Create the file **`InitOrderDemo.java`** with the following full code:

~~~java
public final class InitOrderDemo {
    static int mark(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Parent {
        static int number = mark("PARENT_FIELD", 10);
        static { System.out.println("PARENT_BLOCK"); }

        Parent() {
            System.out.println("PARENT_CONSTRUCTOR");
        }
    }

    interface WithDefault {
        int TOKEN = InitOrderDemo.mark("DEFAULT_INTERFACE_FIELD", 11);
        default void unused() { }
    }

    interface Plain {
        int TOKEN = InitOrderDemo.mark("PLAIN_INTERFACE_FIELD", 22);
    }

    static class Child extends Parent implements WithDefault, Plain {
        static int number = mark("CHILD_FIELD", 20);
        static { System.out.println("CHILD_BLOCK"); }

        Child() {
            System.out.println("CHILD_CONSTRUCTOR");
        }

        static void ping() {
            System.out.println("CHILD_STATIC_METHOD");
        }
    }

    static class Constants {
        static { System.out.println("CONSTANTS_BLOCK"); }

        static final int MAGIC = 7;
        static final int NON_CONSTANT =
                mark("CONSTANTS_COMPUTED", 8);
    }

    public static void main(String[] args) {
        System.out.println("START");

        System.out.println("CLASS=" + Child.class.getSimpleName());
        System.out.println("CONST=" + Constants.MAGIC);
        System.out.println("BEFORE_NEW");

        Child child = new Child();

        System.out.println("AFTER_NEW");
        System.out.println("PLAIN=" + Plain.TOKEN);
        Child.ping();
        System.out.println("NON_CONST=" + Constants.NON_CONSTANT);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac --release 17 InitOrderDemo.java
java InitOrderDemo
~~~

### Verified stdout output

~~~text
START
CLASS=Child
CONST=7
BEFORE_NEW
PARENT_FIELD
PARENT_BLOCK
DEFAULT_INTERFACE_FIELD
CHILD_FIELD
CHILD_BLOCK
PARENT_CONSTRUCTOR
CHILD_CONSTRUCTOR
AFTER_NEW
PLAIN_INTERFACE_FIELD
PLAIN=22
CHILD_STATIC_METHOD
CONSTANTS_BLOCK
CONSTANTS_COMPUTED
NON_CONST=8
~~~

The lines above are **predicted output for Java 17**; compile with `javac --release 17` and run with JDK 17 to verify the order yourself. There is no need to guess the JVM's class-load positions to obtain this stdout output.

### 6.1. Explaining each milestone like a trace exam

**Milestone 1 — `START`:** `main` has started. Class `InitOrderDemo` needs to be initialized to run `main`, but the program does not define any static initializer in the outer class, so no extra trace is printed here.

**Milestone 2 — `Child.class.getSimpleName()`:** the class literal creates/obtains a `Class<?>` object for Child and `getSimpleName()` returns `"Child"`. This operation **does not require Child initialization**, so there is no `CHILD_FIELD` or `CHILD_BLOCK` yet. It may be accompanied by class loading/linking, but that does not show up via static initializers.

**Milestone 3 — `Constants.MAGIC`:** field `MAGIC` is a compile-time constant of type `int`, so the caller prints `7` without triggering Constants `<clinit>`. After `CONST=7`, there is still **no `CONSTANTS_BLOCK`**.

**Milestone 4 — `new Child()`:** this is the first active use requiring Child to be initialized. The JVM initializes superclass Parent first; hence `PARENT_FIELD` then `PARENT_BLOCK`. Next, **the direct superinterface `WithDefault` declares a default method** and belongs to the set needing initialization during Child's class initialization procedure, so `DEFAULT_INTERFACE_FIELD` prints before Child's static lines.

**Milestone 5 — interface Plain:** Plain does not declare a default method, so it is **not initialized merely because Child implements Plain** in this scenario. `PLAIN_INTERFACE_FIELD` has not printed at the time of Child initialization. This differs from the assumption “initializing a class must initialize all of its interfaces”.

**Milestone 6 — Child itself:** Child's two static declarations in source order print `CHILD_FIELD`, `CHILD_BLOCK`.

**Milestone 7 — instance creation:** after class initialization is complete, object construction runs the Parent constructor then Child constructor; printing `PARENT_CONSTRUCTOR`, `CHILD_CONSTRUCTOR`.

**Milestone 8 — reading `Plain.TOKEN`:** `TOKEN` is an `int` but is produced by a **method invocation**, so it is not a compile-time constant variable. `getstatic` for the field declared in Plain requires Plain initialization; `PLAIN_INTERFACE_FIELD` prints before `println` prints `PLAIN=22`.

**Milestone 9 — `Child.ping()`:** Child was already initialized from `new Child`, so `CHILD_BLOCK` does not run again; only `CHILD_STATIC_METHOD` is printed.

**Milestone 10 — `Constants.NON_CONSTANT`:** this is the actual active use of Constants, so `CONSTANTS_BLOCK` prints, then the field initializer's `mark` call prints `CONSTANTS_COMPUTED`; finally `println` prints `NON_CONST=8`.

### Variation questions

- If we swap the two declarations `static int number` and `static { ... }` in Parent, do the two Parent lines swap? **Yes**, following textual order.
- If we remove `default void unused() {}` from WithDefault, is `DEFAULT_INTERFACE_FIELD` still **guaranteed** to print upon `new Child()`? **No**, because a superinterface without default methods is normally not required to be initialized along with a subclass by the rules.
- If we add another `new Child()`, which static initializer is guaranteed to run again? **None**, provided all prior initializations succeeded; the Parent and Child constructors still run for the new object.
- If we replace `Plain.TOKEN` with `Plain.class`, is `PLAIN_INTERFACE_FIELD` guaranteed to run? **No**.
- If `Constants.MAGIC` is changed from an `int` literal to `Integer.valueOf(7)`, is it still a compile-time constant variable? **No**.

## 7. Second Java 17 lab: loaded/linked but not yet initialized

Create the file **`TriggerMatrixDemo.java`**:

~~~java
public final class TriggerMatrixDemo {
    static class Target {
        static { System.out.println("TARGET_INIT"); }

        static final int MAGIC = 40;
        static final Integer BOXED = Integer.valueOf(40);

        static void ping() {
            System.out.println("PING");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("BEGIN");
        System.out.println("CONST=" + Target.MAGIC);

        Class<?> token = Target.class;
        System.out.println("LITERAL=" + token.getSimpleName());

        Class.forName(token.getName(), false,
                TriggerMatrixDemo.class.getClassLoader());
        System.out.println("LOADED_NO_INIT");

        System.out.println("BOXED=" + Target.BOXED);
        Target.ping();
        System.out.println("FINISH");
    }
}
~~~

Run:

~~~bash
javac --release 17 TriggerMatrixDemo.java
java TriggerMatrixDemo
~~~

**Predicted stdout for Java 17 (run it yourself to verify):**

~~~text
BEGIN
CONST=40
LITERAL=Target
LOADED_NO_INIT
TARGET_INIT
BOXED=40
PING
FINISH
~~~

### Why does this order matter?

1. `CONST=40`: `static final int MAGIC = 40` is a constant variable; reading it is not an active use requiring Target initialization.
2. `Target.class` and `getSimpleName()`: may make the JVM aware of the class, but does not require running `<clinit>`.
3. `Class.forName(name, false, loader)`: **may load/link** Target, but the `false` argument **does not require initialization**, so `LOADED_NO_INIT` prints before `TARGET_INIT`.
4. `Target.BOXED`: is a static final `Integer` **reference**, not a constant variable; reading it triggers Target's initialization. The JVM runs the static block, prints `TARGET_INIT`, then evaluates the BOXED value so `println` prints `BOXED=40`.
5. `Target.ping()`: Target is already initialized, so there is no second `TARGET_INIT` line.

Change the variant `false` to `true` in the `Class.forName` call to test: `TARGET_INIT` will appear **before** `LOADED_NO_INIT`, while the subsequent read of BOXED will not re-initialize Target. This is a **variant**, not the stdout output of the original source.

**Distinction:** the single-parameter `Class.forName(name)` overload **requires initialization** by default. `ClassLoader.loadClass(name)` normally only loads and does not automatically initialize. With a custom class loader, the loader's code may have its own side effects, so custom logs should not be predicted without that loader's source.

## 8. Special case: interfaces with default methods vs. interfaces without

For interfaces, the initialization rules differ from what many people guess:

- **Initializing an interface** does not automatically initialize all of its superinterfaces solely because of an extends relationship.
- **Initializing a class** that has a superclass must initialize the superclass first. Under modern JLS/JVMS, certain **superinterfaces declaring default methods** also require initialization during that class's initialization process.
- A superinterface **without default methods** is not necessarily initialized at the time an implementing class is initialized; it may wait for its own active use, such as reading a static field that is not a constant variable.
- An “interface field” is `public static final` by language rules, but that **does not mean all fields are compile-time constants**. A field initialized by a method call is not a compile-time constant.

In the section 6 example, `WithDefault` contains `int TOKEN = mark(...)` and the default method `unused()`: Child initialization printing `DEFAULT_INTERFACE_FIELD` is important to remember. `Plain` has `TOKEN = mark(...)` but **declares no default method**; its initialization is deferred until `Plain.TOKEN` is read.

Do not infer from Java source merely containing the `interface` syntax that its initializer will print when its name is mentioned. **The trace depends on active-use rules and the initialization process of the related class**, not on how close the declarations are in the file.

### A compiler-level caveat

The compiler may generate **synthetic default methods** in certain cases. The JLS notes that default-method superinterface initialization may not be completely obvious from source code. When doing exercises requiring **exact specific bytecode** results, you need to know the compiler/version and the actual class file. For the hand-written Java 17 example in section 6, the `default void unused(){}` construct is explicit.

## 9. Third Java 17 lab: circular class initialization

What surprises many people is that **preparation** sets static fields to their default values before `<clinit>` code runs. If two classes initialize each other in turn on the same thread, a class currently undergoing initialization can be read while its field has not yet received its initializer value.

Create the file **`CircularInitDemo.java`**:

~~~java
public final class CircularInitDemo {
    static class A {
        static int value = B.value + 1;
        static { System.out.println("A_INIT=" + value); }
    }

    static class B {
        static int value = A.value + 1;
        static { System.out.println("B_INIT=" + value); }
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + A.value);
        System.out.println("AGAIN=" + B.value);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CircularInitDemo.java
java CircularInitDemo
~~~

**Verified stdout:**

~~~text
B_INIT=1
A_INIT=2
RESULT=2
AGAIN=1
~~~

Solution:

1. Main reads `A.value`. The JVM prepares A with `A.value` defaulting to **0**, and begins initializing A.
2. A's initializer needs `B.value`, so the JVM begins initializing B; B has also been prepared, so `B.value` defaults to **0**.
3. B's initializer reads `A.value` while A is currently being initialized by **this same thread**. The rules allow proceeding with the current state instead of running A's initializer a second time. `A.value` is still **0** at that moment.
4. B assigns `B.value = 0 + 1 = 1` and prints `B_INIT=1`; B initialization completes.
5. A resumes, assigns `A.value = 1 + 1 = 2`, and prints `A_INIT=2`; A initialization completes.
6. The caller prints `RESULT=2`; the subsequent read of B simply gets `B.value = 1` and prints `AGAIN=1`. No static initializer repeats.

**Do not overgeneralize:** circular initialization across **multiple threads** is more complex and can lead to class initialization deadlock when two threads wait on each other; this program only has one main thread accessing A first. Do not assume “every circular init always returns 0 and runs normally” or that every case has the same print order as the example.

### What if the first trigger is changed from A to B?

If `main` reads `B.value` first, the initialization cycle starts at B; with symmetric two-field logic, the values and print order can change. To predict, **trace the exact access path**; do not look at the order classes are declared in the source to decide which class initializes first.

## 10. How to read the JVM's class-load and class-init traces

In HotSpot/OpenJDK/JDK 17+, Unified Logging can record loading and initialization events separately:

~~~bash
java '-Xlog:class+load=info,class+init=info' InitOrderDemo
~~~

Or view only class load:

~~~bash
java -Xlog:class+load=info InitOrderDemo
~~~

Or class initialization:

~~~bash
java -Xlog:class+init=info InitOrderDemo
~~~

**Note:** hundreds of events related to JVM background libraries can appear, sometimes **before main starts**. The order/count and format of logs depend on the JVM, JDK build, class data sharing, collector, agents, classpath, and configuration. Therefore, **logging output must not be treated as the fixed stdout** of the example.

You can write VM logging to a file and keep program stdout easier to read:

~~~bash
java '-Xlog:class+load=info,class+init=info:file=class-trace.log:uptime,level,tags' InitOrderDemo
~~~

Clearly distinguish three types of information:

| Information | What does it tell you? | What does it NOT tell you? |
| --- | --- | --- |
| `[class,load]` event | The VM recorded a class being loaded, usually with name/source | Does not prove the static block has executed |
| `[class,init]` event | The VM started or performed type initialization per logging mechanism | Is not the initializer's `println` statement; the class might not have `<clinit>` |
| `PARENT_FIELD`/`CHILD_BLOCK` lines from Java | A statement in the static initializer ran up to the print location | Does not describe all classes that have been loaded |

**Important when filtering logs:** if you only search for the name `Child` in the class-load log file, you may see both `InitOrderDemo$Child` and JDK classes containing the word `Child`. Filter by the full name and log tags, checking loader/source when available. The `$` in a nested class's binary name is a literal character, not a shell variable or nested-scope indicator.

### How does `javap -c -p` help?

~~~bash
javap -c -p InitOrderDemo
javap -c -p 'InitOrderDemo$Child'
javap -c -v -p 'InitOrderDemo$Constants'
~~~

In Bash, single quotes preserve the `$` character in the nested class name. PowerShell can also use single quotes. `javap` is **static disassembly**, not a log of classes loaded in a running JVM.

Observe:

- The `<clinit>` method if the class has static initialization logic to execute.
- `getstatic`/`putstatic` in methods/initializers.
- `invokestatic` for static method calls.
- `new`, `dup`, `invokespecial <init>` when creating an instance.
- The `ConstantValue` attribute of a compile-time constant field.
- Constructor `<init>` methods are completely different from `<clinit>`.

**Use `javap` to cross-check why a Java line compiles to that behavior**, not to treat a constant-pool reference as automatic proof that a class has been initialized.

## 11. Standard procedure for solving output prediction problems

When encountering a 10–100 line code snippet with multiple classes, proceed **step by step through runtime events**:

### Step 1 — List the involved classes/interfaces and their print lines

Write a table:

| Runtime type | What do static fields/blocks print? | What does the constructor print? |
| --- | --- | --- |
| Parent | `PARENT_FIELD`, `PARENT_BLOCK` | `PARENT_CONSTRUCTOR` |
| WithDefault | `DEFAULT_INTERFACE_FIELD` | Interface has no instance constructor |
| Plain | `PLAIN_INTERFACE_FIELD` | Interface has no constructor |
| Child | `CHILD_FIELD`, `CHILD_BLOCK` | `CHILD_CONSTRUCTOR` |
| Constants | `CONSTANTS_BLOCK`, `CONSTANTS_COMPUTED` | No instance in the exercise |

Do not use file declaration order as a global initialization order. Types are initialized according to **execution actions**, with exceptions for superclasses/default-method superinterfaces.

### Step 2 — Mark active-use points

For example:

~~~text
Child.class.getSimpleName() → class literal, NO forced Child init
Constants.MAGIC            → compile-time constant, NO forced Constants init
new Child()                → initialize Parent / WithDefault / Child
Plain.TOKEN                → initialize Plain
Child.ping()               → Child already initialized
Constants.NON_CONSTANT     → initialize Constants
~~~

For each active use, check whether the type is already initialized.

### Step 3 — Track state per runtime class

Practical model:

~~~text
UNINITIALIZED
    |
    v
INITIALIZATION_IN_PROGRESS(thread X)
    |
    +--- success ---> INITIALIZED
    |
    +--- abrupt ---> ERRONEOUS
~~~

This means **one successful initialization**; subsequent active uses do not re-run the initializer. When initialization fails, the class can enter an erroneous state and cannot automatically retry initialization within the same runtime identity.

### Step 4 — Expand dependency order

Before running Child's static logic:

1. Initialize superclass Parent if not yet initialized.
2. Under modern rules, initialize required superinterfaces that have default methods.
3. Execute Child's static fields and static blocks in source order.
4. On `new Child()`, after class initialization comes the **constructor chain**.

If superclass or superinterface initialization fails, the subclass's static logic may not run, and a stack trace/exception replaces the normal output path.

### Step 5 — Compute field values carefully

- Primitive fields have default 0/false; reference fields have default null **during preparation**.
- Compile-time constants have different `ConstantValue`/inlining rules.
- During circular initialization, accessing an unassigned field can observe its default value.
- Static field initializers with side effects execute in source order.
- A mutable field can be modified after initialization; do not assume its value stays as it was initially.

### Step 6 — Print results along the execution path, do not guess from load logs

For each `println`, fill in the exact expression value and any side effects that occur **before println completes**. For example:

~~~java
System.out.println("RESULT=" + Feature.compute());
~~~

Java must evaluate the string concatenation expression, which **calls `Feature.compute()`** before `println` prints the result line. If Feature initialization prints a message, that line will appear **before** `RESULT=...`.

This is the reason init log lines “interleave” between two print lines in main.

### Step 7 — Distinguish stdout/stderr, threads, and VM logging

If static initializers run on multiple threads or use `System.err.println`, the display order when streams are merged can depend on scheduling and the logger. In the examples above, there is only the main thread and all application logs use `System.out.println`, so the order is deterministic.

Class-load logging often writes many independent lines; to get the “exact stdout of the source”, run **without VM logging enabled** or direct VM logs to a separate file.

## 12. Common traps

### 12.1. “The JVM loaded it, so the static initializer has already run”

**False.** Loading and initialization are distinct phases. `Feature.class` or `Class.forName(name,false,loader)` clearly illustrates this: the JVM can know about a class before its static block prints.

### 12.2. “Seeing Sub.FIELD means Sub is definitely initialized”

**False.** The field might be **declared in a superclass**, or be an inlined compile-time constant. Identify the declaring class/interface and how the field is used before predicting.

### 12.3. “Every interface is initialized before the implementing class”

**False.** There is a special rule for superinterfaces declaring **default methods**, not a claim that every interface is initialized like a superclass.

### 12.4. “Having `static final` means the initializer won't print”

**False.** Only *constant variables* as defined by Java have the exemption where reading does not trigger initialization. A `static final Integer` or a `static final int` assigned from a method call is not such a case.

### 12.5. “A static initializer always runs exactly once across the entire OS”

**False.** Initialization state is tied to **runtime class identity**, which is affected by the defining class loader. Two independent loaders can define the same binary name and initialize each class once. Launching another JVM process also has its own lifecycle.

### 12.6. “If `<clinit>` fails once, the JVM retries automatically next time”

**False.** If initialization fails, the class enters an erroneous state per the rules; subsequent active uses may receive `NoClassDefFoundError` (with a related cause) instead of attempting to run a new static initializer.

### 12.7. “Class loader logs show the same order on every machine”

**False.** Loading/resolution can be eager and depends on the VM, shared class data, frameworks, agents, and scheduling. Prioritize **active-use/initialization relationships per the specification** to predict application code output lines.

### 12.8. “The constructor runs before the subclass's static block”

**False** for a normal first instance creation: the class must be initialized first; the constructor chain takes place during object creation afterward.

## 13. When initialization fails, what happens to logs and subsequent uses?

Consider the illustrative code:

~~~java
class Unstable {
    static int port = Integer.parseInt("not-a-number");
    static {
        System.out.println("NEVER_REACHED");
    }
}
~~~

This is an illustrative class **without main**. If the program active-uses Unstable and the `parseInt` step throws `NumberFormatException`, the static block after it **does not run**, so `NEVER_REACHED` is not printed. The JVM completes class initialization abnormally, typically wrapping the appropriate exception in `ExceptionInInitializerError` when required per JVMS. When subsequently attempting to use **the same runtime class** again, one may receive `NoClassDefFoundError: Could not initialize class ...`.

Note:

- An error thrown from a static initializer does not automatically mean the JVM exits immediately; threads and callers can catch an appropriate Throwable, though this is a serious error that should not be masked.
- An `Error` raised in an initializer may be handled under different rules than a regular exception; do not assume every Throwable is always wrapped the same way.
- Do not manually invoke `<clinit>` to “retry”. There is no valid Java API to reset the initialization state of the same class.
- To retry business logic that might fail, move it into an **explicit initialization method** with clear state/retry handling rather than relying on a static initializer re-running.
- If a new class with the same binary name is created by **another loader session**, that is a new runtime identity, though it brings its own dependency/class-loader boundary challenges.

For production environments, limit uncontrolled I/O, blocking network calls, and circular dependencies in static initialization. Use logging and diagnose the root cause first; the final `NoClassDefFoundError` message sometimes does not point to the deepest cause.

## 14. Class initialization and multiple threads

The JVMS specifies that class/interface initialization is **synchronized** per runtime class. When thread T1 is initializing A and T2 also needs A, T2 may have to wait for A to finish; no two threads execute the initializer of **the very same runtime class** independently at the same time.

However:

- Initializers of **two different classes** can run on different threads and interleave log lines.
- If A's initializer waits for B and B's initializer waits for A across threads, a **class initialization deadlock** can occur.
- `System.out.println` across multiple threads does not provide a “program-wide source order” rule; there is only per-thread order and specific synchronization relationships.
- In stdout prediction problems with threads, one must examine happens-before, locks, join, thread scheduling, and relationships between initializers; do not assign an absolute order when the specification does not guarantee one.

Example:

~~~text
Thread 1: needs to initialize A → inside A.<clinit> waits for B
Thread 2: needs to initialize B → inside B.<clinit> waits for A

Both threads can get stuck if they hold initialization locks
and each needs the class the other is initializing.
~~~

This is a condition diagram, **not a fixed Java output**. Accurate prediction requires full Java code, synchronization mechanisms, and scheduler assumptions.

## 15. Loading trace, class identity, and “once” when there are multiple loaders

Two classes with the **same binary name** but defined by **two different defining class loaders** are two distinct runtime classes. Each class has its own initialization state and static fields. Therefore, VM logs can record the same class name appearing twice with different loader metadata; two static initializers can print the same label, but each belongs to a different runtime class.

This commonly appears in:

- Plugins/hot-reload with a child loader per session.
- Application servers with separate deployment classloaders.
- Test runners or frameworks isolating dependencies.
- Runtime-generated classes/proxies.

When you want to predict stdout for an app with multiple loaders, add a **defining loader column** to your tracking table. “Class name already initialized” is not enough if there are two runtime identities.

Also do not assume `Class.getClassLoader()` returns a Java object for the bootstrap loader in all cases: for bootstrap classes, the API typically returns `null` by contract.

## 16. Quick prediction practice

### Question 1 — Class literal

~~~java
Class<?> c = Unused.class;
System.out.println("KNOWN");
~~~

Suppose `Unused` has `static { System.out.println("INIT"); }`. Do those two lines alone guarantee printing `INIT`?

**No.** A class literal does not require initialization by itself; the line guaranteed from the visible code is `KNOWN` (ignoring separate JVM logs and effects outside the example).

### Question 2 — Static final

~~~java
static final int A = 3;
static final Integer B = 3;
~~~

Reading which field may avoid initializing the owner? **A** is a constant variable given the appropriate declaration; B is a reference and is not a compile-time constant variable.

### Question 3 — Parent/Child

Calling `new Child()` for the first time with Parent static block printing `P`, Child static block printing `C`, Parent constructor printing `p`, Child constructor printing `c`. Order?

~~~text
P
C
p
c
~~~

If called a second time after both have initialized successfully, only `p`, `c` are added.

### Question 4 — Interface field

`interface I { int X = compute(); }`, where compute prints `I_INIT` and returns 5. If only `I.class` is referenced, is `I_INIT` guaranteed? **No.** If `I.X` is read when I has not yet been initialized, **yes**.

### Question 5 — Circular fields

In CircularInitDemo, why does `B_INIT=1` print before `A_INIT=2`? Because A's initializer **reads B.value** before A's field is assigned, triggering B initialization; B reads A's default 0.

### Question 6 — Logging

Is `[class,load] demo.Feature` enough to prove Feature's static block has run? **No**. To prove block execution, look at logs/traces inside the initializer or a class-init event in its proper meaning.

### Question 7 — Read before println

Why in `System.out.println("VALUE=" + Target.NON_CONSTANT)` can the line `TARGET_INIT` appear **before** the line `VALUE=...`? Because Java must **evaluate the println argument expression** (including getstatic and class initialization if needed) before calling println to print the string.

### Question 8 — Two class loaders

A plugin class with the same binary name is defined by defining loaders A and B. Are their static initializers restricted to running only once in total? **No**; each runtime class has its own initialization state.

### Question 9 — Failed initialization

A class fails in `<clinit>`. Is the next active use guaranteed to re-run `<clinit>`? **No**; the erroneous state typically causes the JVM to throw an error on further use.

### Question 10 — JVM log and stdout

Can one claim that the order of **every** `[class,load]` line on JDK 17 and 21 will be completely identical? **No**. Only predict relationships guaranteed by the spec or source.

## 17. Further reading

- **Java Language Specification 17, §12.4.1 – When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS 17, §12.4.2 – Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **Java Virtual Machine Specification 17, §5.3 – Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS 17, §5.4 – Linking:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS 17, §5.5 – Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JVMS 17, §4.7.2 – ConstantValue:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2
- **JDK 17 java launcher tool:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JDK 17 javap:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Conclusion:** to predict output in JVM class initialization exercises, separate **class-load logs** from **initializer stdout**; accurately mark **active uses**, consider **superclasses and superinterfaces declaring default methods**, execute **static fields/blocks in textual order**, distinguish **constructors from `<clinit>`**, and remember that each runtime class is successfully initialized only once. For **constant variables**, **class literals**, **`Class.forName(false)`**, and **circular initialization**, do not mechanically apply the rule “mentioning a class name prints its static block”.
