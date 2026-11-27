# Migrating to Public APIs Instead of Internal Access When Upgrading to Java 17

When upgrading an application to Java 17, code can break due to dependencies on JDK internal APIs. The solution is to replace those dependencies with documented public APIs backed by compatibility contracts.

JDK 17 is a major milestone because JEP 403 enables strong encapsulation by default for most JDK internal elements. Consequently, libraries that previously read private JDK fields or invoked internal classes can fail at compile time or runtime. This article covers how to identify those dependencies, select replacement APIs, and migrate by use case.

## 1. How do public APIs differ from internal APIs?

**Public APIs** are published in official documentation and carry a usage contract. Examples:

- Java SE APIs in packages such as `java.util`, `java.nio`, `java.lang.invoke`, and `java.security`.
- Documented APIs in JDK modules, such as certain APIs in `jdk.jfr` or `jdk.httpserver`. These can be supported JDK APIs without necessarily belonging to standard Java SE.

**Internal APIs** exist to implement the JDK itself, not as public application contracts. Common packages to inspect include:

- `jdk.internal.*`.
- Many `sun.*` packages.
- Some `com.sun.*` packages.
- Classes, fields, or methods that are neither exported nor opened, even if reachable via reflection.

Do not judge solely by package prefix. Some `com.sun.*` packages provide documented public APIs, such as APIs exposed through JDK modules and described in Javadoc. Check official documentation, the owning module, and `jdeps` output before classifying.

### 1.1. Why avoid depending on internal APIs?

Internal dependencies introduce several risks:

1. **No compatibility guarantee:** implementations may rename classes, fields, methods, or data structures.
2. **Vendor differences:** an internal package may exist in one JDK distribution yet be absent or behave differently in another.
3. **Module restrictions:** unexported packages cannot be accessed normally from other modules.
4. **Blocked deep reflection:** attempts to open private JDK fields/methods may throw `InaccessibleObjectException`.
5. **Maintenance and security friction:** coupling to internal layouts makes it harder for the JDK to evolve implementations safely.

The fact that code runs on one JDK release does not prove an API is supported. What matters is whether the API is documented and published as an application contract.

### 1.2. JEP 403 and Java 17

JEP 403, *Strongly Encapsulate JDK Internals by Default*, took effect in Java 17. Most internal elements of the JDK are strongly encapsulated by default. This means:

- Code cannot access internal packages as public APIs by default.
- Reflection into non-public fields/methods of many JDK classes may be rejected.
- A package being exported for public type access does not mean it is opened for deep reflection.
- The `--illegal-access` flag is obsolete in Java 17; if supplied on the command line, the JVM emits a warning and ignores it rather than relaxing access.

JEP 403 retains a few critical exceptions for internal APIs preserved for compatibility, including `sun.misc.Unsafe`. Remaining accessible does not turn a class into a supported public API. Do not build new code on top of such exceptions.

## 2. Identify code depending on internal APIs

Before editing code, catalog dependencies across source, libraries, and runtime. Searching application source alone is insufficient because third-party dependencies can also use JDK internals.

### 2.1. Use jdeps --jdk-internals

`jdeps` is the class and module dependency analyzer shipped with the JDK. `--jdk-internals` finds references to JDK internal APIs.

Example analyzing a JAR:

~~~bash
jdeps --jdk-internals application.jar
~~~

If the application has classpath dependencies:

~~~bash
jdeps --jdk-internals --class-path "lib/*" application.jar
~~~

For multi-release JARs, specify the target release version:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

The short flag `-jdkinternals` is also supported, though `--jdk-internals` is clearer in new scripts.

Output identifies which classes reference internal packages and suggests replacement APIs. For example, references to `sun.misc.BASE64Encoder` are flagged to migrate to `java.util.Base64`.

### 2.2. Analyze dependencies as well

Your application might not import internal APIs directly while an older library does. Analyze the entire deployment artifact:

~~~bash
jdeps --jdk-internals --class-path "lib/*" application.jar
~~~

For modular applications, pass the appropriate module path:

~~~bash
jdeps --jdk-internals --module-path "mods:lib" application.jar
~~~

The path separator in the example above is a colon for Linux/macOS. On Windows, classpaths and module paths typically use a semicolon.

Use the `jdeps` binary from JDK 17 or your target toolchain so analysis reflects the target deployment environment.

### 2.3. Limitations of jdeps

`jdeps` performs static bytecode analysis. It is useful yet cannot catch every internal access path. Also check:

- Reflection using class or member names built via string concatenation.
- `Class.forName`, `getDeclaredField`, `getDeclaredMethod`, or `MethodHandles` accessing internal classes.
- Package/class names stored in configuration files, plugin descriptors, or scripts.
- JNI/native code resolving symbols or accessing internal structures directly.
- Dynamically loaded dependencies absent from the analyzed artifact.

Initial source searches can uncover suspicious imports:

~~~bash
rg -n "sun[.]|jdk[.]internal[.]|com[.]sun[.]" src
~~~

Search for reflection patterns:

~~~bash
rg -n "Class[.]forName|getDeclared(Field|Method|Constructor)|setAccessible|privateLookupIn" src
~~~

These searches produce a review list, not proof that every hit is an internal API. Legitimate public packages can share prefixes, and reflection on application-owned types may be valid.

### 2.4. Check both compile time and runtime

When building on JDK 17, the compiler can catch unexported packages or removed classes. Reflection dependencies, however, may fail only at runtime.

Therefore, combine:

1. Bytecode and dependency analysis with `jdeps`.
2. Compilation with a Java 17 toolchain.
3. Running tests on an actual JDK 17.
4. Checking startup logs and reflection/plugin paths.
5. Exercising features active mainly in production, such as serialization, logging, proxies, drivers, and instrumentation.

## 3. Mapping table from internal APIs to public APIs

The table below summarizes common upgrade cases. Not every internal API has a one-to-one replacement; some require redesign.

| Internal access | Public API to consider | Notes |
| --- | --- | --- |
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` | Offers basic, URL-safe, and MIME encoders/decoders |
| `sun.reflect.Reflection.getCallerClass` | `java.lang.StackWalker` | Stack-walking API available since Java 9 |
| Many `sun.misc.Unsafe` field/array atomics | `VarHandle` or `java.util.concurrent.atomic` | Must preserve memory ordering and atomic semantics |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Cleaner is a fallback; still prefer explicit resource closing |
| Defining classes via internal APIs | `MethodHandles.Lookup.defineClass` or `defineHiddenClass` | Constrained by package, lookup, and class loader rules |
| Memory access via internal direct-buffer classes | `ByteBuffer`, `ByteBuffer.allocateDirect` | Does not expose arbitrary Unsafe/native pointer capabilities |
| Reading private fields/methods of JDK classes | Official public methods/APIs | `MethodHandles` is not a mechanism to bypass module boundaries |
| `sun.security.*` | `java.security`, `java.security.cert`, `javax.crypto`, `javax.net.ssl` | Choose APIs by specific security operation |
| JDK internal XML parsers | JAXP, StAX, DOM, SAX | Program against documented parser APIs |
| Internal compiler implementation | `javax.tools`, `javax.lang.model`, and documented compiler APIs | Pick APIs by compilation or source analysis needs |

## 4. Replace internal Base64 with java.util.Base64

A straightforward migration example is `sun.misc.BASE64Encoder` and `sun.misc.BASE64Decoder`. These classes were removed in JDK 9. The public `java.util.Base64` API has existed since Java 8 and is the right choice on Java 17.

### 4.1. Basic encoding and decoding

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64Example {
    public static void main(String[] args) {
        String message = "Hello Java 17";
        byte[] input = message.getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(input);
        byte[] decoded = Base64.getDecoder().decode(encoded);

        String result = new String(decoded, StandardCharsets.UTF_8);
        System.out.println(encoded);
        System.out.println(result);
    }
}
~~~

Do not rely on the default charset when converting text to bytes. Specify UTF-8 when that is your protocol or data encoding.

### 4.2. Choose the right encoder variant

`Base64` provides three variants:

| API | Use case |
| --- | --- |
| `Base64.getEncoder()` / `getDecoder()` | Basic Base64 using the standard alphabet |
| `Base64.getUrlEncoder()` / `getUrlDecoder()` | Data used in URLs or filenames |
| `Base64.getMimeEncoder()` / `getMimeDecoder()` | MIME data with line-wrapping rules |

Do not swap only the class name mechanically. Check whether the legacy format inserted line breaks, used the URL-safe alphabet, or emitted padding. Pick the matching encoder and test against stored data or external protocols.

## 5. Replace Reflection.getCallerClass with StackWalker

Some legacy libraries used `sun.reflect.Reflection.getCallerClass` to locate the class calling a helper. The public `StackWalker` API, introduced in Java 9, allows controlled stack traversal.

### 5.1. Retrieve the caller class

~~~java
import java.lang.StackWalker;

public final class CallerInfo {
    private static final StackWalker WALKER =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    private CallerInfo() {
    }

    public static Class<?> callerClass() {
        return WALKER.getCallerClass();
    }
}
~~~

When `CallerInfo.callerClass()` is called, it returns the class invoking that helper method. `RETAIN_CLASS_REFERENCE` retains `Class<?>` references on stack frames.

### 5.2. Filter stack frames

If intermediate wrapper classes must be skipped, use `walk` and filter the stream:

~~~java
Class<?> caller = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE)
        .walk(frames -> frames
                .map(StackWalker.StackFrame::getDeclaringClass)
                .filter(type -> type != CallerInfo.class)
                .findFirst()
                .orElseThrow());
~~~

Adjust the filter in this snippet to match your application's actual call stack. Stacks may include proxies, frameworks, or adapter layers; avoid hardcoding a fixed frame index when call stack depth can vary.

Stack walking is also not a user authentication or authorization mechanism. Caller class is purely technical metadata about the current call chain.

## 6. Replace certain Unsafe operations with VarHandle

`sun.misc.Unsafe` provides low-level primitives such as offset-based field reads/writes, compare-and-set, array element access, and memory fences. Java 17 still retains some `Unsafe` APIs for compatibility, yet it remains an internal API rather than a public contract for new application code.

`VarHandle`, introduced in Java 9, accesses variables with defined memory-ordering modes. It supports instance fields, static fields, array elements, and other variable forms.

### 6.1. Atomic counter using AtomicInteger

If you only need a concurrent counter, atomic classes are usually simpler than `VarHandle`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int current() {
        return count.get();
    }
}
~~~

There is no need to compute field offsets or write manual compare-and-swap loops for this common pattern.

### 6.2. VarHandle for a field

When fine-grained control over access modes is required, `VarHandle` can be used:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup().findVarHandle(
                    Counter.class, "count", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) COUNT.getAndAdd(this, 1) + 1;
    }

    public int current() {
        return (int) COUNT.getVolatile(this);
    }
}
~~~

`MethodHandles.lookup()` inside `Counter` holds permission to look up private fields of `Counter` itself. A lookup created from another class may lack that access.

`VarHandle` provides access modes such as:

- `get`, `set`: plain access.
- `getVolatile`, `setVolatile`: volatile access.
- `getAcquire`, `setRelease`: acquire/release semantics.
- `compareAndSet`, `compareAndExchange`: conditional atomic updates.
- `getAndAdd`, `getAndSet`: value-returning atomic updates.

### 6.3. Do not replace Unsafe with VarHandle mechanically

Low-level operations may depend on very specific memory ordering. When migrating to `VarHandle`:

1. Identify the exact field or data region accessed.
2. Determine whether the code requires plain, opaque, acquire/release, or volatile semantics.
3. Choose the matching access mode.
4. Preserve inter-thread visibility guarantees under the Java Memory Model.
5. Test under contention rather than verifying only single-threaded results.

Do not convert every `Unsafe` call to `getVolatile` or `compareAndSet` by blanket rule. Two APIs can differ in semantics and synchronization guarantees.

### 6.4. Not every Unsafe method has a one-to-one replacement

Some `Unsafe` operations have no direct Java SE equivalent. For example, allocating objects without running constructors or manipulating arbitrary native addresses usually requires redesign.

Options to consider:

- Use constructors, factories, or builders to instantiate objects via public contracts.
- Use `System.arraycopy`, array APIs, or `ByteBuffer` for appropriate data operations.
- Use `AtomicInteger`, `AtomicLong`, `AtomicReference`, or `VarHandle` for synchronization.
- Use JNI or a maintained native library with a clear contract when genuine native interop is required.

Never pick an API merely because its name or capabilities look similar. Confirm the exact semantics you must preserve.

## 7. Replace internal Cleaner with java.lang.ref.Cleaner

If code uses `sun.misc.Cleaner` or an internal cleaner to release resources, the public API is `java.lang.ref.Cleaner`, added in Java 9.

However, `Cleaner` must not replace explicit resource closing. Whenever a resource can be closed deterministically, provide `close()` and implement `AutoCloseable` for try-with-resources. `Cleaner` is strictly a safety net when an object becomes phantom-reachable and the caller forgot to close it.

Structural example:

~~~java
import java.lang.ref.Cleaner;

public final class NativeResource implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private long handle;

        State(long handle) {
            this.handle = handle;
        }

        @Override
        public synchronized void run() {
            if (handle != 0) {
                releaseNativeHandle(handle);
                handle = 0;
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public NativeResource(long handle) {
        this.state = new State(handle);
        this.cleanable = CLEANER.register(this, state);
    }

    @Override
    public void close() {
        cleanable.clean();
    }

    private static void releaseNativeHandle(long handle) {
        // Call application-managed native API.
    }
}
~~~

`State` holds no reference back to `NativeResource`, avoiding a reference cycle that would prevent the cleaner from reclaiming the owning object. In real applications, releasing a native handle must be idempotent and synchronized with operations using the handle.

Caller usage:

~~~java
try (NativeResource resource = new NativeResource(handle)) {
    useResource(resource);
}
~~~

## 8. Define classes with MethodHandles.Lookup

Older frameworks sometimes used internal APIs to define classes into a class loader. Java provides public APIs on `MethodHandles.Lookup`:

- `Lookup.defineClass(byte[])` since Java 9.
- `Lookup.defineHiddenClass(...)` since Java 15.

Example:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(classBytes);
~~~

`defineClass` defines the class in the same runtime package, class loader, and protection domain as the lookup class. The bytecode must match that package, and the lookup must hold the required privilege.

For classes generated strictly for internal runtime use that do not need ordinary binary names, consider `defineHiddenClass`. Hidden classes have different lifecycles and linkage rules from normal classes, so they are not a universal drop-in replacement.

Do not use these APIs to inject arbitrary classes into JDK packages. Module, package, and Lookup rules still apply.

## 9. Replace internal memory access with ByteBuffer and appropriate APIs

Some libraries used internal classes like `sun.nio.ch.DirectBuffer` or `Unsafe` for direct memory access. When the need is buffer-oriented reading and writing, evaluate `java.nio.ByteBuffer`.

~~~java
import java.nio.ByteBuffer;

ByteBuffer heapBuffer = ByteBuffer.allocate(1024);
ByteBuffer directBuffer = ByteBuffer.allocateDirect(1024);

directBuffer.putInt(42);
directBuffer.flip();
int value = directBuffer.getInt();
~~~

`ByteBuffer.allocateDirect` creates a direct buffer suitable for supported I/O or native interop paths. It does not expose a public API to extract and manipulate arbitrary native pointers like `Unsafe`. Direct buffer deallocation lifecycle also differs from an explicit `close()` API on `ByteBuffer`.

When native resources require deterministic lifetimes, wrap the native handle in an `AutoCloseable` abstraction. If you need native function calls or native memory under a different contract, evaluate JNI or a maintained native solution. Do not reach into an internal package just to read a buffer's address.

## 10. Migrate from sun.security.* to Java Security APIs

`sun.security.*` packages hold JDK implementations, not general application APIs. When handling certificates, keys, signatures, or TLS, choose APIs by task:

| Need | Public API |
| --- | --- |
| Read and parse certificates | `java.security.cert.CertificateFactory` |
| Inspect certificates and cert paths | `java.security.cert` |
| Manage keys and key pairs | `java.security.Key`, `KeyPair`, `KeyStore`, `KeyFactory` |
| Sign / verify signatures | `java.security.Signature` |
| Encrypt and decrypt | `javax.crypto.Cipher` |
| MAC and suitable key derivation | `javax.crypto.Mac`, `SecretKeyFactory` |
| TLS client/server | `javax.net.ssl.SSLContext`, `SSLSocket`, `SSLEngine` |
| Algorithms/providers | `java.security.Provider` and documented provider APIs |

Not every certificate-generation task or X.509 structure has a simple single-method Java SE replacement for legacy internal classes. If public JDK APIs do not cover your requirement, use a maintained security library with clear contracts and compatibility policies. Avoid manipulating private JDK structures directly.

## 11. Migrate internal XML parsers to JAXP, StAX, DOM, or SAX

An application may reference XML parser implementations bundled inside the JDK, such as internal Xerces classes. Rather than coupling to implementations, program against public XML APIs:

- `javax.xml.parsers`: instantiate DOM or SAX parsers.
- `javax.xml.stream`: StAX streaming API.
- `org.w3c.dom`: DOM tree model.
- `org.xml.sax`: SAX callbacks.
- `javax.xml.transform`: XML transformations.

Example creating a DOM parser:

~~~java
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
DocumentBuilder builder = factory.newDocumentBuilder();
var document = builder.parse(inputStream);
~~~

For untrusted XML, configure parsers safely according to application requirements: disable external entities or external DTDs when unneeded, restrict external schema access, and verify XXE protections. Switching to public APIs does not automatically make parser configuration secure.

## 12. Migrate compiler internals to documented APIs

If a build tool or plugin depends directly on internal `javac` implementations, evaluate:

- `javax.tools.JavaCompiler` to invoke compilation.
- `javax.tools.DiagnosticCollector` to capture errors/warnings.
- `javax.lang.model` to inspect program models.
- `com.sun.source.tree` and `com.sun.source.util` for documented compiler tree APIs in module `jdk.compiler`.

Example obtaining the standard compiler:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("A full JDK is required");
}
~~~

These APIs let tools integrate with the compiler without touching internal implementation classes. Check module descriptors and JDK 17 documentation for the specific API used; a documented API inside a JDK module might still sit outside standard Java SE.

## 13. Strong encapsulation: exports, opens, and temporary flags

The Java Platform Module System separates public API access from deep reflection.

### 13.1. --add-exports

`--add-exports` lets a reading module access public types in a package that the source module does not export to that target module.

Syntax:

~~~text
--add-exports source.module/package=target.module
~~~

Example:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -jar application.jar
~~~

This illustrates a specific internal package; use it only when you have confirmed a dependency requires it. `ALL-UNNAMED` applies to code running on the classpath. `--add-exports` can also be passed to the compiler when compiling code relying on that package.

### 13.2. --add-opens

`--add-opens` opens a package for runtime deep reflection into non-public members:

~~~text
--add-opens source.module/package=target.module
~~~

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

This option is typically used temporarily when a legacy library reflects on private fields/methods of JDK classes. It is not a replacement for public APIs and does not fix internally coupled source code.

### 13.3. --illegal-access is no longer a solution in Java 17

From Java 9 through Java 16, `--illegal-access` provided a transitional mode for certain reflective accesses. From Java 17 onward, the option is obsolete: the JVM warns and leaves the encapsulation policy unchanged.

Do not add `--illegal-access=permit` or other variants to command lines to fix Java 17 errors. Update dependencies, replace internal APIs, or pinpoint specific packages to open during transition.

### 13.4. When can add-exports/add-opens be used?

Consider them strictly as temporary compatibility measures when:

- The dependency has no fix yet and cannot be replaced immediately.
- The exact module and package needing access are confirmed.
- Scope is tightly bounded and a dependency upgrade plan exists.
- Tests verify the configuration on the target runtime.

Avoid broad package openings. Every extra exported or opened package enlarges the surface exposed to internal implementations.

## 14. Practical migration workflow

An upgrade workflow can be structured into the following steps.

### Step 1: Establish a baseline

- Record current JDK and target JDK.
- Record dependencies, plugins, agents, and native libraries.
- Save deployment command lines and module/classpath setups.
- Run current tests to capture behavioral baselines.

### Step 2: Locate internal references

- Run `jdeps --jdk-internals` on the application JAR and dependencies.
- Search for `sun.*`, `jdk.internal.*`, and suspect `com.sun.*` imports.
- Audit reflection, string-based class loading, and JNI.
- Document affected classes, libraries, modules, and features.

### Step 3: Select replacement APIs

- Consult Java SE 17 and JDK 17 Javadocs.
- Use mapping tables as starting points, then verify exact semantics.
- If no one-to-one API exists, redesign the abstraction or adopt a maintained library.
- Do not choose an API just because the package name looks similar or the class exists in the JDK.

### Step 4: Upgrade dependencies

Review framework, ORM, logging, bytecode library, JSON/XML parser, monitoring agent, and build plugin versions. Choose releases supporting Java 17 that have eliminated invalid internal accesses.

If a dependency lacks a compatible release, evaluate replacing the library or applying temporary add-opens/add-exports flags. Never patch internal JDK classes to keep an old dependency alive.

### Step 5: Update code and build

- Replace internal imports and reflection with public APIs.
- Compile with JDK 17.
- Use `javac --release 17` or equivalent build-tool config to enforce platform API boundaries.
- Remove ineffective `--illegal-access` flags.
- Keep any remaining add-opens/add-exports flags on a short list with owners and justifications.

### Step 6: Test runtime behavior

Run tests on an actual JDK 17, including rarely exercised paths: framework startup, reflection, proxies, serialization, TLS, parsers, dynamic class generation, and plugin loading.

### Step 7: Remove workarounds

Once dependencies are updated or code is migrated to public APIs:

- Remove `--add-opens` and `--add-exports` flags one by one.
- Re-run tests to verify no dependency remains.
- Re-run `jdeps --jdk-internals`.
- Monitor startup and production logs after deployment.

## 15. Before and after migration examples

### 15.1. Base64

Previously, legacy code might have used a removed class:

~~~java
// Legacy internal API, no longer in JDK 17.
// sun.misc.BASE64Encoder encoder = new sun.misc.BASE64Encoder();
~~~

New code:

~~~java
String encoded = Base64.getEncoder().encodeToString(bytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

### 15.2. Caller lookup

Previously, some libraries used:

~~~java
// Internal API; do not use in new code.
// sun.reflect.Reflection.getCallerClass(2);
~~~

New code using StackWalker:

~~~java
private static final StackWalker WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

static Class<?> caller() {
    return WALKER.getCallerClass();
}
~~~

### 15.3. Atomic field

If only a counter is needed:

~~~java
private final AtomicLong requests = new AtomicLong();

long nextRequestNumber() {
    return requests.incrementAndGet();
}
~~~

If custom access modes on a field are required, use `VarHandle` and verify memory semantics carefully. Do not keep field offsets or native addresses merely because legacy code used `Unsafe`.

## 16. Common pitfalls when migrating to public APIs

| Issue | Cause | Resolution |
| --- | --- | --- |
| Compile fails on unexported package | Code references internal or unexported module package | Find public API replacement; check module and jdeps |
| Runtime throws `InaccessibleObjectException` | Reflection tries to access non-public member in closed package | Use public APIs; open package only temporarily with justification |
| Added `--illegal-access=permit` but error persists | Option is obsolete and ineffective on Java 17 | Remove flag, fix dependency, or apply temporary package-specific workaround |
| `jdeps` reports clean yet runtime fails | Access happens via reflection, JNI, or dynamic loading | Search class/member strings and run runtime tests |
| Migrated Unsafe to VarHandle and concurrency tests fail | Memory ordering or atomic semantics changed | Pick matching access modes and run multi-threaded tests |
| Migrated Base64 and output strings differ | Legacy encoder used line wrapping or a different alphabet | Pick basic, URL, or MIME encoder per protocol |
| Used StackWalker and caller differs from expected | Framework/proxy added stack frames or helper sits at different depth | Filter stack frames intentionally by class/method |
| Dependency still requires add-opens | Library does not yet support Java 17 or uses deep reflection into JDK | Upgrade or replace dependency; track temporary flags |
| Assumed all `com.sun` packages are internal | Some `com.sun` packages are documented and exported | Check Javadoc, modules, and support contracts |

## 17. Principles for long-term code compatibility

1. Prefer Java SE APIs whenever possible for portability across JDK vendors.
2. When using APIs in JDK-specific modules, check documentation, module dependencies, and compatibility policies.
3. Never import internal packages or read private fields of JDK classes.
4. Never rely on a global launcher flag to relax encapsulation everywhere.
5. Keep any add-opens/add-exports list minimal, justified, and scheduled for removal.
6. Upgrade dependencies before upgrading the production runtime.
7. Run `jdeps` across both the application and bundled libraries.
8. Add runtime tests for features using reflection, plugins, and native code.
9. For `VarHandle`/atomic code, preserve Java Memory Model semantics rather than merely silencing compiler errors.
10. Monitor deprecation warnings and target JDK migration guides with every upgrade.

## 18. Self-check questions

**1. Why migrate away from JDK internal APIs?**  
Because they carry no compatibility guarantee like public APIs, can change or become strongly encapsulated, and couple applications to implementation details.

**2. What does JEP 403 change in Java 17?**  
Strong encapsulation is enabled by default for most JDK internal elements.

**3. Does `--illegal-access` still grant reflection access on Java 17?**  
No. The option is obsolete; it only emits a warning and does not alter access policy.

**4. Which tool finds bytecode references to JDK internals?**  
`jdeps --jdk-internals`.

**5. Does `jdeps` detect every reflective access?**  
No. It is static analysis; string-based reflection, JNI, and dynamic loading can go undetected.

**6. What replaces `sun.misc.BASE64Encoder`?**  
`java.util.Base64`, choosing the basic, URL-safe, or MIME encoder to match data formatting.

**7. What replaces `sun.reflect.Reflection.getCallerClass`?**  
`java.lang.StackWalker`.

**8. When should VarHandle be used?**  
When accessing fields/arrays with atomic operations or specific memory ordering; for simple counters, `Atomic` classes are often simpler.

**9. Does `sun.misc.Unsafe` still being accessible in Java 17 make it a public API?**  
No. Some internal APIs are retained for compatibility, but they remain unsupported as public contracts.

**10. What is the difference between `--add-exports` and `--add-opens`?**  
`--add-exports` grants access to public types in a package; `--add-opens` grants runtime deep reflection into a package.

**11. Is `--add-opens` the final solution when upgrading to Java 17?**  
No. It is only a narrow transitional workaround when a dependency cannot yet be updated.

**12. Are all `com.sun.*` packages internal APIs?**  
No. Check Javadoc and modules; some packages contain documented public APIs.

**13. When should ByteBuffer replace internal direct-buffer access?**  
When reading/writing buffered data via public NIO APIs; `ByteBuffer` does not replace arbitrary native address manipulation.

**14. Why run tests on the JDK 17 runtime even after jdeps shows no warnings?**  
Because `jdeps` cannot detect all dynamic accesses and does not verify runtime behavior of reflection, native code, or dependencies.

## Official references

- [JEP 403 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/403): strong encapsulation changes in Java 17 and retained exceptions.
- [Java SE 17 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): identifying internal API dependencies, using jdeps, and selecting replacements.
- [Java SE 17 Migration Guide — Removed APIs](https://docs.oracle.com/en/java/javase/17/migrate/removed-apis.html): removed internal APIs and replacements such as Base64, VarHandle, and StackWalker.
- [Java SE 17 — The jdeps Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): `--jdk-internals`, classpath, module path, and multi-release JARs.
- [Java SE 17 API — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): basic, URL-safe, and MIME encoders/decoders.
- [Java SE 17 API — StackWalker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html): stack-walking API and retrieving caller classes.
- [Java SE 17 API — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes, atomic operations, and memory ordering.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): managing cleanup actions when objects are reclaimed.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): defining classes and lookup permissions.
- [JEP 193 — Variable Handles](https://openjdk.org/jeps/193) and [JEP 259 — Stack-Walking API](https://openjdk.org/jeps/259): design of public APIs replacing several internal use cases.
