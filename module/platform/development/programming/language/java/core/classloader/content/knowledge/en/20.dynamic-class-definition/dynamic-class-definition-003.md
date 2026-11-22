# MethodHandles.Lookup.defineClass and Class Definition Context in Java

## 1. Why Does Dynamic Class Definition Need a Trusted “Context”?

Java does not only load bytecode from the classpath or existing JARs. Frameworks, code generation tools, proxy engines, and plugin runtimes can **generate class file bytes at runtime**, and then ask the JVM to define a new type. However, a `byte[]` array alone does not answer the important questions:

- Which **ClassLoader** will the new class belong to?
- What package name and **runtime package** does it have?
- Does it have package-private access to surrounding classes?
- Which module does it belong to, and which APIs can it read and use?
- Which **protection domain** does it receive?
- Who is authorized to create a new class in an existing namespace?
- Has it been **initialized** yet, and does it duplicate an existing definition?

Since Java 9, the `java.lang.invoke.MethodHandles.Lookup.defineClass(byte[])` API addresses a specific case: **defining a normal, named class in the same runtime context as the lookup class**.

Signature:

```java
public Class<?> defineClass(byte[] bytes)
        throws IllegalAccessException
```

This is a method signature of `MethodHandles.Lookup`, not a standalone program.

**Accurate summary:** `Lookup.defineClass` creates and links a class from valid bytecode **with the same defining ClassLoader, the same runtime package, and the same protection domain as the lookup class**. It **requires the `PACKAGE` mode** on the `Lookup` and **does not run the class initializer** upon definition. The method does not accept an argument to choose an arbitrary ClassLoader, nor does it create a new class in another package of the caller's choice.

This differs significantly from a custom `ClassLoader` that reads bytecode itself in `findClass` and then calls `ClassLoader.defineClass`: the party using `Lookup` must prove it has the corresponding package context permission, rather than choosing an arbitrary loader/source from that API.

## 2. Key Terms to Distinguish

| Term | Meaning in This Article | Example |
| --- | --- | --- |
| **Class file bytes** | A sequence of bytes conforming to the JVMS class file format, typically starting with magic `CA FE BA BE` | Contents of `Generated.class` |
| **Binary name** | The binary name of the type in the class file | `demo.lookup.Generated` |
| **Lookup class** | The class that determines the context and permissions of the `Lookup` object | `demo.lookup.LookupDefineDemo` |
| **Lookup modes** | Permission flags such as `PUBLIC`, `MODULE`, `PACKAGE`, `PRIVATE` | `lookup.lookupModes()` |
| **Defining ClassLoader** | The loader that defines the runtime class, contributing to type identity | The application loader of the lookup class |
| **Runtime package** | The pair (package name, defining loader) | `("demo.lookup", appLoader)` |
| **Module** | The JPMS module containing the lookup class and the class defined in that context | The unnamed module in the demo |
| **Protection domain** | Protection domain information associated with the class, used by the runtime for corresponding security mechanisms | `lookupClass.getProtectionDomain()` |
| **Linking** | Verification/preparation/resolution according to JVMS rules | After creating the definition, further resolution may still occur later |
| **Initialization** | Execution of `<clinit>` according to active use rules | When calling a static method of the new class |

A normal runtime class/interface is identified by **(binary name, defining loader)**. Having the same name and the same bytecode, if defined by two independent loaders, results in two different runtime types. Conversely, `Lookup.defineClass` **does not create a separate loader**: it defines the class in the lookup class's loader.

### Relationship with Modules

`Lookup.defineClass` is not an arbitrary mechanism to “inject bytecode into any module”. With a valid lookup, the new class is defined in the context of the lookup class, including the corresponding module. When the source runs on a regular classpath, the lookup class belongs to the **unnamed module** of the loader; when running in a named module, JPMS rules, package boundaries, and lookup creation permissions must be checked.

**Being in the same module does not automatically grant all private access rights:** private members belong to the class/nest boundary, not to every class within the module. The new class can use package-private access when valid, but it is not automatically a nestmate of the lookup class simply because it was defined via `defineClass`.

## 3. Why Must MethodHandles.Lookup Be Used?

A `Lookup` object is the context used by the JVM to check permissions when creating method handles and performing certain privileged operations. A `Lookup` carries information about:

- `lookup.lookupClass()`: the class considered the subject of the lookup.
- `lookup.lookupModes()`: the currently held access permissions.
- Where applicable, the module context and restrictions when the lookup has been transformed or had its permissions reduced.

Example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> callerClass = lookup.lookupClass();
boolean canDefine = (lookup.lookupModes()
        & MethodHandles.Lookup.PACKAGE) != 0;
```

This is a snippet; it requires importing `java.lang.invoke.MethodHandles` and running inside a method belonging to a class with appropriate permissions.

`MethodHandles.lookup()` returns a lookup bound to the **actual caller at the call site**. If the method calling `lookup()` is in `demo.lookup.Host`, the lookup class is `demo.lookup.Host`, not whatever class the application intends to define.

**Important condition:** `defineClass` requires `Lookup.PACKAGE` access. `MethodHandles.publicLookup()` only has the corresponding public/unconditional access and cannot be used to define a new class into a specific package.

If an application receives a `Lookup` from another library, **you should not assume** its permissions remain intact: operations such as `lookup.in(target)` or `dropLookupMode(...)` can reduce the modes. Check `lookupClass()`, `lookupModes()`, and the source providing the lookup when designing APIs.

## 4. What Does defineClass(byte[]) Do and Not Do?

According to the Java SE 17 API, `Lookup.defineClass(byte[])`:

1. Accepts the bytecode of a valid class file.
2. Determines the context from the current lookup class.
3. Requires `PACKAGE` access.
4. Requires the defined class to have **the same package name as the lookup class**.
5. Creates the class with the same **ClassLoader, runtime package, and protection domain** as the lookup class, equivalent in terms of definition to the appropriate `ClassLoader.defineClass` rules.
6. **Creates and links** the class, returning the `Class<?>` object.
7. **Does not run the static initializer** of the new class immediately upon calling `defineClass`.

The JVM's internal ordering, checks, and resolution timing follow their own rules. Do not infer that all dependencies of the new class have already been initialized or that all subsequent calls are guaranteed to succeed.

### Capabilities It Does Not Have

- Does not pass a separate binary name like `defineClass("x.y.Z", bytes, ...)` in certain `ClassLoader` overloads. The name is contained inside the bytes.
- Does not let the caller choose a class loader via an argument.
- Does not allow defining a class in a different package from the lookup class.
- Does not automatically open a named module's package to other modules.
- Does not alter `exports`, `opens`, or `requires` of a module descriptor.
- Does not automatically add the class to a nest for private access; that is a separate topic.
- Does not create a **hidden class**; that API is `defineHiddenClass`.
- Does not redefine a binary name that already exists in the same defining loader as a new version.
- Does not create a secure sandbox for bytecode from untrusted sources.

### Why Must `byte[]` Match the Package?

Suppose the lookup class is `demo.lookup.Host`, while the byte array defines `external.plugin.Generated`. Even if the bytes form a valid class file, the call:

```java
lookup.defineClass(externalBytes);
```

will violate the **same package** rule, which the API typically reports with an `IllegalArgumentException` according to the `Lookup.defineClass` contract. This is not a situation where one should try adding `/` characters to the name: the actual class name resides in the class file's constant pool.

## 5. Verified Java 17 Example: Defining a Class from Bytecode Outside the Classpath

The following hands-on example dynamically generates bytecode using `JavaCompiler` and loads a class that is not on the application classpath. The new class name is chosen as `demo.lookup.Generated`, in the **same package** as the host program:

```text
Host code at compile time:
    demo.lookup.LookupDefineDemo  -> out/demo/lookup/LookupDefineDemo.class

Generated.java file created at runtime in a temporary directory:
    demo.lookup.Generated         -> temp/classes/demo/lookup/Generated.class

Host reads Generated.class as byte[]
   -> MethodHandles.lookup().defineClass(bytes)
   -> Class<?> of demo.lookup.Generated
```

There is no need to run `java -cp ...:temp/classes`. The lookup itself defines the new type directly in the host's loader. This characteristic differs from finding a class via a path using `ClassLoader.loadClass`.

### 5.1. Save the Complete Program

Create the file `src/demo/lookup/LookupDefineDemo.java`:

```java
package demo.lookup;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class LookupDefineDemo {
    private static final String INIT_KEY =
            "example.lookup.defineClass.initialized";

    public static void main(String[] args) throws Throwable {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        System.clearProperty(INIT_KEY);
        Path work = Files.createTempDirectory("lookup-define-");

        try {
            Path source = work.resolve(
                    "src/demo/lookup/Generated.java");
            Path foreign = work.resolve(
                    "src/demo/other/Foreign.java");
            Path output = work.resolve("classes");

            Files.createDirectories(source.getParent());
            Files.createDirectories(foreign.getParent());
            Files.createDirectories(output);

            Files.writeString(source, """
                    package demo.lookup;

                    public final class Generated {
                        static {
                            System.setProperty(
                                "example.lookup.defineClass.initialized", "yes");
                        }

                        static String say() {
                            return "Hello, dynamically defined";
                        }
                    }
                    """);

            Files.writeString(foreign, """
                    package demo.other;
                    public final class Foreign { }
                    """);

            int code = compiler.run(null, null, null,
                    "--release", "17", "-encoding", "UTF-8",
                    "-d", output.toString(),
                    source.toString(), foreign.toString());
            if (code != 0) {
                throw new IllegalStateException(
                        "Dynamic compilation failed");
            }

            byte[] localBytes = Files.readAllBytes(
                    output.resolve("demo/lookup/Generated.class"));
            byte[] foreignBytes = Files.readAllBytes(
                    output.resolve("demo/other/Foreign.class"));

            MethodHandles.Lookup lookup = MethodHandles.lookup();

            System.out.println("lookupClass="
                    + (lookup.lookupClass() == LookupDefineDemo.class));
            System.out.println("hasPackageMode="
                    + ((lookup.lookupModes()
                    & MethodHandles.Lookup.PACKAGE) != 0));

            Class<?> generated = lookup.defineClass(localBytes);

            System.out.println("samePackage="
                    + generated.getPackageName().equals(
                            LookupDefineDemo.class.getPackageName()));
            System.out.println("sameLoader="
                    + (generated.getClassLoader()
                            == LookupDefineDemo.class.getClassLoader()));
            System.out.println("sameModule="
                    + (generated.getModule()
                            == LookupDefineDemo.class.getModule()));
            System.out.println("sameProtectionDomain="
                    + (generated.getProtectionDomain()
                            == LookupDefineDemo.class.getProtectionDomain()));
            System.out.println("notInitializedAfterDefine="
                    + (System.getProperty(INIT_KEY) == null));

            MethodHandle handle = lookup.findStatic(
                    generated, "say", MethodType.methodType(String.class));

            System.out.println("call="
                    + (String) handle.invokeExact());
            System.out.println("initializedAfterCall="
                    + "yes".equals(System.getProperty(INIT_KEY)));

            try {
                MethodHandles.publicLookup().defineClass(localBytes);
                System.out.println("publicLookup=unexpected");
            } catch (IllegalAccessException expected) {
                System.out.println("publicLookup=IllegalAccessException");
            }

            try {
                lookup.defineClass(foreignBytes);
                System.out.println("otherPackage=unexpected");
            } catch (IllegalArgumentException expected) {
                System.out.println("otherPackage=IllegalArgumentException");
            }

            try {
                lookup.defineClass(localBytes);
                System.out.println("duplicate=unexpected");
            } catch (LinkageError expected) {
                System.out.println("duplicate=LinkageError");
            }
        } finally {
            System.clearProperty(INIT_KEY);
            try (Stream<Path> stream = Files.walk(work)) {
                for (Path p :
                        stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

**Command to run**, from the directory containing `src`:

```bash
javac --release 17 -d out src/demo/lookup/LookupDefineDemo.java
java -cp out demo.lookup.LookupDefineDemo
```

There is no need to manually compile `Generated.java` or `Foreign.java`: these two files are temporarily created and compiled at runtime by the program via `JavaCompiler`. A **full JDK** (containing the `jdk.compiler` module) is required, not just a minimal runtime image without the compiler.

### 5.2. Exact Stdout

The program above was compiled with JDK 21 targeting `--release 17` and ran successfully. The obtained stdout:

```text
lookupClass=true
hasPackageMode=true
samePackage=true
sameLoader=true
sameModule=true
sameProtectionDomain=true
notInitializedAfterDefine=true
call=Hello, dynamically defined
initializedAfterCall=true
publicLookup=IllegalAccessException
otherPackage=IllegalArgumentException
duplicate=LinkageError
```

The result is constructed to avoid depending on class/JAR listing order or GC. If the filesystem does not allow creating temporary files or the compiler is unavailable, the program reports a clear error instead of pretending to have the same output.

### 5.3. Reading the Results in Context

**`lookupClass=true`:** `MethodHandles.lookup()` is called inside `LookupDefineDemo.main`, so the lookup class is `LookupDefineDemo`, not `Generated`.

**`hasPackageMode=true`:** the lookup created by the calling class itself has `PACKAGE` permission, which is a prerequisite for `defineClass`.

**`samePackage=true`:** the bytes define a class in `demo.lookup`, matching the package of the lookup class. If the bytes carry the name `demo.other.Foreign`, this condition is not met.

**`sameLoader=true`:** the new class is defined by the same loader as `LookupDefineDemo`. No second custom ClassLoader is created.

**`sameModule=true`:** both the host and the new class belong to the same module context. In the demo run via the classpath, both belong to the unnamed module of the application loader.

**`sameProtectionDomain=true`:** the new class has the same protection domain as the lookup class, not a domain determined by data from the filesystem. This is also why a high-privilege lookup must not be used to define unverified bytecode.

**`notInitializedAfterDefine=true`:** when `defineClass(localBytes)` returns, the static block of `Generated` has not yet run, so the system property has not been set.

**`call=Hello, dynamically defined` and `initializedAfterCall=true`:** calling the static method `say()` via a method handle is an active use; the JVM initializes the class before the call, and the static block sets the system property.

**`publicLookup=IllegalAccessException`:** the public lookup does not have `PACKAGE` mode. Even though the bytes are in the correct package, the lack of lookup permission causes the definition to be rejected.

**`otherPackage=IllegalArgumentException`:** the bytes of `demo.other.Foreign` are not in the same package as `LookupDefineDemo`. The API rejects this class file.

**`duplicate=LinkageError`:** a definition of `demo.lookup.Generated` already exists in that loader. Calling `defineClass` again with the same binary name does not create a “version 2” of the class in the same loader.

### 5.4. Why Use MethodHandle to Call the Static Method?

The `Generated.say()` method has **package-private** visibility (it is not declared `public`). The host lookup belonging to the same runtime package has appropriate permissions and can therefore obtain the handle:

```java
MethodHandle handle = lookup.findStatic(
        generated, "say", MethodType.methodType(String.class));
```

This is a snippet from the full program. The `invokeExact()` call invokes the method with the exact `()String` signature and triggers initialization before execution.

It simultaneously illustrates a practical benefit: the class is defined **in the host lookup's package/loader**, allowing integration with intentionally package-private APIs instead of forcing all internal APIs to be made public. However, you still must control who receives a Lookup with `PACKAGE` permission.

## 6. How Strict Is the “Same Package” Rule?

For example, with the host in `demo.lookup`:

| Actual Class Name in Bytes | Result for the Lookup of `demo.lookup.LookupDefineDemo` |
| --- | --- |
| `demo.lookup.Generated` | Valid regarding the **package condition** if the bytes are valid, not previously defined, and lookup permissions are sufficient |
| `demo.lookup.Helper$Nested` | Belongs to package `demo.lookup`; bytes and other conditions still need to be checked |
| `demo.other.Foreign` | Different package, `IllegalArgumentException` per the API |
| `java.lang.FakeString` | Different package; this lookup cannot be used to intrude into core Java packages |
| Corrupted class file or not a class/interface | Invalid; may throw `ClassFormatError`/`IllegalArgumentException` depending on the error |
| Class with the same binary name already defined by the loader | Linkage conflict; does not automatically overwrite the old class |

**Do not check the package solely by file path**. A class's package is determined from the binary name encoded in the bytecode, not by which directory the file is placed in. Renaming `Foreign.class` to `Generated.class` does not change the package contained in the class file.

### Runtime Package Depends on the Defining Loader

Two classes with the same package string but different loaders belong to two different runtime packages. If a real application needs to define a class in the runtime package of a class in a plugin loader, obtain a **valid Lookup of a class belonging to that loader/plugin itself** through an authorized mechanism, rather than passing bytecode into the host's lookup and expecting the class to automatically “move” to the plugin loader.

Example:

```text
HostLoader defines demo.lookup.Host
PluginLoader defines plugin.internal.Anchor

Host lookup -> defines a class belonging to demo.lookup + HostLoader
Plugin anchor lookup -> defines a class belonging to plugin.internal + PluginLoader
```

This is a conceptual model; obtaining the plugin anchor lookup also requires appropriate permission/module conditions. Having two class loaders does not mean you automatically have the right to obtain a PACKAGE lookup for both.

## 7. Lookup Permissions and Ways to Create Context

### 7.1. MethodHandles.lookup()

`MethodHandles.lookup()` creates a Lookup from the actual caller class. If called inside the `pkg.Anchor` class, it can have full permissions in Anchor's appropriate context. This is the simplest option when code **within that package** proactively decides to generate a class:

```java
final class Anchor {
    static Class<?> defineTrusted(byte[] bytes)
            throws IllegalAccessException {
        return MethodHandles.lookup().defineClass(bytes);
    }
}
```

This is an **illustrative snippet**; it requires importing `MethodHandles` and compiling within the current package. An API like `defineTrusted` should only accept bytes from trusted sources and perform the necessary validity checks.

### 7.2. MethodHandles.publicLookup()

`publicLookup()` is designed for appropriate public members and **does not have PACKAGE mode**, so it cannot call `defineClass` successfully. It is not a “free class-loading Lookup” just because it has public in its name.

### 7.3. privateLookupIn(targetClass, callerLookup)

`MethodHandles.privateLookupIn(targetClass, callerLookup)` can create a Lookup to the target class when the caller has **sufficient permissions** and the access/module relationship permits it. For named modules, the condition that the module/package is properly opened (*opens*) is critical. Merely having the target Class object does not allow obtaining all of its permissions.

One architectural approach:

1. The host defines a public API to ask the plugin to generate the class itself.
2. The plugin has an anchor class in the exact package and loader where the new class needs to reside.
3. Code is granted controlled use of the PACKAGE lookup.
4. The new lookup only defines **classes in the same package** from verified bytes.
5. The host does not need to try opening `java.base` or using reflective access against JPMS policies.

**Capability principle:** A Lookup with `PACKAGE` mode is a delegatable form of privilege. Do not distribute that Lookup to arbitrary plugins or to data from the network; the recipient can use it to define new classes in the lookup class's valid namespace.

### 7.4. Lookup.in and dropLookupMode

These methods can create a Lookup with lower privileges. If the `PACKAGE` privilege is lost, `defineClass` will no longer be permitted:

```java
MethodHandles.Lookup restricted =
        MethodHandles.lookup().dropLookupMode(
                MethodHandles.Lookup.PACKAGE);
```

This is a snippet; calling `restricted.defineClass(bytes)` will lack sufficient PACKAGE privilege and may throw `IllegalAccessException`. Do not label a lookup as “full privilege” merely because the original object came from trusted code.

## 8. Comparing Lookup.defineClass with ClassLoader.defineClass

There are two distinct approaches to defining classes in terms of permissions and configurability.

| Criterion | `Lookup.defineClass(bytes)` | `ClassLoader.defineClass(name, bytes, ...)` |
| --- | --- | --- |
| Caller | Code holding an appropriate `Lookup` | A `ClassLoader` subclass/logic authorized to call the protected API |
| Loader selection | **The lookup class's loader** | The loader receiving the `defineClass` call |
| Package selection | **Must be the same package as the lookup class** | Based on bytes/name and the loader's policy/namespace |
| Protection domain | **Same domain as the lookup class** | Has overloads allowing `ProtectionDomain` to be specified |
| Required privilege | `Lookup.PACKAGE` | Security/JVM rules of ClassLoader and the protected method |
| Package-private integration | Possible within the same runtime package | If defined by a different loader, they do not form the same runtime package |
| Class file bytes | Requires valid bytes | Requires valid bytes |
| Static initialization upon definition? | **No** | `defineClass` is not itself a `<clinit>` invocation |
| Duplicate binary name definition | Does not allow overwriting the class | Does not allow overwriting the class |
| Hidden class? | No | No; a separate API is needed for hidden classes |

### When Should You Use Lookup.defineClass?

Suitable when:

- Generating a new helper class to **collaborate with existing code in that same package**.
- Wanting to use package-private members in a library/runtime that has proactively granted a valid lookup.
- No new ClassLoader needs to be created and the class does not need to be placed in a different package.
- Bytecode is produced by a trusted pipeline with clear naming/versioning rules.
- Wanting to define a **named, ordinary class** that can be processed by standard reflection APIs.

### When Should You Use a Custom ClassLoader?

Better suited when:

- Classes need to be defined across **multiple packages** from a directory, JAR, database, or separate bytecode repository.
- **Library version isolation** is needed, or unloading a group of classes along an independent loader lifecycle.
- Custom parent/child delegation policies, package ownership, and resource lookup are required.
- Plugin loading needs to be managed independently of the host's loader/module.
- Control over protection domains/code sources is needed via a mechanism designed inside the custom loader.

**Do not replace a custom ClassLoader with a host lookup and expect plugins to be isolated.** If all new classes are defined together in the host loader, they are tied to the host lifecycle, with no per-version loader isolation.

## 9. Class Definition, Linking, and Class Initialization Are Three Distinct Steps

Relationship:

```text
valid byte[]
    |
    v
Lookup.defineClass(bytes)
    |
    +-- creates runtime class
    +-- links per API/JVMS contract
    +-- returns Class<?>
    |
    +-- does not automatically run static initializer
            |
            v
later active use (e.g., calling a static method)
    |
    +-- class initialization occurs per JLS rules
```

The JVM may perform parts of verification/resolution at different times, but **calling defineClass does not automatically run the static initializer**. This is why the example prints:

```text
notInitializedAfterDefine=true
...
initializedAfterCall=true
```

Not every operation holding a `Class<?>` is an active use: inspecting the class name, defining loader, or module normally does not equate to calling a constructor or static method. However, certain other reflective/API operations may require initialization under their own contracts; the specific method must be examined.

### What If the Static Initializer Throws an Error?

If `<clinit>` throws an exception, subsequent calls may report `ExceptionInInitializerError` or `NoClassDefFoundError` associated with the class that failed initialization, rather than meaning `Lookup.defineClass` “failed to create the class”. When debugging, separate **definition/linkage** errors from **initialization** errors.

## 10. Exceptions to Know

| Error / Exception | When to Consider It | How to Handle It |
| --- | --- | --- |
| `IllegalAccessException` | The Lookup lacks `PACKAGE` mode | Create/obtain a Lookup with proper permissions at the package anchor; do not use publicLookup |
| `IllegalArgumentException` | Bytes define a class in a different package or not a class/interface per API rules | Check the actual binary name in the class file and the class kind |
| `ClassFormatError` | Not a structurally valid class file | Check the byte source, format, transformer, and compiler |
| `VerifyError` | The JVM cannot verify the bytecode | Check the generator/transformer, descriptors, and stack map frames |
| `UnsupportedClassVersionError` | The class file requires a newer JVM version | Check `javac --release` and the runtime version |
| `LinkageError` | Duplicate definition, linking constraint, or other invalid dependency | Check naming/loader/dependencies and the full root cause |
| `NullPointerException` | `bytes == null` | Do not pass missing data |
| `SecurityException` | A legacy SecurityManager is present and the corresponding permission check is denied | Review the runtime policy; do not swallow the exception |
| `ExceptionInInitializerError` | The class initializer throws an error upon active use | Separate this from the `defineClass` call site |
| `NoClassDefFoundError` | A dependency is unavailable, prior class state failed, or wrong name in a related scenario | Read the cause chain and the timing of the error |

**Do not broadly catch all `Throwable` and convert them to `ClassNotFoundException`.** `LinkageError`, `VerifyError`, or `ClassFormatError` reflect problems different from “no class found”. Masking errors makes debugging and handling JVM state unsafe.

### Duplicate Definition in the Same Loader

Each normal runtime class identity is (binary name, defining loader). If `demo.lookup.Generated` has already been defined, calling `lookup.defineClass(localBytes)` again for the same name and loader will not create a second copy. The example detects `LinkageError` and prints `duplicate=LinkageError`.

A different approach is needed for **hot reload**: design a new ClassLoader or an appropriate JVM instrumentation mechanism, rather than calling `defineClass` again into the same loader. Do not equate instrumentation's redefine/retransform APIs with `Lookup.defineClass`.

## 11. Comparing with defineHiddenClass

Since Java 15, `Lookup.defineHiddenClass(bytes, initialize, options...)` serves special classes that cannot be looked up by the normal binary name of a named class. This is a different approach from `defineClass`.

| Characteristic | `defineClass` | `defineHiddenClass` |
| --- | --- | --- |
| Class kind | Named, ordinary class | Hidden class with special rules |
| Return value | `Class<?>` | `MethodHandles.Lookup` on the hidden class |
| Lookup requirement | `PACKAGE` mode | Full-privilege access per the API |
| Initialization parameter | No; define does not run the initializer | Has a boolean `initialize` parameter |
| Naming/lookup | Has a normal binary name | Not discoverable via the standard `ClassLoader.loadClass(name)` mechanism |
| Optional nestmate | No corresponding class option | The `NESTMATE` option can create a nest relationship per the API |
| Strength/lifetime option | Follows regular class/loader rules | `STRONG` option for hidden classes under its own rules |
| Purpose | Named helper class in the runtime package | Fine-grained runtime-generated implementations, lambda-like internals |

**Do not call `defineClass` with the bytes of an ordinary class and call it a hidden class.** The two APIs have different contracts regarding naming, initialization, privilege, and lifecycle. Some generated-implementation use cases that do not want to occupy a binary name long-term may be better suited to hidden classes, but you must understand nest/module access and class data APIs.

### Does a Hidden Class Mean “No Memory Leaks Are Possible”?

No. A hidden class can still be retained by objects, method handles, `Class<?>` references, registries, or other references. Reclamation depends on reachability/JVM mechanisms and the relevant options; there is no API that makes it “disappear immediately”. Although a class loader can be long-lived, hidden classes are generally designed for more flexible lifecycle scenarios than regular named classes, yet they do not replace cleaning up external resources.

## 12. Security and Bytecode Integrity

A lookup with PACKAGE permission is a powerful **capability**: it allows defining new classes into the lookup class's runtime namespace with the corresponding protection domain. Therefore, both the **source of the bytes** and **whoever holds the lookup** must be controlled.

### Input Bytecode Verification Workflow

1. **Trusted source constraint:** an internal compiler or an artifact signed/built by a verified pipeline.
2. **Namespace constraint:** the new class belongs to the expected package. The API performs the final check, but the application should have clear validation and naming policies.
3. **Size limits:** do not read excessively large byte arrays or an unlimited number of classes.
4. **Class file header check:** magic `CA FE BA BE` and the major version are preliminary checks and **do not prove safety**.
5. **Integrity verification:** verify SHA-256 or a signature against metadata from a trusted source. A digest obtained from the same untrusted source does not verify the publisher.
6. **Bytecode verification:** rely on the JVM verifier and appropriate bytecode generation/transformation tools; do not assume safety just because a class has the magic header.
7. **Dependency graph:** the new class may reference superclasses/interfaces or libraries outside the host's loader/graph; they must be loaded/linked properly.
8. **Naming collision:** use a naming scheme that guarantees no collision with already defined classes; do not attempt to redefine the same binary name in one loader.
9. **Audit:** log the binary name, artifact fingerprint, lookup class, loader identity, and module; avoid logging raw secrets/bytecode.
10. **Execution privileges:** a valid class can still call any API the process is permitted to call; verify the logic or use process isolation when running untrusted code.

**The bytecode verifier is not a sandbox.** Defining the class with the same protection domain as the host can make risks more severe if the host grants `Lookup.defineClass` access to untrusted code or bytes.

### What Not to Do

```java
// Anti-pattern illustration: do not expose as a public API
public Class<?> defineAnyUserBytes(byte[] userBytes)
        throws IllegalAccessException {
    return MethodHandles.lookup().defineClass(userBytes);
}
```

This is an **anti-pattern snippet**, not production sample code. Even though the method has not crossed package boundaries, it turns the privileged class's lookup context into a gateway for defining classes from untrusted input. If plugin extensibility is needed, create a dedicated permission architecture and inspect artifacts more thoroughly.

## 13. Resolving Issues in a Named Module

With JPMS, a class in a named module does not just have a class loader and a runtime package; it also belongs to a module in the runtime graph. When you want to define a new class in the same package of a named module, you should let an **anchor class of that module/package itself** provide the lookup through an authorized mechanism.

Conceptual example:

```java
module app.codegen {
    exports app.codegen.api;
    // app.codegen.internal is not automatically exported or opened.
}
```

If `app.codegen.internal.Anchor` wants to generate a class in `app.codegen.internal`, it can use a lookup properly created inside Anchor. Another module does not automatically gain PACKAGE access to this package merely by declaring `requires app.codegen;` or by knowing the package name string.

### privateLookupIn and opens

To obtain a private lookup to a class belonging to another module, `MethodHandles.privateLookupIn` must respect module readability and whether the target package is properly **opened** to the caller's module. A package that only `exports` its public API does not mean code outside the module can create a privileged lookup into every class in that package.

In practice, prefer having the owning module **proactively provide a narrow capability** to a trusted code generation tool, rather than adding multiple `--add-opens` flags just to “bypass” JPMS encapsulation.

### Same Module Does Not Replace PACKAGE Access

Even when the lookup class and the class bytecode can belong to the same module, `defineClass` still requires:
- The lookup has `PACKAGE` mode;
- The binary name in the bytes has the same package as the lookup class;
- A valid class file;
- No definition/linkage conflict.

Do not infer that just because a module is resolved, a lookup is permitted to define classes in every package within that module.

## 14. Diagnosing When defineClass Fails

Practical workflow:

1. **Identify the actual lookup class.** Log `lookup.lookupClass().getName()` and `lookup.lookupClass().getClassLoader()`.
2. **Read the lookup modes.** Check `PACKAGE` permission with a bitmask; do not rely on a variable name like `trustedLookup`.
3. **Verify the bytes.** Class file version, binary name, magic, checksum, source artifact, and bytecode transformations.
4. **Compare the package** in the class bytes with `lookup.lookupClass().getPackageName()`.
5. **Check whether the class has already been defined.** One loader cannot create two named classes with the same binary name by repeating defineClass.
6. **Distinguish access, format, verification, linking, and initialization errors.** Each category requires a different solution.
7. **If using JPMS:** inspect the module of the lookup class, the caller, and package-opening rules when obtaining the Lookup.
8. **If plugins use multiple loaders:** determine the loader that actually defines the lookup class; do not confuse it with the initiating loader/TCCL.
9. **If encountering memory pressure:** a named class defined by a long-lived loader is not “removed” merely by dropping a local Class<?> reference. Evaluate the loader lifecycle and code generation volume.
10. **Do not catch Throwable** to hide serious errors and then create a fallback class with a mismatched ABI.

### Useful JDK Tools

For bytecode on disk:

```bash
javap -verbose -classpath generated/classes demo.lookup.Generated
```

This is an **illustrative command** for a real artifact: replace the classpath root and class name according to your environment. `javap -verbose` displays the major version, constant pool, flags, methods, and the binary name stored in the class file. It does not verify the generator's full security policy.

For an application with appropriate class-loading logging:

```bash
java -Xlog:class+load=info -cp out demo.lookup.LookupDefineDemo
```

Class-load events can help show which classes the JVM defines/loads, though they do not always display a file source in the same way as URLClassLoader when bytes are supplied directly to a Lookup. Combine this with application logs of the fingerprint/lookup class for diagnosis.

### Snippet for Printing Context After Define

```java
static void printType(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
    System.out.println("package=" + type.getPackageName());
    System.out.println("domain=" + type.getProtectionDomain());
}
```

This is a **helper method**, not a standalone program. When printing the protection domain or code source, avoid exposing sensitive information in production logs.

## 15. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “Any Lookup object can call defineClass.” | It must have `PACKAGE` mode and match the lookup class's package. |
| “publicLookup can generate public classes in any package.” | No; publicLookup does not have PACKAGE access. |
| “defineClass(bytes) chooses the class name from a filename variable.” | The name is inside the class file bytes; the file name does not determine it. |
| “Lookup.defineClass creates a new ClassLoader.” | No; it uses the lookup class's loader. |
| “The same package string in two loaders is the same runtime package.” | No; the runtime package also considers the defining loader. |
| “A newly defined class runs its static block immediately.” | No; defineClass does not automatically run the initializer. |
| “An existing class can be updated by calling defineClass a second time.” | No; a duplicate binary name in the same loader causes a linkage conflict. |
| “Having PACKAGE access means accessing all private members of every class in the same package.” | No; private/nest access has separate constraints. |
| “A host lookup can arbitrarily define classes in a plugin's loader.” | No; the loader is bound to the lookup class. |
| “If a named module exports a package, external code has full privateLookupIn access.” | No; opens/readability and API conditions must be checked. |
| “ClassFormatError means the bytes are malicious.” | It only means the class structure is invalid; it does not evaluate the code's intent. |
| “A class that passes the verifier is safe to run.” | No; permissions, trust, and side effects must still be controlled. |
| “Lookup.defineClass is the same as defineHiddenClass.” | They differ in naming, privilege, initialization, and lifecycle. |
| “The JVM automatically collects every named class when the local Class<?> becomes null.” | No; class unloading depends on the defining loader's reachability and GC. |

## 16. Self-Check Exercises

**Question 1.** A Lookup is created inside `demo.codegen.Anchor`, and the bytes contain `demo.codegen.Generated`. If the Lookup has PACKAGE mode and valid bytecode, which loader does the new class use?

**Answer:** The defining loader of `demo.codegen.Anchor`; it shares the same runtime package and protection domain as the lookup class.

**Question 2.** The bytes contain `other.pkg.Generated`, while the lookup class is in `demo.codegen`. What happens?

**Answer:** Because it is in a different package, `Lookup.defineClass` throws `IllegalArgumentException` per the API contract instead of silently changing the package.

**Question 3.** Why does `MethodHandles.publicLookup().defineClass(bytes)` fail?

**Answer:** The public lookup does not have `PACKAGE` access; the API throws `IllegalAccessException`.

**Question 4.** `defineClass` returns Class<?> successfully. Has the static block in the new class run yet?

**Answer:** Not yet solely due to defineClass. Initialization takes place later according to active use rules, such as the first invocation of an appropriate static method.

**Question 5.** The same bytes are used with two Lookups whose lookup classes were defined by two different defining loaders. Are the two resulting Class<?> instances the same runtime class?

**Answer:** No, if each loader defines it independently. Runtime class identity is (binary name, defining loader).

**Question 6.** Can `Lookup.defineClass` be used instead of a custom URLClassLoader to isolate two library versions with colliding binary names in the same host loader?

**Answer:** No. A lookup in the same host loader does not provide loader isolation; two definitions with the same name in one defining loader conflict.

**Question 7.** To create a hidden class that cannot be looked up by a normal name, which API is more suitable?

**Answer:** `Lookup.defineHiddenClass(...)`, subject to full privilege, the same package, and the corresponding hidden class rules.

**Question 8.** In a named module, does merely `exports`-ing the target package guarantee `privateLookupIn` from every other module?

**Answer:** No. One must consider `opens`, caller privileges, and module readability per the MethodHandles API.

**Question 9.** If `Generated.say()` fails due to a missing dependency after the class was defined, does that mean `defineClass` never created the class?

**Answer:** No. Class definition can succeed while resolution/initialization or a subsequent call fails.

**Question 10.** Why should a Lookup with PACKAGE mode not be exposed to unverified plugins?

**Answer:** It allows defining new classes in the lookup class's runtime package/protection domain. This is a powerful capability, not a bytecode safety filter.

## 17. Checklist for Implementing Dynamic Class Generation

- [ ] Clearly identify the lookup class and the loader/module owning the namespace.
- [ ] Only create/delegate a Lookup with `PACKAGE` access to trusted components.
- [ ] Check the binary name/package in the bytes; avoid conflicts with already defined names.
- [ ] Verify the artifact/generator source, size, class version, and appropriate integrity.
- [ ] Do not treat the magic header or verifier as a sandbox.
- [ ] Use a separate classloader if isolation, reloading, or a different package is required.
- [ ] Distinguish `defineClass`, `defineHiddenClass`, and `ClassLoader.defineClass`.
- [ ] On JPMS, check readability/exports/opens when obtaining a Lookup into the target package.
- [ ] Keep in mind that defineClass does not automatically run the static initializer; control active use.
- [ ] Catch/log errors by the proper category: access, format, verification, linkage, initialization.
- [ ] Limit the number of classes generated in long-lived loaders; monitor Metaspace and caches.
- [ ] Log the lookup class, loader identity, module, binary name, and appropriate errors.
- [ ] Do not attempt to redefine a named class of the same name using the existing lookup.
- [ ] For untrusted bytecode, use an appropriate permission model or process isolation.

## 18. Conclusion and Official Documentation

`MethodHandles.Lookup.defineClass(byte[])` is not simply “read byte[] and create a class”. It is an API that **defines a class within a delegated context**: the new class must be named in the **same package** as the lookup class; use the **same defining ClassLoader, runtime package, and protection domain**; the lookup must have `PACKAGE` access; and the **class initializer has not yet run** after the defineClass call.

It is suitable for generating named helper classes that collaborate with an existing package. When you need a separate namespace, multiple packages, isolation, or hot reload, consider a custom ClassLoader. When you need a hidden class, use the corresponding hidden-class API. Regardless of the choice, the JVM still requires a valid class file, and code execution must adhere to the application's trust model.

### Reference Documentation

- Java SE 17 `MethodHandles.Lookup` — `defineClass`, `defineHiddenClass`, lookup modes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17 `MethodHandles` — `lookup()` and `privateLookupIn(...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 `ClassLoader` — `defineClass` and delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JVMS 17 §4 — The class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS 17 §5 — Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JLS 17 §12.4 — Initialization of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- JLS 17 §12.7 — Unloading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
