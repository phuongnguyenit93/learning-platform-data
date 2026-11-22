# AbstractMethodError and IncompatibleClassChangeError

In **Java Advance Compatibility Migration**, an application may **compile successfully** yet raise `java.lang.AbstractMethodError` or `java.lang.IncompatibleClassChangeError` when running in an integration or production environment. These errors typically appear when code was compiled against **one version of the binary contract** of a class/interface, but the JVM loads a different version at execution time.

For example, a new module calls a method just added to an interface while the old implementation has not been recompiled; or an old client uses bytecode that calls an **instance method** while the deployed library version changed that method to **static**. The result does not necessarily manifest as a compile error, because each artifact may have been compiled successfully at different times.

This is a lesson in the **Troubleshooting** chapter of the **Java Advance Compatibility Migration** module. The content accurately distinguishes the two errors, explains why they belong to the `LinkageError` family, how the JVM resolves/selects methods, real-world migration scenarios, reproducible cross-version compilation examples, the workflow for finding the actual JAR/class loaded, how to use `javap`, Gradle, Maven, and preventive measures.

**Core message:** do not jump to the conclusion "the new JDK has a bug" just because an exception appears right after upgrading Java. First, inspect the **ABI (Application Binary Interface)**, dependency graph, class loader, and runtime version of every artifact participating in the call.

## 1. What are the two errors?

`AbstractMethodError` occurs when a program attempts to execute a method that requires a concrete implementation, but according to runtime method resolution/selection **no suitable concrete implementation is found**. A common situation is when a new interface adds an abstract method while the implementation class is still the old binary.

`IncompatibleClassChangeError` is an error indicating that a class or member is used by the JVM in a way that **no longer matches its actual binary form**. For example, client bytecode calls a method as an instance method, whereas the loaded class only has the corresponding version as a static method.

Inheritance relationship:

~~~text
java.lang.Throwable
        |
        +-- java.lang.Error
                |
                +-- java.lang.LinkageError
                        |
                        +-- IncompatibleClassChangeError
                        |       |
                        |       +-- AbstractMethodError
                        |       +-- NoSuchMethodError
                        |       +-- NoSuchFieldError
                        |       +-- IllegalAccessError
                        |       +-- ...
                        |
                        +-- ClassFormatError
                        +-- VerifyError
                        +-- UnsupportedClassVersionError
                        +-- ...
~~~

The diagram illustrates the relevant branches in the hierarchy. Importantly, **`AbstractMethodError` is a subclass of `IncompatibleClassChangeError`**, so looking only at a parent-level exception name without checking the concrete subtype and stack trace makes misdiagnosis very easy.

### 1.1. Why are they Errors and not Exceptions?

Both belong to the `Error` branch, usually indicating that **the runtime environment and the existing class files do not match the linkage assumptions** of the compiled code. This is not a normal input validation error for the application to catch and continue processing.

Do not fix it with:

~~~java
try {
    service.execute();
} catch (IncompatibleClassChangeError error) {
    // Ignore so the application continues?
}
~~~

Swallowing the error can hide a systemic dependency conflict. The fix direction is to **align binary contracts and artifacts**, except in special cases with a clear, tested fallback design.

## 2. Linkage in the class lifecycle

Four stages must be distinguished:

1. **Loading:** The JVM/class loader finds class bytes and creates the class representation.
2. **Linking:** includes verification, preparation, and resolution (resolution may be performed on demand).
3. **Initialization:** runs static initializers according to Java rules.
4. **Execution:** executes bytecode, during which method invocations/field accesses may trigger resolution or selection.

Diagram:

~~~text
Source A.java / B.java
          |
          | javac at time T1
          v
       .class files
          |
          | JAR / WAR / runtime classpath at T2
          v
   Class loader finds actual class
          |
          v
   Verification / resolution
          |
          v
   Method / field invocation
          |
          +--> matching binary contract -> runs
          |
          +--> missing method/field -> corresponding linkage error
          |
          +--> static/instance mismatch -> ICCE
          |
          +--> no concrete implementation -> AME
~~~

An application may start up normally because the failing code path has not been executed yet. Only when a request, scheduled job, or message processes that exact new method does the JVM detect the conflict.

### 2.1. Compile time and runtime do not use the same classpath

The compiler may see `library-api-2.jar` during compilation, while production loads `library-api-1.jar` or an old implementation. Because each artifact is built separately, the compiler does not necessarily have an opportunity to check the **final combination of class files**.

This is why linkage errors frequently appear in multi-module, plugin-based, application server, or microservice deployment environments.

## 3. How does ABI differ from Java source API?

**Source API** consists of the declarations seen by source code: classes, methods, interfaces, generics, annotations, and access modifiers.

**ABI** reflects the binary characteristics that compiled code relies on, such as:

- Fully qualified class name.
- Class or interface.
- Method name and **JVM method descriptor**.
- Field name and field descriptor.
- Static/instance nature.
- Access flags and inheritance relationships.
- Bytecode instructions such as `invokevirtual` or `invokestatic`.
- Bridge methods generated by the compiler.
- Superclasses/superinterfaces and default methods.

Two source files that look very similar but have **different ABIs** can prevent old client binaries from running.

### 3.1. Method descriptor

Example:

~~~java
public String find(long id) {
    return "...";
}
~~~

JVM descriptor:

~~~text
(J)Ljava/lang/String;
~~~

- `J`: `long` parameter.
- `Ljava/lang/String;`: return type `String`.

With:

~~~java
public Object find(long id) {
    return null;
}
~~~

the descriptor is:

~~~text
(J)Ljava/lang/Object;
~~~

Because the JVM descriptor includes the return type, a change in return type can prevent old binaries from finding the right symbolic reference, even though the Java source looks identical to the original call.

### 3.2. Generic type erasure

Generics undergo erasure in many cases, so changing generic arguments does not necessarily change the JVM descriptor. However, the compiler can generate **bridge methods** to preserve dispatch and binary compatibility when using covariant returns or generics. Therefore, you need to inspect the actual bytecode rather than looking only at the Java method signature formatted by an IDE.

## 4. Distinguishing related errors

| Error | Typical situation | Diagnostic question |
|---|---|---|
| `AbstractMethodError` | The interface/abstract contract exists, but runtime cannot find a suitable concrete implementation | Has the implementation JAR been updated yet? |
| `IncompatibleClassChangeError` (specifically at the superclass) | Invocation/field access mismatches static/instance or conflicts with interface defaults | Did the member/class kind change? |
| `NoSuchMethodError` | The JVM cannot resolve the method by name/descriptor | Did the method binary signature change, or is the runtime JAR wrong? |
| `NoSuchFieldError` | The field no longer exists by name/descriptor | Was the field changed or deleted? |
| `IllegalAccessError` | The member/class exists, but access rules disallow it | Did visibility or module access change? |
| `ClassNotFoundException` | Code asks a loader to find a class, but it is not found | Is a JAR or classloader path missing? |
| `NoClassDefFoundError` | The JVM cannot find/define a dependent class at runtime | Was the class removed, moved to another package, or did init fail? |
| `UnsupportedClassVersionError` | The JVM is too old to load the class-file major version | Does the runtime JDK match the bytecode target? |
| `VerifyError` | Bytecode does not satisfy verification constraints | Is there an issue with bytecode generation/transformation? |
| `ClassCastException` | The runtime object cannot be cast | Is there a classloader identity/inheritance mismatch? |

This table is for orientation. You must read the **exception subtype, message, caused-by chain, stack frames, and class source** instead of relying on a single keyword.

**Note:** `NoSuchMethodError`, `NoSuchFieldError`, and `IllegalAccessError` also fall under `IncompatibleClassChangeError` in the class hierarchy. When saying "pure ICCE" in this lesson, we mainly refer to **`IncompatibleClassChangeError` thrown directly** rather than a specific subclass.

## 5. When does AbstractMethodError occur?

A common situation:

~~~text
V1 contract:
  interface Job {
      void run();
  }

Implementation V1:
  class LegacyJob implements Job {
      public void run() { ... }
  }

V2 contract:
  interface Job {
      void run();
      void cancel();  <-- new abstract method
  }

Runtime:
  Job V2 + LegacyJob class file V1
  client calls job.cancel()
             |
             v
      AbstractMethodError
~~~

`LegacyJob.class` compiled validly at a time when the interface only had `run()`. At runtime, the JVM can load the old class along with the new interface, but it does not have a concrete implementation for `cancel()`. The error occurs when the client actually calls that method.

### 5.1. It does not necessarily fail right when the class is loaded

Do not assume every old implementation will cause the application to fail immediately at startup. Many compatibility errors only arise at method invocation time, especially in rare code branches.

Therefore, **a startup smoke test is not enough** to prove that the runtime dependency graph is compatible.

### 5.2. What if the interface adds a default method?

If V2 adds a **default method** with an implementation:

~~~java
public interface Job {
    void run();

    default void cancel() {
        // Fallback implementation.
    }
}
~~~

an old implementation can inherit the default method and does not need additional implementation in some valid structures. However, default methods also have method selection and conflict rules; not every change from abstract to default is safe across every inheritance graph.

## 6. Example reproducing AbstractMethodError with separate compilation

Example goal: **compile the implementation against API V1**, then upgrade only the API to V2 and compile the new client. Do not recompile the implementation.

### 6.1. Illustrative file structure

~~~text
ame-demo/
├── v1/api/demo/api/Task.java
├── v1/impl/demo/impl/LegacyTask.java
├── v2/api/demo/api/Task.java
├── client/demo/client/Main.java
└── out/
    ├── v1-api/
    ├── impl/
    ├── v2-api/
    └── client/
~~~

### 6.2. API version V1

File `v1/api/demo/api/Task.java`:

~~~java
package demo.api;

public interface Task {
    void execute();
}
~~~

### 6.3. Old implementation

File `v1/impl/demo/impl/LegacyTask.java`:

~~~java
package demo.impl;

import demo.api.Task;

public final class LegacyTask implements Task {

    @Override
    public void execute() {
        System.out.println("Executed by legacy implementation");
    }
}
~~~

This implementation is completely valid according to `Task` V1.

### 6.4. API version V2

File `v2/api/demo/api/Task.java`:

~~~java
package demo.api;

public interface Task {
    void execute();

    void cancel();
}
~~~

V2 adds an abstract method `cancel()` with no default implementation.

### 6.5. Client compiled against V2

File `client/demo/client/Main.java`:

~~~java
package demo.client;

import demo.api.Task;
import demo.impl.LegacyTask;

public final class Main {

    public static void main(String[] args) {
        Task task = new LegacyTask();
        task.execute();
        task.cancel();
    }
}
~~~

### 6.6. Illustrative compilation commands

On Unix/Linux/macOS shells:

~~~bash
mkdir -p out/v1-api out/impl out/v2-api out/client

javac --release 8 \
  -d out/v1-api \
  v1/api/demo/api/Task.java

javac --release 8 \
  -cp out/v1-api \
  -d out/impl \
  v1/impl/demo/impl/LegacyTask.java

javac --release 8 \
  -d out/v2-api \
  v2/api/demo/api/Task.java

javac --release 8 \
  -cp "out/v2-api:out/impl" \
  -d out/client \
  client/demo/client/Main.java
~~~

When compiling `LegacyTask`, the compiler only sees `Task` V1. When compiling the client, the compiler sees `Task` V2 and the old implementation binary.

Run:

~~~bash
java -cp "out/client:out/impl:out/v2-api" \
  demo.client.Main
~~~

On Windows, the usual classpath separator is a semicolon `;`:

~~~powershell
java -cp "out/client;out/impl;out/v2-api" demo.client.Main
~~~

### 6.7. Expected result

The program may print:

~~~text
Executed by legacy implementation
~~~

and then throw an exception of the form:

~~~text
java.lang.AbstractMethodError: Receiver class demo.impl.LegacyTask
does not define or inherit an implementation of the resolved method
'abstract void cancel()' of interface demo.api.Task
~~~

**The detailed error message depends on the Java runtime/version**, so character-for-character message matching is not required. The important point is that runtime contains **V2 API + V1 implementation**, and the called method lacks a concrete implementation.

The commands above are **reproduction instructions for learners**, not test output executed during authoring.

## 7. Fixing the AbstractMethodError example to match the contract

The direct approach is to recompile the implementation against V2:

~~~java
package demo.impl;

import demo.api.Task;

public final class LegacyTask implements Task {

    @Override
    public void execute() {
        System.out.println("Executed");
    }

    @Override
    public void cancel() {
        System.out.println("Cancelled");
    }
}
~~~

Then ensure the new artifact is placed on the **runtime classpath** replacing the old implementation.

Important steps:

1. Upgrade the implementation source or choose a library version that supports API V2.
2. Compile the implementation against the corresponding API.
3. Inspect the ABI method descriptors in the class file.
4. Package the new implementation.
5. Verify that the application/server loads **the exact new JAR**, without an old JAR taking precedence.
6. Run tests that invoke `cancel()`, not just startup checks.
7. If multiple services/plugins use the implementation, upgrade according to the compatibility matrix.

### 7.1. Do not simply add a method to an interface and expect runtime to fix itself

The JVM has no mechanism to auto-write a method body for an old implementation just because a new interface requires it. If backward compatibility is needed, a default method with appropriate semantics or a compatibility adapter can be considered, but this decision must be reviewed.

### 7.2. Default implementations are not always suitable

A default no-op `cancel()` can mask the fact that cancellation is not actually supported and cause incorrect business behavior. A default method is only safe when there is a clear contract and tests.

## 8. An abstract superclass can also lead to AbstractMethodError

AME does not come only from interfaces.

Suppose a library has an abstract superclass:

~~~java
public abstract class BaseProcessor {
    public abstract void process();
}
~~~

An old subclass binary may rely on a different form of the superclass contract at compile time. If the superclass/child binaries diverge and a method call ultimately fails to find a valid concrete implementation, runtime may encounter `AbstractMethodError`.

Depending on how the API changed, the compiler or JVM may detect it at a different stage. You need to analyze **signatures, hierarchy, and compiled bytecode**, rather than assuming every abstract superclass change will necessarily throw the same error.

### 8.1. Issues often appear in framework extensions

A library has base classes such as:

~~~java
public abstract class FrameworkAdapter {
    protected abstract Result handle(Input input);
}
~~~

If a new framework version adds/changes abstract hooks while a plugin extension retains an old binary, an invocation can lead to AME. Custom plugins or third-party adapters are places to check when upgrading Spring, ORMs, drivers, and application servers.

## 9. ICCE when changing an instance method to a static method

A common example of direct `IncompatibleClassChangeError` is changing the **invocation form** of the same method.

Version V1:

~~~java
package demo.lib;

public final class PingUtil {

    public String ping() {
        return "v1";
    }
}
~~~

Client compiled with V1:

~~~java
package demo.client;

import demo.lib.PingUtil;

public final class Main {

    public static void main(String[] args) {
        System.out.println(new PingUtil().ping());
    }
}
~~~

Version V2 of the library:

~~~java
package demo.lib;

public final class PingUtil {

    public static String ping() {
        return "v2";
    }
}
~~~

The old client source was compiled into an **instance method invocation**, but runtime only has a static method with the same binary name/descriptor.

### 9.1. What the JVM can see

Client V1 may contain:

~~~text
invokevirtual demo/lib/PingUtil.ping:()Ljava/lang/String;
~~~

However, the runtime V2 method has the `ACC_STATIC` flag. The method invocation instruction is incompatible with the resolved member, leading to `IncompatibleClassChangeError`, typically with a message like:

~~~text
java.lang.IncompatibleClassChangeError:
Expecting non-static method 'java.lang.String demo.lib.PingUtil.ping()'
~~~

The exact message depends on the JVM, release, and bytecode compiler. What matters is **`invokevirtual` contradicting a static method**.

## 10. Commands to reproduce ICCE caused by static/instance mismatch

Assume the structure:

~~~text
icce-demo/
├── v1/demo/lib/PingUtil.java
├── v2/demo/lib/PingUtil.java
├── client/demo/client/Main.java
└── out/
    ├── v1/
    ├── v2/
    └── client/
~~~

Compile V1:

~~~bash
mkdir -p out/v1 out/v2 out/client

javac --release 8 \
  -d out/v1 \
  v1/demo/lib/PingUtil.java
~~~

Compile client against V1:

~~~bash
javac --release 8 \
  -cp out/v1 \
  -d out/client \
  client/demo/client/Main.java
~~~

Compile library V2:

~~~bash
javac --release 8 \
  -d out/v2 \
  v2/demo/lib/PingUtil.java
~~~

Run **client V1** with **library V2**, without V1 JAR at runtime:

~~~bash
java -cp "out/client:out/v2" demo.client.Main
~~~

Expected: `IncompatibleClassChangeError` because the client bytecode calls an instance method while the runtime implementation changed to static.

**Do not recompile the client with V2 before reproducing**: the compiler may change the invocation to `invokestatic` or report a source error depending on how it is called, losing the original binary mismatch scenario.

## 11. Changing static to instance can also throw ICCE

The reverse case:

- Old client compiled with `public static void send()`.
- Runtime library changed to `public void send()`.
- Old bytecode still contains the `invokestatic` instruction.
- The JVM sees that the actual target method is non-static.

The result can be `IncompatibleClassChangeError`, usually with a message equivalent to "Expected static method".

This is an **ABI breaking change**. Keeping the same method name/parameter types in Java source is not enough to preserve binary compatibility.

### 11.1. Fields also have static/instance mismatches

ICCE is not limited to methods. Client binaries can use:

- `getstatic`/`putstatic` for a static field.
- `getfield`/`putfield` for an instance field.

If a field is changed from static to instance or vice versa between compile time and runtime, the JVM may throw `IncompatibleClassChangeError` upon access.

### 11.2. Avoid fixing by forcing JVM flags

`--add-opens` or `--add-exports` relate to module access; they do not turn an instance method into static or vice versa. Changing flags does not fix bytecode invocation instructions.

## 12. ICCE due to conflicting interface default methods

Java 8 added default methods to interfaces. This helps interfaces evolve their APIs, but when different interfaces independently add a default method with the **same signature**, an old class binary can fall into an ambiguous state.

### 12.1. Separate compilation scenario

Version V1:

~~~java
package demo.spi;

public interface Left {
}
~~~

~~~java
package demo.spi;

public interface Right {
}
~~~

Class compiled with V1:

~~~java
package demo.impl;

import demo.spi.Left;
import demo.spi.Right;

public final class Combined implements Left, Right {
}
~~~

In version V2, `Left` adds:

~~~java
package demo.spi;

public interface Left {

    default String label() {
        return "left";
    }
}
~~~

While `Right` also adds:

~~~java
package demo.spi;

public interface Right {

    default String label() {
        return "right";
    }
}
~~~

A new client can call:

~~~java
Left component = new Combined();
System.out.println(component.label());
~~~

If `Combined.class` is still a binary from V1, that class **has no method override to resolve the conflict**. When method selection encounters two competing default implementations under the corresponding conditions, the JVM may throw `IncompatibleClassChangeError`.

### 12.2. Why did the compiler not block it?

If recompiling the source `Combined implements Left, Right` directly against both V2 interfaces, `javac` typically requires resolving the conflict. However, the V1 `Combined.class` binary was generated before those default methods existed; it may not be re-checked by the new compiler during packaging.

This is an example of the difference between **source compilation consistency** and **runtime binary linkage**.

### 12.3. How to handle it

One way to resolve this is to implement/override the method in `Combined`:

~~~java
public final class Combined implements Left, Right {

    @Override
    public String label() {
        return Left.super.label();
    }
}
~~~

At this point, the class makes an explicit choice. It must be recompiled against the V2 API and deployed as a new binary. Do not arbitrarily decide to use `Left.super.label()` if the actual business semantics require `Right` or a different implementation.

## 13. Interface converted to class and vice versa

A library version may change a public type from an `interface` to a `class` or vice versa. Old compiled code may contain assumptions about:

- `invokeinterface` versus `invokevirtual`.
- `implements` versus `extends`.
- Object construction.
- Inheritance and method resolution.

Depending on the specific change, the JVM may report `IncompatibleClassChangeError` or another linkage error. This is usually a very major breaking change at the ABI level.

### 13.1. Do not fix by changing the dependency jar one-sidedly

If a public type changes from an interface to a class, you must align **all implementations, adapters, and client binaries**. Simply upgrading the API jar and letting old plugin implementations continue running can create widespread conflicts.

## 14. Method resolution and method selection differ

This is an important part for understanding why the two errors are related yet not identical.

### 14.1. Resolution

The JVM uses the symbolic reference from the calling class's constant pool to locate the method/field by class/interface name and descriptor. If an appropriate method cannot be found, it may throw `NoSuchMethodError` or the corresponding resolution error.

### 14.2. Selection

For invocations with dynamic dispatch, the JVM must also select the actual implementation based on the receiver class, inheritance, and interface defaults.

Example:

~~~java
interface Service {
    void run();
}

final class LegacyService implements Service {
    @Override
    public void run() { }
}
~~~

If the library API changes between compilations, the symbolic reference may resolve to `Service.run()`, yet the concrete receiver at runtime lacks a matching implementation for a new method. In that case, `AbstractMethodError` can occur **during the dispatch/selection step**.

### 14.3. Not every invocation uses dynamic dispatch

- `invokestatic`: invokes a static method.
- `invokevirtual`: typically invokes an instance method across the class hierarchy with dispatch.
- `invokeinterface`: invokes an interface method through a receiver implementation.
- `invokespecial`: used for certain constructor calls, private methods, and special superclass/interface invocations.

The specific error depends on the instruction and JVMS rules. Do not assume all linkage errors are caused by `invokevirtual`.

## 15. Inspecting invocation bytecode with javap

`javap` is a useful tool to distinguish **which call the compiled client expected**.

Example:

~~~bash
javap -classpath client.jar -c -p \
  com.example.client.OrderClient
~~~

You may see:

~~~text
invokeinterface #18 // InterfaceMethod com/example/api/Service.cancel:()V
~~~

or:

~~~text
invokevirtual #22 // Method com/example/lib/PingUtil.ping:()Ljava/lang/String;
~~~

or:

~~~text
invokestatic #22 // Method com/example/lib/PingUtil.ping:()Ljava/lang/String;
~~~

The numbers `#18` and `#22` are merely constant pool indices in an illustrative output. When diagnosing, pay attention to **opcode, owner, method name, and descriptor**.

### 15.1. Viewing method signatures

~~~bash
javap -classpath implementation.jar -s -p \
  com.example.impl.LegacyService
~~~

`-s` displays internal type signatures/descriptors. `-p` displays private members as well.

### 15.2. Viewing method flags

~~~bash
javap -classpath implementation.jar -verbose \
  com.example.impl.LegacyService
~~~

Look for flags such as `ACC_PUBLIC`, `ACC_STATIC`, `ACC_ABSTRACT`, and `ACC_BRIDGE`.

Do not only look at the source open in your IDE: the source may be the new version while the production JVM loads the class from a different old artifact.

## 16. Investigation model for a stack trace

Hypothetical example:

~~~text
java.lang.AbstractMethodError:
Receiver class com.example.vendor.LegacyAdapter
does not define or inherit an implementation of
'abstract void com.example.spi.Service.stop()'
    at com.example.app.Worker.shutdown(Worker.java:84)
    at com.example.app.Main.main(Main.java:20)
~~~

Read in order:

1. **Concrete error:** `AbstractMethodError`.
2. **Receiver:** `com.example.vendor.LegacyAdapter`.
3. **Method contract:** `Service.stop()V`.
4. **Call site:** `Worker.shutdown`.
5. **Runtime API:** where is the method currently declared?
6. **Implementation artifact:** which JAR does `LegacyAdapter.class` come from?
7. **Compile-time API:** which SPI version was the implementation built against?
8. **Deployment:** is there a plugin/server library or classloader giving priority to an old version?

The right question is usually not "how do I catch this error?" but **"which binary versions do the caller, the API contract, and the receiver implementation come from?"**

## 17. Identifying the JAR containing the loaded class

A dependency graph may show the version resolved at build time, but an external container or plugin loader may load a different JAR.

### 17.1. Class loading logs on modern JDKs

Example:

~~~bash
java -Xlog:class+load=info \
  -cp "app.jar:lib/*" \
  com.example.Main
~~~

Depending on the JDK and launcher, logs can show which archive/source a class was loaded from. On Java 8, the logging mechanism differs (e.g., `-verbose:class`); use flags appropriate for the runtime.

### 17.2. Printing the CodeSource location in a test environment

Diagnostic code can be written:

~~~java
public static String codeSourceOf(Class<?> type) {
    var domain = type.getProtectionDomain();

    if (domain == null || domain.getCodeSource() == null) {
        return "<unknown>";
    }

    var location = domain.getCodeSource().getLocation();

    return location == null ? "<unknown>" : location.toString();
}
~~~

The example uses `var` so it requires Java 10+. Explicit declarations can be used if Java 8 is needed.

**Limitation:** CodeSource may reflect the container/launcher/nested JAR in its own way and does not always contain an easy-to-read URL. Do not use it as the sole source of evidence.

### 17.3. Do not log sensitive paths and metadata indiscriminately

Enable only necessary diagnostics in controlled environments; class loading logs can be very large and expose system path information. When collecting production logs, security policies must be followed.

## 18. Gradle: investigating dependency resolution

In a Gradle Java project, reference commands:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

In a multi-module project:

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath
~~~

To see why a version was chosen:

~~~bash
./gradlew :orders-service:dependencyInsight \
  --dependency example-spi \
  --configuration runtimeClasspath
~~~

The exact tasks/configurations depend on the project and Gradle plugins in use.

### 18.1. Compile and runtime graphs differ

Example:

~~~text
compileClasspath:
  com.example:service-spi:2.0

runtimeClasspath:
  com.example:service-spi:2.0
  com.example:legacy-service-impl:1.0
~~~

A new SPI combined with an old implementation is an AME candidate. In an application server, runtime also includes server-provided libraries outside this graph.

### 18.2. Do not force dependency versions arbitrarily

Overriding a transitive JAR to a higher version may resolve one conflict while creating an ABI conflict with the parent library. Follow the framework's BOM/compatibility matrix when available, upgrade compatible library sets together, and run integration tests.

### 18.3. Dependency locking

Dependency locks or version constraints can help reproduce the resolved graph. They do not by themselves prove binary compatibility, but they help accurately compare before and after migration.

## 19. Maven: viewing the dependency tree and effective POM

Reference commands:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.example:service-spi
mvn help:effective-pom
~~~

When using a Maven parent/BOM, `help:effective-pom` helps show the merged version management and plugin configuration.

Depending on the Maven Dependency Plugin version, you can use:

~~~bash
mvn dependency:tree -Dverbose
~~~

Rely on actual output and resolved artifacts, because details of omitted/conflict nodes may differ by plugin version.

### 19.1. Approximate Maven scenario

~~~text
app
 +-- com.example:new-client:3.0
 |    +-- com.example:service-spi:2.0
 +-- com.example:legacy-adapter:1.0
      +-- com.example:service-spi:1.0 (omitted/mediated)
~~~

Maven selects `service-spi:2.0`, but `legacy-adapter:1.0` may have been compiled against the old SPI. This is a hypothetical example; you must inspect the actual binaries to know what incompatibility will occur.

### 19.2. Dependency exclusion is not a universal solution

Excluding the old SPI JAR is correct if runtime only needs one API version, but it **does not automatically create the missing implementation** inside `legacy-adapter:1.0`. If the adapter must be updated, choose a compatible adapter version or rebuild it.

## 20. Framework migrations and extension points

Frameworks provide interfaces/abstract classes that plugins or applications implement:

- Spring lifecycle and custom extension APIs.
- Hibernate interceptors, custom types, dialects.
- Servlet Filters/Listeners.
- JDBC drivers and Service Provider Interfaces.
- Serialization modules.
- Logging backends/appenders.
- Bytecode agents and instrumentation frameworks.
- Custom test runners.
- Application server modules.
- Internal SDKs/plugin contracts.

When a framework moves to a new major version, implementations compiled against old contracts may hit AME/ICCE if still loaded.

### 20.1. Spring Boot 2 → 3

Moving from Spring Framework 5 to 6 and Java EE `javax.*` to Jakarta `jakarta.*` can produce:

- Missing classes/`NoClassDefFoundError` if old libraries remain.
- `NoSuchMethodError` if API methods changed.
- `AbstractMethodError` if an extension implementation does not satisfy the new contract.
- `IncompatibleClassChangeError` when binary hierarchy/member flags no longer match.
- Bean initialization errors due to mixed versions.

Do not blame Jakarta for every error just because Boot was upgraded. Look at the concrete exception and class source.

### 20.2. Hibernate 5 → 6

Custom UserType, Dialect, or interceptor classes from Hibernate 5 may need updates for the new API. If an old adapter binary is used with Hibernate 6, linkage errors can occur. Upgrade the entire extension and verify SQL/query behavior, rather than just adding a method to silence AME.

### 20.3. Servlet 4 → Jakarta Servlet 6

`javax.servlet.Filter` and `jakarta.servlet.Filter` are **two different types**. Not finding the class usually leads to `ClassNotFoundException` or `NoClassDefFoundError`, not necessarily AME/ICCE. This illustrates the rule **not to assign one generic error category to every compatibility issue**.

## 21. JDK upgrades do not directly cause AME/ICCE

Upgrading Java 11 → 17 or Java 17 → 21 can bring along:

- Upgrading Gradle/Maven plugins.
- Upgrading libraries that support new class-file versions.
- Upgrading Spring/ORM/HTTP clients.
- Updating Java agents, code generators, testing frameworks.
- Changing container images or application servers.
- Changing packaging, shading, or module path.

Those **indirect** changes can expose dependency ABI mismatches.

### 21.1. A different code path runs after a JDK upgrade

An application may use `Runtime.version()`, service loading, MRJAR, or reflection to pick a new implementation on a newer JDK. In that case, the same JAR on a newer runtime can hit an untested code path, causing a linkage error to surface.

Investigation should compare:

- JDK runtime version.
- Artifact checksums.
- Classloader/launcher.
- Multi-release JAR variants.
- Runtime dependencies.
- Code paths and loaded classes.

### 21.2. An unchanged JAR checksum can still select a different class

With a **multi-release JAR**, a class under `META-INF/versions/17` may be used on Java 17 while Java 11 uses the base or overlay 11. If one variant has a broken ABI or implementation, the issue only appears on one JDK.

Do not conclude from matching artifact versions that runtime is executing the exact same class bytes.

## 22. Multi-release JARs in troubleshooting

Example:

~~~text
library.jar
  com/example/Service.class
  META-INF/versions/11/com/example/Service.class
  META-INF/versions/17/com/example/Service.class
~~~

If Java 17 selects a different versioned variant, inspect:

1. Does the manifest have `Multi-Release: true`?
2. Class-file major version of each variant.
3. Method descriptors and static/abstract flags of base and overlay.
4. Public/protected API consistency.
5. Is the loader MRJAR-aware?
6. Does the client's compile-time view differ from the runtime view?
7. Does `jar --validate` report structural/API inconsistencies?
8. Do tests run against the **packaged JAR** instead of class directories?

A malformed MRJAR can cause `NoSuchMethodError`/AME/ICCE when a newer runtime selects a different class. This is a possibility to investigate, not the default cause of every post-Java-upgrade failure.

## 23. Class loaders and plugin-based applications

Java type identity consists of **the class name and the defining class loader**. An application server or plugin engine can use multiple class loaders.

~~~text
Bootstrap/platform loader
          |
          v
Container/common loader
          |
          +-- shared-api.jar
          |
          v
Application/webapp/plugin loader
          |
          +-- implementation.jar
          +-- another-api.jar
~~~

If the parent loader selects API version A while the child loader selects an implementation compiled against version B, linkage errors or loader constraint violations can arise.

### 23.1. Symptoms

- Standalone application runs locally, WAR deployed on server fails.
- Changing plugin load order yields different results.
- A class appears in two JARs or on the server/common classpath.
- Exception only occurs after hot redeploy.
- Message `loader constraint violation` or class identity conflict.
- CodeSource shows the class was loaded from an unexpected location.

### 23.2. Do not drop JARs arbitrarily into server lib

Adding a framework API version into container-shared libraries can force multiple WARs to load that version when each WAR needs its own. Server-provided dependencies must be managed according to the application server's support matrix.

### 23.3. Separate stable API and plugin implementations

When designing a plugin architecture, have:

- A clear SPI artifact/version contract.
- Plugin implementations compiled/tested against the supported SPI version.
- Consistent classloader policies.
- Version negotiation or rejection of incompatible plugins.
- Plugin API compatibility tests before loading into production.

## 24. Java agents, proxies, and generated bytecode

Some post-JDK-upgrade errors can involve generated or transformed code:

- Byte Buddy/Mockito inline mocking.
- AOP proxies.
- Hibernate bytecode enhancement.
- JDK dynamic proxies.
- Java agents/APM instrumentation.
- Compiler/annotation processor generated classes.
- Runtime code generation (CGLIB-like tools).
- Shading/obfuscation.

These tools may generate classes or method stubs according to the API version they see. If the runtime method contract differs or bytecode transformation fails to preserve ABI, linkage errors can appear.

### 24.1. Distinguishing parser errors from linkage errors

An agent that does not understand a new class-file major version typically throws errors like `Unsupported class file major version N` or `IllegalClassFormatException`. That is not necessarily AME/ICCE.

If the agent transforms the class anyway but produces wrong invocation/dispatch instructions, a linkage error may occur. You need to inspect the **full stack trace and post-transformation bytecode** during deep investigation.

### 24.2. Do not force ASM/Byte Buddy versions without knowing the owner

Many libraries shade their own bytecode parser. Adding a new ASM version to the application classpath may not replace the parser an agent uses. Upgrading the component that owns the agent/transformer to a release supporting the target JDK is usually more reliable.

## 25. ServiceLoader and SPI implementations

`ServiceLoader` loads interface implementations via service registration metadata. If an SPI interface is expanded while old providers remain on the classpath/module path, the following can happen:

~~~text
SPI v2
   |
   +-- NewProvider v2 -> complete methods
   |
   +-- LegacyProvider v1 -> missing new method
                              |
                              v
                        AbstractMethodError
                              when method is called
~~~

Verification steps:

1. Identify the service interface used at runtime.
2. List the providers and the artifacts containing them.
3. Inspect `META-INF/services` or `module-info.java` `provides` declarations.
4. Identify the provider actually selected.
5. Check which SPI version the provider binary was compiled against.
6. Upgrade/rebuild the provider or remove incompatible providers.
7. Test provider selection and execute all critical methods.

Do not just change the service registration name while ignoring the provider's ABI.

## 26. Default methods and binary compatibility in API design

When designing an SPI interface, adding an abstract method can be **risky for already-released implementations**.

### 26.1. Adding an abstract method

~~~java
public interface Decoder {
    String decode(byte[] bytes);

    // V2:
    void reset();
}
~~~

Old implementations lack `reset` and risk AME when the new method is called.

### 26.2. Adding a default method

~~~java
public interface Decoder {
    String decode(byte[] bytes);

    default void reset() {
        // Compatible implementation if semantics allow.
    }
}
~~~

Defaults can reduce recompilation requirements, but:

- Can conflict with a default from another interface.
- Can alter method selection.
- A no-op default can be wrong for business logic.
- Not every contract has a sensible fallback.

### 26.3. Adding a new interface to extend capability

One option is to separate the capability:

~~~java
public interface Decoder {
    String decode(byte[] bytes);
}

public interface ResettableDecoder extends Decoder {
    void reset();
}
~~~

Consumers can check for or require `ResettableDecoder` when the feature is actually needed. This is a design approach that avoids breaking old SPIs in some situations, though behavior must be defined if an implementation does not support the capability.

## 27. Identifying the actual class/method across jars

Once the fully qualified class name is known:

~~~bash
jar tf legacy-adapter.jar
~~~

Find the file:

~~~text
com/example/vendor/LegacyAdapter.class
~~~

Inspect methods:

~~~bash
javap -classpath legacy-adapter.jar -s -p \
  com.example.vendor.LegacyAdapter
~~~

If the method is absent from the class, that is not yet enough to conclude AME because the implementation may be inherited from a superclass or default interface. You must also inspect the hierarchy, interfaces, and method descriptors.

### 27.1. Do not rely solely on decompiled Java source

A decompiler can show Java-like output while hiding certain bridge/synthetic methods or JVM invocation details. For linkage errors, `javap -verbose`/`-c` generally provides evidence closer to the binary.

### 27.2. JARs with multiple copies of a class

A fat JAR, WAR, or multi-release JAR can contain multiple physical entries for one logical class. You must know **which entry the class loader loaded**, not merely find the class name somewhere inside an archive.

## 28. Bridge methods, covariant returns, and generics

The compiler can generate bridge methods to preserve polymorphism when generics undergo type erasure or when a subclass uses a covariant return.

Example:

~~~java
interface Supplier<T> {
    T get();
}

final class StringSupplier implements Supplier<String> {

    @Override
    public String get() {
        return "value";
    }
}
~~~

The compiler can emit a corresponding bridge method of the form `Object get()` to satisfy the binary method contract after erasure.

### 28.1. Errors when binaries are transformed

If a bytecode optimizer/shader or code generator mishandles bridge methods, old client binaries may fail to find the right target or dispatch unexpectedly. The error can be `NoSuchMethodError`, AME, or another linkage form depending on the actual binary.

### 28.2. Checking bridge flags

~~~bash
javap -classpath library.jar -p -verbose \
  com.example.StringSupplier
~~~

Look for `ACC_BRIDGE` and `ACC_SYNTHETIC`, along with method descriptors.

Do not conclude a bridge is missing just because decompiled source does not display it. Check the class file.

## 29. When is recompiling alone sufficient?

**Recompiling** can resolve the error when the implementation source remains valid under the new API or only needs matching bytecode/bridge methods regenerated.

However, it is not always enough:

- New interface added an abstract method that the implementation has not written -> compile will report missing implementation, source edits are required.
- Method changed from instance to static -> consumer source/semantics may need updates.
- Framework major upgrade changed API, SQL, or security behavior -> migration and tests are required.
- Public interface changed to a class -> extension redesign may be required.
- A third-party library lacks source or is EOL -> choose a replacement or maintained fork.
- Runtimes contain multiple old/new JARs -> packaging/dependency selection must be fixed.

**Do not fix merely by recompiling while ignoring contract behavior**. Code that runs is not guaranteed to remain functionally correct.

## 30. Remediation actions by root cause

| Root cause | Primary fix | Do not |
|---|---|---|
| Old implementation missing abstract method | Upgrade/rebuild implementation against new SPI | Catch `AbstractMethodError` and ignore |
| Instance ↔ static method change | Align client and library ABI | Add `--add-opens` |
| Two interface defaults conflict | Explicitly override method in implementing class | Pick behavior randomly |
| Mixed framework versions | Use BOM/compatible release set | Override individual transitive JARs arbitrarily |
| Old JAR on server classpath | Fix classloader/deployment ownership | Copy another duplicate JAR |
| Plugin uses old SPI | Upgrade plugin, version negotiation | Let plugin run until error surfaces |
| Faulty multi-release JAR variant | Fix versioned class and packaging | Test only the base class |
| Java agent generates bad bytecode | Upgrade agent, inspect transformation | Disable all tests long-term |
| Generated client/stub wrong version | Regenerate from matching schema/tool | Hand-edit generated files |
| Runtime JVM older than target | Upgrade runtime or lower target validly | Use module-opening flags |

If a system needs a temporary workaround, document the owner, risk, scope, deadline, and removal path. Do not turn a runtime conflict into a long-term dependency on accidental classpath ordering.

## 31. Prioritized diagnostic workflow

### Step 1: Collect the full exception

Record:

- Exact exception class.
- Verbatim message.
- Stack trace and caused-by chain.
- Failing thread/request/job.
- JDK version and container version.
- Commit, artifact checksum, deployment timestamp.

### Step 2: Find the owner method/field

Based on the message and bytecode:

- Class/interface containing the symbolic reference.
- Method name and descriptor.
- Runtime receiver class.
- Is there a static/instance mismatch?
- Are there multiple default methods?

### Step 3: Identify the binary actually loaded

Use class loading logs/CodeSource, container classpath, and JAR inspection.

### Step 4: Compare compile graph with runtime graph

Inspect direct/transitive dependency versions, BOMs, conflicts, shaded/nested JARs, and server/shared libraries.

### Step 5: Compare API and implementation ABIs

Use `javap -s -p -c -verbose` to check method signatures, flags, opcodes, and inheritance.

### Step 6: Create a minimal reproduction

Isolate one client and two API/implementation versions, or two interface defaults. Reproducing confirms the cause instead of guessing from a stack trace alone.

### Step 7: Fix at the source

Align versions/recompile implementation/regenerate output/change API in an officially supported way.

### Step 8: Verify on real runtime

Run the exact packaged artifact on the target JDK/container and run the test that triggers the previously failing code path.

### Step 9: Check regressions

Include integration, security, serialization, performance, failover, and plugin discovery where relevant.

### Step 10: Document and prevent recurrence

Pin versions, add compatibility tests and CI gates, remove temporary workarounds, and update runbooks.

## 32. What makes an effective minimal reproduction?

A reproduction should keep **only the components creating the mismatch** and remove unrelated factors.

For example, AME only needs:

~~~text
api-v1 Task.class
impl-v1 LegacyTask.class (compiled with api-v1)
api-v2 Task.class (added cancel)
client-v2 Main.class (compiled with api-v2)
runtime: client-v2 + impl-v1 + api-v2
~~~

When the reproduction still fails, the cause is more likely versioning/ABI than Spring configuration or networking.

### 32.1. Do not accidentally recompile everything

If the same Gradle task recompiles the old implementation against API V2, `javac` may reject source that fails the contract. That makes the reproduction fail **at compile time**, no longer reproducing the runtime AME.

To understand binary compatibility, you must retain the binary artifact built against the old version.

### 32.2. Use the actual runtime binary

Production failure may stem from an old plugin JAR. A reproduction using source recompiled with a new compiler may not repeat the error. Use the actual binary if sharing and testing allow.

## 33. What to test to prevent AbstractMethodError?

### 33.1. Interface implementation compatibility tests

If an SPI has multiple implementations:

- Load all supported implementations.
- Invoke the methods in the new contract.
- Run tests against the **exact target API version**.
- If plugins are separate artifacts, test plugin binaries against the new host runtime.
- Document unsupported plugin versions and reject loading early if possible.

### 33.2. Contract test example

~~~java
interface CancelableTask {
    void execute();
    void cancel();
}
~~~

A contract test can verify:

~~~java
void assertCancelable(CancelableTask task) {
    task.execute();
    task.cancel();
}
~~~

The snippet illustrates the idea; calling `cancel()` may require a test fixture, setup/cleanup, or specific state assertions.

### 33.3. Do not merely instantiate the class

Instantiating a provider does not necessarily invoke every interface method. Tests must actually exercise newly added methods or risky dynamic dispatch paths.

## 34. What to test to prevent IncompatibleClassChangeError?

Cases worth adding to regression tests:

- Old client binary running with new library.
- New client running with old library if that is a supported rollout scenario.
- Interface default methods in real inheritance graphs.
- Relevant reflection/MethodHandle/method references.
- Generated/proxy classes using static/instance invocations.
- Plugin loaders and service discovery.
- Multi-release JAR variants.
- External WAR/application server deployments.

If a public API changes instance ↔ static, decide **whether old binaries are supported**; if not, ensure every consumer is rebuilt/deployed in lockstep before introducing the new library at runtime.

## 35. CI binary compatibility gates

A library project with a public API needs mechanisms to detect ABI-breaking changes before release.

Techniques may include:

- Comparing public class/method/field signatures across releases.
- Comparing method descriptors and static flags.
- Comparing inheritance/interface relationships.
- Using a binary compatibility checker suited to the Java ecosystem.
- Compiling consumer fixtures against the old version and running them against the new version.
- Testing service implementations/plugin binaries.
- Testing the final shaded/fat JAR/WAR artifact.
- Running the target JDK matrix and module/classpath modes.

### 35.1. Do not rely solely on semantic versioning

SemVer can aid communication about compatibility, but a version number **does not itself prove binary compatibility**. Evidence and a support matrix are required.

### 35.2. Dependency locking aids reproducibility, not ABI validation

A lockfile preserves dependency graph versions, yet if an implementation JAR is inherently incompatible with an API, the error remains. Locks establish **which combination** ran, while compatibility tests establish how that combination behaves.

## 36. Test matrix by JDK and classpath

Example project moving from Java 11 → 17:

| Item | Java 11 | Java 17 | Evidence |
|---|---|---|---|
| Compile sources | Per support policy | PASS/FAIL | Build logs |
| App startup | PASS/FAIL | PASS/FAIL | Startup logs |
| API/implementation ABI | PASS/FAIL | PASS/FAIL | ABI report |
| SPI implementations | PASS/FAIL | PASS/FAIL | Contract tests |
| Client binary compatibility | PASS/FAIL | PASS/FAIL | Old/new client tests |
| Runtime dependency graph | Reviewed | Reviewed | Lockfile/tree |
| Plugin loading | PASS/FAIL | PASS/FAIL | Plugin tests |
| Framework integration | PASS/FAIL | PASS/FAIL | Integration tests |
| MRJAR class selection | If applicable | If applicable | Variant tests |
| Packaged deployment | PASS/FAIL | PASS/FAIL | JAR/WAR/container logs |
| Security/serialization | PASS/FAIL | PASS/FAIL | Contract fixtures |

`PASS/FAIL` cells are placeholders, not executed results. If the project drops Java 11 support, keeping a pre-upgrade baseline remains useful for distinguishing regressions, though an unbounded release test matrix does not need to be maintained.

## 37. JVM module system and accessibility

In Java 9+, JPMS can cause legacy code accessing internal packages to fail. Common related errors:

- `IllegalAccessError`.
- `InaccessibleObjectException` during deep reflection.
- `NoClassDefFoundError` if a dependent module/class is absent.

These errors are **not synonymous with direct AME or ICCE**, even though some subtypes share a class hierarchy relationship with ICCE.

### 37.1. When to use --add-opens?

`--add-opens` can grant deep reflective access in a specific manner, but it does not create a concrete method body and does not fix static/instance mismatches. An `AbstractMethodError` is not cured by opening a module package.

### 37.2. When to use --add-exports?

`--add-exports` affects module exports/access, not method descriptors or class/interface nature. If the binary ABI has changed, library and client must be aligned.

## 38. Hot redeploy, caching, and production-only errors

In an application server or plugin system:

- The container may hold an old version of a shared JAR.
- A new WAR is deployed, yet an exploded directory retains old files.
- Different class loaders use different artifacts.
- One service node has not been upgraded.
- A rolling update creates a window running mixed client/host versions.
- Generated classes/proxies are cached per classloader.
- MRJAR variants differ by node Java runtime.

### 38.1. Record versions per node

If an error occurs only on node B, compare:

~~~text
Node A:
  JDK 17
  app checksum X
  SPI 2.0
  implementation 2.0

Node B:
  JDK 17
  app checksum X
  SPI 2.0
  implementation 1.0  <-- mismatch candidate
~~~

This is a hypothetical example. In practice, collect checksums, resolved libraries, class loading evidence, and deployment logs.

### 38.2. Restarting sometimes only hides the error

A restart may cause the process to load the right library due to temporary classpath changes, but if artifact deployment remains inconsistent, the error can recur. Packaging/dependency ownership must be fixed to maintain the solution.

## 39. Common diagnostic mistakes

### 39.1. Catching Error and ignoring it

AME/ICCE usually signal misaligned runtime binary contracts. Catching to prevent crashes without fixing the source can cause data inconsistency and hide risk.

### 39.2. Treating the JDK as the sole culprit

JDK upgrades often accompany framework/library/tool updates. First identify the actual JAR class being loaded.

### 39.3. Reading only compileClasspath

Runtime, test, and WAR/server classpaths can differ. An old container-injected library does not appear on Gradle's compile classpath.

### 39.4. Comparing only method names

Method descriptors, static flags, inheritance, bridge methods, and opcodes matter. Matching method names do not guarantee matching ABIs.

### 39.5. Failing to exercise new code paths

Startup tests do not call newly added interface methods, so AME may only surface in production.

### 39.6. Forcing transitive dependencies to the latest version

Can create an ABI mismatch with a parent library. Prefer compatibility matrices and upgrading as a coherent set.

### 39.7. Relying on source instead of binary

Production may load an old JAR. Use `javap` and classloader logs to inspect the actual class file.

### 39.8. Confusing classloader constraints with missing methods

Some errors have messages about loader constraints, duplicate classes, or other type identity issues. Check the exact error subtype and resolution context.

### 39.9. Turning off bytecode instrumentation instead of fixing it

If an error only occurs when an agent is enabled, investigate the agent and bytecode transformation. Turning off coverage/monitoring may just mask a pipeline problem.

### 39.10. Rebuilding only the application without rebuilding plugins

If plugin implementations are released by another vendor/team, rebuilding the application does not fix old plugin binaries. Version/compatibility management is required.

## 40. Incident report template for AME/ICCE

~~~yaml
linkageIncident:
  application: "orders-service"
  error:
    class: "java.lang.AbstractMethodError"
    message: "paste-exact-runtime-message"
    callSite: "com.example.orders.Worker.shutdown"
    methodOwner: "com.example.spi.Service"
    methodDescriptor: "()V"
    receiverClass: "com.example.vendor.LegacyAdapter"
  environment:
    jdk: "record-exact-version"
    runtimeContainer: "record-version"
    artifactChecksum: "record-checksum"
  linkage:
    compileApiVersion: "unknown"
    runtimeApiVersion: "unknown"
    implementationVersion: "unknown"
    classLoader: "unknown"
    jarSource: "unknown"
  investigation:
    stackTraceCaptured: false
    dependencyGraphCompared: false
    javapDescriptorsCompared: false
    runtimeClassSourceVerified: false
    minimalReproductionCreated: false
  remediation:
    action: "upgrade-or-rebuild-implementation"
    owner: "application-team"
    rollbackPlan: "pending"
  validation:
    failingPathRetested: false
    integrationPassed: false
    packagedRuntimeVerified: false
  status: "under-investigation"
~~~

This is a **template** with placeholder values, not a real incident resolution record. For static/instance ICCE errors, replace the fields with the corresponding opcode, static flags, and method owner.

## 41. Diagnostician's checklist

- [ ] Confirmed whether the concrete error type is AME, direct ICCE, or another subclass.
- [ ] Saved the verbatim message/stack trace/JDK/container/version.
- [ ] Identified the failing method/field owner and descriptor.
- [ ] Identified the runtime receiver class, if the invocation has a receiver.
- [ ] Distinguished missing method, missing abstract implementation, and static/instance mismatch.
- [ ] Checked interface default method conflicts if the inheritance graph is involved.
- [ ] Checked class/interface nature and binary hierarchy.
- [ ] Compared source API with actual class files using `javap`.
- [ ] Checked bridge methods/covariant returns if relevant.
- [ ] Identified the JAR/nested JAR/container library that actually loaded the class.
- [ ] Inspected compileClasspath, runtimeClasspath, and testRuntimeClasspath.
- [ ] Inspected Maven/Gradle BOMs, transitive mediation, and overrides.
- [ ] Checked plugin/API/server-provided artifacts.
- [ ] Checked multi-release JAR variant for the running JDK if applicable.
- [ ] Checked Java agents/generated bytecode if the stack trace implicates them.
- [ ] Created a reproduction preserving old binary versions when needed.
- [ ] Selected compatible implementation/API versions or performed a full rebuild.
- [ ] Executed the failing code path on the real packaged runtime.
- [ ] Put appropriate contract/integration/rollout/rollback tests in place.
- [ ] Documented the root cause and added gates to prevent recurrence.

The checklist is a practical guide, **not evidence that a specific project has completed all steps**.

## 42. Quick comparison summary

| Question | AbstractMethodError | Direct IncompatibleClassChangeError |
|---|---|---|
| Is it linkage-related? | Yes | Yes |
| Inheritance relationship | Subclass of ICCE | Subclass of LinkageError |
| Common symptom | Receiver missing concrete implementation | Static/instance mismatch or ambiguous defaults |
| Could compilation have passed earlier? | Yes | Yes |
| Can it appear only when the method is called? | Yes | Yes |
| Typical root cause | New interface/abstract contract + old implementation | Client bytecode expectation differs from actual member/class nature |
| Useful evidence | Interface method + receiver class + hierarchy | Invocation opcode + flags + runtime class |
| Root fix | Upgrade/rebuild implementation or contract-compliant adapter | Align client/library ABI, resolve default conflict |
| Can `--add-opens` fix it? | No | No |
| Should the Error be caught and ignored? | No | No |

**Specifically:** when an exception displays `java.lang.AbstractMethodError`, it is simultaneously **an IncompatibleClassChangeError in terms of type hierarchy**, yet specific diagnostic analysis must rely on the AME subtype. The two errors should not be treated as completely independent branches.

## 43. Summary principles

- **`AbstractMethodError` is a subclass of `IncompatibleClassChangeError`**, and both are `LinkageError`/`Error`, not business exceptions.
- **AME typically reports a missing concrete implementation at method invocation**, such as an API adding an abstract method that an old implementation binary does not yet satisfy.
- **Direct ICCE typically reflects a binary form mismatch**, such as instance ↔ static method/field changes or conflicting interface default methods.
- **Related errors such as `NoSuchMethodError`, `IllegalAccessError`, and `NoSuchFieldError` are distinct cases** that must be diagnosed by subtype and message.
- **Passing compilation does not guarantee runtime linkage** when clients, APIs, and implementations are compiled/deployed from different versions.
- **Method descriptors, invocation opcodes, static/abstract flags, and class hierarchies** matter more than method names seen in source.
- **Use `javap` to inspect actual binaries, class loading logs to identify class sources, and dependency graphs to find mismatches**; do not rely solely on source/IDE.
- **JDK upgrades often expose pre-existing ABI issues through framework/dependency/plugin updates**, not necessarily because the new JVM is broken.
- **Classpaths, custom classloaders, external WAR/server libraries, and multi-release JARs** can produce runtime combinations different from build time.
- **Adding default methods can reduce risk from new abstract interface methods, yet can also introduce conflicts**, so testing remains necessary.
- **Rebuilding the proper implementation, choosing compatible sets, and testing the packaged runtime** are the preferred remedies, rather than catching and ignoring errors.
- **Adding binary compatibility checks, SPI contract tests, and cross-version tests to CI** helps catch errors before production.
- **Rolling upgrades and rollbacks must consider API implementations and plugin artifacts**, not only the application jar.

In **Java Advance Compatibility Migration**, effective diagnosis of `AbstractMethodError` and `IncompatibleClassChangeError` begins with the question: **"What did the class file compiled by the caller expect, and which implementation did the JVM actually load?"**. Once the API version, method descriptor, classloader, and runtime artifact are traced properly, most seemingly mysterious linkage errors become binary inconsistencies that can be reproduced, fixed at the source, and prevented from recurring through controlled build/test processes.
