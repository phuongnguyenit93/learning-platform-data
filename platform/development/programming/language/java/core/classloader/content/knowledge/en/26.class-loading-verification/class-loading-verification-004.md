# Verifying Static Initializer Order and Initialization Errors

## 1. Objective

When learning Java ClassLoaders, it is necessary to distinguish **class loading** from **class initialization**. A ClassLoader can locate the bytecode and return a `Class<?>` while the class's `static` blocks have not yet run. Conversely, when the JVM begins class initialization, static field initializers, static blocks, and superclass relationships must follow a strict order.

This lesson provides a compilable Java 17+ program to verify:

- A class literal and `ClassLoader.loadClass` do not automatically trigger static initialization.
- `Class.forName(name, false, loader)` differs from `Class.forName(name, true, loader)`.
- With `new Derived()`, the superclass's static initializers run before the subclass's, and within each class they run in **the order they appear in the source**.
- `static final` compile-time constants can be inlined without initializing the class; a static field computed at runtime can trigger initialization.
- Static initialization throwing an exception can lead to `ExceptionInInitializerError` on the first attempt and `NoClassDefFoundError` on subsequent uses.
- One class failing initialization does not automatically break all classes in the JVM; initialization state is tied to the **runtime class**, including its defining loader.

## 2. Distinguishing When Loading, Linking, and Initializer Execution Occur

**Loading** creates/looks up the `Class<?>` definition, and **linking** consists of verification, preparation (where static fields receive default values), and resolution, which can occur lazily. Only **initialization** executes the static field initializers and static blocks that need to run. `ConstantValue` (if present) is assigned during initialization before `<clinit>`, not by `static {}` code in the source. This lesson measures **observable output order** and erroneous state using a program, rather than only looking at class-loading logs.

## 3. Static Initialization Ordering Rules

Example:

~~~java
// Illustrative code; mark(...) is a helper that prints a label and returns a number.
class Sample {
    static int a = mark("a", 1);

    static {
        System.out.println("block");
    }

    static int b = mark("b", 2);
}
~~~

When `Sample` is initialized, the output will be in this order:

~~~text
a
block
b
~~~

Static fields and blocks are executed **in textual order** within the class. There is no “all fields before all blocks” rule.

With inheritance:

~~~text
class Base
  static Base.field
  static Base.block

class Derived extends Base
  static Derived.field
  static Derived.block

new Derived():
  Base.field
  Base.block
  Derived.field
  Derived.block
  Base constructor
  Derived constructor
~~~

An uninitialized superclass is initialized before its subclass. Once the static initializers finish, object construction executes the superclass and subclass constructors.

**Exception to understand separately:** Interfaces have special rules; class initialization also involves certain superinterfaces that declare default methods. Do not use “every interface that a class implements is initialized before the class” as an absolute rule.

## 4. Conditions for Predicting the Output

`Derived.class`, `loader.loadClass(...)`, and `Class.forName(name,false,loader)` do not initialize the target class on their own. However, `new Derived()`, accessing a non-constant static field, calling a static method, and `Class.forName(name,true,loader)` require initialization if it has not yet completed. Reading a primitive/`String` `final` assigned a constant expression can be inlined by the compiler, so it does not run the marker. The previous lesson verified each overload in greater depth; here we will simultaneously track **field/block order, superclass, success, and failure**.

## 5. Self-Verifying Java 17+ Program

Create a single file **`InitializationLab.java`**:

~~~java
public final class InitializationLab {
    private InitializationLab() {
    }

    private static void log(String text) {
        System.out.println(text);
    }

    private static int mark(String label, int value) {
        log(label);
        return value;
    }

    private static int fail() {
        log("Broken.fail");
        throw new IllegalStateException("boom");
    }

    static class Base {
        static int first = mark("Base.field", 1);

        static {
            log("Base.block");
        }

        static int last = mark("Base.last", 2);

        Base() {
            log("Base.ctor");
        }
    }

    static final class Derived extends Base {
        static int first = mark("Derived.field", 3);

        static {
            log("Derived.block");
        }

        Derived() {
            log("Derived.ctor");
        }
    }

    static final class Probe {
        static {
            log("Probe.<clinit>");
        }
    }

    static final class OnlyLoaded {
        static {
            log("OnlyLoaded.<clinit>");
        }

        static String value() {
            return "LOADED";
        }
    }

    static final class Constants {
        static final int NUMBER = 42;
        static final String TEXT = "CONST";
        static final Integer BOXED = mark("Constants.<clinit>", 99);
    }

    static final class Broken {
        static int VALUE = fail();
    }

    static final class Healthy {
        static {
            log("Healthy.<clinit>");
        }

        static int VALUE = 7;
    }

    public static void main(String[] args) throws Exception {
        log("01 main");

        // Class literal does not initialize Derived.
        Class<?> literal = Derived.class;
        log("02 class literal: " + literal.getSimpleName());

        log("03 construct");
        new Derived();

        log("04 static again: " + Derived.first);

        Class<?> passive = Class.forName(
                InitializationLab.class.getName() + "$Probe",
                false,
                InitializationLab.class.getClassLoader());
        log("05 forName(false): " + passive.getSimpleName());

        Class.forName(
                InitializationLab.class.getName() + "$Probe",
                true,
                InitializationLab.class.getClassLoader());
        log("06 forName(true)");

        Class<?> loaded =
                InitializationLab.class.getClassLoader().loadClass(
                        InitializationLab.class.getName()
                                + "$OnlyLoaded");
        log("07 loadClass: " + loaded.getSimpleName());

        log("08 invoke: " + OnlyLoaded.value());

        log("09 int constant: " + Constants.NUMBER);
        log("10 String constant: " + Constants.TEXT);
        log("11 boxed: " + Constants.BOXED);

        Class<?> brokenType = Broken.class;
        log("12 Broken.class: " + brokenType.getSimpleName());

        try {
            log("13 Broken first: " + Broken.VALUE);
        } catch (ExceptionInInitializerError first) {
            log("13 first: " + first.getClass().getSimpleName());
            log("13 cause: "
                    + first.getCause().getClass().getSimpleName());
        }

        try {
            log("14 Broken second: " + Broken.VALUE);
        } catch (NoClassDefFoundError second) {
            log("14 second: " + second.getClass().getSimpleName());
        }

        log("15 Healthy: " + Healthy.VALUE);
    }
}
~~~

### 5.1. Compiling and Running

Requires JDK **17 or higher**. Open a terminal in the directory containing the file:

~~~bash
javac -encoding UTF-8 InitializationLab.java
java InitializationLab
~~~

The commands work on Bash, PowerShell, and Command Prompt if `javac`/`java` are in `PATH`; the program does not require libraries outside the JDK.

### 5.2. Exact Stdout for the Source Above

~~~text
01 main
02 class literal: Derived
03 construct
Base.field
Base.block
Base.last
Derived.field
Derived.block
Base.ctor
Derived.ctor
04 static again: 3
05 forName(false): Probe
Probe.<clinit>
06 forName(true)
07 loadClass: OnlyLoaded
OnlyLoaded.<clinit>
08 invoke: LOADED
09 int constant: 42
10 String constant: CONST
Constants.<clinit>
11 boxed: 99
12 Broken.class: Broken
Broken.fail
13 first: ExceptionInInitializerError
13 cause: IllegalStateException
14 second: NoClassDefFoundError
Healthy.<clinit>
15 Healthy: 7
~~~

The numeric labels are only markers printed by the program, not timestamps. The `Class.forName` calls use the defining loader of `InitializationLab` itself to avoid depending on the thread's context loader or external environment.

## 6. Analyzing the Class Literal and Inheritance Section

Before the `new Derived()` statement, the output:

~~~text
01 main
02 class literal: Derived
03 construct
~~~

`Derived.class` and `getSimpleName()` do not cause static initialization in the example. If `<clinit>` had run, you would see `Base.field` or `Derived.field` appear **before** line `02`; in fact, they do not.

After marker `03`:

~~~text
Base.field
Base.block
Base.last
Derived.field
Derived.block
Base.ctor
Derived.ctor
~~~

Both **the order between classes** and **the order within each class** can be observed. `Base` must initialize before `Derived`; inside `Base`, the initializer of `first`, then the block, and then the initializer of `last`; after that come `Derived.first` and the block. Only when all static initializers complete do the `Base` and `Derived` constructors run.

If `new Derived()` is called a second time in the same JVM, both constructors will run again, but the static initializers of already-initialized runtime classes do not automatically run again.

## 7. Do Class.forName and loadClass Behave the Same Way?

No. The next part of stdout:

~~~text
05 forName(false): Probe
Probe.<clinit>
06 forName(true)
07 loadClass: OnlyLoaded
OnlyLoaded.<clinit>
08 invoke: LOADED
~~~

- `Class.forName(..., false, loader)` locates/prepares the matching class but **does not require running `Probe.<clinit>`**.
- `Class.forName(..., true, loader)` requires initialization, so the `Probe.<clinit>` log appears **before** marker `06` is printed.
- `ClassLoader.loadClass` locates the `OnlyLoaded` class but does not initialize it on its own; `OnlyLoaded.<clinit>` appears only after marker `07`.
- The static method `OnlyLoaded.value()` is an active use, triggering initialization before the `LOADED` result is printed.

**Do not equate “not yet initialized” with “cannot fail”.** Loading and linking can still encounter `ClassNotFoundException`, `ClassFormatError`, or `LinkageError`. The difference here concerns only the step of running the class initialization method `<clinit>`.

## 8. Why Do static final Constants Not Cause Constants to Initialize?

Output:

~~~text
09 int constant: 42
10 String constant: CONST
Constants.<clinit>
11 boxed: 99
~~~

The two fields:

~~~java
static final int NUMBER = 42;
static final String TEXT = "CONST";
~~~

are **constant variables**: of primitive/String type and having a constant expression. The Java compiler can inline their values into the bytecode of `InitializationLab.main`. Reading them in the example does not initialize `Constants`.

Meanwhile:

~~~java
static final Integer BOXED = mark("Constants.<clinit>", 99);
~~~

is not a constant variable: `Integer` is a reference type and its value is computed during class initialization. When `BOXED` is read, the JVM initializes `Constants` and calls `mark`.

This relates to JAR versioning: if a library changes the value of a `public static final int` compile-time constant, a **previously compiled** caller may still use the old literal. You cannot infer from that value that the ClassLoader “has loaded the new version”.

## 9. First Initialization Failure and Subsequent Uses

An important snippet:

~~~java
static final class Broken {
    static int VALUE = fail();
}

private static int fail() {
    log("Broken.fail");
    throw new IllegalStateException("boom");
}
~~~

`Broken.class` does not execute `fail()`. When `Broken.VALUE` is read for the first time, the JVM begins initializing the class and calls `fail()`. The code throws `IllegalStateException` (not a subclass of `Error`), so the JVM wraps the error in `ExceptionInInitializerError`.

In stdout:

~~~text
12 Broken.class: Broken
Broken.fail
13 first: ExceptionInInitializerError
13 cause: IllegalStateException
14 second: NoClassDefFoundError
~~~

`Broken.fail` **appears only once**. After the failed initialization attempt, the runtime class `Broken` is in an **erroneous** state; the JVM does not automatically retry `<clinit>` when the same runtime class undergoes active use again. Subsequent uses may receive `NoClassDefFoundError`.

`NoClassDefFoundError` can also be caused by a missing dependency or a wrong class file name, so when you see the message `Could not initialize class`, you need to **trace back to the first initialization exception** rather than assuming a missing JAR.

### A Note on Direct Error

If a static initializer throws `AssertionError` or another `Error`, the JVM may propagate the original `Error` directly instead of wrapping it in `ExceptionInInitializerError`. Subsequent uses of the erroneous class may still report `NoClassDefFoundError`.

Production code should not catch `ExceptionInInitializerError` or `NoClassDefFoundError` and continue unconditionally. You should record the root cause and fix the initialization code/config; an erroneous runtime class is not “fixed” by calling a constructor again.

## 10. Failed Superclass Initialization Blocks the Subclass

Illustrative example, **not a standalone runnable file**:

~~~java
class FailingBase {
    static int value = failure();

    static int failure() {
        throw new IllegalStateException("base init failed");
    }
}

class Child extends FailingBase {
    static {
        System.out.println("Child initializer");
    }

    static void go() {
    }
}
~~~

When `Child.go()` triggers initialization of `Child`, the JVM needs to initialize `FailingBase` first. If `FailingBase` fails initialization, `Child` does not complete initialization and the `Child initializer` line is not printed.

Side effects of static initializers that have already run are **not transactionally rolled back by the JVM**. If they wrote files, registered listeners, or modified global state before throwing an exception, the application must design cleanup/recovery itself if needed.

## 11. Static Fields Reading Default Values During Cyclic Initialization

Static fields are assigned default values during preparation before Java initializers run. Illustrative example:

~~~java
class Defaults {
    static int observed = readLater();
    static int later = 10;

    static int readLater() {
        return later;
    }
}
~~~

If `Defaults` initializes normally, `observed` can receive `0` because `later` has not yet been assigned `10` at the time `readLater()` runs. After all initialization finishes, `later == 10`.

Therefore:

- Do not assume that a static field always sees the expected final values of other fields while `<clinit>` is running.
- Avoid dependency cycles between static initializers of multiple classes.
- Limit I/O, mutable shared state, and callback registration in static initialization.
- When complex dependency ordering needs to be managed, use an explicit initialization/factory lifecycle with clear error handling.

**Java memory/concurrency:** The JVM synchronizes class initialization. Two threads concurrently performing active use on an uninitialized runtime class do not run `<clinit>` twice. However, two static initializers of **two different classes** calling across each other can create a deadlock; automatic synchronization does not resolve every dependency cycle.

## 12. A New Test Must Have an Uninitialized Runtime Class

The initialized/erroneous state belongs to the **(binary name, defining loader)** pair. Running the same class again in the same loader does not make the initializer run again, even if `.class` on disk is modified. A new defining loader or a new JVM process is needed when you want to reset the experiment; the final lesson in this chapter shows how to isolate scenarios and verify that the new loader truly owns the class.

## 13. Observing Bytecode

To understand why static fields run in order, use `javap` after compiling:

~~~bash
javap -c -p InitializationLab
javap -c -p 'InitializationLab$Base'
javap -c -p 'InitializationLab$Derived'
javap -c -p 'InitializationLab$Constants'
~~~

The Bash/PowerShell commands use single quotes so the shell does not process the `$` character in the nested class's binary name. On Command Prompt, double quotes can be used.

Look for:

- `<clinit>` in the bytecode of `Base`, `Derived`, and `Constants`.
- The instructions initializing `first`, calling `log/mark`, and the order of bytecode instructions.
- Constant values embedded into the caller by the compiler and the `getstatic` instruction for `Constants.BOXED`.
- The `main` section calling `Class.forName` with boolean `false`/`true`.

JVM diagnostic logs can help observe class loading. Check the available options with:

~~~bash
java -Xlog:help
~~~

Unified Logging logs are not fixed stdout: tag support and presentation may vary across JVM implementations.

## 14. Common Pitfalls

| Misconception | Correct Understanding |
|---|---|
| `loadClass` returning a class means the static block has already run | Loading and initialization are different |
| `SomeClass.class` always initializes the class | A class literal does not automatically trigger `<clinit>` |
| Static fields always all run before static blocks | All static initializers run in source order |
| Base constructor runs before Derived static initializer | When creating a Derived object, class initialization must complete before object construction |
| Reading a constant field always initializes the class | Compile-time constants can be inlined |
| The second use of Broken will call `fail()` another time | An erroneous class does not automatically retry initialization |
| `NoClassDefFoundError` only appears when a file/JAR is missing | It can occur after a class initialization failure |
| Catching an exception means static side effects are rolled back | There is no automatic rollback |
| Creating a new object makes the static block run again | The constructor is what runs again; `<clinit>` does not run again for an already-initialized class |
| A new ClassLoader automatically fixes an initializer error | There is a new runtime class, but the same code/config error still exists |
| Class loading succeeding means every dependency has been resolved | Resolution can be deferred |
| Two threads run a class initializer twice | The JVM synchronizes class initialization, though multi-class deadlock risks remain |

## 15. Scenario-Based Verification

To test on your own, run the sample program in a **fresh JVM** each time and compare against the stdout in section 5.2. The following modifications are **optional exercises**; if you make them, the output will change:

1. Add a second `new Derived();` statement; expect constructor logs without static logs the second time.
2. Change `Class.forName(..., false, ...)` to `true`; `Probe.<clinit>` will appear earlier.
3. Replace `static final int NUMBER = 42` with a runtime value computed via a method; when reading the field, class initialization will take effect.
4. Change `Broken.fail()` to throw `AssertionError`, adjust the catch block, and compare the first failure.
5. Add a static field initializer before `Base.block` and observe the change in log order.
6. Split the code into JARs and run with separate loaders; compare class identity and initializer lifecycle rather than comparing only class names.

Keep the log of the **first error**: the second time may only show `NoClassDefFoundError` and fail to clearly state the original static initializer cause.

## 16. Self-Check Questions

**1.** Why does `Derived.class` not print `Base.field`?

**Answer:** A class literal does not automatically initialize a class; `Base` and `Derived` have not yet undergone active use by that expression.

**2.** In `new Derived()`, why does `Base.block` come before `Derived.field`?

**Answer:** The superclass initializes before the subclass; each class executes its static initializers in source order.

**3.** How do `Class.forName(name, false, loader)` and `Class.forName(name, true, loader)` differ?

**Answer:** `false` does not request initialization; `true` requests initialization.

**4.** Why do the two constant fields of `Constants` not trigger the static block, while `BOXED` does?

**Answer:** Primitive/String constant variables can be inlined; `BOXED` is a reference field computed at runtime, so accessing it triggers initialization.

**5.** Why does the first use of `Broken.VALUE` produce `ExceptionInInitializerError`?

**Answer:** The static field initializer throws `IllegalStateException`, and the JVM wraps non-`Error` exceptions in `ExceptionInInitializerError`.

**6.** Why does the second attempt produce `NoClassDefFoundError` without running `Broken.fail` again?

**Answer:** The runtime class is already in an erroneous state, so the JVM does not automatically reinitialize it.

**7.** With the same binary name, is a class defined by loader L2 instead of L1 required to retain L1's erroneous state?

**Answer:** No. Two defining loaders can define two runtime classes with separate initialization lifecycles; however, the cause of the error may still recur.

**8.** Does a static initializer failure automatically roll back side effects?

**Answer:** No. The JVM does not automatically undo operations that have already run, such as writing files or registering callbacks.

## 17. References

- [JLS Java SE 17 — Class Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): specifies when and in what order initialization occurs.
- [JLS 17 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): synchronization and error states.
- [JVMS 17 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): JVM rules and errors in `<clinit>`.
- [Java 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): loading and class loader identity.
- [Java 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): the overload controlling initialization.
- [Java 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): class initialization error.
- [Java 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): class definition error.

**Remember:** **Loading ≠ initialization.** Static field initializers and static blocks run in source order, after required superclass initialization; `loadClass`, class literals, and `Class.forName(..., false, ...)` do not force `<clinit>`. If `<clinit>` fails, the class can become erroneous: the first attempt reports `ExceptionInInitializerError`, and subsequent attempts report `NoClassDefFoundError`. A new defining loader can create a new runtime class, but does not automatically fix application errors.
