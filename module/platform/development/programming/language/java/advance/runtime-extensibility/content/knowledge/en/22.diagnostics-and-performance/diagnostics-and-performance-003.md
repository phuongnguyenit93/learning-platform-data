# Identifying NoSuchMethodError, AbstractMethodError, and UnsupportedClassVersionError

## 1. Why Do These Three Errors Frequently Appear in Plugin Systems?

In a runtime-extensibility architecture, plugins are typically compiled and packaged separately from the host application. A plugin's source code may be completely valid at build time, yet at runtime the JVM loads **a different class/API version** or runs on **too old a JDK**. In such cases, the failure does not necessarily occur at application startup, and may only blow up the first time a method is invoked or a class is defined.

The three key errors:

| Error | Core Meaning | Common Causes |
|---|---|---|
| `NoSuchMethodError` | A compiled call references a method that the runtime cannot find by the required symbolic reference | Runtime API/library lacks a method with the exact name and descriptor |
| `AbstractMethodError` | The runtime attempts to invoke a method needing a concrete implementation, but the target method remains abstract or lacks a matching implementation | An older provider does not implement a method from a newer interface/API |
| `UnsupportedClassVersionError` | The JVM cannot read the requested class-file version | Plugin was built with a newer Java version than the running JVM, or the class file has an unsupported version |

All three belong to the `LinkageError` family (directly or via `IncompatibleClassChangeError`), rather than ordinary Java syntax errors. Specifically, `NoSuchMethodError` and `AbstractMethodError` both extend `IncompatibleClassChangeError`; `UnsupportedClassVersionError` extends `ClassFormatError`.

**Distinguishing from business exceptions:** `try/catch (Exception)` will not catch them because `LinkageError` extends `Error`. In a plugin host, compatibility should be detected before publishing a plugin; at an isolation boundary you can log/isolate a linkage incident, but you must not catch every `Error` and carry on as if nothing happened.

## 2. Compilation Layer Differs from Linking/Runtime Layer

```text
Plugin source + API v2  --javac--> plugin.jar
                                    |
                                    v
                    Runtime host + API v1 / old Java
                                    |
                    class loading / verification / resolution
                                    |
                  invoke bytecode / resolve symbolic method
                                    |
                           LinkageError
```

The Java compiler checks methods against the classes on the **compile classpath/module path**. At runtime, the JVM relies on the **runtime classpath/module path and class loader graph**. The two environments can diverge because:

- The build used a newer API while deployment packaged an older API.
- The plugin bundles its own library, causing duplicate classes or loader differences.
- Shading/fat JARs dropped or overwrote classes.
- The plugin's module layer reads an API from a parent layer that is not the expected version.
- Hot reload retained an old instance while publishing a new contract.
- The build used `--release` or a bytecode target incompatible with the runtime.

Do not conclude "the compiler is broken" just because the source compiles cleanly while runtime hits a linkage error. The root cause usually lies in **how artifacts are combined at runtime**.

## 3. NoSuchMethodError: Method Absent at Runtime

Example stack trace:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.GreetingService.greet(java.lang.String)'
    at com.example.plugin.GreetingPlugin.run(GreetingPlugin.java:12)
```

The JVM is attempting to resolve a call to a method with a specific name and **bytecode descriptor**. The descriptor includes parameter types and the return type; changing the return type alone can break binary compatibility even when the method name and parameter list look nearly identical in source.

Common causes:

1. **New method does not yet exist at runtime**: the plugin was built against API v2 containing `greet(String)`, while the host supplies API v1 without it.
2. **Signature change**: `greet(String)` changed to `greet(Object)` or changed return type without preserving a corresponding binary bridge.
3. **Dependency version shift**: the runtime library lacks an overload that the plugin bytecode called.
4. **Wrong class loaded**: same FQCN, but loaded from a different JAR/version by a class loader.

`NoSuchMethodError` does not always mean "there is no method with that name at all". Compare **name, parameter types, return type, and the class actually loaded**. Generic erasure, bridge methods, static/instance changes, and covariant return types can also alter binary method descriptors.

### How to Diagnose

- Read the top line of the stack trace: owner class, method name, parameters, and return type requested by the JVM.
- Locate the class with that owner in the actual runtime artifact, not merely in the source repository.
- Use `javap -s -p` to inspect method descriptors:

```bash
javap -classpath runtime-api.jar -s -p com.example.api.GreetingService
```

- Compare against the API artifact used at compile time.
- Enable JVM class loading logs when needed:

```bash
java -Xlog:class+load=info -jar host.jar
```

- Inspect the dependency tree, classpath/module path, class loaders, shaded JARs, and deployed versions.

**Root fix:** align the runtime API so it is compatible with the plugin bytecode, or rebuild the plugin against the API supported by the host. Editing source without rebuilding and deploying the right artifacts will not resolve the mismatch.

## 4. AbstractMethodError: Call Issued Without a Valid Implementation

Example scenario:

**API v1**:

```java
public interface Processor {
    String process(String input);
}
```

An older plugin implements `process`. Later, **API v2** adds:

```java
public interface Processor {
    String process(String input);
    String description();
}
```

A plugin compiled against API v1 can still be loaded in an API v2 environment, but if the host calls `description()` on the old instance, the runtime can throw `AbstractMethodError`. The old implementation class has no bytecode for the new method; Java does not re-run the plugin's compiler when the host deploys.

The error message typically indicates that the receiver class neither defines nor inherits a suitable implementation for an abstract method the JVM must execute.

Notes:

- Adding an abstract method to an interface can cause older implementations to fail **when the new method is called**.
- A `default` method can sometimes preserve backward compatibility, though you must check for conflicts between interfaces and new semantics.
- Changing abstract/concrete methods, hierarchies, bridge methods, or dependency versions can lead to various linkage errors.
- Do not assume every interface change is guaranteed to throw `AbstractMethodError`; it depends on the call site and bytecode.

### How to Diagnose

1. Identify the **runtime receiver class** and the invoked method from the stack trace.
2. Check which interface/superclass the JVM actually loaded at runtime.
3. Run `javap -p -s` against the plugin JAR to inspect the actual implementation.
4. Compare with the plugin's compile-time API and the API used by the host.
5. Run contract tests: instantiate the plugin and invoke all required service interface methods before registering the plugin.

**Root fix:** rebuild the plugin to implement the full new contract, or maintain a backward-compatible API/adapter with explicit design. The host should not wait until a live request arrives to invoke a newly required method.

## 5. UnsupportedClassVersionError: Class File Newer Than the JVM

Every `.class` file has a class-file major/minor version. Java 17 uses **major version 61**; Java 21 uses **major version 65**. A class built for Java 21 generally cannot be defined by a Java 17 JVM.

Example error:

```text
java.lang.UnsupportedClassVersionError:
  com/example/plugin/ReportPlugin has been compiled by a more recent
  version of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes class file
  versions up to 61.0
```

Reference table:

| Java release | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Do not infer the bytecode target solely from the JDK used to run `javac`: modern compilers can emit bytecode for older versions via `--release`. Conversely, a class with a supported major version can still fail when calling an API absent from the runtime; class-file compatibility and API compatibility are two separate problems.

### How to Fix

- Check `java -version` **inside the exact process/container running the host**.
- Check `javac -version` and build configuration such as Maven's `maven.compiler.release` or Gradle's Java toolchain.
- Inspect the actual artifact bytecode with `javap -verbose`:

```bash
javap -verbose -classpath plugin.jar com.example.plugin.ReportPlugin
```

Look for `major version: ...`. If the Java runtime is too old, upgrade the runtime JDK or rebuild the plugin with an appropriate `--release` if source and dependencies allow.

```bash
javac --release 17 -d out src/com/example/plugin/ReportPlugin.java
```

This snippet assumes the source path exists. `--release 17` restricts the language level and public Java APIs to Java 17; it does not automatically guarantee that all third-party runtime libraries are compatible or that plugin code behaves identically in every environment.

## 6. Java 17+ Demo Reproducing NoSuchMethodError with Two API JARs

The example includes API v1, API v2, and a client compiled against v2 but executed against v1.

Structure:

```text
demo/
├── v1/api/Api.java
├── v2/api/Api.java
└── client/Client.java
```

**`v1/api/Api.java`**:

```java
package api;
public class Api {
    public String hello() { return "v1"; }
}
```

**`v2/api/Api.java`**:

```java
package api;
public class Api {
    public String hello() { return "v2"; }
    public String newMethod() { return "new"; }
}
```

**`client/Client.java`**:

```java
import api.Api;

public class Client {
    public static void main(String[] args) {
        System.out.println(new Api().newMethod());
    }
}
```

From the `demo` directory, run (POSIX shell):

```bash
javac -d out/v1 v1/api/Api.java
javac -d out/v2 v2/api/Api.java
jar --create --file api-v1.jar -C out/v1 .
jar --create --file api-v2.jar -C out/v2 .
javac -cp api-v2.jar -d out/client client/Client.java
java -cp out/client:api-v1.jar Client
```

On Windows, use `;` instead of `:` as the classpath separator.

When running with `api-v1.jar`, the JVM loads an `api.Api` class lacking `newMethod()`. The result is `NoSuchMethodError`, with a message similar to:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String api.Api.newMethod()'
    at Client.main(Client.java:5)
```

Exact line numbers/formatting depend on the compiler/JDK, but the error type and symbolic reference `api.Api.newMethod():String` are the core focus here.

If you switch the runtime JAR to `api-v2.jar`:

```bash
java -cp out/client:api-v2.jar Client
```

Stdout:

```text
new
```

Lesson: **a client that compiles cleanly does not guarantee a matching runtime API**.

## 7. Java 17+ Demo Reproducing AbstractMethodError

Using the same separate-build setup.

**`v1/api/Action.java`**:

```java
package api;
public interface Action {
    String execute();
}
```

**`v1/impl/OldAction.java`**:

```java
package impl;
import api.Action;
public class OldAction implements Action {
    public String execute() { return "done"; }
}
```

**`v2/api/Action.java`**:

```java
package api;
public interface Action {
    String execute();
    String description();
}
```

**`client/TestAction.java`**:

```java
import api.Action;
import impl.OldAction;

public class TestAction {
    public static void main(String[] args) {
        Action action = new OldAction();
        System.out.println(action.description());
    }
}
```

In a dedicated demo directory with the structure above, run:

```bash
javac -d out/v1 v1/api/Action.java v1/impl/OldAction.java
javac -d out/v2 v2/api/Action.java
javac -cp out/v2:out/v1 -d out/client client/TestAction.java
java -cp out/client:out/v2:out/v1 TestAction
```

On Windows, replace `:` with `;`. The runtime loads `api.Action` from `out/v2` first, whereas the `OldAction` instance was compiled earlier against v1. When calling `description()`, the JVM can throw:

```text
java.lang.AbstractMethodError: Receiver class impl.OldAction
does not define or inherit an implementation ...
```

Exact message wording depends on the JDK. The fix is to implement `description()` and rebuild `OldAction`, or design a backward-compatible API contract such as a default method with appropriate semantics.

Note that the `TestAction` build command uses both `out/v2` and `out/v1`; `out/v2` comes first so the compiler sees the new interface. This is strictly an experiment simulating binary compatibility; real projects should never distribute two copies of the same API on the same runtime search path.

## 8. Environment-Dependent Demo for UnsupportedClassVersionError

To reproduce this accurately, **two JDK versions** are needed: a newer JDK to compile and an older JVM to run. For example, JDK 21 and JDK 17:

```java
public class NewerClass {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
```

Compile with JDK 21:

```bash
/path/to/jdk21/bin/javac NewerClass.java
```

Run this class with JDK 17:

```bash
/path/to/jdk17/bin/java NewerClass
```

When compiled by default for Java 21, the class file carries major version 65; JVM 17 supports only up to major version 61 and throws `UnsupportedClassVersionError`. The JDK paths above are **illustrative placeholders**, not literal commands to copy verbatim on every machine. You cannot reproduce this error using only a single JDK 17 installation if the class is compiled with `--release 17` and no higher bytecode version exists.

## 9. Fast Diagnostic Workflow Upon Receiving a Stack Trace

```text
LinkageError occurs
      |
      v
Read exact error name
      |
      +-- UnsupportedClassVersionError
      |       -> check class major/JVM runtime
      |
      +-- NoSuchMethodError
      |       -> compare compile-time vs runtime method descriptor
      |
      +-- AbstractMethodError
              -> find receiver class and missing abstract method
      |
      v
Identify actual class/JAR/module/class loader
      |
      v
Inspect dependency tree, packaging, and API policy
      |
      v
Reproduce from deployed artifact
      |
      v
Fix version/contract + retest
```

Minimum checklist:

1. Record the **full stack trace**, JDK version, and artifact version.
2. Identify the failing method/class and the class loader that loaded that class.
3. Compare compile-time dependencies with actual runtime dependencies.
4. Use `javap` to inspect descriptors or major versions; do not inspect source alone.
5. For plugins, check parent delegation, duplicate classes, and the JPMS module graph.
6. Verify the fix on the **exact final packaged artifact**, not just inside the IDE.
7. Add contract tests and API compatibility checks before activating plugins.

A useful diagnostic log should include plugin ID, plugin version, host API version, JDK version, loader identity, and class source if available. Do not log sensitive user data solely to investigate linkage issues.

## 10. Prevention in Runtime Plugin Systems

**Define a stable API contract:** the host provides a shared API module/JAR, and plugins build against published versions. Use `provided`/`compileOnly` where appropriate so plugins do not bundle their own copy of the shared API and break class identity.

**Verify versions before activation:** a module version alone is insufficient. Plugins should declare API requirements and minimum Java version; the host should enforce version-range policies, capability checks, and binary compatibility.

**Avoid arbitrary loaders:** define which packages are parent-first and which are isolated. The host API must have a single consistent defining loader across the communication boundary.

**Exercise providers before publishing:** run health checks and required methods in staging. Be careful because a method is only linked when that code path runs; a smoke test does not prove every path is safe.

**Provide lifecycle rollback:** if a plugin upgrade causes a linkage failure, stop routing new requests, roll back the registry/snapshot per policy, and drain/handle in-flight requests. Do not automatically retry business operations that already had side effects.

**Maintain build/deployment observability:** store dependency locks, build metadata, runtime API versions, and JDK releases. For untrusted plugins, remember that class loaders and module layers are not security sandboxes.

## 11. Distinguishing from Related Errors

| Error | Key Distinction |
|---|---|
| `ClassNotFoundException` | Loader could not find the class during a name-based lookup |
| `NoClassDefFoundError` | JVM could not define/link a required class or a class previously failed initialization |
| `ClassCastException` | Object cannot be cast to the expected type; may be caused by duplicate class identity |
| `NoSuchMethodError` | Symbolic method reference could not be resolved properly at runtime |
| `AbstractMethodError` | No suitable concrete implementation exists on the receiver |
| `IllegalAccessError` | Class/method/field access is no longer valid under visibility rules |
| `IncompatibleClassChangeError` | Change in instance/static relationship, inheritance, or binary contract |
| `UnsupportedClassVersionError` | Runtime does not support the class-file version |

Do not try to fix everything by "adding the JAR to the classpath". Adding a JAR can cause classes to load from the wrong version and make the problem worse.

## 12. Common Mistakes

- Confusing `NoSuchMethodError` with `NoSuchMethodException`: the latter is a checked exception from reflective APIs, distinct from JVM bytecode method call linkage.
- Confusing `AbstractMethodError` with a source error for forgetting an override: the compiler prevents this in fresh source, yet older binaries can still be loaded.
- Assuming a Java 17 compiler always emits Java 17 bytecode regardless of target/release flags.
- Ignoring the **actual** JDK version inside the container or service process.
- Looking only at the build dependency tree without inspecting the runtime classpath or shaded artifact.
- Treating a module version as a guarantee of binary compatibility.
- Hot-reloading a class loader while leaving old objects communicating with incompatible new APIs/classes.
- Catching `Exception` and expecting it to handle all `LinkageError`s.
- Logging "plugin failed" without recording the owner method, descriptor, and class source.
- Believing a single simple passing test proves every code path is compatible.

## 13. Quick-Reference Checklist

When you encounter:

- **`NoSuchMethodError`**: ask "which **method descriptor** is the bytecode requesting, and does the runtime JAR/module contain that exact method?"
- **`AbstractMethodError`**: ask "does the concrete instance have an **implementation of the method** required by the runtime API?"
- **`UnsupportedClassVersionError`**: ask "is this class-file major version supported by the **running JVM**?"

**Conclusion:** in runtime-extensible Java systems, these three errors typically expose a **contract mismatch between build and runtime**. Resolving them thoroughly requires comparing actual bytecode, dependencies, and loaders, enforcing compatibility policies prior to activation, and testing on the final deployment artifacts.
