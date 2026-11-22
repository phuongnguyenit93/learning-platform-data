# 1.3 Relationship Between Metadata Discovery, Component Discovery, Linking, and Execution

**Module:** Java Advance - dynamic-runtime  
**Knowledge Group:** 1. Overview

A Java system that is extensible at runtime usually does not call every implementation class directly from source code. Instead, the system receives a descriptor, finds the matching class or provider, checks how it connects to the common contract, and only then activates the behavior. The four concepts **metadata discovery → component discovery → linking → execution** describe the responsibilities in that process.

Important point: these are **four logical responsibilities**, not a guarantee that the JVM always executes four independent steps in a strict chronological order. For example, to read runtime annotations of a class using Reflection, you first need a `Class<?>` object representing that class; meanwhile, `ServiceLoader` can defer finding and instantiating providers until iteration.

## 1. What Question Does Each Phase Answer?

| Phase | Main Question | Typical Input | Required Output |
| --- | --- | --- | --- |
| **Metadata discovery** | Which component is *declared* and what conditions does it require? | Annotations, configuration, service descriptor, module descriptor, registry | List of descriptors/candidates along with ID, contract, version, permissions, or attributes |
| **Component discovery** | Where does the actual implementation code reside and is it accessible? | Class name, classpath/module path, `ClassLoader`, `ServiceLoader` | `Class<?>`, provider, object, or factory corresponding to the descriptor |
| **Linking/binding** | Does the candidate match the contract and can it be connected to the call site? | Type, method signature, access permissions, dependencies | Method reference, `MethodHandle`, factory/adapter, or valid call site |
| **Execution** | When passed inputs, what work does the component perform and what result does it return? | Ready object/call site, arguments, context | Result, state change, event, or runtime exception |

For example, an application needs the `upper` operation:

1. The registry declares `id=upper` and the implementing class name: **reading declared information**.
2. The system loads/finds the right class in the right class loader: **identifying the component**.
3. Confirming the class implements the `Action` interface, finding the `run(String)` method and call permissions: **linking with the contract**.
4. Instantiating the object if needed, passing `"java 17"`, and receiving `"JAVA 17"`: **execution**.

**Metadata alone does not guarantee the code exists.** Having a class name in configuration while the JAR is absent means component discovery cannot succeed yet. Finding the class also does not guarantee API compatibility. Successful linking also does not guarantee that business logic will run successfully.

## 2. Distinguishing Two Meanings of “Linking” in Java

### 2.1. JVM linkage: linking classes and bytecode symbols

At compile time, Java writes symbolic references (class names, fields, methods, signatures) into the class file. According to the JVM Specification, a class typically goes through:

- **Loading:** finding the binary representation of the class and creating the runtime type via a class loader.
- **Linking:** consisting of **verification** (checking validity), **preparation** (preparing static fields with default values), and **resolution** (resolving symbolic references into runtime entities).
- **Initialization:** running class initialization code, including static initializers and programmatic static field assignments.

**Loading, linking, and initialization are distinct.** The JVM has the discretion to choose when to perform certain resolution tasks, so you must not assume every reference is already resolved immediately after class loading. A program can encounter `LinkageError` when an action requires resolving an invalid reference.

The call `Class.forName(name, false, loader)` in the example below requests finding the class without proactively initializing it. Conversely, the standard `Class.forName(name)` form requests class initialization. Creating an instance or using certain static members can trigger initialization according to JVM rules.

### 2.2. Application binding: matching a component with a dynamic contract

At the application level, “linking” (binding) is also the act of selecting an implementation for an extension point, such as:

- checking `Action.class.isAssignableFrom(candidate)`;
- obtaining a constructor, method, or method handle with the right name/signature;
- checking accessibility within a package/module;
- creating an adapter or registering a handler so subsequent calls route to the right implementation.

This is a **process designed by the framework/application**; it relates to JVM rules but is not an independent JVM linkage phase named “plugin binding”. If called through an interface, the JVM still performs dispatch to the object's implementation at the call site.

`MethodHandles.Lookup.findVirtual` creates a handle after checking accessibility and method type. `MethodHandle.invokeExact` requires the call-site signature to match the handle's type exactly; a type mismatch can cause `WrongMethodTypeException`.

### 2.3. Where does `invokedynamic` fit?

`invokedynamic` is a type of call site in bytecode: when the call site needs to be linked, the JVM uses a **bootstrap method** to produce a `CallSite` with an appropriate target. Subsequent invocations use the call site's target according to the semantics of that call site type. This mechanism supports dynamic linking patterns at the bytecode level (for example, lambda infrastructure), but is **not synonymous** with scanning JARs, reading a registry, or finding plugins with `ServiceLoader`. Those tasks are higher-level discovery policies.

## 3. Metadata Guides, Loaders and Contracts Determine Executability

| Metadata Source | What Does It Describe? | What Else Must Be Verified? |
| --- | --- | --- |
| Annotation with `@Retention(RUNTIME)` | Role, ID, or configuration attached to a class/method | There must be a way to find the class to inspect; annotations do not automatically scan the entire classpath |
| `META-INF/services/<interface-name>` | Binary names of providers on the classpath | The provider is present, valid, and instantiable according to `ServiceLoader` conventions |
| `module-info.java` with `uses`/`provides` | Services consumed/provided in the module system | The module is resolved in the appropriate layer; read/export/open package permissions are sufficient |
| Configuration/registry/manifest | ID, class name, version, enable/disable conditions | The running artifact actually contains the required implementation and dependencies |
| Reflection on `Class<?>` | Annotations, methods, constructors, interfaces at runtime | Access permissions, types, signatures, and initialization state must still be checked |

There is no standard API that by default “scans the entire application and finds every class with an annotation” across all Java deployment models. Frameworks usually build indexes, read configuration, scan a scope they own, or use a custom discovery protocol.

**Class loaders are part of type identity:** two classes with the same binary name defined by different *defining class loaders* are two distinct runtime types. Therefore, a plugin might “find the class” yet casting it to the host's interface still fails if it carries a copy of `Action` loaded by another loader. In the module system (JPMS), `exports`/`opens` and module readability also govern access, especially for deep reflection.

`ServiceLoader` itself combines multiple responsibilities: reading service declarations, locating providers, and then providing/instantiating them in a potentially deferred manner. When dividing the pipeline into four phases for design and observability, you need to recognize that a single API can handle multiple phases.

## 4. Java 17+ Example: Going from Metadata to Actual Invocation

The example uses a pre-registered class name to simulate a registry; an annotation decides whether the candidate has the right ID; `Class` and the interface check the component; `MethodHandle` binds the call; and finally the program creates the object and runs it. Everything resides in **a single standalone runnable file**, with no external libraries required.

**File: `DynamicPipelineDemo.java`**

~~~java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.util.Locale;

public class DynamicPipelineDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Plugin { String id(); }

    public interface Action {
        String run(String input);
    }

    @Plugin(id = "upper")
    public static class UpperAction implements Action {
        @Override
        public String run(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Throwable {
        // 1. Registry/config provides a candidate (no classpath scanning).
        String declaredName = "DynamicPipelineDemo$UpperAction";
        ClassLoader loader = DynamicPipelineDemo.class.getClassLoader();
        Class<?> candidate = Class.forName(declaredName, false, loader);

        // 2. Read metadata and verify the requested ID matches.
        Plugin metadata = candidate.getAnnotation(Plugin.class);
        if (metadata == null || !"upper".equals(metadata.id())) {
            throw new IllegalStateException("Plugin metadata mismatch");
        }
        System.out.println("metadata=" + metadata.id());

        // 3. Confirm the component adheres to the host's contract.
        if (!Action.class.isAssignableFrom(candidate)) {
            throw new IllegalStateException("Not an Action");
        }
        Class<? extends Action> type = candidate.asSubclass(Action.class);
        System.out.println("component=" + type.getSimpleName());

        // 4. Bind the method to invoke, according to the interface signature.
        MethodHandle call = MethodHandles.lookup().findVirtual(
                Action.class, "run",
                MethodType.methodType(String.class, String.class));
        System.out.println("binding=" + call.type());

        // 5. Instantiate and execute after checking/binding the contract.
        Action action = type.getDeclaredConstructor().newInstance();
        String output = (String) call.invokeExact(action, "java 17");
        System.out.println("output=" + output);
    }
}
~~~

Compile and run (JDK 17 or later):

~~~bash
javac --release 17 DynamicPipelineDemo.java
java DynamicPipelineDemo
~~~

Standard output:

~~~text
metadata=upper
component=UpperAction
binding=(Action,String)String
output=JAVA 17
~~~

**Why does the example accurately demonstrate the relationship?**

- `declaredName` is the **discovery lead**, assumed to come from a registry. There is no automatic annotation-scanning feature to find candidates.
- `Class.forName(..., false, loader)` provides the runtime type to read the annotation; therefore, reading metadata **occurs after `Class` has already been found** in this example. “Metadata discovery” is a responsibility, not necessarily the first JVM event.
- `getAnnotation` verifies the metadata's meaning; `isAssignableFrom` checks the contract, while `asSubclass` provides a safer type for the instantiation step.
- `findVirtual` creates a handle with type `(Action, String) -> String`; `invokeExact` executes on the `UpperAction` object. In practice, direct interface calls or Reflection can be used instead of a method handle.
- `getDeclaredConstructor().newInstance()` creates the object; in a real design, the creation timing and object reuse scope must be defined separately. This example uses a constructor accessible within the same class/nest, so there is no need to bypass Reflection access checks.

Try replacing `"upper"` in the annotation with `"lower"`: the program stops at the metadata check step, before creating the object or calling `run`. Try making `UpperAction` not implement `Action` (and remove `@Override`): the program stops at the contract check step. Both errors illustrate that **being found does not mean it can be linked and executed**.

## 5. When Replacing the Registry with `ServiceLoader`

If an application provides an SPI interface, each provider can be declared via a `META-INF/services/<binary-name-of-SPI>` file (when using the classpath), or `uses`/`provides` in a module descriptor (when using JPMS). For example, if the SPI is named `com.example.spi.Action`, the classpath declaration path is:

~~~text
META-INF/services/com.example.spi.Action
~~~

The file content is the fully qualified provider class name, one name per line, for example:

~~~text
com.example.impl.UpperAction
~~~

After packaging the SPI, implementation, and metadata properly, **illustrative code in an application with the `Action` SPI** can use:

~~~java
ServiceLoader<Action> providers = ServiceLoader.load(Action.class);
for (Action provider : providers) {
    System.out.println(provider.run("java 17"));
}
~~~

This snippet is **not a standalone program** and does not directly use the nested class name from the single-file example in section 4. It requires a project with the corresponding SPI/provider and a valid service descriptor.

`ServiceLoader.load` creates a service loader; locating and instantiating providers usually happens during iteration, so configuration errors may surface later than the `load` call. If you need to inspect provider metadata before creating an instance, you can look at the `ServiceLoader.stream()` and `Provider.type()` APIs, though you must still follow the API's provider-lookup/reading rules.

In both approaches, **the common contract** matters more than the implementation name: the host should know `Action`, while only the registry or discovery knows `UpperAction`. This allows adding implementations without modifying every call site.

## 6. Where Do Errors Occur and How to Diagnose Them?

| Symptom | Suspected Phase | What to Check |
| --- | --- | --- |
| No entry or ID mismatch | Metadata discovery | Service name, annotation retention, configuration, filter, or version |
| `ClassNotFoundException`, `ServiceConfigurationError` | Component discovery/provider setup | Binary name, artifact on classpath/module path, loader/layer, provider declaration |
| `NoClassDefFoundError`, `NoSuchMethodError`, `IncompatibleClassChangeError` | Runtime load/link, binary compatibility | Missing dependency, API/ABI mismatch between compile time and runtime |
| `IllegalAccessException`, `InaccessibleObjectException`, or `IllegalAccessError` | Access/linking | Modifiers, module readability, `exports`/`opens`, correct `Lookup` |
| `NoSuchMethodException` or `WrongMethodTypeException` | Method lookup/binding | Name, parameters, return type; exact signature of `invokeExact` |
| `ExceptionInInitializerError` or exception from provider logic | Initialization/execution | Static initializer, constructor, input data, and root stack trace |

An error can appear *when executing the first action that requires that phase*, not necessarily right at the moment the registry is built. With Reflection, `Method.invoke` can wrap an exception from the target method in `InvocationTargetException`; with a method handle, the target's exception is propagated according to the handle invocation mechanism.

For systematic debugging, record the milestones **metadata read → candidate resolved → contract checked → method bound → instance created → invoked**, along with provider ID, class name, class loader, module/layer, and the exception cause. Do not log sensitive data from inputs or the classpath beyond diagnostic needs.

## 7. Principles for Designing a Reliable Dynamic Runtime Pipeline

1. **Define the contract first:** the interface/SPI, inputs/outputs, lifecycle, version constraints, and error policy must be clear. A provider with nice metadata that does not satisfy the contract must still be rejected.
2. **Separate discovery from activation when possible:** only instantiate when needed; do not launch every plugin just to list them. Be aware that some APIs perform multiple tasks in a single call.
3. **Choose the right search scope:** classpath, module layer, class loader, registry; avoid assuming every provider on the machine will be found automatically by the JVM.
4. **Enforce types and access permissions:** verify `isAssignableFrom`, method signatures, module access; avoid blind casting or turning on `setAccessible(true)` for everything.
5. **Manage lifecycle and caching:** metadata, `Class`, handles, and instances have different costs and semantics. Caches must be tied to the right loader/layer and must have a refresh policy when artifacts change; do not cache a non-thread-safe instance as a singleton if the contract does not allow it.
6. **Maintain trust boundaries:** loading code from external sources can execute code in initialization, constructors, or methods. `ClassLoader` **does not create a security sandbox by itself**. Only load controlled/verified providers in the same process, or isolate using OS processes/permissions when necessary.
7. **Measure each phase before optimizing:** minimize repeated scanning, use a reasonable discovery cache, and create/bind handles once if appropriate. Do not conclude that Reflection, interface dispatch, or `MethodHandle` is always faster based solely on the mechanism name; measure on the actual workload.

## 8. Common Misconceptions

- **“Having an annotation means the plugin is automatically found.”** False; you need a mechanism to traverse class names, a registry, or an index before inspecting annotations.
- **“Loading a class means the plugin has already run.”** False; loading is distinct from initialization, object creation, and method invocation. However, initialization code can still cause side effects when triggered.
- **“Linking in a framework is JVM linking.”** These are two related layers of responsibility, but with different scopes.
- **“`Class.forName(name)` only reads metadata.”** This overload requests class initialization; use the overload with the `initialize=false` parameter when you want to avoid proactive initialization.
- **“Same class name means same type.”** False when the defining class loaders differ.
- **“Finding the provider successfully guarantees execution will succeed.”** A provider can be missing dependencies, violate signatures, be inaccessible, fail in its constructor, or fail in business logic.

## 9. Self-Check Questions

**Scenario A:** The `META-INF/services` file has the exact provider name, yet the application throws `ServiceConfigurationError` during iteration. Check identifying metadata, loader/module, provider loadability, contract, and initialization rules rather than checking only the file name.

**Scenario B:** The registry finds `com.example.UpperAction`, yet `Action.class.isAssignableFrom(candidate)` returns `false` even though the source code states `implements Action`. Check whether the host and the plugin define two copies of `Action` using different defining class loaders.

**Scenario C:** You obtain a `MethodHandle`, yet `invokeExact` throws `WrongMethodTypeException`. Compare `handle.type()` against the **static types of each argument and the return type at the call site**; `invokeExact` does not perform flexible type conversions like `invoke`.

A good way to remember: **metadata describes capability; discovery finds the runtime embodiment; binding establishes the contract/call site; execution produces observable behavior.** The steps depend on one another, can interleave or happen lazily, and an error at any step must be diagnosed according to that step's responsibility.

## References

- [JVM Specification, Java SE 17 — Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 API — MethodHandle and MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
