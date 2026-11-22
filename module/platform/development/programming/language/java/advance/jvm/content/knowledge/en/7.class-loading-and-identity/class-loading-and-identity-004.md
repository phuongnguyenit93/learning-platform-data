# Initiating Loader, Defining Loader, and Constraints Between Loaders

## 1. Objectives

A confusing error in plugin-based Java applications is `demo.Plugin cannot be cast to demo.Plugin`: two class names look identical, yet the JVM treats them as **two different types**. The reason lies in how the JVM identifies a runtime class: **the binary name and the loader that defined the class**. In addition, a class may be requested to load through one loader but be defined by **another loader** after delegation.

After this lesson, you need to distinguish accurately between:

- **Initiating loader** and **defining loader**, according to **JVMS §5.3**.
- **Loading** (creating a class from its definition), **linking/resolution** (linking references), and **initialization** (running `static` initialization).
- **Class identity**: the pair (`binary name`, `defining loader`), not just the name or contents of the `.class` file.
- The default **parent delegation** of `ClassLoader` and the limitation of the claim “every loader is parent-first”.
- **Loading constraints** between loaders, denoted `N^L1 = N^L2`, to ensure type safety for calls and fields across class loader boundaries.
- The differences between **`ClassCastException`**, **`LinkageError` due to loader constraint violation**, `ClassNotFoundException`, and several other linking errors.

The hands-on example uses Java **17+**, a plugin class, two separate `URLClassLoader` instances, and verifies that identical class names do not guarantee identical `Class<?>` identity.

## 2. Two Loader Roles in the JVMS

The **JVMS §5.3, Creation and Loading** specification explains: for a non-array class/interface, a class loader `L` can either directly locate the bytecode representation and ask the JVM to **define** the class, or indirectly **delegate** loading to another loader.

The **defining loader** of a class `C` is the loader that directly causes the JVM to create the runtime definition of `C`, typically via `ClassLoader.defineClass`. The **initiating loader** is a loader that the JVM records as having initiated the loading of `C`, whether it directly defines `C` or is returned the class from the delegation process.

~~~text
                Need to create class named N
                        |
                 loader Child (Lc)
                        |
           +------------+------------+
           |                         |
     Self find/define           Delegate to Parent (Lp)
           |                         |
           v                         v
  Class C = (N, Lc)            Parent defines C
           |                         |
  Lc: defining + initiating          v
                              Class C = (N, Lp)
                                    |
                          Lp: defining + initiating
                          Lc: initiating
~~~

These are **two possible branches**, not a single call taking both paths. **A runtime class has one defining loader** but **can have multiple initiating loaders**. When the delegation chain is long, you must not assume that every intermediate loader is an initiating loader; the JVMS has specific recording rules for participating loaders.

| Criterion | Initiating loader | Defining loader |
| --- | --- | --- |
| Description | The loader that initiates loading `C`, directly or indirectly | The loader that actually defines `C` in the VM |
| Can there be multiple loaders for the same `C`? | Yes | No, a runtime class has one defining loader |
| Must it read `.class` bytecode itself? | Not required; it may delegate | Must be directly responsible for defining the class (bootstrap has its own mechanism) |
| Determines the identity of `C`? | Does not determine it on its own | **Yes**, together with the binary name |
| Observable via `Class.getClassLoader()`? | Does not return the list of initiating loaders | Returns the defining loader, or `null` for bootstrap |

### Bootstrap and a Load Request via a Child Loader

On a typical JDK, `java.lang.String` is defined by the **bootstrap class loader**. Suppose a child loader receives a request:

~~~java
Class<?> c = childLoader.loadClass("java.lang.String");
System.out.println(c == String.class);
System.out.println(c.getClassLoader() == null);
~~~

This is an **illustrative snippet that must be placed inside a method where the variable `childLoader` is declared**. With the normal delegation mechanism, both lines print `true`. `childLoader` may be an initiating loader, but it is **not the defining loader** of `String`.

The `null` value returned by `String.class.getClassLoader()` is the API representation for **bootstrap**; it does not mean `String` was “loaded by no loader”. Both the class name and the defining loader must be observed together when diagnosing.

## 3. An Initiating Loader Does Not Duplicate Runtime Class Identity on Its Own

For normal classes/interfaces, the JVM identifies a type by **(`binary name`, `defining loader`)**. Two loaders both requesting `api.Service` can return the exact **same** `Class<?>` when both delegate to a parent; in that case, **different initiating loaders do not make the type identity different**.

Conversely, if each plugin loader defines `demo.Plugin` itself from the same bytes, they create two separate runtime types. `classA.getName().equals(classB.getName())` can be `true` while `classA == classB` is `false`, and `classA.cast(objectB)` can throw `ClassCastException`.

**Bridge to section 6:** two types with the same binary name can validly coexist. Only when a link via a field/method descriptor **requires unifying the meaning of a type** does the JVM apply loading constraints; having two defining loaders is not an error by itself.

## 4. Delegation Is the Path to the Defining Loader, Not Identity

The default `ClassLoader.loadClass(name, resolve)` mechanism follows **findLoadedClass → parent/bootstrap → findClass → resolveClass if requested**. Parent-first is a useful default behavior for sharing APIs; custom loaders can intentionally use child-first for implementation classes while still complying with JVM constraints.

When debugging, separate three questions: (1) **who had `loadClass` called on it**? (2) **who actually called `defineClass`**? (3) **who owns the API type** appearing in method/field descriptors across the two loaders? `Class.getClassLoader()` reflects the defining loader (bootstrap is represented as `null`), and **does not** return the list of initiating loaders.

Calls to `loadClass` or `Class.forName(name, false, loader)` do not themselves require running `<clinit>`; class initialization is a separate matter. This section only sets the context for diving into **formal constraints** in section 6, rather than repeating the entire algorithm and API from the lesson on bootstrap/platform/application delegation.

## 5. Hands-on Java 17+: Two `URLClassLoader` Instances Loading the Same Class

This hands-on exercise is complete enough to run on JDK 17+ **without external libraries**. It intentionally keeps the plugin file in a separate directory so that the two loaders can define two independent copies.

### 5.1. File Structure

~~~text
loader-lab/
  demo/
    Plugin.java
  LoaderLab.java
~~~

Contents of `demo/Plugin.java`:

~~~java
package demo;

public class Plugin {
    public String message() {
        return "plugin";
    }
}
~~~

Contents of `LoaderLab.java` in the root directory `loader-lab`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderLab {
    public static void main(String[] args) throws Exception {
        Path compiled = Path.of("plugin-classes").toAbsolutePath();
        URL[] urls = { compiled.toUri().toURL() };

        // The platform loader is NOT the application loader of LoaderLab.
        // Therefore, demo.Plugin is not preempted by the app classpath.
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(urls, parent);
             URLClassLoader loaderB = new URLClassLoader(urls, parent)) {

            Class<?> classA = loaderA.loadClass("demo.Plugin");
            Class<?> classB = loaderB.loadClass("demo.Plugin");

            Object objectA = classA.getDeclaredConstructor().newInstance();
            Object objectB = classB.getDeclaredConstructor().newInstance();

            System.out.println("same name="
                    + classA.getName().equals(classB.getName()));
            System.out.println("same class=" + (classA == classB));
            System.out.println("loader A defines="
                    + (classA.getClassLoader() == loaderA));
            System.out.println("loader B defines="
                    + (classB.getClassLoader() == loaderB));
            System.out.println("cross-instance="
                    + classA.isInstance(objectB));
            System.out.println("same within A="
                    + (objectA.getClass() == classA));

            try {
                classA.cast(objectB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cast=ClassCastException");
            }

            Class<?> stringViaA = loaderA.loadClass("java.lang.String");
            System.out.println("delegated String="
                    + (stringViaA == String.class));
            System.out.println("String bootstrap="
                    + (String.class.getClassLoader() == null));
        }
    }
}
~~~

### 5.2. Compile and Run

In the `loader-lab` directory in your terminal:

~~~bash
mkdir plugin-classes
javac -d plugin-classes demo/Plugin.java
javac LoaderLab.java
java LoaderLab
~~~

With PowerShell, you can also create the directory first using `New-Item -ItemType Directory -Force plugin-classes`. Do not add `plugin-classes` to the parent **platform** loader path; the example needs each `URLClassLoader` to locate `demo.Plugin` itself from the input URL. If the directory already exists, skip the creation step.

**Exact stdout when run in the standard layout:**

~~~text
same name=true
same class=false
loader A defines=true
loader B defines=true
cross-instance=false
same within A=true
cast=ClassCastException
delegated String=true
String bootstrap=true
~~~

### 5.3. Why Is Each Line Correct?

- **`same name=true`**: the binary name of both classes is `demo.Plugin`.
- **`same class=false`**: `loaderA`/`loaderB` are two separate defining loaders, so the runtime class identities differ.
- **`loader A defines=true`** and **`loader B defines=true`**: the two classes were indeed defined by their respective loaders.
- **`cross-instance=false`**: an object of `classB` is not an instance of `classA`.
- **`same within A=true`**: `objectA` was created from `classA`.
- **`cast=ClassCastException`**: casting is based on runtime types, not on identical names or identical bytecode.
- **`delegated String=true`**: the `String` class returned when `loaderA` requests it is still `String.class` from bootstrap.
- **`String bootstrap=true`**: the Java API represents the bootstrap loader as `null`.

**Important:** the demo produces a **`ClassCastException` when attempting to cast**, **not intentionally creating a loading constraint violation**. Two separate classes with the same name can validly coexist. A `LinkageError` related to loading constraints occurs when **a specific linking rule** requires two interpretations of a type name to match and they cannot.

### 5.4. What If You Want to Use a Common Parent?

Try changing the architecture so that both children delegate to **a parent that has already defined `demo.Plugin`**. When the parent returns the shared class, you can get:

~~~text
classA == classB  -> true
classA.getClassLoader() == parent -> true
~~~

This is a **comparison scenario**, not advice to arbitrarily modify the example by changing a single parameter: the parent must be set up with the ability to load `Plugin` and delegation must actually be parent-first. The goal is to see that **the initiating loader can differ from the defining loader**.

## 6. Loading Constraints: Why Must the JVM Constrain Loaders Together?

Given two classes defined by different loaders, when one class references a method/field of the other, the JVM needs to agree on the meaning of the **reference types appearing in descriptors**. Otherwise, a type with the same name but different identity could break type safety when passing values across class boundaries.

**JVMS §5.3.4** expresses the constraint in the form:

~~~text
N^L1 = N^L2

The class/interface name N, when loaded via loader L1 or L2,
must both refer to ONE runtime class/interface.
~~~

This is a **constraint on the loading result of a type name `N`**, not a constraint that `L1 == L2`. If `L1` and `L2` delegate the name `N` to the same common defining loader, the constraint is satisfied.

### Example of a Method Crossing an API Boundary

Suppose the host system defines the contract:

~~~java
package api;

public interface Service {
    Message convert(Message input);
}
~~~

and `api.Message` is an independent class whose runtime identity is defined by the **shared host/API loader**. A plugin implements:

~~~java
package plugin;

public final class ServiceImpl implements api.Service {
    @Override
    public api.Message convert(api.Message input) {
        return input;
    }
}
~~~

**The two snippets above are illustrative code in different files and also require the `api.Message` class along with an appropriate build/classpath configuration; they are not a standalone runnable file.**

In the method descriptor `(Lapi/Message;)Lapi/Message;`, both the parameter and the return value refer to the name `api/Message`. When the JVM checks overriding and resolution across loaders, it can apply the loading constraint:

~~~text
api/Message ^ L_host  =  api/Message ^ L_plugin
~~~

If both the host loader and the plugin loader lead to the same `api.Message` defined by the parent, both sides agree. If the plugin loader attempts to define its own `api.Message` making it different from the host's `api.Message`, the linking constraint may be **unsatisfiable**, causing a **`LinkageError` due to loader constraint violation**.

~~~text
         HOST                             PLUGIN
      loader H                           loader P
         |                                  |
  api.Service.convert(Message)   ServiceImpl.convert(Message)
         |                                  |
         +---- type N = api/Message --------+
              constraint N^H = N^P

Valid case:
  H and P load api.Message as the same runtime class from the shared loader.

Violation case:
  H and P have recorded two different runtime api.Message classes,
  yet linking requires type identity in the signature.
~~~

It is **not** the case that whenever two loaders have classes with the same name, the VM throws an error. Loader constraints are applied at **specific linking** relationships. Two separate `demo.Plugin` classes used internally, with no identity constraint between them, can coexist normally.

### When the JVM Applies Loading Constraints

According to the JVMS, the key places include:

1. **Preparation (§5.4.2)** of a class/interface: when an instance method can override a method of a superclass/superinterface, it must be ensured that the class/interface names in the method descriptor do not carry conflicting meanings between defining loaders.
2. **Field resolution (§5.4.3.2)**: reference type names in a field descriptor must be interpreted consistently between the referencing class and the field owner when the VM applies the constraint.
3. **Method/interface method resolution (§5.4.3.3–5.4.3.4)**: names in method descriptors can be constrained across loaders.
4. **When recording an initiating loader**: the VM must immediately check existing constraints; if violated, abort the recording operation and throw `LinkageError` per the specification.

**Resolution can occur eagerly or lazily** according to JVM rules, so the point where the error is thrown may not match the source line where you “created” the loader configuration. You should not conclude that “because `main` ran, all method signatures across plugins have linked successfully”.

### Do Not Confuse Loading Constraints with Dynamic Dispatch

- **Resolution** determines the result of a symbolic reference in the constant pool.
- **Loading constraints** keep the meaning of types in descriptors consistent across loaders during linking.
- **Dynamic dispatch** decides which method implementation runs during a virtual call based on the runtime object type.
- **`invokedynamic`** has its own call-site/bootstrap mechanism.

These concepts all participate in execution/linking, but they **cannot be used interchangeably**.

## 7. Comparing Loading, Linking, and Cast Errors

| Symptom | Type | Meaning and What to Check |
| --- | --- | --- |
| `ClassNotFoundException` | Checked exception | An explicit class-loading call could not find the name; check loader path, binary name, JAR/module |
| `NoClassDefFoundError` | `LinkageError` subclass | A class referenced during execution/linking could not be found/initialized in the given situation; check cause and prior errors |
| `ClassCastException` | Runtime exception | Object is incompatible with the target runtime type; check both `getName` and `getClassLoader` |
| `LinkageError: loader constraint violation` | `LinkageError` | Type names in descriptors across loaders must agree but cannot |
| Duplicate class definition | `LinkageError` in the relevant situation | The same defining loader attempts to recreate a class with an already-defined name |
| `NoSuchMethodError` or `NoSuchFieldError` | `LinkageError` subclass | Symbolic reference does not match the actual loaded API; check dependency versions |
| `IllegalAccessError` | `LinkageError` subclass | Runtime access check denies access; check package identity, visibility, module exports |
| `ExceptionInInitializerError` | `LinkageError` subclass | `static` initialization failed; look for the cause instead of assuming a delegation error |

**Diagnostic rule:** do not call every `LinkageError` a loader constraint violation. Also, `ClassCastException` in the `LoaderLab` example is **different** from `LinkageError`: both classes loaded successfully, and incompatibility was only discovered at cast time.

### Errors Caused by a Duplicate API JAR

A common mistake: the host already has `api.Message`, but the plugin JAR also bundles its own `api.Message` and the custom loader is **child-first**. The name duplication may not cause an immediate error. When the plugin implements the shared interface `api.Service` and the method descriptor involves `api.Message`, the JVM may need to force both loaders to agree on that type. The fix is to **share the API definition via a common loader**, not to force casts between two classes with different identities.

In Maven/Gradle or equivalent build systems, a dependency meant only for compilation but provided by the host at runtime can be marked `provided` or `compileOnly` as intended. However, you still need to check the actual packaging and the framework's loader mechanism rather than assuming that changing the dependency scope alone will fix every error.

## 8. Array Classes and Bootstrap: An Exception Worth Knowing

Array classes **are created directly by the JVM** according to **JVMS §5.3.3**; there is no `[I.class` file for a custom loader author to find via `findClass` like an ordinary Java class.

- If the component type is a **reference type**, the array class has the defining loader of the component type.
- If the component is a **primitive type**, the array class has the bootstrap defining loader.
- The JVM records the initiating loader for the array class according to the JVMS procedure.

Runnable Java 17+ example:

~~~java
public class ArrayLoaderCheck {
    public static void main(String[] args) {
        System.out.println("String[] bootstrap="
                + (String[].class.getClassLoader() == null));
        System.out.println("int[] bootstrap="
                + (int[].class.getClassLoader() == null));
    }
}
~~~

~~~bash
javac ArrayLoaderCheck.java
java ArrayLoaderCheck
~~~

**Stdout:**

~~~text
String[] bootstrap=true
int[] bootstrap=true
~~~

If `demo.Plugin` is defined independently by `loaderA` and `loaderB`, the corresponding array classes `demo.Plugin[]` also have **different identities** because their component types differ. Do not confuse array class identity with two arrays merely having elements of the same class name.

## 9. Sound Plugin and Shared API Design

A helpful diagram:

~~~text
Host / Shared API loader
   |
   +-- api.Service
   +-- api.Message
   +-- api.PluginContext
   |
   +-- Plugin A loader
   |      pluginA.ServiceImpl
   |      pluginA.InternalCache
   |      (api.* -> delegate shared loader)
   |
   +-- Plugin B loader
          pluginB.ServiceImpl
          pluginB.InternalCache
          (api.* -> delegate shared loader)
~~~

### Practical Rules

1. **Share API types through a common defining loader.** Interfaces/DTOs/classes appearing in boundary method/field descriptors should be managed consistently.
2. **Isolate implementation classes** in each plugin loader when needed. Internal classes can share the same name across two plugins if they do not affect API boundaries.
3. **Do not bundle duplicate API JARs into plugins** when a custom loader can redefine API classes itself. Review dependency scope and runtime packaging.
4. **Log the actual defining loader**, not just `Class.getName()`. `getModule()` and JAR source are also useful.
5. **Be careful with hot reload**: old and new plugin generations may use two different loaders; old instances do not automatically convert to the new type.
6. **Release references** when unloading: host singletons, thread context class loaders, static maps, threads, or callbacks can keep the old loader reachable.
7. **Do not treat a class loader as an absolute security sandbox.** Loading untrusted code requires separate security boundaries; the JVM does not guarantee process-level isolation merely through two class loaders.

### Thread Context Class Loader (TCCL)

`Thread.currentThread().getContextClassLoader()` returns the thread's **context class loader**. Some APIs/frameworks, such as provider lookup mechanisms, may use it. However, TCCL **does not change the defining loader** of a class already created by the JVM.

A debug line:

~~~java
System.out.println(Thread.currentThread().getContextClassLoader());
~~~

does not replace:

~~~java
System.out.println(obj.getClass().getClassLoader());
~~~

The second snippet requires `obj` to be non-`null` in context. If TCCL holds a reference to an old plugin loader on a still-living thread, this can also be why the loader is not reclaimed during hot reload.

## 10. Debugging: How to Trace Class Identity and Loader Constraints

When encountering an error with repeated class names or the keyword `loader constraint violation`, investigate in order:

1. **Identify the root error type** and cause chain: `ClassCastException`, `LinkageError`, `NoClassDefFoundError`, `IllegalAccessError`?
2. **Record the class names and defining loaders** of both sides: `Class.getName()`, `Class.getClassLoader()`, `Class.getModule()`; compare loader objects with `==`.
3. **Inspect field/method descriptors** of API boundaries using `javap -v -p` or `javap -s -p`. Pay attention to DTO/shared interface types in the form `Lapi/Message;`.
4. **Check for duplicate JARs**: does a type name exist in both the host classpath and the plugin JAR?
5. **Check the actual delegation policy**, especially child-first classloaders and package allow/deny lists.
6. **Check runtime package and module boundaries** if it is an access error, not just imports in source.
7. **Inspect the thread context loader** and stale references during hot reload.
8. **Fix shared API ownership**, dependency packaging, or the loader graph with verification, then rerun integration tests.

Commands:

~~~bash
java -version
jar tf plugin.jar
javap -s -p -classpath plugin.jar plugin.ServiceImpl
javap -v -p -classpath plugin.jar plugin.ServiceImpl
java -Xlog:class+load=info -jar host.jar
~~~

These are **usage patterns**—replace the JAR/class names with actual files. `-Xlog:class+load=info` is logging on **modern HotSpot** and is not guaranteed to be supported identically by every JVM. Loading log lines show the loaded classes and class sources, but to confirm the defining loader object you should combine them with runtime information. See `java -Xlog:help` on the corresponding HotSpot.

Method snippet to inspect two objects (must be placed inside a class, with both arguments non-`null`):

~~~java
static void inspect(Object a, Object b) {
    Class<?> c1 = a.getClass();
    Class<?> c2 = b.getClass();

    System.out.println("name1=" + c1.getName());
    System.out.println("name2=" + c2.getName());
    System.out.println("same class=" + (c1 == c2));
    System.out.println("loader1=" + c1.getClassLoader());
    System.out.println("loader2=" + c2.getClassLoader());
    System.out.println("1 accepts 2=" + c1.isInstance(b));
}
~~~

**Do not** compare loader names solely by `toString()`, because IDs/hashes can differ across runs. Use object identity when comparing actual loaders or `Class<?>` instances.

## 11. Misconceptions to Avoid

| Misconception | Correct Distinction |
| --- | --- |
| “The loader on which I call `loadClass` is the defining loader.” | The called loader may **delegate**; `getClassLoader()` tells you the defining loader. |
| “A class always has only one initiating loader.” | There can be **multiple** initiating loaders and one defining loader. |
| “Same fully qualified name means the same Java class.” | Requires the same **defining loader** and binary name. |
| “Same class bytes means you can definitely cast across loaders.” | Different defining loaders can produce different runtime class identities. |
| “Parent-first is a hard rule for every custom loader.” | It is the default of `ClassLoader`; custom loaders can have other valid policies. |
| “Just changing package names to match opens up package-private access.” | Runtime package and module rules still matter. |
| “Any class with the same name across two loaders will throw `LinkageError`.” | Multiple definitions can coexist; constraint errors require a mandatory linking relationship. |
| “`ClassCastException` and loader constraint violation are the same error.” | One is a runtime cast; the other is a type-safety issue during linking/preparation. |
| “A loading constraint forces two loader objects to be equal.” | It forces **the classes loaded through them** for the constrained name to be identical. |
| “Loading a class means running `static {}`.” | Loading is distinct from initialization. |
| “The class loader shown in `getClassLoader()` is the entire initiating loader history.” | The API returns the defining loader, not a historical list. |
| “`Class.forName(name, false, loader)` guarantees the class is not linked.” | It avoids requesting initialization; linking may still occur. |
| “The loader of `int[]` must find `[I.class` bytecode.” | Array classes are created directly by the VM. |
| “TCCL determines the defining loader for every class of the thread.” | TCCL serves context-based lookup for some APIs/frameworks; it does not alter an already-created class identity. |
| “Closing a `URLClassLoader` makes all classes and objects it defined disappear immediately.” | Class unloading depends on reachability and GC; closing the loader does not force all objects to vanish. |

## 12. Self-Check Questions

**1.** `child.loadClass("java.lang.String")` returns `String.class`. Which loader defined the class?  
**Answer:** Bootstrap (on a standard JDK). `child` may be an initiating loader, but not the defining loader.

**2.** Why do two different `URLClassLoader` instances reading the exact same bytes produce `classA != classB`?  
**Answer:** Runtime identity is the pair (`binary name`, `defining loader`), and the defining loaders are different.

**3.** If `classA.getName().equals(classB.getName())` is `true`, is `classA.isInstance(objectB)` automatically `true`?  
**Answer:** No. Type checks use runtime identity, not just the name.

**4.** What does the constraint `api/Message^L1 = api/Message^L2` mean?  
**Answer:** For the name `api/Message`, the result of loading via the two loaders must refer to the same runtime class/interface; it does not require the loader objects to be the same.

**5.** Why can host/plugin encounter a loader constraint violation in `Service.convert(Message)`?  
**Answer:** If the same type name `api.Message` in the descriptor is resolved into two different classes, the JVM cannot guarantee the method contract across loaders when the constraint requires identity.

**6.** If two `demo.Plugin` classes are only used privately inside two plugins with no constraint between them, is a `LinkageError` guaranteed?  
**Answer:** No. They can validly coexist.

**7.** Which loader is the defining loader when its code calls `defineClass` to successfully create a class?  
**Answer:** That loader itself.

**8.** Does `Class.getClassLoader()` provide the list of all initiating loaders?  
**Answer:** No. It reflects the defining loader.

**9.** Does `Class.forName(name, false, loader)` request running the static initializer?  
**Answer:** It does not actively request initialization; the class may still be loaded/linked.

**10.** Does `String[].class` have its own defining loader that `URLClassLoader` reads from a `[Ljava/lang/String;.class` file?  
**Answer:** No. Array classes are created by the VM, and the defining loader is tied to the component `String` according to array class rules.

## 13. Official Sources

- [JVMS Java SE 25 — §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defines initiating loader, defining loader, and class identity.
- [JVMS Java SE 25 — §5.3.1–5.3.3](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.1): loading via bootstrap/user-defined loaders and array classes.
- [JVMS Java SE 25 — §5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3.4): `N^L1 = N^L2`, mandatory check points, and `LinkageError` on violation.
- [JVMS Java SE 25 — §5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.2): constraints for method overriding.
- [JVMS Java SE 25 — §5.4.3 Resolution](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.3): field/method references across loaders.
- [JDK 25 — ClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findClass`, `defineClass`.
- [JDK 25 — URLClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): loading classes/resources via URLs and closing the loader.
- [JDK 25 — Class API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getName`, `isInstance`, `cast`, `forName`.
- [JLS Java SE 25 — §12.2 Loading](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.2): loading classes/interfaces and consistency across class loader environments.

**Final takeaway:** To know “who requested loading?”, examine the **initiating loader**. To know “which type in the JVM?”, examine **binary name + defining loader**. To know “can two loaders use two different interpretations of a type across an API boundary?”, check **loading constraints**, instead of equating every cast or class-loading error with `LinkageError`.