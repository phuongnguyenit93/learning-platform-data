# Testing Filters by Class Name, Descriptor, Class Loader, and Module

In Java Instrumentation, `ClassFileTransformer` can receive callbacks for a wide variety of classes: application classes, third-party libraries, frameworks, the JDK, plugin classes, and versions with the same name defined by different class loaders. A faulty filter can cause the agent to **instrument the wrong class**, miss the target method, insert duplicate probes, cause `VerifyError`/`LinkageError`, or produce observability data from the wrong source.

To test a filter reliably, do not just ask "does the class name start with package X?". For every allowed method, **four dimensions** must be evaluated **simultaneously**:

1. **Class name** in JVM internal name form, e.g., `com/acme/order/OrderService`.
2. **Method name and JVM method descriptor**, e.g., `process(Ljava/lang/String;I)Z`. In this topic, the "descriptor" is the criterion that accurately distinguishes overloads and return types, not just the method name.
3. **The class loader that actually defines the class** (defining loader), distinguishing loader instances by identity, even when two loaders load the same binary name.
4. **The module that actually contains the class**, distinguishing named/unnamed modules and `Module` objects, not merely comparing module names as strings.

This lesson belongs to the **Testing and Diagnostics** group of Java Instrumentation. You will design a fail-closed filter, build a positive/negative test matrix, test with real class loaders and modules, verify descriptors from class files, and connect that logic to the `transform` callback. The main example uses **Java 17+ with no external library dependencies** to test filter and method metadata. The sections connecting to an agent/ASM are explicitly marked as integration patterns rather than standalone runnable programs.

## 1. Define the Test Target Before Writing the Filter

A method instrumentation policy can be described as follows:

```yaml
feature: order-latency
target:
  classInternalName: com/acme/order/OrderService
  methodName: submit
  methodDescriptor: (Ljava/lang/String;I)Z
  loaderIdentity: application-loader-A
  moduleIdentity: com.acme.order@boot-layer
action:
  onMatch: INSTRUMENT
  otherwise: SKIP_WITH_REASON
```

This is an **illustrative schema**. `loaderIdentity` and `moduleIdentity` are only human-readable labels in documentation; in runtime code, you must compare **actual `ClassLoader` and `Module` objects**, not infer identity solely from YAML strings.

The policy only matches when **all conditions** are simultaneously true. If a class has the same name and signature but is defined by a different plugin loader, it is not automatically allowed. If the class/loader/module match, but an overloaded method has a different descriptor, it is also not allowed.

```text
Callback transform(module, loader, className, ..., classfileBuffer)
                  |
                  v
        is className valid and matching?
         | NO -> SKIP_CLASS_NAME
         v
        is loader the exact instance?
         | NO -> SKIP_LOADER
         v
        is module the exact Module object?
         | NO -> SKIP_MODULE
         v
      parse method name + descriptor from class bytes
         |
         v
        does method signature match?
         | NO -> SKIP_DESCRIPTOR
         v
       check state, excluded/duplicate/capability
         |
         v
       generate new bytecode + verify + measure effect
```

**Fail-closed principle:** If information is missing to confirm a required dimension, **do not** instrument. Never use fallbacks such as "if module is missing, match by class name" or "if descriptor cannot be parsed, instrument all overloads".

### Success Definition Table

| Status | Exact Meaning | Evidence |
|---|---|---|
| `FILTER_MATCH` | Filter allows class + method across all four dimensions | Predicate test + context/classfile metadata |
| `CLASS_TRANSFORMED` | Transformer returns new class bytes | Callback and bytes differ from original |
| `CLASS_ACCEPTED` | JVM accepts definition after the transformer chain | No corresponding load/retransform error |
| `PROBE_EXECUTED` | Method is invoked and instrumentation code runs | Counter/span/log sentinel appears only for the target |
| `OUT_OF_SCOPE_UNTOUCHED` | Non-matching classes/methods are unmodified | Negative tests, bytecode diff/behavior |
| `CLASSLOADER_ISOLATED` | Same binary name in another loader is not mistakenly selected | Two loader instances and distinct `Class` objects |
| `MODULE_ISOLATED` | Another module is not matched solely by having the same package name | Compare `Module` identity and test with real modules |
| `IDEMPOTENT` | Repeated re-transform/transform does not produce duplicate probes | Check bytes/counter before and after |

A **`FILTER_MATCH`** is not synonymous with **`PROBE_EXECUTED`**. The class might never be loaded, the transformer might return `null`, the JVM might reject the bytes, or the method might never be invoked. Report each status separately for accurate diagnostics.

## 2. Class Name: Binary Name, Internal Name, and Common Pitfalls

### 2.1. Name in the `ClassFileTransformer` Callback

In Java 9+, the callback has the signature:

```java
byte[] transform(
    Module module,
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    java.security.ProtectionDomain protectionDomain,
    byte[] classfileBuffer);
```

The `className` parameter is a **JVM internal name**, using `/` as the package separator, for example `"java/util/List"`, **not** `"java.util.List"` as `Class.getName()` returns for normal classes.

| Source / Meaning | Binary name / name used in reflection | Internal name |
|---|---|---|
| `com.acme.order.OrderService` | `com.acme.order.OrderService` | `com/acme/order/OrderService` |
| `com.acme.order.Outer.Inner` | `com.acme.order.Outer$Inner` | `com/acme/order/Outer$Inner` |
| `java.lang.String` | `java.lang.String` | `java/lang/String` |
| Class in default package `Demo` | `Demo` | `Demo` |

Do not write `className.equals("com.acme.order.OrderService")` in the callback and then wonder why the filter does not match. If configuration stores dot-separated binary names, **normalize once at the configuration boundary** and test the normalization rule; the hot path should compare pre-normalized internal names.

### 2.2. Exact Comparison Before Prefix Matching

If you only need `com/acme/order/OrderService`, use `equals`. For an allowlisted set of packages, use a `/` boundary:

```java
// Illustrative snippet:
boolean inPackage = className != null
        && className.startsWith("com/acme/order/");
```

`startsWith("com/acme/order")` (without a trailing `/`) also matches `com/acme/orders` or `com/acme/orderlegacy`. This is a common bug when configuring filters for multiple packages.

A `startsWith("java/")` filter to exclude the JDK does not cover all packages used by the JVM/JDK; conversely, a `startsWith("com/")` filter is very broad and may select libraries/frameworks. Choose the scope directly from your observability target, rather than guessing from whether a class name "looks like application code".

### 2.3. Names May Be Missing or Violate Assumptions

Write the callback defensively when `className == null` or when class bytes do not conform. Do not fall back to `classBeingRedefined.getName()` if that object is `null` during an initial class load. Do not call `Class.forName` with the target name inside `transform` to verify it: doing so can trigger class loading/reentrancy while the JVM is defining the class.

For lambdas, hidden classes, proxy classes, generated names, arrays, and nested types, clearly determine whether the agent actually sees the corresponding callback. Do not take `Class.getName()` of a hidden class and assume it always maps one-to-one to a normal `className`. If input information falls outside the policy contract, report `SKIP_UNKNOWN_NAME`; do not guess.

## 3. Method Descriptor: Method Name Alone Is Not Enough

The class callback **does not provide a single method's descriptor**. `classfileBuffer` contains the entire class definition; the transformer must parse the class file (via ASM, an appropriate class-file library, or a controlled parser) to obtain each `method_info.name_index` and `method_info.descriptor_index`.

### 3.1. Descriptors Carry Both Parameters and Return Type

According to JVMS `4.3.3`:

```text
MethodDescriptor:
    ( ParameterDescriptor* ) ReturnDescriptor

Examples:
    ()V
    (I)V
    (Ljava/lang/String;)V
    (Ljava/lang/String;I)Z
    ([I)[Ljava/lang/String;
```

Notation table:

| Java type | JVM descriptor |
|---|---|
| `void` | `V` — return descriptor only |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

Source example:

```java
void submit(int count) { }
void submit(String code) { }
boolean submit(String code, int count) { return true; }
String[] transform(int[] values) { return new String[0]; }
```

Corresponding descriptors:

```text
submit(I)V
submit(Ljava/lang/String;)V
submit(Ljava/lang/String;I)Z
transform([I)[Ljava/lang/String;
```

**Do not** match `methodName == "submit"` and instrument every overload. Do not strip the return type from the descriptor even though standard Java source rules forbid overloading solely by return type: the descriptor in the class file still includes the return part, and matching it accurately helps avoid policy/bridge/synthetic method mismatches.

### 3.2. Descriptors Differ from Generic `Signature`s

`List<String>` and `List<Integer>` have the same **erased type descriptor** `Ljava/util/List;` in method parameter contexts. Generic information may reside in the `Signature` attribute; that is **not** the descriptor used by the JVM to link methods.

```java
// Illustrative Java source:
public java.util.List<String> names(java.util.List<Integer> input) {
    return java.util.List.of();
}
```

The descriptor is:

```text
(Ljava/util/List;)Ljava/util/List;
```

Using strings like `"List<String>"` or `"List<Integer>"` as a method descriptor is incorrect. Tests should include a generic fixture to ensure the filter does not confuse source signatures, reflection `toGenericString()`, and JVM descriptors.

### 3.3. Constructors, Static Initializers, Bridge, and Synthetic Methods

- Constructors have the JVM name `<init>` and return `V`, e.g., `<init>(I)V`.
- Class initializers have the name `<clinit>` and descriptor `()V` if present.
- Bridge/synthetic methods may be generated by the compiler and carry access flags `ACC_BRIDGE`/`ACC_SYNTHETIC`; do not rely solely on source names.
- Lambda implementation methods may be named `lambda$...` and are not necessarily stable across compilations.
- For an agent that only wants to measure developer-declared methods, define explicit rules for bridge/synthetic methods; do not blindly drop all synthetic methods if a feature specifically targets them.
- For constructors, do not inject code that reads `this` before the superclass constructor completes without satisfying verifier rules; a name/descriptor match does not guarantee safe bytecode injection.

### 3.4. Verifying Descriptors with `MethodType` in Tests

Java 17 provides `java.lang.invoke.MethodType.toMethodDescriptorString()`:

```java
String a = java.lang.invoke.MethodType
        .methodType(void.class, int.class)
        .toMethodDescriptorString();            // "(I)V"

String b = java.lang.invoke.MethodType
        .methodType(String[].class, int[].class)
        .toMethodDescriptorString();            // "([I)[Ljava/lang/String;"
```

This is a valid snippet inside a Java method and is useful for **verifying test expectations**. Inside the `transform` callback, avoid using reflection on the target class being loaded to extract descriptors: the class may not be defined yet. Extract method metadata **from bytes**, without forcing the target class to be loaded just to decide whether to instrument it.

## 4. Class Loader: Compare Object Identity, Not Display Name

In Java, class identity consists of **binary name and defining class loader**. Two different loaders can define two classes with the same binary name, yet they are **two distinct `Class` objects**.

```text
Loader-A
  └─ sample.ProbeTarget  -> Class-A

Loader-B
  └─ sample.ProbeTarget  -> Class-B

Class-A.getName() == Class-B.getName()  // true
Class-A == Class-B                      // false
Class-A.getClassLoader() == loaderA     // true
Class-B.getClassLoader() == loaderB     // true
```

**Key takeaway for filters:** `className == "sample/ProbeTarget"` is not enough. If a policy only allows classes from `loaderA` and the transformer ignores the loader, it may also instrument the copy from `loaderB` in plugin or application server environments.

### 4.1. `loader == null` Means Bootstrap, Not Current Loader

The `ClassFileTransformer` Javadoc specifies that `loader` is the defining loader and **may be `null` if the class is defined by the bootstrap loader**. A `loader != null` check skips bootstrap classes — which is sometimes the desired policy — but do not confuse `null` with "unknown, substitute the system loader".

```java
// Example of an explicit condition:
boolean appOnly = loader != null
        && loader == approvedLoader;
```

If you genuinely need to instrument a bootstrap class, the policy must be **explicitly opt-in**, with class/module/capability checks and helper visibility verified. Never write `loader == null || loader == approvedLoader` out of habit: it accidentally expands the scope to bootstrap classes.

### 4.2. Identity Differs from Loader Name / Class Name

`loader.getName()` (Java 9+) is only a nullable name, not a unique identifier. `loader.getClass().getName()` only states the **loader implementation type**, not distinguishing two instances. `System.identityHashCode(loader)` helps with diagnostic logging but can collide and must not replace `==` in authorization decisions.

If you only need to distinguish loaders within a single JVM, keep a **reference to the approved loader instance** and compare with `==`. However, an agent holding strong references to loaders can **prevent class loader unloading**. For long-lived agents on servers with redeploys, manage loader scope, safe weak identity mapping, or lifecycle release so application loaders are not retained forever. Do not trade a wrong-instrumentation bug for a memory-retention bug.

### 4.3. Defining Loader vs. Initiating Loader

A loader can delegate to its parent and receive a class that was **defined by the parent**. The callback receives the **defining loader** of the class being transformed, not arbitrarily whichever loader initially called `loadClass`. Tests must prove which loader actually defined which class; merely seeing `child.loadClass("X")` in code does not prove the class belongs to `child` if the parent also has `X`.

When creating a test with two loaders, to ensure they define separate classes, keep the target class **off the parent/system classpath**, and use two `URLClassLoader` instances whose parent only sees JDK/platform classes.

## 5. Module: Named/Unnamed, Identity, and Layers

Java 9+ adds the `Module module` parameter to the callback. Every class belongs to **exactly one runtime module**. Module names alone are also insufficient to infer identity:

- A named module has `module.isNamed() == true` and a non-null `module.getName()`.
- An unnamed module has `module.isNamed() == false` and `module.getName() == null`.
- **Each class loader has its own unnamed module**, so two different loaders typically have two distinct unnamed `Module` objects.
- Named modules can be defined in different `ModuleLayer`s; the same module name string does not always refer to the same runtime module.
- Not every class defined by a loader resides in an unnamed module: a loader can define classes belonging to named modules.

**Comparison for a strict policy:** `module == allowedModule`. Checking `module.getName().equals("demo.feature")` is insufficient if you need to distinguish instances/layers. For unnamed modules, `module.getName() == null` must be handled explicitly without calling `equals` on `null`.

### 5.1. Do Not Conflate Module with Package

`module.getName()` might be `"demo.feature"`, while `className` is `"demo/feature/NamedTarget"`. The two strings are not in the same namespace. Having package `demo.feature` in the class name does not prove the class belongs to module `demo.feature`; only `Class.getModule()` / the callback module and runtime metadata establish that.

Furthermore, `module == someModule` matches the exact module object, but **does not** automatically make helper classes visible in the target loader. JPMS readability/exports/opens and class-loader visibility are separate requirements for instrumented bytecode to call helpers or deep-reflect later.

### 5.2. Do Not Look Up `Module` by Name on Every Callback

Code such as:

```java
ModuleLayer.boot().findModule("demo.feature")
```

may be suitable in **fixed tests for a module in the boot layer**, but it is not a general way to find modules in framework/plugin layers. If tests or production have multiple layers, obtain the module from the callback or an actual `Class<?>`, rather than inferring module identity from a name string.

### 5.3. Null and Edge Cases

In normal Java 9+ callbacks, the JVM supplies the class's `module`. Even so, a pure filter called from a unit test or adapter might receive `null`; the policy should **fail closed** when a required module cannot be verified, rather than assuming an unnamed module. `null` is not an unnamed `Module`; an unnamed module is still a **real `Module` object**.

## 6. Designing a Fail-Closed, Independently Testable Filter

Separate **decision rules** from **bytecode transformation**. Example model:

```java
// Design model code, containing only fields needed for matching.
record Seen(
    String internalName,
    String methodName,
    String descriptor,
    ClassLoader loader,
    Module module
) {}

record Rule(
    String internalName,
    String methodName,
    String descriptor,
    ClassLoader allowedLoader,
    Module allowedModule
) {
    boolean accepts(Seen s) {
        return s != null
            && java.util.Objects.equals(internalName, s.internalName())
            && java.util.Objects.equals(methodName, s.methodName())
            && java.util.Objects.equals(descriptor, s.descriptor())
            && allowedLoader == s.loader()
            && allowedModule == s.module();
    }
}
```

This snippet is a **valid Java 17+ design pattern** without an enclosing class for the records; Section 8 provides a complete runnable program.

Points to note:

- `Objects.equals` handles `null` without throwing an exception. In a real policy, validate that **expected names/descriptor are non-null** at construction time so a `null` input does not accidentally match a `null` expected value.
- Use `==` for loader and module to enforce runtime identity.
- If `allowedLoader == null` is used to represent **bootstrap allowed**, there must be an explicit policy confirming this is opt-in; never interpret a `null` expected loader as "any loader".
- Compare the descriptor **as a full string**, not with `contains`, `startsWith`, or parameter counts.
- For `<init>`/`<clinit>` method names, add explicit rules/guards if the feature is not intended to instrument constructors/initializers.

### 6.1. Defining Rejection Reasons

A diagnostic-rich API can return an enum:

```text
ALLOW
SKIP_UNKNOWN_CONTEXT
SKIP_CLASS_NAME
SKIP_LOADER
SKIP_MODULE
SKIP_METHOD_NAME
SKIP_DESCRIPTOR
SKIP_SYNTHETIC_OR_BRIDGE
SKIP_ALREADY_INSTRUMENTED
SKIP_CAPABILITY
ERROR_INVALID_CLASSFILE
```

These are **suggested statuses**, not a JDK enum. Use finite reason codes for metrics, and do not put full class names/method signatures from all classes into unbounded-cardinality labels. Record detailed information only in sampled diagnostics or test environments.

### 6.2. Filter Ordering Affects Performance and Safety

A class can have hundreds of methods. Before deep parsing:

1. Check `className` null/allowlist (cheap).
2. Check loader/module identity (cheap).
3. If the class is rejected, **return `null` early**, avoiding buffer parsing.
4. For classes passing the gate, parse the method list/descriptors.
5. Check target method and descriptor.
6. Only at the end generate new bytecode/frames/stack-maps and check idempotency.

Do not call loggers, reflection, classloader loading, or JSON serializers on the transformer hot path to "guess" class metadata. The transformer is invoked by the JVM during class definition/retransformation, where dependency loading and reentrancy are highly sensitive.

## 7. Testing Strategy: Three Independent Tiers

### Tier A — Pure Predicate Unit Tests

Construct mock/real context objects and test every filter dimension. Prove both true and false cases for every field, including `null`, malformed namespaces, overloaded descriptors, multiple loaders, and named vs. unnamed modules.

**Pros:** fast, deterministic, no JVM attach or class-byte instrumentation needed.  
**Limitations:** does not prove the transformer actually receives the expected callbacks or injects valid bytecode.

### Tier B — Classfile Metadata Tests

Use **compiled class file bytes** to verify method names and descriptors. Create fixtures with overloads, arrays, generic erasure, constructors, and bridge/synthetic methods as needed. Do not extract method descriptors by calling `Class.forName` from the transformer: at load time the target class may not be defined yet.

**Pros:** catches confusing `Signature` with `descriptor` and parser/method-visitor bugs.  
**Limitations:** the parser may be correct while the generated bytecode still violates verifier rules.

### Tier C — Integration Tests on a Real JVM

- Launch the JVM with `-javaagent` and target classes in a controlled classpath/module path.
- Record `transform` counts for **allow** and **deny**, without logging every class overly broadly.
- Have two loaders define the same binary name, with only one loader allowed.
- Include both a named module and an unnamed module, or two layers if the policy must distinguish layers.
- Invoke the exact target method and verify a probe marker; invoke an overload or an instance from the other loader and ensure no marker appears.
- If using `retransformClasses`, test behavior on already-loaded classes, class modifiability, and absence of duplicate probes.
- Test class/constructor/synthetic exclusions, not only the happy path.
- Verify linkage/helper visibility/JPMS access errors when the injected code actually executes.

Do not claim integration testing is done just because predicate unit tests pass.

## 8. Runnable Java 17+ Example: Overloads, Two Class Loaders, Named Module

This example contains **four Java files**: a fixture class outside the harness runtime classpath, a named module containing another class, and a test harness that exercises the filter. It tests criteria against **real `ClassLoader`/`Module` objects**, while also including synthetic context cases to isolate individual predicate branches.

The test uses a **minimal class-file reader intended only for test fixtures**, supporting the constant-pool tags needed to read method names and descriptors; do not use it to generate or modify production class files. A real JVM transformer should use ASM, the JDK Class-File API, or a reliable parser suited to the runtime.

### 8.1. Directory Layout

```text
filter-lab/
  src-target/
    sample/ProbeTarget.java
  src-module/
    demo.feature/module-info.java
    demo.feature/demo/feature/NamedTarget.java
  src-main/
    FilterHarness.java
```

**Do not put `build/target` on the runtime `-cp`**. If the target fixture is on the parent classpath, both `URLClassLoader` instances may delegate and receive the same class from the parent, defeating the loader-identity test.

### 8.2. `src-target/sample/ProbeTarget.java`

```java
package sample;

public final class ProbeTarget {
    public void execute(int value) {
        // Target overload to select.
    }

    public void execute(String text) {
        // Different overload that must be excluded when selecting (I)V.
    }

    public String[] transform(int[] values) {
        return new String[] {"ok"};
    }
}
```

Notable method descriptors:

```text
execute(I)V
execute(Ljava/lang/String;)V
transform([I)[Ljava/lang/String;
<init>()V
```

Even though the source class is named `sample.ProbeTarget`, a Java agent's callback filter uses the internal name `sample/ProbeTarget`.

### 8.3. `src-module/demo.feature/module-info.java`

```java
module demo.feature {
    // No package exports needed for the harness to inspect metadata only.
}
```

This module does not export package `demo.feature`. The harness only uses `Class.forName(Module, String)` and reads permitted method metadata, **without invoking business methods**. Testing `Module` identity does not mean attempting to bypass module encapsulation.

### 8.4. `src-module/demo.feature/demo/feature/NamedTarget.java`

```java
package demo.feature;

public final class NamedTarget {
    public void execute(int value) {
    }
}
```

The named fixture has the same `execute(I)V` method descriptor as the unnamed fixture, but a different class/loader/module context. The goal is to create **a real module resolved in the boot layer**, not just fabricate a `"demo.feature"` string.

### 8.5. `src-main/FilterHarness.java` — Complete Test

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class FilterHarness {
    private static int checks;

    record Seen(
            String internalName,
            String methodName,
            String descriptor,
            ClassLoader loader,
            Module module) {
    }

    record Rule(
            String internalName,
            String methodName,
            String descriptor,
            ClassLoader approvedLoader,
            Module approvedModule) {

        Rule {
            Objects.requireNonNull(internalName);
            Objects.requireNonNull(methodName);
            Objects.requireNonNull(descriptor);
            Objects.requireNonNull(approvedModule);
        }

        boolean accepts(Seen seen) {
            return seen != null
                    && seen.internalName() != null
                    && seen.methodName() != null
                    && seen.descriptor() != null
                    && seen.module() != null
                    && internalName.equals(seen.internalName())
                    && methodName.equals(seen.methodName())
                    && descriptor.equals(seen.descriptor())
                    && approvedLoader == seen.loader()
                    && approvedModule == seen.module();
        }
    }

    record MethodKey(String name, String descriptor) {
    }

    private static void check(String label, boolean expected,
            boolean actual) {
        if (actual != expected) {
            throw new AssertionError(
                    label + " expected=" + expected
                    + " actual=" + actual);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    private static void requireMethod(
            List<MethodKey> keys, String name, String descriptor) {
        if (!keys.contains(new MethodKey(name, descriptor))) {
            throw new AssertionError(
                    "Method missing: " + name + descriptor);
        }
    }

    private static void skipAttributes(
            DataInputStream in, int count) throws IOException {
        for (int i = 0; i < count; i++) {
            in.readUnsignedShort(); // attribute_name_index
            long length = Integer.toUnsignedLong(in.readInt());
            in.skipNBytes(length);
        }
    }

    // Minimal parser for tests. DO NOT use as a production bytecode library.
    private static List<MethodKey> readMethods(Path classFile)
            throws IOException {
        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(classFile))) {

            if (in.readInt() != 0xCAFEBABE) {
                throw new IOException("Not a class file");
            }
            in.readUnsignedShort(); // minor_version
            in.readUnsignedShort(); // major_version

            int constantPoolCount = in.readUnsignedShort();
            String[] utf8 = new String[constantPoolCount];

            for (int index = 1; index < constantPoolCount; index++) {
                int tag = in.readUnsignedByte();
                switch (tag) {
                    case 1 -> utf8[index] = in.readUTF();
                    case 3, 4 -> in.skipNBytes(4);
                    case 5, 6 -> {
                        in.skipNBytes(8);
                        index++; // long/double occupy 2 cp slots
                    }
                    case 7, 8, 16, 19, 20 -> in.skipNBytes(2);
                    case 9, 10, 11, 12, 17, 18 ->
                            in.skipNBytes(4);
                    case 15 -> in.skipNBytes(3);
                    default -> throw new IOException(
                            "Unsupported cp tag=" + tag);
                }
            }

            in.readUnsignedShort(); // access_flags
            in.readUnsignedShort(); // this_class
            in.readUnsignedShort(); // super_class

            int interfaces = in.readUnsignedShort();
            in.skipNBytes((long) interfaces * 2);

            int fields = in.readUnsignedShort();
            for (int i = 0; i < fields; i++) {
                in.readUnsignedShort(); // access_flags
                in.readUnsignedShort(); // name_index
                in.readUnsignedShort(); // descriptor_index
                skipAttributes(in, in.readUnsignedShort());
            }

            int methods = in.readUnsignedShort();
            List<MethodKey> result = new ArrayList<>();
            for (int i = 0; i < methods; i++) {
                in.readUnsignedShort(); // access_flags
                int nameIndex = in.readUnsignedShort();
                int descriptorIndex = in.readUnsignedShort();
                result.add(new MethodKey(
                        utf8[nameIndex], utf8[descriptorIndex]));
                skipAttributes(in, in.readUnsignedShort());
            }
            return result;
        }
    }

    private static Seen seen(
            Class<?> type, String method, String descriptor) {
        return new Seen(
                type.getName().replace('.', '/'),
                method,
                descriptor,
                type.getClassLoader(),
                type.getModule());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: FilterHarness <build/target>");
        }

        Path targetDir = Path.of(args[0]);
        List<MethodKey> keys = readMethods(
                targetDir.resolve("sample/ProbeTarget.class"));

        requireMethod(keys, "execute", "(I)V");
        requireMethod(
                keys, "execute", "(Ljava/lang/String;)V");
        requireMethod(
                keys, "transform", "([I)[Ljava/lang/String;");
        requireMethod(keys, "<init>", "()V");

        URL url = targetDir.toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] {url},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[] {url},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> classA = Class.forName(
                    "sample.ProbeTarget", false, first);
            Class<?> classB = Class.forName(
                    "sample.ProbeTarget", false, second);

            if (classA == classB
                    || classA.getClassLoader() != first
                    || classB.getClassLoader() != second
                    || classA.getModule() == classB.getModule()) {
                throw new AssertionError(
                        "Fixture class loaders are not isolated");
            }

            Module moduleA = classA.getModule();
            Module moduleB = classB.getModule();

            Rule rule = new Rule(
                    "sample/ProbeTarget", "execute", "(I)V",
                    first, moduleA);

            Seen a = seen(classA, "execute", "(I)V");
            Seen b = seen(classB, "execute", "(I)V");

            check("BASELINE_ALLOWED", true, rule.accepts(a));
            check("OVERLOAD_DENIED", false,
                    rule.accepts(seen(
                            classA, "execute",
                            "(Ljava/lang/String;)V")));
            check("RETURN_DESCRIPTOR_DENIED", false,
                    rule.accepts(seen(
                            classA, "execute", "(I)I")));
            check("METHOD_NAME_DENIED", false,
                    rule.accepts(seen(
                            classA, "transform", "(I)V")));
            check("CONSTRUCTOR_DENIED", false,
                    rule.accepts(seen(
                            classA, "<init>", "()V")));
            check("CLASS_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/Other", "execute", "(I)V",
                            first, moduleA)));
            check("DOT_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            "sample.ProbeTarget", "execute", "(I)V",
                            first, moduleA)));
            check("SECOND_LOADER_DENIED", false, rule.accepts(b));
            check("WRONG_MODULE_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            first, moduleB)));
            check("BOOTSTRAP_LOADER_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            null, String.class.getModule())));
            check("NULL_CLASS_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            null, "execute", "(I)V",
                            first, moduleA)));
            check("NULL_MODULE_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            first, null)));

            Rule arrayRule = new Rule(
                    "sample/ProbeTarget",
                    "transform",
                    "([I)[Ljava/lang/String;",
                    first, moduleA);
            check("ARRAY_DESCRIPTOR_ALLOWED", true,
                    arrayRule.accepts(
                            seen(classA, "transform",
                                    "([I)[Ljava/lang/String;")));
            check("ARRAY_DESCRIPTOR_DENIED", false,
                    arrayRule.accepts(
                            seen(classA, "transform",
                                    "([Ljava/lang/String;)V")));

            Module namedModule = ModuleLayer.boot()
                    .findModule("demo.feature")
                    .orElseThrow();
            Class<?> namedClass = Class.forName(
                    namedModule, "demo.feature.NamedTarget");
            if (namedClass == null) {
                throw new AssertionError(
                        "Named fixture not found");
            }
            Rule namedRule = new Rule(
                    "demo/feature/NamedTarget", "execute", "(I)V",
                    namedClass.getClassLoader(),
                    namedModule);

            check("NAMED_MODULE_ALLOWED", true,
                    namedRule.accepts(
                            seen(namedClass, "execute", "(I)V")));
            check("UNNAMED_MODULE_DENIED", false,
                    namedRule.accepts(a));
            check("NAMED_WRONG_MODULE_DENIED", false,
                    namedRule.accepts(new Seen(
                            "demo/feature/NamedTarget",
                            "execute", "(I)V",
                            namedClass.getClassLoader(),
                            moduleA)));
        }

        System.out.println("ALL_TESTS_PASSED=" + checks);
    }
}
```

**About the parser in the test:** `DataInputStream.readUTF` suffices for the ASCII constant-pool strings in this fixture; this code illustrates accessing `method_info`/`descriptor_index`, not a complete class-file parsing library for handling untrusted classfile data. Production requires a reliable parser with full validation of classfile structure, attributes, versions, and byte offsets. The test parser neither generates nor modifies bytecode, so there is no risk of corrupting verifier frames in the demo.

**About synthetic context cases:** `WRONG_MODULE_DENIED` and `NAMED_WRONG_MODULE_DENIED` intentionally mix contexts to **isolate the module branch of the predicate**, rather than pretending to be a real class–module pair produced by the JVM. The cases `SECOND_LOADER_DENIED`, `NAMED_MODULE_ALLOWED`, and `UNNAMED_MODULE_DENIED` rely on **real `Class`/`Loader`/`Module` objects**. Both kinds of tests are useful, but they must be clearly labeled.

### 8.6. Compile and Run Commands (Bash/macOS/Linux)

From `filter-lab`:

```shell
mkdir -p build/target build/main mods/demo.feature

# Compile the fixture into the target directory only.
javac -d build/target src-target/sample/ProbeTarget.java

# Compile the named module independently.
javac -d mods/demo.feature \
  src-module/demo.feature/module-info.java \
  src-module/demo.feature/demo/feature/NamedTarget.java

# The harness has no compile-time dependency on the two fixtures.
javac -d build/main src-main/FilterHarness.java

# Only build/main is on the classpath.
# Fixture 1 is loaded via two separate URLClassLoaders.
# Fixture 2 is a named module resolved via --add-modules.
java --module-path mods --add-modules demo.feature \
  -cp build/main FilterHarness build/target
```

For Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build/target, build/main, mods/demo.feature | Out-Null
javac -d build/target src-target/sample/ProbeTarget.java
javac -d mods/demo.feature src-module/demo.feature/module-info.java src-module/demo.feature/demo/feature/NamedTarget.java
javac -d build/main src-main/FilterHarness.java
java --module-path mods --add-modules demo.feature -cp build/main FilterHarness build/target
```

In both cases, `build/target` is **not** on `-cp`. If you add it to the classpath, the parent loader can find `sample.ProbeTarget` and both `URLClassLoader`s will receive the same class, breaking the condition of testing two defining loaders.

### 8.7. Expected Stdout

```text
PASS BASELINE_ALLOWED
PASS OVERLOAD_DENIED
PASS RETURN_DESCRIPTOR_DENIED
PASS METHOD_NAME_DENIED
PASS CONSTRUCTOR_DENIED
PASS CLASS_NAME_DENIED
PASS DOT_NAME_DENIED
PASS SECOND_LOADER_DENIED
PASS WRONG_MODULE_DENIED
PASS BOOTSTRAP_LOADER_DENIED
PASS NULL_CLASS_NAME_DENIED
PASS NULL_MODULE_DENIED
PASS ARRAY_DESCRIPTOR_ALLOWED
PASS ARRAY_DESCRIPTOR_DENIED
PASS NAMED_MODULE_ALLOWED
PASS UNNAMED_MODULE_DENIED
PASS NAMED_WRONG_MODULE_DENIED
ALL_TESTS_PASSED=17
```

If `ALL_TESTS_PASSED` does not equal 17 or an `AssertionError` occurs, investigate the fixture/compiler/classpath/module path and predicate—**do not** delete negative tests to make them pass. The output above is **expected and derived from the source**; when studying locally, run the commands to confirm. This lesson does not claim to have observed stdout in the reader's environment.

### 8.8. Why Is This a Test Harness and Not a Complete Java Agent?

`FilterHarness` verifies **rules** and **real metadata**. It does not register a `ClassFileTransformer` and does not generate probe bytes. This is an intentional choice to isolate bugs: if the filter is wrong, we catch it before having to debug `VerifyError`, module readability, class loading recursion, or bytecode frameworks.

Agent integration also requires `premain`/`agentmain`, `Instrumentation.addTransformer`, parsing the incoming class file in the callback, generating valid bytecode, checking retransformation capability when applying to already-loaded classes, and verifying real method invocations.

## 9. Connecting the Filter to `ClassFileTransformer`

In Java 9+, you should **override the six-parameter overload that takes `Module`**. The older five-parameter overload still works, but if you only override that version and rely on a context that does not pass the module, it is very difficult to properly test module-based policies in the callback.

### 9.1. Java 17+ Callback Skeleton (Not a Standalone Runnable Agent)

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

// Skeleton; missing specific policy/bytecode parser.
final class FilteringTransformer implements ClassFileTransformer {
    private final ClassLoader approvedLoader;
    private final Module approvedModule;

    FilteringTransformer(ClassLoader approvedLoader, Module approvedModule) {
        this.approvedLoader = approvedLoader;
        this.approvedModule = approvedModule;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if (!"sample/ProbeTarget".equals(className)) {
            return null;
        }
        if (loader != approvedLoader || module != approvedModule) {
            return null;
        }

        // Next steps in a REAL transformer:
        // 1. Parse classfileBuffer into method_info entries.
        // 2. Match only name "execute" and descriptor "(I)V".
        // 3. If the target method is absent, return null.
        // 4. If present, use a bytecode library to modify the body validly.
        // 5. Return new class bytes; if unmodified, return null.
        return null; // Skeleton only proves the class gate.
    }
}
```

**Do not put this skeleton into production and claim instrumentation is active.** It always `return null` and does not alter bytecode. It also holds a strong reference to `approvedLoader`; if the app has a redeploy lifecycle, manage lifetimes or use a safe scoped/weak-identity architecture. This section only shows **the right place to apply the four criteria** in a real implementation.

### 9.2. ASM Method Visitor (Illustrative, Depends on ASM 9+)

If the application already has a compatible ASM dependency, the transformer can inspect method descriptors:

```java
// Illustrative snippet using ASM; does not compile standalone.
// import org.objectweb.asm.*; requires a compatible ASM dependency.
ClassReader reader = new ClassReader(classfileBuffer);

reader.accept(new ClassVisitor(Opcodes.ASM9) {
    @Override
    public MethodVisitor visitMethod(
            int access,
            String name,
            String descriptor,
            String signature,
            String[] exceptions) {

        boolean target =
                "execute".equals(name)
                && "(I)V".equals(descriptor);

        if (target) {
            // Check ACC_NATIVE/ACC_ABSTRACT/ACC_BRIDGE/ACC_SYNTHETIC
            // depending on the feature, then create a MethodVisitor to modify bytecode.
        }
        return super.visitMethod(
                access, name, descriptor, signature, exceptions);
    }
}, 0);
```

**Key point:** `descriptor` (the third parameter of `visitMethod`) is the JVM method descriptor. `signature` (the next parameter) is the optional generic signature, which may be `null`. Do not use `signature` as the primary match condition for method resolution.

A real transformer must also set up a `ClassWriter`/writer visitor chain, handle stack maps/frames, local variables, exception handlers, verifier compatibility, and return bytes only when a transformation occurred. If using `COMPUTE_FRAMES`, understand how ASM's resolver finds common superclasses to avoid inadvertently loading classes from other loaders; that is a separate risk outside the filter.

### 9.3. Java Class-File API by JDK Version

The Java Class-File API was standardized in JDK 24 (JEP 484). **Do not** copy JDK 24/25 `java.lang.classfile` code into a Java 17 program and claim it is runnable; Java 17–23 do not include that final API. This lesson uses Java 17+ code and only describes replacing the parser with the appropriate API when the runtime/toolchain supports it.

Do not use `jdk.internal.org.objectweb.asm` from the JDK as a default dependency: it is an internal API with encapsulation and compatibility risks; use a managed/versioned bytecode library or the corresponding standard API.

## 10. Testing with a Real Agent: Positive and Negative Matrix

Once you have a code-generating transformer, run **a complete test matrix** rather than merely looking for a single `TRANSFORMED` log line.

| Test Case | Class / internal name | Descriptor | Loader | Module | Expected |
|---|---|---|---|---|---|
| Exact target | Target | `execute(I)V` | A | UA | **ALLOW** |
| String overload | Target | `execute(Ljava/lang/String;)V` | A | UA | DENY |
| Changed return type | Target | `execute(I)I` | A | UA | DENY |
| Constructor | Target | `<init>()V` | A | UA | DENY if only measuring `execute` |
| Similar class name | `sample/ProbeTargets` | `execute(I)V` | A | UA | DENY |
| Dot-separated name | `sample.ProbeTarget` | `execute(I)V` | A | UA | DENY (wrong callback format) |
| Same name in loader B | Target | `execute(I)V` | B | UB | DENY |
| Wrong module | Target | `execute(I)V` | A | other module | DENY (pure predicate) |
| Bootstrap null loader | Target | `execute(I)V` | null | bootstrap module | DENY |
| Null class name | null | `execute(I)V` | A | UA | DENY |
| Null module | Target | `execute(I)V` | A | null | DENY |
| Matching array descriptor | Target | `transform([I)[Ljava/lang/String;` | A | UA | ALLOW per separate array rule |
| Matching named target | `demo/feature/NamedTarget` | `execute(I)V` | named loader | named module | ALLOW per separate named rule |
| Swapped named/unnamed | Named context against UA rule | `execute(I)V` | any | other module | DENY |
| Duplicate instrumentation | Target already has probe marker | `execute(I)V` | A | UA | SKIP/IDEMPOTENT |
| Method not found | Target only has other signatures | target descriptor absent | A | UA | SKIP |
| Unmodifiable class | Target already loaded, retransform unsupported | target | A | UA | SKIP_WITH_REASON |
| Bytecode parser error | Corrupted `classfileBuffer` | unknown | A | UA | FAIL/SKIP per policy, do not instrument blindly |

In the table, UA and UB are **distinct** unnamed modules of loaders A and B. Rows with loader/module combinations that a real JVM cannot produce are used to test **predicate logic**; integration tests must use valid object contexts.

### 10.1. Test the *Absence* of Instrumentation Too

If the goal is to instrument only `execute(I)V`, invoke:

- `execute(int)` on class A: the probe marker increments exactly once per invocation.
- `execute(String)` on class A: the marker does not increment.
- `execute(int)` on class B: the marker does not increment.
- A class with the same prefix but different internal name: the marker does not increment.
- A method with the same name in a different named module: the marker does not increment when outside the policy.

Verify that the method's output/behavior remains identical to before the agent was enabled. A `SKIP` log alone is not enough; verify **unchanged bytecode/effects** or confirm the absence of markers for excluded cases. However, do not emit millions of logs for every excluded JDK class in production.

### 10.2. Testing Classes Loaded Before Agent Registration

`addTransformer` only applies to relevant class definitions/lifecycle events per contract; a class already loaded before the agent is registered does not automatically pass through `transform` just because the agent appeared. To apply to already-loaded classes, check:

```java
// Snippet inside an agent, not a standalone file.
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
```

This is the **retransformation** step, which has class schema, ordering, and `canRetransform` constraints. During retransformation, `classBeingRedefined` is typically the `Class<?>` object being replaced; during initial load, it is `null`. Test both paths if the feature claims to support them.

### 10.3. Do Not Ignore the Old Overload When Overriding the Module Overload

In `ClassFileTransformer`, the default implementation of the six-parameter overload delegates to the five-parameter version; if you only override the five-parameter version, you still get callbacks, but lose the ability to rely directly on `Module` inside that method. Conversely, if you only override the six-parameter version per Java 9+, the JVM calls the new overload in standard environments. Unit tests should catch adapters that accidentally invoke the module-less overload when production policy requires module identity.

## 11. Placing Test Fixtures Along Truly Meaningful Boundaries

### 11.1. One Class Name, Two Different Loaders

**Mandatory** for agents running in application servers, servlet containers, plugin environments, or OSGi-like module boundaries. Do not create two variables pointing to the **same `URLClassLoader` instance** and treat them as two loaders. You must actually call `new URLClassLoader(...)` twice and verify:

```java
classA != classB
classA.getName().equals(classB.getName())
classA.getClassLoader() != classB.getClassLoader()
```

These expressions are only illustrative expressions; in `FilterHarness` in Section 8, concrete objects are created and verified.

### 11.2. One Loader, Multiple Named Modules

A single class loader can be associated with multiple modules, especially in complex module layers/frameworks. Therefore, a policy that only compares the loader is not enough. If a feature is only valid for module `foo`, test a class in another module loaded by the same loader to ensure the module guard works.

When you need to distinguish **two layers that have the same module name**, construct two `ModuleLayer` instances in an integration test and compare `Module` identity. A predicate that only uses `module.getName()` will mistakenly match both. This is an edge case to prioritize when your agent supports dynamic plugin layers.

### 11.3. Bootstrap Loader

If the policy must not touch JDK classes, test `loader == null` with an internal name like `java/lang/String`. Real bootstrap callbacks can occur if JVM/agent configuration permits them; helpers must be visible to the bootstrap loader when needed. **Never** treat `loader == null` as a wildcard for "any loader".

### 11.4. Nested Classes, Arrays, Generics, and Bridges

- Nested: `Outer$Inner`, not `Outer.Inner`, in binary names.
- Arrays: `[I`, `[Ljava/lang/String;` are type descriptors; they are not method-bearing class files that can be processed identically to normal classes.
- Generics: match the **erased JVM descriptor**, not `Signature`.
- Bridge/synthetic: instrumenting both the bridge and the implementation can measure a single Java source call **twice** because the bridge forwards to the implementation. Test exact access flags to decide intentionally.
- Records: accessors, constructors, and synthetic details must be verified against the actual compiler-generated classfile output.
- Interface methods / default methods: descriptors are still JVM descriptors, but bytecode injection and call paths differ from ordinary class methods.
- Lambdas / hidden classes: do not rely on auto-generated names as a stable API; test policies against actual observations and fail safely.

## 12. Diagnostics Without Overloading the System

### 12.1. Log a Concise Decision with Enough Traceability to Reproduce

A sample test record:

```json
{
  "operation": "CLASS_FILTER",
  "classInternalName": "sample/ProbeTarget",
  "methodName": "execute",
  "descriptor": "(I)V",
  "loaderTag": "A",
  "moduleName": null,
  "moduleKind": "UNNAMED",
  "decision": "ALLOW",
  "reason": "EXACT_FOUR_DIMENSION_MATCH",
  "bytecodeChanged": false
}
```

**This is an illustrative diagnostic schema**, not automatic output from a Java agent. `loaderTag=A` is a tag from the test fixture; in production, do not use arbitrary tags as the basis for authorization. `bytecodeChanged=false` matches the predicate harness: it only decides and does not generate probes yet.

### 12.2. Connecting Invocations to Effects

A test report should include:

```text
targetCount=1
matchedMethodCount=1
transformedClassCount=1
verifiedProbeCallCount=1
unexpectedTransformCount=0
wrongLoaderMatchCount=0
wrongModuleMatchCount=0
verifyErrorCount=0
```

This is a **sample criterion** for a single-target test, not a default count for every application. If the target has not been loaded/called, `verifiedProbeCallCount=0` can be completely valid; do not falsely report a test pass based solely on the matcher.

### 12.3. Avoid Logging Unbounded Dynamic Labels

An agent observes tens of thousands of class names and loader identities. Do not put every `className`, `descriptor`, full classloader `toString`, or protection domain URL into metric labels: this can cause high cardinality, increase memory/CPU usage, and leak deployment paths.

Use finite reason codes, sampling, and time-bounded debug logging. When detailed diagnostics are needed, record class/loader/module names under a bounded policy, and do not serialize `ClassLoader` or `ProtectionDomain` into object graphs.

### 12.4. Exceptions to Triage

| Symptom | Analysis Step |
|---|---|
| Target never matches | Check internal name format, method descriptor, loader/module identity |
| Target matches multiple times | Check retransform, multiple transformers, probe idempotency |
| `ClassNotFoundException` from helper | Likely helper visibility issue, not the filter rule |
| `NoClassDefFoundError` when invoking probe | Linkage/helper class loader/module readability, inspect inserted bytecode |
| `ClassCastException: X cannot be cast to X` | Likely same name defined by two defining loaders |
| `IllegalAccessError` | Incompatible module/loader/package runtime access |
| `VerifyError` | Invalid bytecode frames/stack/locals after transformation |
| `ClassFormatError` | Invalid final class bytes |
| `UnsupportedOperationException` in retransform | Capability/schema limitation |
| Probe placed in wrong overload | Matched method name but ignored descriptor |
| Probe placed in app in another plugin | Matched class name but ignored loader/module identity |
| No probe despite filter allow | Bytecode transform returned `null`, class not loaded, or method never invoked |

## 13. Avoiding Bugs from Concurrent Instrumentation or Redeploys

The filter is invoked by the JVM under varying circumstances, potentially across multiple threads when class loading happens concurrently. A good policy is **immutable** once created, or uses a configuration update mechanism with clear memory visibility.

- Do not use an unsynchronized mutable `HashMap` for a runtime allowlist written from another thread.
- Do not use `loader.getName()` in place of loader identity, even in caches.
- Do not hold strong references to application classloaders in an agent cache for the lifetime of the JVM if classloaders must be freed on redeploy.
- Do not call `Class.forName` from the transformer to determine method signatures, avoiding class-loading recursion.
- Do not reflect on a target class currently being defined; parse `classfileBuffer`.
- Do not retain raw `classfileBuffer`s for all classes in a static list for debugging; bytecode histories can become huge.
- With multiple transformer instances, test transformation order and ensure removing one plugin does not inadvertently alter another plugin's filter scope.
- If the policy is reloaded at runtime, test the old config, the new config, and the preflight window before retransformation.
- For hidden/generated classes, instrument only when exact details are verified and the agent has a specific purpose.

**Filter atomicity:** A five-field predicate in an immutable record/rule prevents a request from seeing a combination of a new name rule with an old loader rule. When updating policy, publish **a new immutable `Rule`/`RuleSet`** via a `volatile` reference; do not mutate separate maps/sets independently without synchronization.

## 14. Common Mistakes

1. **Comparing `"com.acme.Foo"` against the callback `className`.** Wrong format; the callback uses `com/acme/Foo`.
2. **Filtering only by package prefix without a trailing `/`.** Can match similarly named packages.
3. **Comparing only the method name.** Can instrument the wrong overload.
4. **Using generic `Signature` instead of `descriptor`.** Wrong for erased JVM method types.
5. **Omitting the return type from the descriptor.** No longer matches the full descriptor.
6. **Comparing class loaders by `getClass().getName()`.** Multiple instances of the same loader class can define the same binary name.
7. **Treating a `null` loader as the system loader.** A `null` callback loader represents the bootstrap loader.
8. **Comparing only the module name.** Fails to distinguish multiple layers/module objects with the same name.
9. **Treating an unnamed module as `null`.** Unnamed modules are still `Module` objects; only `getName()` returns `null`.
10. **Calling `Class.forName` inside `transform` to look up metadata.** Can cause recursive loading/deadlock and the target is not yet defined.
11. **Using `classBeingRedefined` in a load-time callback without a null check.** During normal loading it is `null`.
12. **Having no negative tests.** Passing the happy path does not prove you are not over-instrumenting.
13. **Assuming `transform` returning bytes means the probe ran.** The JVM must still accept the class and the method must be invoked.
14. **Allowing when module/descriptor is missing.** Not fail-closed.
15. **Holding strong `ClassLoader` references indefinitely in the agent.** Can cause retention / class-unloading leaks.
16. **Logging all class names on every callback.** Can cause massive overhead/cardinality.
17. **Using reflection `getMethods()` on the transform path.** Unsuitable for unloaded classes and may miss private/declaration semantics.
18. **Ignoring bridge/synthetic/constructor access flags.** Can double-instrument or produce invalid bytecode.
19. **Testing a loader by calling `child.loadClass` without checking the defining loader.** Parent delegation may return a parent-defined class.
20. **Assuming JDK 17 has the standard Java Class-File API.** The standard API was introduced in JDK 24; Java 17 requires another library/reader.
21. **Not testing idempotency on retransformation.** Can create multiple probe layers or measure the same method twice.
22. **Modifying formatting/source cells just to inspect results more easily.** For a content-filling task, touch only the exact assigned target area.
23. **Confusing module visibility with filtering.** The policy may match correctly while the helper still fails to link across JPMS/loader boundaries.
24. **Using broad regexes to match all classes instead of an approved policy.** Can touch out-of-scope frameworks/JDK/plugins.

## 15. Pre-Enablement QA Checklist for Agents

### Filter Definition

- [ ] Are class names in configuration normalized to internal form and checked for exact/prefix boundaries?
- [ ] Does the rule include both method name and **full descriptor**?
- [ ] Is the bootstrap policy defined for when `loader == null`?
- [ ] When loader-specific scope is needed, does it compare the exact `ClassLoader` instance without pinning the loader indefinitely?
- [ ] When module-specific scope is needed, does it compare the exact `Module` object and handle named/unnamed modules?
- [ ] Are missing class name/module/descriptor denied with a reason?
- [ ] Are constructors/initializers and bridge/synthetic methods handled intentionally?

### Unit Tests

- [ ] Happy path for an exact class + method.
- [ ] Overloads with the same name but different argument descriptors.
- [ ] Wrong return descriptor.
- [ ] Wrong binary/internal name format and near-matching prefixes.
- [ ] Two distinct defining loaders for the same binary name.
- [ ] Named module, unnamed module, and distinct `Module` identities.
- [ ] Bootstrap `null` loader / unknown inputs.
- [ ] Methods with arrays, objects, and generic erasure.
- [ ] Classfile fixture parser accurately reads `method_info`, without using reflection to substitute for bytes of an undefined class.

### Integration Tests

- [ ] Java agent registers the callback overload with the `Module` parameter.
- [ ] Only allowed class + method are modified; test the absence of markers as well.
- [ ] Probes preserve business behavior, return values, and exceptions.
- [ ] Both new class loads and retransformations (if applicable) are tested.
- [ ] Bytecode is valid according to the real JVM verifier, with no `VerifyError`/`LinkageError`.
- [ ] Agent helpers/dependencies are not instrumented, avoiding recursion.
- [ ] Classloader unload/redeploy does not leave stale policies or memory leaks.
- [ ] Rejection reason logs are bounded and contain no sensitive user data.

## 16. Self-Check Questions

1. **In what format does the `ClassFileTransformer` callback pass `java.lang.String`?** `java/lang/String`.
2. **Why is `className` insufficient to uniquely identify a class?** Two defining loaders can define the same binary name.
3. **What is the descriptor of `void execute(int)`?** `(I)V`.
4. **What is the descriptor of `void execute(String)`?** `(Ljava/lang/String;)V`.
5. **What is the descriptor of `String[] transform(int[])`?** `([I)[Ljava/lang/String;`.
6. **Does generic `List<String>` appear directly in a method descriptor?** No; the descriptor uses the erased class type.
7. **What does `loader == null` mean in the callback?** The bootstrap loader, not a wildcard or the system loader.
8. **Do different class loader names prove different `Class` identities?** No; you must identify the defining loader object.
9. **Can two different `URLClassLoader`s loading the same class file create two different `Class` objects?** Yes, if each loader defines it itself and does not delegate the target to the parent.
10. **Does `Module.getName() == null` mean the module argument is `null`?** No, it can be an unnamed `Module` object.
11. **Is comparing `module.getName()` enough when multiple module layers exist?** No, use `Module` identity when the scope requires it.
12. **Which parameter of the class-level callback provides the method descriptor?** No direct parameter; you must parse `classfileBuffer`.
13. **Why shouldn't you call `Class.forName` inside the transformer to inspect methods?** It can trigger reentrant class loading and the target is not yet defined.
14. **What is `classBeingRedefined` typically during a new class load?** `null`.
15. **If the predicate passes but the transformer returns `null`, is the class modified?** Not by that transformer step.
16. **If a method is instrumented but never called, has the probe effect been proven?** No; you must verify the effect upon invocation.
17. **Why are negative overload tests needed?** To ensure signatures with the same name are not mistakenly instrumented.
18. **Why test a class with the same name in loader B?** To prove the loader-specific boundary is enforced.
19. **Can `isNamed()` replace module identity?** No; it only tells whether the module is named or unnamed.
20. **If module info is missing in a pure test, what should happen?** Deny under the fail-closed policy and report `SKIP_UNKNOWN_CONTEXT`.
21. **If classloaders need to be unloaded, what is the risk of holding a strong reference to `approvedLoader` in a singleton agent?** Classloader retention; lifecycle must be managed.
22. **In the demo, what does `ALL_TESTS_PASSED=17` prove?** It only proves the written predicate/metadata/loader/module tests passed; it does not prove bytecode probes were inserted.
23. **What can a package-prefix rule `"com/acme/pay"` mistakenly match?** `com/acme/payment` or other packages/classes sharing that prefix.
24. **When the module matches but the helper cannot be loaded, should you relax the filter?** No; resolve class-loader visibility/linkage separately.

## 17. Official References

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `transform(Module,ClassLoader,String,Class<?>,ProtectionDomain,byte[])` callback, internal class name, defining loader, `classBeingRedefined`, and returning `null`.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): contract compatible with the Java 17+ example.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `isModifiableClass`, capabilities, and transformation ordering.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loaders, parent delegation, and per-loader unnamed modules.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): named/unnamed, `getName`, `getLayer`, and runtime module identity.
- [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getModule`, `getClassLoader`, `Class.forName(Module,String)`.
- [Java SE 21 — `MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): `toMethodDescriptorString` and JVM descriptors.
- [JVMS SE 21 — `4.3 Descriptors`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): type descriptors and method descriptor grammar.
- [JVMS SE 21 — `4.6 Methods`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6): `method_info`, `name_index`, `descriptor_index`, and method access flags.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup, class transformations, and JPMS read edges.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): Java Class-File API standardized in JDK 24 (not Java 17).

**Conclusion:** Testing Instrumentation filters means **testing the right class, the right method signature, the right class loader, and the right module**, not just a `startsWith` check on the class name. Use **internal class names**, **full JVM descriptors**, **`ClassLoader`/`Module` identity**, negative test cases, and post-transformation probe effect verification. When any criterion cannot be verified, **denying with a reason** is safer than instrumenting on a guess.
