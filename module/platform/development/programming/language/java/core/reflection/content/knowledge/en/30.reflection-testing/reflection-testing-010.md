# Testing Two ClassLoaders Defining Classes with the Same Name in Java

In Java, **two classes with the same fully qualified name are not necessarily the same type at runtime**. For a normal class, type identity consists of the **binary name and the class loader that *defined* that class** (*defining class loader*). Therefore, if two different class loaders each call `defineClass` to define the same name such as `sample.Plugin` from the exact same bytecode content, the JVM still creates **two distinct types**.

This lesson uses a standalone runnable Java 17+ test to verify:

- Same `Class.getName()`, yet **`Class<?>` instances are not equal**.
- Two types cannot be cast or assigned to each other based solely on matching names.
- Each loader should define a class with a given name only once; another loader can define a same-named class in its own namespace.
- Two independent plugins can still collaborate through a **shared interface loaded by a parent loader**, if the class loader hierarchy is designed properly.

This is an essential skill when testing plugins, application servers, hot-reload libraries, scripting engines, and multi-class-loader environments.

## 1. Class Identity Rules at Runtime

Look at these two entries:

```text
binary name   = sample.Plugin
loader A      = PluginLoader@...
loader B      = PluginLoader@...
```

The `@...` suffix here is an illustrative notation for two class loader instances, not deterministic JVM output.

If loader A defines `sample.Plugin` and loader B also **defines** `sample.Plugin` itself, then:

```text
(sample.Plugin, loader A)  !=  (sample.Plugin, loader B)
```

This explains why:

```java
Class<?> a = Class.forName("sample.Plugin", false, loaderA);
Class<?> b = Class.forName("sample.Plugin", false, loaderB);

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                         // false, if A/B each define it
System.out.println(a.isAssignableFrom(b));          // false, if no subtype relationship
```

This is an **illustrative snippet**: it assumes `loaderA` and `loaderB` have been created and actually defined the target class independently. If both loaders merely **delegate to the same parent loader**, both `Class.forName` calls can return the **exact same** `Class<?>`.

### Defining Loader vs. Initiating Loader

- **Defining loader** is the loader that actually defines the class via a mechanism such as `defineClass`. Runtime identity depends on this loader.
- **Initiating loader** is the loader associated with the class-loading request; it may simply delegate and receive a class defined by another loader.
- `clazz.getClassLoader()` returns the **defining loader** (for some platform classes, the result can be `null` for the bootstrap loader).

Therefore, **two different `ClassLoader` objects do not automatically produce two different runtime classes**. The test must force them to define the target class themselves instead of silently delegating everything to the same parent loader.

## 2. Why Default Behavior Easily Fails to Reproduce the Phenomenon

The default `ClassLoader.loadClass(String)` typically performs parent-first delegation: check already-loaded classes, ask the parent loader to find the class, and load locally only when needed. If both loaders share the same parent and the parent already sees `sample.Plugin`:

```text
PluginLoader A ──┐
                 ├──> AppClassLoader ──> sample.Plugin
PluginLoader B ──┘

Result: both lookup paths point to the same Class<?> defined by AppClassLoader.
```

Thus, a test that merely calls:

```java
ClassLoader a = new ClassLoader() {};
ClassLoader b = new ClassLoader() {};
Class<?> typeA = a.loadClass("sample.Plugin");
Class<?> typeB = b.loadClass("sample.Plugin");
```

**does not prove** the JVM creates two types. The two `ClassLoader` instances above do not override finding/loading, so both will likely be served by the parent.

To test the two-distinct-types case, one of two approaches is required:

1. Create two separate loaders whose class source is outside the parent loader's scope, so each loader calls `findClass` then `defineClass` itself.
2. Write a class loader that **prefers defining the exact target class itself**, while still delegating all other classes to the parent.

This lesson uses approach 2, intentionally scoped only to the name `sample.Plugin`. This is a controlled simulation; **do not switch an entire loader to child-first** without understanding the consequences for shared libraries and APIs.

## 3. Designing a Test with Deterministic Results

We use three Java files and two instances of a custom class loader:

```text
src/
├── host/
│   └── Speaker.java          (shared contract, loaded by app loader)
├── sample/
│   └── Plugin.java           (class bytecode redefined)
└── TwoLoadersTest.java       (test runner + PluginLoader)
```

Desired loader structure:

```text
                    AppClassLoader
                 /                  \
        PluginLoader A         PluginLoader B
          sample.Plugin          sample.Plugin
                 \                  /
                  \__ host.Speaker _/
                       (same Class<?>)
```

Both plugins implement `host.Speaker`. The child loaders define `sample.Plugin` themselves from **the same bytecode**, while delegating lookup of `host.Speaker` to the same parent loader. This lets us observe two properties simultaneously:

- The two `sample.Plugin` classes **do not share type identity**, so casting an object from side A to side B's class fails.
- Both instances **are compatible** with `host.Speaker` defined by the parent, so `hello()` can be called through the shared contract.

## 4. Compilable and Runnable Java 17+ Program

### File 1 — `src/host/Speaker.java`

```java
package host;

public interface Speaker {
    String hello();
}
```

The `Speaker` interface sits on the application classpath. The host program uses this interface as the **meeting point** between plugins.

### File 2 — `src/sample/Plugin.java`

```java
package sample;

import host.Speaker;

public class Plugin implements Speaker {
    public Plugin() {}

    @Override
    public String hello() {
        return "hello from plugin";
    }
}
```

We only need **one** source file and **one** `Plugin.class` bytecode file. Two distinct class loaders will read **the same bytecode array**, yet each loader defines the class in its own space.

### File 3 — `src/TwoLoadersTest.java`

```java
import host.Speaker;
import java.nio.file.Files;
import java.nio.file.Path;

public class TwoLoadersTest {
    private static final String TARGET = "sample.Plugin";

    static final class PluginLoader extends ClassLoader {
        private final byte[] bytecode;

        PluginLoader(byte[] bytecode) {
            super(TwoLoadersTest.class.getClassLoader());
            this.bytecode = bytecode.clone();
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytecode, 0, bytecode.length);
                }
                if (resolve) resolveClass(found);
                return found;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use: java -cp out TwoLoadersTest out/sample/Plugin.class");
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassLoader one = new PluginLoader(bytes);
        ClassLoader two = new PluginLoader(bytes);

        Class<?> a = Class.forName(TARGET, false, one);
        Class<?> b = Class.forName(TARGET, false, two);

        System.out.println("Same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("Same Class object: " + (a == b));
        System.out.println("Distinct defining loaders: "
                + (a.getClassLoader() != b.getClassLoader()));
        System.out.println("A assignable from B: "
                + a.isAssignableFrom(b));
        System.out.println("Interface accepts A: "
                + Speaker.class.isAssignableFrom(a));
        System.out.println("Interface accepts B: "
                + Speaker.class.isAssignableFrom(b));

        Object instanceA = a.getDeclaredConstructor().newInstance();
        Object instanceB = b.getDeclaredConstructor().newInstance();

        System.out.println("Instance A is B: "
                + b.isInstance(instanceA));
        try {
            b.cast(instanceA);
            System.out.println("Cast unexpectedly succeeded");
        } catch (ClassCastException expected) {
            System.out.println("Cast B <- instance A: ClassCastException");
        }

        Speaker first = Speaker.class.cast(instanceA);
        Speaker second = Speaker.class.cast(instanceB);
        System.out.println("Shared interface: "
                + first.hello() + " | " + second.hello());
    }
}
```

### Compile and Run

From the directory containing `src/`. With JDK 17 or newer, execute:

```bash
javac -encoding UTF-8 -d out src/host/Speaker.java src/sample/Plugin.java src/TwoLoadersTest.java
java -cp out TwoLoadersTest out/sample/Plugin.class
```

The `javac -d out` command produces:

```text
out/
├── host/
│   └── Speaker.class
├── sample/
│   └── Plugin.class
├── TwoLoadersTest.class
└── TwoLoadersTest$PluginLoader.class
```

The runner and shared interface class files sit on the application classpath; inside the program, each `PluginLoader` only holds the bytecode read from `out/sample/Plugin.class`.

### Actual Output

```text
Same binary name: true
Same Class object: false
Distinct defining loaders: true
A assignable from B: false
Interface accepts A: true
Interface accepts B: true
Instance A is B: false
Cast B <- instance A: ClassCastException
Shared interface: hello from plugin | hello from plugin
```

The output was verified by compiling and running the corresponding Java program. File names, class names, and printed strings match the source code above.

## 5. Exact Explanation of Each Result

### 5.1. Same Name, Different `Class<?>`

`a.getName().equals(b.getName())` returns `true` because both classes carry the binary name `sample.Plugin`.

`a == b` returns `false` because the two `Class<?>` objects represent two different types: the class defined by loader A and the class defined by loader B.

Having the same bytecode **does not** force Java to merge two classes from two loaders. Each loader defining the bytecode creates a separate type namespace for that name.

### 5.2. `getClassLoader()` Identifies the Source of Identity

`a.getClassLoader() != b.getClassLoader()` is `true`. In the test, loaders A and B are distinct and each genuinely called `defineClass` for `sample.Plugin`.

This is a necessary verification step. If you only print two distinct loader variables without checking the **defining loader of the resulting `Class<?>`**, the test could accidentally prove only two loader instances exist, without proving the class was defined separately.

### 5.3. `isAssignableFrom` and `isInstance` Do Not Look Only at Names

`a.isAssignableFrom(b)` is `false`. Two independent classes have no type-inheritance relationship with each other even with matching names.

`b.isInstance(instanceA)` is also `false`: `instanceA` was created by class A, so it is not an instance of class B.

Calling `b.cast(instanceA)` throws `ClassCastException` as expected. The error does not come from `hello()`, nor from differing name strings, but from **different runtime type identities**.

### 5.4. Why Are Both Still Recognized as `Speaker`?

Both `sample.Plugin` from loader A and loader B implement **the same `host.Speaker` from the parent loader**. Because `Speaker` is defined by the parent loader:

```java
Speaker.class.isAssignableFrom(a);  // true
Speaker.class.isAssignableFrom(b);  // true
```

Both objects can be viewed through `Speaker`:

```java
Speaker left = Speaker.class.cast(instanceA);
Speaker right = Speaker.class.cast(instanceB);
```

This is the practical benefit of plugin architecture: **keep the shared contract in the host/parent loader, and load only separate implementations in plugin loaders**. Through the shared interface, the host program never needs to cast to a specific loader's `sample.Plugin`.

## 6. Inspecting the Overridden `loadClass` Method Closely

In `PluginLoader`, the condition:

```java
if (!TARGET.equals(name)) {
    return super.loadClass(name, resolve);
}
```

preserves **parent delegation** for every class other than `sample.Plugin`: Java APIs, `host.Speaker`, `java.lang.String`, and shared dependencies. For `sample.Plugin`, the loader defines it locally.

The core block:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> found = findLoadedClass(name);
    if (found == null) {
        found = defineClass(name, bytecode, 0, bytecode.length);
    }
    if (resolve) resolveClass(found);
    return found;
}
```

There are four points to understand:

1. `getClassLoadingLock(name)` coordinates concurrent loading calls for the same binary name on a single loader. This aligns with `ClassLoader`'s locking contract.
2. `findLoadedClass(name)` prevents **defining a duplicate a second time in the same loader**. Once the loader has defined the class with that name, subsequent requests return the already-created `Class<?>`.
3. `defineClass(name, bytecode, 0, bytecode.length)` uses the bytecode to create a runtime class whose **defining loader is the current `PluginLoader` instance**. The bytecode's binary name must match `name`; otherwise, the JVM can report errors such as `NoClassDefFoundError`.
4. `resolveClass(found)` is called when the `resolve` argument requests linking/resolution; this does not equate to forcing class initialization.

**Why clone the bytecode?** `PluginLoader`'s constructor uses `bytecode.clone()` so both loaders keep immutable data per the example's intent against external mutation. Cloning bytecode alone does not create separate classes; what decides it is **two `defineClass` calls by two different loaders**.

**Why not override `findClass` for all names?** The lesson aims to demonstrate the phenomenon scoped strictly to `sample.Plugin`. In larger applications, `findClass`/`loadClass` are usually implemented with an explicit strategy, dependency resolution, and namespace protection. This minimal pattern is a test fixture, not a complete production class loader.

## 7. Common Flawed Test: Both Loaders Delegate to the Parent

If you write code like:

```java
ClassLoader parent = TwoLoadersTest.class.getClassLoader();
ClassLoader childA = new ClassLoader(parent) {};
ClassLoader childB = new ClassLoader(parent) {};

// If sample.Plugin is on the app classpath, both typically delegate to the parent.
Class<?> a = Class.forName("sample.Plugin", false, childA);
Class<?> b = Class.forName("sample.Plugin", false, childB);
```

This is an **illustrative snippet depending on a project already having `TwoLoadersTest`/`sample.Plugin`**. With default parent-first delegation and `sample.Plugin` on the application classpath, `a == b` can be `true`.

Do not conclude "the JVM does not support two classes with the same name." The fixture simply has not created two distinct **defining loaders**.

To test properly:

- Ensure the target class is defined locally in each loader (as in the example).
- Print `a.getClassLoader()` and `b.getClassLoader()` or compare them directly.
- Assert `a != b` and `a.getName().equals(b.getName())`.
- Instantiate objects from each respective `Class<?>` and test `isInstance`/`cast`.

## 8. Test Variations Worth Knowing

### 8.1. Same Loader Requesting the Same Name Again

After A has loaded `sample.Plugin`, calling:

```java
Class<?> again = Class.forName("sample.Plugin", false, one);
System.out.println(again == a); // true
```

is an illustrative snippet in the example's `main` context; it shows that **the same loader does not define another copy** once it has cached the class successfully. Repeated requests still return the same `Class<?>`.

If you try calling `defineClass` a second time with the exact same binary name in **the same loader**, the JVM can throw `LinkageError` due to duplicate definition; do not design hot reload by trying to overwrite an old class inside a still-live loader.

### 8.2. Attempting Direct Cast by Class Name from the Host

If the host imports `sample.Plugin` and casts an instance defined by plugin loader A:

```java
// Illustrates the idea; requires host compilation to see sample.Plugin.
sample.Plugin p = (sample.Plugin) instanceA;
```

This can also throw `ClassCastException` because `sample.Plugin` referenced directly by the host is normally the class defined by the application loader, **different** from plugin loader A's `sample.Plugin`. The exception message may mention both loaders, even though both types print the same class name.

### 8.3. What If the Shared Interface Is Also Defined Twice?

Suppose loader A defines both `sample.Plugin` and `host.Speaker` itself, and loader B also defines both classes. Then:

```text
(host.Speaker, loader A) != (host.Speaker, loader B)
```

The host calling `Speaker.class.isAssignableFrom(a)` can return `false`, breaking the shared communication channel. This is a common bug when a plugin bundles duplicate shared APIs inside its own JAR and the class loader resolves APIs child-first.

Reliable plugin design explicitly decides **which packages are shared/delegated** and **which packages are defined by the plugin itself**, while ensuring interface version compatibility.

### 8.4. Same Name, Different Bytecode

Two loaders can load different bytecode versions for the same binary name. They still have distinct type identities. If the bytecode differs in methods, fields, or API signatures, runtime compatibility or linkage errors can also occur when mixing objects, calls, and class loaders.

This lesson uses **identical bytecode** to isolate a single cause: different loaders.

### 8.5. Unloading / Hot Reload

A new loader can define a new generation of `sample.Plugin`. Old-generation and new-generation classes remain two different types even when keeping the same name. Class unloading depends on whether related classes/loaders are still referenced, GC, and runtime conditions; you cannot guarantee immediate unloading just by deleting a JAR file.

After hot reload, avoid keeping old references in static caches, thread context class loaders, threads, or registries; otherwise, the old loader and all of its classes can stay alive.

## 9. Relationship with Reflection and Practical Testing

Reflection commonly returns `Class<?>`, `Method`, `Field`, or `Constructor`. These metadata objects **belong to a specific class defined by a specific loader**. Therefore, when a framework scans plugins and calls `Method.invoke`, it must pass a receiver of the **exact runtime class**, not merely an object whose `getClass().getName()` matches the declaring class name.

Valid check:

```java
// In the context of the example above:
Class<?> targetClass = a;
Object target = targetClass.getDeclaredConstructor().newInstance();
boolean receiverMatches = targetClass.isInstance(target); // true
```

Flawed check:

```java
// Insufficient to confirm compatibility:
boolean nameMatches = target.getClass().getName()
        .equals(b.getName()); // true, yet b.cast(target) still fails
```

**In Reflection caches:** Do not use only `String className` as the cache key if the application has multiple loaders. Use `Class<?>` or a key explicitly tied to loader/class generation, depending on lifecycle policy. Conversely, a global cache holding `Class<?>`/`Method` indefinitely can prevent class unloading; caches must manage plugin lifecycles.

### Suggested Assertions for an Automated Test

With `a`, `b`, `instanceA`, `instanceB`, and `one`/`two` in the program:

```java
// This is a set of assertions to place in a test using the same fixture, not a standalone file.
if (!a.getName().equals(b.getName())) throw new AssertionError();
if (a == b) throw new AssertionError();
if (a.getClassLoader() == b.getClassLoader()) throw new AssertionError();
if (a.isAssignableFrom(b)) throw new AssertionError();
if (b.isInstance(instanceA)) throw new AssertionError();
if (!Speaker.class.isInstance(instanceA)) throw new AssertionError();
if (!Speaker.class.isInstance(instanceB)) throw new AssertionError();
```

These conditions test **essential behavior**, independent of whatever hash code `ClassLoader.toString()` prints. With JUnit, convert them to `assertEquals`/`assertNotSame`/`assertFalse`/`assertTrue`/`assertThrows`; the choice of framework does not change the essence of the test.

## 10. Warnings When Moving the Fixture to Production Systems

- **Do not load untrusted bytecode just for testing.** `defineClass` is not a security sandbox. Loaded code can execute during class initialization or method invocation; control bytecode sources and execution privileges.
- **Do not arbitrarily load all classes child-first.** Duplicating `java.*` or host APIs can cause package-protection errors, loader constraints, incompatibilities, or `ClassCastException`. The JVM enforces protection rules for namespaces such as `java.*`.
- **Keep shared APIs in the parent loader or a common shared loader.** In plugin systems, pass well-contracted DTO types or serialize across boundaries rather than passing internal implementations directly.
- **Pay attention to Java modules (JPMS).** Module readability, `exports`, and `opens` can affect Reflection; the classpath test in the example runs in the **unnamed module** and does not replace tests in named-module deployments.
- **Loader constraints.** When multiple loaders participate in resolving method/field signatures, the JVM can impose identity constraints on shared types. A flawed linking design can trigger `LinkageError` alongside `ClassCastException`.
- **Thread context class loader** can differ from the class loader that defined the thread's code. `Thread.currentThread().getContextClassLoader()` is often used by frameworks to discover resources/services, but it does not automatically merge two same-named types.
- **Do not compare only `getName()`.** When debugging, log class name, defining loader description, and module when needed; always check permissions and avoid leaking sensitive information in logs.

## 11. When Should You Choose a Shared Loader?

If the goal is to **share the exact same type** across parts of a system, have them all delegate loading of that class to one appropriate loader. This keeps runtime type identity unified.

If the goal is to **isolate plugins/versions**, let each plugin loader define its implementations while unifying contracts in a single shared place. This lets plugins reuse binary names without the host confusing implementations with one another.

| Goal | Loading architecture | Verification |
| --- | --- | --- |
| Share one class | Two child loaders delegate to the same defining loader | `a == b` |
| Two isolated implementations | A and B each define the same binary name | `a.getName().equals(b.getName())` and `a != b` |
| Two plugins implementing one contract | Shared interface defined by parent/host loader | `SharedApi.class.isAssignableFrom(a/b)` |
| Hot reload without colliding with old classes | Create a new loader for the new implementation, coordinate lifecycle | Old and new classes have distinct identities; clear references when retired |

## 12. Self-Check Questions

1. Why can two classes with the same `getName()` still not be cast to each other?
2. If two different `ClassLoader`s both delegate the target class to the same parent, what is `a == b`?
3. Does `Class.getClassLoader()` reflect the *defining loader* or always the loader used on the initial call?
4. In the example, why are both `Speaker.class.isAssignableFrom(a)` and `Speaker.class.isAssignableFrom(b)` true while `a.isAssignableFrom(b)` is false?
5. Why must `findLoadedClass` be used when defining classes on demand?
6. Why does hot reload usually create a new loader instead of calling `defineClass` again on the old loader?
7. When an application caches plugin Reflection metadata by class name, what bug can happen after reload?
8. If the shared API interface is also defined separately by two loaders, can the host still cast both plugins to the host's interface safely?

## 13. References

- [Java SE 17: `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock`.
- [Java SE 17: `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isAssignableFrom`, `isInstance`, `cast`.
- [Java Language Specification §12.2: Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): uniqueness of runtime class identity and class loaders.
- [Java Virtual Machine Specification §5.3: Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se17/html/jls-5.html#jvms-5.3): defining loader and initiating loader.