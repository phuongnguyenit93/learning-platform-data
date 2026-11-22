# Bootstrap Loader, Hidden Classes, and Array Classes in Inspection Results

> **Key takeaway:** `Instrumentation.getAllLoadedClasses()` does not only return application classes with ordinary binary names. The JVM snapshot can also contain classes loaded by the **bootstrap loader**, **hidden classes**, and **array classes**. All of these objects are represented by `Class<?>`, but they differ in **discoverability by name, class loader association, lifecycle, and modifiability**. In particular, appearing in the loaded list **does not mean** a class can be passed to `retransformClasses` or `redefineClasses`.

This lesson belongs to the **Runtime Inspection** section in Java Advance – instrumentation. The goal is to accurately interpret data collected from an agent, avoid misclassifying classes with a `null` loader, distinguish hidden classes from arrays of hidden classes, and verify the behavior yourself with a runnable Java 17+ application with a startup agent.

## 1. Correctly Understanding “Currently Loaded Classes”

When the JVM passes an `Instrumentation` object to `premain` or `agentmain`, the agent can request:

~~~java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
~~~

This is an **illustrative API snippet** inside an agent that already has the `Instrumentation instrumentation` variable, not a standalone Java file. According to Java SE 17, the returned array consists of **currently loaded classes and interfaces**, including **hidden classes/interfaces** and **array classes of all kinds**.

Examples of names that may appear in an inspection tool's log:

~~~text
java.lang.String
java.lang.Object
SurveyApp
HiddenSample/0x000000...
[I
[[I
[Ljava.lang.String;
[LHiddenSample/0x000000...;
~~~

The `0x000000...` suffix above is only an **illustration** of a hidden class name, not a stable ID or the example's stdout value. Strings like `[I` or `[Ljava.lang.String;` are the array name forms returned by `Class.getName()`, not `.class` filenames on disk.

A snapshot is a point-in-time slice:

- It does not mean **every `.class` file on the classpath/module path has been loaded**.
- It does not mean every class in the snapshot **can be found again by name via `ClassLoader.loadClass(name)`**.
- It does not mean these classes all have bytecode supplied by a separate `.class` file (array types are a counterexample).
- It does not mean all of them can be modified via `retransformClasses`/`redefineClasses`.
- It does not provide a stable class order, an invariant count, or a live-maintained list until the JVM shuts down.

From finding a `Class<?>`, we must separate at least four questions: **what kind of class is it**, **which loader**, **is it discoverable by name**, and **is it modifiable**. Collapsing all four questions into a single `isLoaded` variable will make reports inaccurate.

## 2. `getAllLoadedClasses` and `getInitiatedClasses` Are Two Different Views

Java Instrumentation provides two commonly compared APIs:

~~~java
Class<?>[] all = inst.getAllLoadedClasses();
Class<?>[] initiatedByApp = inst.getInitiatedClasses(appLoader);
Class<?>[] initiatedByBootstrap = inst.getInitiatedClasses(null);
~~~

This is an **illustrative snippet**; `inst` and `appLoader` must be valid variables in the agent/app. In Java SE 17:

| API | What does it answer? | Limitations not to forget |
| --- | --- | --- |
| `getAllLoadedClasses()` | Which `Class<?>` objects is the JVM currently recording as loaded? | Includes hidden and array classes; does not require a discoverable name |
| `getInitiatedClasses(loader)` | Which classes is `loader` recorded as the **initiating loader** for, discoverable by name through the load/linkage mechanism? | **Does not** include hidden classes/interfaces or arrays with a hidden element type |
| `Class.getClassLoader()` | The loader associated with a class object, which may be `null` | `null` does not only occur for named bootstrap classes |
| `Class.isHidden()` | Is the class actually a hidden class? | Do not guess based on a class name substring |
| `Class.isArray()` | Does `Class<?>` represent an array type? | Arrays also have a `Class<?>` even without a separate class file |
| `isModifiableClass(clazz)` | Can this class's definition be modified under the instrumentation contract? | Different from presence in the inventory |

**`Initiating loader` is not always the `defining loader`.** A loader can find a class by **delegating to a parent loader**; that loader is called the initiating loader in a linkage process, while the class is actually defined by the parent. Therefore, `getInitiatedClasses(loader)` should not be described simply as “all classes defined by this loader itself”.

With `getInitiatedClasses(null)`, the `null` argument represents the **bootstrap class loader**: the result is the classes that the bootstrap loader can find by name according to the API contract.

Specifically:

- **Hidden class**: can appear in `getAllLoadedClasses()` but **not** in any `getInitiatedClasses(loader)`.
- **Array of a hidden class**: can also appear in all-loaded, but **not** in the initiated list because its element type is hidden.
- **Array with an ordinary element type**: may appear in the appropriate initiated list, depending on whether the runtime has created/recorded that array type.

Comparing counts between the two APIs **is not a subtraction to count “missing” classes**. The two APIs serve two different questions.

## 3. Bootstrap Loader: Why `getClassLoader() == null` Is Not Enough

### 3.1. Built-in loader hierarchy

On typical OpenJDK/HotSpot, the system has bootstrap, platform, and application/system class loaders:

~~~text
Bootstrap loader           (usually represented by null)
    |
    v
Platform class loader      (ClassLoader object)
    |
    v
Application class loader   (ClassLoader object)
    |
    v
Custom/plugin loaders      (depending on architecture and delegation policy)
~~~

This is a common diagram, **not a requirement that every custom loader always uses linear parent-first delegation**. Some frameworks/containers create multiple loaders and different policies.

JDK example:

~~~java
System.out.println(String.class.getClassLoader() == null);
System.out.println(Object.class.getClassLoader() == null);
~~~

These two statements are an **illustrative code snippet**; on typical OpenJDK/HotSpot they print `true` and `true`. Do not infer that every class whose name starts with `java.` is loaded by the bootstrap loader; you must also check the platform loader and the corresponding modules.

### 3.2. Other `null` cases

| `Class<?>` object | Typical `getClassLoader()` | Explanation |
| --- | --- | --- |
| `String.class` | `null` | Named class belonging to bootstrap |
| `Object.class` | `null` | Named class belonging to bootstrap |
| `int.class` | `null` | Primitive type with no ordinary defining class loader |
| `void.class` | `null` | The `void` type, not a normal classfile |
| `int[][].class` | `null` | Array of primitive, not a named bootstrap classfile |
| `String[].class` | `null` | Array whose element type `String` belongs to bootstrap |
| `SurveyApp.class` | Usually non-null | Application class |

The Java `ClassLoader` Javadoc states that **array classes are created automatically by the runtime**, not directly by `ClassLoader.defineClass`. The loader reported by `Class.getClassLoader()` for an array is the loader of its **element type**, and arrays of primitives have a `null` loader.

Therefore, you **must not** do:

~~~java
// Illustrative snippet of INCORRECT counting:
if (type.getClassLoader() == null) {
    bootstrapNamedClasses++;
}
~~~

The snippet above lumps both arrays and primitives into the count of named bootstrap classes. To count named bootstrap classes, check `isArray()`, `isHidden()`, and `isPrimitive()` **before** checking for a null loader.

### 3.3. Can bootstrap classes be modifiable?

`getClassLoader() == null` **does not automatically imply** `isModifiableClass(type) == false`. A named bootstrap class may be allowed by the VM to have its definition modified, depending on the specific JVM/capability/class. Retransforming also requires `isRetransformClassesSupported()`.

However, modifying JDK classes is a very sensitive operation: it can affect logging, serialization, class loading, module visibility, and the JVM runtime. An instrumented method inside a bootstrap class **does not by default see helpers located on the application classpath**. The presence of a bootstrap class in inspection results **is not a recommendation to modify it**.

## 4. Hidden Classes: The JVM Knows the Class, but Loaders Cannot Find It by Binary Name

### 4.1. How are hidden classes created?

Hidden classes are a Java 15+ mechanism (JEP 371), used by runtimes/frameworks for implementation classes that do not need to be discovered via an ordinary binary name. Java 17 supports creating them via `MethodHandles.Lookup.defineHiddenClass(...)`.

Example:

~~~java
byte[] classFile = Files.readAllBytes(Path.of("HiddenSample.class"));
Class<?> hidden = MethodHandles.lookup()
        .defineHiddenClass(classFile, false)
        .lookupClass();
~~~

This is an **illustrative snippet**, requiring appropriate imports and lookup. The complete example in section 7 uses `HiddenSample` and `SurveyApp` in the same runtime package/module, ensuring valid lookup permissions. The `false` argument means **do not require immediate initialization** in this operation; the class is still **defined** by the JVM and already has a `Class<?>`.

A hidden class:

- Has a real `Class<?>` object and can be accessed via reflection/lookup on that reference itself.
- `isHidden() == true`; this is the right way to classify it.
- `getName()` on Java 17+ has a suffix containing `/` (e.g., of the form `HiddenSample/0x...`); **it is not a binary name that can be passed to `Class.forName` to discover it**.
- `getCanonicalName()` typically returns `null`, as tested in the demo; this is not a data error.
- Has a loader/module associated with the lookup class per API rules, but the loader cannot find it via an ordinary binary name.
- Can appear in `getAllLoadedClasses()`, yet is excluded from `getInitiatedClasses(loader)`.
- Is not modifiable by standard Java agent/JVM TI redefine/retransform mechanisms.

Importantly: **loaded ≠ name-discoverable ≠ modifiable**. A class can satisfy the first condition without satisfying the other two.

### 4.2. Why a hidden name is not a “full class name” to cache

Suppose the log shows:

~~~text
HiddenSample/0x000000...
HiddenSample/0x000000...
~~~

The two lines above are only **illustrative samples** of the prefix; the JVM-generated suffix may differ. Do not strip the suffix and use `HiddenSample` as a unique ID: there can be multiple **distinct** hidden classes originating from the same classfile or similar framework logic.

If you need to identify a class at **runtime**, use the `Class<?>` object itself and its loader/module. If exporting long-term reports, use a system-assigned session/deployment ID, and avoid holding strong references to every hidden `Class<?>` in an agent's static map, which would prevent the class from being unloaded.

### 4.3. Hidden classes and GC lifecycle

Without `MethodHandles.Lookup.ClassOption.STRONG`, a hidden class can be unloaded **while its defining loader is still reachable**, if other references allow it. If a hidden class is created with `ClassOption.STRONG`, it has a strong relationship with its loader similar to a normal named class.

Therefore, the count of hidden classes between two snapshots can change due to the runtime generating more or class unloading. **Not seeing a hidden class in a later snapshot** does not by itself prove the earlier API call was wrong. Conversely, **seeing a hidden class in a snapshot** does not mean it will live until the end of the process.

A note when testing GC: a local `hidden` variable, a `Class<?>[]` snapshot, a method handle, or a static cache still holding the class can change unloading conditions. Do not use a single `System.gc()` call to “prove” whether a class has or has not unloaded; GC has no guaranteed deadline.

### 4.4. Hidden classes cannot be modified by retransforming like named classes

In an OpenJDK test run:

~~~text
hidden-in-all=true
hidden-in-app-initiated=false
hidden-modifiable=false
~~~

Even though the JVM has loaded/defined the hidden class, `isModifiableClass(hidden)` is still false. **Do not** pass hidden classes from `getAllLoadedClasses()` directly into `retransformClasses(...)`. If a framework needs instrumented code inside a hidden class, it must design the byte generation appropriately **before the class is defined**, rather than relying on hot-retransforming an existing hidden definition.

## 5. Array Classes: Types That Have `Class<?>`, but No Separate `.class` File

### 5.1. Array types and naming

Example:

~~~java
Class<?> one = int[].class;
Class<?> two = int[][].class;
Class<?> three = String[].class;
~~~

each type has its own `Class<?>`. They are **array types created by the runtime** as needed, not class-file definitions like `int[].class` on disk. How to inspect them:

~~~java
System.out.println(int[][].class.isArray());                 // true
System.out.println(int[][].class.getComponentType() == int[].class); // true
System.out.println(int[].class.getComponentType() == int.class);     // true
~~~

These are illustrative statements that can be placed in `main`. For multidimensional arrays, `getComponentType()` **strips only one array dimension**; to reach the final element type, loop until `!type.isArray()`.

Common `Class.getName()` forms:

| Type | Name from `getName()` |
| --- | --- |
| `int[].class` | `[I` |
| `int[][].class` | `[[I` |
| `String[].class` | `[Ljava.lang.String;` |
| `String[][].class` | `[[Ljava.lang.String;` |
| `SurveyApp[].class` | `[LSurveyApp;` when the class is in the default package |

A name starting with `[` is **normal**, not a parse error. Do not try to read a file named `[I.class` or confuse `[` with a class in source code.

### 5.2. Arrays of hidden classes

You can create an array class whose element type is a hidden `Class<?>`:

~~~java
Class<?> arrayOfHidden = java.lang.reflect.Array.newInstance(hidden, 0).getClass();
~~~

This is an **illustrative code snippet**, with `hidden` already created as in the previous section. Length 0 is still enough for the JVM to create the array type and return an array object, from which we get `Class<?>`.

Interesting facts:

- `arrayOfHidden.isArray()` is `true`.
- `arrayOfHidden.getComponentType() == hidden` is `true` for a one-dimensional array.
- `arrayOfHidden` is in `getAllLoadedClasses()` if that type has been created and is currently loaded; the demo prints `true`.
- **Not present** in `getInitiatedClasses(appLoader)` because the element type is a hidden class.
- `isModifiableClass(arrayOfHidden)` is `false` because it is itself an **array class**.

To classify an array of a hidden class, **do not** only call `arrayOfHidden.isHidden()`: that is a check on the **array class itself**, not its hidden element. Loop `getComponentType()` down to the **final element type** and check `isHidden()` on the element.

### 5.3. Arrays and primitives are not modifiable

Java SE 17 specifies that `Instrumentation.isModifiableClass()` returns `false` for **primitive and array classes**. This property is independent of whether an array element belongs to a modifiable named class.

~~~java
inst.isModifiableClass(int.class);      // false
inst.isModifiableClass(int[][].class);  // false
inst.isModifiableClass(String[].class); // false
~~~

The snippet above requires `Instrumentation inst`; it is not a standalone file. Having the `Can-Retransform-Classes: true` capability also **does not turn** array/primitive classes into modifiable targets.

**Do not misunderstand:** arrays appearing in a survey are completely valid, but they are not suitable as targets for redefine/retransform. For an application method that needs instrumentation, choose the named class containing that method and check class eligibility separately.

## 6. A Clear Classifier Without Relying on Names

A sensible order to classify a `Class<?>`:

~~~text
Class<?> type
    |
    +-- type.isArray()? ---- YES -> find final element type
    |                               +-- isHidden()     -> ARRAY_OF_HIDDEN
    |                               +-- isPrimitive()  -> ARRAY_OF_PRIMITIVE
    |                               +-- other          -> ARRAY_OF_NAMED
    |
    +-- type.isHidden()? --- YES -> HIDDEN
    |
    +-- type.isPrimitive()? YES -> PRIMITIVE_OR_VOID
    |
    +-- loader == null? ---- YES -> NAMED_BOOTSTRAP
    |
    +-- remaining ----------------> NAMED_NON_BOOTSTRAP
~~~

An illustrative Java method:

~~~java
static String category(Class<?> type) {
    if (type.isArray()) {
        Class<?> element = type;
        while (element.isArray()) {
            element = element.getComponentType();
        }
        if (element.isHidden()) return "ARRAY_OF_HIDDEN";
        if (element.isPrimitive()) return "ARRAY_OF_PRIMITIVE";
        return "ARRAY_OF_NAMED";
    }
    if (type.isHidden()) return "HIDDEN";
    if (type.isPrimitive()) return "PRIMITIVE_OR_VOID";
    if (type.getClassLoader() == null) return "NAMED_BOOTSTRAP";
    return "NAMED_NON_BOOTSTRAP";
}
~~~

This is a method that can be placed in a utility class; **not yet a standalone program**. The benefit of this order is that `int[][].class` is not misrecorded as a named bootstrap class just because `getClassLoader() == null`.

Summary table:

| Class kind | `getAllLoadedClasses()` | `getInitiatedClasses()` | `isModifiableClass()` |
| --- | --- | --- | --- |
| Named bootstrap (e.g., `String`) | Yes if currently loaded | In bootstrap set when discoverable | **Depends on class and JVM** |
| Named application class | Yes if currently loaded | In appropriate initiating loader | **Depends on class and JVM** |
| Hidden class | Yes if currently loaded | **No** | **False** under standard agent/JVM TI |
| Array of primitive | Yes if created/loaded | Depends on runtime discoverability/conditions | **False** |
| Array of named class | Yes if created/loaded | May be in appropriate initiated set | **False** |
| Array of hidden element | Yes if created/loaded | **No** | **False** |
| Primitive and `void` | Has `Class<?>` representation, but not a normal named classfile | Not used like named-class lookup | **False** |

The table is a **rule for interpreting data kinds**, not a promise about the counts/names of classes present in every JVM session.

## 7. Running Java 17+ to See Bootstrap, Hidden, and Array Classes Together

This is a **complete** example using a startup Java agent to receive `Instrumentation`, after which the application actively creates a hidden class and several array types, then takes both kinds of snapshots. No libraries outside the JDK are needed.

### 7.1. File `SurveyAgent.java`

~~~java
import java.lang.instrument.Instrumentation;

public final class SurveyAgent {
    private static Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent=ready");
    }

    public static Instrumentation instrumentation() {
        return instrumentation;
    }
}
~~~

In the demo, the agent only provides `Instrumentation` for the application to inspect itself. The agent **does not** modify bytecode, and letting application code call into the agent like this is for illustration; production needs proper authorization and lifecycle policies.

### 7.2. File `HiddenSample.java`

~~~java
public final class HiddenSample {
    public String value() {
        return "hidden";
    }
}
~~~

This classfile is generated by `javac` and then read by `SurveyApp` **as data bytes**. Do not call `new HiddenSample()` in the demo program: the goal is to create a **hidden version** via `Lookup.defineHiddenClass`, not to test a regular class loaded by name by the app loader.

### 7.3. File `SurveyApp.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SurveyApp {
    private static boolean contains(Class<?>[] classes, Class<?> target) {
        for (Class<?> candidate : classes) {
            if (candidate == target) return true;
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("HiddenSample.class"));
        Class<?> hidden = MethodHandles.lookup().defineHiddenClass(bytes, false).lookupClass();
        Class<?> hiddenArray = Array.newInstance(hidden, 0).getClass();
        Class<?> intArray = int[][].class;
        Class<?> stringArray = String[].class;
        Class<?> app = SurveyApp.class;
        Class<?> bootstrap = String.class;

        Instrumentation inst = SurveyAgent.instrumentation();
        Class<?>[] all = inst.getAllLoadedClasses();
        Class<?>[] initiatedByApp = inst.getInitiatedClasses(app.getClassLoader());
        Class<?>[] initiatedByBootstrap = inst.getInitiatedClasses(null);

        System.out.println("bootstrap-loader-null=" + (bootstrap.getClassLoader() == null));
        System.out.println("bootstrap-in-all=" + contains(all, bootstrap));
        System.out.println("bootstrap-in-bootstrap-initiated=" + contains(initiatedByBootstrap, bootstrap));
        System.out.println("app-loader-nonnull=" + (app.getClassLoader() != null));
        System.out.println("app-in-all=" + contains(all, app));
        System.out.println("app-in-app-initiated=" + contains(initiatedByApp, app));
        System.out.println("hidden-isHidden=" + hidden.isHidden());
        System.out.println("hidden-name-has-slash=" + hidden.getName().contains("/"));
        System.out.println("hidden-canonical-null=" + (hidden.getCanonicalName() == null));
        System.out.println("hidden-in-all=" + contains(all, hidden));
        System.out.println("hidden-in-app-initiated=" + contains(initiatedByApp, hidden));
        System.out.println("hidden-modifiable=" + inst.isModifiableClass(hidden));
        System.out.println("int-array-isArray=" + intArray.isArray());
        System.out.println("int-array-loader-null=" + (intArray.getClassLoader() == null));
        System.out.println("int-array-in-all=" + contains(all, intArray));
        System.out.println("int-array-modifiable=" + inst.isModifiableClass(intArray));
        System.out.println("string-array-in-all=" + contains(all, stringArray));
        System.out.println("string-array-loader-null=" + (stringArray.getClassLoader() == null));
        System.out.println("hidden-array-isArray=" + hiddenArray.isArray());
        System.out.println("hidden-array-in-all=" + contains(all, hiddenArray));
        System.out.println("hidden-array-in-app-initiated=" + contains(initiatedByApp, hiddenArray));
        System.out.println("hidden-array-modifiable=" + inst.isModifiableClass(hiddenArray));
        System.out.println("primitive-modifiable=" + inst.isModifiableClass(int.class));
    }
}
~~~

**Why does the lab have these steps?**

1. `Files.readAllBytes(Path.of("HiddenSample.class"))` reads the exact bytes of the compiled class.
2. `Lookup.defineHiddenClass(bytes, false)` creates a hidden `Class<?>` in the same runtime package/module as the lookup class.
3. `Array.newInstance(hidden, 0)` creates an array class with a hidden element, even though the array has length 0.
4. The `int[][].class` and `String[].class` types ensure specific array test samples exist before taking the snapshot.
5. `contains(...)` compares **the same `Class<?>` object using `==`**, not by name. Different hidden suffixes will not break the check.
6. Printing **clearly named booleans** instead of printing all class names/counts makes verification easier across different JVMs.
7. `getAllLoadedClasses()` and `getInitiatedClasses(...)` are **separate snapshots**, with no promise that all JVM classes remain invariant between calls.

### 7.4. File `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: SurveyAgent
~~~

Save the manifest file with a trailing newline. Because the demo **only inspects** and calls `isModifiableClass` without using retransform/redefine, the `Can-Retransform-Classes` or `Can-Redefine-Classes` flags are not needed.

### 7.5. Compile and run

Create the structure:

~~~text
survey/
  SurveyAgent.java
  HiddenSample.java
  SurveyApp.java
  agent.mf
~~~

From the `survey` directory, run:

~~~bash
javac --release 17 SurveyAgent.java HiddenSample.java SurveyApp.java

jar --create --file survey-agent.jar --manifest agent.mf SurveyAgent.class

java -javaagent:survey-agent.jar SurveyApp
~~~

The syntax uses JDK 17+ and can be executed from Bash/CMD/PowerShell in the directory containing the sources. If an IDE runs from a different working directory, `Path.of("HiddenSample.class")` may not point to the right file; in that case, configure a consistent working directory. Compiling with `--release 17` keeps the classfile/code compatible with Java 17.

### 7.6. Verified stdout

Compiled the files above with `javac --release 17` and ran on OpenJDK 24. **Actual stdout:**

~~~text
agent=ready
bootstrap-loader-null=true
bootstrap-in-all=true
bootstrap-in-bootstrap-initiated=true
app-loader-nonnull=true
app-in-all=true
app-in-app-initiated=true
hidden-isHidden=true
hidden-name-has-slash=true
hidden-canonical-null=true
hidden-in-all=true
hidden-in-app-initiated=false
hidden-modifiable=false
int-array-isArray=true
int-array-loader-null=true
int-array-in-all=true
int-array-modifiable=false
string-array-in-all=true
string-array-loader-null=true
hidden-array-isArray=true
hidden-array-in-all=true
hidden-array-in-app-initiated=false
hidden-array-modifiable=false
primitive-modifiable=false
~~~

Read in three groups:

- **Bootstrap:** `String.class` has a `null` loader, is in all-loaded, and is in the bootstrap initiated set.
- **Hidden:** the hidden class has `isHidden()==true`, a name containing `/`, is in all-loaded, but **not** in the app loader's initiated set and is not modifiable.
- **Array:** the created array types appear in all-loaded, but `isModifiableClass()==false`. The array with a hidden element is also excluded from the initiated set.

`SurveyApp` serves as the control for a named application class: it has a non-`null` loader and appears in both all-loaded and the appropriate initiated set. The main results align with the Java SE 17 Javadocs, though `String.class.getClassLoader()==null` and GC/VM details may depend on the implementation. **Do not hardcode class count results, hidden suffixes, or enumeration order in real programs.**

## 8. A Safe Filter When the Next Goal Is Retransform

When the purpose of inspection is to find classes that can be instrumented, do not pass **all** output of `getAllLoadedClasses()` into `retransformClasses(...)`.

~~~java
// Illustrative snippet in the agent, requiring variables inst, allowedNames, and function matchesScope:
if (!inst.isRetransformClassesSupported()) {
    return;
}
for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if (candidate.isArray() || candidate.isHidden() || candidate.isPrimitive()) continue;
    if (!allowedNames.contains(candidate.getName())) continue;
    if (!matchesScope(candidate.getClassLoader(), candidate.getModule())) continue;
    if (!inst.isModifiableClass(candidate)) continue;
    // Record candidate; do not mass-retransform here.
}
~~~

**This is a code snippet and does not run standalone** because it lacks definitions for `allowedNames`, `matchesScope`, and `inst`. Role of each step:

- `isArray()` excludes array classes, including arrays of hidden elements.
- `isHidden()` excludes non-modifiable hidden classes.
- `isPrimitive()` is an extra safeguard if the utility is used on `Class<?>` objects outside an all-loaded snapshot.
- `allowedNames` accepts only named classes/methods within the scope that truly needs instrumentation.
- `matchesScope` must verify the exact defining loader/module, avoiding collisions when multiple deployments/plugins share the same binary name.
- `isModifiableClass` confirms the specific class is permitted to have its definition modified.
- `isRetransformClassesSupported()` confirms the **general capability** of the agent/JVM. The last two checks are independent conditions; having one of them be `true` is not enough.

Even when all checks pass, you also need a `ClassFileTransformer` registered with `canRetransform=true`, valid class-file bytes, no schema restriction violations, and safe operational policies. This is why you should not turn “inventory” into “hot-patch everything”.

**Named bootstrap classes require special caution:** Some classes may report `isModifiableClass==true`, but patching them affects the entire JVM and the agent's helpers may not be visible from bootstrap. Do not include those classes in an allowlist by default.

## 9. Collecting Metrics Without Distorting Results

### 9.1. Do not retain the entire `Class<?>[]` longer than necessary

A long-running agent across the JVM lifetime that holds strong references to every `Class<?>` from snapshots risks **pinning class loaders, hidden classes, or old plugin deployments**. Better practices:

- Iterate over the snapshot within a short unit of work.
- Aggregate **counters by category** instead of storing all class objects.
- Store only bounded names/metadata and attach a deployment/session ID if needed.
- For long-lived per-class information, consider `ClassValue<T>` or a cache whose lifecycle matches the class/loader, avoiding a static strong `Map<Class<?>,...>` with no cleanup path.
- Do not use `System.identityHashCode(loader)` as a permanent unique ID: hashes can collide/be reused and do not manage lifecycle automatically.

Illustrative example counting a snapshot:

~~~java
int hidden = 0;
int arrays = 0;
for (Class<?> clazz : inst.getAllLoadedClasses()) {
    if (clazz.isArray()) arrays++;
    else if (clazz.isHidden()) hidden++;
}
System.out.println("hidden=" + hidden + ", arrays=" + arrays);
~~~

This snippet **has no fixed stdout**, because class counts vary by environment, application/JVM activity, and GC. When you want to count **arrays with hidden elements** separately, walk down `getComponentType()` before incrementing the counter.

### 9.2. Record the scope and timestamp of the snapshot

An inspection record might contain:

~~~text
timestamp / JVM build / process identity
survey API = ALL_LOADED or INITIATED
class kind = NAMED_BOOTSTRAP / NAMED_APP / HIDDEN / ARRAY_OF_HIDDEN / ...
class name (only when appropriate for requirements and privacy)
loader/module scope in the inspection session
isModifiableClass result if needed
~~~

This is an **illustrative schema**, not a ready-made config file. A count like “hidden classes = 50” without a timestamp, VM version, statistical scope, or collector context is usually hard to compare.

Classes in the JVM can carry internal framework/application names. Do not export all names, modules, and paths into public logs/telemetry unless truly needed: it can expose system structure and cause high-cardinality metrics.

### 9.3. Snapshots themselves can cause side effects

Scanning thousands of `Class<?>` objects takes time and allocates a fairly large temporary array; reflection, formatters, loggers, and agent helpers can trigger additional class loading. Therefore:

- Do not continuously scan the entire JVM on a hot request path.
- Avoid printing thousands of lines from class-loading callbacks or using heavy logging libraries inside a transformer.
- Do not assume the array order from `getAllLoadedClasses` is stable.
- If the question is “which classes unloaded after a redeploy”, combine JVM class unloading logs, JFR, or `jcmd`/heap analysis; do not just compare counts from a single call.
- Clean up snapshot/class references once the inspection task is done if there is no need to retain them.

**GC is non-deterministic:** A default hidden class may be eligible for unloading even while its loader is still alive, but there is no guarantee it will be unloaded at a specific point in time. `System.gc()` is not a synchronous command that guarantees class unloading.

## 10. Common Inspection Mistakes

| Symptom or assumption | Actual issue | How to handle |
| --- | --- | --- |
| “`getClassLoader()==null` means every item is a bootstrap named class” | Confuses primitives and arrays with bootstrap classes | Classify array → hidden → primitive → named first |
| “Hidden classes are not in `getAllLoadedClasses`” | Confuses all-loaded with initiated | Use `getAllLoadedClasses`, check `isHidden()` |
| “`getInitiatedClasses(appLoader)` is missing hidden classes so the agent is buggy” | Hidden classes are not discoverable by binary name | Read the initiated API contract carefully |
| “An array with a hidden element must be in initiated because its loader is the app loader” | Arrays with hidden elements are also excluded | Loop `getComponentType()` down to the hidden element |
| “`hidden.getName()` having `/` is a Java package name” | The `/` in a hidden name is part of the JVM-assigned identifying suffix | Use `isHidden` and `Class<?>` identity, do not construct `Class.forName` |
| “`[Ljava.lang.String;` is an abnormal class filename” | This is the JVM array name format | Recognize `isArray` and the element type |
| “A loaded array can be retransformed” | Arrays are never modifiable | Do not pass arrays to `retransformClasses` |
| “Stripping the hidden suffix yields a unique ID” | Multiple hidden classes can share the same base name | Do not strip the suffix and treat the remaining string as class identity |
| “A bootstrap class is definitely not modifiable” | Loader and modifiability are two separate dimensions | Check class eligibility and capability, weigh the risks |
| “Class counts must be identical every time” | Snapshots change due to loading/unloading and GC | Attach timestamp, VM build, and analyze trends |
| “`Class.forName` can find every `Class<?>` in all-loaded” | Hidden classes are not discoverable, arrays use different names | Hold the Class reference, use the appropriate API |
| “Keeping snapshots forever is harmless” | Strong references can retain classloaders and hidden classes | Store only aggregated metrics or caches with cleanup |
| “Every class in all-loaded was defined by a loader calling `defineClass` itself” | Arrays are created by the JVM, hidden classes have their own define path | Distinguish class kinds before interpreting |

## 11. Practice Exercises

**Scenario A.** The tool sees that `String.class` and `int[][].class` both have `getClassLoader()==null`. Should it report two “bootstrap loaded named classes”?

**Answer:** No. `String` is a named bootstrap class on typical OpenJDK; `int[][]` is an **array type of a primitive**. Check `isArray()` before classifying by loader.

**Scenario B.** A hidden class returns `isHidden()==true`, is present in all-loaded, and has `getClassLoader()==appLoader`, yet is absent from `getInitiatedClasses(appLoader)`. Is the API inconsistent?

**Answer:** No. A hidden class can be loaded without being discoverable by binary name. The initiated list intentionally excludes hidden classes per its contract.

**Scenario C.** `Array.newInstance(hidden,0).getClass()` returns an object. Can it appear in all-loaded? Can it be retransformed?

**Answer:** This array class can appear in the snapshot after it is created, and it is **not modifiable**. It is also excluded from the initiated set because its element type is hidden.

**Scenario D.** Does `int[][].class.getComponentType()` return `int.class`?

**Answer:** No. It returns `int[].class`; you need to call it one more time to get `int.class`. A function classifying multidimensional arrays needs a loop.

**Scenario E.** An agent wants to find retransformable classes and only checks `isModifiableClass(type)==true`. Is that sufficient?

**Answer:** Not yet. You also need `isRetransformClassesSupported()`, the right classloader/module, a capable transformer, valid classfile bytes, and structural constraints. Modifiable does not grant the capability by itself.

**Scenario F.** A hidden class was in yesterday's snapshot but is gone today, while the app loader is still alive. Is it definitely a leak or bug?

**Answer:** No. A hidden class without `STRONG` can unload independently of its loader when GC permits. You need evidence about lifecycle and GC before concluding.

**Scenario G.** Two loaders can define two classes with the same binary name. Is using `Class.getName()` as a map key enough to distinguish them?

**Answer:** No. Named class identity requires the defining loader as well, and hidden classes have non-discoverable names. Use `Class<?>` identity itself at runtime and an ID with a clear lifecycle when exporting long-term data.

**Conclusion:** Treat runtime inspection as an **inventory with multiple kinds of `Class<?>` objects**, not a list consisting only of named, loader-discoverable, modifiable classes. The bootstrap loader explains many `null` loader values; hidden classes explain loaded classes that are not discoverable; array classes explain runtime-generated types whose names start with `[` and are not modifiable. Classifying these three groups accurately before aggregating metrics or deciding on retransformation avoids both inaccurate reports and invalid API calls.

### Official Sources

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, retransformation capability.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isHidden`, `isArray`, `isPrimitive`, `getName`, `getComponentType`, `getClassLoader`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/platform/application loaders and array class loader rules.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, non-discoverable names, `STRONG` option, class unloading.
- [OpenJDK — JEP 371 Hidden Classes](https://openjdk.org/jeps/371): goals and semantics of hidden classes.
