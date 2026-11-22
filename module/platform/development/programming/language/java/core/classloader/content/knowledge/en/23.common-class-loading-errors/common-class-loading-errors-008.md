# `AbstractMethodError` and `IncompatibleClassChangeError` in Java: binary compatibility and class loader errors

## 1. Understanding the two error types properly

`AbstractMethodError` and `IncompatibleClassChangeError` are errors in the `LinkageError` family. They typically appear when the JVM is running a set of `.class` files that are **no longer binary-compatible with one another**, for example when a program was compiled against API version A but at runtime loads version B of that API.

Both have very practical implications in applications that use third-party libraries, plugins, application servers, custom class loaders, redeployment, or hot-reload mechanisms: **successful compilation does not guarantee that all classes will be linked and methods invoked successfully after deployment**.

Important inheritance relationship:

```text
java.lang.Throwable
  └─ java.lang.Error
       └─ java.lang.LinkageError
            └─ java.lang.IncompatibleClassChangeError
                 ├─ java.lang.AbstractMethodError
                 ├─ java.lang.NoSuchMethodError
                 ├─ java.lang.NoSuchFieldError
                 ├─ java.lang.IllegalAccessError
                 └─ java.lang.InstantiationError
```

Note: sibling classes in the tree are not the same single error; each type provides different diagnostic clues. For example, `NoSuchMethodError` indicates that a referenced method could not be resolved as expected; `AbstractMethodError` relates to **invoking** a method for which the runtime cannot find a matching implementation; whereas a direct `IncompatibleClassChangeError` can occur when the runtime sees that a method is actually an instance method while the bytecode requires a static one.

| Characteristic | `AbstractMethodError` | Direct `IncompatibleClassChangeError` |
|---|---|---|
| Nature | Attempting to invoke a method for which the dispatch step cannot find a valid concrete implementation | Detecting a structural change in a class/method/field that is incompatible with previously compiled bytecode |
| Typical example | Removing a `default` implementation on an interface and replacing it with an abstract method, while an old implementation has not been recompiled | Changing a `static` method to an instance method while an old caller still uses `invokestatic` |
| When detected | May occur only when the method is called/resolved, not necessarily at application startup | May occur during resolution/linking or when the corresponding instruction executes |
| Fundamental fix | Recompile and distribute the contract, implementation, and caller **in sync** | Restore the binary contract or update the caller and runtime library in sync |

**Relationship to remember:** `AbstractMethodError extends IncompatibleClassChangeError`. Therefore, a `catch (IncompatibleClassChangeError e)` block also catches `AbstractMethodError`, but when investigating you must preserve the **specific error type**, full stack trace, and class loader information. These errors are `Error`s, not checked exceptions; catching them to "ignore" them usually leaves the application running in an inconsistent state.

## 2. Binary compatibility: why does compilation pass while runtime fails?

A `.class` file does not contain the full source code of its dependent classes. It contains **symbolic references** (class/interface names, method/field names, type descriptors), along with invocation bytecodes such as `invokestatic`, `invokevirtual`, `invokeinterface`, or `invokespecial`. At runtime, the JVM must resolve and execute those references against the class definitions that are **actually loaded**.

Example:

```text
Build time:
  Client.class  ──compiled against──> Library API v1

Runtime:
  Client.class  ──JVM resolves to───> Library API v2
                                       ^
                                       incompatible method change
```

If `Client.class` retains a static-call opcode while `Library` in v2 only has an instance method with the same name/descriptor, the old bytecode is not automatically rewritten to become an instance call. Similarly, if an invocation expects a method to have an implementation while at runtime only an abstract method exists, the JVM cannot invent the missing body on its own.

**Source compatibility is different from binary compatibility.** Re-running `javac` on all updated sources can catch errors at compile time; however, if you only swap out a JAR while keeping old classes, errors may surface when running in production. Conversely, there are source-incompatible changes that remain binary-compatible with previously compiled callers. The severity and type of error depend on the specific change.

**The class loader is the decisive factor:** a runtime class is identified by its **binary name + defining class loader**, not just its package/class name. Parent delegation, classpath order, module path, fat JARs, plugin applications, and isolated loaders all determine which version of a class is actually selected.

## 3. Experiment A — reproducing `AbstractMethodError` with Java 17+

In v1, `Contract.message()` is a `default` method, so `Provider` does not need to implement it itself. The old caller compiles and invokes it validly. When `Contract` is replaced at runtime with v2 containing an abstract method, `Provider.class` from v1 still has no implementation; the call fails.

### Experiment structure

```text
ame/
  v1/
    src/demo/
      Contract.java
      Provider.java
      Runner.java
    classes/                 (generated by javac)
  v2/
    src/demo/
      Contract.java
    classes/                 (generated by javac)
```

File **`ame/v1/src/demo/Contract.java`**:

```java
package demo;

public interface Contract {
    default String message() {
        return "default-v1";
    }
}
```

File **`ame/v1/src/demo/Provider.java`**:

```java
package demo;

public class Provider implements Contract {
    // Valid in v1 by inheriting the default method.
}
```

File **`ame/v1/src/demo/Runner.java`**:

```java
package demo;

public class Runner {
    public static void main(String[] args) {
        Contract provider = new Provider();
        System.out.println(provider.message());
    }
}
```

File **`ame/v2/src/demo/Contract.java`**:

```java
package demo;

public interface Contract {
    String message(); // v2: no longer has a default implementation
}
```

From the directory containing `ame/`, run on Unix/Linux/macOS (Bash):

```bash
mkdir -p ame/v1/classes ame/v2/classes

javac -d ame/v1/classes \
  ame/v1/src/demo/Contract.java \
  ame/v1/src/demo/Provider.java \
  ame/v1/src/demo/Runner.java

javac -d ame/v2/classes ame/v2/src/demo/Contract.java

# Baseline: all v1 classes.
java -cp ame/v1/classes demo.Runner

# Mix the v2 contract with v1's Provider and Runner.
java -cp ame/v2/classes:ame/v1/classes demo.Runner
```

The baseline prints correctly:

```text
default-v1
```

The mixed run **terminates with an error**; the beginning of the stack trace on HotSpot JDK 17+ looks like:

```text
Exception in thread "main" java.lang.AbstractMethodError: ...
    at demo.Runner.main(Runner.java:...)
```

The detailed JVM description, line numbers, and stack trace formatting may vary depending on the JDK version. What remains constant in this scenario is the **error type** `java.lang.AbstractMethodError`. The example was tested on JDK 21: the receiver `demo.Provider` neither defines nor inherits an implementation for the abstract `demo.Contract.message()`.

Why does the old bytecode run all the way to the call site?

1. The old `Runner.class` contains a call to `demo.Contract.message:()Ljava/lang/String;`.
2. At runtime, `Contract` is loaded from `ame/v2/classes` because this path appears **before** `ame/v1/classes`.
3. The old `Provider.class` does not implement `message()` itself; at compile time it relied on the `default` method of the v1 interface.
4. With the v2 interface, there is no longer a matching concrete implementation to dispatch to. The JVM throws `AbstractMethodError` when executing the call.

If you recompile `Provider.java` from v1 against `Contract` from v2, `javac` will catch the missing implementation unless the code is fixed or the class is declared abstract. That explains why the error can "only happen at runtime" with mixed-version binaries.

**Do not conclude that all changes from a method to abstract look the same.** A key point in the scenario above is that the caller/implementation was compiled independently of the new contract. Changing a method from concrete to abstract in a superclass can also produce `AbstractMethodError` according to JLS `13.4.16`.

## 4. Experiment B — reproducing `IncompatibleClassChangeError` when static changes to instance

In v1, the caller's bytecode uses `invokestatic`. In v2, the method with the same name/descriptor is now an instance method, so the old instruction is no longer valid for the new method.

### Structure

```text
icce/
  v1/
    src/demo/
      Library.java
      Client.java
    classes/
  v2/
    src/demo/
      Library.java
    classes/
```

File **`icce/v1/src/demo/Library.java`**:

```java
package demo;

public class Library {
    public static String mode() {
        return "static-v1";
    }
}
```

File **`icce/v1/src/demo/Client.java`**:

```java
package demo;

public class Client {
    public static void main(String[] args) {
        System.out.println(Library.mode());
    }
}
```

File **`icce/v2/src/demo/Library.java`**:

```java
package demo;

public class Library {
    public String mode() {
        return "instance-v2";
    }
}
```

Compile and run (Bash):

```bash
mkdir -p icce/v1/classes icce/v2/classes

javac -d icce/v1/classes \
  icce/v1/src/demo/Library.java \
  icce/v1/src/demo/Client.java

javac -d icce/v2/classes icce/v2/src/demo/Library.java

java -cp icce/v1/classes demo.Client
java -cp icce/v2/classes:icce/v1/classes demo.Client
```

The baseline prints correctly:

```text
static-v1
```

The second command fails (HotSpot JDK 17+, the message part may vary):

```text
Exception in thread "main" java.lang.IncompatibleClassChangeError: Expected static method ...
    at demo.Client.main(Client.java:...)
```

Try analyzing the bytecode stored in the v1 caller:

```bash
javap -classpath icce/v1/classes -c demo.Client
```

In the `main` method there will be an `invokestatic` instruction calling `demo/Library.mode:()Ljava/lang/String;`. This is proof that the old caller **encoded a static call**; simply editing `Library`'s source code and swapping the JAR at runtime will not turn the caller's bytecode into an instance call.

In Windows PowerShell/cmd, when the classpath has two directories, replace `:` with `;` and wrap the classpath in quotes if needed, for example:

```powershell
java -cp "icce/v2/classes;icce/v1/classes" demo.Client
```

Separate paths are used solely for illustration; in real projects, classes with the same name may reside in two JARs, generated class directories, or different class loaders.

## 5. What happens inside the JVM and class loader?

Overview of the steps:

1. **Loading:** the class loader supplies the bytes defining the class by name and delegation mechanism. With multiple URLs/JARs, the search order within a loader can affect which version is loaded.
2. **Linking:** verification and resolution ensure that symbolic references in the bytecode can bind to runtime definitions. Resolution may be performed lazily, so errors sometimes only surface when execution reaches a specific code branch.
3. **Method invocation/dispatch:** `invokestatic`, `invokevirtual`, `invokeinterface`, and `invokespecial` have different requirements. If the method kind or dispatch result is invalid, the JVM reports the appropriate linkage error.
4. **No silent reloading of a class with the same name:** a standard loader does not "swap the bytes of an already-defined class" just because a JAR on disk has changed. Plugin frameworks/restart loaders may create a **new loader** carrying the new version of the class, while the old loader still retains the old definition.

In an app server or plugin container, simply asking "is the right JAR on disk?" is not enough; you need to know **which loader defines which class**, whether a parent loader takes precedence in loading first, and which dependencies the artifact build process packaged.

A subtle example:

```text
Bootstrap / platform loader
   └── Application loader → API v1
           └── Plugin loader → implementation v2
```

If the plugin loader delegates the API to the parent, the plugin may actually use **API v1** even though v2 is present in the plugin directory. In the reverse design, a caller in the parent may resolve a class implementation against a different contract than expected. The actual error could be `AbstractMethodError`, `IncompatibleClassChangeError`, `ClassCastException`, `NoClassDefFoundError`, or another `LinkageError`, depending on type constraints and opcodes; **do not attribute every class loader error to the two exceptions in this article**.

In particular: two independent loaders that both define `demo.Contract` create **two different runtime types**. Casting an instance across loader boundaries may throw `ClassCastException`, not necessarily `IncompatibleClassChangeError`. Cases of loader constraint violations may be reported as `LinkageError`. You need to read the **exact exception class and stack trace**.

## 6. Types of binary changes that commonly cause related errors

| Change between build and runtime | Possible symptoms | Hints |
|---|---|---|
| Concrete/default implementation is removed and method becomes abstract | `AbstractMethodError` when invoking the old implementation | Compare the interface/superclass and the implementation at runtime |
| Method `static` ↔ instance | `IncompatibleClassChangeError` | Compare the invoke opcode and the modifiers of the actually loaded method |
| Field `static` ↔ instance | `IncompatibleClassChangeError` when accessing the field with the old opcode | Compare `getstatic/putstatic` with `getfield/putfield` |
| Method deleted or name/descriptor/return type changed so old symbolic reference cannot resolve | `NoSuchMethodError` (a subclass of `IncompatibleClassChangeError`) | Compare the JVM descriptor signature, not just the method name |
| Field deleted or descriptor changed | `NoSuchFieldError` | Check the actual field signature on the runtime class |
| Member access changed to no longer be permitted | `IllegalAccessError` | Check Java access, module/package, and runtime class |
| Interface changed to class or vice versa | Possibly `IncompatibleClassChangeError` | Check the runtime kind of the reference and the relevant bytecode |
| Two loaders load a class with the same name but different identities | Possibly `ClassCastException` or another loader constraint error | Print the defining loader, trace class loading, check parent delegation |

Note: the table describes **typical symptoms** and does not guarantee that every JVM version or every set of binaries will produce one specific error. The JVM may detect another violation earlier, depending on the first instruction executed and how references are resolved.

## 7. Investigation workflow for errors in real-world applications

### Step 1 — record the observed cause, do not guess from one line of the stack trace

Record in full:
- **Full exception class**, message, `Caused by` lines (if any), and the stack trace of the relevant thread.
- Method name, class/interface, descriptor if available, JDK version, and caller location.
- The API version that the **caller was built against** and the API version that the JVM is actually loading.
- Deployment timing: did the error only appear after a JAR update, hot reload, restart, redeploy, or classpath change?

The stack trace typically points to the **failing call site**, not necessarily to the JAR file **containing the incompatible runtime definition**.

### Step 2 — confirm the class-loading path with runtime evidence

If you can modify the program directly, place the check in a part of the code guaranteed to still execute:

```java
import java.net.URL;

public final class ClassOrigin {
    public static void describe(Class<?> type) {
        System.out.println("Class: " + type.getName());
        System.out.println("Loader: " + type.getClassLoader());
        var domain = type.getProtectionDomain();
        var source = domain == null ? null : domain.getCodeSource();
        URL location = source == null ? null : source.getLocation();
        System.out.println("Code source: " + location);
    }
}
```

This is an **illustrative utility** meant to invoke `ClassOrigin.describe(SomeClass.class)` from another program; it has no standalone `main`. `getClassLoader()` may return `null` for classes loaded by the bootstrap loader. `CodeSource` may also be `null`; frameworks/shading/nested JARs can mean the location is not simply a single file on disk. Therefore, use JVM logs and build metadata to cross-check when the output is not clear enough.

You can enable logging when starting a HotSpot JDK 17 application:

```bash
java -Xlog:class+load=info -cp app-classes:lib/* com.example.Main
```

The path/classpath is an **illustrative example**; replace it with your actual runtime path. Read the lines related to the failing class to see where the JVM loaded its definition from. On JDK 17, `java -verbose:class ...` is also useful. If using the module path or a custom class loader, also record the loader identity when possible; multiple JARs with the same version string do not guarantee the same class bytes.

### Step 3 — inspect binary signatures and instructions

Run `javap` on the **deployed artifact** and on the **artifact that the caller was compiled against**:

```bash
javap -classpath path/to/api-v1.jar -p -s com.example.Library
javap -classpath path/to/api-v2.jar -p -s com.example.Library
javap -classpath path/to/app-classes -c -p com.example.Client
```

What to compare:

- Class or interface; superclass and implemented interfaces.
- `abstract` / `default` / `static` / `final` and access modifiers.
- Method name and **descriptor**, for example `()Ljava/lang/String;` differs from `()V`.
- Caller's opcodes: `invokestatic`, `invokevirtual`, `invokeinterface`; corresponding field-access opcodes.
- Whether the concrete method inherited by the implementation actually exists in the runtime contract.

In a plugin/app server, running `javap` on a local JAR is a **build diagnosis** and is not a substitute for proving the JVM actually selected that JAR. Use class-loading logs and loader identity to connect the evidence.

### Step 4 — verify the dependency tree and deployment package contents

Cross-check Maven/Gradle dependency resolution against the **runtime artifact**, because a dependency declaration is not necessarily the class bytes actually packaged:

- Gradle: `./gradlew dependencies --configuration runtimeClasspath`, `./gradlew dependencyInsight --dependency ten-thu-vien --configuration runtimeClasspath` (be sure to select the right module/configuration).
- Maven: `mvn dependency:tree` and the corresponding scope/shading/assembly configurations.
- For a Spring Boot executable JAR, inspect the libraries in `BOOT-INF/lib`; for an app server, inspect shared library directories and deployment modules; for plugins, inspect the JARs visible to parent/child loaders.
- Compare the versions of API, SPI, providers, adapters, generated proxies, and callers. Watch out for transitive dependencies pulling in an older version, the same API being packaged multiple times, or deploying individual JAR replacements while the JVM is still running an older version.

### Step 5 — fix consistently and run regression checks

The proper fix is to **restore a consistent binary contract** across modules: choose compatible versions of the API and implementation; rebuild affected callers/providers; ensure the runtime receives the right set of class bytes; and then recreate the class loader or restart the process when needed to clear previously loaded old classes.

Do not fix this by catching `AbstractMethodError` and arbitrarily calling another method, tweaking the classpath "until it runs," or adding `System.gc()`. Garbage collection cannot fix bytecode with wrong references, nor can it turn an abstract method into a concrete one. `Class.forName` only loads/initializes a class according to how it is called and may help surface some issues early; it does **not** resolve binary incompatibility on its own.

If you must maintain multiple plugin versions, design a stable API boundary, clear adapters, and consistent versioning and parent delegation rules. Also verify integration tests **using the exact runtime JAR set**, rather than only compiling tests against a different dependency set.

## 8. Examples of distinguishing errors and wrong conclusions

**Wrong:** "`AbstractMethodError` happens because someone forgot to override an abstract method; just edit the code so the compiler catches it."  
**Right:** With a clean source build, the compiler normally catches a missing implementation. When runtime combines `.class` files compiled from **different contract versions**, a missing implementation may only surface at dispatch time.

**Wrong:** "`IncompatibleClassChangeError` definitely means there are two JARs with the same name on the classpath."  
**Right:** Duplicate JARs are only one possible cause. A single JAR of the wrong version relative to the compiled caller also causes the error; moreover, a class loader can load classes from directories, modules, or other bytecode sources.

**Wrong:** "Just clear the Gradle/Maven cache and it will go away."  
**Right:** A corrupted cache is a hypothesis that should only be checked when there is evidence for it. The root cause is usually a binary version mismatch; verify the dependency graph, artifact contents, and the source from which the JVM loads classes.

**Wrong:** "If the error happens when Spring creates a bean, it must be a dependency injection error."  
**Right:** The framework may simply be where the first method call is triggered. Read the underlying cause in the stack trace and distinguish linkage errors from bean configuration errors.

**Wrong:** "Two `Class<?>` instances with the same `getName()` are the same type."  
**Right:** Check `==` and the defining loader; the same name with different loaders can be two different runtime classes.

**Wrong:** "Just restart without needing to know the cause."  
**Right:** A restart may cause a new loader to read the right artifacts and temporarily resolve a partial redeploy, but if the deployment still contains an incompatible set of bytecodes, the error will recur.

## 9. Quick diagnostic checklist

1. Is the actual exception `AbstractMethodError`, a direct `IncompatibleClassChangeError`, or another subclass (`NoSuchMethodError`, `IllegalAccessError`, etc.)?
2. Which API version was the caller built against? Which `Class<?>` is actually loaded at runtime, from which loader and code source?
3. Were there changes from `default/concrete → abstract`, `static ↔ instance`, method descriptors, class/interface, superclass, or implementation?
4. What opcodes does `javap -c` of the caller contain? What methods/fields does `javap -p -s` of the runtime class report?
5. Are there multiple versions of the API/plugin, shared libraries, parent delegation, shaded JARs, app-server libraries, or stale hot-reload loaders?
6. Have **all related binaries** been rebuilt/redeployed and integration tests run with the same dependency set as production?

## 10. Self-check questions

**Question 1:** Why does `Provider` in Experiment A compile validly against v1 yet throw `AbstractMethodError` when run with the v2 interface?  
**Answer:** v1 has a `default` implementation; v2 only has an abstract declaration. The old `Provider.class` does not implement `message()` itself and was not recompiled.

**Question 2:** In Experiment B, why does the runtime not automatically call `new Library().mode()` instead of `Library.mode()`?  
**Answer:** `Client.class` contains `invokestatic` according to the v1 contract; the JVM does not rewrite the program on its own, instantiate an object, and replace the instruction to match v2.

**Question 3:** Does `AbstractMethodError` belong to the `IncompatibleClassChangeError` family?  
**Answer:** Yes. It is a direct subclass of `IncompatibleClassChangeError`, and both belong to `LinkageError`.

**Question 4:** Seeing two classes with the same name `com.example.Api` from two loaders, can you conclude for sure that `AbstractMethodError` will be thrown?  
**Answer:** No. You need to know the specific references/loader constraints and instructions; they may be two valid separate runtime types, or raise a `ClassCastException`/another linkage error.

**Question 5:** What are the three most important pieces of evidence when debugging?  
**Answer:** (i) full exception class/stack trace at the call site; (ii) version and loader/code source of the runtime class; (iii) signature/modifiers + bytecode opcodes and the set of artifacts that the caller was actually built against.

## Official references

- [Java SE 17 — `AbstractMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html): error definition, part of the `IncompatibleClassChangeError` family.
- [Java SE 17 — `IncompatibleClassChangeError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IncompatibleClassChangeError.html): error caused by an incompatible change to a class definition.
- [JLS 17, Chapter 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): especially `13.4.16` on concrete-to-abstract and `13.4.18` on static/instance methods.
- [JVMS 17, Chapter 6 — JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): `invokestatic`, `invokeinterface`, and other instructions for explaining caller bytecode.
