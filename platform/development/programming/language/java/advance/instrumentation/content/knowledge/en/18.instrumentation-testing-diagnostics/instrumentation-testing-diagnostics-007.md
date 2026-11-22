# Testing bridge, synthetic, lambda, record, sealed class, and multiple class loaders

In Java Instrumentation, a `ClassFileTransformer` does not only encounter "normal" classes and methods written by developers. The compiler and JVM can generate **bridge methods**, **synthetic members**, **lambda** support structures, **record classes**, **sealed hierarchies**, and classes with the **same binary name defined by different class loaders**. If a transformer is only tested on a simple POJO, it may accidentally double-instrument methods, miss lambda bodies, corrupt record/sealed class metadata, or conflate class identities across multiple loaders.

This lesson belongs to the **Testing and Diagnostics** topic of Java Advance — Instrumentation. The goal is to build a **reproducible test suite**, observe both bytecode and runtime behavior, and verify that the agent handles special cases correctly. We will compile with **Java 17+**, using reflection, `javap -v`, a **real Java agent**, and two **custom class loaders**. The example suite was compiled with `javac --release 17` and ran successfully on JDK 24.

**Overarching principle:** test all three layers of information — **source/compile-time structure**, **class-file metadata**, and **runtime identity/behavior**. Do not assume that compiler-generated method names are always fixed; do not assume two classes with the same name are the same class; do not treat a transformer callback as proof that bytecode was modified if the transformer only returns `null`.

## 1. Risk matrix to cover

| Special type | Signals to detect | Instrumentation risk | What to verify |
| --- | --- | --- | --- |
| **Bridge method** | `Method.isBridge()`; `ACC_BRIDGE`, often with `ACC_SYNTHETIC` | Instrumenting both the bridge and the real method causes double-counting; mistakenly changing the descriptor | Erased calls and typed calls still dispatch correctly |
| **Synthetic method/member** | `Member.isSynthetic()`; `ACC_SYNTHETIC` | Excluding all synthetics may miss necessary compiler-generated code | Intentional include/exclude policy |
| **Lambda expression** | `invokedynamic`, `lambda$...` methods in some compilers, runtime lambda class | Assuming a lambda proxy is always a normal, modifiable class | Behavior is correct; if hidden, handle according to JVM capabilities |
| **Record** | `Class.isRecord()`, `Record` attribute, record components | Changing component/constructor structure or metadata rejected by verifier/JVM | Reflection components and accessors/results are unchanged beyond intentional changes |
| **Sealed class/interface** | `Class.isSealed()`, `PermittedSubclasses` attribute | Removing/modifying permitted hierarchy invalidly during retransform/redefine | Permits list and subtype dispatch are accurate |
| **Multiple class loaders** | Same `Class.getName()` but different `Class<?>`/loader identity | Caching by name conflates classes, transformer picks wrong target | Both definitions are distinguished and receive separate callbacks |
| **Special retransform** | `classBeingRedefined != null`, capability/modify checks | Attempting to retransform unmodifiable classes or add schema changes | Selected classes keep working, callbacks appear within the expected scope |

The test suite needs **negative-path checks** (classes that must be skipped), not just the happy path. Each row in the matrix maps to an observation technique: reflection, `javap`, `Instrumentation.isModifiableClass`, callback logs, identity comparison, or actual method invocations.

## 2. Distinguishing "compiler-generated" from "runtime-generated"

Java has two points in time where special structures are created:

1. **At compile time:** `javac` can generate bridge methods for generic overriding, generate synthetic methods as the implementation body of a lambda, and emit record/sealed metadata into the class file.
2. **At runtime:** The JVM/`LambdaMetafactory` can generate a class implementing a functional interface; a class loader can define the same binary name multiple times under different defining loaders; an agent can retransform already-loaded classes.

Not every compiler/JVM uses the same synthetic method names or the same lambda proxy mechanism. For example, `lambda$supplier$0` is a **common javac naming pattern**, not a Java source method with a public naming contract across all compilers. When testing instrumentation correctness, prioritize flags/descriptors/semantics; only assert a specific name pattern if the build **pins the compiler and version**.

### Three levels of assertions

| Level | Example | Portability |
| --- | --- | --- |
| **Behavior** | `((Base<String>) service).convert("hi")` returns `"HI"` | Tied to Java semantics defined by the test |
| **Reflection metadata** | `bridge.isBridge()`, `Event.class.isRecord()`, `Shape.class.isSealed()` | Standard Java API, applies according to the compiled class |
| **Compiler/JVM detail** | Method named `lambda$...`, lambda proxy has `isHidden()==true` | Compiler/runtime-dependent, needs matrix testing |

In the demo suite, we pin `javac --release 17` and a JDK 24 runtime, so we can record the **exact stdout** of that run. On other JVMs/Java compilers, tests for names and hidden lambda proxies should be checked against actual runtime results rather than hardcoding an assumed value.

## 3. Bridge methods: generic overrides require testing two call paths

Consider a generic class:

~~~java
abstract class Base<T> {
    public abstract T convert(T input);
}

final class StringService extends Base<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

This is an **illustrative source snippet**, also part of `Cases.java` in the complete demo. When `T` undergoes **type erasure**, the method in `Base<T>` has the equivalent JVM descriptor:

~~~text
convert(Ljava/lang/Object;)Ljava/lang/Object;
~~~

While the implementation has the signature:

~~~text
convert(Ljava/lang/String;)Ljava/lang/String;
~~~

To preserve overriding/polymorphism through the erased signature, `javac` generates a **bridge method** logically equivalent to:

~~~java
// Pseudocode: compiler-generated bridge, NOT declared in Java source.
public Object convert(Object input) {
    return convert((String) input);
}
~~~

The bridge has the erased descriptor `(Object)Object`, whereas the developer-written method accepts/returns `String`. In a class file generated by `javac`, the bridge typically has both `ACC_BRIDGE` and `ACC_SYNTHETIC`.

### The double-counting case

Suppose instrumentation inserts a counter at the **entry of every method** named `convert` without checking descriptor/flags:

~~~text
((Base<String>) service).convert("hi")
        |
        v
StringService.convert(Object) [bridge] -> counter +1
        |
        v
StringService.convert(String) [implementation] -> counter +1
        |
        v
"HI"
~~~

For **a single business call**, the counter can become 2. This is not a `LongAdder` bug or a JVM bug; it is a **method-selection policy** bug.

Valid approaches:

- **Method-level business metrics:** instrument only the implementation, skip the bridge; document the reason clearly.
- **Bytecode-call metrics:** measure both the bridge and the implementation if you genuinely want to know the entry count of each separate method body.
- **Boundary tracing:** instrument the entrypoint with a deduplication rule per logical invocation.
- **Validation:** assert `Method.isBridge()`/descriptor, the number of probes created, and call behavior through a generic reference.

**Do not blindly skip all synthetic methods**: bridges are usually synthetic, but other synthetics serve different roles (e.g., lambda implementations). The filter needs to combine `ACC_BRIDGE`, `ACC_SYNTHETIC`, method descriptor, and the measurement goal.

### Reflection check

~~~java
Method bridge = java.util.Arrays.stream(
        StringService.class.getDeclaredMethods())
        .filter(Method::isBridge)
        .findFirst()
        .orElseThrow();

System.out.println(bridge.isSynthetic());
~~~

This is an **illustrative snippet placed in a program that imports `java.lang.reflect.Method`**. For the demo class compiled by `javac`, the result is `true`. When you want to verify flags at the bytecode level, run:

~~~bash
javap -p -v -classpath app-bin tutorial.app.StringService
~~~

Look for the line:

~~~text
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

Do not confuse `ACC_BRIDGE` with a Java source modifier; the compiler uses it to mark a bridge method. When a transformer rewrites a method, **do not strip bridge flags/signatures** unless intentional and with a clear understanding of verifier/linkage constraints.

## 4. Synthetic members: not everything synthetic is a bridge

`Synthetic` means a class/member is marked as generated by a compiler or tool, not directly representing a normal source declaration. The corresponding reflection APIs:

- `Class.isSynthetic()` for classes.
- `Method.isSynthetic()` for methods.
- `Field.isSynthetic()` for fields.
- `Method.isBridge()` **only** for bridge methods.

There are synthetic methods that **are not bridges**. In the demo, `LambdaCase` contains a lambda expression, and `javac` creates a synthetic method to hold its body. Therefore, the classification:

~~~text
method.isBridge() == true   -> BRIDGE policy branch
method.isSynthetic() == true && !method.isBridge()
                            -> SYNTHETIC_NON_BRIDGE policy branch
normal method               -> NORMAL branch
~~~

This is an **agent-defined classification**, not three official API categories. It helps audit "why a method was skipped/measured." A codebase with annotation processing or Kotlin/Scala/other JVM languages may generate more synthetic members than plain Java; the test matrix should include the project's actual compilers.

### Descriptor matters more than method name

For a JVM class, method identity in bytecode is defined by **name and method descriptor**, not name alone. Two `convert` methods with different parameter types are two distinct methods. When finding a method to instrument, you must compare the descriptor as well to be exact; an ASM example:

~~~java
if (name.equals("convert")
        && descriptor.equals("(Ljava/lang/String;)Ljava/lang/String;")) {
    // Implementation method only, not the (Object)Object bridge.
}
~~~

This is an **illustrative code snippet inside an ASM MethodVisitor/ClassVisitor context**, and does not compile standalone without `name`, `descriptor`, and the ASM dependency. For production bytecode weaving, preserve access flags and method signature information to classify accurately.

## 5. Lambda: distinguishing invokedynamic, synthetic body, and runtime class

A Java lambda expression:

~~~java
final class LambdaCase {
    public java.util.function.Supplier<String> supplier(String suffix) {
        return () -> "x-" + suffix;
    }
}
~~~

In a class file compiled by `javac`, the lambda call site typically uses **`invokedynamic`** and bootstrap linkage involving `LambdaMetafactory`. The compiler may generate a method like `lambda$supplier$0` carrying `ACC_SYNTHETIC` to hold the body. However, the object implementing `Supplier<String>` at runtime has its own runtime class, which may be a **hidden class** depending on the JDK/JVM.

Key points to remember:

- **Synthetic lambda body method** may exist **inside the host class** `LambdaCase`.
- **Lambda implementation object** has `getClass()` different from `LambdaCase.class`.
- **Not every lambda must create a `lambda$...` method**. Some method references or compiler strategies may differ.
- **There is no guarantee a transformer will receive a class definition callback for every hidden lambda proxy** in the same way as named application classes. Use the right tool for the required level of observation.
- When a `Class<?>` is a hidden class, you must check `isModifiableClass`: do not blindly call `retransformClasses` on it.
- Do not use `lambdaProxy.getClass().getName()` followed by `Class.forName(...)` to try loading a "copy" of the runtime lambda class: a hidden class name is not a binary name resolvable through normal lookup.

In the verified JDK 24 run:

~~~text
lambdaSyntheticMethods=1
lambdaResult=x-lambda
lambdaProxyHidden=true
lambdaProxyModifiable=false
~~~

**Exact interpretation:** This is the output of **a specific `javac --release 17` and a specific JVM**. It proves the host class has one synthetic `lambda$...` method in this example; the runtime lambda proxy is hidden and unmodifiable in the test environment. Do not generalize this to "every lambda on every JVM has exactly one synthetic method/hidden class."

### Choosing a sensible lambda measurement point

| Measurement goal | Insertion point to consider | Additional testing needed |
| --- | --- | --- |
| How often code inside the lambda body runs | Host class method executing the body, if the compiler generates such a method | Synthetic method detection; exceptions/return values |
| Duration of functional API calls | Method calling `Supplier.get()` or an application-controlled API boundary | Do not turn every call into a double-count |
| Which lambda expressions are created | `invokedynamic`/factory invocation call site in the host class | Capture semantics, allocation, classloader |
| Runtime proxy behavior | Observe the object through API/application code | Hidden class, class identity, modifiability, and JVM-specific implementation |

With bytecode rewriting mechanisms, preserve bootstrap method arguments, `invokedynamic` descriptors, and captured values. Changing a lambda call site's descriptor without recomputing stack frames/bootstrap linkage can cause `VerifyError` or `BootstrapMethodError`.

## 6. Record: a structure with semantic meaning, not just a final class

A Java 17 record:

~~~java
record Event(String label, int count) { }
~~~

From Java source it looks short, but the compiler generates the required runtime members: private final fields for components, public component accessors, a canonical constructor, and implementations of `equals`, `hashCode`, and `toString`. The class file has a **`Record` attribute**; reflection provides:

~~~java
Event.class.isRecord();               // true
Event.class.getRecordComponents();   // two components: label, count
~~~

**Do not use method count as the sole criterion** to identify a record. Record components have their own API/attribute. With `javap -v`, a valid record generated by `javac` will show a section:

~~~text
Record:
  ...
~~~

The `...` here indicates **abbreviated `javap` output for illustration**, not content to copy into source; the runnable demo can use `javap -v` to inspect the details.

### Instrumenting a record without breaking its structure

A transformer can add logging/metrics into valid **method bodies**, but for already-loaded classes it must obey retransformation/redefinition limits. Do not arbitrarily add new fields for probes, remove record components, change component descriptors, change the `java.lang.Record` superclass, or corrupt the `Record` attribute.

Include these assertions:

1. `Event.class.isRecord() == true` before and after.
2. `getRecordComponents()` has the right count, names, and types.
3. Record accessors `label()` and `count()` return the right values.
4. `equals/hashCode/toString` still behave as required when the transformer injects code.
5. The canonical constructor still enforces application invariants.
6. Do not mistake final record fields for arbitrarily mutable state.
7. If serialization, reflection frameworks, or record-based DTO mapping are used, test together with those frameworks to catch regressions.

**Demo limitation:** it observes/retransforms but returns `null`, so it does not actually inject instructions. With a real bytecode patcher, add tests comparing post-patch results and JVM verifier checks.

## 7. Sealed class/interface: keeping the permitted class list intact

A Java 17 sealed interface:

~~~java
sealed interface Shape permits Circle, Rectangle {
    String kind();
}

final class Circle implements Shape {
    @Override
    public String kind() { return "circle"; }
}

non-sealed class Rectangle implements Shape {
    @Override
    public String kind() { return "rectangle"; }
}
~~~

Key concepts:

- `sealed` restricts which classes are directly permitted to `extends`/`implements`.
- Direct subtypes of a sealed type must declare one of `final`, `sealed`, or `non-sealed`, per Java rules.
- `non-sealed Rectangle` allows subclasses to continue extending it under normal class loading rules; this does **not** mean any class can become a direct subtype of `Shape`.
- The class file of a sealed type contains the **`PermittedSubclasses` attribute**.
- Reflection APIs `Class.isSealed()` and `getPermittedSubclasses()` can verify metadata.

In the demo:

~~~text
shapeIsSealed=true
permitted=Circle,Rectangle
shapeDispatch=circle
~~~

`permitted=...` is sorted by name in the test code for stable output; **do not assume reflection's return order is an arbitrary contract that tests should depend on**.

### Risks for redefinition/retransformation

For an already-loaded class, do not arbitrarily modify `PermittedSubclasses`, directly change `extends/implements`, or add/modify superclasses/fields/method descriptors at will. JVMTI enforces restrictions on class schema. Even if a byte array still parses, it may be rejected by the JVM when applied.

If an agent needs to patch the method body of `Shape.kind()` or a subtype, check:

- Whether the target is actually modifiable.
- That the output bytecode preserves class identity and valid structural attributes.
- That updated method dispatch still works through a `Shape`-typed reference.
- That the set of permitted subclasses is not altered unintentionally.
- That there are no `IncompatibleClassChangeError` or verifier/linkage errors after the update.

A test that intentionally violates `PermittedSubclasses` should run in a **separate test JVM** to avoid corrupting the main test pipeline. Do not treat a schema-change attempt rejected by the JVM as a shortcoming of the API; that is proper enforcement.

## 8. Two class loaders: same name does not mean same Class

To the JVM, the runtime identity of a class depends on **binary name and defining class loader**. Two loaders can use the same class bytes to define two classes named `tutorial.fixture.Twin`:

~~~text
binary name = tutorial.fixture.Twin
          |
          +-- IsolatedLoader("A") --> Class<?> A
          |
          +-- IsolatedLoader("B") --> Class<?> B

A.getName().equals(B.getName()) == true
A == B                            == false
A.getClassLoader() == B.getClassLoader() == false
~~~

This case is especially important for application servers, plugin systems, hot-reload containers, and multiple parallel class loader versions.

**A transformer should not cache solely by `className`** if transformation data depends on the loader/module. The minimum key should usually consider **class loader identity + internal name**; if module boundaries exist, also consider module and protection domain/policy when genuinely relevant.

### Why can't you cast an instance of A to type B?

The two classes have different runtime types, even though they share the same name and methods. An instance created by `Class<?> A` is not naturally an instance of `Class<?> B`. Casting across an incompatible boundary can cause `ClassCastException`/loader constraint errors. The demo suite does not cast them; instead, it invokes the public method via reflection on each respective `Class<?>`.

### Do not accidentally use parent-first for the fixture

If `tutorial.fixture.Twin` is also present on the application classpath, a parent-delegating `ClassLoader.loadClass(name)` may return the class defined by the parent, invalidating the test. The demo suite **does not put `fixture-bin` on the runtime `-cp`**; the two `IsolatedLoader` instances directly call `defineClass(...)` with bytes from the compiled fixture file. As a result, the two runtime definitions genuinely have different loaders.

### With ClassFileTransformer

At load time, the callback receives `className="tutorial/fixture/Twin"` for both definitions, but `loader` differs. On retransform, those exact existing `Class<?>` objects are passed so the JVM invokes capable transformers again (if capability/target modifiability allow).

A meaningful log must include the loader:

~~~text
fixtureCallback=load loader=isolated-A
fixtureCallback=load loader=isolated-B
fixtureCallback=retransform loader=isolated-A
fixtureCallback=retransform loader=isolated-B
~~~

There is no need to call `loader.loadClass("tutorial.fixture.Twin")` from the callback. During class definition, doing so can cause class-loading reentrancy; **the `className` and `classfileBuffer` parameters are sufficient** for filtering/transforming.

## 9. Multi-layer test strategy: metadata, behavior, callback, and isolation

A solid test suite should separate stages:

1. **Compile test:** generate bytecode with a pinned compiler/version.
2. **Class-file inspection:** use `javap -v -p` or a parsing library to inspect flags/attributes/descriptors.
3. **Reflection metadata:** check `isBridge`, `isSynthetic`, `isRecord`, `isSealed`, `isHidden`, and loaders.
4. **Behavior test:** invoke the generic bridge, lambda, record accessor, sealed subtype dispatch, and fixture instances.
5. **Agent callback test:** print/count callbacks of filtered targets, without logging the entire JVM.
6. **Retransform capability test:** check `isRetransformClassesSupported()`, manifest `Can-Retransform-Classes`, and `isModifiableClass`.
7. **Identity test:** two classes with the same binary name but different loaders are not conflated.
8. **Negative test:** do not attempt to modify unmodifiable array/primitive/hidden classes.
9. **Post-transform test:** re-run behavior/metadata checks after retransformation.
10. **Production patcher test:** if actually modifying bytes, verify probe count, stack frames, verifier, startup, and runtime on the target JDK.

Note the two levels of success:

- **"Observer transformer was invoked"**: the callback ran and returned `null`. This is what the demo directly proves.
- **"Bytecode transformation succeeded"**: a new byte array must be returned, accepted by the JVM, and pass behavior tests. Do not infer the second level from the first.

## 10. Complete JDK 17+ demo: one agent, six class types tested

The demo has three parts:

- **`EdgeCaseAgent` agent:** registers a capable `ClassFileTransformer` if the JVM supports it, logs the fixture's two separate loaders, and provides inspection/retransform APIs.
- **Application:** contains generic override, lambda, record, sealed hierarchy, and a driver checking reflection/behavior.
- **`Twin` fixture:** compiled separately, **not on the runtime classpath**, only defined from bytes by the two loaders.

The commands in the example are runnable under JDK 17+ on a JVM with Java Instrumentation. The results below are verified stdout on **JDK 24**, not speculative output. The case where a JVM does not support retransformation is explicitly reported by the agent as skipped rather than claiming success.

### 10.1. File layout

~~~text
special-types-agent-demo/
├── agent-src/
│   └── tutorial/agent/EdgeCaseAgent.java
├── app-src/
│   └── tutorial/app/
│       ├── Cases.java
│       └── Driver.java
├── fixture-src/
│   └── tutorial/fixture/Twin.java
└── agent.mf
~~~

After compiling, the output directories include:

~~~text
agent-bin/
app-bin/
fixture-bin/
dist/
└── edge-agent.jar
~~~

`Cases.java` contains several **package-private top-level declarations** (class/record/interface). This is valid in Java when they share the same package; not every declaration must reside in a file of the same name if it is not public.

### 10.2. File agent-src/tutorial/agent/EdgeCaseAgent.java

~~~java
package tutorial.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class EdgeCaseAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        inst.addTransformer(new Observer(), inst.isRetransformClassesSupported());
        System.out.println("agentReady=true");
    }

    public static boolean modifiable(Class<?> type) {
        return instrumentation.isModifiableClass(type);
    }

    public static boolean retransformSupported() {
        return instrumentation.isRetransformClassesSupported();
    }

    public static long countLoaded(String binaryName) {
        long count = 0;
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (type.getName().equals(binaryName)) count++;
        }
        return count;
    }

    public static void verifyRetransformation(Class<?>... types) throws Exception {
        if (!instrumentation.isRetransformClassesSupported()) {
            System.out.println("retransformSkipped=unsupported");
            return;
        }
        for (Class<?> type : types) {
            if (!instrumentation.isModifiableClass(type)) {
                System.out.println("retransformSkipped=unmodifiable:" + type.getName());
                return;
            }
        }
        instrumentation.retransformClasses(types);
        System.out.println("retransformCount=" + types.length);
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer) {
            if ("tutorial/fixture/Twin".equals(className)) {
                String loaderId = loader == null ? "bootstrap" : loader.toString();
                String phase = classBeingRedefined == null ? "load" : "retransform";
                System.out.println("fixtureCallback=" + phase + " loader=" + loaderId);
            }
            return null;
        }
    }
}
~~~

**Explanation:**

- `premain` receives `Instrumentation` provided by the JVM when running with `-javaagent`; application code does not create instrumentation itself.
- `addTransformer(new Observer(), inst.isRetransformClassesSupported())` registers as capable when the runtime has the capability, otherwise non-capable to observe load time.
- The observer filters only `tutorial/fixture/Twin` by internal name and logs loader/phase, **without calling the loader to load the target**.
- Because the test does not use `redefineClasses`, labeling `"retransform"` when `classBeingRedefined != null` is accurate **within the demo scenario**. In a general-purpose agent, a non-null parameter **also appears during redefine**, so do not rely on that condition alone to distinguish all events.
- `countLoaded(...)` counts classes present in **a snapshot** of `getAllLoadedClasses()`; results may vary in other environments.
- `isModifiableClass` and `isRetransformClassesSupported` are two independent conditions; `isModifiableClass==true` does not guarantee every bytecode patch is valid.
- `return null` means **no bytes are modified** in the observer. Calling retransform is still a real JVM operation that can affect other transformers if any exist.

### 10.3. File app-src/tutorial/app/Cases.java

~~~java
package tutorial.app;

import java.util.function.Supplier;
import java.util.Locale;

abstract class Base<T> {
    public abstract T convert(T input);
}

final class StringService extends Base<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

final class LambdaCase {
    public Supplier<String> supplier(String suffix) {
        return () -> "x-" + suffix;
    }
}

record Event(String label, int count) { }

sealed interface Shape permits Circle, Rectangle {
    String kind();
}

final class Circle implements Shape {
    @Override public String kind() { return "circle"; }
}

non-sealed class Rectangle implements Shape {
    @Override public String kind() { return "rectangle"; }
}
~~~

This single file can produce multiple `.class` files: `Base.class`, `StringService.class`, `LambdaCase.class`, `Event.class`, `Shape.class`, `Circle.class`, and `Rectangle.class`.

- `Base<T>` + `StringService` produces a bridge when `javac` handles erasure.
- `LambdaCase` has a lambda with captured parameter `suffix`.
- `Event` is a record with two components.
- `Shape` is a sealed interface; `Circle` is a final permitted subtype; `Rectangle` is a non-sealed permitted subtype.

This code only compiles on a JDK with the corresponding Java features (Java 17+ is a safe baseline for the entire demo). There are no third-party libraries.

### 10.4. File fixture-src/tutorial/fixture/Twin.java

~~~java
package tutorial.fixture;

public final class Twin {
    public Twin() {}

    public String value() {
        return "twin";
    }
}
~~~

The fixture will be compiled into `fixture-bin/tutorial/fixture/Twin.class`. **Do not add `fixture-bin` to `-cp` at runtime**. The driver reads the bytes and asks **two different IsolatedLoader instances** to define this exact class.

### 10.5. File app-src/tutorial/app/Driver.java

~~~java
package tutorial.app;

import tutorial.agent.EdgeCaseAgent;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public final class Driver {
    private static final String TWIN = "tutorial.fixture.Twin";

    private static final class IsolatedLoader extends ClassLoader {
        private final String id;

        IsolatedLoader(String id) {
            super(Driver.class.getClassLoader());
            this.id = id;
        }

        Class<?> defineTwin(byte[] bytes) {
            return defineClass(TWIN, bytes, 0, bytes.length);
        }

        @Override
        public String toString() {
            return "isolated-" + id;
        }
    }

    public static void main(String[] args) throws Exception {
        StringService service = new StringService();
        Method bridge = Arrays.stream(StringService.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("bridgeCount="
                + Arrays.stream(StringService.class.getDeclaredMethods())
                        .filter(Method::isBridge).count());
        System.out.println("bridgeIsSynthetic=" + bridge.isSynthetic());
        System.out.println("bridgeDispatch="
                + ((Base<String>) service).convert("hi"));

        LambdaCase lambdaCase = new LambdaCase();
        Supplier<String> supplier = lambdaCase.supplier("lambda");
        System.out.println("lambdaSyntheticMethods="
                + Arrays.stream(LambdaCase.class.getDeclaredMethods())
                        .filter(m -> m.isSynthetic()
                                && m.getName().startsWith("lambda$"))
                        .count());
        System.out.println("lambdaResult=" + supplier.get());
        System.out.println("lambdaProxyHidden="
                + supplier.getClass().isHidden());
        System.out.println("lambdaProxyModifiable="
                + EdgeCaseAgent.modifiable(supplier.getClass()));

        Event event = new Event("E", 4);
        System.out.println("recordIsRecord=" + Event.class.isRecord());
        System.out.println("recordComponents="
                + Event.class.getRecordComponents().length);
        System.out.println("recordValue="
                + event.label() + ":" + event.count());

        String permitted = Arrays.stream(Shape.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("shapeIsSealed=" + Shape.class.isSealed());
        System.out.println("permitted=" + permitted);
        System.out.println("shapeDispatch="
                + ((Shape) new Circle()).kind());

        byte[] bytes = Files.readAllBytes(
                Path.of("fixture-bin", "tutorial", "fixture", "Twin.class"));
        Class<?> first = new IsolatedLoader("A").defineTwin(bytes);
        Class<?> second = new IsolatedLoader("B").defineTwin(bytes);

        System.out.println("sameBinaryName="
                + first.getName().equals(second.getName()));
        System.out.println("sameClassObject=" + (first == second));
        System.out.println("sameLoader="
                + (first.getClassLoader() == second.getClassLoader()));

        Object a = first.getDeclaredConstructor().newInstance();
        Object b = second.getDeclaredConstructor().newInstance();
        System.out.println("fixtureValues="
                + first.getMethod("value").invoke(a) + ","
                + second.getMethod("value").invoke(b));
        System.out.println("loadedTwinCount=" + EdgeCaseAgent.countLoaded(TWIN));

        System.out.println("arrayModifiable="
                + EdgeCaseAgent.modifiable(int[].class));
        System.out.println("primitiveModifiable="
                + EdgeCaseAgent.modifiable(int.class));
        System.out.println("retransformSupported="
                + EdgeCaseAgent.retransformSupported());

        EdgeCaseAgent.verifyRetransformation(StringService.class,
                LambdaCase.class, Event.class, Shape.class, first, second);

        System.out.println("afterBridge="
                + ((Base<String>) service).convert("hi"));
        System.out.println("afterRecord="
                + event.label() + ":" + event.count());
    }
}
~~~

**Why is this loader test more reliable than comparing class names alone?**

- `IsolatedLoader.defineTwin(bytes)` calls the protected `ClassLoader.defineClass` through a loader subclass.
- The two loader objects have the same implementation but are **distinct instances**, with clear log names `isolated-A` and `isolated-B`.
- `first == second` checks **Class object identity**, which is more accurate than comparing `getName()`.
- Each class can create an instance and return `"twin"` via reflection; both classes share the same behavior while having distinct runtime identities.
- Because `fixture-bin` is not on the application classpath, the driver cannot accidentally use a parent-provided `Twin`.
- `countLoaded(TWIN)` confirms the JVM snapshot contains two definitions with the same binary name in the test environment.

Another design point: `EdgeCaseAgent.verifyRetransformation(...)` accepts the **actual `Class<?>` objects** of both definitions, rather than just the class name. This lets the JVM target both distinct classes accurately.

### 10.6. Agent manifest: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: tutorial.agent.EdgeCaseAgent
Can-Retransform-Classes: true
~~~

The manifest needs a **trailing blank line**. `Can-Retransform-Classes: true` lets the agent request the capability, though you must still check `isRetransformClassesSupported()` because the JVM may not support it.

Do not confuse `Can-Retransform-Classes` with `Can-Redefine-Classes`. The demo calls `retransformClasses(...)`, so the former capability is the right one. It does not use `redefineClasses(new ClassDefinition(...))`.

### 10.7. Compile and run

**Bash/Linux/macOS/Git Bash**, run from the `special-types-agent-demo/` directory:

~~~bash
mkdir -p agent-bin app-bin fixture-bin dist

javac --release 17 -d agent-bin \
  agent-src/tutorial/agent/EdgeCaseAgent.java

javac --release 17 -cp agent-bin -d app-bin \
  app-src/tutorial/app/Cases.java \
  app-src/tutorial/app/Driver.java

javac --release 17 -d fixture-bin \
  fixture-src/tutorial/fixture/Twin.java

jar --create --file dist/edge-agent.jar \
  --manifest agent.mf -C agent-bin .

java -javaagent:dist/edge-agent.jar \
  -cp app-bin tutorial.app.Driver
~~~

**Windows PowerShell**, the same commands written one per line:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin, fixture-bin, dist | Out-Null
javac --release 17 -d agent-bin agent-src/tutorial/agent/EdgeCaseAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/tutorial/app/Cases.java app-src/tutorial/app/Driver.java
javac --release 17 -d fixture-bin fixture-src/tutorial/fixture/Twin.java
jar --create --file dist/edge-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:dist/edge-agent.jar -cp app-bin tutorial.app.Driver
~~~

**Important note on runtime classpath:** `app-bin` is the application classpath; the agent is located by the JVM via `-javaagent`, while `fixture-bin` must exist on the **filesystem for the driver to read bytes**, and must **not** be added to `-cp`. When running from a different directory, adjust the relative path to `fixture-bin` in the program or the working directory.

`jar -C agent-bin .` packages all agent classes, including `EdgeCaseAgent$Observer.class`. If the nested class is missing, the agent can fail immediately in `premain` before the app starts.

### 10.8. Exact stdout verified on JDK 24

~~~text
agentReady=true
bridgeCount=1
bridgeIsSynthetic=true
bridgeDispatch=HI
lambdaSyntheticMethods=1
lambdaResult=x-lambda
lambdaProxyHidden=true
lambdaProxyModifiable=false
recordIsRecord=true
recordComponents=2
recordValue=E:4
shapeIsSealed=true
permitted=Circle,Rectangle
shapeDispatch=circle
fixtureCallback=load loader=isolated-A
fixtureCallback=load loader=isolated-B
sameBinaryName=true
sameClassObject=false
sameLoader=false
fixtureValues=twin,twin
loadedTwinCount=2
arrayModifiable=false
primitiveModifiable=false
retransformSupported=true
fixtureCallback=retransform loader=isolated-A
fixtureCallback=retransform loader=isolated-B
retransformCount=6
afterBridge=HI
afterRecord=E:4
~~~

**Group-by-group explanation:**

| Signal | Evidence |
| --- | --- |
| `bridgeCount=1`, `bridgeIsSynthetic=true` | In the `javac`-compiled class, there is one bridge that is also synthetic |
| `bridgeDispatch=HI` | Invocation through the generic base reference dispatches correctly |
| `lambdaSyntheticMethods=1` | Host `LambdaCase` has one synthetic lambda implementation method under this compiler |
| `lambdaResult=x-lambda` | The lambda retains the captured suffix and returns the right result |
| `lambdaProxyHidden=true` | The JDK 24 runtime creates a hidden lambda proxy for this case |
| `lambdaProxyModifiable=false` | This specific lambda proxy cannot be retransformed on the test JVM; the agent does not force modification |
| `recordIsRecord=true`, `recordComponents=2` | Reflection sees the record and two components |
| `recordValue=E:4` | Component accessors work |
| `shapeIsSealed=true`, `permitted=Circle,Rectangle` | Sealed metadata is present and accurate |
| `shapeDispatch=circle` | Interface dispatch through the sealed hierarchy works |
| Two `fixtureCallback=load` lines with A/B | The JVM receives two class definitions with the same name but different loaders |
| `sameBinaryName=true`, `sameClassObject=false`, `sameLoader=false` | Class identity must account for the loader; name cannot be used as the sole key |
| `loadedTwinCount=2` | The snapshot contains both created definitions |
| `arrayModifiable=false`, `primitiveModifiable=false` | The API specifies that array/primitive classes cannot be modified |
| `retransformSupported=true` | The test agent/JVM supports retransformation |
| Two `retransform` callbacks, `retransformCount=6` | Both fixture classes were retransformed along with the four sample classes |
| `afterBridge=HI`, `afterRecord=E:4` | Behaviors remain correct after observer-only retransformation |

**Interpretation warning:** `retransformCount=6` is the number of `Class<?>` objects passed to a successful retransform call, **not the number of methods with probes inserted**. The observer returns `null`, so no new bytecode is produced. The values `lambdaProxyHidden=true` and `lambdaProxyModifiable=false` are **observed results on this runtime**, not a promise for every JVM.

### 10.9. Checking class-file flags/attributes with javap

Run:

~~~bash
javap -p -v -classpath app-bin tutorial.app.StringService
javap -v -classpath app-bin tutorial.app.Event
javap -v -classpath app-bin tutorial.app.Shape
~~~

In the JDK 24 verification run, the relevant excerpts appear:

~~~text
StringService:
    flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC

Event:
    Record:

Shape:
    PermittedSubclasses:
~~~

These are **relevant excerpt lines**, not the full stdout of `javap -v`. For record/sealed, use the full `javap` output to cross-check field descriptors and the list of permitted subclasses. To inspect the lambda call site, try:

~~~bash
javap -p -c -v -classpath app-bin tutorial.app.LambdaCase
~~~

Look for `invokedynamic` and the associated `BootstrapMethods` entries. Do not assert that the host class file always contains the same `lambda$...` symbol across all compilers.

## 11. How to turn the demo into an assertion-based regression test?

The demo prints logs for readability. In real unit/integration tests, use assertions instead of manual stdout inspection.

Example assertion for bridge:

~~~java
long bridges = java.util.Arrays.stream(
        StringService.class.getDeclaredMethods())
        .filter(java.lang.reflect.Method::isBridge).count();

if (bridges != 1) throw new AssertionError("Bridge count changed");

StringService service = new StringService();
if (!"HI".equals(((Base<String>) service).convert("hi"))) {
    throw new AssertionError("Generic dispatch was changed");
}
~~~

This is a **snippet placed in the same `tutorial.app` package**, not a standalone program. With a pinned compiler in the pipeline, asserting the bridge count makes sense. With multi-compiler support, tests may need to evaluate flags/behavior flexibly across different compilers.

Assertion for record/sealed:

~~~java
if (!Event.class.isRecord()
        || Event.class.getRecordComponents().length != 2) {
    throw new AssertionError("Record metadata changed");
}

if (!Shape.class.isSealed()
        || Shape.class.getPermittedSubclasses().length != 2) {
    throw new AssertionError("Sealed metadata changed");
}
~~~

Assertion for loader identity:

~~~java
if (!first.getName().equals(second.getName())
        || first == second
        || first.getClassLoader() == second.getClassLoader()) {
    throw new AssertionError("Loader isolation was lost");
}
~~~

This snippet requires the two `Class<?> first, second` variables from the fixture loader as in the driver, and only checks what the test specifies. If a framework caches instrumentation results by `className` rather than by loader, add separate metrics or markers to assert that **both definitions produce independent results**, rather than only asserting that two callbacks appeared.

### Event tests need two separate outputs

In an agent that actually modifies bytecode, record both:

~~~text
Transform decision:
  class internal name, loader identity, method name + descriptor,
  flags (bridge/synthetic), include/skip reason

Execution outcome:
  callback count, bytes returned? null/non-null,
  retransform call succeeded?, behavior assertions passed?
~~~

**Do not log "PATCHED" merely because `ClassFileTransformer.transform` was called.** With `return null`, the exact meaning is "observer received callback; no bytes modified at that step."

## 12. Negative matrix and JVM boundaries

For an isolated test environment, confirm that the following operations **are not performed unconditionally**:

| Case | Condition/risk | Expected test result |
| --- | --- | --- |
| `int.class` | Primitive class is unmodifiable | `isModifiableClass==false`, do not call retransform |
| `int[].class` | Array class is unmodifiable | `isModifiableClass==false`, do not call retransform |
| Lambda proxy is hidden/unmodifiable | May not be retransformable | Report skip per API, do not throw errors into production |
| Record with modified component fields | Schema change may be rejected by JVM | Test failure separately, do not attempt to alter live class |
| Sealed type with different permitted list | Structural metadata/hierarchy change is not portable | Do not arbitrarily alter during retransform |
| Bridge with changed descriptor | Breaks erased dispatch/overriding | Verify descriptor + typed/generic calls |
| Synthetic lambda body skipped | Loses measurement while business code still runs | Include/skip policy is tested |
| Two loaders with same class name | Name-keyed cache overwrites metadata | Class/loader identity is kept separate |
| Fixture accidentally on app classpath | Parent loader may define it first | Run with classpath containing only `app-bin` |
| Transformer throws exception | JVM may still run subsequent transformers | Do not treat exception as an atomic "abort pipeline" |

A negative test that intentionally returns malformed class bytes, alters field schema, or modifies `PermittedSubclasses` should run in a **separate JVM process** with timeout and exit-code checks. It can cause class loading failures or break agent startup; do not mix these destructive scenarios into the same JVM running the happy-path suite.

### Exceptions to distinguish

- `UnsupportedOperationException`: capability or class change is not supported.
- `UnmodifiableClassException`: JVM considers the target unmodifiable.
- `ClassFormatError`: output is not a valid class file.
- `VerifyError`: bytecode violates verifier rules.
- `LinkageError` or `ClassCircularityError`: linkage or class/hierarchy definition issue.
- `ClassCastException`: attempting to use an instance defined by one loader as an incompatible type from another loader.
- `BootstrapMethodError`: `invokedynamic`/lambda bootstrap linkage failure when a call site is patched improperly.

A failure does not necessarily have a single cause; retain class name, loader identity, JVM version, transform stage, exception chain, bytes hash, and reproduction command.

## 13. A testable instrumentation policy

For a production agent, do not select methods with scattered conditions without recording reasons. Example policy:

~~~text
If class is array/primitive/hidden-unmodifiable:
    SKIP_UNMODIFIABLE

If class is not in allowlist or loader is not permitted:
    SKIP_SCOPE_OR_LOADER

If method.isBridge():
    SKIP_BRIDGE_BY_POLICY   (when measuring logical business calls)

If method.isSynthetic() and not bridge:
    INCLUDE_LAMBDA_BODY / SKIP_SYNTHETIC_BY_POLICY
    (depends on measurement goal, no blanket skip)

If class.isRecord():
    instrument only valid method bodies; preserve Record metadata

If class.isSealed():
    preserve PermittedSubclasses/hierarchy

If transforming:
    do not mutate input classfileBuffer in place;
    return new byte[]; verify post-transform behavior
~~~

This is **policy pseudocode**, not Java statements. Key testing point: **the same class/method under the same policy must produce a reproducible decision**, and every skip reason should be categorized by policy or JVM limitation.

A diagnostic record should include:

- Internal class name (e.g., `tutorial/fixture/Twin`).
- Loader identity or agent-assigned stable ID (not just `ClassLoader.toString()`).
- Module and protection domain when needed.
- Method name, descriptor, access flags.
- Phase load/redefine/retransform (must be determined from orchestration state, not only `classBeingRedefined != null`).
- Decision (include/skip), reason code.
- Callback outcome (null/new bytes/exception).
- Verifier/apply result and corresponding behavior test.

**Do not hold strong references to class loaders indefinitely** just for auditing. Using a map keyed by `ClassLoader`/`Class<?>` in a long-lived agent can prevent class unloading in plugin containers; use weak references or an appropriate cleanup/bounded cache strategy.

## 14. Advanced notes when using ASM or Byte Buddy

With ASM, a `MethodVisitor` receives access flags to distinguish `ACC_BRIDGE` and `ACC_SYNTHETIC`. With Byte Buddy, matchers can select bridge/synthetic based on the goal. Both need testing against **real bytecode** from the expected compiler, not reflection alone.

An illustrative ASM filter snippet:

~~~java
boolean bridge = (access & org.objectweb.asm.Opcodes.ACC_BRIDGE) != 0;
boolean synthetic = (access & org.objectweb.asm.Opcodes.ACC_SYNTHETIC) != 0;

if (bridge) {
    // Policy: skip bridge when counting logical method execution.
}
~~~

This is a **snippet requiring the ASM dependency**, not part of the JDK-only runnable demo. If instrumenting a lambda host synthetic body, identify it by descriptor and bytecode semantics; do not rely solely on matching `name.startsWith("lambda$")` in production where multiple compilers may exist.

### Stack maps, frames, and invokedynamic

Especially when inserting probes into bridge or lambda methods:

1. Preserve the operand stack and local variable layout.
2. When needed, recompute `StackMapTable`/`maxStack`/`maxLocals` using an appropriate tool.
3. Do not break the bridge target invocation or required cast.
4. Do not modify the `invokedynamic` descriptor/`BootstrapMethods` without checking linkage.
5. Preserve record/sealed structural attributes.
6. Do not arbitrarily add fields/methods when retransforming loaded classes.
7. Verify return values, thrown exception identity, and no double probes.
8. Test both load-time instrumentation and retransform-time on the target JDK.

For example, an "all methods" matcher might instrument generated accessors, bridges, lambda bodies, constructors, and `ObjectMethods`-related methods of a record. Depending on the use case, **some of these must be excluded**, while others **must be kept**. There is no universal rule that "synthetic is noise."

## 15. Common mistakes when writing tests

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using one plain class to conclude the agent works well | Misses bridge, lambda, record, sealed metadata | Have dedicated class fixtures |
| Skipping all synthetic methods | Loses lambda body instrumentation | Separate bridge from synthetic non-bridge |
| Unconditionally instrumenting both bridge and implementation | Counter double-counts on erased dispatch | Define logical-method policy and test counts |
| Assuming every lambda proxy is a normal class | Attempts to retransform hidden/unmodifiable class | `isHidden`/`isModifiableClass` and skip reason |
| Testing a fixed `lambda$...` name across all compilers | Brittle tests when changing `javac`/compiler | Assert behavior/metadata or pin the toolchain |
| Checking only `Class.getName()` | Conflates two classes from different loaders | Compare `Class<?>` and defining loader |
| Putting the fixture JAR on the runtime classpath | Parent may define fixture, breaking multi-loader test | Use separate bytes outside the classpath |
| Reading class files from disk instead of `classfileBuffer` in transformer | May miss prior transforms or dynamic generation | Parse the exact bytes provided by the JVM |
| Adding fields to a loaded record | Schema change is rejected | Patch bodies within JVM limits |
| Modifying permitted hierarchy after loading | Linkage/unsupported changes | Preserve `PermittedSubclasses` metadata |
| Treating a logged callback as patched bytes | False positive | Distinguish observer/null from replacement `byte[]` |
| Using `classBeingRedefined!=null` to strictly distinguish retransform/redefine | Mislabels phase | Track caller/operation context if needed |
| Not checking `isRetransformClassesSupported` | Runtime capability error | Correct manifest + API check |
| Forgetting to check `isModifiableClass` | Attempts to modify disallowed class | Explicit skip |
| Treating `LongAdder.sum` as unique loaded-class count | Callback count differs from class identity | Define metrics accurately |
| Missing Java 17 target in CI | Record/sealed class bytes may differ | Pin `--release 17`, runtime matrix |
| Not testing multi-loader plugins | Wrongly instruments same-named types | Configure loader-aware policy |
| Not testing after retransformation | Behavior/metadata regressions | Pre/post tests and verifier |

## 16. CI integration checklist

- [ ] Compile fixtures with the **exact compiler/target release** production needs to support.
- [ ] Run `javap -v -p` or bytecode inspection to confirm critical flags and attributes.
- [ ] Test bridge methods on both erased and typed call paths.
- [ ] Test synthetic lambda implementation methods according to the compiler in use.
- [ ] Do not rely on hidden lambda proxies always being modifiable.
- [ ] Test record components, accessors, and `equals`/`hashCode`/`toString` if instrumented.
- [ ] Test sealed permitted subclasses and interface dispatch.
- [ ] Create two independent class loaders defining the same binary name.
- [ ] Verify callbacks and cache keys distinguish loader identity.
- [ ] Do not use a class loader to reload the very class currently being transformed.
- [ ] Check capability and modifiability before retransformation.
- [ ] Do not attempt to retransform array/primitive/unmodifiable hidden classes.
- [ ] Test behavior both before and after retransform/patch.
- [ ] Run negative tests in a separate JVM if malformed class bytes or schema changes are involved.
- [ ] Observe error types, exit codes, timeouts, and class-loading latency.
- [ ] Do not let agent logging/loader references hang the program or leak memory.
- [ ] Distinguish **callback observed**, **bytecode patched**, and **behavior verified** in reports.

## 17. Self-check exercises

**Question 1.** `StringService.convert(String)` overrides `Base<T>.convert(T)`. Why can the class file contain an extra `convert(Object)`, and which flags help identify it?

**Question 2.** If an agent inserts a counter at the entry of both the bridge and the implementation `convert`, how many times can a single call through `Base<String>` increment the counter? Is this a concurrency bug?

**Question 3.** Does `Method.isSynthetic()==true` imply `Method.isBridge()==true`?

**Question 4.** Is a lambda body method named `lambda$supplier$0` guaranteed by the Java standard to appear with that exact name across all compilers?

**Question 5.** The JDK 24 test reports `lambdaProxyHidden=true` and `lambdaProxyModifiable=false`. Can you force `retransformClasses(lambdaProxy.getClass())` on all JVMs?

**Question 6.** Can a record be identified solely by the class being `final`? Which APIs should be used?

**Question 7.** A transformer retransforms `Event` but alters `Record` components or adds a new field. What can happen?

**Question 8.** `Shape.class.isSealed()==true`; `getPermittedSubclasses()` returns two subclasses. Can the permitted list be changed arbitrarily during retransformation?

**Question 9.** Two `Class<?>` objects have the same `getName()` but different `getClassLoader()`. Are they one class or two classes?

**Question 10.** If the `Twin.class` fixture is placed on the application classpath and code calls parent-first `loadClass`, what can cause the "two loaders" test to become invalid?

**Question 11.** An agent calls `Instrumentation.retransformClasses(...)` on six classes, the callback returns `null`, and then prints `retransformCount=6`. Can we conclude that the six classes received new code?

**Question 12.** Does `classBeingRedefined != null` in the callback definitively prove it is a retransform rather than a redefine?

**Question 13.** Why should both `bridgeDispatch=HI` and `afterBridge=HI` be measured in a retransform test?

**Question 14.** The goal is "count each logical business call exactly once." If a bridge method forwards to the implementation, which policy should be chosen?

**Question 15.** Why can a classloader-aware cache cause a memory leak, and how can it be mitigated?

**Question 16.** When `getAllLoadedClasses()` contains a hidden class, does that mean it is modifiable for retransformation?

### Answers

1. Due to **type erasure** and polymorphic overriding; the bridge typically has `ACC_BRIDGE`, often accompanied by `ACC_SYNTHETIC`.
2. Possibly **2 times**: the bridge and the implementation. Not a concurrency bug, but a measurement-point selection bug.
3. **No**. A bridge is usually synthetic, but a synthetic method can also be a lambda implementation or another compiler-generated helper.
4. **No**. The name and implementation strategy are compiler details; inspect the specific compiler.
5. **No**. You must query `isModifiableClass` and capabilities on the actual runtime; a hidden lambda proxy may not be modifiable.
6. **No**. Use `Class.isRecord()` and `getRecordComponents()`, cross-checking the `Record` attribute.
7. The JVM may reject it due to invalid class schema/metadata; preserve allowed structure and patch only valid bodies.
8. **No**. A sealed hierarchy has `PermittedSubclasses` and JVMTI restrictions; do not treat retransformation as a way to arbitrarily alter hierarchies.
9. **Two runtime classes**, because their defining class loader identities differ.
10. The parent may provide the same class instead of two independent definitions. Avoid putting `fixture-bin` on `-cp` and use `defineClass` intentionally.
11. **No**. A callback returning `null` is observer-only; a successful retransform does not mean probes were inserted.
12. **No**. Both redefine and retransform can pass a non-null class object.
13. To ensure generic dispatch works **before and after** the operation, catching regressions caused by bytecode updates.
14. You can **skip the bridge and instrument the implementation**, or deduplicate logical invocations by design; test both erased dispatch and typed calls.
15. Strong references to `Class<?>`/`ClassLoader` can prevent unloading; use lifecycle/bounded caches or weak keys/references where appropriate.
16. **No**. `getAllLoadedClasses` is discovery; modifiability is a separate API and depends on the class type and JVM.

## 18. Conclusion

**Bridge, synthetic, lambda, record, sealed, and multiple class loaders** are not rare edge cases: they appear in modern Java applications and systems using generics, functional APIs, immutable data models, sealed hierarchies, and plugin loading. A reliable agent must know **which structures are compiler/JVM-generated, what class modification limits apply, and what defines a target's runtime identity**.

A test suite should combine **reflection + javap + observer Java agent + retransform capability/modifiability + behavior assertions**. When moving to a real bytecode patcher, add verifier checks, probe-count tests to avoid double instrumentation, and run a matrix across real compilers/JVMs. **Do not infer that bytes were modified just because a transformer callback ran; do not infer that two classes with the same name are the same class; do not infer that every synthetic/hidden class can be instrumented the same way.**

## 19. Official technical references

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks on load/redefine/retransform, role of `className`/`loader`/`classfileBuffer`, `return null`, and bytecode chaining.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses`.
- [Java SE 21 — Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `isBridge()` and `isSynthetic()`.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isRecord()`, `getRecordComponents()`, `isSealed()`, `getPermittedSubclasses()`, `isHidden()`, and class loader identity.
- [Java SE 21 — RecordComponent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html): record component metadata.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, defining class loader, and runtime class identity.
- [Java Language Specification 21 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): structure/semantics of records.
- [Java Language Specification 21 — §8.1.1.2 Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): permitted subtypes and sealed hierarchy.
- [JVM Specification 21 — §4 The class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): `ACC_BRIDGE`, `ACC_SYNTHETIC`, `Record`, and `PermittedSubclasses` attributes.
- [JVM Tool Interface — RedefineClasses/RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): limits on class schema changes, identity, active frames, and class-file transform.
