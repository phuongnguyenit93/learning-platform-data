# Compiling Java Rules from Memory and Integrating Through the Same Contract

A business application may have two sources of rules: **pre-packaged rules** in host or plugin code and **rules created or edited while the system is running**. If each source uses a different invocation style, the host has to maintain two execution paths, two result formats, and two test mechanisms. A better design is to define **one stable Java contract**, compile dynamic rules into classes implementing that contract, and then place both built-in and dynamic rules into the same registry.

Java 17 provides the **javax.tools.JavaCompiler** API (JSR 199) to compile source code represented by JavaFileObject. By combining **SimpleJavaFileObject**, **ForwardingJavaFileManager**, and a **custom ClassLoader**, we can feed source code from a String into the compiler, capture `.class` bytecode as `byte[]` without saving dynamic sources or classes to files, and load implementations via the shared interface.

This exercise walks from the Rule contract → in-memory source → in-memory bytecode → class loader → Rule instance → unified evaluation pipeline. The final sections cover error handling, security boundaries, resource limits, versioning, and what it takes to turn this prototype into a production-ready system.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Define a clear **Rule SPI/contract** independent of where implementations originate.
2. Create a JavaFileObject for String-based source and pass it to **JavaCompiler.getTask(...)**.
3. Capture **all class outputs** via JavaFileManager and store them in `Map<String, byte[]>`.
4. Use a child loader to load bytecode while **delegating the Rule interface and Request DTO to the host's loader**.
5. Verify that a newly compiled class implements Rule properly and instantiate it via a public constructor.
6. Place dynamically compiled rules into the same list/registry alongside pre-compiled Java rules.
7. Distinguish **compile failure**, **class loading/linkage failure**, **instantiation failure**, and **business execution failure**.
8. Understand why **the ability to dynamically compile Java does not mean it is safe to run untrusted code**.

Both host and sample plugin code use **Java 17+**, requiring no Maven/Gradle or external libraries. The experiment runs on the **classpath** without module-info.java; migrating to JPMS requires additionally considering module graphs and readability.

## 2. Overall Architecture

~~~text
                     SHARED CONTRACT (API)
                 demo.api.Rule + demo.api.Request
                              |
                    +---------+---------+
                    |                   |
              Built-in rule       Java source from String
              SmallAmountRule               |
                    |                       v
                    |              SimpleJavaFileObject
                    |                       |
                    |                       v
                    |             javax.tools.JavaCompiler
                    |                       |
                    |                       v
                    |           MemoryJavaFileManager
                    |                       |
                    |               Map<String,byte[]>
                    |                       |
                    |                       v
                    |            MemoryClassLoader
                    |             (parent = API loader)
                    |                       |
                    |                       v
                    |             demo.dynamic.TravelRule
                    |                 implements Rule
                    |                       |
                    +-----------+-----------+
                                |
                                v
                         List<Rule> registry
                                |
                                v
                          Request input
                                |
                                v
                       rule.matches(request)
                                |
                                v
                         boolean decision
~~~

Notably, **two different implementations enter the exact same List<Rule>**. The decision logic calling `rule.matches(request)` knows only the Rule interface. It never has to ask "did this rule come from a .class file, a JAR, or a runtime-compiled String?" and never runs a separate eval channel.

JavaCompiler only produces bytecode. It **does not automatically execute** classes, register classes with ServiceLoader, or manage plugin lifecycles. Loading, contract verification, instantiation, registration, and invocation are all controlled by the host.

## 3. Designing the Contract Before Writing the Compiler

The experimental contract consists of two stable types:

- **Request**: an immutable record carrying the minimal data each rule may observe: category and amount.
- **Rule**: an interface with id() for management and matches(Request) returning a boolean decision.

~~~java
package demo.api;

public interface Rule {
    String id();
    boolean matches(Request request);
}
~~~

~~~java
package demo.api;

public record Request(String category, int amount) {}
~~~

These two snippets belong in Rule.java and Request.java respectively; do not place two public top-level types in the same file. In a real system, Request is usually a richer DTO with validation/nullability, allowed enum/domain values, and schema versioning.

**Why must we keep exactly one copy of the API?** In the JVM, class identity depends not only on package + class name, but also on the **defining ClassLoader**. Two copies of demo.api.Rule defined by two different loaders **are not the same type**, even if their bytecode and names match. When that happens, `Rule.class.isAssignableFrom(generatedClass)` or casting to Rule can fail.

The rule here is: **the host creates and owns Rule/Request; the dynamic rule's class loader uses the host loader as its parent; never compile another copy of Rule.java inside the dynamic task**.

A solid contract also specifies whether `matches(...)` may have side effects, which exceptions may be thrown, maximum execution time, thread-safety, Rule instance lifecycle, and how multiple rules are combined. The demo uses boolean for deterministic output; production systems may use `Decision(status, reason, evidence)` while keeping that DTO in the shared API.

## 4. Hands-On Project Structure

From the **rule-lab/** directory:

~~~text
rule-lab/
├── src/
│   ├── api/demo/api/
│   │   ├── Rule.java
│   │   └── Request.java
│   ├── builtin/demo/builtin/
│   │   └── SmallAmountRule.java
│   └── host/demo/host/
│       └── DynamicRulesDemo.java
└── build/
    └── classes/                  (generated during build)
~~~

No .java file is needed for the dynamic rule: its source is a **Java text block** inside the host. After running, no .class file for demo.dynamic.TravelRule appears in build/classes: it stays in memory.

### 4.1. Shared API: Rule.java

Create **src/api/demo/api/Rule.java**:

~~~java
package demo.api;

public interface Rule {
    String id();
    boolean matches(Request request);
}
~~~

### 4.2. Shared DTO: Request.java

Create **src/api/demo/api/Request.java**:

~~~java
package demo.api;

public record Request(String category, int amount) {}
~~~

Records have been available since Java 16. In this exercise, amount is an integer in conventional lab units; financial products should use explicit currency units and appropriate types (such as BigDecimal or minor units).

### 4.3. Built-in rule: SmallAmountRule.java

Create **src/builtin/demo/builtin/SmallAmountRule.java**:

~~~java
package demo.builtin;

import demo.api.Request;
import demo.api.Rule;

public final class SmallAmountRule implements Rule {
    @Override
    public String id() {
        return "small-amount";
    }

    @Override
    public boolean matches(Request request) {
        return request.amount() <= 100;
    }
}
~~~

This is a regular Java implementation compiled by javac before the host runs. It knows nothing about the JavaCompiler API and needs no custom ClassLoader.

### 4.4. Host compiling and loading rules in memory

Create **src/host/demo/host/DynamicRulesDemo.java**:

~~~java
package demo.host;

import demo.api.Request;
import demo.api.Rule;
import demo.builtin.SmallAmountRule;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DynamicRulesDemo {
    // 1. JavaFileObject holding source inside a String.
    private static final class SourceText extends SimpleJavaFileObject {
        private final String source;

        SourceText(String binaryName, String source) {
            super(URI.create("string:///"
                    + binaryName.replace('.', '/')
                    + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // 2. JavaFileObject receiving .class bytes via OutputStream.
    private static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream data = new ByteArrayOutputStream();

        ClassBytes(String binaryName) {
            super(URI.create("mem:///classes/"
                    + binaryName.replace('.', '/')
                    + JavaFileObject.Kind.CLASS.extension),
                    JavaFileObject.Kind.CLASS);
        }

        @Override
        public OutputStream openOutputStream() {
            return data;
        }

        byte[] bytes() {
            return data.toByteArray();
        }
    }

    // 3. Redirect all class outputs to a Map instead of disk.
    private static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> compiled = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String binaryName,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (kind != JavaFileObject.Kind.CLASS) {
                throw new IOException("Only CLASS output is supported");
            }
            ClassBytes output = new ClassBytes(binaryName);
            compiled.put(binaryName, output);
            return output;
        }

        Map<String, byte[]> bytecodes() {
            Map<String, byte[]> result = new HashMap<>();
            for (var entry : compiled.entrySet()) {
                result.put(entry.getKey(), entry.getValue().bytes());
            }
            return Map.copyOf(result);
        }
    }

    // 4. Load dynamic classes; Rule/Request remain defined by the parent loader.
    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> bytecodes;

        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> bytecodes) {
            super(parent);
            this.bytecodes = bytecodes;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] bytes = bytecodes.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    // Keep loader alongside instance to manage dynamic rule lifecycle.
    private record LoadedRule(Rule rule, ClassLoader loader) {}

    private static LoadedRule compileAndCreate(
            String binaryName, String source) throws Exception {

        if (source.length() > 10_000) {
            throw new IllegalArgumentException("Source exceeds lab limit");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with JDK 17+, not a runtime without javac");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiledBytes;

        // Standard manager is used to READ the host classpath.
        // Our wrapper redirects WRITING class outputs into memory.
        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            MemoryFileManager memory = new MemoryFileManager(standard);

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-classpath", System.getProperty("java.class.path"));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    memory,
                    diagnostics,
                    options,
                    null,
                    List.of(new SourceText(binaryName, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            if (!success) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println("compile-error line="
                            + d.getLineNumber() + " "
                            + d.getMessage(Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }
            compiledBytes = memory.bytecodes();
        }

        MemoryClassLoader loader = new MemoryClassLoader(
                Rule.class.getClassLoader(), compiledBytes);

        Class<?> raw = Class.forName(binaryName, true, loader);
        Class<? extends Rule> implementation = raw.asSubclass(Rule.class);
        Rule rule = implementation.getDeclaredConstructor().newInstance();
        return new LoadedRule(rule, loader);
    }

    public static void main(String[] args) throws Exception {
        String binaryName = "demo.dynamic.TravelRule";

        // 5. This is the ENTIRE source of the dynamic implementation.
        // There is no TravelRule.java file on disk.
        String javaSource = """
                package demo.dynamic;

                import demo.api.Request;
                import demo.api.Rule;

                public final class TravelRule implements Rule {
                    public TravelRule() {}

                    @Override
                    public String id() {
                        return "travel-high";
                    }

                    @Override
                    public boolean matches(Request request) {
                        return "travel".equals(request.category())
                                && request.amount() >= 500;
                    }
                }
                """;

        LoadedRule dynamic = compileAndCreate(binaryName, javaSource);
        Rule builtin = new SmallAmountRule();

        // 6. Both are invoked through the SAME Rule interface.
        List<Rule> registry = List.of(builtin, dynamic.rule());

        System.out.println("contract="
                + Rule.class.isInstance(dynamic.rule()));
        System.out.println("separate-implementation-loader="
                + (dynamic.loader() != Rule.class.getClassLoader()));

        for (Request request : List.of(
                new Request("travel", 800),
                new Request("office", 60))) {

            System.out.println("request="
                    + request.category() + "/" + request.amount());
            for (Rule rule : registry) {
                System.out.println("  " + rule.id()
                        + "=" + rule.matches(request));
            }
        }
    }
}
~~~

**Reviewing each component's role:**

- SourceText is a JavaFileObject with Kind.SOURCE. getCharContent returns the String already in RAM. A URI like `string:///...` is merely a logical file name for the compiler; it does not mean a file is created on disk.
- ClassBytes receives bytecode via ByteArrayOutputStream. The compiler can emit **multiple** `.class` files from one source (nested classes, anonymous classes, etc.), so the file manager stores a Map keyed by **binaryName**, not a single `byte[]`.
- MemoryFileManager wraps StandardJavaFileManager: standard still reads classes/modules from the compile environment; `.class` output via getJavaFileForOutput is redirected to memory. In the demo, annotation processors are disabled via `-proc:none`.
- MemoryClassLoader uses default parent delegation. It looks up dynamic classes in the bytecode map when the parent does not find them. The chosen parent is **Rule.class.getClassLoader()**, ensuring demo.api.Rule and demo.api.Request share the same identity as the host.
- `Class.forName(binaryName, true, loader)` not only loads the class but also **initializes the class** if needed; a rule's static initializer may have side effects. The demo only runs **trusted** code, not arbitrary Java submitted by strangers.
- `asSubclass(Rule.class)` verifies that the dynamic class actually implements the shared contract. This is not a loose type conversion by class name.
- `getDeclaredConstructor().newInstance()` requires an accessible no-arg constructor under standard access rules; the demo source declares a public constructor.
- LoadedRule holds both the instance and its loader so the host can manage lifecycle. There is no universal `ClassLoader.close()` that guarantees immediate class unloading; finish in-flight work and drop references when replacing rule versions.
- `List<Rule> registry` makes no distinction between built-in and dynamic rules; both are invoked via `matches(Request)`.

**Pattern boundaries:** This is a classpath model with in-memory dynamic source and bytecode. The standard manager still reads the host classpath from compiled classes/JARs on disk. It does not mean "all javac activity avoids the filesystem", and the code above does not yet implement sandboxing, total output quotas, caching, or hard CPU limits.

## 5. Compiling and Running the Exercise

From **rule-lab/**, run with JDK 17+ in bash:

~~~bash
mkdir -p build/classes

javac --release 17 -encoding UTF-8 -d build/classes \
  src/api/demo/api/Rule.java \
  src/api/demo/api/Request.java \
  src/builtin/demo/builtin/SmallAmountRule.java \
  src/host/demo/host/DynamicRulesDemo.java

java -cp build/classes demo.host.DynamicRulesDemo
~~~

**Exact expected stdout** when a JDK compiler is available and the code is unmodified:

~~~text
contract=true
separate-implementation-loader=true
request=travel/800
  small-amount=false
  travel-high=true
request=office/60
  small-amount=true
  travel-high=false
~~~

Analysis:

- `contract=true` proves the dynamic object is an instance of **Rule.class held by the host**.
- `separate-implementation-loader=true` confirms the implementation class is defined by a different loader while the shared interface remains common.
- For travel/800, SmallAmountRule returns false while runtime-compiled TravelRule returns true.
- For office/60, SmallAmountRule returns true while TravelRule returns false.
- No branch in the for loop needs to know whether a provider came from the compiler or a pre-built class. This is **one unified contract** in practice.

**On Windows:** when a classpath has multiple entries, the separator is `;` instead of `:`. In the demo there is only one entry (`build/classes`), so the java command works identically. `mkdir -p` and backslash line continuations are bash syntax; use Git Bash/WSL or translate to the corresponding PowerShell commands.

**Environment requirement:** `ToolProvider.getSystemJavaCompiler()` requires the runtime to include the JDK compiler module (`jdk.compiler`). A stripped-down runtime image without a compiler may return null. A standard JDK 17+ used to build and run the example normally includes this API.

## 6. Why Compilation Success Alone Is Not Enough to Publish to the Registry

There are four distinct boundaries:

| Boundary | What is known | What can still go wrong |
| --- | --- | --- |
| CompilationTask.call() returns true | Source is valid under current compiler options and dependencies | Loading the class later may encounter linkage/init errors |
| MemoryFileManager holds byte[] | Bytecode has been emitted into memory | Class name/type, output count, and execution permissions are not yet verified |
| Class.forName(...) succeeds | JVM defined/initialized the target class | Constructor may fail; methods may cause side effects |
| asSubclass + newInstance succeed | A type-valid Rule instance exists | matches(...) may still throw RuntimeException, run slowly, or have logic bugs |

A real host should perform **pre-publish validation**: class name allowlist, interface type, constructor, unique rule ID, version/API hash, sanity tests, input/output constraints, dependency load checks, resource limits, and logging policy.

When any step fails, do not insert faulty bytecode or instances into the live registry serving traffic. Build the complete candidate in a staging area, validate it, and then **swap the registry snapshot** using proper synchronization. If validation fails, keep the active version running.

**An important nuance:** a compilation task can succeed on source that lacks a properly named Rule implementation and still emit bytecode. `Class.forName(binaryName, ...)` or `asSubclass(...)` catches the mismatch afterward. Compilation is a necessary condition, not the completion criterion for a plugin.

## 7. Errors That Must Be Classified Separately

### 7.1. Compilation error

For example, change the dynamic source from:

~~~java
request.amount() >= 500
~~~

to:

~~~java
request.unknownAmount() >= 500
~~~

This is a **replacement snippet inside the source text block**, not a standalone program. The compiler will not find `unknownAmount()` on demo.api.Request. `CompilationTask.call()` returns false; DiagnosticCollector provides `Diagnostic.Kind.ERROR` with line/column/message and source reference.

The demo host prints diagnostics to stderr and throws `IllegalStateException("Compilation failed")`. It does not attempt to load classes from the Map after compilation fails. Exact javac diagnostic wording can vary across JDK builds; the lab **does not prescribe fixed stdout** for this failure case.

Another variant is changing `public final class TravelRule` to `WrongRule` while still passing `binaryName="demo.dynamic.TravelRule"`. The compiler may report a mismatch between the public class name and URI, or if the source is valid under another name, the class lookup step will fail. For diagnostics, log the **requested binaryName**, logical source name, and list of output classes; never work around this by letting ClassLoader load whatever first class it finds.

### 7.2. Class identity or loader error

If the dynamic source includes its own copy of demo.api.Rule while the host expects the pre-built `Rule.class`, the JVM can hit class identity conflicts. With the demo's parent-first loader, the API comes from the parent, yet you should still avoid placing binary names belonging to host API packages into the Map and relying on accidental delegation order.

Diagnosis:

~~~java
// Illustrative integration snippet: variable dynamic and type Rule already exist.
Class<?> type = dynamic.rule().getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(Rule.class.getClassLoader());
System.out.println(Rule.class.isAssignableFrom(type));
~~~

In the demo, className is demo.dynamic.TravelRule, its class loader differs from the host API loader, yet `isAssignableFrom` returns true. If false, inspect **which two loaders defined the SPI**, the module graph, dependency versions, and the implementation's package. Sharing the same class name does not guarantee type compatibility.

### 7.3. Initialization error

A class may implement Rule yet lack a public no-arg constructor, its constructor may throw IllegalStateException, or its static initializer may corrupt state. For instance, if the dynamic source declares only a single-parameter constructor, reflection via `getDeclaredConstructor()` throws NoSuchMethodException.

`Class.forName(binaryName, true, loader)` can also throw `ExceptionInInitializerError` if the static initializer fails. Constructor invocation can throw `InvocationTargetException` (whose cause is the actual exception thrown by the constructor). Distinguish these from `CompilationTask.call()` returning false.

**Do not catch Throwable and report every failure as "compilation failed".** Linkage errors (`NoClassDefFoundError`, `VerifyError`, `IncompatibleClassChangeError`, etc.) or runtime initialization errors must record the exact stage; upon serious JVM errors, follow a fail-closed policy instead of continuing arbitrarily.

### 7.4. Error while executing a rule

Even after a Rule instance is created, `matches(request)` can still throw RuntimeException, spawn threads, or block on I/O if implementations are allowed to call those APIs. A real host must bound each rule's impact, define whether fallback applies, and report **RULE_EXECUTION_ERROR** separately from **COMPILE_ERROR**.

Integration snippet example:

~~~java
// Illustrative code: rule and request are already resolved.
try {
    boolean matched = rule.matches(request);
    // Feed matched into the Decision/registry pipeline.
} catch (RuntimeException ex) {
    // Log rule ID/version and cause; choose fail-closed or degraded mode.
}
~~~

Never silently return false on every error. `false` means "the rule ran and did not match"; a failure means "the outcome could not be determined". Conflating these two states can cause the system to make dangerous decisions.

## 8. Integrating into a Shared Registry and ServiceLoader

In the lab, the registry is just `List.of(...)`, whereas a real plugin host can maintain a shared registry:

~~~java
// Illustrative code: host already has Rule API and dynamicRule object.
List<Rule> rules = new java.util.ArrayList<>();

// Classpath providers registered in META-INF/services/demo.api.Rule.
java.util.ServiceLoader.load(Rule.class).forEach(rules::add);

// Add verified runtime-compiled implementation.
rules.add(dynamicRule);

// From here the host simply iterates and invokes Rule.
~~~

**Dynamic rules do not automatically appear in ServiceLoader just because the compiler generated a class.** ServiceLoader requires service registration via META-INF/services or module `provides` according to the deployment model. For in-memory dynamic rules, the host can **register the instance directly into the registry** as shown above; there is no need to fabricate fake descriptors to make ServiceLoader scan a bytecode Map.

In a real architecture:

- **Discovery** determines how candidates are located from JARs, modules, databases, source code, or external registries.
- **Compilation/loading** turns source into a valid Rule instance with version and loader metadata.
- **Registration** places verified instances into a shared list/snapshot.
- **Execution** sees only Rule/Request and returns results per contract.
- **Lifecycle** stops accepting new requests, drains active tasks, and drops references/loaders when replacing versions.

Whether you use a DI container, a map of strategies, or a routing table instead of ServiceLoader, the principle remains identical: **one shared contract and one consistent execution path**.

## 9. Keeping Host Classes Out of Dynamic Output

At compile time, javac needs the definitions of Rule and Request. The option:

~~~text
-classpath <host's java.class.path value>
~~~

in the demo helps the compiler locate the pre-built API classes in `build/classes`. This is a choice **for a simple classpath lab**, not a policy to copy verbatim into a multi-tenant service. If the host classpath contains internal libraries not meant for rules, the compiler can resolve those APIs and dynamic source can link against them.

In production, supply an **explicitly allowlisted compile classpath**, containing only the approved API/SPI/DTO and rule libraries. Execution needs matching runtime permissions and may require process isolation. Never let requests arbitrarily control `-classpath`, `--module-path`, `-processorpath`, `-d`, or other compiler options.

Having StandardJavaFileManager read dependencies from the classpath **does not cause Rule to be recompiled**. In the demo, compile units contain only `SourceText(TravelRule)`. Therefore the output Map holds only the new implementation and any nested types generated by that source, not the host's API.

With JPMS named modules, merely passing `-classpath` like in the lab may be insufficient: you must consider the module path, readability, exports, and the API layer. ModuleLayer/uses/provides follow different contracts; creating a classpath MemoryClassLoader does not generate a Module object or add a module to a layer. When migrating the architecture to named modules, design module resolution and loader mapping separately.

## 10. Limitations You Must Not Overlook

The lab code **is not a sandbox**. JavaCompiler can consume significant CPU/heap, and compiled code, once loaded and executed, runs with the full privileges of the host process. A ClassLoader separates class namespaces; it **is not a security boundary**.

| Risk | What the lab code does | What production still needs |
| --- | --- | --- |
| Huge source input | Checks `String.length()` against 10,000 UTF-16 code units | Check **input bytes before buffering the full request**, file count, encoding, total bytes |
| Excessive class/bytecode output | Stores in Map and ByteArrayOutputStream | Enforce **class count and total byte limits inside the output stream**, not after compile finishes |
| Excessive compiler diagnostics | Uses DiagnosticCollector | Listener/Writer with count/character/byte quotas and safe logging |
| Automatic annotation processors | Sets `-proc:none` | Lock processor path/options and dependency allowlists |
| Compiler hangs or burns CPU | No timeout yet | Compile inside a **process/container with CPU/RAM quotas** and hard deadlines |
| Execution side effects | Only runs trusted source in the lab | Run untrusted code in a separate process with restricted file/network/OS privileges |
| Loading wrong ABI | `asSubclass` checks Rule type | API version pinning, binary compatibility tests, classpath/module identity |
| Stale rule lifecycle | LoadedRule keeps instance and loader | Registry snapshots, task draining, and clearing references before unloading |
| Duplicate rule names/versions | Demo uses a fixed dynamic name | Namespace/versioning scheme, artifact hashing, ownership verification |
| Unexpected dependency loading | Parent points to host loader | Compile/runtime dependency policy; avoid exposing the entire host classpath to workers |

**A soft timeout is not a hard timeout.** For instance, wrapping a compiler task in `Future.get(timeout)` and calling `cancel(true)` only limits **how long the caller waits**; it does not guarantee the compiler or rule code actually stopped. If an untrusted user submits source that exhausts compiler CPU/heap, you need process isolation and real kill/cleanup mechanisms.

**Never equate successful compilation with safe source code.** Valid Java code can still call `System.exit`, access files, open network sockets, spawn threads, or trigger side effects in static initializers, constructors, or `matches`. `Class.forName(..., true, loader)` and `newInstance` in the lab **already execute user code**; isolating them from the host is mandatory if sources are untrusted.

Production systems also require digital signatures/hashes or verified origins for rule code, change audit trails, publish permissions, dependency checks, and rollback mechanisms.

## 11. Versioning, Caching, and Hot Reload

A dynamic rule is a **versioned unit of implementation**, not an in-place mutation of the existing Rule interface. When source changes:

1. Create a new candidate version with source hash, API version, compiler options, and dependency set.
2. Compile into new bytecode and hold output temporarily in memory or a quota-bounded artifact cache.
3. Create a new class loader (do not try reusing a loader that already defined the same binaryName).
4. Instantiate the new Rule and run contract, ID, and health/sanity checks.
5. Publish a new registry snapshot only after validation passes.
6. Stop routing new requests to the old version and wait for in-flight requests using the old instance to finish.
7. Clear references from registries, threads, ThreadLocals, callbacks, and caches to the old Rule/loader so GC can reclaim them once unreachable.

**Why must a new loader be created?** The JVM does not redefine the same class name in the same loader via `defineClass` as a normal hot-replace. Calling `defineClass` again for an existing binaryName typically throws LinkageError; loading different bytecode through a new loader is a much cleaner versioning model. Do not force "in-place class replacement in the old loader" in production unless you have intentionally chosen specialized instrumentation/redefinition mechanisms with their own constraints.

**Caching** can reduce compile cost for repeated sources. Keys should include **source hash + Java release + compiler options + Rule/Request API version + dependency fingerprints**. Caching solely by source text risks reusing bytecode that is binary-incompatible after host API changes. Caches need TTL/size caps and must not leak data across tenants without an explicit policy.

A rule version may hold instance state. Do not arbitrarily share a single instance across concurrent requests if the implementation is not thread-safe; choosing singleton, per-request instance, or actor/serial executor belongs in the lifecycle contract.

## 12. Proper Three-Layer Testing

### 12.1. Contract tests

For every Rule instance (builtin or dynamic), run the exact same test suite:

~~~java
// Illustrative code: given Rule rule and Request request.
String id = rule.id();
if (id == null || id.isBlank()) {
    throw new IllegalArgumentException("Rule ID must not be blank");
}
boolean decision = rule.matches(request);
// Assert decision per test case policy.
~~~

Stop testing via a branch like "if dynamic then call eval(String)". This lets one contract test suite catch behavioral mismatches across both rule sources.

### 12.2. Compilation tests

- Valid input with matching binaryName → `CompilationTask.call()` succeeds and bytecode contains the requested class.
- Syntax/type error → `CompilationTask.call()` fails with diagnostic locations; candidate is not published.
- Mismatched package/class name → verify source URI, class file names, and the `Class.forName` step.
- Source with nested classes → Map captures **all** outputs needed by the implementation.
- Oversized source → rejected before creating a compilation task.
- Mismatched options, compile classpath, or JDK version → full error logged and active registry untouched.

### 12.3. Runtime integration tests

- Parent loader sees the right Rule/Request; dynamic class casts to Rule and executes `matches`.
- Built-in and dynamic rules receive **the same Request object** and share result/error handling code.
- Broken constructor or static initialization → candidate is not published.
- `matches` throws an exception → recorded as **execution failure**, not treated as `matches=false`.
- Source update/recompile with a new loader → new version is selected after publish; in-flight work on the old version finishes per lifecycle.
- Concurrent requests → consistent registry snapshots with no races during loader swaps.
- Untrusted or hung rule → worker/process is isolated and the system continues serving other requests.

**Output must be verifiable decisions**, not merely Strings printed by the compiler. If the application needs multi-state decisions, define a Decision type with explicit error/status codes instead of boolean; all implementations return that type.

## 13. Extension Exercises

**Exercise A — third rule:** Write a source String for `demo.dynamic.OfficeRule` implementing Rule that returns true when `request.category().equals("office")` and `amount >= 50`. Compile it in the same process under a different binaryName, add it to the registry, and print results. No changes to the Rule interface are needed.

**Exercise B — syntax error check:** Change `amount()` to `amountX()` in the TravelRule source. Capture diagnostic line/kind and verify no dynamic Rule instance is published when compilation fails. Do not rely on a subsequent class-loading error as your compilation-failure check.

**Exercise C — class identity check:** Create a loader that does not share the Rule API from the parent in a controlled experiment and try casting types. Analyze why matching the name `demo.api.Rule` is insufficient; restore the parent-first setup for the host.

**Exercise D — new version:** Change the threshold from 500 to 900, create a new loader, and swap the registry after validation. Verify `Request("travel", 800)` changes from match to no-match in the new version, while the old instance is retired only after no requests remain using it.

**Exercise E — output quota:** Add file-count and total-byte-write limits to ClassBytes/MemoryFileManager before buffering into ByteArrayOutputStream. Test with source generating nested/anonymous classes. When quotas are exceeded, publish no partial output.

**Exercise F — process separation:** Move compiling, loading, and executing untrusted sources to a separate Java worker process that receives source and Request over a bounded IPC protocol. Compare waiting on a `Future` timeout inside the same JVM with terminating the worker process and reclaiming resources.

**Exercise G — combining with a plugin JAR:** Create a JAR-packaged Rule provider with `META-INF/services/demo.api.Rule`; use ServiceLoader in the host to load it into the registry, then add TravelRule from the memory compiler. Verify all three implementations are invoked via one `List<Rule>` and the same Request schema.

## 14. Production Readiness Checklist

- **API:** Rule/Request are shared artifacts with clear versioning and behavioral contracts; never redefined inside implementation loaders.
- **Source:** Java sources have verified owners, class/package names, size, and encoding; compile classpath and options are server-controlled.
- **Compiler:** check `ToolProvider.getSystemJavaCompiler()`, collect diagnostics, disable annotation processing unless permitted; manage the standard file manager properly.
- **Output:** retain all emitted class files in memory, enforce class count/byte limits, and never register failed or partial outputs.
- **Loading:** parent loader unifies the SPI; verify exact class name, subtype check, constructor validation, and classify linkage/instantiation errors.
- **Registration:** publish only Rules passing validation and contract tests; update registry snapshots atomically per concurrency design.
- **Execution:** all Rules share the same invocation path and DTO; timeouts, exceptions, and retry/fallback are policy-defined.
- **Security:** never treat ClassLoader as a sandbox; compile and execute untrusted sources outside the host JVM with quotas and OS isolation.
- **Lifecycle:** track plugin ID/version, support rollback, clean up callbacks/threads/references, and use a new loader on reload.
- **Observability:** record compiler duration, output byte count, diagnostics, loader/version IDs, and rule invocation latency, separating compile, load, and execution errors.

Java SE 17 references: [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html), [SimpleJavaFileObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html), [ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html), [ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), and [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

**Conclusion:** The success of runtime extensibility does not lie in generating a .class file, but in ensuring **dynamic code adheres to the same contract stabilized by the host**, is loaded via a loader that respects class identity, and enters the pipeline only after verification. Then a built-in rule, a JAR provider, and a rule compiled from a String can all process Requests through Rule — while compilation, loading, lifecycle, and security remain cleanly separated and managed responsibilities.