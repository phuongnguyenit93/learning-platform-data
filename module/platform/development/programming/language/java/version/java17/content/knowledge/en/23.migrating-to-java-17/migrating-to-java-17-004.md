# Auditing Reflection, Bytecode Generation, and Annotation Processors When Upgrading to Java 17

> **Topic:** Java 17  
> **Chapter:** Migrating to Java 17  
> **Goal:** Identify areas affected when upgrading an application to Java 17, especially deep reflection, JDK internal API access, runtime bytecode generation, and compile-time annotation processors. Learn how to audit dependencies, migrate to supported APIs, and use module-opening flags only as controlled transitional workarounds.

## 1. Why audit these three areas?

Java 17 continues strong enforcement of the module boundaries introduced in Java 9. Applications that ran on older Java versions can fail when moving to Java 17 because libraries or application code:

- Use reflection to access private fields, constructors, or methods inside JDK packages.
- Depend on classes in internal packages such as `sun.*`, `com.sun.*`, or packages not exported by their module.
- Generate bytecode and define classes using class loaders or internal JDK APIs.
- Use annotation processors that access internal implementation classes of `javac`.
- Rely on illegal access behaviors that previously emitted warnings yet still functioned in earlier Java releases.

These problems often do not show up at compile time. An application can compile cleanly yet fail at runtime when executing a rarely used feature, when a framework initializes proxies, when an ORM reads private fields, or when the compiler invokes an annotation processor.

In Java 17, three layers require inspection:

1. **Reflection:** does code access non-public members or un-opened packages?
2. **Bytecode generation:** do class-generating libraries use supported APIs and respect module boundaries?
3. **Annotation processing:** do processors use public compiler APIs or depend on internal implementations?

## 2. Key change: strong encapsulation in Java 17

### 2.1. From JPMS to strong encapsulation

Java 9 introduced the Java Platform Module System (JPMS). A named module can control:

- Which packages are **exported** so other modules can access public APIs.
- Which packages are **opened** so other modules can perform deep reflection.
- Which modules are read via `requires`.

Java 9 through Java 15 provided a transitional grace period for some legacy JDK packages. Starting in Java 16, strong encapsulation became the default; Java 17 completes this policy under JEP 403.

As a result, applications can no longer rely on deep access into arbitrary JDK implementation classes. A reflective call can throw `java.lang.reflect.InaccessibleObjectException` if the target module's package is not open to the calling module.

### 2.2. `--illegal-access` is no longer a fix in Java 17

In transitional releases, the `--illegal-access` flag controlled warnings or permitted certain illegal reflective accesses to older JDK packages.

In Java 17, this option is obsolete and no longer restores permissive access as in earlier Java versions. Do not use commands such as:

```bash
java --illegal-access=permit -jar app.jar
```

to resolve module access errors on Java 17. Identify the target module/package, upgrade the library, or open the exact package using the appropriate module mechanism when genuinely needed.

### 2.3. Export and open are two different permissions

| Directive | Effect |
|---|---|
| `exports p` | Allows other modules to access public APIs in package `p` per Java access rules |
| `opens p` | Allows deep runtime reflection on members of package `p` |
| `open module m` | Opens every package of the module for deep runtime reflection |
| Neither exported nor opened | Other modules have neither normal access nor deep reflection access to that package |

Example:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.entity to org.hibernate.orm.core;
}
```

Other modules can use public APIs in `com.acme.model.api`. Hibernate is granted deep reflection access to `com.acme.model.entity`. Other packages preserve their encapsulation boundaries.

Do not use `opens` when code only needs to call public APIs; likewise, do not assume `exports` allows frameworks to access private fields.

## 3. Auditing reflection

### 3.1. APIs to search for in source code

Look for common reflection calls:

```java
field.setAccessible(true);
method.setAccessible(true);
constructor.setAccessible(true);
AccessibleObject.setAccessible(...);
```

In addition, inspect:

- `Class.getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.
- `Field.get`/`Field.set`, `Method.invoke`, `Constructor.newInstance`.
- `MethodHandles.privateLookupIn` and `Lookup.find*`.
- `Class.forName` with dynamically configured class names.
- ORM, dependency injection, JSON/XML mappers, serializers, proxies, and mocking frameworks.

Not every reflection call is problematic. Accessing public APIs or reflecting within the same module typically continues to work. The goal is to find crossings over module boundaries or dependencies on JDK internals.

### 3.2. Example of accessing a private field

Suppose a class resides in an application module:

```java
package com.acme.model;

public class Customer {
    private String name;
}
```

Within the same module or when the package is appropriately opened, code can use:

```java
Field field = Customer.class.getDeclaredField("name");
if (field.trySetAccessible()) {
    Object value = field.get(customer);
}
```

`trySetAccessible()` returns `false` if reflective access cannot be enabled. It lets code handle closed packages gracefully without relying on exceptions for control flow.

With `setAccessible(true)`, if access cannot be enabled due to module boundaries, the call can throw `InaccessibleObjectException`.

### 3.3. Use canAccess instead of legacy checks

Java 9 added `AccessibleObject.canAccess(Object)` to check whether a reflection object can access a member for a specific receiver:

```java
Field field = Customer.class.getDeclaredField("name");
boolean accessible = field.canAccess(customer);
```

For static members, pass `null` as the receiver:

```java
Field version = Config.class.getDeclaredField("VERSION");
boolean accessible = version.canAccess(null);
```

`canAccess` checks accessibility in the current context; it does not open packages or grant new permissions.

### 3.4. Conditional checking and access handling

Example of explicit error handling:

```java
Field field = Customer.class.getDeclaredField("name");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package com.acme.model is not open for deep reflection");
}

String name = (String) field.get(customer);
```

Error messages should name the module/package that must be opened to operate. Avoid swallowing the failure and returning a default value, as that can silently corrupt ORM or serialization data.

### 3.5. Open packages via module descriptor

If you own the module containing the class and a framework genuinely needs deep reflection, declare `opens` in `module-info.java`:

```java
module com.acme.application {
    requires org.hibernate.orm.core;

    opens com.acme.application.entity
        to org.hibernate.orm.core;
}
```

Only the entity package is opened, and only to the Hibernate module. This expresses intent clearly in the module descriptor and fits when you control the module's source.

If the application does not use a module descriptor (running on the classpath), the unnamed module is open for reflection under JPMS rules. However, when a library attempts to access an internal package of a named JDK module, strong encapsulation still applies.

### 3.6. Use --add-opens when the module descriptor cannot be modified

The runtime `--add-opens` option opens a package of a source module to a target module:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar legacy-app.jar
```

Meaning:

- `java.base` is the source module.
- `java.lang` is the opened package.
- `ALL-UNNAMED` represents all unnamed modules (typically code on the classpath).

If the target module is named, specify that module name instead of `ALL-UNNAMED`:

```bash
java --add-opens java.base/java.lang=com.acme.application -m com.acme.application/com.acme.Main
```

Multiple packages can be opened with multiple options:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED -jar legacy-app.jar
```

This is a runtime workaround. It reduces encapsulation of the opened package for the target module. Restrict it to the exact package and recipient module; do not open entire modules when only one package is needed.

### 3.7. --add-exports is for accessing public APIs in unexported packages

`--add-exports` and `--add-opens` are not interchangeable:

- `--add-exports` grants standard access to public types/members of an unexported package.
- `--add-opens` grants runtime deep reflection into a package.

Example:

```bash
java --add-exports java.base/sun.security.x509=ALL-UNNAMED -jar legacy-app.jar
```

This option only exposes the specific package in the module graph/runtime. It does not turn an internal API into a stable, supported API. If the JDK alters or removes internal classes, the application can still break.

When compiling code that references an unexported package, the corresponding compiler option can be used:

```bash
javac --add-exports java.base/sun.security.x509=ALL-UNNAMED ...
```

Do not add both `--add-exports` and `--add-opens` out of habit. Grant only the specific permission required after diagnosing the error.

### 3.8. MethodHandles and privateLookupIn

Code using `MethodHandles` is also subject to module rules. For example:

```java
MethodHandles.Lookup lookup =
        MethodHandles.privateLookupIn(Customer.class,
                MethodHandles.lookup());

VarHandle nameHandle = lookup.findVarHandle(
        Customer.class, "name", String.class);
```

`privateLookupIn` produces a lookup with private access to the target class when module conditions are satisfied. When caller and target belong to different modules, the caller must read the target module and the target package must be open to the caller module; the original lookup must also hold sufficient privilege.

If the package is not open, the call can fail with `IllegalAccessException`. Do not assume `MethodHandles` bypasses strong encapsulation just because it does not call `setAccessible`.

### 3.9. Prefer public APIs over internal reflection

Before adding `--add-opens`, consider:

- Is there a dedicated public method or API replacement?
- Has the framework released a newer version supporting Java 17?
- Can the framework be configured to use constructors/setters instead of private field access?
- Can an adapter inside the owning module expose a clean API?
- Can SPI/services replace classpath scanning and reflective access into implementations?

Opening packages should be a deliberate, scoped decision with a plan for removal once dependencies are upgraded.

## 4. Auditing JDK internal APIs and dependencies

### 4.1. Find references to JDK internals with jdeps

`jdeps` detects many static references to JDK internal APIs:

```bash
jdeps --jdk-internals --recursive app.jar
```

If dependencies reside in a library directory:

```bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
```

For multi-release JARs, specify the target release version to analyze:

```bash
jdeps --jdk-internals --multi-release 17 --recursive app.jar
```

Output identifies which application classes depend on which internal packages and suggests replacement APIs if the JDK provides them.

### 4.2. Limitations of jdeps

`jdeps` analyzes dependencies inferable from bytecode and archive structure. It cannot reliably detect every dynamic access:

- `Class.forName("sun....")` where class names are assembled from configuration.
- Reflection on field/method names read from external files.
- Class names supplied at runtime by plugins or frameworks.
- Bytecode generated after startup.
- Code paths reached only in production or rarely enabled features.

Combine `jdeps` with source searches, dependency audits, integration tests, and runtime observation.

### 4.3. Find deprecated APIs with jdeprscan

`jdeprscan` scans classes/JARs for usage of deprecated Java platform APIs:

```bash
jdeprscan --release 17 --for-removal app.jar
```

This complements `jdeps` while answering a different question:

- `jdeps --jdk-internals`: does the application depend on JDK internal APIs?
- `jdeprscan`: does the application use deprecated or deprecated-for-removal APIs?

Deprecated APIs are not necessarily internal; internal APIs are not necessarily marked deprecated. Run both during an upgrade audit.

### 4.4. Inspect module descriptors and dependencies

For modular JARs:

```bash
jar --describe-module --file app.jar
```

List runtime modules:

```bash
java --list-modules
```

Review required modules and dependencies. Applications running on the classpath may lack descriptors; in those cases `jdeps` remains helpful for spotting internal references, though it does not replace reviewing modules and reflection.

## 5. Auditing bytecode generation

### 5.1. What is bytecode generation?

Several frameworks create classes at runtime rather than using only pre-compiled classes. Common scenarios include:

- Dynamic proxies for interfaces.
- Proxies/subclasses for ORM lazy loading.
- Mock objects in tests.
- Dependency injection and AOP.
- Serializers generating optimized accessors or adapters.
- Frameworks generating classes to invoke methods/fields faster than reflection.

Libraries often use ASM, Byte Buddy, Javassist, or JDK APIs to emit bytecode. When moving to Java 17, verify both support for reading new class file versions and how generated classes are defined within modules/packages.

### 5.2. Check bytecode library versions

For every dependency capable of generating classes:

1. Check releases supporting Java 17.
2. Read release notes regarding JPMS, strong encapsulation, reflection, and class definition.
3. Update frameworks to currently supported versions.
4. Test proxy creation, mocking, ORM entities, and serialization.
5. Check logs for warnings or exceptions when classes are defined.

Avoid upgrading ASM or Byte Buddy standalone if a wrapping framework imposes its own version requirements. Use dependency versions published as supported by the framework.

### 5.3. Class loaders, packages, and modules during class definition

Classes are defined within a class loader and bound to a runtime package/module under JVM rules. Two classes sharing the same package name but loaded by different class loaders do not necessarily belong to the same runtime package.

This affects:

- Accessing package-private classes/members.
- Accessing protected members.
- Defining subclasses/proxies in the target's package.
- Generated code's access to other modules.

If a framework defines generated classes in a separate class loader, the generated class may fail to access package-private members the framework expects. Errors typically appear at runtime when the class is defined or when the JVM verifies/links it.

### 5.4. Prefer MethodHandles.Lookup.defineClass

Java 9 added `MethodHandles.Lookup#defineClass(byte[])` to define a class in the same package, class loader, and module as the lookup class, provided the lookup holds appropriate package privileges.

Illustrative example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
byte[] generatedClassBytes = generateClassBytes();

Class<?> generated = lookup.defineClass(generatedClassBytes);
```

Key requirements:

- Bytecode must be valid and the class name must belong to the same package as the lookup class.
- The lookup must have `PACKAGE` access.
- The class is defined in the lookup class's class loader and runtime package/module.
- The class name must not collide with an already defined class in that loader.

This API fits when the generated class belongs in the package of the class owning the lookup. It is not meant for defining classes into arbitrary packages of other modules.

### 5.5. Lookup and privateLookupIn

When a lookup needs private access to another class, `MethodHandles.privateLookupIn` can be used if module access permits:

```java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(
                Customer.class,
                MethodHandles.lookup());
```

If the target resides in a different module, the target package must be open to the caller's module and the caller must read the target module. This is a module rule and cannot be bypassed merely by generating bytecode.

### 5.6. Hidden classes

Java 15 introduced hidden classes via `Lookup#defineHiddenClass`. Hidden classes suit framework/runtime implementation classes that do not need to be discovered by ordinary binary names.

Conceptual example:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                generatedClassBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Key characteristics of hidden classes:

- Cannot be loaded normally via `Class.forName` by binary name.
- Not discoverable via standard class loader enumeration.
- Can join the lookup class's nest when `NESTMATE` is used and conditions are met.
- Well-suited for internal proxies/adapters that do not require stable application-facing class names.

Not every framework needs hidden classes. Use this API only when the class generation design calls for it and libraries support Java 17.

### 5.7. Avoid internal APIs for defining classes

Older frameworks may use reflection or internal APIs to invoke mechanisms like `ClassLoader#defineClass` with elevated access, or reference `jdk.internal.*` packages.

In Java 17, internal packages are guarded by strong encapsulation. Prefer:

- `MethodHandles.Lookup#defineClass`.
- `MethodHandles.Lookup#defineHiddenClass` where suitable.
- Public `java.lang.reflect.Proxy` for interface proxies.
- Modern versions of ASM/Byte Buddy/Javassist supporting Java 17.

Avoid broadly opening `java.base/jdk.internal.*` packages to keep an old framework running without assessing the risk.

## 6. Dynamic proxies and module boundaries

### 6.1. Standard Proxy API

`java.lang.reflect.Proxy` is the public API for creating interface proxies:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("findName")) {
        return "Java 17";
    }
    return null;
};

Service service = (Service) Proxy.newProxyInstance(
        Service.class.getClassLoader(),
        new Class<?>[] { Service.class },
        handler);
```

The Proxy API is the right choice when implementing interfaces dynamically. There is no need to hand-roll bytecode or call internal JDK APIs for this common pattern.

### 6.2. Proxies in named modules

When interfaces belong to named modules, generated proxy classes must obey module and package visibility rules. The JDK creates the proxy class in an appropriate module/package based on interface visibility.

If a proxy implements non-public interfaces or interfaces from packages/modules with restricted visibility, verify:

- Are the interfaces public?
- Are the packages exported to the consuming module?
- Do the interfaces satisfy same-package/module constraints under Proxy rules?
- Is a framework attempting deep reflection against the generated proxy implementation?

Never assume a proxy class always lives in the application's package or can access every internal member of its interfaces.

## 7. Auditing annotation processors

### 7.1. When do annotation processors run?

Annotation processors execute during compilation to read annotations, inspect program models, and optionally emit new source files or resources.

Standard APIs include:

- `javax.annotation.processing`: processor interfaces, round environment, messager, and filer.
- `javax.lang.model`: type, element, annotation, and package models.
- `com.sun.source.*`: public compiler tree API for inspecting syntax trees, provided by the `jdk.compiler` module.

Processors run inside the compiler JVM, so processor dependencies and annotation-handling code must also be compatible with JDK 17.

### 7.2. Distinguish public APIs from javac internals

Prefer using:

- `javax.annotation.processing.AbstractProcessor`.
- `ProcessingEnvironment`, `RoundEnvironment`, `Filer`, `Messager`.
- `TypeElement`, `ExecutableElement`, `VariableElement`, `Types`, `Elements`.
- `com.sun.source.tree` and `com.sun.source.util` when public AST analysis is needed.

Avoid depending on internal implementations such as:

- `com.sun.tools.javac.code.*`.
- `com.sun.tools.javac.tree.*`.
- `com.sun.tools.javac.processing.*`.
- `com.sun.tools.javac.util.*`.

Internal compiler packages are not stable APIs for external processors. In Java 17, strong encapsulation can block reflective or direct access to unexported modules. Opening internal compiler packages via flags should be strictly a temporary workaround while upgrading the processor.

### 7.3. Example processor using standard APIs

Minimal processor:

```java
package com.acme.processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

public class AuditProcessor extends AbstractProcessor {
    @Override
    public Set<String> getSupportedAnnotationTypes() {
        return Set.of("com.acme.annotations.Audit");
    }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.RELEASE_17;
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (TypeElement annotation : annotations) {
            var elements = roundEnv.getElementsAnnotatedWith(annotation);
            for (var element : elements) {
                processingEnv.getMessager().printMessage(
                        javax.tools.Diagnostic.Kind.NOTE,
                        "Found @Audit on " + element);
            }
        }
        return false;
    }
}
```

This processor uses only standard APIs to find annotated elements and emit diagnostics. It does not need access to internal javac classes.

### 7.4. Registering a processor on the classpath

If the processor is packaged as a standard JAR, register it via a service provider file:

```text
META-INF/services/javax.annotation.processing.Processor
```

The file contains the processor class name:

```text
com.acme.processor.AuditProcessor
```

When compiling, place the processor JAR on the processor path:

```bash
javac --processor-path processor.jar -d out src/com/acme/App.java
```

`--processor-path` (or `-processorpath`) specifies where to locate annotation processors. It differs from `--class-path`: the processor path holds processor code; the classpath holds dependencies of the program being compiled.

### 7.5. Registering a processor as a named module

If the processor is modularized, its module descriptor can declare:

```java
module com.acme.audit.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with com.acme.processor.AuditProcessor;
}
```

Place the processor module on the processor module path:

```bash
javac --processor-module-path processor-mods -d out src/com/acme/App.java
```

If the processor uses the public compiler tree API in `com.sun.source.*`, the processor module may need `requires jdk.compiler;`. Do not treat `com.sun.tools.javac.*` packages as stable API dependencies.

### 7.6. Specifying processors explicitly

To avoid automatic discovery of every processor on the path, name the class explicitly:

```bash
javac --processor-path processor.jar --processor com.acme.processor.AuditProcessor -d out src/com/acme/App.java
```

In builds with multiple processors, specifying the list explicitly controls which processors run and reduces discrepancies between developer and CI environments.

### 7.7. Processor diagnostics

Useful `javac` options:

| Option | Purpose |
|---|---|
| `-proc:none` | Skip annotation processing |
| `-proc:only` | Run annotation processing only, skipping normal compilation |
| `-processor <class>` | Specify processor classes |
| `-processorpath <path>` | Path to search for processors on the classpath |
| `--processor-module-path <path>` | Path to search for processor modules |
| `-s <directory>` | Directory for generated source files |
| `-d <directory>` | Output directory for compiled classes |

Example disabling processing to isolate whether a failure originates from a processor:

```bash
javac -proc:none -d out src/com/acme/App.java
```

If the build succeeds with processing disabled, that points investigation toward the processor or its generated code. It is not a final fix if the project relies on processor-generated sources.

### 7.8. Processors run at compile time, not runtime

Annotation processors typically execute during build/compile. A runtime image built with `jlink` does not need processors if the application only needs the already generated and compiled classes.

Keep these distinct:

- Processor JARs are build-time dependencies.
- Generated sources/classes are build outputs.
- Runtime dependencies are classes/JARs/modules needed when the application runs.

Do not bundle processors into the runtime image merely because they ran during compilation, unless the application has a separate runtime requirement for that library.

## 8. When an annotation processor uses javac internals

### 8.1. Common symptoms

When upgrading the JDK, an older processor may hit:

- `IllegalAccessError` when accessing internal `jdk.compiler` classes/packages.
- `InaccessibleObjectException` when performing deep reflection.
- `NoSuchFieldError` or `NoSuchMethodError` due to changed javac internals.
- `ClassNotFoundException` or `NoClassDefFoundError` due to misconfigured processor/module paths.
- Source/class generation failures caused by assumptions about internal compiler structures.

These errors can come from the processor itself or a dependency used by the processor.

### 8.2. Use add-exports/add-opens strictly as temporary workarounds

If a legacy processor references public classes in an unexported internal package, exports can be opened at compile time:

```bash
javac --add-exports jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED \
      --processor-path processor.jar \
      -d out src/com/acme/App.java
```

If the processor uses deep reflection on private compiler members, open the package to the JVM running `javac`. The `-J` option forwards arguments to the JVM launching the compiler:

```bash
javac -J--add-opens=jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED \
      --processor-path processor.jar \
      -d out src/com/acme/App.java
```

The packages shown are examples only. Open only the exact package reported in your actual error and the exact target module. Do not add a blanket list of `com.sun.tools.javac.*` packages.

Workarounds may get an old build running temporarily, but they do not guarantee processor compatibility with future JDK releases. The long-term solution is updating the processor or migrating to public APIs.

### 8.3. Check processor versions

For each processor:

1. Identify the exact artifact name and resolved version in the build dependency tree.
2. Read release notes for Java 17 support and javac/JPMS changes.
3. Check whether the processor references `com.sun.tools.javac.*`.
4. Update to a vendor-supported release.
5. Remove module workarounds if the new version no longer requires them.
6. Run a clean compile to verify generated sources are consistent.

Some processors couple deeply to javac internals. Never infer processor compatibility merely because the runtime application runs on Java 17; processors must be verified during compilation with JDK 17 itself.

## 9. Audit workflow when upgrading to Java 17

### Step 1 — Inventory relevant components

List:

- ORM, DI, proxy, AOP, and serialization frameworks.
- Bytecode generation libraries.
- Annotation processors and compiler plugins.
- Test/mocking libraries.
- Code invoking reflection or MethodHandles.
- Libraries using JNI or JDK internal APIs.

Inspect the dependency tree to see actual resolved versions, including transitive dependencies. Do not check only directly declared dependencies.

### Step 2 — Analyze JDK internal APIs

Run:

```bash
jdeps --jdk-internals --recursive --multi-release 17 app.jar
jdeprscan --release 17 --for-removal app.jar
```

Run additionally on key dependency JARs. Record referenced internal classes/packages and replacement public APIs.

### Step 3 — Search for reflection and dynamic class generation

Search source and configs for keywords:

```text
setAccessible
trySetAccessible
getDeclaredField
getDeclaredMethod
getDeclaredConstructor
privateLookupIn
Class.forName
defineClass
defineHiddenClass
Proxy.newProxyInstance
```

Also verify:

- Do framework configs enable field access or private member access?
- Are class names loaded from configuration/plugin files?
- Is bytecode generated at runtime?
- Is code generated at compile time?

Source search is only the first step because frameworks often invoke these APIs inside dependencies.

### Step 4 — Update libraries

Prefer versions confirmed by the vendor to support Java 17. Specifically verify:

- Does the framework support strong encapsulation?
- Does the bytecode generator understand class file version 61 and module boundaries?
- Is the annotation processor compatible with javac 17?
- Are there patches for `InaccessibleObjectException`, `IllegalAccessError`, or proxy failures?

If a dependency is unmaintained, evaluate replacing or isolating it instead of continually opening internal JDK access.

### Step 5 — Add only narrowly scoped module flags

When an old dependency cannot be removed immediately:

1. Record the exact source module and package from the error.
2. Identify the target module (named module or `ALL-UNNAMED`).
3. Distinguish whether `--add-exports` or `--add-opens` is required.
4. Apply the flag at the right stage: compile time or runtime.
5. Document the reason, owning dependency, and target version for removing the workaround.

Do not place a broad module-opening flag into shared scripts just to hide an undiagnosed failure.

### Step 6 — Test rarely exercised code paths

Features to exercise:

- Application startup and component scanning.
- ORM entity loading, lazy proxies, and private field mapping.
- JSON/XML serialization and deserialization.
- Dependency injection, AOP, and dynamic proxies.
- Test mocking.
- Plugin loading and configuration-driven reflection.
- Clean compilation with annotation processing.
- Incremental builds and CI builds.

### Step 7 — Remove obsolete workarounds

After upgrading frameworks/processors:

- Try running without `--add-opens`/`--add-exports`.
- Remove flags one at a time.
- Re-run tests covering the affected features.
- Keep only genuinely required flags, tightly scoped and documented.

## 10. Testing and observability on Java 17

### 10.1. Test on the actual target JDK

Compile and test using the actual JDK 17 you plan to deploy, rather than compiling on a newer JDK with target bytecode 17. Setting a target version does not replicate the entire module system, reflection rules, or `javac 17` implementation.

### 10.2. Capture logs to diagnose failures

When access errors occur, preserve the full details:

- Exception type and message.
- Source module name.
- Blocked package.
- Target/caller module.
- Full stack trace.
- Relevant JDK and dependency versions.

`InaccessibleObjectException` messages typically name the exact package and module that must be opened. Use that information to determine the exact permission needed instead of guessing.

### 10.3. Verify both runtime and compile-time

| Stage | Components to verify |
|---|---|
| Compile | javac, annotation processors, compiler plugins, generated sources |
| Test | Mocking frameworks, proxies, reflection, test runtime |
| Startup | Dependency injection, ORM bootstrap, service loading |
| Runtime feature | Serialization, dynamic class loading, plugins, scripting |
| Production-like | Class loader lifecycle, module flags, native dependencies |

A passing compile build does not prove processors have no issues on incremental or alternate builds. Simple tests do not prove frameworks avoid reflection in other features.

## 11. Common errors when upgrading to Java 17

| Error / symptom | Common cause | Resolution |
|---|---|---|
| `InaccessibleObjectException` | Deep reflection into a package that is not open | Upgrade the framework; if needed, open the exact package via `opens` or `--add-opens` |
| `IllegalAccessError` | Code references a type/member in a package not exported to the caller module | Use public APIs; check tightly scoped `exports` or `--add-exports` |
| `NoSuchFieldException` after JDK upgrade | Code/framework relied on unstable internal fields | Remove implementation dependency; use supported APIs |
| `NoSuchMethodError` or `NoSuchFieldError` in processor | Processor depends on changed internal javac structures | Update the processor and verify JDK 17 compatibility |
| Proxy created but method invocation fails | Module/package visibility or generated class in incompatible loader/module | Check interface visibility, class loader, and proxy module |
| `IllegalAccessException` from `privateLookupIn` | Caller does not read target module or target package is not open | Update module descriptor or use public APIs |
| Class generation fails verifier | Invalid bytecode, wrong class file version, or invalid access flags/package | Update bytecode library and emit Java 17-compatible class files |
| Processor does not run | Processor JAR missing from processor path/module path or broken service registration | Check `--processor-path`/`--processor-module-path` and service descriptor |
| Generated source fails to compile | Processor emitted source with wrong package, name, or types | Inspect `-s` output, processor logs, and generated source |
| App runs only with many add-opens flags | Legacy framework relies heavily on deep reflection into JDK internals | Update/replace the framework; keep workarounds minimal during transition |

### 11.1. Understand module access errors accurately

When encountering an access error, classify it first:

- Compile failure due to unexported package: check `exports`/`--add-exports`.
- Deep reflection failure due to closed package: check `opens`/`--add-opens`.
- `privateLookupIn` failure: check readability and opens.
- Class definition failure: check loader, package, module, lookup mode, and bytecode.
- Processor failure: determine whether the error occurs in the JVM running `javac` or in the module graph of the compiled source.

Do not add both flag types for every failure. Normal access and deep reflection solve two distinct problems.

### 11.2. The special case of sun.misc.Unsafe

Some legacy code uses `sun.misc.Unsafe` for low-level memory operations or special allocations. This is an internal/discouraged API for normal applications; certain key APIs remain accessible for compatibility, but should not be treated as a stable contract.

During audits, locate both `sun.misc.Unsafe` and other internal APIs. Where possible, replace them with standard APIs such as `VarHandle`, `ByteBuffer`, `java.util.concurrent`, or supported memory/access APIs in your target Java release. Do not switch to another internal API merely to sidestep a current error.

## 12. Class file and bytecode considerations on Java 17

Java 17 supports class file version 61. Bytecode-generating libraries must emit class files compatible with the target runtime and understand the bytecode attributes they process.

During review:

- Confirm bytecode libraries support class file version 61.
- Check the target version requested by frameworks when generating classes.
- Do not emit class files newer than Java 17 if the application must run on Java 17.
- Verify stack map frames, access flags, nestmates, and module/package assumptions.
- Run real tests for proxies, mocks, ORM lazy loading, and generated accessors.

Compiling sources with `--release 17` constrains the Java APIs source code can call, but it does not automatically validate bytecode generated dynamically by frameworks at runtime.

## 13. Pre-release checklist for Java 17

### Reflection

- [ ] Searched for `setAccessible`, `trySetAccessible`, `getDeclared*`, and `privateLookupIn`.
- [ ] Distinguished export errors from open errors.
- [ ] Updated ORM, DI, serialization, proxy, and mocking frameworks.
- [ ] Every remaining `--add-opens` specifies an exact target module/package and documented rationale.
- [ ] Not relying on `--illegal-access`.

### Bytecode generation

- [ ] Listed frameworks generating proxies/classes at runtime.
- [ ] Bytecode libraries support class file version 61.
- [ ] Preferred public APIs like `Lookup.defineClass`, `defineHiddenClass`, or `Proxy` when appropriate.
- [ ] No reflection into internal ClassLoader/javac/JDK implementations.
- [ ] Tested class loader, module, and package access of generated classes.

### Annotation processors

- [ ] Inventoried direct and transitive processors.
- [ ] Processors are compatible with javac 17.
- [ ] Processors use standard `javax.annotation.processing`/`javax.lang.model` APIs where possible.
- [ ] Processors do not depend on `com.sun.tools.javac.*` when supported alternatives exist.
- [ ] Processor path/module path and service registration are configured cleanly.
- [ ] Generated sources verified in clean builds and CI.

### Build and runtime

- [ ] Ran `jdeps --jdk-internals` on the application and relevant dependencies.
- [ ] Ran `jdeprscan --release 17`.
- [ ] Ran integration tests on an actual JDK 17.
- [ ] Exercised rarely used paths: startup scan, proxies, ORM, serialization, plugins, and compile processing.
- [ ] Removed module flags no longer needed after dependency updates.

## 14. Hands-on exercises

### Exercise 1 — Distinguish exports and opens

A framework calls `setAccessible(true)` on private fields of an entity inside the application module. The module descriptor only declares `exports com.acme.entity`.

1. Why can `InaccessibleObjectException` still occur?
2. Is `opens` or `exports` required?
3. Write the directive opening the package to the specific framework module.

**Hint:** `exports` grants access to public APIs; deep reflection requires `opens`. For example:

```java
opens com.acme.entity to org.example.orm;
```

### Exercise 2 — Resolve a privateLookupIn failure

Module `com.acme.app` invokes `MethodHandles.privateLookupIn` on a class in module `com.acme.model`. State the two module conditions that must be met and how to update the module descriptors.

### Exercise 3 — Locate JDK internal APIs

Run:

```bash
jdeps --jdk-internals --recursive --multi-release 17 app.jar
```

Inspect the output, identify application/dependency classes referencing internal packages, and locate the replacement APIs suggested by the JDK. Then re-run to confirm the dependency has been eliminated.

### Exercise 4 — Audit an annotation processor

A processor fails with `IllegalAccessError` while accessing `com.sun.tools.javac.tree`.

1. Why is this package not a stable API for processors?
2. Which standard APIs can replace it?
3. How should processor versions and module paths be verified?
4. Why is adding `--add-exports` only a workaround?

### Exercise 5 — Choose a class-definition API

A framework needs to generate an implementation class in the same package as the lookup-owning class. Compare:

- `ClassLoader#defineClass`.
- `MethodHandles.Lookup#defineClass`.
- `MethodHandles.Lookup#defineHiddenClass`.

Choose the appropriate API and explain limitations around packages, class loaders, and lookup by binary name.

### Exercise 6 — Build a migration checklist

Pick a project using an ORM, dependency injection, and annotation processors. List the dependencies to audit, `jdeps`/`jdeprscan` commands, features to test, and any temporary module flags. Define the criteria for removing each flag.

## 15. Official Java 17 documentation

- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation policy in Java 17 and status of `--illegal-access`.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): default strong encapsulation introduced in Java 16.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): modules, exports, opens, and `--add-exports`/`--add-opens` options.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, and reflection rules.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception thrown when reflective access cannot be enabled.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `privateLookupIn`, `defineClass`, and `defineHiddenClass`.
- [Java SE 17 API — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): API for creating dynamic interface proxies.
- [Java 17 javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): processor path/module path and compiler options.
- [Java 17 jdeps command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency and JDK internal API analysis.
- [Java 17 jdeprscan command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): detecting usage of deprecated APIs.
- [Java SE 17 API — javax.annotation.processing](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html): standard API for annotation processors.
- [Java SE 17 API — javax.lang.model](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/package-summary.html): type, element, and package model used during annotation processing.
- [Java SE 17 API — com.sun.source.util](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/package-summary.html): public compiler tree API.

**Key takeaway:** Java 17 enforces strong encapsulation for JDK internals. Deep reflection requires an opened package; accessing public APIs requires an exported package. Bytecode generators must respect class loaders, packages, and modules, preferring APIs like `Lookup#defineClass` or `defineHiddenClass`. Annotation processors should rely on `javax.annotation.processing` and `javax.lang.model` instead of `com.sun.tools.javac.*`. Use `jdeps --jdk-internals`, `jdeprscan`, source/dependency audits, and real JDK 17 tests; keep `--add-opens`/`--add-exports` strictly as narrow, documented workarounds with a removal plan.
