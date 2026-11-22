# Distinguishing Class Loading, Bytecode Verification, and Linking Errors

A Java application can compile successfully on a new JDK yet fail at startup, when loading a plugin, or when entering a rarely used business branch. The stack trace may contain `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedClassVersionError`, `VerifyError`, `NoSuchMethodError`, or `IllegalAccessError`. These errors look similar in that they all relate to classes and bytecode, yet they reflect **different issues in the process by which the JVM brings compiled code to execution**.

During JDK migration, distinguishing the stages of *loading*, *verification*, *resolution*, and *initialization* will help determine whether to check the classpath, class file version, bytecode structure, API signatures, access permissions, or initialization logic. Merely looking at the exception name and adding a JAR or changing a JVM option often does not solve the real cause.

## 1. From `.class` File to Executed Code

Java source code is compiled into bytecode in a `.class` file. This file contains information about the class, fields and methods, bytecode instructions, the constant pool, and the metadata needed for the JVM to perform checks. When a class is used, the JVM must load the class definition and prepare it for execution.

According to the JVM model, the process has the following main concepts:

```text
         Java source code
                 |
               javac
                 v
        .class file / JAR
                 |
                 v
            1. Loading
                 |
                 v
            2. Linking
          +------+------+------+
          |             |      |
       Verify        Prepare  Resolve
                 |
                 v
        3. Initialization
                 |
                 v
          Code execution
```

The diagram above depicts the stages conceptually; it is not a guarantee that the JVM will resolve all references before running any piece of code. The JVM may perform some reference-resolution steps eagerly or lazily until they are used, according to the constraints of the specification.

| Concept | What does the JVM do? | Investigation question |
|---|---|---|
| Loading | Locates and creates the runtime definition of a class from class file data | Does the class exist and is it visible to the appropriate class loader? |
| Verification | Checks the validity and type safety of bytecode | Is the class file valid and does the bytecode satisfy JVM rules? |
| Preparation | Prepares runtime structures and default values for static fields | Are the metadata and structure of the class compatible with the runtime? |
| Resolution | Turns symbolic references into actual classes, fields, or methods | Does the right class/member exist, with a matching type and access permissions? |
| Initialization | Executes class initialization logic such as static initializers | Does initialization logic throw an exception or depend on missing configuration/services? |

Key point for binary compatibility: a `.class` file can be **found and loaded**, yet still fail at the bytecode verification, API resolution, or initialization step. Therefore, "the JAR is already on the classpath" is not synonymous with "binary compatible."

## 2. Loading: When the JVM Locates and Defines a Class

Loading is the process in which the JVM uses a class loader to locate class file data, interpret its format, and create the corresponding `Class` object. For an ordinary application, a class may reside in an output directory, a JAR, a module, or a source provided by a custom class loader.

Factors affecting loading include the class name, classpath/module path, the class loader used, artifact structure, and deployment environment. These factors can change when upgrading the JDK, switching frameworks, moving to containers, or changing plugin mechanisms.

### 2.1. `ClassNotFoundException`: Looking Up a Class by API but Not Finding It

`ClassNotFoundException` is a checked exception that typically appears when the program **explicitly requests loading a class by name** and the class loader cannot find a matching definition. Typical APIs include `Class.forName(...)` and `ClassLoader.loadClass(...)`.

Example:

```java
public class PluginLoader {
    public static void main(String[] args) throws Exception {
        Class<?> plugin = Class.forName(
            "com.example.plugins.InvoicePlugin"
        );
        System.out.println(plugin.getName());
    }
}
```

If the class `com.example.plugins.InvoicePlugin` is not found by the class loader, the call may throw:

```text
java.lang.ClassNotFoundException:
    com.example.plugins.InvoicePlugin
```

Common causes are a missing JAR, a wrong package/class name, a plugin configuration error, an unpackaged artifact, or the active class loader not seeing the JAR.

You should not conclude based solely on whether the class exists somewhere on the machine. The question to answer is: **can the class loader of the failing execution path find that exact class?**

### 2.2. `NoClassDefFoundError`: A Required Class Cannot Be Provided at Runtime

`NoClassDefFoundError` is a `LinkageError` that can appear when a class was previously referenced from bytecode, yet the required definition is unavailable at runtime. For example, the application is compiled against `payment-api.jar`, but at runtime it lacks a transitive dependency that a class in that JAR needs.

```text
Compile:
  application.jar + payment-api.jar + payment-core.jar

Runtime:
  application.jar + payment-api.jar
                            |
                            v
               missing class from payment-core.jar
                            |
                            v
                 NoClassDefFoundError
```

This case can occur when the build succeeds but the runtime artifact is packaged without a dependency. The error can also appear after the class has already failed during initialization; in that case, you need to read the message and the *cause* to find the initial error.

Example:

```text
java.lang.NoClassDefFoundError: com/example/core/PaymentRule
```

The name in the message typically uses slashes `/` according to the internal name in the class file. Cross-reference it with the corresponding Java class name `com.example.core.PaymentRule`.

### 2.3. Why Are the Two Errors Easily Confused?

| Characteristic | `ClassNotFoundException` | `NoClassDefFoundError` |
|---|---|---|
| Type | Checked exception | `LinkageError` |
| Common context | Calling an API to load a class by name | JVM needs the class while linking/using a compiled class, or the class failed initialization |
| Example | `Class.forName("...Plugin")` | Compiled binary references a class from a JAR missing at runtime |
| First investigation | Class name, class loader, classpath/module path | Missing class, runtime dependencies, prior cause, initialization |

The two errors are not two synonymous names. In some systems, a `ClassNotFoundException` from a class loader can be the underlying cause leading to a `NoClassDefFoundError` where the JVM needs that class. You must read the entire `Caused by` chain, not just the first exception.

### 2.4. Class Loaders Can Make a Class "Exist Yet Be Unusable"

The JVM identifies a class by the pair **binary name and defining class loader**. Two classes with the same name defined by two different class loaders are two distinct types at runtime.

In applications using plugins, servlet containers, or custom class loaders, this can produce errors such as `ClassCastException`, `LinkageError`, or errors related to loader constraints. For example, a plugin carrying a copy of an API that the host also loads can cause an object from the plugin not to cast to the same type name loaded by the host.

When investigating, besides the class name, check the class loader and the location of the JAR being loaded. Do not try to fix it by adding a second copy of the JAR to the classpath without knowing the loader resolution order.

## 3. Class File Format: `UnsupportedClassVersionError` and `ClassFormatError`

Before executing bytecode, the JVM must understand the structure of the `.class` file. Every class file has a *major version* indicating the bytecode format version. An older runtime cannot run a class file that requires a version newer than what it supports.

### 3.1. `UnsupportedClassVersionError`

Suppose a class is built with JDK 21 targeting Java 21, yet is deployed onto JVM 17. JVM 17 does not support Java 21's class file major version 65 and may throw:

```text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
```

Some common major versions:

| Java Version | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

`UnsupportedClassVersionError` reports a mismatch between the class file format and the running JVM. It differs from `NoSuchMethodError`: here, the JVM has not even reached invoking a specific method of a new API.

The appropriate fix is to run on a runtime that supports that class file, or recompile targeting a supported Java level. When using a newer compiler to produce artifacts for an older runtime, prefer `javac --release N` instead of only configuring the bytecode target, because `--release` also restricts the Java SE APIs that can be used.

```bash
# Example: compile with a newer JDK while targeting Java 17
javac --release 17 -d out src/com/example/App.java
```

`--release` does not guarantee that external dependencies are also compatible with Java 17. A dependency JAR built for Java 21 can still cause `UnsupportedClassVersionError` when its classes are loaded.

### 3.2. `ClassFormatError`

`ClassFormatError` indicates that the class file data does not conform to the format required by the JVM. For example, a bytecode transformation tool produces a corrupted `.class` file, writes an incorrect constant pool, or creates invalid metadata structures.

During JDK migration, the cause may lie in a bytecode library, obfuscator, agent, code generator, or build plugin that does not yet support the class file structure of the new JDK. A damaged JAR or a class file corrupted during packaging can also lead to this situation.

Inspect the actual artifact being loaded, the version of the tool creating/transforming classes, and whether there are multiple copies of the same-named class in the execution path. If the error only occurs at runtime after an agent intervenes, compare the class before and after transformation.

## 4. Verification: Bytecode Must Be Valid According to JVM Rules

Verification is the step where the JVM checks bytecode against the rules of the specification. It helps ensure that instructions do not use the operand stack and local variables with the wrong types, do not jump to invalid positions, and obey the constraints necessary for the JVM to execute safely.

Normal Java source code compiled by an appropriate `javac` usually produces valid bytecode. Verification errors appear much more often when class files are manipulated by bytecode tools, agents, obfuscators, or generators.

### 4.1. `VerifyError`

`VerifyError` is an error in the `LinkageError` family indicating that the verifier detected a problem in the bytecode. Some messages may mention stack map frames, the operand stack, data types, or invalid control-flow branches.

Illustrative error message:

```text
java.lang.VerifyError: Bad type on operand stack
  Exception Details:
    Location:
      com/example/Service.process()V @12: invokevirtual
```

To investigate, determine **which class file the verifier actually processed**. If the application has an agent or class transformer, the bytecode on disk may differ from the bytecode actually defined in the JVM. If you have just upgraded the JDK, check the compatibility of ASM, Byte Buddy, CGLIB, obfuscators, or bytecode-generation tools that the application uses.

`VerifyError` does not mean the compiler found a syntax error in Java source code. Nor should you by default use flags to disable verification as a fix; the right approach is to find the class file or tool that produced invalid bytecode.

### 4.2. Verification Differs from Resolution

A class can be structurally valid and pass verification yet still fail to find a method referenced by the bytecode. In that case, the issue lies in resolution/linkage, not the bytecode verifier.

Conversely, a class can contain all necessary class and method names yet fail verification because its internal instruction structure is invalid. Both are binary-related errors, but their fixes differ.

## 5. Resolution and Linking: References Must Match the Runtime API

In bytecode, a method call or field access typically uses a symbolic reference. This reference specifies the class name, member name, and corresponding descriptor. During resolution, the JVM locates the actual class/member and checks conditions regarding types, invocation style, and access permissions.

For example, the descriptor of a method taking `String` and returning `int` has the form:

```text
(Ljava/lang/String;)I
```

A call compiled to use `compute(String):int` will not automatically turn into `compute(Object):int` or `compute(String):long` if the runtime library changes the signature. The JVM does not re-perform overload resolution the way the compiler does.

### 5.1. `NoSuchMethodError`: The Required Method No Longer Has the Right Descriptor

Suppose version 1 of a library has:

```java
package com.example.api;

public class NameFormatter {
    public String label() {
        return "ready";
    }
}
```

The client application compiles against version 1:

```java
package com.example.client;

import com.example.api.NameFormatter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new NameFormatter().label());
    }
}
```

Then version 2 replaces the method with a different overload:

```java
package com.example.api;

public class NameFormatter {
    public String label(String prefix) {
        return prefix + "ready";
    }
}
```

If the old `Main.class` is kept and the v1 library JAR is replaced with v2, the client bytecode still requests `NameFormatter.label:()Ljava/lang/String;`. That method no longer exists in the v2 class, leading to the error:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.NameFormatter.label()'
```

This is a binary compatibility error. When recompiling the client source against library v2, the compiler typically reports that the method is no longer compatible; however, the runtime error occurs here because **the compiled client was not recompiled**.

### 5.2. Experimenting with a Compiled Consumer

To clearly see the difference, create three source files at the paths:

```text
api-v1/com/example/api/NameFormatter.java
api-v2/com/example/api/NameFormatter.java
client/com/example/client/Main.java
```

Each API directory contains one version of the class from the example above. Then run:

```bash
# Compile and package API version 1
javac -d out-v1 api-v1/com/example/api/NameFormatter.java
jar --create --file api-v1.jar -C out-v1 .

# Compile the client against API v1
javac -cp api-v1.jar -d out-client client/com/example/client/Main.java

# Compile and package API version 2
javac -d out-v2 api-v2/com/example/api/NameFormatter.java
jar --create --file api-v2.jar -C out-v2 .

# Run the old client binary with API v2
java -cp api-v2.jar:out-client com.example.client.Main
```

On Windows, the classpath separator is `;` instead of `:`:

```powershell
java -cp 'api-v2.jar;out-client' com.example.client.Main
```

The key point is not to recompile `Main.class` after replacing the JAR. Only in this way can you verify whether an already-released client binary runs with the new API. Similarly, do not leave `api-v1.jar` on the runtime classpath at the same time, because the loaded class might not be the version 2 class you intend to test.

### 5.3. `NoSuchFieldError`: A Field Is Removed, Renamed, or Changes Type

Bytecode also stores references to fields by name and descriptor. If a field was previously declared as:

```java
public static int RETRY_LIMIT = 3;
```

but the new library version removes the field or changes its type to `long`, the old binary may report `NoSuchFieldError`. If only access visibility changes while keeping the name and descriptor, the error may be `IllegalAccessError` instead of `NoSuchFieldError`.

One note for `static final` constants with a constant value under the compile-time constant rules: the compiler may embed the value directly into consumer bytecode (*inlining*). Therefore, changing a constant value in a library will not necessarily cause an old client to see the new value. This is a form of behavioral compatibility risk even though the binary may not report a linkage error.

### 5.4. `IllegalAccessError`: The Member Exists but Access Is No Longer Permitted

Suppose a library changes a `public` method to `protected`, package-private, or `private` while keeping its name and descriptor. A previously compiled client can find the method yet no longer has permission to call it. The JVM may throw `IllegalAccessError` when checking access permissions.

Similarly, in an application using the module path, a package that is no longer `exports`-ed to the consumer module can cause access to a public type to be denied. You must examine access modifiers, packages, class loaders, subclass relationships, and module configuration together.

Adding `--add-opens` only pertains to deep access via reflection; it is not a general way to fix ordinary linkage errors. For public-type access between modules, `exports` conditions and readability are what need to be checked.

### 5.5. `IncompatibleClassChangeError` and `AbstractMethodError`

`IncompatibleClassChangeError` is the family of errors occurring when a class/member definition at runtime does not match the assumptions embedded in the binary at compile time. Forms such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, and `AbstractMethodError` all belong to this group.

For example, a binary compiled to call an instance method while the runtime supplies an incompatible static method structure, or an interface/class changing in a way that makes the invocation no longer valid, can trigger an error in this family.

`AbstractMethodError` can appear when a call requires a concrete implementation yet the runtime cannot find a matching implementation, for example in combinations of classes/interfaces compiled with different versions.

You should not fix `AbstractMethodError` by guessing a missing method in the current source; compare the binaries and the class/interface hierarchy of the artifacts actually being loaded.

## 6. Initialization: A Class Can Load and Link, Yet Fail Initialization

Class initialization takes place when the JVM executes the necessary initialization steps, including the logic of static initializers and assigning static fields according to initialization code. This stage is distinct from loading and verification.

Example:

```java
public class FeatureFlags {
    static final String REGION;

    static {
        REGION = System.getenv("APP_REGION");
        if (REGION == null) {
            throw new IllegalStateException("APP_REGION is missing");
        }
    }
}
```

The first use that forces the class to initialize can lead to `ExceptionInInitializerError`, with the *cause* being `IllegalStateException`. Subsequent uses in the same runtime may encounter `NoClassDefFoundError` with a message indicating that the class could not be initialized.

When seeing:

```text
java.lang.NoClassDefFoundError: Could not initialize class ...
```

do not jump to the conclusion that a JAR is missing. Look for the first preceding exception in the log and the cause of the initialization failure: environment variables, configuration files, database connections, data parsing errors, library versions, or static dependencies.

### 6.1. `Class.forName` Can Both Load and Initialize

A normal `Class.forName("com.example.FeatureFlags")` call requests initializing the class after locating and appropriately linking it, so it can expose static initializer failures. If you want to test locating/loading a class without yet initializing it, there is an overload:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName(
    "com.example.FeatureFlags", false, loader
);
```

The `false` parameter requests not initializing the class as part of this call. Even so, the class or related dependencies may still need to be loaded, checked, or linked as required by the JVM. You should not treat this operation as a test proving the class will definitely initialize or work successfully.

## 7. Symptom-Based Diagnostic Diagram

When an application fails after a JDK or dependency upgrade, you can start from the main exception and locate the corresponding stage:

```text
Application fails when using a class
                   |
                   v
      Inspect exception and cause
                   |
      +------------+-------------+
      |            |             |
 ClassNotFound  Unsupported      VerifyError /
 Exception     ClassVersion     ClassFormatError
      |            |             |
      v            v             v
 Check         Check major   Check bytecode,
 loader,       version and   generator, agent,
 classpath     target JVM    transformer tool
                   |
                   v
      If the class can be loaded
                   |
          +--------+--------+
          |                 |
  NoSuchMethod/Field   IllegalAccess /
  /AbstractMethod      IncompatibleClassChange
          |                 |
          v                 v
  Compare descriptor, Compare modifiers,
  dependency/JAR      class/interface, module
          |
          v
  If initialization error: inspect ExceptionInInitializerError
  or NoClassDefFoundError (Could not initialize class)
```

The diagram helps guide investigation, but it does not replace reading the full stack trace. A higher-level error may wrap the underlying error; for example, a framework may throw a bean creation exception while the inner cause is `NoSuchMethodError` or `ExceptionInInitializerError`.

| Notable Error | Typically Related Stage/Aspect | Evidence to Check First |
|---|---|---|
| `ClassNotFoundException` | Loading a class by name | Class name, class loader, JAR, and runtime configuration |
| `NoClassDefFoundError` | Unable to supply required class definition or class failed initialization | Missing dependency, error message, and prior cause |
| `UnsupportedClassVersionError` | Class file / JVM format | Major version and actual runtime version |
| `ClassFormatError` | Class file structure | Artifact, bytecode generator/transformer, `.class` file |
| `VerifyError` | Bytecode verification | Bytecode at error location, stack map frames, transformer/agent |
| `NoSuchMethodError` | Method resolution | Method descriptor in consumer and API of runtime JAR |
| `NoSuchFieldError` | Field resolution | Field name/descriptor in consumer and runtime API |
| `IllegalAccessError` | Access check during linking | Modifiers, package, module exports, and class loader |
| `AbstractMethodError` | Linking / method dispatch | Class/interface hierarchy and binaries from different versions |
| `ExceptionInInitializerError` | Class initialization | Static initializer and underlying exception |

## 8. Using JDK Tools to Verify Bytecode and Linking

When investigating, prioritize evidence from the **actual deployed artifact**. Source code on the current branch may not match the class files running in production.

### 8.1. Listing Classes in a JAR with `jar`

```bash
jar --list --file application.jar
```

You can search directly for the class to check in the list, for example `com/example/api/NameFormatter.class`. If using an executable/fat JAR, classes and dependencies may reside in a dedicated structure such as a directory containing nested JARs. In that case, you need to understand how the framework's launcher constructs the classpath/runtime class loader.

If a class appears in multiple JARs, determine which copy is actually loaded by the JVM. Merely having the filename inside an archive is not enough to conclude the runtime is using that class.

### 8.2. Checking Class File Version with `javap -verbose`

```bash
javap -verbose -classpath application.jar com.example.App
```

In the output, look for lines similar to:

```text
minor version: 0
major version: 61
```

Major version 61 corresponds to Java 17. Be sure to use the exact `.class` file or exact JAR that the runtime loaded. If the application has multiple versions of a class within the same JAR, you must inspect the actual class matching the target runtime.

### 8.3. Viewing Method Descriptors with `javap -s -p`

```bash
javap -classpath api-v1.jar -s -p com.example.api.NameFormatter
javap -classpath api-v2.jar -s -p com.example.api.NameFormatter
```

`-s` prints member descriptors; `-p` displays non-public members as well. Comparing two versions helps detect methods whose parameters, return type, name, or access visibility changed.

Example:

```text
public java.lang.String label();
  descriptor: ()Ljava/lang/String;
```

If the new version only has `label(String)`, the descriptor already differs. This explains why the old client bytecode cannot automatically switch to the new call.

### 8.4. Inspecting Consumer Bytecode and Constant Pool

```bash
javap -c -verbose -classpath out-client com.example.client.Main
```

`-c` shows the bytecode instructions, while `-verbose` displays information such as the constant pool, method references, and major version. For `NoSuchMethodError`, look for `invokevirtual`, `invokestatic`, or the corresponding method-invocation instructions, then read the `Methodref`/`InterfaceMethodref` reference.

For example, a reference line may show:

```text
Methodref com/example/api/NameFormatter.label:()Ljava/lang/String;
```

Cross-reference this reference against the class in the actual runtime JAR. This is the way to verify exactly which method the binary requires, rather than inferring from current source.

### 8.5. Checking Dependencies with `jdeps`

`jdeps` analyzes static dependencies of classes/JARs. For example:

```bash
jdeps --recursive application.jar
```

If you need to provide paths to external dependency JARs:

```bash
jdeps --class-path 'libs/*' --recursive application.jar
```

`jdeps` is useful for identifying packages or modules that an artifact statically references. The tool cannot fully detect classes loaded only via reflection, string names, service loaders, or dynamic plugin mechanisms. Therefore, it is an input to investigation, not a certificate that every runtime class is present.

For multi-release JARs, pay attention to Java-version-specific classes under `META-INF/versions/` and choose an appropriate analysis configuration, such as `jdeps`'s `--multi-release` option.

### 8.6. Tracing Classes Loaded at Runtime

On modern JDKs, unified logging can record class-loading activity:

```bash
java -Xlog:class+load=info -cp 'libs/*:app.jar' com.example.Main
```

On Windows, adjust the classpath separator to `;`. Class loading logs help identify which JAR or module a class was loaded from. Depending on the JDK version and log level, the printed information may vary.

Filter the log by the failing class and match it to the exact running process. In a system with multiple JARs containing same-named classes, this is often direct evidence showing which copy was chosen at runtime.

## 9. Causes Specific to JDK Migration

### 9.1. Building with a New JDK While the Runtime Is Still Old

A new JDK can produce class files that an older runtime does not understand. If only the compiler is changed without updating the runtime, the application may encounter `UnsupportedClassVersionError`. Use `--release` to target a supported Java level and run tests on the lowest still-supported runtime.

### 9.2. APIs or Modules Scheduled for Removal

Some APIs/modules previously bundled with the JDK have been removed in later releases. For example, the Java EE and CORBA modules were removed from the JDK starting in Java 11. Applications relying on previously bundled JAXB may encounter compile or runtime errors if matching dependencies are not added.

When investigating, determine whether the class originally belonged to the JDK or to an external dependency, and whether the new JDK still provides it. Do not try to solve it by changing class loaders when the problem is that the library is no longer in the runtime.

### 9.3. Frameworks and Bytecode Libraries Not Yet Supporting the New JDK

Frameworks, agents, or proxy-generating libraries may generate/transform class files. When they do not yet understand a new class file version or the runtime's verifier rules, the application may hit `ClassFormatError`, `VerifyError`, or other class-loading errors.

Cross-check the versions of Spring, Hibernate, Byte Buddy, ASM, Mockito, coverage tools, and monitoring agents against the target JDK. If the error only appears when a test runner or agent is active, check that tool before changing business code.

### 9.4. Changing a Dependency While the Client Binary Was Not Recompiled

An application compiled with version A of a library may run with version B at runtime due to transitive dependency conflicts, classpath ordering, or packaging an artifact differently from build time. This is a common cause of `NoSuchMethodError` and `NoSuchFieldError`.

Compare the build-time dependency tree against the actual list of JARs at runtime. Check differences among `compileOnly`, `provided`, `runtimeOnly`, and packaged dependencies when using Maven/Gradle. You should not rely solely on dependency declarations while ignoring how the artifact is produced and deployed.

### 9.5. Module Path and Reflection Changing Access Permissions

When moving from the classpath to the module path, module readability, `exports`, and `opens` can alter access capabilities to APIs. A direct call error may be `IllegalAccessError`, whereas deep reflection may throw `InaccessibleObjectException`.

Distinguish clearly: ordinary bytecode access requires visibility/module-export conditions; deep reflection requires package-opening conditions. The `--add-exports` and `--add-opens` options do not serve the same purpose and do not replace upgrading libraries that access JDK internals.

### 9.6. Multi-Release JARs and Version-Selected Classes

A multi-release JAR can contain base classes and dedicated classes for Java 9 and later under `META-INF/versions/N/`. The runtime can select the class matching its version. Therefore, the same JAR can supply different class definitions on Java 11 and Java 21.

When an error only appears on one runtime, inspect the manifest and versioned entries in the JAR, and verify the actual class loaded. You should not inspect only the base class and conclude that the runtime API is identical across all JDKs.

## 10. Investigation Workflow Applicable in Projects

To avoid fixing in the wrong place, you can investigate in the following order.

### Step 1: Record the Actual Environment

Collect the JDK version and vendor, command line, classpath/module path, container information, dependencies, and deployed JARs. If there are multiple instances, identify the exact instance producing the error.

```bash
java -version
```

This command should be run inside the same image/container or host that the application uses, rather than only on a developer's machine.

### Step 2: Find the Root Error in the Stack Trace

Read the first meaningful exception and the `Caused by` chain. Especially for `NoClassDefFoundError: Could not initialize class`, look for the initial initialization error. If a framework reports a bean-creation error, look for a cause that is a class loading/linkage error.

### Step 3: Verify the Artifact Containing the Class and Bytecode Version

Check the JAR with `jar --list`; check major version, methods/fields, and descriptors with `javap`. If there are multiple copies of a class, determine which copy the runtime loaded from the class loading log.

### Step 4: Compare the Consumer Binary Against the Runtime API

For `NoSuchMethodError`/`NoSuchFieldError`, use `javap -c -verbose` to inspect the reference requested by the consumer and `javap -s -p` to inspect members in the runtime library. For `IllegalAccessError`, compare access flags, packages, and module exports.

### Step 5: Inspect the Class Loader and Dependency Tree

Check which class loader loaded the class, whether duplicate copies exist, and what the JAR order is. Inspect artifacts outside the build, container layers, plugin folders, fat JARs, or dependencies excluded from runtime.

### Step 6: Reproduce with the Old Binary

Keep the consumer artifact compiled against the old dependency version; replace just one dependency with the new version and run the relevant flows. This shows whether binary compatibility is broken. Recompiling the consumer immediately may mask a runtime error that an already-deployed binary will encounter.

### Step 7: Fix the Root Cause and Run Appropriate Tests

Depending on the error, you may need to switch runtimes, use `--release`, add missing dependencies, remove duplicate JAR versions, upgrade frameworks/agents, retain APIs with old descriptors, fix module exports, or adjust initialization logic. Then run compatibility tests on the target JDK and still-supported runtime versions.

| Confirmed Cause | Remediation Approach |
|---|---|
| Class is not in runtime artifact | Package/supply the dependency properly and check the class loader |
| Class file too new for JVM | Choose an appropriate runtime or recompile with a supported `--release` |
| Invalid bytecode | Fix/upgrade the bytecode generation or transformation tool, re-release the artifact |
| Method/field changed descriptor | Preserve a compatible API or rebuild all consumers against the new contract |
| Access permission narrowed | Restore a compatible API surface or migrate consumers to a supported public API |
| Runtime uses wrong dependency version | Fix dependency resolution/packaging and confirm the loaded JAR |
| Static initializer failed | Fix the root initialization error, configuration, and required dependencies |

## 11. Misconceptions That Often Prolong Incidents

**"If the class is in the JAR, it will definitely run."** The JVM must still understand the format, verify bytecode, resolve references, and initialize the class when needed. The presence of a class alone does not guarantee executability.

**"`ClassNotFoundException` and `NoClassDefFoundError` are both just missing JARs."** They have different contexts; `NoClassDefFoundError` can also appear after initialization fails. You must read the root cause.

**"`NoSuchMethodError` means a source method is missing."** Bytecode needs a method with the exact name and descriptor at runtime. Current source having a same-named overload does not guarantee satisfying an old reference.

**"If the application compiles successfully, it is binary compatible."** Compilation usually produces new binaries. It does not verify that previously released JARs/clients still link against the new API.

**"The JVM will resolve every method immediately at startup."** The JVM has the right to perform resolution at times permitted by the specification; an error may only surface when a rarely used code path is triggered.

**"Changing `JAVA_HOME` fixes all class errors."** `JAVA_HOME` only affects environment selection according to how a tool uses it. It does not by itself resolve missing dependencies, changed descriptors, class loader conflicts, or misgenerated bytecode.

**"Just swap the framework, no need to check agents or plugins."** Bytecode transformation tools, test runners, coverage tools, and APM agents can also load or generate classes. Inspect the entire runtime chain when an error only appears in one environment.

## 12. Checklist Before Concluding Binary Compatibility

- [ ] Recorded actual JDK, vendor, build number, classpath/module path, and runtime artifacts.
- [ ] Read the entire stack trace and `Caused by` chain.
- [ ] Distinguished class loading, class file format, verification, resolution, and initialization errors.
- [ ] Identified the class loader and JAR actually supplying the failing class.
- [ ] Checked the major version against the target JVM version.
- [ ] Compared method/field descriptors of the consumer binary and the runtime library.
- [ ] Checked access modifiers and module exports/opens if there is an access error.
- [ ] Checked transitive dependencies, duplicate JARs, and runtime packaging.
- [ ] Considered multi-release JARs, bytecode generators, and agents where relevant.
- [ ] Ran the old consumer artifact against the new dependency without recompiling.
- [ ] Tested dynamic class loading flows, plugins, reflection, and rarely used initialization.
- [ ] Documented results and the remediation tied to the exact cause.

## 13. Conclusion

Class-related errors in Java appear at different stages. `ClassNotFoundException` usually relates to a call to load a class by name; `NoClassDefFoundError` relates to failing to supply a required class definition or a class having failed initialization; `UnsupportedClassVersionError` and `ClassFormatError` point to format problems; `VerifyError` relates to bytecode rules; and errors such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, and `AbstractMethodError` usually indicate that linking against the runtime API no longer matches compile-time assumptions.

In JDK migration, you need to verify **the right artifact, the right class loader, the right bytecode, and the right dependency version**. Tools like `jar`, `javap`, `jdeps`, and class-loading logs help turn assumptions into evidence. Testing both new source and previously compiled consumer binaries will catch errors that a successful build or a simple startup might miss.
