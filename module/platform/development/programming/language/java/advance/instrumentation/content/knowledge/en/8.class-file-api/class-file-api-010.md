# Choosing a Class-Loader-Appropriate Resolver to Avoid Unintended Class Loading

## 1. The Problem in the Java Class-File API

When using the **Java Class-File API** to generate, transform, or inspect bytecode, there are times when the tool needs to know the inheritance and interface relationships of classes appearing in the bytecode. For example, when computing `StackMapTable` at the merge point of two control-flow branches, the tool may need to determine the appropriate common type of two reference values.

The Java Class-File API provides the **`java.lang.classfile.ClassHierarchyResolver`** interface for looking up class hierarchy information. An important pitfall when writing a **Java agent** is that the default resolver uses **reflection and the system class loader**, which can cause unloaded classes to be loaded while the JVM itself is processing class loading.

A transformer may encounter the following consequences:

- Accidentally triggering `ClassLoader.loadClass(...)`, altering the timing and order of class loading.
- Loading the wrong class if the target class only exists in a plugin loader, container loader, module layer, or a specialized loader.
- Seeing hierarchy information for **the same binary name but a different class definition**, producing invalid stack map frames.
- Encountering recursion or circularity while transforming a class and then asking the loader to load a related class.
- Causing side effects from custom loaders: network access, class decryption, logging, synchronization, or the agent's own callbacks.
- Encountering `NoClassDefFoundError`, `LinkageError`, `VerifyError`, or Class-File API errors because the correct hierarchy cannot be found.

**Core principle:** **Knowing the inheritance structure does not require defining or loading a class into the JVM.** Choose a resolver that obtains metadata directly from class files/resources or known data, in **the right class loader namespace**, instead of defaulting to reflection.

**Version:** `java.lang.classfile` and `ClassHierarchyResolver` are official APIs starting from **JDK 24** (JEP 484; preview iterations in earlier JDKs may have different APIs). The examples use **JDK 24 or later** and cannot be compiled with JDK 17. The JVM and `java.lang.instrument` concepts are still useful for Java 17+, but **do not use the `java.lang.classfile` API on Java 17**.

## 2. Why Does the Class-File API Need Inheritance Relationships?

In bytecode, there are **verification types** on the operand stack and in local variables. At a point where two branches converge to the same instruction, the verifier needs a common type state that can be shared.

Example logic:

```java
Object select(boolean flag) {
    Object result;
    if (flag) {
        result = new java.util.ArrayList<>();
    } else {
        result = new java.util.LinkedList<>();
    }
    return result;
}
```

When generating or recomputing stack map frames, the tool may need to know which classes/interfaces `ArrayList` and `LinkedList` inherit from to determine the appropriate value type at the merge point. Choosing the wrong hierarchy can make `StackMapTable` inconsistent with the actual bytecode.

Distinctions to keep in mind:

- **Parsing a class file**: most information can be read from bytes without loading the class; the model is built lazily by the Class-File API.
- **Generating stack maps / verifying a class**: may require information about **other classes** besides the class being transformed.
- **Loading a class by the JVM**: creating/linking a `Class<?>` object through class loading; this is different from reading a `.class` file.
- **Initializing a class**: executing `<clinit>` when initialization conditions are met; class loading and initialization are not synonymous. Although a reflection-based resolver does not necessarily initialize a class, **premature class loading alone is already a risk** for an agent.

For tasks that compute frames, the resolver selection policy should be decided **before** generating the class file, rather than waiting for a `VerifyError` and guessing a fix.

## 3. What Is `ClassHierarchyResolver`?

The `java.lang.classfile.ClassHierarchyResolver` interface provides hierarchy information to the Class-File API when generating stack maps and verifying bytecode. Its core method:

```java
ClassHierarchyResolver.ClassHierarchyInfo getClassInfo(ClassDesc classDesc);
```

`ClassDesc` belongs to `java.lang.constant` and is a **symbolic type descriptor**, not a `Class<?>` object. For example, `ClassDesc.of("com.example.Service")` only constructs a descriptor; it **does not load the `Service` class itself**.

According to the specification:

- The resolver returns `ClassHierarchyInfo` if it knows the corresponding class/interface.
- It returns `null` if unknown; this signals another resolver in an `orElse(...)` chain to try looking it up.
- It may throw `IllegalArgumentException` when valid information cannot be provided, for example when a class is not accessible for lookup.
- **Normal applications do not need to call `getClassInfo` directly.** The Class-File API calls this method during stack map computation/verification; applications should configure the resolver using `ClassFile.ClassHierarchyResolverOption.of(...)`.

How to attach a resolver:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;

ClassHierarchyResolver resolver = /* choose based on class environment */;
ClassFile cf = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver));
```

The snippet above **illustrates where to attach the configuration**, not a standalone program; the `resolver` variable must be created from a concrete option in the next section.

`ClassFile.of()` **without passing an option** will use the default resolver. For an agent, do not assume the default is safe enough.

## 4. Distinguishing the Resolver Types

### 4.1. `defaultResolver()`: simple but risks class loading

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.defaultResolver();
```

According to the JDK 24 Javadoc, the default resolver obtains the hierarchy via reflection through the **system class loader**. It **can load unloaded system classes**, and **cannot properly look up** classes that only exist in another class loader.

It is reasonable to use in tests or small tools where class loading is intentionally accepted and all relevant classes are properly present via the system loader. **Do not choose the default for a bytecode transformer running while the JVM loads classes** if avoiding additional loading is required or the system has multiple loaders.

### 4.2. `ofClassLoading(ClassLoader loader)`: reflection using a specified loader

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(targetLoader);
```

This approach uses reflection with the provided loader to read the hierarchy. It helps avoid **using the wrong system loader** when a class belongs to a custom loader, but it does **not** eliminate the possibility that the loader may be invoked to load additional classes.

Use it when you **intentionally allow class loading**, the correct loader has been chosen, and the execution point is not on a sensitive transformation path. Be especially careful with plugin/container loaders because `loadClass` may call back into application code or have side effects.

**Do not confuse:** `Class.forName(name, false, loader)` (which does not request initialization) **can still load/link a class**. Passing `false` does not turn reflection into metadata-only resolution.

### 4.3. `ofClassLoading(MethodHandles.Lookup lookup)`: reflection with access restrictions

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(lookup);
```

Uses classes accessible to a `MethodHandles.Lookup`; if a class is not accessible through the lookup, the API may throw `IllegalArgumentException` instead of returning `null`. This is a visibility/lookup control mechanism, **not a guarantee against loading classes**.

Suitable when loading via reflection is permitted and the lookup environment needs to be governed by module/access rules.

### 4.4. `ofResourceParsing(ClassLoader loader)`: reads `.class` resources without using reflection to create `Class<?>`

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(targetLoader);
```

The resolver reads structural information from **class file resources** found by that loader, instead of loading classes via reflection. This is often a good choice for an agent when the loader can provide the right resources.

Limitations to understand:

- **Resource lookup is not the same as class definition.** A custom loader may define classes from decrypted bytes, dynamically generated bytes, an in-memory cache, or sources without an accessible `.class` file.
- `getResourceAsStream` may have custom behavior, I/O, or callbacks implemented by the loader. "Not creating `Class<?>` via reflection" **does not mean zero side effects**.
- If the resource in the loader is a **different version** of the bytes being defined by the JVM, the hierarchy result may be wrong.
- You need to consider delegation mechanisms, module resources, and the same class name appearing in multiple loaders.

For an agent using `ClassFile` to generate stack maps for a class just received in `ClassFileTransformer.transform(...)`, `ofResourceParsing` is usually safer than `ofClassLoading` **if** the resource source actually matches the class definitions.

### 4.5. `ofResourceParsing(Function<ClassDesc, InputStream>)`: full control over the byte source

When a loader does not provide the right resources, use a deliberate mapper:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(desc -> {
            // Select the right InputStream based on ClassDesc, loader/module,
            // artifact version, and known bytes.
            // Return null if no reliable source is found.
            return findClassFileStream(desc);
        });
```

This is an **illustrative snippet**, not standalone code: `findClassFileStream` represents your system's function.

The mapper can read class files from a JAR, build directory, in-memory archive, or an agent-managed snapshot. **Return `null` when not found** so that a subsequent resolver can try; **do not secretly call `Class.forName`** to make up for a missing resource if the goal is to avoid class loading. The stream must be supplied with the exact class file contents and have its opening/closing managed according to the API.

If the I/O stream throws `IOException`, the resolver may wrap it into `UncheckedIOException` during lookup. You must distinguish **not found** from **read error** so you do not silently generate wrong frames.

### 4.6. `of(interfaces, classToSuperClass)`: hierarchy purely from metadata

```java
import java.lang.constant.ClassDesc;
import java.util.List;
import java.util.Map;

ClassDesc task = ClassDesc.of("demo.Task");
ClassDesc base = ClassDesc.of("demo.Base");
ClassDesc impl = ClassDesc.of("demo.Impl");

ClassHierarchyResolver metadata =
        ClassHierarchyResolver.of(
                List.of(task),
                Map.of(impl, base,
                       base, ClassDesc.of("java.lang.Object")));
```

This is an example of configuring **limited metadata**: the `interfaces` collection indicates types treated as interfaces; the map provides the class → superclass relationships known to the system. The example **does not fully describe** every interface a class implements; to generate frames on real bytecode, the resolver must return an accurate enough hierarchy for the types encountered, not just two sample entries.

Advantage: no need to call a loader or read class files when complete metadata is available. Suitable for offline/build pipelines or agents with a reliable hierarchy snapshot. Not suitable if the hierarchy is missing required classes/interfaces.

### 4.7. `orElse(...)`: layering trusted sources

```java
ClassHierarchyResolver resolver =
        primaryResolver.orElse(fallbackResolver);
```

If `primaryResolver` returns `null` because it does not know a type, the second resolver is queried. Do **not** treat `orElse` as a mechanism to catch all exceptions or fix an incorrect hierarchy from the first source: when the first source returns an **incorrect but non-null** result, the fallback is not queried.

Recommended order for an instrumentation tool with archives/snapshots:

```text
1. Snapshot/metadata for the exact target loader & class bytes
        |
        +-- type unknown -> 2. Resource parsing from the right source
                                    |
                                    +-- type unknown
                                           -> 3. Trusted JDK/platform resources
        |
        +-- still unknown -> report a clear error, do not load blindly
```

Do not use `orElse(defaultResolver())` as an unconditional fallback for an agent that must **not load classes**: it inadvertently reintroduces reflection into the pipeline.

### 4.8. `cached()`: reduces I/O but carries stale data risks

```java
ClassHierarchyResolver resolver =
        underlyingResolver.cached();
```

The JDK 24 Javadoc explicitly states that `cached()` is **not thread-safe** by default, and the cache also stores **`null`** results when a class name is not yet known. This leads to:

- A new class appearing after the cache has recorded `null` may still be treated as nonexistent.
- If a class is redefined or its resource is updated, the old cache may reflect an outdated hierarchy.
- Caching by name but sharing across **two different class loaders** will mix namespaces and is very dangerous.
- Long-lived caches may retain unnecessary objects or data; scope their lifecycle to loader/artifact/version.

If multiple threads are involved, use the `cached(Supplier<Map<...>>)` overload with an appropriate thread-safe map strategy and test for correctness. Do not share a cache across loaders that can define the same binary name with different hierarchies.

## 5. Resolver Selection Table by Scenario

| Context | Preferred | Why |
| --- | --- | --- |
| Agent transforming classes at load time, with reliable `.class` resources from loader | `ofResourceParsing(targetLoader)` | Reads class file metadata, avoiding asking the JVM to create `Class<?>` via reflection |
| Agent receives class bytes from memory/custom loader, resources may differ | `ofResourceParsing(Function)` with exact byte mapping + dedicated metadata | Does not rely on a mismatched resource lookup |
| Offline/build pipeline, full hierarchy already available | `of(interfaces, classToSuperClass)` | No class loading, no I/O when metadata is complete |
| Generating frames for custom classes and JDK classes | Custom source resolver `orElse` appropriate JDK resource resolver | Preserves priority order and avoids class loading |
| Test tool using only system classpath where class loading is acceptable | `defaultResolver()` | Easy to use, but unsuitable for agents avoiding loading |
| Runtime with custom loader where class loading is intentional | `ofClassLoading(targetLoader)` | Reflection on the right loader, accepting loading side effects |
| Need restrictions based on `MethodHandles.Lookup` permissions | `ofClassLoading(lookup)` | Controls access, does **not** eliminate loading |
| Repeated resolutions for the same immutable artifact/loader | `cached()` or cache with appropriate map | Reduces cost, but requires invalidation/thread-safety policy |

**Rule:** Choose a resolver based on **the source of truth for the hierarchy** and **the right class-loader namespace**, not the shortest code to write.

## 6. Runnable Java 24 Example: Recomputing Stack Maps Without Calling `loadClass` on the Class Source

This example compiles a real class file with `javac`, then reads and transforms it using the Class-File API and a `ClassLoader` intentionally designed to **serve resources only**. Every `loadClass(...)` call to the source loader is counted and rejected, proving that the resolver does not use class loading through the source loader.

Note on test scope: the Java runtime itself loads the **JDK classes needed to run the tool**, so the measurement only monitors **the loader used to supply application class files**. It does not claim that no classes at all are loaded in the entire JVM.

Create the directory structure:

```text
resolver-demo/
├── sample/
│   └── Example.java
└── NoLoadResolverDemo.java
```

### 6.1. `sample/Example.java`

```java
package sample;

import java.util.ArrayList;
import java.util.LinkedList;

public final class Example {
    public static Object choose(boolean first) {
        Object result;
        if (first) {
            result = new ArrayList<String>();
        } else {
            result = new LinkedList<String>();
        }
        return result;
    }
}
```

The method has two branches and a reference-type merge point. The Class-File API will be asked to **regenerate stack maps** when building the output.

### 6.2. `NoLoadResolverDemo.java`

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class NoLoadResolverDemo {
    private NoLoadResolverDemo() {
    }

    // Allows reading .class resources in the directory,
    // but disallows using this loader to define classes.
    private static final class ResourceOnlyLoader extends ClassLoader {
        private final Path root;
        private int loadRequests;

        ResourceOnlyLoader(Path root) {
            super(null); // Do not set a Java parent loader.
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        public InputStream getResourceAsStream(String name) {
            Path file = root.resolve(name).normalize();

            // Prevent the resource name from escaping the root directory.
            if (!file.startsWith(root)) {
                return null;
            }

            try {
                return Files.newInputStream(file);
            } catch (NoSuchFileException missing) {
                return null;
            } catch (IOException failure) {
                throw new UncheckedIOException(failure);
            }
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            loadRequests++;
            throw new ClassNotFoundException(
                    "Class loading is disabled: " + name);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("classes");
        ResourceOnlyLoader files = new ResourceOnlyLoader(root);

        ClassHierarchyResolver appResources =
                ClassHierarchyResolver.ofResourceParsing(files);

        // Only read JDK class-file resources via the platform loader.
        // Do not use defaultResolver() / ofClassLoading(...).
        ClassHierarchyResolver jdkResources =
                ClassHierarchyResolver.ofResourceParsing(
                        ClassLoader.getPlatformClassLoader());

        ClassHierarchyResolver resolver =
                appResources.orElse(jdkResources).cached();

        ClassFile cf = ClassFile.of(
                ClassFile.ClassHierarchyResolverOption.of(resolver),
                ClassFile.StackMapsOption.GENERATE_STACK_MAPS);

        byte[] source = Files.readAllBytes(
                root.resolve("sample/Example.class"));

        ClassModel model = cf.parse(source);
        byte[] rewritten = cf.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println("parsed=" +
                model.thisClass().asSymbol()
                        .equals(ClassDesc.of("sample.Example")));
        System.out.println("rebuilt=" + (rewritten.length > 0));
        System.out.println("verified=" + cf.verify(rewritten).isEmpty());
        System.out.println("sourceLoadRequests=" + files.loadRequests);
    }
}
```

Design explanation:

1. `ResourceOnlyLoader` only serves `.class` files via `getResourceAsStream(...)`. If the Class-File API or configuration accidentally requests `loadClass` on this loader, the program records/blocks the call.
2. `appResources` looks up `sample` classes from the compiled directory. It does not rely on the system classpath to guess the hierarchy of custom classes.
3. `jdkResources` reads JDK class-file resources through the platform loader; it is not equivalent to `defaultResolver()`, which uses reflection. In specialized applications, an explicit mapper from the module/JDK image may be needed to ensure accurate resource sources.
4. `orElse` prioritizes the hierarchy from the application directory, then falls back to JDK resources.
5. `GENERATE_STACK_MAPS` instructs the Class-File API to recompute stack maps when building the output, rather than just copying existing frames. Correctness depends on the chosen hierarchy.
6. `ClassTransform.ACCEPT_ALL` forwards class elements without intentionally changing logic; the example focuses solely on **resolver selection and class file round-tripping**.
7. `cf.verify(rewritten)` checks the result using the API in the same context; this is an additional check, not a substitute for loading/running on the target JVM.
8. The program **does not use `Class.forName("sample.Example")`**; it only works with bytes and `ClassModel`.

### 6.3. Compile and Run

Open a terminal in the `resolver-demo/` directory. **JDK 24+** is required for `java.lang.classfile`:

```bash
mkdir classes
javac --release 24 -d classes sample/Example.java NoLoadResolverDemo.java
java -cp classes NoLoadResolverDemo
```

On JDK 24 with standard class resources and Class-File API support, expected stdout:

```text
parsed=true
rebuilt=true
verified=true
sourceLoadRequests=0
```

There are no `loadClass` calls to `ResourceOnlyLoader`. The `javac` command compiles both classes before running; at runtime, the program only **reads** `sample/Example.class` and does not define `sample.Example` as a `Class<?>`.

**Important verification note:** `sourceLoadRequests=0` only proves that the resolver did not call `loadClass` on **the instrumented source loader**. It does not prove that `ClassFile` opened no resources, performed no I/O, or that the JVM loaded no JDK classes to run the tool itself. If you want to verify every class loading event in an agent environment, add checks using `Instrumentation.getAllLoadedClasses()` or monitor class loading events at the JVM level.

If a JVM/system has different module resource policies that prevent `jdkResources` from supplying a required class file, replace the fallback with **a controlled `jrt:/` or archive source** instead of reverting to reflection. That is an **insufficient hierarchy source** issue, not a reason to automatically load all classes.

### 6.4. Counterexample: why changing the resolver can be dangerous?

Replace the resolver selection line with:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofClassLoading(files);
```

When the Class-File API needs hierarchy information beyond what it already has, it may call `files.loadClass(...)` to try to obtain `Class<?>`. The demo loader will reject it, and generation/verification may fail. **This is a risk counterexample**, not a recommended variant for running successfully.

Similarly, using `ClassHierarchyResolver.defaultResolver()` may load via the **system loader** and see a different version of `sample.Example` than the file the demo is rewriting. For an agent serving plugin/custom loaders, that is a **correctness** issue in addition to performance side effects.

## 7. Choosing a Resolver in a Real `ClassFileTransformer`

A transformer receives parameters such as:

```java
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

In an agent's problem space, `loader` is the **defining class loader** of the class being transformed:

- `loader == null` represents the bootstrap loader.
- `loader != null` is a specific class loader instance; it is not necessarily the system loader.
- `className` is typically a JVM internal name using `/` separators.
- `classfileBuffer` is **the bytes of the class currently being processed by the JVM**, which may differ from the `.class` file a loader returns via resource lookup.
- During retransformation, class bytes may be resupplied by the JVM through a mechanism different from "reading the exact same file on disk."

Options:

### 7.1. Prioritize the snapshot/bytes from the callback as the source for the current class

If the resolver may need the hierarchy of the class currently being transformed, the most accurate choice is usually **the current `classfileBuffer`** (or metadata derived from those same bytes), rather than defaulting to `loader.getResourceAsStream(className + ".class")`, because that resource may:

- Not exist (the loader defines classes from in-memory data);
- Point to a different version if a transformer processed it earlier;
- Be generated/decrypted differently than in `loadClass`;
- Reside in a nested module/JAR that normal resource search cannot see.

The `ofResourceParsing(Function)` mapper lets you return a `ByteArrayInputStream` from the exact byte snapshot of the target class, then find dependent classes in dedicated sources sharing **the same class-loader namespace**.

**Illustrative snippet for the stream-selection step** (not a standalone program):

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.constant.ClassDesc;

ClassDesc target = ClassDesc.of("com.example.Service");
byte[] targetBytes = classfileBuffer.clone();

ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(desc -> {
            if (desc.equals(target)) {
                return new ByteArrayInputStream(targetBytes);
            }

            // Everything else must be read from the right source for each class
            // in the target loader's namespace and module.
            return trustedStreamFor(desc);
        });
```

This snippet assumes `classfileBuffer` and `trustedStreamFor` are provided by the transformer and the agent's infrastructure. **`trustedStreamFor` is not a JDK method**. In real code, `target` is determined from the internal class name in the callback, rather than hard-coding every class to `com.example.Service`.

If the transformer runs while the JVM is still defining a class, avoid calling `Class.forName` or executing application code from inside the mapper. It can trigger the loader again or cause recursion.

### 7.2. The bootstrap loader needs a separate branch

When `loader == null`, **do not call `loader.getResourceAsStream(...)`**. You can obtain the platform hierarchy from the JDK/module image source and the hierarchy of agent-added bootstrap search classes from known JARs. Do not assume the platform loader can see every class in JARs appended to the bootstrap classpath by the agent.

For core `java.base` classes, consider reading class files via runtime-appropriate resources/JRT. For application classes on the bootstrap search path added by the agent, read from the exact appended archive/snapshot. Being on the bootstrap loader does not mean a class name starts with `java/`.

### 7.3. Do not reuse a resolver across two non-equivalent loaders

Two loaders can define **the same binary name** with different superclasses:

```text
Plugin loader A: com.demo.Task extends com.demo.BaseA
Plugin loader B: com.demo.Task extends com.demo.BaseB
```

`ClassDesc.of("com.demo.Task")` produces the same symbolic descriptor in both cases, but the hierarchy relationships of the two definitions **are not the same**. A resolver cache shared by `ClassDesc` without distinguishing the loader can produce wrong stack maps.

Rule: create a resolver/cached context scoped to the exact **loader + module layer/artifact/version** when those factors can affect class definitions. Do not hold a strong reference to a plugin `ClassLoader` indefinitely just to cache metadata.

## 8. Resource Parsing Still Requires Defensive Design

### Do not equate a resource with the class actually defined

`ClassLoader.getResourceAsStream("com/demo/Foo.class")` is a **resource lookup**. It is not guaranteed to return the exact bytes that `ClassLoader.loadClass("com.demo.Foo")` used. A loader might use child-first delegation for classes but parent-first for resources, or decrypt/transform bytes inside `findClass`.

When in doubt, prioritize **snapshots at the define/transform point** and metadata provided by the build/deployment. If there is not enough data to generate reliable frames, report a clear error; do not write a class file you cannot prove valid.

### Do not treat "no class loading" as "no side effects"

A resource-reading resolver can execute custom `getResourceAsStream` code, open files, read network storage, decompress JARs, or mutate caches. When instrumentation runs on a hot path, avoid slow I/O, reentrant code, and locks that can deadlock with the loader.

Build an **immutable resource snapshot** or a reasonably scoped cache, measure latency, and limit the number of lookups.

### Be careful with modules and access permissions

Java 9+ distinguishes class loaders, module layers, and access. A class in a named module may not have resources visible in the same way as a class on the regular classpath. `MethodHandles.Lookup` also has its own access restrictions. Verify resource sources and hierarchy semantics against the actual module environment.

**Do not fix errors by blindly opening modules or bypassing access** just so the parser can read a class file. A stream obtained from a trusted source may be enough to compute metadata without altering the application's module/runtime mechanisms.

## 9. Cache and Fallback Correctness

**Cache misses:** `cached()` can store **`null`**. If a plugin loads a new class file after the cache has recorded "unknown," the old resolver may not automatically see the new one. You must create a new resolver or manage invalidation by version.

**Thread safety:** `cached()` is **not thread-safe** by default. A multi-threaded agent may register multiple transformers and load classes concurrently; choose a cached resolver with an appropriate synchronization policy if shared across threads. Customize `cached(Supplier<Map<...>>)` if you need a map with specific thread-safety characteristics.

**Wrong fallback order:** A resolver reading the system classpath that returns a successful result for a class name also defined by a plugin will prevent the plugin source from being queried. Therefore, you must **prioritize the target class's source first**; `orElse` does not automatically detect wrong results.

**Unexpected fallback loading:** If you use `resourceResolver.orElse(ClassHierarchyResolver.defaultResolver())`, the final branch can still load classes. When **no loading** is required, every fallback branch must satisfy that requirement too.

**Errors must be surfaced:** If the hierarchy is insufficient, do not temporarily assign `java.lang.Object` to everything and assume it is right. Stack map verification has constraints on classes/interfaces, arrays, and assignment compatibility; a wrong "approximation" can lead to `VerifyError` or classfile generation errors.

## 10. Distinguishing Error States

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Agent loads extra classes during bytecode rewriting | `defaultResolver()` or `ofClassLoading(...)` uses reflection | Switch to a controlled resource/metadata resolver and test class load counts |
| `ClassNotFoundException` in custom loader | Reflection asks the loader to find an unloaded class | Check call paths; avoid using a loading resolver on hot paths |
| `IllegalArgumentException` during generate/verify | Missing hierarchy, class inaccessible via `Lookup`, or incompatible bytecode | Check class/module/loader, supply the right metadata source; do not fall back to blind loading |
| `UncheckedIOException` during resource resolution | `.class` stream has a read error | Fix resource storage/source, log class/source name, distinguish from "not found" |
| `VerifyError` after transformation | Stack frames do not match actual classes | Verify hierarchy matches **defining loader**, class version, control flow, and bytecode |
| Plugin A works, Plugin B fails with the same class name | Cache/lookup picked the wrong namespace or parent-first resource | Separate resolvers by loader/module/artifact; test duplicate binary names |
| `getResourceAsStream` called but class not found | Loader only supports memory definitions, remote/nested JAR/module resources | Use `ofResourceParsing(Function)` and direct byte/snapshot sources |
| `loader == null` causes `NullPointerException` | Agent calls a method on the bootstrap loader, which does not exist as an object | Handle bootstrap as a special case; use controlled JDK resources/sources |
| Transformer causes stack overflow / circularity | Resolver triggers class loading that re-enters the callback | Remove reflection in callbacks; avoid recursive dependencies and reentrant I/O |
| Cache does not see newly updated classes | `cached()` retains unknown values / stale metadata | Create resolver/cache per epoch/version and reset on changes |
| Changing `StackMapsOption` to "dodge errors" | Dropping frames improperly can make the class fail the verifier | Provide an accurate resolver and generate/verify frames as required |

## 11. Checklist for Implementing the Class-File API in a Java Agent

1. **Verify the JDK:** `java.lang.classfile` is official starting in JDK 24; if the agent must run on Java 17, choose another compatible bytecode tool, such as ASM or Byte Buddy.
2. **Identify the hierarchy source:** know which loader, module, and artifact version define the class bytes.
3. **Avoid unintended class loading:** do not use `defaultResolver()` or `ofClassLoading(...)` in sensitive transformers unless loading is acceptable.
4. **Choose resource/metadata resolution:** prefer `ofResourceParsing(...)` or `of(...)`; use callback bytes when external resources are unreliable.
5. **Attach the resolver to the context:** `ClassFile.of(ClassFile.ClassHierarchyResolverOption.of(resolver), ...)`; do not expect the default context to know about custom loaders.
6. **Compute stack maps deliberately:** use `GENERATE_STACK_MAPS` when actually needed, understand that `STACK_MAPS_WHEN_REQUIRED` can reuse compatible frames, and do not drop frames blindly.
7. **Fallbacks must not break policy:** every `orElse(...)` must have an accurate hierarchy source and must not trigger class loading when that is a constraint.
8. **Cache by namespace:** avoid mixing classes with the same name from different loaders; manage stale negative caches and thread safety.
9. **Test the output:** verify the class file and try loading/running it on the target JVM, watching for `VerifyError`, `ClassFormatError`, and `LinkageError`.
10. **Measure runtime risks:** resource lookup counts, callback latency, unintended class loads, recursion, and startup impact.

## 12. Self-Check Questions

**Question 1.** Why is `ClassHierarchyResolver.defaultResolver()` unsuitable for an agent running inside `ClassFileTransformer`?

**Answer:** The default resolver uses reflection/the system loader, which can **load unloaded classes** and look up the wrong class if it only exists in a custom loader. During transformation, that behavior can alter loading order or cause recursion.

**Question 2.** Does using `ofResourceParsing(targetLoader)` guarantee receiving the exact bytes being defined by the JVM?

**Answer:** No. Resource lookup can differ from the class definition path, especially with memory definitions, custom loaders, modules, and nested JARs. You need to verify the source or use a mapper with the exact byte snapshot.

**Question 3.** Does `ClassDesc.of("demo.Service")` load the `demo.Service` class itself?

**Answer:** No. `ClassDesc` is a symbolic descriptor. Class loading occurs only if a resolver or other code chooses to invoke the corresponding loader/reflection.

**Question 4.** Does `primary.orElse(fallback)` automatically catch `IllegalArgumentException` from `primary` and switch to `fallback`?

**Answer:** No. The fallback is queried when `primary` returns **`null`** because it does not know the class; it is not a mechanism to catch all exceptions.

**Question 5.** Why can't a shared `ClassDesc → ClassHierarchyInfo` cache be used for two plugin loaders?

**Answer:** Two loaders can define the same class name with different superclasses/interfaces. Caching by descriptor without binding to a namespace can retrieve the wrong hierarchy and produce invalid stack frames.

**Question 6.** Why must `cached()` consider lifecycle and multithreading?

**Answer:** By default, the cache is not thread-safe and also stores unknown (`null`) results; if the hierarchy changes or multiple threads look up concurrently, results can become stale or hit concurrency issues.

## 13. Official Documentation

- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): standardized API in Java 24.
- [Java SE 24 — `java.lang.classfile` package](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): parse/transform/generate, stack map computation, and resolver configuration.
- [Java SE 24 — `ClassHierarchyResolver`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html): `defaultResolver`, `ofClassLoading`, `ofResourceParsing`, `of`, `orElse`, `cached`.
- [Java SE 24 — `ClassFile.ClassHierarchyResolverOption`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.ClassHierarchyResolverOption.html): impact of the resolver on stack map generation/verification.
- [Java SE 24 — `ClassFile.StackMapsOption`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html): `GENERATE_STACK_MAPS`, `STACK_MAPS_WHEN_REQUIRED`, and `DROP_STACK_MAPS`.
- [Java SE 24 — `ClassFile` API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `ClassFile.of`, `parse`, `transformClass`, `verify`.
- [Java SE 24 — `ClassTransform`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ClassTransform.ACCEPT_ALL` and transforming class models.

**Takeaway:** In the Class-File API, **reading a hierarchy does not have to mean loading a class**. For instrumentation, choose a **resolver based on resources/metadata of the right class-loader namespace**, attach it via `ClassFile.ClassHierarchyResolverOption`, avoid `defaultResolver`/`ofClassLoading` when class loading is a risk, and test both stack maps and actual class loading.
