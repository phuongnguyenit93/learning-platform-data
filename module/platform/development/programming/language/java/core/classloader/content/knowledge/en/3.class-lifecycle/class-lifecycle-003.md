# Loading Required Superclasses and Superinterfaces in the Java Class Lifecycle

## 1. Objective: Why Must Supertypes Be Loaded Before a Subclass Operates?

When the JVM creates a runtime definition for a Java class, finding that class's `.class` file is only the first step. The JVM must also establish **inheritance relationships**: which direct superclass this class has (`extends`), which direct superinterfaces it has (`implements`, or `extends` between interfaces), and whether they are valid. The required supertypes must be loaded according to JVM rules before the subclass definition can be created successfully.

Example:

```java
interface Auditable {}
interface Identified extends Auditable {}
class Entity {}
class Customer extends Entity implements Identified {}
```

When loading `Customer`, the JVM must process the direct superclass `Entity` and the direct interface `Identified`. To load `Identified`, the JVM must also process the superinterface `Auditable`. These relationships form a type dependency graph, not merely relationships between source files.

It is important to distinguish from the start:

- **Loading:** the JVM finds/creates the runtime representation of a class or interface from its binary definition, usually via a `ClassLoader`.
- **Linking:** verifying the definition, preparing static fields, and handling symbolic references according to JVM rules.
- **Initialization:** executing the static initialization of the class/interface (`<clinit>`, if present). **Loading a supertype does not mean its static initializer must run at that moment.**
- **Resolution:** converting symbolic references in the constant pool into runtime references. Not every class mentioned in methods, fields, or generics is required to be loaded at the exact same time as the subclass.

The focus of this article is direct dependencies from the **inheritance structure**: superclasses and superinterfaces.

## 2. What Metadata Tells the JVM Which Types Need to Be Loaded?

A `.class` file contains structural information, including:

| Class file component | Meaning for parent relationships |
| --- | --- |
| `this_class` | Binary identifier of the type being defined |
| `super_class` | Reference to the direct superclass of a normal class; for `java.lang.Object`, the index is 0 |
| `interfaces[]` | List of direct superinterfaces declared by the class/interface |
| `access_flags` | Indicates whether the definition is a class/interface, has `final`, `abstract`, etc., for validity checks |

A normal Java class (except `java.lang.Object`) has one superclass; if `extends` is not written in source code, the superclass is `java.lang.Object`. A class can `implements` multiple interfaces. An interface can `extends` multiple interfaces.

**Special detail about the class file:** in the class file format, the `super_class` of an interface records `java/lang/Object`, but that does not turn `Object` into a “superinterface” listed in `interfaces[]` and does not change interface inheritance rules in Java. When referring to “direct superinterfaces”, we mean the entries in `interfaces[]`.

A type definition contains many other references besides parent relationships: parameter types, return types, fields, local variables, annotations, and method bodies. Those references may require resolution at other times. One must not conclude that the JVM **always loads all** types appearing in bytecode immediately when loading a class.

## 3. Loading Order of Superclasses and Superinterfaces

According to the JVM class/interface creation model (JVMS §5.3), when a definition is created from bytecode, the JVM must establish direct relationships before completing the new definition. The logical sequence can be pictured as follows:

1. A loader receives a request to load a binary name, for example `com.example.Customer`.
2. The loader checks whether the class has been previously defined/accepted or locates the bytecode. With parent delegation, it may ask its parent loader first.
3. When the JVM creates the `Customer` definition, it uses metadata to identify `Entity` as the direct superclass and `Identified` as the direct superinterface.
4. The JVM requests loading of the required supertypes through the relevant loader rules; this operation continues recursively for the superclasses and superinterfaces of those supertypes themselves.
5. The JVM checks the relationships: a superclass cannot be an interface or a `final` class; an indicated superinterface must actually be an interface; inheritance relationships must not form a cycle.
6. Only when the corresponding conditions are satisfied can the JVM finish creating the runtime representation of the subtype. Linking and initialization still have their own rules/timing.

Example graph:

```text
Customer (class)
├── extends Entity (class)
│   └── extends java.lang.Object
└── implements Identified (interface)
    └── extends Auditable (interface)
```

The nodes in the direct and indirect inheritance branches are dependencies that need to be processed. This diagram **is not a guarantee of an absolute log order** across all JVMs: class loading may happen early due to the verifier, reflection, other code, or the linking process, and delegation may transfer defining responsibility to another loader. What is mandatory is that the relevant supertypes must be valid when the subtype definition succeeds.

### 3.1. The Superclass Must Be a Suitable Class

For `class Customer extends Entity`, the JVM needs to create/obtain the runtime type corresponding to `Entity`. `Entity` in turn has a superclass, normally ending at `java.lang.Object`. If `Entity` is not found or cannot be defined, loading `Customer` may also fail.

A Java class cannot extend a `final` class. The compiler usually blocks this directly, but the JVM must still guard validity when encountering invalid bytecode or incompatible binaries, potentially reporting `IncompatibleClassChangeError`.

### 3.2. Superinterfaces Are Also Dependencies of the Definition

For `class Customer implements Identified`, `Identified` must be loaded as an **interface**. If `Identified extends Auditable`, loading that interface must process `Auditable`. If a name listed as a superinterface resolves to a regular class, the JVM rejects the invalid structure and does not “auto-fix” the relationship.

An interface can `extends` multiple interfaces, and a class can `implements` multiple interfaces. Therefore, the graph is a branching structure, not just a linear list of superclasses.

### 3.3. There Is No Such Thing as “Initializing All Parents” During the Loading Phase

Loading establishes the type definition, whereas initialization runs static code. Therefore, seeing that the JVM has loaded a superinterface does not mean its static initializer output has been printed.

Distinguishing between **a parent class having been loaded** and **a parent class having been initialized** is an important skill when reading logs and troubleshooting errors.

## 4. Java 17+ Experiment: Loading Differs from Initialization

The program below shows that the JVM can obtain the `Class` of a subclass without running static initialization; when subclass initialization is triggered, the superclass and **superinterfaces declaring default methods** follow specific initialization rules. An interface that only declares a runtime constant without any default methods does not yet need to be initialized merely because a subclass `implements` it.

Save the entire code into `ParentLoadDemo.java`:

```java
public class ParentLoadDemo {

    interface Marker {
        // Not a compile-time constant: contains a method call.
        int VALUE = mark("Marker");

        static int mark(String name) {
            System.out.println(name + " initialized");
            return 1;
        }
    }

    interface Behavior {
        int VALUE = mark("Behavior");

        static int mark(String name) {
            System.out.println(name + " initialized");
            return 2;
        }

        // Interface with a default method.
        default String label() {
            return "demo";
        }
    }

    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent implements Marker, Behavior {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. Before load");

        Class<?> type = Class.forName(
                "ParentLoadDemo$Child",
                false,
                ParentLoadDemo.class.getClassLoader());

        System.out.println("2. Loaded: " + type.getSimpleName());
        System.out.println("3. Trigger Child initialization");

        Object instance = type.getDeclaredConstructor().newInstance();

        System.out.println("4. Child instance: " + (instance instanceof Child));
        System.out.println("5. Marker value: " + Marker.VALUE);
    }
}
```

Compile and run using JDK 17 or later:

```bash
javac ParentLoadDemo.java
java ParentLoadDemo
```

**Expected stdout:**

```text
1. Before load
2. Loaded: Child
3. Trigger Child initialization
Parent initialized
Behavior initialized
Child initialized
4. Child instance: true
Marker initialized
5. Marker value: 1
```

Reading the results:

- `Class.forName(name, false, loader)` retrieves the `Child` definition without requesting initialization of `Child`. Retrieving its name with `getSimpleName()` also does not trigger `<clinit>` of `Child`.
- Creating an instance via reflection is an **active use** of `Child`; the JVM must initialize this type before instantiating the object.
- Before initializing `Child`, the JVM initializes its superclass `Parent` and the relevant superinterfaces **that declare default methods** according to JLS/JVMS rules; here `Behavior` is initialized.
- `Marker` does not declare any default methods, so it does not have to be initialized simply because `Child implements Marker`.
- When the expression `Marker.VALUE` is actually read, `VALUE` is a `static final` value computed by a method call (not a constant expression), causing `Marker` to initialize in the final step.
- `(instance instanceof Child)` only checks the object's type; it is not the reason that caused the earlier initialization lines.

**Note:** this example observes **initialization timing**, not all loading timing. Not seeing the `Marker initialized` line at step 2 does not prove that `Marker` has not been *loaded*; it only proves that its static initialization code has not yet run.

## 5. Initialization Rules by Parent Relationship: Classes and Interfaces Differ

When **initializing a class** `C`, the JVM initializes any not-yet-initialized superclasses and relevant superinterfaces **that declare default methods** according to the ordering rules of JLS §12.4.2/JVMS §5.5, before running the initialization code of `C`. Indirectly inherited interfaces may also be involved through that recursive rule. One must distinguish **declaring a default method** from merely inheriting a default method from a superinterface; the specific order must follow the specification's definition, rather than being inferred from the order of JAR files.

When **initializing an interface**, the JVM is not required to automatically initialize all of its superinterfaces in the way a class's superclasses are initialized. Interface initialization typically occurs when there is an active use of that interface itself or under other conditions defined by the specification.

| Action | Must superclasses/superinterfaces be loaded? | Immediate static initialization? |
| --- | --- | --- |
| Defining `Child extends Parent implements Marker` | Must process the corresponding parent dependencies to define `Child` | Does not imply running `<clinit>` |
| `Class.forName("Child", false, loader)` | Requires finding/loading/linking `Child` along with required structural dependencies | Does not actively initialize `Child` |
| `new Child()` (first use) | Relevant types must be ready | Initializes `Parent`, interfaces with default methods per the rules, then `Child` |
| Reading `Marker.VALUE` (not a constant expression) | `Marker` must have a valid definition | Initializes `Marker` if not yet initialized |
| Reading `SomeInterface.CONST = 10` | May be inlined by the compiler as a compile-time constant | Not sufficient to conclude the interface will be initialized |

You should not use `System.out.println` inside a static initializer as evidence of **loading order**, because it shows **initialization order**. To observe loading, use dedicated logging or JVM diagnostic tools.

## 6. Which ClassLoader Loads Supertypes?

A class is defined by loader `L`, yet its superclass or superinterface **does not necessarily share the same defining loader**. When the JVM resolves structural dependencies for `C`'s definition, it uses the loader dictated by `C`'s resolution rules, and that loader may then delegate to its parent.

Plugin system example:

```text
ApplicationLoader
├── api.Plugin       (shared interface)
└── api.Result       (shared result type)
      ↑
      ├── PluginLoaderA ── impl.PluginA implements api.Plugin
      └── PluginLoaderB ── impl.PluginB implements api.Plugin
```

If `impl.PluginA` is defined by `PluginLoaderA` and `api.Plugin` is defined by `ApplicationLoader`, the `implements` relationship is still valid: the subclass's loader can request the supertype and receive the `Class` defined by the parent loader.

However, if the plugin's loader defines its own copy of `api.Plugin` separate from the host's copy, the two interfaces may have the same name yet **different type identities**. When the host casts an `impl.PluginA` object to the host's `api.Plugin`, the cast can fail even though the plugin “already implements Plugin”.

The runtime identity of a type is determined by **(binary name, defining loader)**. The distinction between **initiating loader** (requesting the load) and **defining loader** (actually defining the class) explains why two different plugins can still share a single superinterface.

### 6.1. Parent Delegation Does Not Mean the Parent Automatically Sees Child Classes

A child loader typically asks its parent loader first under the parent-first mechanism, but the parent loader does not automatically look down into every child loader. When the host defines `api.Plugin`, the plugin loader can share that interface; conversely, the host cannot automatically load every `impl.PluginA`.

A custom class loader can be designed as child-first or with selective delegation. Whichever approach is chosen, **shared APIs/SPIs** at the host–plugin boundary generally require the same defining loader to preserve type compatibility.

### 6.2. The JVM Checks Loader Constraints When Linking Types

Rather than merely comparing names and attempting casts, the JVM also enforces **loading constraints** in linking scenarios that require ensuring type consistency across loaders. If the same name appears in method signatures across linked types with conflicting runtime definitions, the JVM may report `LinkageError` (for example, `loader constraint violation`).

You should not try to fix the error by arbitrarily forcing two plugins onto the same classpath; instead, identify **which types must be shared** and **which types should actually be isolated**.

## 7. What Happens If a Supertype Cannot Be Loaded?

An easily overlooked point is that an application may be able to load the bytecode of `Child.class` and still **fail to define `Child` validly** because `Parent.class` or a superinterface is missing or invalid.

### Scenario 1: Missing Superclass at Runtime

```java
// Parent.java
public class Parent {}
```

```java
// Child.java
public class Child extends Parent {}
```

Both files compile successfully if they are on the same classpath. Suppose, however, that at deployment only `Child.class` is present while `Parent.class` is no longer on the path used by the class loader: the first attempt to load `Child` may report `NoClassDefFoundError: Parent` (often with a `ClassNotFoundException` in the underlying cause).

Point to check: **a message naming Parent** does not necessarily mean your code directly requested loading `Parent`; it may be a mandatory inheritance dependency of `Child`.

### Scenario 2: Missing a Superinterface

```java
// Auditable.java
public interface Auditable {}
```

```java
// Child.java
public class Child implements Auditable {}
```

When the runtime cannot find `Auditable`, `Child` likewise cannot have its type definition created successfully under the `implements` relationship. This issue occurs even if the application **has not called a single method** of `Auditable`.

### Scenario 3: Invalid Bytecode or Incompatible Version Changes

Some typical errors:

| Symptom | What to Consider |
| --- | --- |
| `NoClassDefFoundError: Parent` | A superclass/superinterface or required dependency is unavailable when the JVM needs it; can also be related to a previous failed initialization—read the cause |
| `ClassNotFoundException` | A load-by-name API could not find the requested type; distinct from `NoClassDefFoundError` caused by dependency linking/definition |
| `IncompatibleClassChangeError` | Bytecode expects a class while the runtime provides an interface, or vice versa; invalid inheritance from a `final` class also belongs to this error group |
| `ClassCircularityError` | Superclass/superinterface relationships form an invalid cycle during loading |
| `VerifyError` | The JVM verifier detects bytecode that fails to meet type-safety requirements or related constraints |
| `LinkageError` with `loader constraint violation` | Two loaders define incompatible types in a relationship that requires consistency |
| `ExceptionInInitializerError` | Execution has already entered **initialization** and a static initializer failed; not conclusive proof that superclass loading failed |

**Classification warning:** `ClassNotFoundException` is a checked exception that can occur when calling `Class.forName` for the **requested name**; `NoClassDefFoundError` is a `LinkageError` that usually indicates the JVM cannot use an expected dependency definition. These two types must not be handled by catching only one and guessing which class is broken.

### Example: Checking Dependencies at Runtime

You do not need to write a custom class loader to observe a missing-superclass scenario. In a test environment:

1. Compile both `Parent.java` and `Child.java`: `javac Parent.java Child.java`.
2. Move `Parent.class` out of **the test process's classpath**, without touching the real deployment.
3. Request loading `Child` via `Class.forName("Child", false, loader)`.
4. Inspect the `Throwable` chain, especially the missing class name and the nested cause in `Caused by`.
5. Restore the proper dependency file/class before continuing testing.

The steps above are only a described test scenario and do not have a fixed stdout applicable to every loader/JVM configuration.

## 8. Order of Loading, Linking, Initialization, and Resolution: Do Not Conflate Them

Consider the relationships:

```java
interface Audit {}
class Root {}
class Order extends Root implements Audit {
    static Helper helper;
}
class Helper {}
```

Key distinctions to keep clear:

1. To create the runtime definition of `Order`, the JVM must process `Root` and `Audit` as its **direct supertypes**.
2. The fact that `Order` has a field `Helper helper` does not allow inferring that `Helper` **must be initialized** together with `Order`. Resolution of the `Helper` reference may happen at a different time, depending on demand and the JVM.
3. `Root` may already have been loaded earlier by other code; when loading `Order`, the JVM reuses the existing definition from the appropriate loader instead of defining a duplicate type.
4. If `Order` is initialized, its superclass `Root` must be initialized first; `Audit` is **not necessarily** initialized if it does not satisfy the interface initialization conditions.
5. The **verify** and **resolve** processes may require the JVM to process additional types beyond the direct supertypes. Therefore, “superclasses and superinterfaces are required” does not mean “only they can be loaded at that time”.

### Visualizing Along Two Axes

```text
Structural dependencies:
Order ──extends──> Root ──extends──> Object
   └──implements──> Audit

Lifecycle phases of each type:
Loading ──> Linking [verify → prepare → resolve when appropriate] ──> Initialization
             (resolution may be performed early or late)
```

Structural relationships indicate **which types are needed to define a class**; lifecycle phases indicate **what actions the JVM performs on each type**. The two axes must be analyzed separately.

## 9. How to Diagnose a Missing Superclass or Superinterface

When encountering class loading errors in a large application, follow this sequence instead of merely adding JARs at random:

1. **Identify the class being requested for loading.** Record the binary name in `Class.forName`, `ClassLoader.loadClass`, the stack trace, or the object instantiation site.
2. **Read the entire exception chain.** Distinguish the requested `Child` name from the missing `Parent`/interface name in the cause.
3. **Inspect the `extends` and `implements` definitions.** You can use `javap -p -verbose Child.class` to view `super_class` and `interfaces` in bytecode, even when source code is no longer available.
4. **Verify the process's actual classpath/module path.** A JAR file existing on disk does not prove that the current loader has access to it.
5. **Check the loader and delegation.** Print `clazz.getClassLoader()` for classes that did load, and identify the parent loader and the set of URLs/JARs of any custom plugin loader.
6. **Monitor loading logs.** With HotSpot/JDK 17+, you can run `java -Xlog:class+load=info ...` to see which source various classes are loaded from. Class-load logs and `<clinit>` output lines do not carry the same meaning.
7. **If the error involves modules**, check readability and exports/opens depending on the situation. These are additional constraints; they do not eliminate supertype loading requirements.
8. **If there is a version conflict**, compare the compiled JAR against the runtime JAR; pay particular attention to a class changing from an interface to a class, changing its superclass, or changing its implements relationships.
9. **Check hot-reload/plugin-reload scenarios.** A new loader may define a new `Child`, while the host still retains an interface or instance from the old loader; check the runtime type identity and any references retaining the old loader.

For types that have already been loaded, the following helper snippet provides clues:

```java
static void inspect(Class<?> type) {
    System.out.println("Type: " + type.getName());
    System.out.println("Loader: " + type.getClassLoader());
    Class<?> parent = type.getSuperclass();
    System.out.println("Superclass: " +
            (parent == null ? "<none>" : parent.getName()));
    for (Class<?> iface : type.getInterfaces()) {
        System.out.println("Direct interface: " + iface.getName());
    }
}
```

This is a **helper method**—place it in a running class and call `inspect(SomeType.class)`. `getInterfaces()` returns the **direct** interfaces; to view the transitive closure, you must also traverse the superinterfaces of each interface. `getSuperclass()` returns `null` for `Object`, interfaces, and certain special types such as primitives/arrays per the API; that is not evidence that class loading failed.

## 10. Common Misconceptions

- **“Having `Child.class` present is enough to load `Child`.”** False if a direct or indirect superclass/superinterface cannot be loaded.
- **“The JVM only loads the superclass, not superinterfaces.”** False: direct superinterfaces and their superinterface chains are also structural relationships that must be processed.
- **“Loading a superinterface means its static fields are already initialized.”** False: loading and initialization are different; the default method rule only governs certain class initialization scenarios.
- **“No object has been created yet means the parent has not been loaded.”** False: the JVM may load/link classes prior to active use, especially through reflection or the verifier.
- **“Whenever an interface has a default method, loading `Child` immediately runs its initializer.”** False: triggering class initialization is what involves the superclass/superinterface initialization rules; loading alone does not trigger it.
- **“Having the same interface name is enough for `implements` across plugins.”** False: the same runtime type identity is required, including the defining loader.
- **“A missing superclass must produce `ClassNotFoundException`.”** Frequently `NoClassDefFoundError` may appear for the dependency; you must inspect the full cause.
- **“Every type appearing in field/method declarations must be loaded immediately along with the subclass.”** False: inheritance structure dependencies and the resolution of other references have their own mechanisms and timing.

## 11. Self-Check Questions

**1. `class Invoice extends Document implements Serializable`: when loading `Invoice`, which types are structural dependencies?**

`Document` (and the required superclass chain) and `Serializable` (along with any relevant superinterfaces, if present). `java.lang.Object` appears at the top of the class chain except for `Object` itself.

**2. Does a successful `Class.forName("Invoice", false, loader)` guarantee that `static { ... }` in `Document` has already executed?**

No. Loading and linking differ from initialization. The `false` argument requests not actively initializing the selected class; if a type was already initialized by a prior action, the API does not undo that state.

**3. What if `Invoice implements A, B`, `B extends C`, and `C` disappears from the runtime?**

`B` cannot be considered a complete interface when its required superinterface is missing, so loading `Invoice` may fail when resolving the structural dependency chain.

**4. Interface `Feature` has been loaded, yet `Feature`'s initializer has not run. Is there a contradiction?**

No. An interface can be loaded before it is initialized. Initializing a class that implements `Feature` does not necessarily initialize `Feature` if `Feature` does not declare any default methods and has not been used in another way that triggers initialization.

**5. Both plugins `implements api.Plugin`; why can a plugin fail to cast to the host's `api.Plugin`?**

Because `api.Plugin` in one plugin may have been defined separately by a different loader, creating a distinct runtime type. The host and plugins need to agree on an API/SPI interface defined by a shared loader.

## 12. Conclusion and Reference Materials

To define a valid class/interface, the JVM must process the **superclasses and superinterfaces declared by metadata** along with recursive inheritance dependencies, checking the validity of those relationships within the class loader environment. This belongs to **loading/creation** and relates to **linking**; it is not equivalent to running **initialization** for all supertypes.

When encountering a subclass loading error, start with three questions: **which supertypes are required, which loader is searching for/defining that type, and did the error occur during loading, linking, or initialization?**

Authoritative documentation for deeper reading:

- *Java Virtual Machine Specification*, §5.3 “Creation of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Virtual Machine Specification*, §5.4 “Linking”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- *Java Virtual Machine Specification*, §5.5 “Initialization”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- *Java Language Specification*, §12.4 “Initialization of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
