# JVM Startup, Initial Class Initialization, and Calling main by Java Version

## 1. The Big Picture

When running the command `java ...`, **the JVM does not jump straight into the first line of `main`**. The Java launcher determines the program to run, sets up the JVM and the runtime environment; the VM loads, links, and initializes the initial class/interface before invoking a valid `main` method. Although `main` is the logical starting point of the application, several JDK classes and necessary `static initializer`s may execute before it.

~~~text
Shell / OS
   |
   | java [VM options] <main-class | -jar JAR | -m module[/class] | File.java> [app args]
   v
Java launcher: chooses launch mode, prepares JVM and environment
   |
   v
Determine initial class / interface
   |
   v
Load class -> Link (Verify + Prepare + Resolve when needed)
   |
   v
Initialize initial class (and required superclasses / superinterfaces)
   |   execute static field initializers, static blocks
   v
Select candidate main by Java version
   |
   +---- static main ------> invoke directly
   |
   +---- instance main ---> create object with no-arg constructor
   |                         then invoke main on the object
   v
Application runs; other classes may be loaded/initialized when needed
~~~

In the diagram, **initial class** means the application type chosen as the entry point, **not the first class loaded by the JVM across the entire process lifetime**. The JVM may have already loaded, linked, or initialized many platform classes before the application is invoked. How the initial class is selected can differ across class path, JAR, module, source-file launcher, and even embedded JVM environments.

The lesson needs to distinguish three operations:

- **Loading:** finding/defining the runtime representation of a class or interface.
- **Linking:** verifying bytecode, preparing static state memory, resolving symbolic references according to JVM rules.
- **Initialization:** running `static` initializer expressions and `static { ... }`, which may trigger initialization of related classes.

Loading or linking **does not automatically mean** that `static initializer`s have run.

## 2. Who Selects the Initial Class?

According to **JLS `12.1** and **JVMS `5.2**, the JVM starts program execution by using an **initial class or interface** and invoking the corresponding `main`. How the initial class is determined is the responsibility of the launch environment, most commonly the `java` tool from the JDK.

| Launch mode | Example | How the application is selected |
| --- | --- | --- |
| Class path | `java -cp out demo.App alpha beta` | Binary name of the class `demo.App` |
| Executable JAR | `java -jar app.jar alpha` | `Main-Class` in the JAR's manifest |
| Named module | `java -m demo.app/demo.App alpha` | Main class selected in the module; can use the main class recorded in the module if `/demo.App` is omitted |
| Source-file mode, Java 11+ | `java App.java alpha` | Launcher compiles the source then selects the entry class from the source file |
| Compact source, Java 25+ | `java Hello.java` with `void main() { ... }` | Compiler generates an implicit class for the JVM to invoke `main` |

On the class path:

~~~bash
java -Xmx256m -Dapp.mode=test -cp out demo.App first second
~~~

`-Xmx256m` is a VM option, `-Dapp.mode=test` is a system property, `-cp out` is the class search path, and `demo.App` is the initial class. The two tokens `first`, `second` appearing **after the class name** are application arguments: `args[0]` and `args[1]` if the `main(String[])` method is invoked. `-Xmx256m` placed after `demo.App` will be interpreted as an application argument, no longer a VM startup option.

The source-file launcher (`java App.java`) **compiles the Java source during startup and then runs the resulting class**, which does not mean the JVM directly interprets `.java` source text. Whereas when running a compiled class (`java App`), the JVM obtains the appropriate bytecode from the class path/module path.

## 3. Loading, Linking, and Initializing the Initial Class

### Loading: Finding and Defining the Class

The runtime can load a class from a JAR, module, `.class` file, compiler-generated source, or a custom class loader. The identity of a runtime class is based on its **binary name and defining class loader**; therefore, two different loaders can define two classes with the same name that are two distinct runtime classes.

Loading only sets the stage for subsequent steps; it is not enough to assert that `static { System.out.println("loaded"); }` has run. A class name not found, a corrupted class file, or a class file version unsupported by the VM can cause startup to fail at this stage or related stages.

### Linking: Verify, Prepare, Resolve

- **Verify:** the class file/bytecode satisfies the virtual machine's format and validity rules.
- **Prepare:** allocates and assigns **default values** to `static` variables (`0`, `false`, `null`…), handling compile-time constants according to the specification. Do not misunderstand "prepare" as having executed all field declaration expressions.
- **Resolve:** maps symbolic references (symbolic indices/names in the constant pool) to concrete runtime references. The runtime may do this eagerly or lazily; **not all references are necessarily resolved before `main`**.

Example:

~~~java
static int count = calculate();
~~~

During prepare, `count` has the default value of `int`. The expression `calculate()` only runs at the time the class **initializes** (during initialization according to Java rules), not because loading has just completed.

### Initialization: Before main and Ordered

For ordinary classes, the main rules are:

1. Initialize required **superclass**es before the subclass. Certain superinterfaces declaring default methods may also need to be initialized according to JLS `12.4` rules.
2. Execute static field initializers and static initialization blocks of the class **in source text order**.
3. For each runtime class identity, successful initialization is not run again merely because of additional method calls or creating new objects.
4. The VM synchronizes the initialization process when multiple threads attempt to use a class for the first time. Threads may wait instead of concurrently running `static` initialization twice.

The compiler may generate a special method `<clinit>` in the class file to execute class initialization logic. `<clinit>` is **different from** `<init>` (constructor/object initialization) and **different from** `main` (the application entry-point method).

Not every class on the class path must be initialized before `main`. Unused classes may remain uninitialized; another class may be initialized before/after `main` due to active use such as `new`, calling a `static` method, or reading a `static` field that is not a compile-time constant.

## 4. By Java Version, What Is a Valid main?

### Java 8–20: Traditional Signature

The pattern widely accepted in older Java releases:

~~~java
public class TraditionalMain {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
~~~

`String... args` can be written instead of `String[] args` because varargs has the array type `String[]`. The parameter name `args` can be changed. The traditional signature requires **`public static`**, returning **`void`**, and **one `String[]` parameter**. `int main`, `main(int[])`, or `static void main()` are not traditional entry points.

The pattern above is still accepted in Java 25+, and should be used in applications that want broad support across different JDKs or build tools.

### Java 21–24: The Previews

Java began experimenting with shorter ways to write the `main` entry and simpler source files:

| Version | Status | JEP |
| --- | --- | --- |
| Java 21 | First preview | JEP 445 |
| Java 22 | Second preview | JEP 463 |
| Java 23 | Third preview | JEP 477 |
| Java 24 | Fourth preview | JEP 495 |
| **Java 25+** | **Stable, no need to enable preview for this feature** | **JEP 512** |

With preview versions 21–24, it is necessary to check the exact syntax of that version, usually compiling with `--enable-preview --release N` or `--enable-preview --source N` and running the preview bytecode with `--enable-preview` on the corresponding runtime. Do not assume that every preview syntax variant is identical to the stable Java 25 release.

### Java 25+: Expanded main Candidates

According to **JLS `12.1.4, Java SE 25 and later**, a `main` candidate declared or inherited in the initial class/interface must return `void`, be named `main`, have `public` / `protected` / package access (**not `private`**), and take **one `String[]` or `String...`**, or **no parameters**. A candidate may be a **`static` or instance method**, and may have `throws`.

Examples of standalone signatures that can serve as valid entry points:

~~~java
public static void main(String[] args) { } // traditional
static void main(String[] args) { }        // package access
protected static void main() { }           // no parameters
void main() { }                            // instance method
public void main(String... args) { }       // instance + varargs
~~~

This is an **illustrative set of signatures**, not a standalone runnable Java file: when combining multiple signatures into the same class, overloading and `main` selection rules must be considered.

**Priority rule:** if there is a `main(String[])` candidate, the runtime selects the version taking `String[]`. Only when there is no such candidate is the parameterless `main()` selected. Therefore, an **instance `main(String[])` can be chosen instead of `static main()`**; `static` is not a higher-priority criterion than parameters. In the same class, a static and an instance method with the **same signature** cannot coexist.

If the selected method is an instance `main`, the VM creates an instance of the initial class using a no-arg constructor according to the corresponding rules, and only then invokes the method. Class initialization still **comes first**; the constructor and instance field/block initializers run **before** the body of the instance `main`. If a valid instance cannot be created, startup fails before the method runs.

## 5. Java 17+ Example: Static Initialization Before main

Create the file `BootOrder.java`:

~~~java
class Parent {
    static int parentValue = mark("1. Parent static field");

    static {
        System.out.println("2. Parent static block");
    }

    static int mark(String message) {
        System.out.println(message);
        return 1;
    }
}

public class BootOrder extends Parent {
    static int childValue = mark("3. Child static field");

    static {
        System.out.println("4. Child static block");
    }

    {
        System.out.println("6. Instance initializer");
    }

    BootOrder() {
        System.out.println("7. Constructor");
    }

    public static void main(String[] args) {
        System.out.println("5. main args = " + String.join(",", args));
        new BootOrder();
    }
}
~~~

Compile/run commands:

~~~bash
javac BootOrder.java
java BootOrder A B
~~~

**Exact stdout:**

~~~text
1. Parent static field
2. Parent static block
3. Child static field
4. Child static block
5. main args = A,B
6. Instance initializer
7. Constructor
~~~

**Explanation:** To invoke `BootOrder.main`, the VM initializes `BootOrder`. It must initialize `Parent` first, so milestones 1–2 appear before 3–4. After that, it invokes `static main`, printing milestone 5. No `BootOrder` instance is needed to invoke static main; it is the `new BootOrder()` statement inside main that causes milestones 6–7.

If `new BootOrder()` is removed, the last two lines disappear. This result clearly distinguishes:

- Class initialization: `static` initializers run before `main`.
- Object initialization: instance initializers and constructor run on `new`, **not by default** before a `static main`.
- The order above only describes the printed markers of the user-written classes. It does not list every internal class that the JVM/JDK has initialized.

Inspecting bytecode:

~~~bash
javap -p -c BootOrder
javap -p -c Parent
~~~

`javap` helps you identify class initialization code (shown corresponding to `static {}`/`<clinit>`), constructor code, and `main`. Do not assume bytecode offsets/constant-pool indexes are identical across all compiler versions.

## 6. Java 17+ Example: Loading Is Not Initializing

Create the file `LazyInit.java`:

~~~java
class Configuration {
    static final String LABEL = "constant";

    static int PORT = initPort();

    static {
        System.out.println("Configuration static block");
    }

    static int initPort() {
        System.out.println("Configuration initPort");
        return 8080;
    }
}

public class LazyInit {
    public static void main(String[] args) {
        System.out.println("Before: " + Configuration.LABEL);
        System.out.println("Port: " + Configuration.PORT);
    }
}
~~~

~~~bash
javac LazyInit.java
java LazyInit
~~~

**Exact stdout:**

~~~text
Before: constant
Configuration initPort
Configuration static block
Port: 8080
~~~

`Configuration.LABEL` is a **constant variable** with a literal value, which can be inlined by the compiler so referencing this constant does not force the `Configuration` class to initialize. When reading `Configuration.PORT` (a static field that is not a constant variable), the VM initializes the class: calls `initPort()`, runs the `static block`, and then prints the value 8080.

Do not apply the conclusion above to every `static final`. `static final String V = System.getenv("X")` is not a compile-time constant, so the first active use of the field can trigger initialization. Similarly, `Configuration.class` only obtains the class literal, and does not itself imply that static initializers have run.

## 7. Java 25+ Example: Instance main and Compact Source

### A. Instance main Forces Object Creation

Create `InstanceEntry.java` with **JDK 25+**:

~~~java
class InstanceEntry {
    static {
        System.out.println("1. static init");
    }

    {
        System.out.println("2. instance init");
    }

    InstanceEntry() {
        System.out.println("3. constructor");
    }

    void main() {
        System.out.println("4. instance main");
    }
}
~~~

~~~bash
javac InstanceEntry.java
java InstanceEntry
~~~

**Stdout:**

~~~text
1. static init
2. instance init
3. constructor
4. instance main
~~~

Here the runtime initializes the class first (milestone 1), **creates an object** with the no-arg constructor (milestones 2–3), and finally invokes instance `main()` (milestone 4). One should not phrase it as "the JVM always calls the constructor before `main`": that conclusion is **only true when the selected entry is an instance main**.

### B. main Taking String[] Beats Parameterless main

Create `MainChoice.java` on JDK 25+:

~~~java
class MainChoice {
    static void main() {
        System.out.println("static no-arg main");
    }

    void main(String[] args) {
        System.out.println("instance args main: " + String.join(",", args));
    }
}
~~~

~~~bash
javac MainChoice.java
java MainChoice x y
~~~

**Stdout:**

~~~text
instance args main: x,y
~~~

The runtime selects `main(String[])` even though that method is an instance method and even though `static main()` exists: **the form with parameters takes precedence**. The runtime creates an instance using the default no-arg constructor; the example does not print a constructor trace. If `main(String[])` is deleted, `static main()` becomes the entry point.

### C. Compact Source File: Short Java Source, VM Still Runs a Class

Create `Hello.java` (Java 25+):

~~~java
void main() {
    System.out.println("Hello from compact source");
}
~~~

~~~bash
java Hello.java
~~~

**Stdout:**

~~~text
Hello from compact source
~~~

The compiler generates an **implicitly declared class** wrapping `main`, the source-file launcher compiles it, and the VM executes that class. Java 25 brought this syntax out of preview (JEP 512). `--enable-preview` is not needed for this specific feature on JDK 25+. Java 21–24 had preview versions that need to be checked depending on the release.

## 8. Initialization Errors and the Difference Between Class and Object

If the static initializer of the **initial class** throws an exception, the program may stop **before entering the body of `main`**. If a secondary class is first used inside main and then fails, main has already started, but that active use operation fails. According to JLS `12.4.2, an initialization failure caused by an ordinary exception may be wrapped into an `ExceptionInInitializerError`; the runtime class enters an erroneous state and subsequent accesses usually receive `NoClassDefFoundError`.

Create the file `InitFailure.java`:

~~~java
class BrokenConfig {
    static int VALUE = fail();

    static int fail() {
        throw new IllegalStateException("bad configuration");
    }
}

public class InitFailure {
    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            try {
                System.out.println(BrokenConfig.VALUE);
            } catch (LinkageError error) {
                System.out.println(i + ": " + error.getClass().getSimpleName());
            }
        }
    }
}
~~~

~~~bash
javac InitFailure.java
java InitFailure
~~~

**Stdout:**

~~~text
1: ExceptionInInitializerError
2: NoClassDefFoundError
~~~

Because `BrokenConfig` is not the initial class, `InitFailure.main` was able to run and actively accessed `BrokenConfig.VALUE`. The first access caused `<clinit>` to fail; the second attempt tried to use a class already in an erroneous state. If the error were in the static initializer of `InitFailure`, `InitFailure.main` itself might not have run yet.

In concurrent applications, threads do not arbitrarily initialize the same runtime class independently twice: the VM manages initialization synchronization and initialization state. However, the same class name loaded by **different defining class loaders** can be different runtime classes, with separate static state.

## 9. Diagnosing Startup by Root Cause

| Symptom | Question to ask | Check |
| --- | --- | --- |
| `Could not find or load main class` | Are the full class name, package, class path/module path correct? | `java -cp ... fully.qualified.MainClass` and JAR content |
| `Main method not found` | Is the signature valid on the running JDK? | `java -version`; use the `public static void main(String[])` pattern if backward compatibility is needed |
| `UnsupportedClassVersionError` | Was the bytecode compiled for a newer release than the runtime? | `javap -verbose ClassName` to view the class major version; consider `javac --release` |
| `ExceptionInInitializerError` | Which static initializer/field initializer threw an exception? | Check `Caused by` and the initial stack trace; look for `<clinit>` |
| `NoClassDefFoundError` after a static error | Is the class already in an erroneous state? | Trace back to the first initialization failure, class loader, and dependencies |
| `constructor runs before main` | Is the entry an instance main on Java 25+? | Compare the selected signature and `new` in the application |
| Two mains coexist | Is `main(String[])` or `main()` prioritized? | Java 25+: `main(String[])` takes priority; see JLS `12.1.4` |
| Static block does not run | Is this just a class literal/compile-time constant? | Check active use instead of inferring from loading |

Commands to check version and bytecode:

~~~bash
java -version
javac -version
javap -p -c BootOrder
javap -verbose BootOrder
java -Xlog:class+load=info BootOrder
~~~

`-Xlog:class+load=info` illustrates **HotSpot** unified logging on modern JDKs. The log lines indicate classes being loaded, **not proof that each class's static initializer has also run**. The output can be very long and build-dependent; check `java -Xlog:help` before applying it on a specific VM/version. In cases where an error only occurs at runtime, record both `java -version` and `javac -version` because using a different JDK for compilation than for runtime is a common source of errors.

Do not forget the lifecycle boundary: `main` returning **does not always mean the process terminates immediately**. Remaining non-daemon threads can keep the JVM alive, and shutdown hooks can execute when the JVM shuts down. This is a phase after `main` has already been entered.

## 10. Common Misconceptions

1. **"The class containing `main` is definitely the first class the VM loads."** False. The initial class is the application entry point; the VM may have already processed runtime classes.
2. **"Class loaded means the static block has run."** False. Loading is different from initialization; linking resolution can also be deferred.
3. **"Prepare has already run `static int x = f()`."** False. Preparation sets default values; initialization is what calls `f()`.
4. **"Every time a static method is called, the static block runs again."** False once the class has initialized successfully within the same runtime identity.
5. **"Every application class is initialized before main."** False. Many classes only initialize upon active use.
6. **"`main` must always be `public static void main(String[])`."** This is the traditional and broadly compatible pattern, but Java 25+ has other entry forms.
7. **"Java 17 runs `void main()` like Java 25."** False for standard entry points: the expanded capability was preview in 21–24 and stable from 25.
8. **"The constructor always runs before main."** Only happens when the runtime must create an object for an **instance main**, or the program itself creates an object before calling a method.
9. **"Compact source means the JVM reads Java source directly."** False. The launcher compiles it into a class and the JVM runs bytecode.
10. **"When main finishes, the process must close immediately."** False if non-daemon threads remain or shutdown processing continues.

## 11. Self-Check

**1. Why does `Parent`'s static block run before `BootOrder`?**  
Because superclass initialization must take place before subclass initialization.

**2. What is the difference between `<clinit>` and `<init>`?**  
`<clinit>` represents class initialization logic; `<init>` is the constructor for an object. A static main by itself does not create an instance of the initial class.

**3. Can Java 17 run `class App { void main() {} }` with `java App`?**  
No, under traditional main entry rules. It requires `public static void main(String[] args)` or the equivalent varargs variant.

**4. In Java 25+, between `static void main()` and `void main(String[] args)`, which is chosen?**  
`void main(String[] args)` is chosen; the runtime creates an object to invoke the instance method.

**5. Does referencing `static final String LABEL = "x"` always cause the class to be initialized?**  
No. A constant variable with a constant expression initializer can be inlined and does not trigger class initialization when read.

**6. If an error occurs in the initial class's static initializer, is it possible that main has never run?**  
Yes. The JVM must initialize the initial class successfully before invoking main.

## 12. References

- [JLS Java SE 25, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): startup, initializing the initial class, `main` entry, initialization triggers, and errors.
- [JLS Java SE 26, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html): updated rules on candidate main and class initialization.
- [Java Language Changes by Release, Java 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): the preview series JEP 445/463/477/495 and the stable version JEP 512 in Java 25.
- [Oracle Java 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): documentation for the stable feature.
- [Oracle Java 24 — Simple Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/24/language/simple-source-files-and-instance-main-methods.html): documentation for the preview status in JDK 24.
- [Oracle Java 25 — java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): syntax for class path, JAR, module, source-file mode, and option classification. For expanded `main` signatures, prefer the JLS `12.1.4` text of the corresponding release.
- [Java SE Specifications](https://docs.oracle.com/javase/specs/): choose the **JVMS Chapter 5** version matching the release to read the standard on loading/linking/initializing.

**Remember:** The JVM prepares the environment and initial class **before** invoking `main`; `static` blocks can run before the body of `main`, while constructors only run when an object is needed. When encountering a "does not enter main" error, check **launch mode, class path/module path, class-file version, static initialization, and the main signature for the JDK in use**.
