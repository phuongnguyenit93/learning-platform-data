# When the JVM Needs to Create and Load a Class or Interface

When reading or executing a Java program, the JVM does not necessarily load every class and interface appearing in the source code right from the start. The JVM creates **runtime type definitions** based on execution needs, the linking process, library requests such as reflection, and may load some types earlier for optimization. The essential point is to understand **when the JVM needs to have a type** and **when that type is actually initialized**.

This article explains precisely the two terms in the title:

- **Class/interface creation in the JVM** (*class/interface creation*, per the JVM Specification): constructing the runtime representation of a **type** identified by its name and defining class loader. This is **not** calling `new` to create an application object.
- **Class/interface loading** (*class/interface loading*): using the class loader mechanism to find the binary representation (typically from a `.class` file, JAR, module, or other bytecode source), and then having the JVM create the runtime definition for that type. For an **array class**, the JVM has special creation rules and does not require a `.class` file for the array.

For example, the JVM may have already created the type definition for `com.acme.Order` and returned `Order.class` without having run any `static` initializer of `Order`, and without any `new Order()` object existing at all.

## 1. Four Moments That Must Be Kept Separate

```text
Program references a type T
          |
          v
    Loading / Creation
  find/define T in the JVM
          |
          v
         Linking
  verification -> preparation -> resolution (*)
          |
          v
     Initialization (when triggered)
  run static initialization of T
          |
          v
    Instance creation (only when needed)
  new T(...) / corresponding object creation mechanism

(*) Resolution can be done incrementally as references are used.
    This is a relationship diagram, not a mandatory schedule where
    every step occurs consecutively right away in a single execution.
```

| Concept | What does the JVM need to do? | Observable result |
|---|---|---|
| **Loading / creation** | Identify the type, locate bytecode if it is an ordinary type, and construct the runtime type representation | A `Class<?>` representation exists; may occur when the JVM resolves a type reference |
| **Verification** | Check validity constraints of the bytecode representation | Invalid bytecode can lead to `VerifyError` |
| **Preparation** | Prepare storage for `static` fields with default values or values per `ConstantValue` when applicable | Does not yet mean running all `static` initialization expressions |
| **Resolution** | Convert symbolic references into concrete runtime references, applying type/access checks | When using the reference, `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError`… may be observed |
| **Initialization** | Execute `static` initialization logic (the class initialization method `<clinit>` if present) | Logs from `static { ... }` or methods called when assigning `static` fields |
| **Instance creation** | Allocate/initialize an object of a concrete class | Constructor, new state of each instance |

**Rule to remember:** *Loaded* does not mean *class-initialized*; *class-initialized* does not mean *an instance has been created*; and *creating an instance* does not mean *reloading the class from bytecode*.

### The Semantics of “Need” Differ from “Definitely Beginning to Load Only at That Moment”

There are two levels to distinguish:

1. **Requirements of program semantics:** When the JVM must use information about type T to execute validly (for example, resolving a method/field reference or performing a type check), the JVM must have obtained the corresponding type definition of T before that operation completes.
2. **Execution schedule chosen by the JVM:** The JVM may prepare ahead of time, eagerly load dependent types, or defer resolution. Therefore, one cannot infer backward from a line of Java that **precisely** on that line the JVM reads `T.class` for the first time.

Conversely, the rules for **class/interface initialization** are stricter: Java clearly specifies the active-use cases that lead to initialization. When you want to prove ordering, observe the `static` initializer; when you want to see actual loading activity, use the JVM's class-loading logging tools.

## 2. Where Does the JVM Start Creating/Loading Classes?

According to the JVM Specification, at startup the JVM selects an **initial class or interface**, creates and links that initial type, initializes it according to the relevant rules, and then runs the appropriate entry point (for example, `main`). While code executes, references to other types continue to lead to loading or linking work.

A type definition for T can be created from the following primary causes:

- **Symbolic reference from another class/interface:** For example, the bytecode of class D contains a symbolic reference to T in its run-time constant pool. When the JVM needs to process that reference during execution or linking/resolution, the JVM may have to create/load T.
- **Library APIs requesting type lookup:** For example, `Class.forName(...)`, `ClassLoader.loadClass(...)`, reflection frameworks, service/provider loading, or custom-built plugin code.
- **Array class creation:** The JVM creates an array class according to its own rules when the corresponding array type needs to be present; the component type may need to be loaded, but **doing so does not automatically initialize the component class**.
- **Types defined from dynamic bytecode sources:** A custom loader uses the `defineClass` API or another valid class-definition mechanism. This is still creating a **type definition**, independent of invoking an instance constructor.

The important starting point is not “which files are sitting on disk,” but rather **which type is requested by a symbolic reference or API call within which loader's namespace**.

### The Role of Symbolic References and the Constant Pool

A `.class` file does not pre-embed Java object pointers to every class it uses. It contains names and symbolic references—for example, references to types, fields, methods, or an entry related to a method invocation.

```text
Caller bytecode
  constant pool:
    #... Class com/acme/Service
    #... Methodref com/acme/Service.run:()V
               |
               | resolution when needed
               v
  Type com.acme.Service has been defined by the appropriate loader
               |
               v
  Runtime reference to method/field can be used
```

The JVM must enforce type safety, verification, and access control constraints. When the proper definition of T is missing, the related operation may fail at the time the JVM attempts to use that type. One should not assume that all symbolic references are resolved at a single point in time.

## 3. Java Operations That Can Lead to Type Loading or Resolution

The following examples consider the class `Service` as an ordinary application type and assume it has not yet been loaded by the required loader.

### 3.1. Using `new`

```java
Service service = new Service();
```

The `new` instruction in bytecode must resolve the `Service` type and requires type information to create an instance. If this type definition does not yet exist, the JVM will load/create it through the loader mechanism. Before instance creation completes, `Service` needs to be initialized (if not already); afterward, the constructor is called.

**Do not infer** that every `new Service()` reloads `Service`. Once the class definition already exists and is initialized, subsequent `new` calls create new objects sharing that same runtime definition.

### 3.2. Reading/Writing `static` Fields and Calling `static` Methods

```java
int current = Service.counter;
Service.counter = 10;
Service.refresh();
```

To resolve a field or method, the JVM needs the definition of the class/interface that actually declares that member. When the usage is an initialization trigger under Java's rules, the JVM must initialize the member-declaring type before the operation. For `static` access, initialization belongs to **the resolved type that declares the member**, not necessarily the type named on the left-hand side in the source code.

**An often-overlooked exception:** reading a *compile-time constant variable* does not require initializing the declaring type. For example, `static final int PORT = 8080;` may have its value inlined directly by the compiler into the caller's bytecode. However, `static final int PORT = readPort();` is **not** a constant variable, and reading this field directly is an active use.

### 3.3. Operators and Type Checks

```java
boolean ok = value instanceof Service;
Service s = (Service) value;
Class<Service> type = Service.class;
```

These operations may require the JVM to have runtime information about `Service` to perform type checks or produce the `Class` representation. **They do not automatically require initializing `Service`.**

With `instanceof` and casting, some cases are optimized or the reference has already been resolved beforehand, so one should not claim that **every execution** of the check creates/loads a class anew. If the target class is absent or cannot be resolved, the associated operation may encounter a linkage error when needed.

### 3.4. Reflection and Loading Requests by Name

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> a = loader.loadClass("com.acme.Service");
Class<?> b = Class.forName("com.acme.Service", false, loader);
Class<?> c = Class.forName("com.acme.Service");
```

This is an **API illustration snippet**, not a standalone program; it succeeds only if the corresponding loader can actually locate that binary name.

- `loader.loadClass(name)` asks the loader to find/load the type; by default behavior it **does not require initializing** the class. Calling this loader also does not guarantee it will be the defining loader if delegation is in effect.
- `Class.forName(name, false, loader)` requests finding/loading and linking the type, but **does not require initializing** it.
- `Class.forName(name)`, the single-argument overload, typically uses the caller's loader and **requires initializing** the type (per the API documentation), if it has not yet been initialized.

None of the methods in the three lines above creates a `Service` instance on its own. You must separate the returned `Class<?>` from `new Service()` or invoking a constructor via reflection.

### 3.5. Loading by Frameworks, Plugins, and Dependency Injection

A framework may read class names from configuration, inspect annotations, open metadata, and call `loadClass` or `Class.forName`. A plugin loader may also define classes directly from a JAR's bytecode.

Points to observe:

- **Metadata inspection** may only require the type definition without initializing it.
- **Bean/service instantiation** can cause the class to be initialized and an instance to be created.
- **Custom class loaders** determine namespaces: the same binary name with two different defining loaders can result in two incompatible runtime types.

Consult the specific framework's API to know whether it actively initializes the class; do not guess merely because the framework already knows the class name.

## 4. Array Classes Are a Special Case of Type Creation

For example:

```java
Service[] services = new Service[3];
Class<?> arrayType = Service[].class;
Class<?> componentType = arrayType.getComponentType();
```

The JVM has a separate runtime definition for the array type `Service[]`. **Array classes are created by the JVM**; there is no `Service[].class` file on disk for a loader to read.

If the component is a reference type, the JVM needs the corresponding component type and associates the array class's defining loader with the component's defining loader. If the component is a primitive, the array class is associated with the bootstrap loader per the JVM specification. Arrays with different dimensions are different types: `Service[]` and `Service[][]` do not share the same `Class`.

**Creating an object array does not create element objects and does not automatically initialize the component class.** `new Service[3]` creates an array object with three `null` elements; it is not equivalent to running `new Service()` three times.

For arrays, distinguish the following:

| Operation | Creates an instance of `Service`? | May create/touch the array type? | Requires initializing `Service` solely because of that operation? |
|---|---|---|---|
| `Service[].class` | No | Yes | No |
| `new Service[3]` | No | Yes | No |
| `services[0] = new Service()` | Yes | Array already exists | Yes, if not yet initialized |
| `int[].class` | Not applicable | Yes, array class of primitive | Not applicable |

## 5. Java 17+ Experiment: Clearly Observing Initialization Timing

Because **loading can happen early**, a log message inside a `static` initializer only shows **initialization**, not the exact moment the JVM reads the `.class` file. The program below deliberately separates those behaviors.

Create the file **`LoadingMomentsDemo.java`**:

```java
public class LoadingMomentsDemo {
    static class Service {
        static final int VERSION = 3; // compile-time constant
        static final int PORT = port();

        static {
            System.out.println("Service.<clinit> block");
        }

        static int port() {
            System.out.println("Service.port()");
            return 8080;
        }

        Service() {
            System.out.println("Service constructor");
        }
    }

    interface Feature {
        int VALUE = trace(); // not a compile-time constant

        static int trace() {
            System.out.println("Feature initialized");
            return 7;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> mirror = Service.class;
        System.out.println("Class literal ready");

        ClassLoader loader = LoadingMomentsDemo.class.getClassLoader();
        Class<?> loaded = loader.loadClass(mirror.getName());
        System.out.println("Same Class: " + (mirror == loaded));

        System.out.println("Constant: " + Service.VERSION);

        Service[] slots = new Service[2];
        System.out.println("Array length: " + slots.length);

        Class.forName(mirror.getName(), false, mirror.getClassLoader());
        System.out.println("forName(false) returned");

        System.out.println("Port: " + Service.PORT);
        new Service();

        System.out.println("Feature value: " + Feature.VALUE);
    }
}
```

Compile/run:

```bash
javac LoadingMomentsDemo.java
java LoadingMomentsDemo
```

**Expected stdout:**

```text
Class literal ready
Same Class: true
Constant: 3
Array length: 2
forName(false) returned
Service.port()
Service.<clinit> block
Port: 8080
Service constructor
Feature initialized
Feature value: 7
```

**Explanation of each milestone:**

1. `Service.class` allows obtaining `Class<?>`. There is no output from `Service` yet: a class literal does not by itself force the initializer to run.
2. `loader.loadClass(mirror.getName())` uses the appropriate loader to locate the same class definition; the resulting mirrors are equal. This code does not require initializing `Service`.
3. `Service.VERSION` is a constant variable (`static final int` assigned from a constant expression). The caller can use the value `3` directly without triggering `Service`'s initializer.
4. `new Service[2]` creates an **array instance** with two `null` slots. The JVM has the array type and component information, yet still does not need to initialize `Service`.
5. `Class.forName(name, false, loader)` returns without requiring `Service` to be initialized.
6. **The first read of `Service.PORT`** is an active use of a `static` field that is not a constant variable. The JVM initializes `Service`: running `port()` first and then the `static` block in source-code order; therefore, those two log lines appear before `Port: 8080`.
7. `new Service()` subsequently runs the constructor and prints `Service constructor`, without re-running the `static` initializer.
8. `Feature.VALUE` is also not a constant variable. Reading the field triggers initialization of the `Feature` interface: `trace()` prints one line, and then the value `7` is printed.

**Why is “Same Class: true” reliable?** Both `Service` and `LoadingMomentsDemo` are defined from the same application code unit by the corresponding loader mechanism, and this loader returns the exact same `Class<?>` that `Service.class` represents. The program does not rely on JDK-dependent class loader names.

The program demonstrates **when the JVM is required to initialize** a class/interface; it does not attempt to claim that the bytecode of `Service` is read for the first time specifically at `Service.class`.

### Observing Actual Loading on HotSpot

With HotSpot JVM/JDK 17+, you can use Unified Logging:

```bash
java -Xlog:class+load=info LoadingMomentsDemo
```

The log lines tagged with type names and loading sources help identify when the JVM **records a load event**. This log output depends on the JDK, JVM, module/classpath configuration, and runtime; an implementation-dependent loading order cannot be treated as a program contract.

You can additionally use `javap -c -v LoadingMomentsDemo` to inspect symbolic references and bytecode instructions such as `ldc`, `getstatic`, `anewarray`, `new`, and `invokestatic`. This is a bytecode analysis tool and does not replace observing the JVM at runtime.

## 6. Key Distinction: Loading Is Not Initialization

A quick decision table:

| Syntax/operation | May need to load/link type T? | Must initialize T solely due to this operation? | Creates an instance of T? |
|---|---|---|---|
| `T.class` | Yes | **No** | No |
| `Class.forName("pkg.T", false, loader)` | Yes, explicitly requests lookup/loading/linking | **Not required** | No |
| `loader.loadClass("pkg.T")` | Yes, explicitly requests lookup/loading | **Not required** | No |
| `Class.forName("pkg.T")` | Yes | **Yes**, under this overload if not yet initialized | No |
| `new T()` where T is a concrete class | Yes | **Yes**, before object creation completes | **Yes** |
| `T.staticMethod()` where method is declared by T | Yes | **Yes**, if not yet initialized | No |
| `T.nonConstantStaticField` read/write, declared on T | Yes | **Yes**, if not yet initialized | No |
| `T.COMPILE_TIME_CONSTANT` | Not necessarily | **No** | No |
| `new T[10]` | May need component type and array type | **Does not** initialize component T | Does not create T; creates array instance |
| `value instanceof T` or cast `(T) value` | May need to resolve T | **No** | No |

**Note on “Yes” cells:** the table describes **the requirement when an operation needs a type**, without guaranteeing that every execution will trigger a new bytecode-reading event. The type may have already been loaded, linked, or initialized earlier.

**Note on `Class.forName`:** the descriptions above apply to the overloads explicitly shown in the table; the API also provides a module-based overload with its own semantics. Always check the exact method signature.

## 7. Common Misconceptions

1. **“Java loads every class on the classpath when running `main`.”** Incorrect: the classpath contains loadable candidates; execution/linking needs, libraries, and JVM strategy determine which definitions appear.
2. **“Reading a line with `T.class` definitely runs T's `static` block.”** False: obtaining a class literal by itself does not trigger initialization.
3. **“The JVM can only load a class strictly at its first use.”** False: the JVM is permitted to choose early loading/linking as long as observable semantics are preserved.
4. **“Loading a class always creates an object of T.”** False: loading creates the runtime type representation; an instance of T is a separate matter.
5. **“`ClassLoader.loadClass` and `Class.forName(String)` are the same.”** False with respect to initialization requirements under the overloads discussed.
6. **“Creating `new T[5]` is equivalent to five `new T()` calls.”** False: the array has default `null` slots; no T instance has been created.
7. **“Interfaces never initialize.”** False: accessing a non-constant field or calling a static method can trigger initialization of an interface.
8. **“Implementing an interface always initializes that interface.”** False: loading/linking the type relationship and initializing an interface are distinct; pay special attention to the rule for superinterfaces with default methods when a class initializes.
9. **“A single binary name corresponds to only one type across the entire JVM.”** False: the defining loader is part of a runtime type's identity.
10. **“A log line from a `static` block tells you the exact moment the class file was read.”** False: that log only reflects initialization.

## 8. Self-Check

**Question 1.** The JVM needs to evaluate `T.class` in a program, while `T` has not yet been initialized. Must `<clinit>` be called immediately?

**Answer:** No. The JVM may have to define or may have already defined T in order to provide `Class<?>`, but `T.class` alone is not a trigger to initialize T.

**Question 2.** Why is `Class.forName("pkg.Plugin", false, loader)` still useful if it does not create an instance?

**Answer:** Because it requests lookup/loading/linking to determine which loader's namespace the `Plugin` type exists in; the application can then inspect the type, metadata, constructors, or decide to create an object later.

**Question 3.** Given `interface I { int A = 10; int B = compute(); ... }`, do reading only `I.A` versus reading `I.B` produce the same initialization result?

**Answer:** No. `I.A` is a compile-time constant and can be inlined; `I.B` is not a constant variable, so accessing it directly triggers initialization of I.

**Question 4.** Does the code `new Widget[4]` require calling the `Widget()` constructor four times?

**Answer:** No. It creates an array of four reference elements, each initially `null`.

**Question 5.** The same `p.Widget`, yet two class loaders actually define two separate versions: is this a single type?

**Answer:** No. The JVM considers the binary name together with the defining loader to determine runtime type identity; two definitions are two distinct types.

## 9. Decision Map When Reading a Java Operation

```text
JVM encounters a reference to type T
            |
            v
Is type T already defined in the required loader?
        /                     \
       no                     yes
       |                       |
Find binary representation   Use existing definition
and define T                   |
       \                      /
        v                    v
    Verify/link/resolve as appropriate
                    |
                    v
     Does it trigger initialization of T?
             /              \
            no              yes
             |                |
    Use type information   Initialize T if needed
             |                |
             +--------+-------+
                      |
                      v
      Does it actually create an instance of T?
                 /          \
                no          yes
                |            |
        No T object      Create concrete object
```

Three useful questions when analyzing runtime behavior are: **Which type does the JVM need? Which loader defines that type? Which operation forces initialization or instance creation?** Answering these three questions separately prevents confusing the time of class loading with the time of running static initializers or constructors.

### Further Reading from Official Specifications

- [JVM Specification, 5.2–5.5: Startup; Creation and Loading; Linking; Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java Language Specification, 12.2–12.5: Loading; Linking; Initialization; Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html)
