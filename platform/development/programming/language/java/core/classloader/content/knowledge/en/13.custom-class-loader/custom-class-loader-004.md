# Reading and Checking Bytecode from a Directory, Memory, or Custom Source in Java ClassLoader

## 1. Goal and Problem Statement

Java can load classes not only from standard JARs and the classpath, but also from a custom-configured directory, a byte array in memory, or an application-managed bytecode store. This capability enables plugin implementations, dynamic code generation, library version isolation, or custom deployment mechanisms.

The familiar extension point is `ClassLoader.findClass(String name)`. An application subclass overrides this method to **locate bytecode**, check the required inputs, and then use `defineClass(...)` to create the class's runtime definition.

However, simply “reading a byte array and calling `defineClass`” is not enough to design a safe loader. You must also pay attention to:

- **Class name (binary name):** must match the actual definition inside the class file.
- **Byte source:** a properly rooted directory, an in-memory store, or a controlled custom source.
- **Valid data:** class file format, bytecode version, structure, trust level, and size limits.
- **Delegation:** the parent loader may already have provided the class before `findClass` is called.
- **Type identity:** two loaders defining the same binary name create two distinct runtime types.
- **Errors and concurrency:** class-loading failures must be reported properly, and duplicate definitions must be avoided when multiple threads request the same class.
- **Lifecycle:** resource lookup, loader leaks, bytecode caching, and plugin reloading must be designed separately.

This lesson clearly distinguishes **reading bytecode from a custom source** from **verifying bytecode** and **defining a class in the JVM**.

## 2. Three Separate Steps: Find, Check, Define

With the name `lesson.plugin.Greeting`, a custom loader typically performs:

```text
request: loader.loadClass("lesson.plugin.Greeting")
       |
       v
ClassLoader.loadClass:
  (1) already recorded as loaded? -> return existing Class
  (2) parent has the class?       -> return parent Class
  (3) not yet present             -> findClass(binaryName)
                                         |
                               fetch bytecode from source
                                         |
                               preliminary/policy checks
                                         |
                               defineClass(name, bytes, ...)
                                         |
                               JVM checks, creates definition
                                         |
                               return runtime Class<?>
```

**API Roles:**

| API | Responsibility | Common Misconception |
| --- | --- | --- |
| `loadClass(String)` | Entry point for finding/loading a class; defaults to parent-first delegation | Does not mean the invoked loader is the defining loader |
| `findLoadedClass(String)` | Checks whether the JVM has recorded the class as loaded with this initiating loader | Not an arbitrary application-managed bytecode cache |
| `findClass(String)` | Extension point to locally find/define a class | Does not automatically read directories/JARs without an implementation |
| `defineClass(String, byte[], int, int)` | Creates a runtime definition from bytecode supplied by the loader | Not merely “parsing the header”; the JVM also applies class/linking rules |
| `resolveClass(Class<?>)` | Handles linking/resolution of an already defined class | Not synonymous with running the `static initializer` |
| `Class.forName(name, initialize, loader)` | Looks up a type and chooses whether to actively initialize it | Can be affected by parent delegation just like `loadClass` |

When you only need to change the **bytecode source**, you should normally override `findClass` and keep the default `loadClass` algorithm. If you override `loadClass` to apply child-first delegation, you must manually preserve synchronization rules, already-loaded classes, class loader compatibility, and mandatory namespaces.

## 3. Binary Names and Directory Mapping

Suppose the bytecode is compiled from:

```java
package lesson.plugin;

public final class Greeting {
    public String message() {
        return "hello";
    }
}
```

This is the source code of an example class, not a standalone program with a `main` method. Its binary name is `lesson.plugin.Greeting`. With a **classpath root** at the `plugins/classes` directory, the class file is typically located at:

```text
plugins/classes/lesson/plugin/Greeting.class
```

Therefore, the familiar mapping is:

```java
Path classFile = root.resolve(
        binaryName.replace('.', '/') + ".class");
```

This is a snippet, assuming `root` and `binaryName` exist.

**Do not confuse:**

- `lesson.plugin.Greeting` is the **binary name**, whereas `lesson/plugin/Greeting.class` is a relative path inside a root.
- Nested classes have a `$` in their binary name, such as `Outer$Nested`; do not change it to `Outer.Nested` when passing it to `loadClass`.
- A JAR uses `/` in entry names, regardless of the operating system's path separator.
- The parent may already have defined `lesson.plugin.Greeting`; the existence of a separate file does not guarantee that the child's `findClass` will run.

### A Directory Is a Data Source, Not a Security Layer

If the class name can originate from outside, you should not append it directly to a path without validation. You need to restrict the namespace, normalize the path, verify the root, handle symbolic links, and enforce appropriate access permissions. A syntactically valid path can still lead to content controlled by an untrusted party.

If the application only loads classes in `lesson.plugin.*`, a package allowlist policy helps avoid accidentally reading bytecode from another API area. However, a name allowlist does **not** prove the bytecode is safe.

## 4. Bytecode from Memory: No JAR File Needed at Definition Time

Another source is a `Map<String, byte[]>` containing class file bytes:

```text
"lesson.plugin.Greeting" -> [0xCA, 0xFE, 0xBA, 0xBE, ...]
"lesson.plugin.Helper"   -> [0xCA, 0xFE, 0xBA, 0xBE, ...]
```

This illustrates the data structure. A `MemoryClassLoader` can retrieve a `byte[]` by binary name and call `defineClass`; the JVM **does not require** a class to come from a file on disk.

Notable implementation choices:

- **Copying the byte array:** if external code still holds the array and modifies it while the loader is using it, results can be unpredictable. Copy the array when accepting it into the loader and prevent external callers from modifying the copy in use.
- **Caching definitions without redefining:** `findLoadedClass` and the default `loadClass` algorithm help reuse an already-recorded `Class<?>`.
- **Complete dependency map:** `Greeting`'s bytecode may require `Helper` or a parent interface; the loader's source must have a way to locate them or rely on the parent.
- **Memory limits:** storing many copies of class bytes, plus runtime metadata, can increase memory usage; once a class is defined, you do not necessarily need to keep every original `byte[]` forever.
- **Class identity:** identical bytecode loaded by two different defining loaders creates two distinct runtime types.

Bytecode from a network or database is not inherently more “trustworthy” than bytecode from memory. For custom sources, you must also design authentication, versioning, caching, timeouts, checksum/signature verification from a trusted source, and rollback when the source is unavailable.

## 5. Levels of “Bytecode Checking” to Distinguish

There are three layers that must not be conflated.

### 5.1. Checks Before Calling defineClass

The application can check:

1. **Allowed name/namespace:** for example, only accept `lesson.plugin.*`; never attempt to define `java.*`.
2. **Source:** a configured root, an internal bytecode store, or an allowlisted artifact ID.
3. **Size:** do not unconditionally read oversized files; consider performing a bounded stream read rather than relying solely on file size at a single point in time.
4. **Class-file magic:** the first four bytes of a class file are `CA FE BA BE`. This is **only a preliminary check** and does not prove the class is valid.
5. **Class file version:** the major version must be supported by the runtime; do not rely solely on the `.class` extension.
6. **Integrity/authenticity:** check the SHA-256 against a digest published via a trusted channel, or perform appropriate artifact signature verification. There is no security value if the “expected hash” is fetched from the same untrusted source alongside the bytecode.
7. **Additional policy:** package sealing, signers/certificates, protection domains, and how plugins are allowed to connect to host APIs.

**External** name checks do not replace the JVM comparing against the actual binary name inside the class file.

### 5.2. JVM Format Checks and Verification

When `defineClass(name, bytes, offset, length)` is called, the JVM applies the checks required for class definition. Depending on the error, timing, and JVM rules, you may encounter:

| Error | Typical Meaning |
| --- | --- |
| `ClassFormatError` | Invalid class file structure |
| `UnsupportedClassVersionError` | The class file uses a bytecode version not supported by the current JVM |
| `NoClassDefFoundError` due to wrong name | The requested name does not match the name defined inside the class file |
| `VerifyError` | The bytecode does not satisfy verifier constraints |
| `SecurityException` | Violation of restrictions on definition, namespace, package, or source/certificate |
| `LinkageError` due to duplicate definition | Attempting to redefine the same binary name within a single defining loader |
| `NoClassDefFoundError` due to missing dependency | A superclass, superinterface, or required dependency cannot be loaded when the JVM needs it |
| `ExceptionInInitializerError` | An **initialization** error while executing static code; not synonymous with `defineClass` failing |

A class can be **defined successfully** and only later encounter a dependent class resolution error or an initialization error upon active use. Do not jump to the conclusion that “defineClass completing = the entire bytecode graph has been verified, linked, and initialized”.

### 5.3. Do Not Treat the JVM Verifier as a Sandbox for Untrusted Code

The JVM bytecode verifier guarantees many type-safety and VM invariants, but it does **not** prevent a valid class from calling privileged APIs of the process. A custom loader by itself does not isolate networking, the filesystem, process execution, or native code. For untrusted plugins, a stronger isolation model is required (for example, a managed process or container with reduced privileges), rather than relying on `ClassLoader` as a security boundary.

## 6. Runnable Java 17 Example: Same Bytecode from a Directory and an In-Memory Map

This experiment generates and compiles a `lesson.plugin.Greeting` class using the JDK's `JavaCompiler`, and then loads the **same bytecode** in two ways:

1. `DirectoryLoader` reads the `.class` file from the root directory.
2. `MemoryLoader` reads the `byte[]` from a `Map`.
3. Both loaders have the platform loader as their parent, so the parent does not load the plugin class from the application classpath.
4. The JVM creates two separate runtime definitions despite the same binary name.
5. The program checks lookup of an already-recorded class, tests a bootstrap class, and tests the case where a class does not exist.

**Save the entire program** to `BytecodeSourceDemo.java`:

```java
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class BytecodeSourceDemo {
    private static final String TYPE = "lesson.plugin.Greeting";
    private static final int MAX_BYTES = 1_000_000;

    private static void checkBytes(String name, byte[] bytes)
            throws ClassNotFoundException {
        if (!TYPE.equals(name) || bytes == null
                || bytes.length < 8 || bytes.length > MAX_BYTES) {
            throw new ClassNotFoundException(name);
        }
        if ((bytes[0] & 0xFF) != 0xCA
                || (bytes[1] & 0xFF) != 0xFE
                || (bytes[2] & 0xFF) != 0xBA
                || (bytes[3] & 0xFF) != 0xBE) {
            throw new ClassNotFoundException(
                    "Not a class-file header: " + name);
        }
    }

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TYPE.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            Path file = root.resolve(
                    name.replace('.', '/') + ".class").normalize();
            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            byte[] bytes;
            try {
                if (!Files.isRegularFile(file)
                        || Files.size(file) > MAX_BYTES) {
                    throw new ClassNotFoundException(name);
                }
                bytes = Files.readAllBytes(file);
            } catch (IOException exception) {
                throw new ClassNotFoundException(name, exception);
            }

            checkBytes(name, bytes);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> source;

        MemoryLoader(Map<String, byte[]> source, ClassLoader parent) {
            super(parent);
            this.source = new HashMap<>();
            source.forEach((name, bytes) ->
                    this.source.put(name, bytes.clone()));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] stored = source.get(name);
            if (stored == null) {
                throw new ClassNotFoundException(name);
            }
            byte[] bytes = stored.clone();
            checkBytes(name, bytes);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static String invokeGreeting(Class<?> type)
            throws Exception {
        Object instance = type.getDeclaredConstructor().newInstance();
        Method method = type.getMethod("message");
        return (String) method.invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        Path temp = Files.createTempDirectory("bytecode-source-");
        Path source = temp.resolve(
                "src/lesson/plugin/Greeting.java");
        Path classes = temp.resolve("classes");
        Path bytecode = classes.resolve(
                "lesson/plugin/Greeting.class");

        try {
            Files.createDirectories(source.getParent());
            Files.createDirectories(classes);
            Files.writeString(source, """
                    package lesson.plugin;
                    public final class Greeting {
                        public String message() {
                            return "hello";
                        }
                    }
                    """);

            int exit = compiler.run(null, null, null,
                    "--release", "17",
                    "-d", classes.toString(), source.toString());
            if (exit != 0) {
                throw new IllegalStateException("javac failed");
            }

            byte[] originalBytes = Files.readAllBytes(bytecode);
            ClassLoader parent = ClassLoader.getPlatformClassLoader();

            DirectoryLoader directory =
                    new DirectoryLoader(classes, parent);
            MemoryLoader memory = new MemoryLoader(
                    Map.of(TYPE, originalBytes), parent);

            Class<?> fromDirectory = directory.loadClass(TYPE);
            Class<?> fromMemory = memory.loadClass(TYPE);

            System.out.println("directory="
                    + invokeGreeting(fromDirectory));
            System.out.println("memory="
                    + invokeGreeting(fromMemory));
            System.out.println("sameName="
                    + fromDirectory.getName().equals(
                            fromMemory.getName()));
            System.out.println("sameClass="
                    + (fromDirectory == fromMemory));
            System.out.println("directoryDefining="
                    + (fromDirectory.getClassLoader() == directory));
            System.out.println("memoryDefining="
                    + (fromMemory.getClassLoader() == memory));
            System.out.println("directoryCached="
                    + (fromDirectory == directory.loadClass(TYPE)));
            System.out.println("stringBootstrap="
                    + (memory.loadClass("java.lang.String")
                            .getClassLoader() == null));

            try {
                memory.loadClass("lesson.plugin.Missing");
            } catch (ClassNotFoundException exception) {
                System.out.println("missing=ClassNotFoundException");
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(bytecode);
            Files.deleteIfExists(source.getParent());
            Files.deleteIfExists(
                    source.getParent().getParent());
            Files.deleteIfExists(temp.resolve("src"));
            Files.deleteIfExists(bytecode.getParent());
            Files.deleteIfExists(
                    bytecode.getParent().getParent());
            Files.deleteIfExists(classes);
            Files.deleteIfExists(temp);
        }
    }
}
```

Compile and run with **JDK 17 or later** (not just a runtime image without a compiler):

```bash
javac BytecodeSourceDemo.java
java BytecodeSourceDemo
```

**Expected stdout when the compiler and filesystem work normally:**

```text
directory=hello
memory=hello
sameName=true
sameClass=false
directoryDefining=true
memoryDefining=true
directoryCached=true
stringBootstrap=true
missing=ClassNotFoundException
```

### Explaining the Results

- Both loaders find the **same bytecode** produced by `javac`, so calling `message()` returns `hello` in both cases.
- `sameName=true` because `Class.getName()` for both is `lesson.plugin.Greeting`.
- `sameClass=false` because the two loaders are **two different defining loaders**; the JVM does not treat them as a single runtime class.
- `directoryDefining=true` and `memoryDefining=true` prove that the class was defined by the loader responsible for finding the bytecode, not the platform parent.
- `directoryCached=true`: for the same loader, the second request receives the already-loaded definition without calling `defineClass` again.
- `stringBootstrap=true`: `java.lang.String` is still defined by the bootstrap loader via delegation.
- When `MemoryLoader` has no byte array for `lesson.plugin.Missing`, `findClass` throws `ClassNotFoundException`. This is a sound contract when the loader's source does not contain the requested class.

### Intentional Limitations of the Experiment

- Only **one binary name**, `lesson.plugin.Greeting`, is allowed: this helps avoid accidentally reading/defining classes outside the scope of the lesson. A real-world loader must have a broader policy that is valid for dependent classes.
- Checking `CA FE BA BE` is **preliminary**; the JVM is the component that checks the class file against the specification. This program does not claim to verify artifact signatures or sandbox code.
- Calling `Files.size` before `Files.readAllBytes` is a convenient size-limiting step; if the file can be modified concurrently, there is a *time-of-check/time-of-use* risk. Untrusted sources require bounded stream reads and stronger filesystem policies.
- Paths are constructed only from a fixed name, so the example does not fully demonstrate defenses against path traversal, symlink escape, or arbitrary namespaces.
- The example uses the JDK's JavaCompiler to avoid needing an external JAR; when loading bytecode from a database or HTTP, you only replace the **byte source** and preserve the corresponding validation/definition rules.

## 7. Invalid Data Checks: What to Do with Corrupted Bytecode?

Distinguish between two error categories:

**Category 1 — The loader cannot find a valid source:** the name is outside the allowed namespace, the file does not exist, it cannot be read, or the byte array is missing from the store. `findClass` should throw `ClassNotFoundException`, optionally with `IOException` as the cause.

**Category 2 — Bytes were retrieved, but they are not a valid class file:** `defineClass`/the JVM may throw `ClassFormatError`, `UnsupportedClassVersionError`, `VerifyError`, or an appropriate `LinkageError`. You should not catch every `Throwable` and turn it into `ClassNotFoundException`, because doing so hides the underlying technical cause.

Example of an array that is not a class file:

```java
byte[] invalid = new byte[]{1, 2, 3, 4};
```

This is an illustrative snippet. If you pass this array into the loader above under a valid key, the `checkBytes` check rejects it upfront because its length is less than 8. If bytes pass the magic check yet still contain invalid class file contents, the JVM may reject them at `defineClass` or during a subsequent linking phase. **Magic bytes are not enough to affirm that bytecode is safe or structurally valid.**

### When the Requested Name Differs from the Name in the Class File

Suppose you request `lesson.plugin.Other` but supply bytes that actually define `lesson.plugin.Greeting`. When calling `defineClass("lesson.plugin.Other", bytes, ...)`, the JVM must enforce the name constraint; the result is not a silent “class rename” to Other. In typical configurations, it may throw `NoClassDefFoundError` with wrong-name details.

**Do not try to fix the binary name by editing a few bytes in the class file.** A class file contains the constant pool, descriptors, signatures, bootstrap methods, and many other interdependent pieces of metadata; if you genuinely need to rename a class, you must use an appropriate bytecode transformation tool and re-verify consistency.

## 8. Loading from Custom Sources: Databases, Artifact Repositories, HTTP, or Dynamically Generated Code

You can abstract the bytecode source so that `findClass` does not depend on the filesystem:

```java
@FunctionalInterface
interface BytecodeRepository {
    byte[] read(String binaryName) throws java.io.IOException;
}
```

This is a snippet of a data source interface, not a standalone runnable application. Depending on the implementation, the `read` method may obtain a byte array from:

- A `Map<String,byte[]>` generated by a compiler or at runtime.
- Object storage or a database with an exact mapping from binary name to blob bytes/version.
- An artifact registry with checksum, signature, and publisher metadata.
- A dynamic compiler using `javax.tools.JavaCompiler` and `JavaFileManager` to capture bytes directly in memory.
- An internal cache layer containing verified/approved plugin classes.

**Avoid downloading bytecode directly from an unauthenticated URL and executing it inside the application JVM.** For low-trust sources, prefer signed artifact structures from a trusted build pipeline, verify the origin, restrict access, and consider isolating execution in a separate process. SHA-256 only proves that the data matches a **previously trusted** digest; it does not indicate that “this code is not malicious”.

### Caching Bytes Is Not “Reloading a Class” in the Same Loader

The backing repository may update `Greeting.class` across versions. However, a loader that has already defined `lesson.plugin.Greeting` cannot arbitrarily replace that definition by reading the new version's bytes and calling `defineClass` again with the same name. Repeated loads via the default `loadClass` usually return the already-recorded class.

If hot reloading is required, you typically must **create a new loader** for the new version, switch the application's routing, and release references to the old loader. State migration and objects shared across loaders must be handled separately; two versions of `Greeting` may not be castable to one another.

## 9. Valid Bytecode Still Needs Dependencies and Shared APIs

A class that has just been successfully defined with `defineClass` may still need superclasses, interfaces, or methods from **unresolved** libraries. The loader must find those dependencies, directly or via its parent. For example, an implementation in `lesson.plugin` declares `implements lesson.api.Plugin`: the host and plugin can only exchange objects safely under the `Plugin` type when both use the **same `Class<?>` definition** of the shared interface.

In plugin systems, shared APIs/SPIs and DTOs are typically placed in the parent loader, while implementation classes live in the plugin loader. Libraries that require version isolation must have their own lookup scope; default parent-first delegation will select the parent's version if the parent finds the same binary name. The JVM still enforces loading constraints when method signatures cross loader boundaries.

**Distinguish between two checks:** the integrity/authenticity of the **source bytes** before `defineClass`, and the availability/consistency of **related types** during linking. A valid checksum does not prove that the dependency graph is valid or that the plugin can be cast to a host interface.

## 10. Multithreaded Concurrency and Duplicate Class Definitions

When multiple threads simultaneously request `loader.loadClass("lesson.plugin.Greeting")`, the default `ClassLoader.loadClass` mechanism synchronizes on the appropriate loading lock and checks `findLoadedClass` before choosing `findClass`. Therefore, if you only override `findClass`, you normally benefit from the core's duplicate-loading prevention rules.

If you override `loadClass` yourself, you must control:

1. A clear parent/child policy.
2. Checking whether the class is already recorded as loaded before defining a new one.
3. Class-loading locking compatible with `getClassLoadingLock(name)` and parallel-capable status if applicable.
4. Avoiding calling `loadClass(name)` from `findClass(name)` for the same name, which causes recursion.
5. Not holding long-lived application locks across network fetches or calling back into other loaders in ways that create wait cycles.
6. A cache + timeout policy so a remote source does not make all threads wait indefinitely.

The same defining loader must not define the same binary name twice as two independent classes. If a conflict occurs, the JVM may throw `LinkageError`. **Never catch this error and return an arbitrary Class object with the wrong name or loader** just to “get past” the load call.

### Loading Differs from Initialization

`defineClass` and `loadClass` are not APIs for “executing code inside a static block”. The JVM has separate loading, linking, and initialization phases. Creating an instance or calling a static method may trigger initialization later; an application-written loader should not use logging inside `static {}` to infer every bytecode read.

## 11. Common Errors and Diagnostic Guidance

| Symptom | Questions to Check |
| --- | --- |
| `ClassNotFoundException` | Was the requested loader given the right binary name/namespace? Are the root, repository key, read permissions, and source correct? |
| `NoClassDefFoundError` | Is a superclass/interface or other dependency missing, was there a wrong name, or did the class previously fail initialization? |
| `ClassFormatError` | Are the bytes a structurally valid class file? Did the source return HTML/JSON instead of `.class`? |
| `UnsupportedClassVersionError` | Is the Java runtime new enough to read the class file's major version? |
| `VerifyError` | Does the bytecode violate verifier constraints? Was it transformed or generated invalidly? |
| `LinkageError` duplicate definition | Did two threads or code paths call `defineClass` again with the same name in the same loader? |
| `ClassCastException` between classes of the same name | Did two defining loaders create two different runtime types? |
| `SecurityException` | Was there an attempt to define `java.*` or a violation of package certificate/protection constraints? |
| `NoSuchMethodError` | Does the runtime dependency differ from the API that the plugin bytecode was compiled against? |
| `ExceptionInInitializerError` | Did static initialization code fail after active use, rather than during byte reading? |
| Cannot find `.properties` resource | Does the custom loader properly override/configure `findResource(s)` or package/module resource lookup? |
| Old plugin still occupies memory | Is the old ClassLoader being retained by a static registry, thread, TCCL, callback, or cache? |

**Note:** `ClassNotFoundException` (checked) and `NoClassDefFoundError` (Error) must not be swapped arbitrarily. When `findClass` cannot find the bytes, use `ClassNotFoundException`; when the JVM detects that a dependent class is unavailable, the runtime message may be `NoClassDefFoundError`. You must inspect the full cause.

### Useful Tools

For accessible `.class` files or JARs:

```bash
javap -verbose -classpath plugins/classes lesson.plugin.Greeting
jar tf plugins/plugin.jar
java -Xlog:class+load=info -cp app/classes app.Main
```

These are **illustrative commands**, depending on the project's file layout and runtime classes. `javap` shows constant pool details, major version, and class structure; `jar tf` lists JAR entries; class-load logs help determine which source various classes are loaded from. For an in-memory loader, `CodeSource` may not appear as a file/JAR URL; that does not mean the class definition is wrong.

To determine the defining loader of a loaded class:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("definingLoader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

This is a helper method that must be placed inside an application class and invoked; it is not a standalone program with `main`. `getClassLoader() == null` indicates that the class was defined by the bootstrap loader.

## 12. Resource Lookup and Limitations When Loading from Memory/Database

A loader that only overrides `findClass` can load `Greeting.class` from a database, yet:

```java
loader.getResource("lesson/plugin/config.properties");
```

may return `null`. This is not contradictory, because class loading and resource lookup are two separate API paths.

If the repository also stores resources, you should consider `findResource` and `findResources`, or provide a separate abstraction for plugins. In particular, `getResource` usually prioritizes the parent by default, while `getResources` can return multiple URLs. Returning a URL whose stream cannot be opened will cause consuming APIs to fail even though the lookup appeared to succeed.

If a class resides in a named module, `ClassLoader.getResource` and `Module.getResourceAsStream` are also subject to module visibility and package openness rules. Do not assume that an in-memory byte source turns a class into a named module without the corresponding module configuration.

## 13. Misconceptions to Avoid

**“Reading the four bytes CA FE BA BE means the class is valid.”** False; that is only the magic header. The JVM verifier, class format rules, and other constraints evaluate it much further.

**“Having a byte[] means the class automatically exists.”** False; you need `defineClass` or an appropriate class-creation mechanism and proper name resolution.

**“If `defineClass` succeeds, the bytecode is safe to run.”** False; valid bytecode can still execute any behavior permitted to the process, including accessing data and the network.

**“Two loaders loading the same bytes return the same Class object.”** False; different defining loaders create two separate runtime types.

**“If the bytecode map changes, the old loader automatically replaces the class.”** False; an already-defined binary name is not automatically replaced within the same defining loader.

**“When a class is not found, just return null from findClass.”** False; `findClass` must throw `ClassNotFoundException` when no matching class exists, per the API contract.

**“If the class already exists in the parent, findClass must have been called.”** False; parent-first `loadClass` may return it from the parent before searching locally.

**“Filtering out ../ is enough to prevent all path traversal.”** False; you must consider symlinks, canonical/real paths, filesystem races, and access permissions if names/paths are untrusted.

**“A custom ClassLoader is a security sandbox.”** False; proper isolation/process policies are required when untrusted code must be executed.

## 14. Self-Check Exercises

**Question 1.** `DirectoryLoader` is called with `lesson.plugin.Greeting`. Which file must the loader map this name to if the root is `plugins/classes`?

**Answer:** `plugins/classes/lesson/plugin/Greeting.class`, while also verifying that the path lies within the permitted root.

**Question 2.** A byte array starts with `CA FE BA BE`. Is that enough to confirm the class is valid and safe?

**Answer:** No. The magic number is only a preliminary check; version, structure, verification, linkage, trusted source, and execution permissions also apply.

**Question 3.** Two independent loaders receive the same bytes with the same binary name. Can an instance from loader A be cast to the class defined by loader B?

**Answer:** Not simply by sharing the same name/bytes. Runtime identity depends on the defining loader, so the two classes are distinct.

**Question 4.** Once `Greeting` has been defined in a loader, the repository is updated with new bytes. Does calling `loadClass` with the same name reload it?

**Answer:** No. The loader reuses the already-loaded class; a new defining loader is needed for an independent definition.

**Question 5.** Bytecode is downloaded over HTTP without a signature, though its magic header is valid. Should it be run in the main JVM?

**Answer:** It cannot be concluded to be safe. You need a trusted source, artifact verification via a trusted channel, restricted privileges, and potentially process isolation.

**Question 6.** `findClass` obtains the bytecode, yet the class later throws `NoSuchMethodError` when calling a library. Why?

**Answer:** Defining the class's bytecode does not guarantee that runtime APIs differing from the compile-time ABI version contain the referenced method.

**Question 7.** Two threads simultaneously request the same class name in the same loader. Why is overriding only `findClass` usually safer than overriding `loadClass` as well?

**Answer:** The default `loadClass` algorithm already coordinates class-loading locks, parent delegation, and `findLoadedClass` to prevent duplicate definitions.

## 15. Production Loader Checklist

- [ ] Identify permitted namespaces/packages and which data sources are trusted.
- [ ] Map binary names to paths/keys safely; handle symlinks, path traversal, and read permissions.
- [ ] Limit read size and duration; control memory usage when sources return large `byte[]` arrays.
- [ ] Check integrity/authenticity using an expected digest or signature from a trusted source.
- [ ] Keep I/O failures in `ClassNotFoundException` with a cause, without masking class format/linkage errors.
- [ ] Ensure superclasses/superinterfaces, APIs/SPIs, and dependencies are provided by the right loader.
- [ ] Leverage default `loadClass` if you only need to change how bytecode is located.
- [ ] Handle concurrency and avoid duplicate `defineClass` calls for the same binary name.
- [ ] Distinguish caching bytes from the lifecycle of a runtime `Class`.
- [ ] Design resource lookup and cleanup for plugins/redeployment.
- [ ] Do not treat a custom ClassLoader as a sandbox for untrusted code.
- [ ] Test missing files, wrong names, corrupted bytes, wrong JDK versions, two different loaders, and dependency conflicts.

## 16. Conclusion and Official Documentation

A custom `ClassLoader` can read bytecode from **a directory, a memory map, or a custom source**. However, proper design requires separating **locating bytecode** (`findClass`) from **defining the class** (`defineClass`), checking the name/source/size/integrity before handing bytes to the JVM, and letting the JVM perform format checks and linking constraints. Afterward, delegation, identity, dependencies, errors, and loader lifecycle must be managed deliberately.

Official references:

- Java SE 17 `ClassLoader` API, especially `findClass`, `defineClass`, `loadClass`, and `findLoadedClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JVMS 17 §4, *The class File Format*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS 17 §5, *Loading, Linking, and Initializing*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java SE 17 `JavaCompiler` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
