# Replacing Internal APIs with Supported Public APIs in Java 17

## 1. Why Replace Internal APIs?

Some older Java libraries or applications directly call classes residing in JDK internal packages, such as names starting with `sun.`, `com.sun.`, or `jdk.internal.` packages. These classes may have been accessible in an earlier JDK version, yet **not all of them are public APIs that Java SE commits to supporting**. They may change, become more strongly encapsulated, or be removed in JDK upgrades.

Java 9 introduced the module system into the platform (Project Jigsaw). Java 17 continues strongly encapsulating JDK internal components under JEP 403. Consequently, an application that previously ran by relying on deep access into the JDK may encounter compilation or runtime errors such as:

- `package ... is not visible`.
- `module ... does not export ...`.
- `InaccessibleObjectException` when reflection tries to access an unopened member.
- `NoSuchMethodError` or `ClassNotFoundException` if an internal API has changed or been removed.

The sustainable approach is **identifying the functionality the code needs and migrating to a public API with a documented contract**. Do not merely hunt for another internal package to replace the old one.

After this lesson, learners should be able to:

1. Distinguish Java SE public APIs from JDK internal APIs.
2. Understand the impact of the module system and strong encapsulation in Java 17.
3. Inventory internal dependencies using JDK tools.
4. Select replacement APIs by function, such as Base64, Cleaner, VarHandle, LockSupport, or ImageIO.
5. Recognize cases with no drop-in replacement that require design changes.
6. Distinguish `exports`, `opens`, `--add-exports`, and `--add-opens`.
7. Compile, run, and test applications on Java 17 without relying on internal access permissions.

## 2. How Do Public APIs and Internal APIs Differ?

### 2.1. Documented public APIs

A public API is the interface published and documented by the vendor for applications to use. For the JDK, consult the Java SE API Specification and Javadoc for the exact version.

Examples of public APIs:

- `java.util.Base64` for Base64 encoding and decoding.
- `java.lang.ref.Cleaner` for registering resource cleanup actions as a fallback safety net.
- `java.lang.invoke.VarHandle` for accessing variables and arrays with explicit memory access modes.
- `java.util.concurrent.locks.LockSupport` for parking/unparking threads.
- `javax.imageio.ImageIO` for reading and writing images.
- `java.net.http.HttpClient` for sending HTTP requests.

These APIs have explicit contracts in Java SE documentation or the corresponding module documentation. Applications can rely on those contracts across JDK upgrades within published compatibility guarantees.

### 2.2. Internal APIs are not compatibility guarantees

Package names such as `sun.misc`, `sun.reflect`, or `jdk.internal.*` are typically signals to investigate closely. However, **do not classify solely by package name prefix**: some `com.sun.*` packages are documented and are public APIs of JDK modules, such as the HTTP server API in `jdk.httpserver`.

Verify each class and package against official Javadoc, module descriptors, and `jdeps`. Starting with `com.sun` does not automatically mean internal, nor does a class being currently accessible mean it is supported long term.

### 2.3. Accessible does not mean supported

In Java 17, a few critical internal APIs are still exposed via module `jdk.unsupported` to support legacy applications. For example, `sun.misc.Unsafe` may still be present on JDK 17. This **does not turn it into a stable Java SE API** and does not guarantee internal details will remain unchanged.

Principles for selecting APIs:

1. Prefer APIs with public Javadoc belonging to Java SE or documented JDK modules.
2. Verify the API is available in the target Java version.
3. Clarify the contract regarding exceptions, thread safety, mutability, and resource lifecycle.
4. Do not treat adding JVM flags to access internal packages as completing migration.

## 3. Strong Encapsulation in Java 17

### 3.1. The module system controls accessible packages

A module can declare which packages are exported to other modules:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Other modules can use public types in exported packages if they read the containing module.

Key concepts:

| Concept | Meaning |
|---|---|
| Readability | Whether a module has permission to read another module, usually declared via `requires` |
| `exports` | Exposes public types of a package for normal use by other modules |
| `opens` | Allows deep reflection into a package at runtime |
| Encapsulation | Restricts internal implementation parts that are not exposed |
| Unnamed module | Home of the traditional classpath; JARs on the classpath typically belong to the unnamed module |

Example module using the HTTP client:

~~~java
module com.example.client {
    requires java.net.http;
}
~~~

`java.base` is implicitly required by every Java module, so `requires java.base` does not need to be written.

### 3.2. JEP 403 and Java 17

JEP 403 completes strong encapsulation of JDK internal components. In Java 17:

- Internal packages not exported/opened by default are no longer accessible as before.
- Deep reflection into private JDK members may be blocked.
- The `--illegal-access` flag is no longer a way to restore broad access as in earlier transitional JDK releases.
- A few critical internal APIs remain exposed via `jdk.unsupported` for compatibility, yet remain internal APIs.

Therefore, when upgrading to Java 17, find and eliminate dependencies on JDK internals instead of relying on relaxed access modes.

### 3.3. Compile-time and runtime errors

Two forms of errors have different causes:

**Compilation error:** code imports a package not exported by its containing module to the current module. The compiler may report that the package is not visible.

**Runtime error:** code uses reflection to unlock a member not opened by the target module. Operations like `setAccessible(true)` can throw `InaccessibleObjectException`.

Do not fix both error types with the same JVM flag. Determine whether readability, package export, or package open for deep reflection is missing.

## 4. Inventorying Internal Dependencies Before Fixing

### 4.1. Using jdeps

`jdeps` is a dependency analysis tool for classes, JARs, and modules. The `--jdk-internals` option helps detect static references to JDK internal APIs.

Example:

~~~bash
jdeps --jdk-internals application.jar
~~~

To analyze dependencies deeply:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

For multi-release JARs, you can specify the version to analyze:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

Read the output to identify:

- Which classes depend on internal APIs.
- Which internal packages/modules are used.
- Replacement hints known to the tool (if any).
- Whether the dependency comes from application code or a third-party library.

### 4.2. jdeps does not detect every dynamic access

`jdeps` analyzes bytecode and statically recognizable dependencies. It may not fully detect:

- Class or package names concatenated as strings and passed to `Class.forName`.
- Reflection driven by runtime metadata.
- Runtime-generated code.
- Access arising from plugins or dependencies loaded only in another deployment configuration.

Hence, `jdeps` output is a starting point. Combine source code search, dependency graph inspection, integration tests, and real plugin flow testing.

### 4.3. Distinguishing jdeps from jdeprscan

`jdeprscan` finds APIs marked deprecated in the JDK. Deprecated APIs and internal APIs are two distinct groups:

- A public API may be deprecated yet still be a public API.
- An internal API may not be marked deprecated yet still lack support commitments.

Example:

~~~bash
jdeprscan --release 17 application.jar
~~~

Both tools can be run for a fuller picture, but do not substitute one tool's output for the other's.

## 5. Replacement Map by Functionality

There is no single public API that replaces all internal APIs. Build a mapping by the **actual functionality needed**:

| Legacy approach or need | Public replacement direction | Notes |
|---|---|---|
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` | Standard API since Java 8 |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Cleaner is a fallback; still prefer explicit closing |
| CAS/atomic field access via `sun.misc.Unsafe` | `VarHandle` or `AtomicInteger`/`AtomicLong`/`AtomicReference` | Choose by data type and memory semantics |
| Atomic access to array elements | `MethodHandles.arrayElementVarHandle` or appropriate atomic classes | No manual offset/index scale calculation |
| Thread park/unpark via Unsafe | `LockSupport.park`/`unpark` | Understand permits and interruption |
| Defining a class in caller's package | `MethodHandles.Lookup.defineClass` | Bounded by Lookup and package permissions |
| Reading/writing images via legacy internal codecs | `javax.imageio.ImageIO` | Verify available formats and providers |
| Accessing private JDK members | Use corresponding public API or redesign | No way to turn private APIs into stable contracts |
| Arbitrary native memory allocation via Unsafe | No stable drop-in replacement in Java 17; consider DirectByteBuffer/JNI per requirements | FFM in Java 17 is still incubator |
| Instantiating objects bypassing constructors | Factory/constructor; appropriate serialization API if fitting use case | No general replacement for allocateInstance |

This table is a guide; before replacing, read the target API's Javadoc and verify semantic differences.

## 6. Replacing Internal Base64 with java.util.Base64

Legacy Base64 classes in `sun.misc` are a classic example to replace with the standard `java.util.Base64` API.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Hello Java".getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);

String restored = new String(decoded, StandardCharsets.UTF_8);
System.out.println(restored); // Hello Java
~~~

Common variants:

- `Base64.getEncoder()` / `getDecoder()`: standard Basic Base64 format.
- `Base64.getUrlEncoder()` / `getUrlDecoder()`: URL- and filename-safe alphabet.
- `Base64.getMimeEncoder()` / `getMimeDecoder()`: MIME format with line separator rules.

Do not swap a legacy decoder for a new one while ignoring data variants. Identify whether legacy data is Basic, URL-safe, or MIME Base64; check padding and line wrapping according to the interchange format.

## 7. Replacing sun.misc.Cleaner with java.lang.ref.Cleaner

`java.lang.ref.Cleaner` is a public API for registering cleanup actions when an object becomes phantom reachable. It has been available since Java 9 and is included in Java 17.

However, Cleaner **does not replace deterministic resource closing**. If a resource can be closed explicitly, such as a file, socket, or channel, implement `AutoCloseable` and encourage callers to use try-with-resources. Cleaner should only act as a safety net when callers forget to close.

### 7.1. Safe Cleaner structure example

~~~java
import java.io.IOException;
import java.lang.ref.Cleaner;
import java.nio.channels.FileChannel;

public final class ManagedResource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    // State must not hold a strong reference to ManagedResource.
    private static final class State implements Runnable {
        private final FileChannel channel;

        State(FileChannel channel) {
            this.channel = channel;
        }

        @Override
        public void run() {
            try {
                channel.close();
            } catch (IOException ex) {
                // Log according to the application's policy.
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public ManagedResource(FileChannel channel) {
        this.state = new State(channel);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
~~~

Key points:

- The cleanup action must not hold a strong reference to the registered object, otherwise the object may never become unreachable.
- `cleanable.clean()` can be invoked explicitly and the cleanup action runs at most once.
- Cleaner runs asynchronously when the object becomes unreachable; exact execution timing is not guaranteed.
- Do not use Cleaner as a substitute for `close()` in normal business flows.

## 8. Replacing Unsafe Variable Operations with VarHandle

`VarHandle` is a public API in `java.lang.invoke` since Java 9. It allows accessing instance fields, static fields, and array elements with various access modes, including volatile, acquire/release, and atomic read-modify-write.

### 8.1. Atomic update of a field

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    Counter.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }

    public boolean setIfZero() {
        return VALUE.compareAndSet(this, 0, 1);
    }
}
~~~

`findVarHandle` locates a field by name and type. `getAndAdd` and `compareAndSet` are atomic access modes; the field must be accessed with the matching receiver and value type.

Not every `Unsafe` operation translates directly into an identical `VarHandle` call. Choose the memory access mode based on the algorithm's synchronization requirements.

### 8.2. Atomic access to array elements

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AtomicArrayExample {
    private static final VarHandle ELEMENT =
            MethodHandles.arrayElementVarHandle(int[].class);

    public static void main(String[] args) {
        int[] values = {10, 20, 30};

        boolean changed = ELEMENT.compareAndSet(
                values, 1, 20, 25);

        System.out.println(changed);    // true
        System.out.println(values[1]);  // 25
    }
}
~~~

Instead of manually computing base offsets and index scales with Unsafe, use a VarHandle for the array type being accessed. The API handles access according to the Java contract.

### 8.3. Choosing Atomic classes for simpler needs

If you only need a counter or atomic reference, `AtomicInteger`, `AtomicLong`, and `AtomicReference` are often easier to read than VarHandle:

~~~java
AtomicInteger counter = new AtomicInteger();
int next = counter.incrementAndGet();
~~~

VarHandle is useful when you need direct access to fields/arrays of a data structure without wrapping every value in an atomic object.

### 8.4. Memory fences

Some Unsafe fence operations can be replaced with `VarHandle`'s public fence APIs:

~~~java
VarHandle.releaseFence();
VarHandle.acquireFence();
VarHandle.fullFence();
~~~

Fences operate at the memory-ordering level. Do not add fences arbitrarily to "make things thread-safe"; understand happens-before, volatile, and access modes before replacing. For ordinary synchronization, `synchronized`, locks, or atomic classes may be simpler and safer.

## 9. Replacing Unsafe.park/unpark with LockSupport

`java.util.concurrent.locks.LockSupport` is the public API for parking and unparking threads:

~~~java
import java.util.concurrent.locks.LockSupport;

Thread worker = new Thread(() -> {
    System.out.println("Waiting");
    LockSupport.park();
    System.out.println("Resumed");
});

worker.start();

LockSupport.unpark(worker);
~~~

Points to remember:

- `unpark(thread)` grants a permit to the thread; permits do not accumulate indefinitely, at most one permit is pending.
- `park()` can return because it was unparked, interrupted, or due to a spurious wakeup.
- Code using `park` should typically check the condition in a loop.
- If a thread is interrupted, the interrupt status may remain set; the application must handle it per its contract.

Conditional wait pattern:

~~~java
while (!condition) {
    LockSupport.park(this);
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
}
~~~

Do not use park/unpark as an arbitrary substitute for `wait/notify` or `Condition`. For most applications, `BlockingQueue`, `CountDownLatch`, `Semaphore`, `Lock`, and `Condition` are easier to use because they provide higher-level synchronization abstractions.

## 10. Defining Classes with Public APIs

Some legacy code uses `Unsafe.defineClass` to define classes dynamically. The replacement depends on where the class must be defined and who holds defining authority.

### 10.1. MethodHandles.Lookup.defineClass

`MethodHandles.Lookup.defineClass(byte[])` has existed since Java 9. It defines a class in the same package, class loader, and protection domain as the lookup class, provided the Lookup holds appropriate PACKAGE access:

~~~java
import java.lang.invoke.MethodHandles;

byte[] classBytes = loadClassBytes();
Class<?> generated = MethodHandles.lookup().defineClass(classBytes);
~~~

The bytecode must declare the matching package. This API is not a way to define classes arbitrarily into any package or class loader.

### 10.2. ClassLoader.defineClass for custom class loaders

If an application builds a custom class loader, it can extend `ClassLoader` and call the protected `defineClass` method inside the subclass:

~~~java
public final class PluginClassLoader extends ClassLoader {
    public PluginClassLoader(ClassLoader parent) {
        super(parent);
    }

    public Class<?> definePlugin(String name, byte[] bytes) {
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Package selection, loader constraints, protection domains, signers, and permissions must be designed properly. Do not define classes arbitrarily into another module's or JDK's namespace.

## 11. Replacing Internal Image APIs with ImageIO

Legacy internal image codecs such as `com.sun.image.codec.jpeg` are not appropriate choices for new code. Java provides `javax.imageio.ImageIO`:

~~~java
import java.awt.image.BufferedImage;
import java.io.InputStream;
import java.io.OutputStream;
import javax.imageio.ImageIO;

BufferedImage image;
try (InputStream input = openInput()) {
    image = ImageIO.read(input);
}

try (OutputStream output = openOutput()) {
    boolean written = ImageIO.write(image, "png", output);
    if (!written) {
        throw new IllegalStateException("No writer for PNG format");
    }
}
~~~

`ImageIO.read` can return `null` if no matching reader is found; `ImageIO.write` returns `false` if no writer exists for the requested format. Check return values and do not assume every JDK includes every third-party codec.

If specialized codecs or formats are required, use an ImageIO provider or a supported library with clear documentation.

## 12. Cases Without a Drop-in Replacement

Not every internal API has a direct public method replacement. Sometimes the right solution is changing the design.

### 12.1. Creating objects bypassing constructors

`Unsafe.allocateInstance` can create objects without running constructors. Java SE does not provide a general equivalent API to bypass all class invariants.

Approaches:

- Use constructors or static factories to initialize valid objects.
- For Java serialization, use standard serialization mechanisms and documented hooks.
- If a library must instantiate external types, design an SPI/factory or require a public constructor.
- Do not use deep reflection to bypass constructors or open JDK private APIs.

### 12.2. Arbitrary native memory

Operations like `Unsafe.allocateMemory` and `freeMemory` have no stable drop-in replacement in Java 17 Java SE.

Options depending on requirements:

- `ByteBuffer.allocateDirect` for bounded direct memory buffers suited to NIO APIs. However, Java 17 provides no general public method to immediately free a direct buffer at an arbitrary point; manage reference lifecycles and do not treat this as a complete substitute for allocate/free memory.
- JNI or a controlled native library if low-level native memory management is genuinely needed.
- The Foreign Function & Memory API in Java 17 is still an incubator API (JEP 412), not yet a stable Java SE API. Do not treat it as a stable production contract if the requirement is using only standardized Java 17 APIs.

If FFM is needed, re-evaluate the target JDK version and the API's standardization status in that version.

### 12.3. Accessing private JDK fields

There is no general public API allowing applications to arbitrarily read or modify private fields of JDK classes. If an application needs that information:

- Look for corresponding public accessors or management APIs.
- Use documented JMX, management APIs, or diagnostic APIs if functionally appropriate.
- If relying on internal structures for optimization, switch to public abstractions and re-measure performance.
- If no equivalent API exists, drop the dependency or redesign the feature.

Do not treat `--add-opens` as a replacement API.

### 12.4. Handling OS signals

Some applications use internal classes to register signal handlers. Java SE does not provide a general portable API for arbitrary POSIX signals. If the goal is cleanup during normal process termination, use `Runtime.addShutdownHook`; if specific signal handling is required, rely on supported environment/native-layer mechanisms and accept platform constraints.

## 13. Reflection and Modules: exports vs opens

### 13.1. `exports` for public APIs

A module exports a package so other modules can call its public API:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

`exports` does not automatically permit accessing private members via reflection.

### 13.2. `opens` for deep reflection

If a framework needs deep reflection into an **application** package, open that specific package:

~~~java
module com.example.application {
    requires some.framework;
    opens com.example.model to some.framework;
}
~~~

This is narrower than opening the entire module. Open only the packages truly needed and only to the exact target modules.

### 13.3. Use public reflection first

If you only need to invoke public constructors or methods, use public reflection:

~~~java
Constructor<?> constructor =
        type.getConstructor(String.class);
Object instance = constructor.newInstance("value");
~~~

Do not call `setAccessible(true)` out of habit if private member access is unnecessary. With newer APIs, you can check `trySetAccessible()`; it returns a boolean indicating whether access was enabled. Yet being accessible in one configuration does not mean the design should depend on private implementations.

### 13.4. MethodHandles.privateLookupIn

When private lookup access is needed for a class in another module, `MethodHandles.privateLookupIn` can be used if module and access conditions are satisfied:

~~~java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(targetClass, MethodHandles.lookup());
~~~

The target class's package must be opened by its module to the module holding the appropriate lookup. This is a controlled mechanism, not a way to bypass JDK strong encapsulation. Do not ask frameworks to open internal Java packages just to use private lookup.

## 14. --add-exports and --add-opens Are Only Transitional Bridges

These two flags often appear when applications upgrade to Java 9+ or Java 17.

| Flag | Effect | What it cannot do |
|---|---|---|
| `--add-exports module/package=target` | Allows target module to access public types in an unexported package | Does not open private members for deep reflection |
| `--add-opens module/package=target` | Opens package at runtime for deep reflection | Does not turn internal APIs into supported APIs; does not replace JDK contracts |

General forms:

~~~bash
java --add-exports source.module/internal.package=ALL-UNNAMED -jar app.jar
java --add-opens source.module/internal.package=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` refers to unnamed modules (typically applications running from the classpath). For modularized applications, specify the exact target module name.

These flags can help keep systems running while upgrading libraries, investigating, or breaking down a migration. However:

1. Document the exact package, module, and dependency requiring the flag.
2. Narrow the target, avoiding `ALL-UNNAMED` when unnecessary.
3. Plan to remove the flag once the library moves to public APIs.
4. Test on the target JDK without flags to confirm migration is complete.

Do not use `--add-opens` on JDK packages as a long-term solution for accessing private implementations. A flag only alters access for a single run; it does not make internal members stable APIs.

## 15. Migration Process for an Internal Dependency

A workflow you can apply in a project:

### Step 1: Locate all dependency points

Run `jdeps --jdk-internals` on relevant JARs and modules. Search source code for `sun.*`, `com.sun.*`, `jdk.internal.*` imports and class names used via reflection.

### Step 2: Identify the actual functionality

Do not stop at the class name. Ask what the code is trying to do:

- Encode/decode Base64?
- CAS a field?
- Clean up native resources?
- Dynamically define classes?
- Read a private field for metadata?
- Convert image data?

A single internal class may be used for multiple purposes; each purpose may require a different replacement API.

### Step 3: Select public APIs and identify differences

Read the Java 17 Javadoc of the target API. Compare:

- Semantics and data types.
- Exceptions and error reporting.
- Thread safety, memory ordering, and lifecycle.
- Performance limits or compatibility constraints.
- Module and access permission requirements.

### Step 4: Update code and dependencies

Replace imports, types, invocations, and resource management. If a third-party dependency still uses internals, upgrade to a Java 17-compatible version or replace the library.

### Step 5: Test on JDK 17

Compile against the target API:

~~~bash
javac --release 17 -d out @sources.txt
~~~

Run unit tests and integration tests with JDK 17. Test error paths, boundary data, reflection paths, plugins, serialization, and concurrency where relevant.

### Step 6: Verify no internal dependencies remain

Re-run:

~~~bash
jdeps --jdk-internals --recursive application.jar
~~~

Audit source code and deployment configurations to remove unneeded internal-access flags. A clean jdeps result is a good signal for static dependencies, though runtime testing is still needed for dynamic access.

## 16. Before and After Migration Examples

### 16.1. Base64 encoding

**Legacy internal API approach** (do not use in new code):

~~~java
// Example illustrating a legacy API name, not a Java SE API.
// sun.misc.BASE64Encoder encoder = new sun.misc.BASE64Encoder();
// String encoded = encoder.encode(data);
~~~

**Public API approach:**

~~~java
String encoded = Base64.getEncoder().encodeToString(data);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

### 16.2. Atomic field

Replace offset calculation and Unsafe CAS calls with VarHandle:

~~~java
private volatile long sequence;
private static final VarHandle SEQUENCE;

static {
    try {
        SEQUENCE = MethodHandles.lookup().findVarHandle(
                Sequence.class, "sequence", long.class);
    } catch (ReflectiveOperationException ex) {
        throw new ExceptionInInitializerError(ex);
    }
}

long next() {
    return (long) SEQUENCE.getAndAdd(this, 1L) + 1L;
}
~~~

No need to know JVM object layout or field offsets anymore.

### 16.3. Resource cleanup

Replace internal Cleaner with `java.lang.ref.Cleaner`, while providing an explicit `close()` so callers release resources promptly. Cleaner serves only as a fallback.

## 17. Common Mistakes

### 17.1. Changing only the package without checking the contract

Switching an internal class to a similarly named public class does not guarantee identical behavior. Compare semantics, exceptions, threading, and lifecycle before switching.

### 17.2. Treating Unsafe as a public API because JDK 17 still includes it

`sun.misc.Unsafe` is retained for compatibility, not as a committed Java SE API. Use VarHandle, atomic classes, or appropriate abstractions.

### 17.3. Adding --add-opens and considering migration done

Flags only open access at runtime. Reliance on private implementations remains and can break in future JDKs.

### 17.4. Opening an entire module to a framework

`open module` or opening packages broadly weakens encapsulation. Prefer narrowly scoped `opens package to module` and open only data packages needing reflection.

### 17.5. Relying solely on jdeps

Static analysis can miss dynamic reflection and plugins. Combine source search, tests, and runtime observation.

### 17.6. Replacing native memory with DirectByteBuffer without lifecycle planning

Direct buffers are not drop-in replacements for arbitrary allocate/free memory. Java 17 has no general public API to free immediately; design an appropriate lifecycle or choose a clearly managed native layer.

### 17.7. Using incubator FFM as a stable Java 17 API

The Foreign Function & Memory API in Java 17 is incubator. If only stable Java 17 Java SE APIs are allowed, do not treat it as a standardized replacement.

### 17.8. Testing only compilation while skipping runtime

Some errors appear only when reflection, serialization, class loading, or plugin paths actually run. Runtime testing on the target JDK is mandatory.

## 18. Practice Exercises

### Exercise 1 — Classify APIs

For each name below, check Javadoc and determine whether it is a public or internal API: `java.util.Base64`, `sun.misc.Unsafe`, `java.lang.ref.Cleaner`, `jdk.internal.misc.Unsafe`, `javax.imageio.ImageIO`. Explain why being accessible locally does not prove long-term support.

### Exercise 2 — Using jdeps

Run `jdeps --jdk-internals` on a project JAR. Record classes referencing internal packages and find which dependency introduces them. If output is empty, state the limitations of static analysis regarding dynamic reflection.

### Exercise 3 — Replacing Base64

Write UTF-8 encode/decode code using `java.util.Base64`. Try both basic and URL-safe encoders, and explain why the two encoded strings can differ.

### Exercise 4 — Replacing CAS with VarHandle

Write a class with a `volatile int count` field. Use VarHandle to increment atomically and compare with `AtomicInteger`. State when the Atomic API is more readable.

### Exercise 5 — Module exports and opens

Create a library module exporting `com.example.api` and opening `com.example.model` to a specific framework module. Explain why `exports` does not permit accessing private members via reflection.

### Exercise 6 — No direct replacement

A library uses `Unsafe.allocateMemory` and `Unsafe.freeMemory`. Propose options based on requirements: bounded buffers, native memory access via JNI, or architectural changes. Explain why DirectByteBuffer and Java 17's incubator FFM are not equivalent replacements in all cases.

### Exercise 7 — Removing internal-access flags

An application runs only with `--add-opens`. Identify which package is opened, why reflection accesses private members, and design a plan to switch to public APIs or narrowly scoped `opens` in the application's module. Finally, re-run tests without flags.

## 19. Completion Criteria

Learners have mastered this lesson when they can:

1. Explain the difference between public supported APIs and internal JDK APIs.
2. Describe the impact of the module system and strong encapsulation in Java 17.
3. Use `jdeps --jdk-internals` to locate internal dependencies and explain its limits with dynamic reflection.
4. Select `java.util.Base64`, `java.lang.ref.Cleaner`, `VarHandle`, `LockSupport`, or `ImageIO` appropriately by function.
5. Recognize when no drop-in replacement exists and redesign is required.
6. Distinguish `exports` from `opens`, and `--add-exports` from `--add-opens`.
7. Avoid treating `sun.misc.Unsafe` or internal-access flags as stable contracts.
8. Test on JDK 17 without internal-opening flags, covering reflection and runtime paths.
9. Verify static dependencies with jdeps and dynamic dependencies through tests/runtime observation.

## 20. Official Documentation

- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation changes in Java 17.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): modules, exports, opens, and access flags.
- [Java SE 17 API — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): field/array access modes and memory fences.
- [Java SE 17 API — `Cleaner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup actions and Cleanable.
- [Java SE 17 API — `Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): Basic, URL, and MIME encoders/decoders.
- [Java SE 17 API — `LockSupport`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark.
- [Java SE 17 API — `ImageIO`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/imageio/ImageIO.html): image reading/writing.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup and defineClass.
- [Java SE 17 API — `jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency analysis and JDK internals.
- [Java SE 17 API — `jdeprscan`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): deprecated API detection.
- [OpenJDK JEP 412 — Foreign Function & Memory API (Incubator)](https://openjdk.org/jeps/412): incubator status of FFM in Java 17.

**Key takeaway:** replacing an internal API is a contract migration, not just editing imports. Identify the functionality, choose a documented public API, understand differences in permissions and lifecycle, and test on Java 17 without relying on flags that open JDK internals. If no equivalent API exists, redesign or isolate platform-dependent parts instead of pretending a JVM flag solved the problem.
