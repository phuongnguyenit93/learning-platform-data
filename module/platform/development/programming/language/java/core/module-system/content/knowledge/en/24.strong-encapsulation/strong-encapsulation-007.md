# Reducing Internal API Dependencies with Public APIs

Internal APIs are classes, interfaces, methods, or packages belonging to the JDK's internal implementation, not committed as stable public APIs for applications. Depending on them can cause a program to compile or run on one JDK yet break when upgrading to another JDK.

The Java Module System strengthens boundaries between modules and packages. Starting in Java 9, many internal JDK packages are not exported to external code. Encapsulation tightened across releases; starting in JDK 17, the broad mechanism for unauthorized access to internal packages was removed. The sustainable approach is to replace internal dependencies with supported public APIs.

## 1. Why Avoid Internal APIs?

Internal APIs often have package names such as sun.*, jdk.internal.*, or certain com.sun.* packages. However, you cannot conclude based solely on the package prefix: the JDK also has public, documented APIs in com.sun.* packages. You need to inspect the module, API documentation, and support status of each type.

Risks of using internal APIs:

- **No compatibility guarantee:** the JDK may rename, move, or delete internal types between releases.
- **Blocked by the module system:** unexported or unopened packages can cause compilation errors, IllegalAccessError, or InaccessibleObjectException.
- **Coupling to implementation details:** code may rely on object layout, private fields, class loader structure, or unspecified behavior.
- **Difficult upgrades and testing:** each JDK change may require updating workarounds and adding access-opening flags.
- **Increased security risk:** deep access to internal state can break encapsulation and library safety assumptions.

An application running successfully on one JDK does not prove the dependency is supported. Check whether the API is documented in the official Java SE API or JDK API, whether the module exports the package, and whether the documentation commits to supporting it for applications.

## 2. Distinguishing Public APIs, Internal APIs, and Deprecated APIs

| API Type | Characteristics | How to Handle |
|---|---|---|
| Public Java SE API | Specified and documented; carries compatibility guarantees under Java SE policy | Prefer using |
| Public JDK API outside Java SE | Documented in the JDK, though support scope may differ from Java SE | Check API documentation and commitments |
| Internal API | Implementation detail with no stability guarantee for applications | Find a public replacement API |
| Deprecated API | API may still be public, but marked as discouraged or scheduled for removal | Find a replacement API and plan migration |

Deprecated does not mean internal. A deprecated API can still be a public API; conversely, an internal API may not yet be marked deprecated yet still not be supported as a contract for applications.

Do not use a package name alone as the sole criterion. Check Javadoc documentation, module descriptors, relevant JEPs, and dependency analysis tool results.

## 3. Finding Dependencies on JDK Internals

### Using jdeps

jdeps is a class- or module-level dependency analysis tool. The --jdk-internals option helps find references to JDK internal APIs in compiled classes or JARs.

Example:

~~~bash
jdeps --jdk-internals app.jar
~~~

Analyzing a set of JARs:

~~~bash
jdeps --jdk-internals lib/*.jar
~~~

Specifying the multi-release JAR version to analyze:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

If the application has external dependencies, provide the appropriate classpath so jdeps can perform complete analysis:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

The output typically identifies which class references an internal API, the API name, and the module/package containing it. Use that output to determine whether the dependency is direct or comes from a third-party library.

jdeps analyzes bytecode. It cannot detect every case of dynamically constructed access via reflection, string-concatenated class names, JNI, or native code. Therefore, combine it with source code searches and runtime testing.

### Searching source code and build configuration

Search for common imports and names:

~~~text
sun.
com.sun.
jdk.internal.
Unsafe
ReflectionFactory
SharedSecrets
~~~

Search compiler configurations, JVM arguments, and dependent libraries as well. An application may not import internal APIs directly yet still depend on a library that uses them.

Inspect Maven or Gradle dependency trees to identify which library version pulls in the internal API. Upgrading a library to a version that has switched to public APIs is usually better than opening JDK packages for the entire application yourself.

### Checking runtime errors

Some dependencies only surface when code executes branches using reflection or internal classes. Watch for errors such as:

- IllegalAccessError: code lacks permission to access a type or member under access rules.
- InaccessibleObjectException: deep reflection cannot open a member of a module/package.
- NoClassDefFoundError or ClassNotFoundException: internal type no longer exists or cannot be found.
- NoSuchMethodError or NoSuchFieldError: API/implementation details have changed.

Do not handle these errors by adding module-opening flags wholesale before identifying the class and package actually causing the error.

## 4. Process for Replacing with Public APIs

For each detected internal API, document its actual purpose before choosing a replacement API. Two APIs with similar names do not necessarily share the same semantics, performance, resource lifecycle, or security model.

Recommended workflow:

1. **Identify call sites:** find classes, methods, fields, or reflection operations using the internal API.
2. **Understand the purpose:** does the code need to encode data, access memory, read metadata, manipulate classes, monitor runtime, or work with files?
3. **Find supported APIs:** consult the Java SE API, JDK API, and official migration guides.
4. **Compare semantics:** check error handling, data limits, thread safety, access permissions, and lifecycle.
5. **Replace at an appropriate abstraction:** prefer fixing within an adapter or integration module rather than letting internal APIs spread throughout the application.
6. **Test on the target JDK:** verify outputs, exceptions, required performance, and behavior when modules are encapsulated.
7. **Remove workarounds:** once migration is complete, remove add-exports/add-opens flags and unneeded dependencies.

## 5. Common Replacement Examples

The examples below represent common migration paths. Verify your application's specific requirements before replacing.

| Internal API or Legacy Approach | Public API to Consider | Notes |
|---|---|---|
| sun.misc.BASE64Encoder / BASE64Decoder | java.util.Base64 | Provides encoders/decoders for Basic, URL, and MIME |
| com.sun.image.codec.jpeg | javax.imageio.ImageIO | Use ImageIO and appropriate ImageReader/ImageWriter |
| sun.misc.Unsafe for controlled variable access | java.lang.invoke.VarHandle | Supports variable access with memory ordering and atomic operations |
| Unsafe for off-heap memory allocation/access | java.lang.foreign.MemorySegment and Arena | Foreign Function & Memory API finalized in JDK 22; clear lifetime management |
| Reflection into private JDK fields | Public API designed for that operation | There is no single general replacement API for all internal fields |
| Reading class or module structure by parsing implementation | java.lang.classfile (if supported by target JDK) or bytecode tools with supported APIs | Choose based on JDK version and compatibility requirements |
| Monitoring runtime statistics via internal structures | java.lang.management, JFR, or documented monitoring APIs | Choose the API matching the data you need to observe |

### Base64

Legacy code may use the sun.misc.BASE64Encoder class:

~~~java
// Legacy approach: depends on JDK internal API
// BASE64Encoder encoder = new BASE64Encoder();
// String encoded = encoder.encode(bytes);
~~~

Replace with the standard API:

~~~java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(bytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

If the data is used in URLs, choose getUrlEncoder() and getUrlDecoder(). If MIME formatting with line separators is needed, choose getMimeEncoder() and getMimeDecoder(). Do not swap decoders mechanically if the input format has specific rules.

### Image I/O

Replace legacy JPEG codec classes with javax.imageio:

~~~java
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;

BufferedImage image = ImageIO.read(new File("input.jpg"));
if (image == null) {
    throw new IllegalArgumentException("Unsupported image format");
}

boolean written = ImageIO.write(image, "jpg", new File("output.jpg"));
if (!written) {
    throw new IllegalStateException("No suitable writer available");
}
~~~

ImageIO.read() can return null if no suitable reader is found. ImageIO.write() returns a boolean indicating whether a writer supports the requested format. Applications must check these cases instead of assuming files always read/write successfully.

### Variable Access with VarHandle

If code uses Unsafe solely to read, write, or update variables with memory ordering, consider VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

VarHandle provides access modes such as get, set, getVolatile, compareAndSet, and getAndAdd depending on the variable type and supported access modes. Choose the right memory semantics; not every Unsafe operation has a one-to-one replacement with VarHandle.

### Off-Heap Memory

If the goal is working with native memory, JDK 22 and later have the finalized Foreign Function & Memory API. MemorySegment represents a memory region with clear bounds and lifetime; Arena manages the lifetime of allocations.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8);

    segment.set(ValueLayout.JAVA_LONG, 0, 42L);
    long value = segment.get(ValueLayout.JAVA_LONG, 0);

    System.out.println(value);
}
~~~

When the Arena closes, segments belonging to that arena can no longer be used. This expresses ownership and memory lifetime more clearly. Do not switch to MemorySegment if the code only needs a byte array or ByteBuffer; use the simplest abstraction that meets requirements.

## 6. When Reflection Is Needed, Distinguish exports and opens

The module system has two concepts that are often confused:

- **exports** allows other modules to access public types in a package under module rules.
- **opens** allows deep reflection into non-public members of a package at runtime.

An exported package does not mean its private fields can be opened with reflection. Conversely, opens does not make a package an API that can be imported and called directly at compile time.

If opening a package is needed during migration, you can use:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

This option opens package java.lang of module java.base to classes belonging to the unnamed module. It affects only deep reflection access at runtime for the specified package.

If code needs access to public types in an unexported package, --add-exports is a different option:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

With javac, you can pass the corresponding --add-exports when compiling:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
      -d out src/example/Main.java
~~~

The examples above only illustrate how to create a compatibility bridge. They should not be viewed as the final migration solution. Opening an internal package does not make that API supported and can keep the application dependent on JDK internals.

If the caller is a named module, replace ALL-UNNAMED with the appropriate target module name. Open or export only the exact packages and modules required; avoid granting broad permissions to the entire application.

## 7. Role and Limits of --illegal-access

In early JDK releases after Java 9, the --illegal-access option previously supported a transition period for some reflective accesses from legacy code into internal JDK packages.

Starting in JDK 16, strong encapsulation was applied more broadly by default. Starting in JDK 17, --illegal-access no longer restores the previous broad opening mechanism; this option is retained only for syntax compatibility and emits warnings without reopening internal packages.

Therefore, do not add:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

to fix applications on modern JDKs. Identify the specific package and move to public APIs. If you need to temporarily run a legacy application, use narrowly scoped --add-exports or --add-opens based on actual errors, then plan their removal.

## 8. Planning Migration for Large Applications

For applications with many modules or third-party libraries, do not replace all internal APIs at once without a dependency inventory and tests.

You can divide the work into groups:

| Group | Work Required |
|---|---|
| Application source code | Search for imports, reflection, MethodHandles, and internal class names |
| Direct dependencies | Upgrade libraries or replace implementations |
| Transitive dependencies | Identify which library pulls in internal APIs; coordinate with vendors if needed |
| JVM arguments | List --add-exports, --add-opens, and legacy options |
| Testing | Run on both the lowest and highest supported JDKs |
| Release | Remove unneeded workarounds, verify launch scripts and deployment docs |

Integrate internal API checking into CI:

~~~bash
jdeps --jdk-internals --class-path "lib/*" build/app.jar
~~~

You can save the output and fail the build when new dependencies appear, depending on project policy. If you cannot block immediately, at least record a baseline and track newly added dependencies.

For third-party libraries, prioritize upgrading to a version supporting the target JDK. If no replacement exists yet, isolate the library behind an adapter or separate module so the rest of the application does not depend directly on internal APIs.

## 9. Post-Migration Testing Checklist

After replacement, verify the behaviors the old code previously provided:

- Are business results equivalent to the original requirements?
- Are null, empty data, large data, and malformed data cases handled properly?
- Are memory ordering, atomicity, or thread safety still correct if Unsafe was replaced?
- Are native memory and resources released with the right lifetime?
- Does reflection still work in the actual modular environment?
- Does the application run on all committed supported JDKs?
- Are there any remaining internal API references in jdeps output?
- Can --add-exports and --add-opens options be removed?
- Do launch scripts, container images, and CI environments use the same JDK configuration?

In particular, run tests with the module path if the application is modular. An application running on the classpath can mask readability, exports, or opens issues that only appear when moving to the module path.

## 10. Takeaways

Strong encapsulation protects the boundary between supported APIs and JDK implementation details. The sustainable migration approach is to detect dependencies with jdeps and source searches, identify the intended use, and replace with appropriate public APIs such as Base64, ImageIO, VarHandle, MemorySegment, or runtime management APIs.

--add-exports and --add-opens should only be narrowly scoped bridges during transition. They do not create compatibility guarantees for internal APIs. After migration, remove workarounds, inspect bytecode, and run tests on the target JDKs.

## References

- JEP 403 — Strongly Encapsulate JDK Internals: https://openjdk.org/jeps/403
- JEP 396 — Strongly Encapsulate JDK Internals by Default: https://openjdk.org/jeps/396
- Oracle Java Platform, jdeps tool: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Java API — VarHandle: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html
- Java API — Foreign Function & Memory: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html
