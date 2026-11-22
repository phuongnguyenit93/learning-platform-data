# Distinguishing Class Loading, Linking, and Initialization in Java

## 1. Goal and Big Picture

When the JVM uses a class, three distinct concepts are often lumped together as "loading a class," even though they perform three different jobs:

1. **Loading:** finding or creating a representation of a class or interface in the JVM from its name and definition.
2. **Linking:** verifying validity, preparing static state, and resolving symbolic references so the class can be used safely.
3. **Initialization:** executing the initialization logic for static variables and static blocks of the class or interface at the time specified by Java.

A quick mental model:

~~~text
.java source code
  │ javac (compiled before execution)
  ▼
.class bytecode
  │
  ▼
LOADING
  ├─ Locate bytecode / class definition
  ├─ Create runtime representation and java.lang.Class object
  └─ Identify class via (binary name, defining class loader)
  │
  ▼
LINKING
  ├─ Verification: check bytecode and safety constraints
  ├─ Preparation: allocate/assign initial default values for static fields
  └─ Resolution: convert symbolic references to runtime entities
  │
  ▼
INITIALIZATION
  ├─ Initialize prerequisite classes/interfaces per JVM rules
  └─ Run the class's own static initialization code (if any)
  │
  ▼
Use the class: create instances, invoke methods, read/write state...
~~~

**Key takeaway:** a loaded class is not necessarily an initialized class; a class may already be linked while its static blocks have not yet run. The JVM is permitted to resolve many symbolic references **lazily**, so you should not assume that all resolution work finishes as soon as the class is first encountered.

## 2. What Does Loading Actually Do?

The JVM needs a runtime definition for a referenced type. For developer-declared classes, it typically uses a **class loader** to locate the bytecode and create the class definition. A class loader can obtain bytecode from the classpath, modules, JARs, the network, or a custom source depending on application design. The delegation mechanism usually gives the parent loader a chance to handle the request first; custom loaders may follow different policies.

The result is a **java.lang.Class** object representing the type. The JVM uses **(binary name + defining class loader)** to distinguish class definitions: two different loaders can create two distinct classes even with the same fully qualified name. Therefore, in plugin or container environments, two classes with the same name are not necessarily castable to one another.

Loading **does not run** static blocks, does not invoke constructors, and does not create instances of the class on its own. Arrays follow separate array-class creation rules handled by the JVM; creating an array with element type `Foo` does not mean `Foo` is initialized.

Distinguish between calling a loader operation and what the JVM may perform internally: **ClassLoader.loadClass("pkg.Foo")**, under its normal contract, returns a `Class` without actively initializing `Foo`; whether the JVM loads or links related types may happen as needed. Do not use class-loading logs to infer that static logic has already executed.

## 3. Linking: Three Activities with Distinct Responsibilities

| Activity | Meaning | What Must Not Be Inferred |
| --- | --- | --- |
| **Verification** | Checks the structure and validity of bytecode and type constraints; may throw `VerifyError` when the definition is invalid. | It is not the step that executes static methods or constructors. |
| **Preparation** | Prepares storage for static fields and sets their default values; for eligible constant variables, values from `ConstantValue` may be set during this step. | It does not execute arbitrary static initialization expressions from the program. |
| **Resolution** | Turns symbolic references in the constant pool into their corresponding runtime references (classes, fields, methods, etc.); checks accessibility and constraints as needed. | It does not necessarily resolve everything at once or at a single fixed point in time. |

For example, consider the declarations:

~~~java
class Sample {
    static int counter = 42;
    static final int LIMIT = 10;
    static final String LABEL = "ready";
    static final Object TOKEN = new Object();
}
~~~

During **preparation**, static fields receive their default state: a normal `int` starts at `0`, and an `Object` reference defaults to `null`. The two **constant variables** `LIMIT` and `LABEL` have constant expression values, are represented via `ConstantValue`, and can be set according to preparation rules. By contrast, **counter = 42** and **new Object()** belong to initialization: they are not executed simply because the class has finished preparation.

Do not treat the table above as a checklist of events fully observable in logs. The Java Virtual Machine Specification allows **resolution to happen lazily**, even only when a reference is actually used. Errors such as `NoSuchMethodError` or `IllegalAccessError` may reflect a reference being resolved at runtime, not necessarily when the JVM first loads the class.

## 4. Initialization: When Static Code Actually Runs

Initialization is the phase in which the JVM executes the special class initialization method **<clinit>** (if generated by the compiler) built from static field initializers and static initializer blocks, in **source-code order**. This is not an object constructor. A constructor runs each time an appropriate instance is created; successful initialization of a class definition normally occurs **once in the lifetime of the corresponding Class**.

Before initializing a class, the JVM ensures the initialization of its required superclass and eligible superinterfaces (notably superinterfaces that declare `default` methods). Initializing an interface does not automatically initialize all of its superinterfaces. Ordering and thread synchronization are controlled by the JVM: another thread needing to use the class may have to wait for an ongoing initialization to complete. If initialization fails, the class can be marked in an erroneous state and subsequent uses will fail with related errors.

**Note on values during static initialization:** static fields already hold default values from preparation. If a static initializer calls a method that reads a field assigned later in the source code, that method can observe the default value (for example, `0`) rather than the final value. Do not equate allocating default values with executing assignment statements.

## 5. When Does an Operation Trigger Class Initialization?

Under the conditions of the Java Language Specification, the following typical **active use** actions trigger initialization of the corresponding class if it has not already been initialized:

| Operation | Initializes Target Class? | Explanation |
| --- | --- | --- |
| Creating an object with **new Foo()** | **Yes** | `Foo` must be initialized before creating an instance. |
| Reading/writing **Foo.staticField** that is not a constant variable | **Yes** | Initializes the **class that actually declares the field**, not necessarily the class name written to the left of the dot. |
| Calling **Foo.staticMethod()** | **Yes** | The class declaring the static method is initialized before the call. |
| **Class.forName("pkg.Foo")** | **Yes, by default** | The single-argument form requests loading, linking, and initializing the found type. |
| **Class.forName(name, false, loader)** | **Does not actively initialize** | Useful for obtaining the `Class` while deferring initialization. |
| **loader.loadClass(name)** | **Does not actively initialize** | Returns the `Class` per the method's contract; the class may be linked. |
| **Foo.class** | **No** | A class literal is not an active use that runs static blocks. |
| **new Foo[3]** | **Does not initialize Foo** | Creates the array class/object; no `Foo` instance is created. |
| Reading **Foo.CONSTANT** for a compile-time constant primitive/`String` | **Usually no** | The compiler may inline the constant directly into the caller's bytecode, emitting no `getstatic`. |
| Accessing a **static final** field initialized by a method call or object creation | **Yes, when the field is read directly** | `final` does not mean compile-time constant. |

For example, `Parent.X`—when `X` is actually declared in `Parent` and accessed via `Child`—initializes **Parent**, and does not automatically initialize `Child`. Interfaces have their own initialization rules: invoking a static method or reading a non-constant static field of an interface can also trigger initialization of that interface.

With reflection, merely obtaining a `Class` object or inspecting metadata does not imply that static initializers have run; operations such as reading a static field or invoking a static method via reflection can trigger initialization. Similarly, `MethodHandle` mechanisms, JVM startup, or special APIs have their own rules: the table above covers **the core cases**, not an exhaustive list of every trigger in the specification.

## 6. Runnable Example: Proving "Having a Class" Differs from "Static Code Has Run"

Create the file **LoadLinkInitDemo.java**:

~~~java
public class LoadLinkInitDemo {
    static class Target {
        static final int COMPILE_TIME_CONST = 7;

        static int value = initValue();

        static {
            System.out.println("Target: static block");
        }

        static int initValue() {
            System.out.println("Target: init value");
            return 42;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("1. constant = " + Target.COMPILE_TIME_CONST);

        Class<?> type = Target.class;
        System.out.println("2. class literal = " + type.getSimpleName());

        Class.forName(type.getName(), false, type.getClassLoader());
        System.out.println("3. forName(false) completed");

        System.out.println("4. value = " + Target.value);
        System.out.println("5. value again = " + Target.value);
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac LoadLinkInitDemo.java
java LoadLinkInitDemo
~~~

Expected stdout of the program:

~~~text
1. constant = 7
2. class literal = Target
3. forName(false) completed
Target: init value
Target: static block
4. value = 42
5. value again = 42
~~~

Step-by-step explanation:

1. **COMPILE_TIME_CONST** is a constant variable: the compiler can inline the value `7` into the caller, so `Target` does not need initialization yet.
2. **Target.class** obtains/creates the `Class` object without initializing `Target`. The class may have been loaded, and the JVM may have performed some linking work, but no static output is printed.
3. **Class.forName(..., false, ...)** requests the `Class`, while the `false` argument prevents initialization per the API call. You must not conclude at this point that all resolution for `Target` is complete.
4. The first access to **Target.value** is an active use: before printing `"4. value"`, the JVM executes **initValue()**, then the static block in source order. The read then returns `42`.
5. The subsequent read **does not re-run** the static block: the same class definition has already been successfully initialized.

This demonstrates **initialization**, not a precise measurement of when verification or resolution occurs. From stdout alone, you cannot reconstruct the entire linking lifecycle.

## 7. Second Example: Superclass Order and Initialization Count

Create **InitOrderDemo.java**:

~~~java
public class InitOrderDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        new Child();
        new Child();
    }
}
~~~

~~~bash
javac InitOrderDemo.java
java InitOrderDemo
~~~

Stdout:

~~~text
Parent initialized
Child initialized
~~~

The superclass is initialized before `Child`; the two `new` expressions create **two objects** but do not run the static initializers twice. If there were a constructor printing to stdout, the constructor would run for each object, unlike the two lines above.

## 8. Which Phase Do Common Errors Belong To?

| Symptom or Error | Appropriate Interpretation |
| --- | --- |
| **ClassNotFoundException** when calling `Class.forName`/`loadClass` | The loader was asked to find a class by name and could not find/load it; this is typically a checked exception from class-lookup APIs. |
| **NoClassDefFoundError** | The JVM cannot obtain the needed class definition at link/execution time, or the class entered an erroneous state after a failed initialization; not strictly synonymous with `ClassNotFoundException`. |
| **VerifyError** | Bytecode violates verification rules; belongs to linking/verification issues. |
| **NoSuchMethodError / NoSuchFieldError / IllegalAccessError** | A binary/API/access mismatch surfaced when a reference was resolved or used; inspect dependencies, classpath, and loaders. |
| **ExceptionInInitializerError** | Initialization threw a non-`Error` exception out of static initialization logic; the JVM wraps the original exception in this error. |
| **Exception or Error in <clinit>** | Not every initialization failure is wrapped the same way: an `Error` may be thrown directly; subsequent uses of the class may receive `NoClassDefFoundError`. |

An error occurring "at application startup" is **not enough** to determine whether it belongs to loading, linking, or initialization. Inspect the **Throwable type, cause chain, and stack trace**, identify which class the JVM requested, which dependencies are on the runtime classpath, and which class **defines** the field/method being used.

For example, a static initializer that depends on environment configuration that is not yet ready can prevent the entire class from initializing. Moving fallible tasks (network connections, reading secrets, I/O) out of static initializers generally makes startup clearer and makes errors easier to handle and retry.

## 9. How to Analyze a Real-World Situation

When you see "the class loaded, but the print inside the static block didn't run," check in order:

1. **What was the exact operation?** Did it only call `loadClass`, take `Foo.class`, or inspect metadata, or did it actually use `new`/`getstatic`/`invokestatic`?
2. **Is the field a constant variable?** A `static final` primitive or `String` with a constant expression can be inlined by the compiler. Inspect the caller's bytecode with **javap -c** if needed.
3. **Which class actually declares the member?** Accessing an inherited static field through a subclass name does not initialize the subclass just because the syntax uses the subclass name.
4. **Which loader defined the class?** In plugin servers, multiple loaders can create `Class` objects with the same name. Check **type.getClassLoader()** and the actual module/classpath.
5. **Was there an earlier initialization error?** Look for the first exception and its root cause; a later `NoClassDefFoundError` may just be a downstream symptom.
6. **Do not judge resolution from a single milestone.** The JVM is allowed to resolve symbolic references on demand during execution.

You can use **javap -c LoadLinkInitDemo** to observe different bytecode instructions (such as an inlined constant versus **getstatic**); with HotSpot on modern Java, **java -Xlog:class+load=info LoadLinkInitDemo** helps observe class-loading events. Class-loading logs do not directly prove when initialization occurred: to see that, use controlled output from static initializers as in the example. Depending on the VM/version, check available logging tags with **java -Xlog:help**.

## 10. Misconceptions to Avoid

- **"Loading a class runs its static block."** False. Loading creates the runtime definition; static blocks belong to initialization.
- **"Linking is just bytecode checking."** Incomplete. Linking consists of verification, preparation, and resolution.
- **"Static fields get their coded assignment values during preparation."** False for ordinary initialization expressions: preparation sets default values; assignment code runs during initialization. `ConstantValue` is the case to distinguish.
- **"`final` means compile-time constant."** False. **static final Object TOKEN = new Object()** and **static final int N = calculate()** are not constant variables.
- **"Using a class literal definitely runs `<clinit>`."** False. **Foo.class** is not an active use that triggers initialization.
- **"`Class.forName` always only loads."** False. The single-argument form normally initializes the class; the overload with the `initialize` flag controls this behavior.
- **"A class is initialized exactly once by name."** Missing a condition: the same name can be defined by different loaders, and each **Class** has its own initialization state.
- **"Seeing an error at program start means it's a loading error."** False. Linking and initialization can also fail early, and lazy resolution can fail later.

## 11. Self-Check Questions

**Q1.** If class `A` has a static block, does `Class<?> x = A.class;` guarantee that the static block has run?

**Answer:** No. Obtaining a class literal does not actively trigger initialization.

**Q2.** If `static final int MAX = 100;`, why might printing `A.MAX` not run `A`'s static block?

**Answer:** `MAX` is a constant variable with a compile-time constant expression. The caller can embed the value `100` directly without accessing the static field at runtime.

**Q3.** If a class has been loaded and prepared, can there still be unresolved symbolic references?

**Answer:** Yes. Resolution can be performed lazily when a reference is needed.

**Q4.** Two plugin loaders each define their own `example.Task`. Why can both run `Task`'s static initializer logic?

**Answer:** They are two distinct runtime definitions because their defining loaders differ; initialization is tracked per `Class`.

**Q5.** Code accesses a static field and gets `ExceptionInInitializerError` the first time, then `NoClassDefFoundError` on subsequent attempts. Which error should you investigate first?

**Answer:** Investigate the exception/cause from the initial failed initialization. On later attempts, the class may already be in an erroneous state, making `NoClassDefFoundError` merely a symptom.

## 12. Key Takeaways

**Loading** answers: *Does the JVM have a definition for this type yet, and which loader defined it?*  
**Linking** answers: *Has that definition been verified/prepared, and how have required references been resolved?*  
**Initialization** answers: *When does static code execute, in what order, and did it succeed or fail?*

When debugging, separate these three questions. Do not deduce when static initializers ran merely from the fact that the JVM has recognized a `Class`, and do not assume all references must be resolved right at load time.

**Primary References:** Java Language Specification §12.2–12.4 (loading, linking, initialization) and Java Virtual Machine Specification §5.3–5.5 (creation/loading, linking, initialization), Java SE 21 edition:
- https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
- https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
