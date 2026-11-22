# Specification Rules, HotSpot Details, and Differences Across JDK Versions

> **Context:** Java Core → ClassLoader → Overview Model. This article distinguishes between what the **JVM/Java SE mandates**, the behavior of the **`ClassLoader` API**, what is commonly observed on **OpenJDK/HotSpot**, and what must be re-verified when changing JDK versions.

## 1. Three Layers of Rules to Distinguish

A phenomenon such as “which loader loaded class A?”, “why can't this be cast?”, or “why doesn't the new JDK find the old class?” can belong to three layers:

| Layer | Source of Rules | What Can You Rely On? |
| --- | --- | --- |
| **JVM Specification (JVMS)** | Class definition, runtime identity, loading, linking, initialization, verification, access control, loading constraints | Compatibility rules of a spec-compliant JVM; does not require a JVM to use HotSpot's internal data structures or exact log ordering |
| **Java SE API/JLS** | `java.lang.ClassLoader`, `Class`, `Module`; JLS §12 | Method contracts, class initialization conditions, default API delegation model, and declared exceptions |
| **JDK/VM Implementation** | OpenJDK/HotSpot, launcher, module runtime image, diagnostic tools | Specific loader class names, JDK file layout, JVM flags, logs, Metaspace/CDS, performance, and memory structure; may change across JDK/VM releases |

**Rule of thumb:** If you want to claim “every JVM works this way,” you must find the basis in the JVMS/JLS or the standard API. If you claim “on HotSpot JDK 17/21/25 you can observe,” specify the version scope and how to verify it.

## 2. Invariants Mandated by the JVMS

### 2.1. A Class's Identity Is Not Just Its Name

For ordinary classes, runtime identity is determined by the pair:

`(binary name, defining class loader)`

Two different loaders calling `defineClass` from bytecode named `example.Plugin` create **two distinct runtime types**, even if the bytes are identical. Therefore:

- Their `Class<?>` objects are not equal; you cannot implicitly cast an object from the first loader to the type defined by the second loader.
- “Same package name” does not automatically grant package-private access. A **runtime package** is defined by *package name + defining loader*; modular access is also subject to module checks.
- Two copies with the same name can coexist when defined by two different defining loaders; a single loader cannot define the same binary name twice in that same way. Duplicate definition causes a linkage error, such as `LinkageError`.

The **defining loader** directly defines the class; the **initiating loader** is the loader that the JVM records as having successfully initiated the loading of the class, possibly via delegation. These two roles are not necessarily the same. Do not infer the defining loader solely from the loader that originally received the `loadClass` call.

### 2.2. Default Delegation Does Not Mean an Immutable Parent-First Rule

The default `ClassLoader.loadClass(String, boolean)` API follows this order: check `findLoadedClass` → try parent (or bootstrap when there is no parent) → call `findClass` if not found → resolve when requested. Therefore, the parent-first diagram is very useful for loaders using the default implementation.

However, the JVMS allows application-defined loaders to perform lookup/delegation in any appropriate manner as long as loading and linking constraints are respected. A loader can be **selectively child-first** to isolate plugins. You should not conclude that “every Java ClassLoader is always parent-first.” Class names shared across boundaries (host/plugin APIs, shared libraries, platform classes) must be unified under a single loader to avoid identity and linkage conflicts.

When writing a custom loader, you need to:
1. Maintain consistency: each loaded name must return the exact same `Class` within the same loader.
2. Follow concurrent loading lock rules, `getClassLoadingLock`, and `findLoadedClass`; only register as **parallel capable** if the implementation supports it.
3. Check allowed namespaces for definition; the JVM/API restricts defining classes in namespaces such as `java.*`.
4. Do not equate “being able to read a `.class` resource” with “having permission to define or access the type” — module/export, signatures, packages, bytecode verification, and security/access rules still apply.

### 2.3. Loading, Linking, and Initialization Are Distinct Phases

| Phase | Meaning | What to Remember |
| --- | --- | --- |
| **Loading** | Find the binary representation and create the class (or the JVM creates an array class) | Does not automatically run `static{}` or static field initializers |
| **Verification** (linking) | Check bytecode validity/type-safety | Malformed class file data can cause `VerifyError` or a form of `LinkageError` |
| **Preparation** (linking) | Create static fields and assign default values | Does not run Java initializers; there is an exception for `ConstantValue` constants as specified by the spec |
| **Resolution** (linking) | Turn symbolic references into runtime references with access/loading constraint checks | Can be performed lazily or eagerly, within the error timing bounds specified by the JVMS |
| **Initialization** | Execute `<clinit>`, static initializers, and static assignments in spec order | Triggered by active use actions listed in the JLS/JVMS; each class is initialized at most once per identity |

The statement “the class is loaded” **does not prove the class has been initialized**. `ClassLoader.loadClass(name)` normally only requests loading; `Class.forName(name, true, loader)` requests initialization. Conversely, `Class.forName(name, false, loader)` does not request initialization. Whether a class has been initialized must be evaluated by its exact identity (name + defining loader), not by name alone.

### 2.4. Type Safety, Loading Constraints, and Related Errors

The JVM enforces **loading constraints** when types in different loaders interact via superclasses, method/field descriptors, etc. If the same type name is required to represent the same runtime type but two loaders resolve to different classes, the JVM may throw `LinkageError`. The goal is to prevent a method call from passing an object whose actual type differs from what the receiver expects.

Commonly confused errors:

| Situation | Typical Symptom | Correct Interpretation |
| --- | --- | --- |
| Calling `loadClass`/`Class.forName` with a name that cannot be found | `ClassNotFoundException` (checked) | The class was not found via the requested loader/loading path |
| Executing bytecode references a class present at build time but unresolvable at runtime | `NoClassDefFoundError` | A runtime type linkage error; can also occur after a failed class initialization |
| Class file is newer than the VM supports | `UnsupportedClassVersionError` | Not a missing class; it is an unsupported **bytecode format/version** |
| Missing method/field at runtime due to binary dependency mismatch | `NoSuchMethodError` / `NoSuchFieldError` | Binary incompatibility; check the classpath/module path and the actual JAR version loaded |
| Access violation during resolution | `IllegalAccessError` | Different from reflective access errors such as `InaccessibleObjectException` |
| Two loaders define the same name, but an object is cast to the other side's type | `ClassCastException`, possibly containing loader descriptions | Two `Class` objects with different identities; matching names do not make them compatible |
| `static{}` throws an exception during initialization | Usually `ExceptionInInitializerError`; subsequent uses may throw `NoClassDefFoundError` | You must find the *first* root-cause error in the logs, not just the follow-up error |

The specification defines the categories of error conditions and valid timings; **log ordering, internal class names, exact stack traces, and error messages** are not stable interfaces for business code to depend on.

### 2.5. Array Classes and Primitives

The JVM creates array classes directly; it does not read a `[Lexample/Foo;.class` file. For an array whose component is a reference type, the defining loader corresponds to the defining loader of the component type; arrays of primitives are associated with the bootstrap loader. Thus `int[].class.getClassLoader()` returns `null`; `Foo[].class.getClassLoader()` follows the loader that defines `Foo`. This is a JVMS rule, not a HotSpot-specific optimization.

## 3. Loader Hierarchy: API Contract and JDK Implementation

For JDK 9+, the common model can be represented as:

~~~text
Bootstrap (VM built-in; Java reflection usually shows null)
    ↑
Platform loader (ClassLoader.getPlatformClassLoader())
    ↑
Application/System loader (ClassLoader.getSystemClassLoader())
    ↑
Custom loaders (if created by the application/framework)
~~~

This diagram is a **teaching model**, not a claim that every class always traverses all nodes. The API documents that the platform loader may need to delegate to another loader when handling certain upgraded modules; classes in modules may be associated with different loaders. The loader hierarchy and JPMS readability/export/access are **two separate control axes**.

- **Bootstrap:** VM built-in loader; in the `Class.getClassLoader()` API it is typically represented as `null`. `null` is not an error and does not mean the class is unloaded.
- **Platform:** loads many platform/JDK classes; JDK 9+ provides `getPlatformClassLoader()`. Do not equate all `java.*` classes with the platform loader: many core classes belong to bootstrap.
- **Application/System:** typically loads code on the class path and some modules; the specific instance can be customized via the system loader mechanism. On JDK 9+, **do not cast the system loader to `URLClassLoader`**; the API does not guarantee that implementation type.
- **Custom:** plugin, container, app server, hot-reload, and module layer loaders. They have a parent, but the parent is not automatically the owner of every class and does not automatically resolve class/resource conflicts.

Verification code in a simple application running on the **class path** of JDK 17+:

~~~java
public class LoaderFacts {
    public static void main(String[] args) {
        System.out.println(String.class.getClassLoader() == null);
        System.out.println(
                LoaderFacts.class.getClassLoader()
                        == ClassLoader.getSystemClassLoader());
        System.out.println(LoaderFacts.class.getModule().isNamed());
        System.out.println(Object.class.getModule().getName());
    }
}
~~~

~~~bash
javac LoaderFacts.java
java -cp . LoaderFacts
~~~

`stdout` under the conditions above:

~~~text
true
true
false
java.base
~~~

The second and third results are specific to a **basic class path** launch, not an invariant of every custom runtime or module layer. `java.base` is the standard module name containing `java.lang.Object`.

## 4. Two Experiments Distinguishing Loading/Initialization and Class Identity

### 4.1. Loading Does Not Automatically Run Static Initializers

File **`InitBoundary.java`** (Java 17+):

~~~java
public class InitBoundary {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = InitBoundary.class.getClassLoader();
        System.out.println("1. before load");
        loader.loadClass(Target.class.getName());
        System.out.println("2. after load");
        Class.forName(Target.class.getName(), true, loader);
        System.out.println("3. after initialization");
    }
}
~~~

~~~bash
javac InitBoundary.java
java InitBoundary
~~~

`stdout`:

~~~text
1. before load
2. after load
Target initialized
3. after initialization
~~~

`Target.class` only obtains the `Class` object without triggering initialization; `loadClass` does not require initialization; calling `Class.forName` with `initialize=true` forces initialization, so the line inside `static{}` appears between the two markers. Re-run in *a new JVM* to repeat the initial state; calling it again in the same JVM will not re-run `static{}`.

### 4.2. Same Binary Name Across Two Defining Loaders Still Produces Two Types

File **`IdentityBoundary.java`** (Java 17+, only illustrates overriding a single class name; do not use this loader as-is in production):

~~~java
import java.io.IOException;
import java.io.InputStream;

public class IdentityBoundary {
    static class Token {}

    private static final String TARGET = Token.class.getName();

    static final class Isolated extends ClassLoader {
        Isolated() {
            super(IdentityBoundary.class.getClassLoader());
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(TARGET)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = findClass(name);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(TARGET)) {
                throw new ClassNotFoundException(name);
            }
            String resource = name.replace('.', '/') + ".class";
            try (InputStream in = IdentityBoundary.class
                    .getClassLoader().getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> left = new Isolated().loadClass(TARGET);
        Class<?> right = new Isolated().loadClass(TARGET);

        System.out.println(left.getName().equals(right.getName()));
        System.out.println(left == right);
        System.out.println(
                left.getClassLoader() == right.getClassLoader());
        System.out.println(left == Token.class);
    }
}
~~~

~~~bash
javac IdentityBoundary.java
java IdentityBoundary
~~~

`stdout`:

~~~text
true
false
false
false
~~~

Explanation: two separate `Isolated` instances read the same `Token` class file, and each loader calls `defineClass`. Same name returns `true`; class identity and loader instances are not the same. `Token.class` from the application loader is a third type. The override only handles the target class so that delegation is preserved for JDK classes and other dependencies; when designing a real plugin system, you need strict namespace policies, dependency resolution, security, and lifecycle management.

**Do not misinfer:** different loaders do not automatically cause a `ClassCastException`. Only when performing an operation that requires two `Class` objects to be compatible (cast, assignment, reflection, method linkage, etc.) will the appropriate error occur. And if a custom loader **delegates**, multiple loaders can return *the same* `Class` defined by the parent.

## 5. ClassLoader Meets the Java Platform Module System (JPMS)

Starting in JDK 9, a module can be placed in a **module layer** and assigned a loader; one loader can host multiple modules. This is not a 1-to-1 module ↔ loader mapping. The ability to load bytecode is different from the ability to **access** a type: JPMS also evaluates readability, `exports` (public API access), and `opens` (rule-based deep reflection). A class present in the runtime image that is not validly readable/accessible from the calling module still cannot be used as an arbitrary public class.

General examples:

- `ClassLoader.loadClass("pkg.Hidden")` may return a `Class`, yet subsequent access can still fail due to module/package access rules.
- `--add-exports module/pkg=target` can open access to public types in an unexported package; `--add-opens module/pkg=target` serves deep reflection. Use them targeted for compatibility/migration, not as a long-term fix instead of public APIs.
- `Thread.currentThread().getContextClassLoader()` (**TCCL**) gives libraries/frameworks the ability to look up providers in the caller's context, typically involving `ServiceLoader`, SPI, containers, and plugins. The TCCL is not the “defining loader of the thread”; it must be set, restored in a `finally` block, and must not retain references to plugin loaders during hot-reload.
- Resource lookup via `getResource` / `getResources` has its own delegation mechanism and may be subject to **module encapsulation**; a resource existing on disk/JAR does not guarantee every loader will return its URL.
- A multi-release JAR (`Multi-Release: true`) can contain different bytecode under `META-INF/versions/N`. The runtime may select the appropriate variant for the running Java version. Thus, “the same JAR name” can still yield different actual classes depending on the JDK.

Do not substitute the parent loader tree for the module graph check; these are two different questions: **who defines the type?** and **who is allowed to read/access the type?**

## 6. HotSpot: What Is Commonly Seen but Should Not Be Treated as a JVMS Rule

### 6.1. Class Sources and Runtime Structure

- On **JDK 8**, JDK classes typically reside in `rt.jar` and the extension mechanism; many applications encounter `ExtClassLoader` / `AppClassLoader` in implementation names.
- Starting in **JDK 9**, the runtime image uses the module system and system resources may appear with the `jrt:/` scheme. The extension loader became the **platform loader**, and applications must not assume the system loader is a `URLClassLoader` or that `java.home/lib/rt.jar` exists.
- HotSpot stores class metadata in **Metaspace** (since JDK 8; replacing PermGen). Metaspace is a HotSpot memory management detail; the JVMS describes the method area but does not require every JVM to lay out a “Metaspace” like HotSpot.
- HotSpot may use Class Data Sharing (CDS), archived classes, lazy resolution, and load/link optimizations depending on build and configuration; do not infer from a “source” log that a class is always read byte-by-byte directly from that exact path.
- Class unloading relates to the reclaimability of the loader/class and GC; it does not happen immediately upon calling `URLClassLoader.close()`. `close()` releases closeable handles/resources; classes and loaders that are still referenced are not yet freed.

### 6.2. Tool-Based Diagnostics, Not Internal Names

The example commands are for **OpenJDK/HotSpot on JDK 17+**; other versions may have different option names or amounts of detail:

~~~bash
# Print the class loading process (logs can be very long).
java -Xlog:class+load=info InitBoundary

# Also show class unloading events (if GC actually unloads classes).
java -Xlog:class+load=info,class+unload=info InitBoundary

# Legacy compatibility syntax from older JDKs, with less detail/filtering.
java -verbose:class InitBoundary

# Run with the PID of a live Java process, if jcmd can attach.
jcmd <pid> VM.classloaders
jcmd <pid> VM.classloader_stats
~~~

`jcmd` commands depend on the target JVM, attach permissions, container environment, and the list of diagnostic commands supported by the VM; run `jcmd <pid> help` to confirm which commands are actually available. `VM.classloaders` is useful for seeing the hierarchy, and `VM.classloader_stats` for viewing statistics, but they are **not** a standard output contract of the Java language.

When investigating an issue, record `java -version`, the JDK vendor, how the app is launched on the classpath/module path, the set of JARs, and the JVM command line together. Log output changes across JDKs, and enabling extra logging can affect performance; do not parse with regexes that depend on names like `jdk.internal.loader.ClassLoaders$AppClassLoader`.

### 6.3. Loader Lifecycle and Memory Leaks in Containers/Plugins

Class unloading depends on there being no remaining references keeping the loader/class alive; a single GC cycle also does not guarantee unloading happens immediately. Common sources of retained references: static registries on the host, `ThreadLocal`, long-lived threads, thread context class loaders, executors/schedulers, listeners, JMX, callbacks, and caches holding `Class`/`Method`. When reloading a plugin:

1. Stop tasks and threads owned by the plugin; unregister listeners/registrations.
2. Restore the TCCL after use and clean up `ThreadLocal`/caches holding plugin objects or classes.
3. Close `URLClassLoader`/resources if applicable; then drop strong references to the loader, instances, and classes.
4. Monitor loader/class counts, GC, and Metaspace across multiple reload cycles; use tools appropriate for your HotSpot version.

Do not use a single measurement of Metaspace MB growth to conclude there is a leak: observe the trend across multiple GC/reload cycles and distinguish VM caching/committed memory behavior.

## 7. Key Differences Across JDK Versions

| Version | Differences to Remember When Learning/Implementing ClassLoader | Common Class File Major |
| --- | --- | ---: |
| **JDK 8** | Pre-JPMS; heavy classpath/`rt.jar`/extension dirs configurations; PermGen replaced by Metaspace on HotSpot | **52** |
| **JDK 9** | JPMS (`module-info.java`, module path, layer); **platform** loader replaces extension; modular runtime image, `jrt:/`; system loader can no longer be assumed to be `URLClassLoader`; unified logging `-Xlog` | **53** |
| **JDK 11** | Java EE/CORBA modules listed in JEP 320 removed from the JDK; legacy apps may hit missing classes even though the loader works properly | **55** |
| **JDK 15** | **Hidden classes** (JEP 371), used by dynamic runtimes/frameworks; a hidden class's `Class.getName()` is not necessarily a normal binary name; do not assume it can be reloaded via `Class.forName` | **59** |
| **JDK 17** | Strong encapsulation of JDK internals (JEP 403); `--illegal-access` no longer has its previous broad effect; reflection may hit `InaccessibleObjectException` | **61** |
| **JDK 21** | Core JVMS rules on class identity/loading still apply; re-check HotSpot tools, module configuration, and class file versions when upgrading | **65** |
| **JDK 25** | Continues JVMS/JPMS boundaries; do not rely on internal loader names, VM options, or logs from JDK 8/11 as a long-term contract | **69** |
| **JDK 26** | Class file major increases with release; programs compiled with a newer JDK's default target may not run on older runtimes | **70** |

**Distinguish versions:** the **Java source** version, the class file target of `javac --release N`, and the **runtime JVM** are three separate pieces of information. For example, an application running on JDK 17 that loads a `major=65` file compiled for Java 21 can receive `UnsupportedClassVersionError`. Lowering `--release` only addresses bytecode target and permitted compile-time APIs; it cannot fix third-party APIs requiring a newer JDK or semantic differences caused by JPMS, reflection, or custom loaders.

Verification commands:

~~~bash
java -version
javac -version
javap -verbose LoaderFacts
~~~

In the `javap -verbose` output, look for the `major version` line. When inspecting a JAR containing multiple class versions, identify the actual selected entry (including multi-release JARs) before drawing conclusions.

### 7.1. JDK 8 → 17/21/25 Upgrade Examples: Which Layer Does the Change Belong To?

**Case A — legacy code casting the system loader:**

~~~java
// Often works on some JDK 8 environments; not an API contract.
java.net.URLClassLoader loader =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

On many JDK 9+ HotSpot builds, this cast leads to `ClassCastException`. The proper fix is to use the `ClassLoader`/`getResource` API when you only need to load resources, or manage an application-created `URLClassLoader` if you genuinely need to manipulate URLs. Do not test by casting internal loaders.

**Case B — accessing `sun.*`/`jdk.internal.*` via reflection:** JDK 17+ may block this under default module encapsulation. This is primarily a JPMS/runtime access restriction, not the parent loader “forgetting to load” the class. Prefer supported APIs; only use `--add-opens`/`--add-exports` for specific packages while migrating dependencies.

**Case C — missing `javax.xml.bind` when moving to JDK 11+:** Java EE/CORBA modules were removed from the JDK. You must add a compatible dependency and consider the right namespace/version; creating a child-first loader does not bring back removed APIs on its own.

**Case D — plugin with two library versions:** a plugin loads the same FQCN in a different loader from the host API. Casts or linkage can fail. Place shared interfaces under a unified parent/loader; explicitly choose which packages are delegated and which are isolated; inspect transitive dependencies and TCCL.

## 8. Investigation Workflow When Seeing ClassLoader-Related Errors

1. **Identify the first error:** capture the full exception/cause/stack trace, distinguishing checked `ClassNotFoundException` from `LinkageError`, `ClassCastException`, and `InaccessibleObjectException`.
2. **Determine the runtime context:** `java -version`, VM vendor, flags, launch classpath/module path, module layer, and class file major version.
3. **Check where the class is defined:** `clazz.getName()`, `clazz.getClassLoader()`, `clazz.getModule()`, and resource path/code source where appropriate; avoid printing sensitive information from production environments.
4. **Check which dependency version was actually selected:** duplicate JARs, version mediation, shaded packages, multi-release entries, classpath/module path, and classload order.
5. **Separate “finding” issues from “access” issues:** does the class not exist/fail to resolve, is the module not readable/exported/open, is the package sealed, is the bytecode too new, or do loaders have different identities?
6. **Create a minimal reproduction:** a single Java file or a small plugin with the same loader pattern; compare the same workload on the target JDK versions you need to support.
7. **Use diagnostics with caution:** `-Xlog:class+load` or `jcmd` if available; cross-check against the API and specification, because HotSpot logs/class names are not stable APIs.

### Self-Check Knowledge Checklist

- If two classes have the same FQCN but different defining loaders, are they necessarily the same type? **No.**
- If `ClassLoader.loadClass` succeeds, has `static{}` definitely run? **No.**
- If a class is in the runtime image, can every other module reflectively access it? **No.**
- Is the parent-first diagram the only algorithm every loader is forced to use? **No.**
- Is `String.class.getClassLoader() == null` on HotSpot an error? **No**, that is how the API represents the bootstrap loader.
- Are `java -Xlog:class+load` and the name `AppClassLoader` mandated by the JVMS? **No**, they are JDK/VM implementation/tooling details.
- Does `URLClassLoader.close()` guarantee immediate unloading? **No.**
- Does a `NoClassDefFoundError` always mean a JAR file is missing? **No**; you must trace back to linkage or a failed initialization.

## 9. Authoritative References

1. [JVMS `5 — Loading, Linking, and Initializing (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html) — defining/initiating loader, class identity, loading constraints, runtime package, linking, and initialization.
2. [`ClassLoader` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — default delegation, built-in loaders, parallel capable, resource lookup.
3. [JLS §12 — Execution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html) — class initialization and active use scenarios.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261) — module/loader changes since JDK 9.
5. [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320) — why legacy classes are no longer in JDK 11.
6. [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) — special dynamic class mechanism since JDK 15.
7. [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) — accessing JDK internals since JDK 17.
8. [`jcmd` tool (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — `VM.classloaders` and `VM.classloader_stats` commands.
9. [JAR File Specification — Multi-release JAR](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) and [`ClassFile` versions (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFile.html) — bytecode differences by version.

**Key takeaway:** whenever discussing ClassLoader, first determine whether the statement belongs to the *JVMS/JLS specification*, the *Java SE API contract*, or a *HotSpot observation on a specific JDK*. Doing so lets you explain compatibility errors accurately, choose fixes that remain maintainable across JDK upgrades, and avoid relying on unguaranteed implementation details.
