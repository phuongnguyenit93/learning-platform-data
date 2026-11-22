# Distinguishing Loading, Linking, and Initialization in the Lifecycle of a Class

## 1. Objectives and Overview Model

A Java class may already exist as a **Class object** in the JVM yet **not have run its static initializer**. It may have been verified and prepared, while some symbolic references remain unresolved. Conversely, when the application actually uses the class, the JVM must ensure the required steps have completed in the proper order and according to type-safety rules.

The three key terms of the Java Virtual Machine Specification (JVMS) are:

1. **Loading:** finding/obtaining the binary representation of a class/interface and creating the corresponding runtime class.
2. **Linking:** bringing the newly loaded class into a state usable by the JVM, consisting of **verification**, **preparation**, and **resolution**; resolution may be performed partially or eagerly depending on specification conditions.
3. **Initialization:** executing the initialization work of the class/interface, typically **static field initializers** and **static initializer blocks**, expressed by the compiler in the special method **<clinit>** if needed.

After this lesson, you should be able to:

- Distinguish the three phases, and understand **verification**, **preparation**, **resolution**, and the milestone guaranteed before initialization.
- Correctly state the operations that cause **active use**: creating an instance, invoking a static method, reading/writing an appropriate static field, reflection requesting initialization.
- Explain why **Class.forName(name, false, loader)**, **T.class**, or a **compile-time constant** does not necessarily trigger initialization.
- Accurately trace the order of static initializers, superclass, and subclass; distinguish the interface case.
- Distinguish **ClassNotFoundException**, **ClassFormatError**, **VerifyError**, **NoSuchMethodError**, **ExceptionInInitializerError**, and **NoClassDefFoundError**.
- Use Java 17+, **javap**, and class-loading logs to observe what is observable, while avoiding over-inferring when the verifier/resolver runs.

**Context:** This lesson is about the lifecycle of a **class or interface within a single JVM**; it is not synonymous with the lifecycle of an **instance object**, of a **ClassLoader**, or of the entire JVM process.

## 2. Lifecycle Diagram and Mandatory Milestones

Read the diagram as a **dependency model**, not as an absolute synchronized schedule for every class in a program:

~~~text
Class bytes source / module / classpath
               |
               v
        [1] LOADING
     - Find binary representation
     - Create runtime class, Class object
     - Attach defining class loader
               |
               v
        [2] LINKING
     +-----------------------------------+
     | Verification                      |
     |   Check validity/safety           |
     |                                   |
     | Preparation                       |
     |   Create static fields            |
     |   Assign default values           |
     |                                   |
     | Resolution                        |
     |   Symbolic ref -> real entity     |
     |   May happen partially            |
     +-----------------------------------+
               |
               v
        [3] INITIALIZATION
     - Mark state as being initialized
     - Initialize superclass / appropriate
       superinterfaces
     - Execute static initialization
       and applicable ConstantValues
               |
               v
       READY FOR ACTIVE USE
~~~

Important constraints according to the JVMS:

- A class/interface must be **completely loaded before linking**.
- It must be **completely verified and prepared before initialization**.
- **Resolution** of each symbolic reference may be deferred until that reference is actually used, or performed eagerly when the JVM meets the conditions. Therefore, not every dependency of a class needs to be resolved before running the first part of the static initializer.
- Activities may indirectly trigger loading/linking of other classes. It is impossible to list a single sequential path from class A to class B that every JVM must follow.
- **Initialization** is a class-level event, coordinated when multiple threads request it concurrently; **the static initializer is not re-run on each new**.

Quick comparison table:

| Criterion | Loading | Linking | Initialization |
| --- | --- | --- | --- |
| Main result | Runtime class is created and attached to a loader | Metadata, validity, static storage, and symbolic references are processed as required | Static initialization of the class completes or fails |
| Executes static initializer code of target class? | Not part of the loading phase | **No**, not the responsibility of verification/preparation/resolution | **Yes**, if the class/interface has initialization code to run |
| Involves class bytes? | Yes | Yes, especially verification/descriptors/constant pool | Relies on code and metadata already loaded/linked |
| Can cause loading of other classes? | Yes, e.g., superclass/superinterface | Yes, when verifying/resolving types/references | Yes, due to using other classes in static code |
| Completes all symbolic references? | No | **Not required** up front | Not necessarily; resolution may still happen later |

## 3. Loading: How Does a Class Become a Runtime Type?

### 3.1. Class Identity Is Not Just the Name

For ordinary classes, the JVM identifies a type by its **binary name** and **defining loader**:

~~~text
(com.example.Order, LoaderA)
(com.example.Order, LoaderB)
~~~

If LoaderA and LoaderB define two classes with the same name, they are still **two distinct runtime classes**. Passing an object of the first class to a place expecting the second class can fail on cast, reflection, interface method invocation, or linking constraints.

Concepts to distinguish:

- **Defining loader:** the loader that actually defines the class.
- **Initiating loader:** the loader that initiates/requests the loading process and may have successfully delegated to another loader.
- **Bootstrap loader:** the foundational loader of the JVM; the Java API typically represents it as **null** when reading **Class.getClassLoader()** on a corresponding class.
- **Application/platform/custom loader:** different lookup sources; delegation mechanisms depend on the loader and module configuration.

Loading a class normally does not automatically grant reflection access in the Java Platform Module System. Module readability/exports/opens are subject to separate rules.

### 3.2. Some APIs That Learners Mistake for Initialization

~~~java
// Illustrative lines placed inside a method with throws Exception.
Class<?> a = SomeType.class;
Class<?> b = Class.forName("SomeType", false,
        SomeType.class.getClassLoader());
Class<?> c = SomeType.class.getClassLoader()
        .loadClass("SomeType");
~~~

They can all lead to or use a Class object, but **do not require executing SomeType's static initializer** merely by taking a class literal, using the forName overload with **initialize=false**, or using a normal **loadClass(name)**.

Conversely:

~~~java
// Illustrative code inside a method with throws Exception.
Class<?> c = Class.forName("SomeType"); // single-parameter overload
~~~

**Class.forName(String)** uses the appropriate initiating class loader and **requests initialization** per the API contract. **Class.forName(name, true, loader)** does the same. Saying “Class.forName only loads a class” without distinguishing the overloads is inaccurate.

**Context note:** In the illustrative lines, **SomeType** must be an actual class that can be found by the appropriate name. Nested class names use the **$** character in binary names, for example **Example$Inner**, not **Example.Inner**.

### 3.3. Loading Can Be an Indirect Result

The JVM may have to load the superclass, implemented interfaces, or a class referenced in a descriptor to verify/resolve constraints. The fact that bytecode contains the name of another class **does not guarantee** that the class is loaded at one fixed offset across all JVMs.

For example, the compiler may emit a constant-pool entry pointing to **com.example.OptionalFeature** inside a method that is only called under a corresponding configuration. The JVM has the right to use eager or lazy resolution within the bounds of the specification. Avoid relying on the reasoning “that method hasn't been called yet, so the other class is definitely not loaded” when designing systems.

### 3.4. Array Classes Differ from Ordinary Class Files

The JVM creates array classes via a separate mechanism. There is no convention of looking up a file **[I.class** for type **int[]**. For **String[]**, the array class has a **Class** object, but does not have user-written **<clinit>** code like an ordinary class.

- **int[].class.getClassLoader()** normally returns **null** (primitive array).
- **UserType[].class.getClassLoader()** returns the loader of the reference component type per the API.
- Creating **new UserType[10]** creates an array with null elements, and **does not initialize UserType** merely because the array component has type UserType.

## 4. What Are the Exact Three Tasks of Linking?

### 4.1. Verification: Checking Validity

**Verification** checks that the loaded class has a structure and bytecode satisfying the JVM's rules on type safety, operand stack, locals, control flow, and constraints.

Errors the verifier can detect or relate to:

- An **ireturn** instruction used where an incompatible reference needs to be returned.
- A branch jumping into the middle of another instruction's operand bytes.
- An instruction consuming a value of a type not permitted by the JVM from the operand stack.
- Stack depth or StackMapTable inconsistent across branch paths.
- Class file, inheritance, or descriptor violating required JVM constraints.

Conceptual bytecode example (not a valid Java program):

~~~text
iconst_1
areturn   // Cannot return a reference when the stack contains an int
~~~

**Normal javac** does not emit this kind of violating bytecode from valid Java source. Anyone doing bytecode weaving/instrumentation or generation must use a verifier, update stack map frames, and adhere to class-file version/format.

From **ClassFormatError** (invalid class file data/format) to **VerifyError** (bytecode fails verification conditions), both are class-related errors, but **their causes and phases should not be conflated**. These error types are branches of **LinkageError**.

### 4.2. Preparation: Preparing Static Storage and Default Values

During **preparation**, the JVM creates static fields for the class/interface and initializes them to **default values** according to type. No Java code needs to be executed to perform this preparation work.

| Static field type | Default value at preparation |
| --- | --- |
| **int, short, byte, long** | 0 |
| **float, double** | 0.0 (corresponding type) |
| **boolean** | false |
| **char** | character with value 0 |
| **reference** | null |

Example:

~~~java
// Illustrative partial class code:
static int retries = 5;
static Object holder = new Object();
~~~

During preparation, the two fields exist with default values **0** and **null**. Evaluating the expression **= 5** or **new Object()** is the job of **initialization** according to class rules, not preparation.

**Easily confused exception:** A **static final** field with a **ConstantValue** attribute (compile-time constant) is assigned its constant value by the JVM during the **initialization procedure**, before superclass initialization and running <clinit> code according to JVMS §5.5. One should not claim that every static final constant is assigned its final value right at preparation. However, accessing a Java constant variable from a client does not necessarily trigger initialization of the declaring class because the compiler can use the known constant; that is a separate rule.

### 4.3. Resolution: From Symbolic Reference to Real Reference

A class file generally does not contain direct pointers to other runtime methods/fields/classes. It holds **symbolic references** in the constant pool, for example:

~~~text
Owner internal name: java/lang/String
Method name:          length
Method descriptor:    ()I
~~~

**Resolution** locates the appropriate runtime entity for the reference, checking accessibility, signature, member kind, and required constraints. Many bytecode instructions require resolution, such as **new**, **getstatic**, **putstatic**, **invokevirtual**, **invokestatic**, **getfield**, **checkcast**, **ldc**, and **invokedynamic**.

Example:

~~~java
// Illustrative code:
int size = someString.length();
~~~

The bytecode may contain **invokevirtual** pointing to the symbolic method reference **java/lang/String.length:()I**. When this reference is used, the JVM must ensure it resolves to the appropriate method.

Errors related to resolution/linking include:

| Error | A common cause |
| --- | --- |
| **NoSuchMethodError** | The running binary class no longer has the method with the name+descriptor the caller compiled against |
| **NoSuchFieldError** | The referenced field no longer exists as requested by the caller |
| **IllegalAccessError** | Accessing the member/class is forbidden by access/module rules at runtime |
| **IncompatibleClassChangeError** | The member/class structure differs from compile-time assumptions; e.g., static/instance changed incompatibly |
| **NoClassDefFoundError** | The JVM needs a class dependency but cannot find/load/initialize it under the given conditions |

**Important:** resolution does not necessarily complete all at once before the class begins initialization. The JVM may resolve a reference when an instruction uses it. Thus, a linkage error for a rarely used method might only surface when that method is executed, depending on the JVM and reference kind.

### 4.4. What Do Eager and Lazy Resolution Mean?

~~~text
Interpretation A (illustrative only):
Load C -> verify -> prepare -> resolve many refs early
       -> init C -> call method needing ref

Interpretation B:
Load C -> verify -> prepare -> init C
       -> call method -> resolve exact ref needed
~~~

The JVMS grants the JVM the choice of early or late resolution timing for many symbolic references, while still guaranteeing mandatory properties regarding linking outcomes and error-throwing points. **Dynamically-computed constants/call sites** have their own rules; the diagrams above must not be applied blindly to all bootstrap resolution.

Conclusion: observing **Class.forName(name,false,loader)** return does not prove that every class the target might use has been resolved.

## 5. Initialization: What Does Java Execute?

When a class/interface needs to be initialized, the JVM ensures that verification/preparation and necessary foundational steps have completed. Initialization work typically includes:

1. Transitioning the class state to **being initialized** and coordinating with other threads.
2. Assigning **static final** fields that have **ConstantValue** per JVM rules.
3. For a **class**, ensuring its superclass and eligible superinterfaces are processed in the specified order.
4. Executing the initialization code of the class/interface in the order defined by the compiler and specification.
5. Marking the class **fully initialized** if successful, or **erroneous** if the process fails.

### 5.1. What Is <clinit>?

In a class file, static initialization code is combined by the compiler into the special method **<clinit>** when needed:

~~~java
class Configuration {
    static int port = loadPort();

    static {
        System.out.println("Configuration initialized");
    }

    static int loadPort() {
        return 8080;
    }
}
~~~

Semantically, this runs the call **loadPort()** followed by the static block when Configuration is initialized; the corresponding code may appear in **<clinit>**. <clinit> is not a constructor **<init>** and cannot be written directly as an ordinary Java method.

Classes that only have static compile-time constants may **not need** a <clinit> containing code, yet still have class lifecycle state.

### 5.2. Static Fields and Static Blocks Run in Textual Order

~~~java
class Steps {
    static int a = print("a", 1);
    static { System.out.println("block"); }
    static int b = print("b", 2);

    static int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

When Steps is initialized for the first time, the print order is:

~~~text
a
block
b
~~~

The JVM does **not** run **all static field initializers first** and then **all static blocks**. The compiler must preserve the textual order of static initializers per the JLS.

### 5.3. Initialization Is Not Instance Construction

~~~java
class Widget {
    static {
        System.out.println("class init");
    }

    {
        System.out.println("instance init");
    }

    Widget() {
        System.out.println("constructor");
    }
}
~~~

On the first **new Widget()**:

~~~text
class init
instance init
constructor
~~~

On the second **new Widget()** in the same runtime class:

~~~text
instance init
constructor
~~~

**Static initialization** occurs at the class level, whereas **instance field initializers**, **instance initializer blocks**, and constructors run according to the rules for creating each object. Both are called “initialization” in Vietnamese, so they must never be conflated when analyzing the JVM class lifecycle.

## 6. When Is a Class/Interface Initialized?

Common cases according to JLS §12.4.1/JVMS §5.5:

- Creating an instance via **new C()** for the first time causes C to need initialization (and its superclass per the rules).
- Invoking a **static method actually declared by C**.
- Writing a **static field declared by C**.
- Reading a **static field declared by C that is not a constant variable**.
- Requesting initialization through certain reflection APIs, such as **Class.forName(name,true,loader)**.
- C being chosen by the JVM as the initial class when starting the process.
- Other specified situations such as method handles and initialization of subclasses/appropriate superinterfaces.

**Do not treat every syntax mentioning the name C as an active use.**

### 6.1. Operations That Normally Do Not Trigger Initialization on Their Own

| Operation | Note |
| --- | --- |
| **C.class** | A class literal does not run C's <clinit> on its own |
| **obj instanceof C** | Does not require initialization of C merely for type checking |
| Cast **(C) obj** | Does not initialize C merely for casting |
| Creating **new C[10]** | Creates an array, does not create C instances, and does not init C on its own |
| Declaring **C variable;** | Declaring a variable of type C is not an active use |
| **ClassLoader.loadClass(name)** | Normally does not request initialization |
| **Class.forName(name,false,loader)** | Requests load/link per API, does not initialize |
| Reading compile-time constant **C.ANSWER** | Does not initialize C if the field is a constant variable per the rules |
| Calling **getDeclaredMethods()** on Class | Do not assume every reflection inspection inits the class; read each API's contract |

**Note:** operations that do not **initialize C** may still cause C or other classes to be **loaded**, **linked**, or **resolved** depending on the case. This is why the absence of static log output cannot be used as proof that a class has not been loaded.

### 6.2. Static Field Declared in a Superclass

Consider:

~~~java
class Base {
    static int number = 123;
}

class Child extends Base {
    static {
        System.out.println("Child init");
    }
}
~~~

If a client reads:

~~~java
System.out.println(Child.number);
~~~

The field **number** is actually declared in **Base**. Java rules only require initializing class **Base** for that operation; there is no requirement to initialize **Child** just because Child's name appears to the left of the dot.

Conversely, if reading a non-constant field **Child.ownNumber** actually declared in Child, class Child needs to init and superclass Base is also initialized beforehand if not already initialized.

### 6.3. Compile-Time Constants and Inlining

~~~java
class Constants {
    static final int LIMIT = 256;         // constant variable
    static final String MODE = "basic";    // constant variable
    static final int DYNAMIC = compute(); // not a constant variable

    static int compute() {
        return 7;
    }

    static {
        System.out.println("init Constants");
    }
}
~~~

When a client writes **Constants.LIMIT** or **Constants.MODE**, the compiler can substitute the constant value directly into the client's bytecode, so reading them **does not cause Constants to initialize**.

Reading **Constants.DYNAMIC** is an active use and must trigger initialization if not yet run.

Be careful with **static final**: not every field with both keywords is a constant variable. **static final Integer BOXED = 1**, **static final String TEXT = new String("x")**, and **static final int DYNAMIC = compute()** are all not Java constant variables under the applicable compile-time constant expression rules.

**Binary compatibility consequence:** When changing the value of a public static final compile-time constant in a library, old clients may continue using the inlined value until recompiled. Do not equate this issue with class loader caching or initialization errors.

## 7. Runnable Java 17+ Example: Loaded but Not Initialized

Create the file **LifecycleObservation.java**:

~~~java
public class LifecycleObservation {
    static class Probe {
        static final int LIMIT = 42;
        static int current = initializeCurrent();

        static int initializeCurrent() {
            System.out.println("Probe:field");
            return 7;
        }

        static {
            System.out.println("Probe:block");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main:start");

        ClassLoader loader =
                LifecycleObservation.class.getClassLoader();
        Class<?> type = Class.forName(
                "LifecycleObservation$Probe", false, loader);

        System.out.println("sameClass=" + (type == Probe.class));
        System.out.println("constant=" + Probe.LIMIT);
        System.out.println("main:before-active-use");

        System.out.println("value=" + Probe.current);
        System.out.println("valueAgain=" + Probe.current);

        Class.forName("LifecycleObservation$Probe", true, loader);
        System.out.println("main:end");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 LifecycleObservation.java
java LifecycleObservation
~~~

**Exact stdout in a fresh JVM launch:**

~~~text
main:start
sameClass=true
constant=42
main:before-active-use
Probe:field
Probe:block
value=7
valueAgain=7
main:end
~~~

Step-by-step explanation:

1. The main class **LifecycleObservation** is initialized before calling main.
2. **Class.forName(...,false,loader)** loads/links **Probe** per contract without requesting initialization.
3. **Probe.class** is not an active use, so comparing Class objects does not print Probe's messages.
4. **Probe.LIMIT** is a constant variable; the client can use the constant 42 directly.
5. The first access to **Probe.current** is the active use: the JVM runs Probe's static initialization in order: **initializeCurrent()** then the static block.
6. Reading current again returns 7 without **re-running** init.
7. Calling **Class.forName(...,true,loader)** after the class is already successfully initialized does not cause init to run again.

**What cannot be inferred from stdout:** Printing nothing during forName(false) does not prove the verifier has not run or that the pool has no resolved symbolic references. Linking steps are not designed to print logs from Java source.

## 8. Preparation and Default Values Observable in <clinit>

Create the file **PreparationObservation.java**:

~~~java
public class PreparationObservation {
    static class State {
        static int first = readSecond();
        static int second = 9;

        static int readSecond() {
            return second;
        }

        static {
            System.out.println("State:ready");
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + State.first);
        System.out.println("second=" + State.second);
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 PreparationObservation.java
java PreparationObservation
~~~

**Stdout:**

~~~text
State:ready
first=0
second=9
~~~

Analysis:

- When linking State, static fields are created and receive the default value **0**.
- When initializing State, the initializer of **first** calls the method **readSecond()** before the initializer of **second** runs.
- **readSecond()** can read **second** while it holds the default value 0 (indirect reference via a method, avoiding Java source's direct illegal forward reference rule).
- Then **second = 9**, followed by the static block printing **State:ready**.
- Main waits for State to finish initialization and prints **first=0** and **second=9**.

This behavior is caused by the **order of static initializers** in the class. Do not conclude that preparation “runs readSecond's code”; readSecond executes during initialization.

If you try writing directly **static int first = second; static int second = 9;**, the Java compiler can report **illegal forward reference**. The example uses a method to show the valid default state during sequential initialization.

### 8.1. Limits of Observation

The JVM does not provide an ordinary Java hook for you to insert println statements arbitrarily between verification and preparation of the same class. The program above **indirectly** shows that a static field whose initializer expression has not yet been assigned in <clinit> holds its default value when initialization code begins running.

Do not guess the memory size of static fields or the order of internal VM data structures from this output.

## 9. Superclass Initialized Before Subclass

Create the file **InheritanceInitialization.java**:

~~~java
public class InheritanceInitialization {
    static class Parent {
        static int base = trace("Parent:field", 10);

        static {
            System.out.println("Parent:block");
        }
    }

    static class Child extends Parent {
        static int own = trace("Child:field", 20);

        static {
            System.out.println("Child:block");
        }
    }

    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("main:start");
        System.out.println("childOwn=" + Child.own);
        System.out.println("baseViaChild=" + Child.base);
        System.out.println("main:end");
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 InheritanceInitialization.java
java InheritanceInitialization
~~~

**Stdout:**

~~~text
main:start
Parent:field
Parent:block
Child:field
Child:block
childOwn=20
baseViaChild=10
main:end
~~~

Reason:

1. Reading **Child.own** triggers initialization of Child.
2. Before that, the JVM must ensure superclass **Parent** is initialized.
3. Parent runs its initializers in field-then-block order.
4. Child then runs its field initializer and static block.
5. The subsequent **Child.base** actually accesses a field declared in Parent and **does not re-init** any class.

If only **Child.base** is read first without ever accessing **Child.own**, the JVM can init Parent without **needing to init Child**.

### 9.1. Interfaces Have Different Rules from Classes

- Initializing a **class** entails initializing its superclass and those superinterfaces that qualify by declaring default methods per JVMS/JLS rules.
- Initializing an **interface** **does not automatically** initialize all of its superinterfaces.
- When accessing a static field of an interface, the active use rule considers the interface that declares it; a constant variable does not necessarily trigger initialization.
- There are compiler-generated default methods; analyzing complex interface initialization requires checking the class file, not just method names visible in source.

Example of an interface with fields:

~~~java
interface Flags {
    int STATIC_CONSTANT = 5;
    int DYNAMIC = initialize();

    static int initialize() {
        System.out.println("Flags:init");
        return 8;
    }
}
~~~

Reading **Flags.STATIC_CONSTANT** does not require init; reading **Flags.DYNAMIC** requires initializing Flags and running the code of **initialize()**. This is standalone illustrative code demonstrating the principle; output only occurs when placed in a program with main and accessed.

## 10. Class Lifecycle When Multiple Threads Request Initialization Concurrently

The JVM must coordinate class initialization when multiple threads perform active use concurrently:

- If one thread is initializing C, another thread needing C initialized will wait according to the initialization lock mechanism specified by the VM.
- If the thread currently initializing C recursively requests initialization of C again, the VM has rules for handling recursive requests; it does not simply run a second <clinit>.
- When init succeeds, the class reaches the fully initialized state; subsequent requests do not re-run static initialization.
- If init fails, the class transitions to the **erroneous state**; subsequent init requests for the same runtime class do not automatically re-run <clinit>.

**Do not equate the initialization lock with all static methods being synchronized.** After the class has been initialized, static methods still have their own concurrency rules; reading/writing mutable static fields across threads must follow the Java Memory Model. Class initialization provides publication guarantees for initialized state per JVM semantics, not thread-safety for all subsequent static state.

### 10.1. Can a Class Be Initialized Twice in the Same JVM?

The **same runtime class**, meaning the same **(binary name, defining loader)** identity, executes initialization once if successful.

However, two different defining class loaders can define two runtime classes with the same binary name; each runtime class has its own initialization lifecycle. This is why a redeployed web container/plugin can see a fresh copy of static initializers when using a new loader, while the old class still exists if the old loader remains referenced.

## 11. Failed Initialization: Erroneous State and Subsequent Errors

An error occurring in a static field initializer or static block can cause class initialization to fail.

- If <clinit> code throws a non-Error exception, the JVM normally reports **ExceptionInInitializerError** wrapping the original error per JVMS rules.
- If the cause is already an **Error**, the JVM may throw that Error directly.
- The class is marked **erroneous** when initialization fails, and subsequent active uses of the same runtime class may receive **NoClassDefFoundError** instead of re-running the initializer.
- Dependent classes (e.g., subclasses) may fail when superclass initialization errors out.

### 11.1. Runnable Example: First Time and Subsequent Times Differ

Create the file **FailedInitialization.java**:

~~~java
public class FailedInitialization {
    static class Broken {
        static int number = fail();

        static int fail() {
            System.out.println("Broken:init");
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.number);
        } catch (Throwable problem) {
            System.out.println("first="
                    + problem.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.number);
        } catch (Throwable problem) {
            System.out.println("second="
                    + problem.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 FailedInitialization.java
java FailedInitialization
~~~

**Stdout:**

~~~text
Broken:init
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

- The first access triggers **Broken.<clinit>**. **fail()** prints its log and throws IllegalStateException; the JVM wraps the error per rules so the caller sees ExceptionInInitializerError.
- The next access does not re-run **fail()**, because the runtime class Broken is already in the **erroneous state**; the JVM reports NoClassDefFoundError.
- The pattern of catching **Throwable** is only for **observing errors in this experiment**. Production code should not use a broad catch(Throwable) to keep running after serious Errors.

**Do not rush to explain every NoClassDefFoundError as “missing .class”**. It can also appear because the class failed initialization earlier. Always read the **cause** and the full error chain from the first failure.

### 11.2. Can You “Retry” Init by Calling Class.forName Again?

For the **same runtime class** that is already erroneous, calling **Class.forName(name,true,loader)** again does not recover its state; initialization still fails. To resolve it, you must fix the root cause and usually need a new process/configuration or a **genuinely different** runtime class defined by a new loader, if the architecture permits. Do not use a new loader to mask errors and cause class-identity conflicts.

## 12. Error Groups by Lifecycle Phase

| Error | Typical issue category | When is it commonly encountered? |
| --- | --- | --- |
| **ClassNotFoundException** | Lookup request by name cannot find the class | **Class.forName**, **ClassLoader.loadClass** |
| **ClassFormatError** | Class file has invalid structure/tags/descriptors or format constraints | Loading and validating class data |
| **UnsupportedClassVersionError** | Runtime does not support the class file's major/minor version | Loading a newer-version class on an older JVM |
| **VerifyError** | Bytecode/stack maps/control flow violate verification conditions | Linking — verification |
| **NoSuchFieldError** | Field compiled against is no longer compatible at runtime | Resolution/field access |
| **NoSuchMethodError** | Method was incompatibly changed/removed at runtime | Resolution/invocation |
| **IllegalAccessError** | Access/module permission check fails | Linking/resolution |
| **IncompatibleClassChangeError** | Expectations about class/member being instance/static/interface mismatch | Linking or using a reference |
| **ExceptionInInitializerError** | Static initializer throws a non-Error exception | First-time initialization |
| **NoClassDefFoundError** | JVM cannot define/load class as needed or class is already erroneous | When class is needed, after load/init failure |
| **ClassCircularityError** | Invalid circular class inheritance constraint | During loading/linking |
| **OutOfMemoryError** | JVM resources exhausted; can occur in many places | Not specific proof of a single phase |

**One symptom can have multiple causes.** For example, NoClassDefFoundError is not only caused by the classpath, and IllegalAccessError is not like a Java compile-time error for private access because runtime class files may differ from build-time classes.

**Checking the root cause** is always more valuable than guessing from a single exception name.

## 13. How to Observe the Lifecycle with Tools

### 13.1. javap: Identifying <clinit>, Not Directly Measuring Phases

After compiling:

~~~bash
javap -c -p LifecycleObservation
javap -c -p 'LifecycleObservation$Probe'
javap -v -p 'LifecycleObservation$Probe'
~~~

Because the command contains **$** in the name, it needs appropriate shell quoting; the lines above work in Bash/PowerShell where single quotes are supported, while Command Prompt requires syntax adjustment. **javap -p** shows private members; **-c** shows bytecode; **-v** also shows the constant pool/attributes.

You can look for:

- In main: **ldc** containing the class literal, **getstatic** for Probe.current, and **invokestatic** for Class.forName.
- In Probe: the special method **static {}** or **<clinit>** as displayed by javap, including the call to **initializeCurrent** and println.
- The **ConstantValue** attribute or how the compiler uses the constant for **Probe.LIMIT**.
- Class/method/field references in the constant pool.

**Limitation:** javap only shows the **compiled class file**; it does not tell you the exact runtime moment when the verifier ran or when each reference was resolved on every JVM.

### 13.2. Class Loading and Initialization Logs on Supported JVMs

With HotSpot supporting Unified JVM Logging (Java 17):

~~~bash
java -Xlog:class+load=info LifecycleObservation
~~~

This type of log can output many class names, data sources, and other details; format, level, and order depend on the JVM. A load log **is not** a log that <clinit> has run.

Supported tags can be queried with:

~~~bash
java -Xlog:help
~~~

Do not claim that every VM/version shares a single dedicated “init” tag at the same log level or output layout. Use deliberate stdout from static blocks combined with runtime logs to distinguish:

- **A class can be loaded before** the initializer's println line.
- **A static initializer runs once** upon active use.
- **Absence of an initializer line** is insufficient to conclude the class has not been loaded/linked.

### 13.3. Observing Class Loader and Module

~~~java
// Illustrative code placed in a method:
Class<?> type = LifecycleObservation.class;
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule().getName());
~~~

Depending on the environment, the loader may print its implementation name, and module name may be null for an unnamed module. Therefore, these are dynamic diagnostic values, not fixed stdout to memorize.

To obtain a Class object **without init**, use the **Class.forName(name,false,loader)** overload; however, even this API still has loading/linking effects and can throw linkage errors.

## 14. Practical Timeline of a new Statement

When a program encounters:

~~~java
// Illustrative expression:
Widget w = new Widget();
~~~

With **Widget** never having been initialized before, summary of behavior:

1. The JVM must ensure the required Widget class definition has been loaded/created.
2. The JVM ensures verification and preparation are complete; appropriate resolution is handled as needed.
3. Because **new Widget()** is an active use, the JVM requires initialization of Widget, including its superclass and relevant superinterface cases.
4. After initialization succeeds, the JVM performs instance creation: allocation, default values for instance fields, processing the constructor chain, instance field initializers, and constructor body per the rules.
5. Returns a reference to the object if the entire operation succeeds.

**Do not equate** static fields receiving default values during **preparation** with instance fields receiving default values during **object creation**. They occur at different levels.

In bytecode, **new** and **invokespecial <init>** are distinct instructions/operations. **<clinit>** is not a constructor, and the source statement **new Widget()** can trigger both class initialization and instance initialization when used for the first time.

## 15. Resolution, Class Initialization, and Startup Dependencies: A Scenario

Suppose:

~~~java
// Illustrative code in class Service:
static {
    System.out.println("Service init");
}

static String loadData(boolean enabled) {
    if (enabled) {
        return OptionalLibrary.read();
    }
    return "disabled";
}
~~~

If **OptionalLibrary** does not exist at runtime, one cannot conclude from source alone that **loadData(false)** will always succeed or that the JVM will necessarily throw an error as soon as Service is loaded. The timing of reference resolution also depends on JVM strategy, linkage conditions, and Java/module semantics.

More reliable design practices:

- If the library is a required dependency, package and verify it at deployment/build time; do not rely on lazy resolution to “dodge” the dependency.
- If the feature is genuinely optional, use explicit class loading/reflection or well-designed module/plugin boundaries, handling missing-dependency errors deliberately.
- Do not place logic with hard-to-recover side effects inside a static initializer just to load libraries dynamically.
- Write integration tests running with the real classpath/module path, not just unit tests with all dependencies present.

## 16. Do Interfaces, Enums, Records, and Nested Classes Have the Same Phases?

**Yes:** classes and interfaces both undergo loading, linking, and initialization per the specification, though initialization rules have differences.

- **Interface:** interface static fields are typically **public static final**; a field assigned the result of a method call that is not a compile-time constant can still require interface initialization. Interface initialization does not automatically init all of its superinterfaces.
- **Enum:** is a class with initialization steps related to enum constants; operations using an enum can trigger initialization of the enum class, creating the enum instances per the rules.
- **Record:** is a specialized class, still having class initialization for static members; the record canonical constructor controls instance initialization, not replacing <clinit>.
- **Nested/static member class:** has its own binary name and its own class lifecycle. Initializing the outer class **does not automatically** init all static nested classes merely because they are declared inside.
- **Anonymous/local class:** also has runtime class identity; binary name details are compiler-generated, and creating an instance of it is an appropriate active use.

For example, Java often refers to “outer class” and “nested class” in one source unit, but the JVM sees them as separate class definitions across class files and loader contexts.

## 17. Misconceptions to Avoid

1. **“Loaded means the static block has already run.”** False; loading can happen earlier than initialization.
2. **“Class.forName always only loads.”** False; the single-parameter overload and initialize=true can trigger initialization.
3. **“C.class guarantees the static initializer runs.”** False; a class literal is not an active use under normal rules.
4. **“Linking is a single operation that must resolve every reference.”** False; it consists of verification, preparation, and resolution, and resolution can be lazy.
5. **“Preparation runs static int x = compute().”** False; that is initialization.
6. **“Preparation immediately assigns every static final field its final value.”** Inaccurate; ConstantValue is applied according to its own initialization procedure.
7. **“If it is static final, reading it definitely won't init the class.”** False for a static final that is not a constant variable.
8. **“Creating new C[10] is the same as new C().”** False; array allocation does not create C instances and does not require initializing C merely for its component type.
9. **“Reading Child.parentField will init Child.”** Not if the field is actually declared in Parent and there is no other active use of Child.
10. **“Every parent interface must init before a subinterface.”** False; interfaces have different rules from classes.
11. **“Static initializers run once per object.”** False; they run at the runtime class level.
12. **“NoClassDefFoundError only means a .class file is missing.”** False; a class that failed initialization earlier can also produce this error.
13. **“Two classes with the same name always share static state.”** False if defined by different loaders.
14. **“javap shows the exact time the JVM links every reference.”** False; it shows bytecode/metadata, not global runtime timing.
15. **“The JIT is allowed to skip class initialization rules to be faster.”** False; all optimizations must preserve observable semantics and side effects per the specification.

## 18. Practice Exercises with Answers

**Exercise 1 — Identifying the phase**

A loader has found the bytes and created a Class object; the JVM checks stack typing; later, a static block prints a log. Match the three actions to their phases.

**Answer:** Creating the Class object belongs to **loading**; stack typing belongs to **linking/verification**; printing the static block log belongs to **initialization**.

**Exercise 2 — Default value**

~~~java
class C {
    static int a = read();
    static int b = 15;

    static int read() { return b; }
}
~~~

On the first access to **C.a**, what is its value?

**Answer:** **0**. When a's initializer runs, b still has its default value because b's initializer appears later in textual order.

**Exercise 3 — Class literal**

~~~java
class C {
    static { System.out.println("C initialized"); }
}
Class<?> type = C.class;
~~~

Does taking the class literal necessarily print **C initialized**?

**Answer:** No. A class literal may obtain/cause the class to be loaded/linked as needed, but it is not an active use that initializes the class.

**Exercise 4 — Static constant**

~~~java
class C {
    static final int X = 9;
    static final Integer Y = 9;
    static { System.out.println("init"); }
}
~~~

Do reading **C.X** and **C.Y** have the same initialization behavior?

**Answer:** No. **X** is a constant variable so reading it does not require initializing C; **Y** is a boxed Integer, not a compile-time constant variable, so **getstatic** to read Y triggers initialization.

**Exercise 5 — Accessing an inherited static field**

Given **Base.count** and **Child extends Base**. When only reading **Child.count**, if count is actually declared in Base, which class needs to be initialized?

**Answer:** Class **Base** when the field is not a constant variable; Child does not need to be initialized because it does not declare the field.

**Exercise 6 — Early or late resolution**

An uncalled method contains a symbolic ref to class OptionalFeature. Can we assert that the JVM has definitely not resolved that ref?

**Answer:** No. The JVMS permits early or late resolution within the specified constraints. Do not rely on this to omit required dependencies.

**Exercise 7 — Failed initialization**

A static initializer throws IllegalStateException the first time. What can the first and subsequent errors be?

**Answer:** Usually **ExceptionInInitializerError** the first time; the class transitions to erroneous, and subsequent active uses usually receive **NoClassDefFoundError**; the initializer is not re-run.

**Exercise 8 — Nested class**

Outer has been initialized. Is the static nested class **Outer.Helper** definitely initialized too?

**Answer:** No. A nested member class has its own runtime class; nested declaration does not mean sharing the same initialization lifecycle.

**Exercise 9 — Constructor vs <clinit>**

A program creates two C objects in a row. How many times do a static block and the constructor run?

**Answer:** If C is newly initialized and both creations succeed, the static block runs **once**, and the constructor runs **twice**.

**Exercise 10 — Loader identity**

Two different class loaders define two classes with the same name **example.Counter**. Are their static initializers/state shared?

**Answer:** No. These are two distinct runtime classes; each has its own initialization and static storage.

**Exercise 11 — Checking the error**

The runtime library version removed a method, but the caller was built against the old version. Which phase group does this error usually belong to?

**Answer:** The **linking/resolution** group, which can manifest as **NoSuchMethodError** when the reference needs to be resolved/used.

**Exercise 12 — Mandatory schedule**

At the moment a class's <clinit> starts running, must the JVM have already verified/prepared that class? Must every reference already be resolved?

**Answer:** **Already verified and prepared**, but **not required to have resolved every symbolic reference**.

## 19. Checklist for Troubleshooting and Application Design

1. **Identify the actual class:** binary name + defining loader + module, avoiding confusion between two classes with the same name in plugins/application servers.
2. **Separate the questions:** “loaded?”, “verified/prepared?”, “which symbolic references resolved?”, “initialized?”.
3. **Use the right API:** forName(name,false,loader) for lookup without requesting initialization; forName(name,true,loader) when initialization is genuinely desired.
4. **Check active use:** new, static read/write, static invoke, reflection, and compile-time constant exceptions.
5. **Trace <clinit> order:** static fields/static blocks in textual order, superclass, and default-method superinterfaces when applicable.
6. **Diagnose the cause:** ClassFormatError, VerifyError, NoSuchMethodError, ExceptionInInitializerError, and NoClassDefFoundError are distinct signals.
7. **Avoid heavy static init:** minimize I/O, network connections, thread creation, dynamic loading, or failure-prone dependencies in static initializers; if needed, design initialization with clear error reporting and thorough tests.
8. **Do not rely on lazy resolution:** required dependencies must be packaged completely; optional dependencies need explicit contracts and handling.
9. **Use javap and runtime logging purposefully:** read Code/constant pool and combine with actual traces rather than inferring from source/stack trace alone.
10. **Be careful with concurrency:** mutable static state after initialization still requires appropriate synchronization/happens-before.
11. **Test in the right environment:** JDK version, --release, module path, classpath, container/IDE loaders, and library versions.
12. **Code with side effects:** if changing initialization timing via reflection, instrumentation, or lazy holder, preserve observable order and user contracts.

### Official Documentation

- **JVMS Java SE 17, §5.3 — Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17, §5.4 — Linking (Verification, Preparation, Resolution):** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS Java SE 17, §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17, §12.2–12.3 — Loading, Linking:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **JLS Java SE 17, §12.4 — Initialization and active use:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- **Java 17 API, Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API, ClassLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

**Core takeaway:** **Loading** creates the runtime class; **Linking** verifies, prepares static storage, and resolves symbolic references as needed; **Initialization** executes the class's initialization code according to active uses and specified ordering. **Having a Class object does not mean <clinit> has run**; **starting <clinit> does not mean every reference has been resolved**. When diagnosing errors, identify the right phase, the right runtime class, and the exact operation that triggered that use of the class.
