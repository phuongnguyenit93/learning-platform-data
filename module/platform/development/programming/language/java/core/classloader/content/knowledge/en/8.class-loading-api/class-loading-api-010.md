# Distinguishing Class Loading, Object Creation, and Calling Constructors via Reflection

In Java, phrases such as “loading a class”, “initializing a class”, “creating an object”, and “calling a constructor” describe **different actions**. They often appear close together when a program uses reflection, so it is very easy to mistakenly think that `Class.forName("...")` has already created an instance, or that `getDeclaredConstructor()` has already executed the constructor. In reality, a class may have already been loaded and linked by the JVM without being initialized; a `Class<?>` object can exist before any instance does; and **looking up a constructor** is different from **executing a constructor**.

This lesson focuses on the **class-loading and reflection APIs** in Java 17+: `ClassLoader.loadClass`, `Class.forName` overloads, `Class.getConstructor`/`getDeclaredConstructor`, `Constructor.newInstance`, standard `new` usage, and distinguishing the errors that occur at each step. The examples intentionally print checkpoints to show clearly **what has happened** and **what has not happened yet**.

## 1. Five Concepts to Separate

| Action | Meaning | Example | Does it create an instance of the business class on its own? |
| --- | --- | --- | --- |
| **Loading** (class loading) | The JVM identifies a runtime class/interface from a name and loader, possibly needing to read class-file bytes | `loader.loadClass("demo.Widget")` | **No** |
| **Linking** | Verification, preparation, and resolution according to JVM rules | Performed by the JVM when needed so the class can be used | **No** |
| **Initialization** (*class* initialization) | Executes static initializers/`<clinit>` upon active use | `Class.forName(name, true, loader)` | **No** |
| **Instantiation** (*object* creation) | Obtains a new object of the class, allocating it and running the appropriate instance initialization sequence | `new Widget()` or `constructor.newInstance()` | **Yes** |
| **Constructor lookup / invocation** | Finding constructor metadata differs from calling a constructor to create an instance | `getDeclaredConstructor()` / `newInstance()` | **Only invocation creates an instance** |

**Terminology note:** in Vietnamese, both *class initialization* and *object initialization* are often called “khởi tạo” (initialization), but they are not the same:

- **Class initialization:** runs `static` assignments and `static { ... }` blocks according to JVM rules, typically once per class definition in a loader's lifetime. A `Widget` object does not necessarily exist yet.
- **Object initialization:** when a new instance is created, the JVM performs the object initialization process, including the superclass constructor, instance field initializers, instance initializer blocks, and the constructor body in the order specified by Java.
- **The `Class<?>` object:** is a Java object representing the runtime type. It is **not** an instance of `Widget` that the application uses as business data.

### Reading the Overall Flow

```text
Widget.java
    │ javac
    ▼
Widget.class
    │ ClassLoader.loadClass / Class.forName(..., false, ...)
    ▼
Class<?> of Widget  ── may have already undergone loading/linking
    │
    ├─ getName(), getDeclaredConstructor()  → metadata, constructor not called yet
    │
    ├─ Class.forName(..., true, ...)         → requests class initialization
    │
    └─ Constructor.newInstance(args)
            │
            ├─ ensures class initialization when needed
            ├─ allocates a new instance
            ├─ performs object initialization
            └─ returns a new object or an exception
```

The diagram is a conceptual model, not a guarantee that the JVM will perform resolution at one exact source line. The JVM may load/link eagerly and resolve references on demand, but **the side effects of class initialization** must follow the timing permitted by Java.

## 2. What `ClassLoader.loadClass` Can and Cannot Do?

Example:

```java
ClassLoader loader = MyApplication.class.getClassLoader();
Class<?> type = loader.loadClass("demo.Widget");
```

This is a **snippet**; compiling it requires `MyApplication` and `demo.Widget`. Key points:

1. `loadClass` takes the **binary name** of the class, not the path `demo/Widget.class`.
2. The class loader looks up a known definition or locates/delegates class loading through its parent and the `findClass` mechanism.
3. The return value is `Class<?>`, a **type-describing object**. The call **does not include a `Widget()` constructor call**.
4. `ClassLoader.loadClass(String)` normally **does not require class initialization**. Actions related to linking may take place at the JVM's discretion.
5. The invoked loader may **differ from the defining loader**. If it delegates to the parent, a class defined by the parent is still returned normally.

For example, `loader.loadClass("java.lang.String")` typically receives the exact `String.class` via the bootstrap loader, even though the loader receiving the request is the application loader.

You **cannot** conclude from the result of `loadClass` that “the static block has run” or that “a business object already exists”. A way to check whether a class has been initialized in learning examples is to place a simple side effect inside the static initializer and observe the order, but **do not use expensive side effects for production checks**.

### Distinguishing Lookup Errors

`loadClass("demo.Missing")` can throw the **checked exception** `ClassNotFoundException` if the class is not found. If bytes are found but have an invalid format, missing dependencies, or linking fails, the error may belong to the `LinkageError` family. A loader failing to find a class is different from a class constructor throwing an exception.

## 3. `Class.forName`: Overloads Determine Whether to Initialize the Class Immediately

Two important forms:

```java
Class<?> a = Class.forName("demo.Widget");
Class<?> b = Class.forName("demo.Widget", false, loader);
Class<?> c = Class.forName("demo.Widget", true, loader);
```

This is a **snippet**, assuming `loader` has already been declared. According to the API:

- `Class.forName(String className)` finds, loads/links, and **requests initialization** of the named class. The loader is chosen based on the context of the calling class.
- `Class.forName(String name, boolean initialize, ClassLoader loader)` lets you specify the **loader** and the `initialize` flag. With `false`, the method finds/loads/links the class without **requesting initialization**; with `true`, it requests initialization.
- `Class.forName(Module module, String name)` is another overload in Java 9+, serving to find a class in a module and **does not request initialization**; the result can be `null` if the class cannot be found in the specified module. It is **not like** the overloads that throw `ClassNotFoundException`.

Key point to remember: **`Class.forName(name)` does not call the constructor** of the found class. It can trigger the **static initializer**, but it does not create `new Widget()`.

### Class Literal: `Widget.class`

```java
Class<Widget> type = Widget.class;
```

This is a snippet that requires `Widget` to be defined. A class literal provides the `Class<Widget>` object and **does not by itself request initialization of `Widget`**. The JVM may load or link the class to handle the expression; you should not equate these internal steps with running the `static` block.

### A Note on Nested Class Names

In the example below, a `static nested class` named `Target` inside `LifecycleDemo` has the **binary name**:

```text
demo.LifecycleDemo$Target
```

Do not pass a name like `demo.LifecycleDemo.Target` to `Class.forName`/`loadClass`, because that is not the binary name of a member class. `$` is how javac typically generates binary names for nested classes; `Target.class.getName()` helps obtain the proper name instead of concatenating strings manually.

## 4. Lab A — Loading, Metadata, Class Initialization, and Instance Initialization

Run the standalone program with **Java 17+**.

File tree:

```text
lifecycle-lab/
└── src/
    └── demo/
        └── LifecycleDemo.java
```

File **`src/demo/LifecycleDemo.java`**:

```java
package demo;

import java.lang.reflect.Constructor;

public final class LifecycleDemo {
    public static class Target {
        static {
            System.out.println("Target <clinit>");
        }

        public Target() {
            System.out.println("Target <init>");
        }

        public void work() {
            System.out.println("Target.work()");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. main started");

        ClassLoader loader = LifecycleDemo.class.getClassLoader();
        Class<?> fromLoader =
                loader.loadClass("demo.LifecycleDemo$Target");
        System.out.println("2. loaded: " + fromLoader.getSimpleName());

        Class<?> noInit = Class.forName(
                "demo.LifecycleDemo$Target", false, loader);
        System.out.println("3. same Class: " + (fromLoader == noInit));

        Constructor<?> ctor = noInit.getDeclaredConstructor();
        System.out.println("4. constructor found");

        Object first = ctor.newInstance();
        System.out.println("5. first instanceof Target: " +
                (first instanceof Target));

        ((Target) first).work();

        Object second = ctor.newInstance();
        System.out.println("6. different instances: " +
                (first != second));
    }
}
```

From the `lifecycle-lab` directory, run:

```sh
javac --release 17 -d out src/demo/LifecycleDemo.java
java -cp out demo.LifecycleDemo
```

**Exact stdout in a new process:**

```text
1. main started
2. loaded: Target
3. same Class: true
4. constructor found
Target <clinit>
Target <init>
5. first instanceof Target: true
Target.work()
Target <init>
6. different instances: true
```

Checkpoint-by-checkpoint analysis:

1. `main` in `LifecycleDemo` was already prepared/initialized by the JVM before execution began. This **does not automatically force** the static initializer of `LifecycleDemo.Target` to run.
2. `loadClass` returns the `Class<?>` of the nested class `Target`; the second line only prints the type name. No `Target` object is created.
3. `Class.forName(name, false, loader)` returns the exact same `Class<?>`; it does not request class initialization.
4. `getDeclaredConstructor()` **looks up the no-argument constructor metadata**; it does not allocate `Target` and does not call the constructor body. Retrieving metadata may entail some resolution steps, but it is not an active use requiring `Target` to be initialized.
5. `ctor.newInstance()` requests a new instance. The JVM performs class initialization if it is not yet complete, so `Target <clinit>` appears **before** `Target <init>`.
6. `first instanceof Target` is a type check on the already-created object. It does not execute a new constructor; here the result is `true` because the class in the program is the same runtime definition.
7. `((Target) first).work()` calls an instance method and prints its own message; it is not a constructor call.
8. The second `ctor.newInstance()` creates **a different object**, so the constructor prints `Target <init>` again, but the static initializer **does not run again**.

The `<clinit>` and `<init>` markers in the output are used as **illustrative strings** printed by the code itself. In JVM bytecode, `<clinit>` is the special class initialization method and `<init>` is the specially named instance initialization method, whereas the `System.out.println(...)` statements simply help observe the order.

If the class initializer fails, the reflective construction call may fail **before the constructor body starts**. Read the cause in the stack trace to distinguish a class initialization error from an error inside the constructor.

## 5. Lab B — The `initialize` Flag of `Class.forName` and When `static` Runs

A second standalone program helps compare two different JVM processes. Create the file **`src/demo/ForNameDemo.java`** in a separate directory or in the same `src/demo` directory of the lab, then compile it.

```java
package demo;

public final class ForNameDemo {
    public static class Ready {
        static {
            System.out.println("Ready static initialization");
        }

        public Ready() {
            System.out.println("Ready constructor");
        }
    }

    public static void main(String[] args) throws Exception {
        boolean eager = Boolean.parseBoolean(args[0]);

        System.out.println("initialize flag: " + eager);
        Class<?> type = Class.forName(
                "demo.ForNameDemo$Ready",
                eager,
                ForNameDemo.class.getClassLoader());

        System.out.println("Class returned");
        type.getDeclaredConstructor().newInstance();
        System.out.println("Object created");
    }
}
```

Compile:

```sh
javac --release 17 -d out src/demo/ForNameDemo.java
```

**First run**, using `initialize=false`:

```sh
java -cp out demo.ForNameDemo false
```

**Stdout:**

```text
initialize flag: false
Class returned
Ready static initialization
Ready constructor
Object created
```

**Second run**, using `initialize=true`:

```sh
java -cp out demo.ForNameDemo true
```

**Stdout:**

```text
initialize flag: true
Ready static initialization
Class returned
Ready constructor
Object created
```

Observed conclusion: with `false`, the class is looked up beforehand, but the initializer only runs when `Constructor.newInstance()` creates an object. With `true`, `Class.forName` requests initialization before returning `Class<?>`. Both cases require **one constructor call when creating an object**. Each `java` command here starts a separate JVM process, preventing the previous run—where the class was already initialized—from skewing the measurement.

**Do not misinterpret:** the `initialize=true` flag does not mean “initialize an instance”. It only refers to **class initialization**; only the subsequent `newInstance()` statement creates the actual object.

## 6. Constructor Reflection: Finding the Right Constructor Differs from Executing It

The `java.lang.reflect.Constructor<T>` class represents a **constructor declaration** of a class. Commonly used APIs:

| API | What does it find? | Runs the constructor? |
| --- | --- | --- |
| `type.getConstructor(Class<?>... parameterTypes)` | **Public constructor** matching the parameter types list | No |
| `type.getConstructors()` | All public constructors | No |
| `type.getDeclaredConstructor(Class<?>... parameterTypes)` | Constructor declared directly in the class, **including non-public ones** | No |
| `type.getDeclaredConstructors()` | All constructors declared in that class | No |
| `constructor.getParameterTypes()` | Parameter type information | No |
| `constructor.canAccess(target)` | Checks current accessibility; target for a constructor is `null` | No |
| `constructor.trySetAccessible()` | Attempts to bypass access checks when module rules permit | No |
| **`constructor.newInstance(args...)`** | **Creates an instance and calls the selected constructor** | **Yes** |

For constructors, **there is no constructor inheritance** like there is for methods. `getDeclaredConstructor` only searches constructors declared in the class itself; it does not take superclass constructors and assume they can be called as constructors of the subclass.

Two subtle points:

- **`getDeclaredConstructor()` with no arguments** finds specifically the **0-parameter constructor**. If only `Widget(String)` exists, it throws `NoSuchMethodException`; the JVM **does not automatically generate a no-arg constructor** when the class has already declared another constructor.
- `getDeclaredConstructor(String.class, int.class)` requires the **exact parameter types signature**. Do not pass `Integer.class` instead of `int.class` during **lookup**. Argument conversion during **invocation** has its own rules.

### Constructor Lookup Is Not Method Lookup

`getMethod("run")` looks up a public method, which may include inherited methods. `getDeclaredConstructor()` looks up a constructor with the specified signature. Do not try to use `getMethod("<init>")`; `<init>` is a special name inside the JVM class file, not an ordinary Java method that can be called via `getMethod`.

## 7. Lab C — Constructor Overloads, Argument Matching, and Argument Type Reflection

File **`src/demo/ConstructorChoice.java`**:

```java
package demo;

import java.lang.reflect.Constructor;

public final class ConstructorChoice {
    public static class Job {
        private final String id;
        private final int attempts;

        public Job() {
            this("default", 1);
        }

        public Job(String id, int attempts) {
            this.id = id;
            this.attempts = attempts;
            System.out.println("constructor: " + id + "/" + attempts);
        }

        public String summary() {
            return id + ":" + attempts;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Job> type = Job.class;

        Constructor<Job> noArgs = type.getConstructor();
        Constructor<Job> withArgs =
                type.getConstructor(String.class, int.class);

        System.out.println("constructors found");
        Job first = noArgs.newInstance();
        Job second = withArgs.newInstance("batch", 3);

        System.out.println("first: " + first.summary());
        System.out.println("second: " + second.summary());
        System.out.println("distinct: " + (first != second));
    }
}
```

Compile and run from the directory containing `src`:

```sh
javac --release 17 -d out src/demo/ConstructorChoice.java
java -cp out demo.ConstructorChoice
```

**Exact stdout:**

```text
constructors found
constructor: default/1
constructor: batch/3
first: default:1
second: batch:3
distinct: true
```

Why does `"constructor: default/1"` print only **once**, even though the default constructor calls `this("default", 1)`? Because in practice it delegates to the body of the two-parameter overload, where there is a single print statement; when using `this(...)`, the called constructor belongs to the same single instance initialization.

Lessons about reflection:

- `getConstructor` only finds **public constructors**. Here both constructors are `public`.
- `getConstructor(String.class, int.class)` returns metadata for the constructor with parameter types **String, int**, without allocating an object by itself.
- `withArgs.newInstance("batch", 3)` creates a `Job` and calls the selected constructor. When passing arguments, reflection supports boxing/unboxing and widening primitive conversions according to the rules; you should not rely on automatic overload lookup like the Java source compiler.
- `Class<Job>` and `Constructor<Job>` preserve convenient generic information, so the returned variable has type `Job` without requiring a manual cast.
- Direct `new Job()` and `noArgs.newInstance()` both create objects, but they differ in when the constructor is resolved, access checking, and how exceptions are thrown.

### Looking Up Constructors with Primitives and Wrappers

`int.class` represents the primitive type `int`. `Integer.class` is a different **reference type**. For the constructor `Job(String, int)`:

```java
type.getConstructor(String.class, int.class);      // found
type.getConstructor(String.class, Integer.class);  // NoSuchMethodException
```

This is a snippet to place in a method with `throws NoSuchMethodException` and the `type` variable from the example above. **Signature lookup compares exact types**; when calling `newInstance("batch", Integer.valueOf(3))`, reflection can unbox the argument to `int` because the constructor has already been selected.

If a class has multiple overloaded constructors that accept numbers, the author must **select the exact** overload via `getConstructor(parameterTypes...)`. `newInstance` does not run compile-time overload resolution like the `new Job(...)` syntax in Java source.

## 8. How Do Standard `new` and `Constructor.newInstance` Differ?

Both approaches can call the same constructor:

```java
Job direct = new Job();
Job reflective = Job.class.getConstructor().newInstance();
```

This snippet assumes `Job` is a publicly accessible type with a public no-arg constructor, and the enclosing method handles `ReflectiveOperationException`.

| Criterion | `new Job()` | `getConstructor().newInstance()` |
| --- | --- | --- |
| Selecting class/constructor | The compiler knows the Java type and chooses the overload from source | The program can choose the type/signature based on runtime metadata |
| Type and access checks | Primarily at compile time, with JVM runtime checks | Additional runtime lookup/access checks |
| Creates an instance | Yes | Yes |
| Requires class initialization | Yes, if not yet initialized | Yes, if not yet initialized |
| Constructor body | Runs | Runs |
| Result type | `Job` | `Job` with `Constructor<Job>`; `Object` if using `Constructor<?>` |
| Constructor throws checked exception | Java source must obey `throws`/`catch` | Constructor-thrown exception is wrapped in `InvocationTargetException` |
| Wrong signature | Reported in advance by the compiler (usually) | `NoSuchMethodException` at runtime |
| Wrong arguments at invocation | The compiler helps catch this | `IllegalArgumentException` may appear at runtime |

Reflection is useful when the class/constructor is only determined at runtime: DI containers, serialization frameworks, plugin discovery, runtime annotation processors, and test frameworks. However, if the type and constructor are known with certainty at compile time, `new` syntax or a factory is usually clearer, less prone to runtime errors, and easier to maintain.

### Reflection Does Not Automatically Solve All Class-Loading Issues

If you only have a class name without knowing the appropriate loader, `Class.forName(...)` may load a copy of the class in a different loader from the one the application intends to use. Once you have `Class<?>`, the constructor is obtained from **that exact runtime type**. Two classes with the same name defined by two different defining loaders will have `Constructor<?>` objects attached to **two different runtime classes**. You cannot simply cast an object from the plugin loader's type to the host's type just because the class names match.

## 9. Instance Initialization: Step Ordering Easily Confused with `static`

A constructor call is not simply executing the lines inside the final constructor body. For an ordinary class object, the program follows the instance initialization sequence:

1. The JVM needs a valid class, initialized according to the rules (if not yet initialized).
2. Allocates a new object and sets **default values** for instance fields before specific initializers run.
3. Executes the superclass constructor chain (`super(...)`) according to Java language rules.
4. Executes the instance field initializers and instance initializer blocks of the respective class in source order.
5. Executes the appropriate constructor body, after any required `this(...)`/`super(...)` calls during initialization.

Standalone example, file **`src/demo/OrderDemo.java`**:

```java
package demo;

class Parent {
    static {
        System.out.println("Parent static");
    }

    {
        System.out.println("Parent instance block");
    }

    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child static");
    }

    {
        System.out.println("Child instance block");
    }

    Child() {
        System.out.println("Child constructor");
    }
}

public final class OrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");
        new Child();
        System.out.println("after first");
        new Child();
    }
}
```

Run:

```sh
javac --release 17 -d out src/demo/OrderDemo.java
java -cp out demo.OrderDemo
```

**Exact stdout:**

```text
before new
Parent static
Child static
Parent instance block
Parent constructor
Child instance block
Child constructor
after first
Parent instance block
Parent constructor
Child instance block
Child constructor
```

When `Child` must be initialized, the JVM initializes superclass `Parent` before initializing `Child` itself; therefore, both static blocks appear before the object constructors. Each subsequent `new Child()` still runs the **instance blocks and constructor chain**, but **does not re-run the static initializers**. If you replace the two `new Child()` expressions with an appropriate `Constructor<Child>.newInstance()`, the static and instance ordering principles are still preserved.

The full sequence includes additional specific rules for related interface initialization and constructor chaining; the example deliberately uses ordinary classes to illustrate the main flow. Do not use `ClassLoader.loadClass` as a mechanism to "run the Parent constructor first" — that is a different thing.

## 10. A Class Can Be Initialized Without Any Instance at All

Reading a static field or calling a static method belonging to a class can require **class initialization**, even if no object is created.

Illustrative snippet example:

```java
class Settings {
    static {
        System.out.println("Settings initialized");
    }

    static int getPort() {
        return 8080;
    }
}
```

If another program calls `Settings.getPort()`, the JVM may have to execute the static initializer without calling `new Settings()`, without calling the `Settings()` constructor, and without needing any Settings instance.

Conversely, a **constant variable** such as `public static final int PORT = 8080` can be inlined into the caller by the compiler. Reading it from another class does not necessarily require initializing the declaring class. That is why, to accurately check when a static initializer runs, you should not rely solely on reading a compile-time constant.

Operations such as `SomeClass.class`, `someClass.getName()`, and looking up constructor metadata are typically **not** active uses. However, static method invocation, reading a non-constant static field, object creation, and certain reflection operations can be active uses. In particular, `Class.forName(name, true, loader)` requests initialization even when no constructor is called.

## 11. Common Mistakes with `Class.newInstance()`

Legacy API:

```java
Object instance = type.newInstance();
```

`Class.newInstance()` has been **deprecated since Java 9**. Java 17+ code should use:

```java
Object instance = type.getDeclaredConstructor().newInstance();
```

Both are **snippets**; the `type` variable has type `Class<?>` and the method must handle exceptions appropriately.

A technical reason worth remembering: `Class.newInstance()` has an unintuitive exception-handling mechanism, because it can **propagate checked exceptions thrown by the constructor** without reflecting them fully in its signature. Using `getDeclaredConstructor().newInstance()` throws `InvocationTargetException`, helping the caller distinguish **errors in calling the reflective API** from **exceptions arising inside the constructor**.

Furthermore, selecting a constructor via `getDeclaredConstructor(Class<?>...)` allows specifying the exact overload, without limiting yourself to the public zero-argument constructor that `Class.newInstance()` tries to use.

Do not use `Class.newInstance()` in new examples just because it is slightly shorter. Especially in framework code, retrieving `InvocationTargetException.getCause()` is important to preserve the origin of the error.

## 12. Lab D — Errors Inside the Constructor and `InvocationTargetException`

Create the file **`src/demo/ConstructorErrorDemo.java`**:

```java
package demo;

import java.lang.reflect.InvocationTargetException;

public final class ConstructorErrorDemo {
    public static class Broken {
        public Broken() {
            System.out.println("constructor entered");
            throw new IllegalStateException("bad config");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "demo.ConstructorErrorDemo$Broken",
                false,
                ConstructorErrorDemo.class.getClassLoader());

        System.out.println("Class found");
        try {
            type.getDeclaredConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable original = e.getCause();
            System.out.println("reflection wrapper: " +
                    e.getClass().getSimpleName());
            System.out.println("constructor cause: " +
                    original.getClass().getSimpleName());
            System.out.println("message: " + original.getMessage());
        }
    }
}
```

Run with JDK 17+:

```sh
javac --release 17 -d out src/demo/ConstructorErrorDemo.java
java -cp out demo.ConstructorErrorDemo
```

**Exact stdout:**

```text
Class found
constructor entered
reflection wrapper: InvocationTargetException
constructor cause: IllegalStateException
message: bad config
```

Verification points:

- `Class.forName(..., false, ...)` locates the class without requesting initialization; there is no output from the constructor before calling `newInstance`.
- The constructor **did begin executing**, because it printed `constructor entered`, and then the constructor itself threw `IllegalStateException`.
- `Constructor.newInstance` wraps the exception thrown by the constructor inside `InvocationTargetException`; `getCause()` returns the original exception.
- If the class static initializer throws an exception **before the constructor body runs**, the JVM may report `ExceptionInInitializerError` or a related initialization error. That is a **different case**; do not assume all construction failures are `InvocationTargetException`.

In real applications, logging must preserve the stack trace/cause as well, not just call `getSimpleName()`. The example above prints exception names to verify the order and content deterministically.

## 13. Error Matrix by Operation

| Action | Possible Errors | Meaning |
| --- | --- | --- |
| `loader.loadClass(name)` | `ClassNotFoundException` | The loader could not find the requested class; does not say whether the constructor has a bug. |
| `Class.forName(name, ..., loader)` | `ClassNotFoundException`, `LinkageError`, initialization errors if `true` | Invalid name/loader, linking failed, or static initialization encountered a problem. |
| `type.getConstructor(types...)` | `NoSuchMethodException` | No **public constructor** matches the parameter list. |
| `type.getDeclaredConstructor(types...)` | `NoSuchMethodException` | The class does not declare a constructor with that signature, even after considering non-public ones. |
| `ctor.newInstance(args...)` | `InstantiationException` | The declaring class is abstract or cannot be instantiated per the API contract. |
| `ctor.newInstance(args...)` | `IllegalAccessException` | The caller does not have permission to access the constructor under access/module rules. |
| `ctor.newInstance(args...)` | `IllegalArgumentException` | Invalid argument count/types or unsupported conversion. |
| `ctor.newInstance(args...)` | `InvocationTargetException` | Code **inside the constructor** threw an exception; inspect `getCause()`. |
| Reflection opening private access | `InaccessibleObjectException` or `trySetAccessible() == false` | The module/package is not properly opened or reflection permission is not allowed. |
| Class initialization during construction | `ExceptionInInitializerError`/`NoClassDefFoundError` | Static initialization failed on the first attempt or the class already carries a failed initialization state. |
| Casting the newly created object | `ClassCastException` | The runtime object is not assignable to the target type, possibly due to class loader identity. |

Errors are listed by **primary context**, which does not mean each API only produces that exact error type. Certain errors like `LinkageError`, `SecurityException`, or `ExceptionInInitializerError` are unchecked and can arise across different phases. If a log only prints “Cannot instantiate”, you need to trace **which phase** failed: class not found, constructor not found, access denied, class initialization failed, or the constructor body threw an exception.

### `InstantiationException` and Abstract Classes

Reflection does not permit creating an instance directly of an **abstract class**, even though an abstract class has a valid constructor (that constructor is called by subclasses when instantiating a subclass). An interface has no Java constructor to look up via `getDeclaredConstructor()` in the usual object-creation manner. Enum constructors are not used to arbitrarily create enum constants via reflection; `Constructor.newInstance` rejects enum instantiation.

A **record** has a constructor (typically the canonical constructor) and can still be instantiated via reflection if the constructor/access/arguments are valid; do not impose the assumption that “every class has a no-arg constructor”. A record that declares components typically requires passing the exact parameters of the canonical constructor.

## 14. Distinguishing Access Modifiers from Reflective Accessibility

In ordinary code, the Java compiler checks `public`, `protected`, package-private, and `private`. Reflection can find a **private constructor** via `getDeclaredConstructor`, but **finding it does not mean you are permitted to call it**.

Illustrative example:

```java
Constructor<?> ctor = type.getDeclaredConstructor();
boolean changed = ctor.trySetAccessible();
if (changed) {
    Object value = ctor.newInstance();
}
```

This is a **snippet**, requiring a `type` variable and exception handling. `trySetAccessible()` attempts to suppress Java language access checks within the bounds of module rules; if unsuccessful, it returns `false` (or may raise a security error depending on the environment). `setAccessible(true)` can throw `InaccessibleObjectException` when performing deep reflection into a package that a named module does not open.

You **should not** assume every JDK-internal private constructor can be invoked using `setAccessible(true)`. Since Java 9+, the Java Platform Module System distinguishes **exports** (public API access) from **opens** (deep reflection), and newer JDK versions are stricter about encapsulating JDK internals. When designing APIs for frameworks/DI, you should expose a public constructor/factory or declare `opens ... to ...` as needed rather than relying on tricks that break encapsulation.

If the caller and target code are **nestmates** in the same Java nest, private access permissions follow separate rules. However, the learning examples above use public nested classes/constructors to avoid relying on operations that open reflection access.

### `getDeclaredConstructor` Does Not Automatically Grant Higher Privileges Than `getConstructor`

- `getDeclaredConstructor` sees declared constructors, **including private ones**.
- `getConstructor` only sees public constructors.
- **`newInstance` itself** still checks caller and module access permissions. Therefore, seeing private metadata is not sufficient to infer that it can be invoked.

## 15. Reflection and ClassLoader Identity: Creating an Object Can Still Fail to Cast

When a class is loaded via a separate loader, `type.getDeclaredConstructor().newInstance()` creates an object with **that runtime class `type`**. It does not turn the object into the class of the same name known to the host.

To visualize:

```text
HostLoader defines api.Task
PluginLoader defines api.Task

Class<?> hostType    → (api.Task, HostLoader)
Class<?> pluginType  → (api.Task, PluginLoader)

pluginType.getDeclaredConstructor().newInstance()
          → instance of pluginType
          → CANNOT be automatically cast to hostType
```

Check with:

```java
Class<?> actualType = instance.getClass();
System.out.println(actualType.getName());
System.out.println(actualType.getClassLoader());
System.out.println(expectedType.isInstance(instance));
```

The snippet requires declaring `instance` and `expectedType`. If `isInstance` returns `false`, the reflective constructor call may have completely succeeded, yet the two types across the loader boundary are still incompatible.

**The proper design in a plugin system:** the interface/service API must be resolved by both the host and plugin to the **same `Class<?>`**, typically via a parent/shared-API loader, while the implementation is defined separately by the plugin loader. Then the host can cast the implementation instance to the shared interface without needing to load the implementation itself on the application classpath.

### What If the Loader Does Not Yet Know the Class, Only the Bytes?

A custom loader can read bytes in `findClass` and use `defineClass` to create a runtime class. That is the **loading part**, not calling the loaded class's constructor. Only after having `Class<?>` does the program look up the constructor and create an instance. Do not turn `findClass` or `defineClass` into a “instantiate plugin object” function without distinguishing the lifecycle phases.

## 16. When Should You Use `getDeclaredConstructor().newInstance()`?

Valid scenarios:

1. **Plugin registry:** the binary class name is configured or read from metadata, with the concrete implementation unknown at compile time.
2. **Dependency injection container:** the framework determines the constructor from annotations/metadata and provides the corresponding arguments.
3. **Serialization/deserialization tools:** have an appropriate object instantiation mechanism, although not every serializer calls a regular Java constructor.
4. **Test framework:** creates test classes and calls lifecycle hooks based on runtime metadata.
5. **Dynamic factory:** the user selects an implementation through configuration while the system wants to control type/constructor access.

A safe and easy-to-debug execution flow:

```text
Class name / configuration metadata
        ↓ validate name and choose the right ClassLoader
Class<?> type = Class.forName(name, false, loader)
        ↓ validate desired subtype/interface
expectedInterface.isAssignableFrom(type)
        ↓ select constructor by parameter types
type.getDeclaredConstructor(...)
        ↓ check appropriate access permissions
constructor.newInstance(args...)
        ↓ cast to shared interface / catch categorized errors
host uses object via contract
```

**Note:** checking `isAssignableFrom` helps avoid an invalid cast, but **does not by itself make running an untrusted plugin safe**. A constructor can open files, start threads, access the network, or cause side effects. A class loader only addresses visibility/definition; sandboxing requires independent security measures.

### When Is `new` or a Factory Usually Better?

If the application already knows `new Service(config)` at compile time, direct construction is usually transparent, ensures compiler signature checking, involves fewer reflection exceptions, and is convenient to refactor. Reflection should solve **genuine runtime discovery needs**; it is unnecessary just to avoid writing a `new` statement.

If an API has multiple constructor overloads or requires complex configuration, a **public static factory** or a plugin-provided factory in the shared API can help keep the contract more stable than having the host look up concrete constructors by name. A factory is also an option for classes with a private constructor so the framework does not need to open deep access.

## 17. Controlling Side Effects and Lifecycle When Creating Plugin Objects

The fact that `Class.forName(..., false, loader)` only looks up a class does not mean the entire process is “harmless”: loading, verification/linking, or running agent/loader code can have costs and side effects depending on the implementation. However, static initialization of the target class is controlled by JVM rules, and the constructor body does not run until an instance is created.

A constructor should not do too much uncontrolled work, especially in a plugin runtime:

- Do not automatically register global listeners or create background threads unless there is a clear unregistration/stop mechanism.
- Consider moving network/file connections, loading configuration, or opening resources into a `start()`/factory lifecycle that can report errors clearly and clean up safely.
- If a constructor throws after partial side effects, the caller may receive an `InvocationTargetException` without a valid object to call `close()` on; therefore, resource/rollback design must be handled carefully.
- With plugin reloading, objects and `Class<?>` can keep the class loader alive. `URLClassLoader.close()` releases resources opened by the loader, but does not guarantee immediate class/object unloading; GC still depends on reachability.

Distinguish three operations in operational logs: **load type**, **instantiate service**, **start service**. Even though all three may occur back-to-back, they are three different states and should have separate error reporting.

## 18. A Symptom-Based Diagnostic Workflow

**If it says “cannot load class”:** check the binary name, classpath/module path, parent loader, whether the class file exists, and whether the runtime JDK supports the bytecode version. Catch `ClassNotFoundException` around the loader/`forName` call where appropriate.

**If “the class loaded, but cannot create the object”:** verify whether the class is an interface/abstract/enum; which constructors exist; and whether the parameter types and access permissions match. Log `getDeclaredConstructors()` in debugging tools, while avoiding putting metadata of untrusted classes into public logs.

**If “the constructor ran, but returned an error”:** catch `InvocationTargetException`, inspect `getCause()`; distinguish an exception from the constructor body from an initialization error that occurred before the body.

**If “the object was created, but casting failed”:** check `type.getClassLoader()`, `expectedInterface.getClassLoader()`, `isAssignableFrom`, and shared API packaging. Do not assume two classes with the same binary name are sufficient.

**If “the static block ran too early”:** look for calls to `Class.forName(name)` (which initializes by default), instance creation, static method calls, or reading a non-compile-time-constant static field. You can replace it with `Class.forName(name, false, loader)` when only metadata is needed and API semantics allow.

**If “the static block did not run when calling `loadClass`”:** that behavior is expected for normal `loadClass(String)`; an active use or `Class.forName(..., true, ...)` is needed when you actually want to initialize the target.

**If “re-running does not print the static block anymore”:** class initialization typically happens only once per runtime class. To observe it from the beginning, run a fresh JVM; calling `Constructor.newInstance` multiple times does not automatically reset static state.

### Supporting Tools

```sh
javap -classpath out -c -p demo.LifecycleDemo
javap -classpath out -v 'demo.LifecycleDemo$Target'
java -Xlog:class+load=info -cp out demo.LifecycleDemo
```

`javap` shows that the class file contains the `<init>` constructor, the `<clinit>` class initializer, and bytecode such as `new`/`invokespecial`. For nested class names containing `$`, quote them as shown in Unix shells to avoid environment variable substitution; PowerShell also interprets single quotes as literal. HotSpot's unified class-load log has runtime-dependent output and **only provides a loading signal**, without proving on its own that the constructor ran; to know whether the constructor ran, observe the application's own output/stack trace.

## 19. Common False Claims

- **"`loadClass` is the same as `new`."** False: it returns `Class<?>`, without creating a business instance.
- **"`Class.forName(name)` automatically calls the default constructor."** False: this overload requests **class initialization**, without creating an instance.
- **"`getDeclaredConstructor` runs the constructor."** False: it only returns **constructor metadata**.
- **"Using `getDeclaredConstructor` lets you call private constructors immediately."** False: access and JPMS are still checked at invocation time.
- **"`getDeclaredConstructor(Integer.class)` will find a constructor taking `int`."** False: parameter type lookup is exact; argument conversion is a separate step.
- **"`Constructor.newInstance` runs the static block every time."** False: class initialization does not repeat per object; the instance constructor can run many times.
- **"A constructor throw will always expose `IllegalStateException` directly."** False: `Constructor.newInstance` usually wraps body exceptions inside `InvocationTargetException`; class initialization errors are a separate group.
- **"`Class.newInstance` is the newest option."** False: it is deprecated; use `getDeclaredConstructor().newInstance()` instead.
- **"A ClassLoader defining a class automatically produces an instance."** False: type metadata and object instances are two distinct concepts.
- **"Reflection eliminates identity issues across multiple class loaders."** False: the newly created object carries the exact runtime type of the class used by reflection.
- **"A loaded class definitely has a public zero-argument constructor."** False: it might not have one, or it may be abstract/interface/enum/record with its own constraints.
- **"You can determine resolution timing for sure from `javap` output alone."** False: `javap` reads file metadata; the JVM is allowed to perform resolution according to its runtime strategy.

## 20. Self-Check: Answer Before Checking the Answers

**1. What kind of object does `ClassLoader.loadClass("demo.Target")` return?** A `Class<?>` representing the target runtime class; it does not automatically create a target instance or force the target constructor to run.

**2. How does `Class.forName("demo.Target")` differ from the `Class.forName("demo.Target", false, loader)` overload?** The first form requests class initialization; the form with `false` locates/loads/links without requesting initialization, while also specifying the loader explicitly.

**3. When `getDeclaredConstructor()` succeeds, do you know the constructor body has run?** No. That is only a metadata lookup.

**4. Why does `Constructor.newInstance()` print the static block only the first time, while the constructor prints every time?** Class initialization normally runs once for that class, whereas each new instance must go through object initialization.

**5. Why is `getConstructor(int.class)` different from `getConstructor(Integer.class)`?** Primitive `int` and wrapper `Integer` are two different types; constructor lookup requires exact parameter types.

**6. Is `Class.newInstance()` still recommended for Java 17+?** No. The API is deprecated; use `getDeclaredConstructor().newInstance()` with clear exception handling.

**7. If a constructor throws `IllegalArgumentException` from inside its body, where should you look for it?** When called through `Constructor.newInstance`, the body exception is typically the `cause` of `InvocationTargetException`. If `newInstance` directly throws `IllegalArgumentException` due to invalid arguments, that is a reflection invocation issue before the constructor body runs.

**8. For a class with a private constructor, which API finds the constructor?** `getDeclaredConstructor(...)`; whether it can be called depends on access rules, module openness, and the caller.

**9. Can a class be initialized without any instance yet?** Yes. Calling a static method or `Class.forName(..., true, ...)` can initialize the class without creating an object.

**10. Why can reflection create an object named `demo.Plugin` properly, yet the host's cast fails?** Because the object may be an instance of a runtime class with the same binary name defined by a different defining loader; shared API identity must be used.

## 21. Official References

- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, and defining/initiating loaders.
- [Java SE 17 `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName` overloads, `getConstructor`, `getDeclaredConstructor`, class literals, and the deprecated `newInstance()`.
- [Java SE 17 `Constructor` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `Constructor.newInstance`, argument/access checks, and `InvocationTargetException`.
- [Java SE 17 `InvocationTargetException` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): how to retrieve the target exception.
- [The Java Language Specification, Java SE 17, 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization; class instance creation and the instance initialization sequence.
- [The Java Virtual Machine Specification, Java SE 17, 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, class initialization, and execution boundaries.

**Key rule to remember:** **`loadClass` finds a runtime *type*; `Class.forName` also has an option to request *class initialization*; `getDeclaredConstructor` finds *constructor metadata*; only `Constructor.newInstance` creates an *instance* and executes the constructor.** When debugging, identify each step along with the specific class loader and runtime type to avoid conflating these four actions.
