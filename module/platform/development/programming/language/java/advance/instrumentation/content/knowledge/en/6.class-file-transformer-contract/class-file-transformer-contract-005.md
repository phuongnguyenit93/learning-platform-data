# Filtering Classes by Name, Loader, Module, and Code Source Before Bytecode Analysis

## 1. The problem: transformers are invoked for more classes than we intend to modify

After a Java agent registers a `ClassFileTransformer` via `Instrumentation.addTransformer(...)`, the JVM can invoke the callback for application, library, agent, and runtime classes. If we parse the entire `classfileBuffer` first and only then decide whether a class needs instrumentation, the agent wastes CPU/memory on unrelated classes, slows down startup, and increases the risk of accidental modifications.

**Core principle:** use the metadata that the JVM **already provides in the callback** to filter first, and only analyze bytecode when the class is within the intended scope. The four main metadata items are:

1. **Class name**: internal name such as `com/acme/orders/OrderService`.
2. **Class loader**: the `ClassLoader` object that **defines** the class.
3. **Module**: the runtime module (named or unnamed) that owns the class.
4. **Code source**: `CodeSource` obtained via `ProtectionDomain`, if the class has this metadata.

This lesson helps you design an ordered allowlist, understand when each condition must be checked, handle `null`, distinguish class name from JVM identity, and build a runnable Java 17+ agent that proves **it never reads the bytecode of rejected classes**.

**Limitation to remember:** an instrumentation scope filter helps select the right targets; it does **not** by itself verify code signatures or grant JVM permissions. If a criterion is a mandatory policy requirement, missing data to evaluate it must have an explicit handling branch, typically `return null` (do not instrument).

## 2. Reading the `ClassFileTransformer.transform` contract accurately

On JDK 17 there is an overload with module information:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
~~~

This is an API signature extracted for structure, not a standalone program. When writing a class transformer, override this overload if you need the module. On Java 17, both `transform` overloads are **default methods**; the six-parameter overload delegates to the five-parameter overload by default, and the five-parameter overload returns `null` by default. Therefore, you should not assume this is a functional interface for use with a lambda.

| Parameter | Meaning in the callback | What to guard against |
|---|---|---|
| `className` | Internal class name such as `java/util/List`, using `/` | Mistakenly comparing against a binary name with `.`; not handling `null` |
| `loader` | Defining class loader; `null` if defined by the bootstrap loader | Comparing the loader's class name instead of instance identity |
| `module` | Named or unnamed module of the class | Calling `module.getName().equals(...)` when the module is unnamed |
| `protectionDomain` | Domain used when defining the class, which may contain a `CodeSource` | Chaining `getCodeSource().getLocation()` without `null` checks |
| `classBeingRedefined` | Usually `null` on initial definition; the target class during redefine/retransform | Confusing it with a class to actively look up via `Class.forName` |
| `classfileBuffer` | Classfile bytes passed by the JVM to the transformer on this invocation | Parsing early, mutating in-place, or retaining a reference for later modification |

If the class does not need to be modified, **return `null`**. If it does need to be modified, create a **valid new byte array**, and do not modify `classfileBuffer` directly. When multiple transformers are present, the bytes from an earlier transformer may be passed into a later transformer; do not assume the input array is identical to the `.class` file on disk.

The order of callbacks is not a fixed list of classes: the JVM can invoke them multiple times from different threads, especially when the application loads classes dynamically, and there may be redefine/retransform passes depending on capabilities.

## 3. Placing metadata filters at the start of the callback

An easy-to-check order that usually performs well:

~~~text
transform(module, loader, name, redefining, domain, bytes)
     |
     v
[1] name matches exact class or package allowlist?
     | no -> return null
     v
[2] loader identity/loader policy matches?
     | no -> return null
     v
[3] module type and name/identity match?
     | no -> return null
     v
[4] domain -> CodeSource -> valid origin?
     | no/unknown -> return null
     v
[5] only now parse/inspect classfileBuffer
     |
     +-- no changes -> return null
     +-- needs transformation -> return valid new byte[]
~~~

This approach avoids turning every callback into a JAR open, annotation scan, method analysis, or constant pool decode. Name and identity filters are typically very cheap; URL/path checks are also only executed for the small set of classes that passed the earlier conditions.

Scope expression:

~~~text
selected =
    isAllowedName(className)
 && isAllowedLoader(loader)
 && isAllowedModule(module)
 && isAllowedOrigin(protectionDomain)

if (!selected) return null;
return inspectOrTransform(classfileBuffer);
~~~

This is **pseudo-code**, not a standalone runnable Java class. In practice, define clearly what "allowed" means: an exact class, a package with boundaries, a loader identity, a module name/instance, and an allowed source directory/JAR.

## 4. Filtering by name: internal name vs. binary name

The name normally written in Java code and the name in the callback are two different forms:

| Name in Java | `className` in the transformer |
|---|---|
| `com.acme.OrderService` | `com/acme/OrderService` |
| `com.acme.internal.Metrics` | `com/acme/internal/Metrics` |
| `com.acme.Outer$Inner` | `com/acme/Outer$Inner` |

If selecting only a single exact class:

~~~java
if (!"com/acme/OrderService".equals(className)) {
    return null;
}
~~~

Placing the literal on the left side of `equals` is **null-safe** if `className` has no value. If selecting the `com.acme.orders` package and its subpackages:

~~~java
if (className == null
        || !className.startsWith("com/acme/orders/")) {
    return null;
}
~~~

There must be a trailing `/` on the prefix to avoid accidentally matching `com/acme/ordersInternal/Hidden`. If you only want the outer class and not nested classes, use exact class name comparison; nested names usually contain `$` and a broad prefix can be too wide.

The naming policy should include an exclude set for agent/helper packages, the bytecode engine, or the logging backend if the allowlist could cover them. Common mistakes are `startsWith("com/acme")` without a separator, accidentally touching `com/acme2`, or using `contains("Service")` which does not express package boundaries.

**Do not call `Class.forName(...)` inside the callback to determine the class name.** The callback already provides the name. Actively loading a class while the JVM is defining another class can cause class loading recursion, linkage errors, or cause the target class to load before the agent is ready. Only after filtering completes should you proceed to byte analysis if needed.

## 5. Filtering by class loader: identity defines the class

According to the JVM, class identity is not just a string name. Two definitions with the same binary name but **different defining loaders** are two different types.

~~~text
System loader -------> demo.OrderService  (Class A)
Plugin loader -------> demo.OrderService  (Class B)

Same name, different defining loader => A and B have different identities.
~~~

In a normal classpath program, if only the system loader is allowed:

~~~java
if (loader != ClassLoader.getSystemClassLoader()) {
    return null;
}
~~~

This is an **`==` comparison between two loader objects**, not comparing `loader.getClass().getName()`. Multiple `URLClassLoader` instances have the same Java class, yet each instance can define a separate set of classes.

`loader == null` is the bootstrap loader case. The snippet above excludes bootstrap classes automatically; if you write a different condition, you must handle null before calling methods on `loader`:

~~~java
if (loader == null) {
    return null;
}
~~~

**When should you not lock onto the system loader?** Spring Boot executable JARs, OSGi, application servers, plugin platforms, multiple custom class loaders, or hot-reload environments may load business code through a different loader. In those cases you need a verified policy for target loaders, such as a specific set of instances or a way to identify the custom application loader combined with code source/module. Do not drop loader checks altogether just because the system loader case filters incorrectly.

Hot-reload systems must be careful not to retain unbounded strong references to old class loaders. Caching by loader can leak the application on redeploy. If the loader set is updated concurrently, build an appropriate state-publishing/caching mechanism instead of letting the callback read a collection being mutated without synchronization.

## 6. Filtering by `Module`: named, unnamed, and layers

JDK 9+ uses the Java Platform Module System. `Module` reflects the runtime module of the class:

- **Named module:** `module.isNamed() == true`; `module.getName()` returns a name such as `com.acme.orders`.
- **Unnamed module:** `module.isNamed() == false`; `module.getName() == null`. Each defining loader has its own unnamed module.
- Named modules also belong to a module layer (there can be multiple layers in an application), so **module name is not always sufficient to identify a module instance** in complex topologies.

If you only want classes from the classpath unnamed module:

~~~java
if (module == null || module.isNamed()) {
    return null;
}
~~~

If you only want a specific named module:

~~~java
if (module == null
        || !module.isNamed()
        || !"com.acme.orders".equals(module.getName())) {
    return null;
}
~~~

The two snippets above are illustrative conditions. They cannot be applied together because they express **two different module selection policies**.

What to avoid:

~~~java
// Wrong: getName() can be null if it is an unnamed module.
if (module.getName().equals("com.acme.orders")) {
    // ...
}
~~~

Do not assume "unnamed = trusted application". A plugin JAR or library on the classpath also belongs to an unnamed module. Combine module with loader and origin.

If you want to instrument a named module and inject calls to an agent helper, **module selection does not guarantee the helper is accessible**: you also have to consider readability, exports/opens, and loader visibility. `Instrumentation.redefineModule(...)` can expand certain module relationships per the API contract, but that is a separate decision, applied only when needed and tested.

## 7. Filtering by code source: `ProtectionDomain` and `CodeSource`

`ProtectionDomain` groups protection domain information when a class is defined. `ProtectionDomain.getCodeSource()` returns a `CodeSource` **if available**. `CodeSource.getLocation()` returns the codebase `URL` **if provided**.

You must handle the entire null chain:

~~~text
protectionDomain?
    |
    +-- null --------------> return null
    |
    v
getCodeSource()?
    |
    +-- null --------------> return null
    |
    v
getLocation()?
    |
    +-- null --------------> return null
    |
    v
location (URL) -> apply origin policy
~~~

Defensive example:

~~~java
if (protectionDomain == null) return null;
java.security.CodeSource cs = protectionDomain.getCodeSource();
if (cs == null || cs.getLocation() == null) return null;
java.net.URL url = cs.getLocation();
~~~

**The source is not necessarily a `.class` file path:** for a classpath directory, the location is usually the root directory. For a class from a JAR, the location may be a URL to the JAR. With custom class loaders, in-memory/generated classes, nested JARs, runtime images, or specialized packaging, this metadata may be absent or have a non-`file:` URL scheme.

To compare a `file:` code source against an allowed directory/JAR, use `URL → URI → Path` instead of a string prefix:

~~~java
java.net.URL location = cs.getLocation();
if (!"file".equalsIgnoreCase(location.getProtocol())) {
    return null;
}

java.nio.file.Path actual;
try {
    actual = java.nio.file.Path.of(location.toURI())
            .toAbsolutePath()
            .normalize();
} catch (java.net.URISyntaxException
        | IllegalArgumentException ex) {
    return null;
}

if (!actual.equals(allowedOrigin)) {
    return null;
}
~~~

`allowedOrigin` is a `Path` normalized from configuration **once** before registering the transformer. Use `Path.equals` when the policy is **an exact classpath root or a single JAR**; use `Path.startsWith(Path)` when the policy allows subdirectories (and symbolic links/permissions have been considered). Do not use `location.toString().startsWith("/opt/app")` because `/opt/app-bak` shares the same string prefix, and URL encoding can differ from OS paths.

**Some important limitations:**

- `normalize()` resolves `.` and `..` syntactically; it does not verify symbolic links or actual files. `toRealPath()` can require disk I/O, so perform it at initialization/configuration time if required, not on every callback.
- `CodeSource` is metadata attached to the class by the loader; it is **not cryptographic proof** that the bytes were properly signed or have not been replaced.
- For unknown sources when the policy requires an origin allowlist, it is best to **fail closed**: return `null` before parsing bytecode. If the product needs to instrument generated classes, define an explicit separate policy branch rather than implicitly allowing all null sources.
- If the URL does not have a `file:` scheme (for example, a nested-loader representation), do not pass it directly into `Path.of(URI)`; write an adapter appropriate for that origin type.
- Choose the code source as seen by the **running** JVM. Paths inside a container may differ from the host.

## 8. A runnable Java agent on JDK 17+ using all four conditions

The example below uses only the JDK, requiring no Byte Buddy, ASM, or Maven. The agent observes only **`sample.target.ReceiptService` from the system loader, unnamed module, and source directory `out/app`**. Only after passing all four conditions does it read the first 8 bytes of the classfile: the `CAFEBABE` magic and Java 17 major version `61`.

The example also creates two rejected scenarios: a class with the same simple name but wrong package, and a class with the **same full binary name** defined by a different custom `URLClassLoader`. The transformer always returns `null` to preserve original behavior.

### 8.1. The files

~~~text
filter-demo/
├── MANIFEST.MF
├── src/
│   ├── agent/sample/agent/
│   │   ├── FilterAgent.java
│   │   └── ScopeFilter.java
│   └── app/sample/
│       ├── app/App.java
│       ├── target/ReceiptService.java
│       └── other/ReceiptService.java
└── out/                  # Created during the build step
    ├── agent/
    ├── app/
    └── filter-agent.jar
~~~

File `src/agent/sample/agent/FilterAgent.java`:

~~~java
package sample.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;

public final class FilterAgent {
    private FilterAgent() {}

    public static void premain(String agentArgs, Instrumentation inst) {
        if (agentArgs == null || agentArgs.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected code-source directory in agent arguments");
        }

        Path allowedOrigin = Path.of(agentArgs)
                .toAbsolutePath()
                .normalize();

        inst.addTransformer(new ScopeFilter(allowedOrigin));
        System.out.println("[agent] filter installed");
    }
}
~~~

`premain` runs before `App.main`. The configured path is normalized once; the transformer receives immutable state. Here exactly one argument is chosen for the source directory, so no complex key-value parser is needed.

File `src/agent/sample/agent/ScopeFilter.java`:

~~~java
package sample.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class ScopeFilter implements ClassFileTransformer {
    private static final String TARGET =
            "sample/target/ReceiptService";

    private final Path allowedOrigin;

    public ScopeFilter(Path allowedOrigin) {
        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) throws IllegalClassFormatException {

        // 1. Filter name: do not touch bytecode.
        if (!TARGET.equals(className)) {
            return null;
        }

        // 2. Filter defining loader by identity.
        if (loader != ClassLoader.getSystemClassLoader()) {
            return null;
        }

        // 3. Filter module: classpath unnamed module only.
        if (module == null || module.isNamed()) {
            return null;
        }

        // 4. Filter code source, defensive against null.
        if (protectionDomain == null) {
            return null;
        }
        CodeSource source = protectionDomain.getCodeSource();
        if (source == null || source.getLocation() == null) {
            return null;
        }

        URL location = source.getLocation();
        if (!"file".equalsIgnoreCase(location.getProtocol())) {
            return null;
        }

        Path actualOrigin;
        try {
            actualOrigin = Path.of(location.toURI())
                    .toAbsolutePath()
                    .normalize();
        } catch (URISyntaxException | IllegalArgumentException ex) {
            return null;
        }
        if (!allowedOrigin.equals(actualOrigin)) {
            return null;
        }

        // ONLY AFTER ALL FOUR GUARDS inspect the bytecode.
        if (classfileBuffer == null || classfileBuffer.length < 8) {
            throw new IllegalClassFormatException("Short class header");
        }

        int magic = ((classfileBuffer[0] & 0xff) << 24)
                | ((classfileBuffer[1] & 0xff) << 16)
                | ((classfileBuffer[2] & 0xff) << 8)
                | (classfileBuffer[3] & 0xff);
        if (magic != 0xCAFEBABE) {
            throw new IllegalClassFormatException("Bad class magic");
        }

        int major = ((classfileBuffer[6] & 0xff) << 8)
                | (classfileBuffer[7] & 0xff);

        System.out.println("[agent] selected "
                + className.replace('/', '.')
                + " major=" + major);
        return null; // Observe only, do not modify class bytes.
    }
}
~~~

A few important points when reading the code:

- `TARGET.equals(className)` is safe when `className == null`; it is the first guard.
- `loader != ClassLoader.getSystemClassLoader()` rejects the bootstrap loader and other custom loaders without calling any method on `loader`.
- `module == null || module.isNamed()` allows only unnamed modules; this is a demo policy, not a restriction imposed by the JVM.
- `CodeSource` may be absent; missing information is safely rejected.
- `major` is computed only after all four guards have passed. The Java 17 classfile major version is **61**.
- When no transformation is needed, return `null`; do not modify the byte array from the JVM and do not block other transformers.

File `src/app/sample/target/ReceiptService.java`:

~~~java
package sample.target;

public final class ReceiptService {
    private ReceiptService() {}

    public static void execute() {
        System.out.println("[app] target execute");
    }
}
~~~

File `src/app/sample/other/ReceiptService.java`:

~~~java
package sample.other;

public final class ReceiptService {
    private ReceiptService() {}

    public static void execute() {
        System.out.println("[app] other execute");
    }
}
~~~

File `src/app/sample/app/App.java`:

~~~java
package sample.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java sample.app.App <compiled-app-dir>");
        }

        System.out.println("[app] main");

        // Same name/package selected by the agent, system loader.
        Class<?> target = Class.forName(
                "sample.target.ReceiptService");
        target.getMethod("execute").invoke(null);

        // Same simple name, different package: fails the name guard.
        Class<?> other = Class.forName(
                "sample.other.ReceiptService");
        other.getMethod("execute").invoke(null);

        // Same full binary name, but different defining loader.
        URL source = Path.of(args[0])
                .toAbsolutePath()
                .normalize()
                .toUri()
                .toURL();

        try (URLClassLoader isolated = new URLClassLoader(
                new URL[] { source },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> copy = Class.forName(
                    "sample.target.ReceiptService",
                    true,
                    isolated);
            copy.getMethod("execute").invoke(null);
        }

        System.out.println("[app] done");
    }
}
~~~

The new `URLClassLoader` has the **platform class loader** as its parent. Because the platform loader does not have this business class, the copy of `sample.target.ReceiptService` is defined by the custom loader. If the system loader were used as the parent, parent-first delegation could return the already-loaded class, preventing the example from demonstrating a different loader.

File `MANIFEST.MF` (must end with a trailing newline):

~~~text
Manifest-Version: 1.0
Premain-Class: sample.agent.FilterAgent

~~~

When packaged with `jar cfm`, the manifest is stored as `META-INF/MANIFEST.MF` inside the agent JAR. `Can-Retransform-Classes` is not needed because the example only observes initial loads.

### 8.2. Compiling

From the `filter-demo/` directory, create the output folders.

Bash:

~~~bash
mkdir -p out/agent out/app
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Run the following commands using **JDK 17 or later**:

~~~bash
javac --release 17 -d out/agent src/agent/sample/agent/FilterAgent.java src/agent/sample/agent/ScopeFilter.java

javac --release 17 -d out/app src/app/sample/app/App.java src/app/sample/target/ReceiptService.java src/app/sample/other/ReceiptService.java

jar cfm out/filter-agent.jar MANIFEST.MF -C out/agent .
~~~

`javac --release 17` ensures the compiled class files target Java 17; the header has major version 61. `out/agent` holds the agent classes; `out/app` holds the application classes.

### 8.3. Running without the agent

~~~bash
java -cp out/app sample.app.App out/app
~~~

Output:

~~~text
[app] main
[app] target execute
[app] other execute
[app] target execute
[app] done
~~~

The target class is loaded twice by two different loaders, and the method prints the same string. There are no agent lines.

### 8.4. Running the agent with the matching origin

~~~bash
java -javaagent:out/filter-agent.jar=out/app -cp out/app sample.app.App out/app
~~~

Expected output in the example's classpath directory environment:

~~~text
[agent] filter installed
[app] main
[agent] selected sample.target.ReceiptService major=61
[app] target execute
[app] other execute
[app] target execute
[app] done
~~~

Explanation:

1. The agent is initialized before the application and registers the transformer.
2. `sample.target.ReceiptService` from the system loader, unnamed module, and `out/app` directory passes all four guards; the transformer reads the header and prints `major=61`.
3. `sample.other.ReceiptService` fails immediately at the name guard.
4. The copy of `sample.target.ReceiptService` created by the isolated `URLClassLoader` has the same full name and same source directory, but fails the loader guard, so its header is not read a second time.
5. Both copies of `ReceiptService` still run unchanged because the transformer always returns `null`.

### 8.5. Proving the source guard with a non-matching origin configuration

~~~bash
java -javaagent:out/filter-agent.jar=out/not-the-app -cp out/app sample.app.App out/app
~~~

With an exact source policy, `out/not-the-app` differs from `out/app`. The output has no `[agent] selected ...` line, even though the target is still loaded and executed; the callback is rejected **before parsing bytes**.

Note: the demonstration example does not check whether the directory passed into `premain` exists. In a real system, validate configured paths early and decide clearly between fail-fast or disabled mode.

## 9. From demo to a real bytecode-analyzing transformer

In the example we read the first 8 bytes of the classfile solely to illustrate the **starting point** for working with bytes. When building a real agent, the section after the four guards can call ASM, Byte Buddy, or the Class-File API if using a supported JDK (the Class-File API was standardized in JDK 24). On JDK 17, do not import `java.lang.classfile` because that API does not exist in JDK 17.

~~~text
Metadata gates passed
       |
       v
Class-file parser
       ├── read class version, constant pool
       ├── find methods/annotations to instrument
       └── build new result
              ├── unchanged: null
              └── modified: valid new byte[]
                              └── checked by JVM verifier
~~~

Real transformations must satisfy classfile rules, code attributes, stack map frames, exception paths, and retransform/redefine constraints if it is not an initial load. **Filtering the right target does not guarantee valid bytecode transformation.**

Some complex cases:

- Instrumenting already-loaded classes via `retransformClasses` requires the capability, modifiable classes, and a transformer registered as retransform-capable. `addTransformer` does not automatically reprocess already-loaded classes.
- A class with the same name can appear from multiple class loaders; the filter's decision must be based on the loader of the **current callback invocation**, not a global name lookup.
- If instrumented bytecode calls a helper, you must verify that the helper can link from the target class's defining loader/module; the four class-selection guards do not automatically solve helper visibility.
- In a system with multiple agents, a transformer may see bytes already transformed by an earlier step. Ensure idempotency or distinguish already-modified classes using an accurate mechanism; do not rely on a single hash without understanding the transformation chain.

## 10. Misconceptions that lead to bugs

### 10.1. "Right package means right class"

False in plugin platforms: two loaders can both contain `com.acme.OrderService`. A name-only filter instruments both. You need loader identity and/or code source/module policy.

### 10.2. "The loader's `getClass().getName()` is enough to distinguish"

No. Two `URLClassLoader`s share the same Java class. They are different instances and can define separate classes; comparing by loader class name yields the wrong result.

### 10.3. "Unnamed module means app code"

No. Each loader has its own unnamed module; classpath library code or plugins can all belong to an unnamed module. You must check loader and code source.

### 10.4. "Having a `ProtectionDomain` guarantees a CodeSource URL"

No. `ProtectionDomain.getCodeSource()` and `CodeSource.getLocation()` can be `null`. Returning `null` for classes with insufficient information when origin is required is a safe and predictable policy.

### 10.5. "Comparing URL strings with `startsWith` is enough"

No. Separators, URL encoding, canonical paths, and symlinks change the result. Use `URI`/`Path` structures for compatible schemes and distinguish exact origin from subtree origin.

### 10.6. "Parse first to find the loader or module"

False. Both pieces of information are already in the callback. Do not parse the constant pool, load classes reflectively, or open JARs just to infer data you already have.

### 10.7. "`return null` blocks all other transformers"

False. It only tells the JVM that the current callback did not transform the input. The JVM still applies the transformer chain per the API contract.

### 10.8. "CodeSource verifies class trustworthiness"

No. CodeSource can carry URL and signer metadata, but origin alone is not comprehensive security proof. Checking trust/signatures/hashes is a separate responsibility.

### 10.9. "Logging every skip gives free debugging"

No. Callback volume can be huge, especially at startup. Synchronous logging in every callback slows down the application and can trigger additional class loads from the logging framework. Prefer counters/rate limiting and time-bounded debugging.

### 10.10. "System loader is the loader of every business class"

No. Spring Boot executable JARs, application servers, and frameworks use custom loaders. Not seeing an event does not necessarily mean the name is wrong; diagnose the actual runtime loader/module/origin before adjusting the policy.

## 11. Testing and QA matrix for deployment

| Scenario | Name | Loader | Module | Source | Behavior |
|---|---|---|---|---|---|
| Target from `out/app` with system loader | Pass | Pass | Unnamed pass | Pass | Read class header, major=61 |
| Class with same simple name, different package | Fail | Not checked | Not checked | Not checked | Return `null` before reading bytes |
| Same full binary name as target, custom loader | Pass | Fail | Not checked | Not checked | Return `null` |
| Target with right loader/module, different source | Pass | Pass | Pass | Fail | Return `null` |
| Bootstrap loader `null` | Depends | Fail in demo | Not checked | Not checked | Skip |
| Named module | Depends | Depends | Fail in demo | Not checked | Skip |
| Missing `CodeSource` under mandatory policy | Pass | Pass | Pass | Unknown | Return `null`, record skip metric if needed |
| Corrupted classfile bytes, metadata passes | Pass | Pass | Pass | Pass | Parser/verifier may report error; do not use invalid bytes |

QA in production-like environments should include real classloaders, module layers, nested JAR origins, generated classes, code source changes during deployment/containerization, multiple active agents, and retransform/redefine callbacks if the agent uses them. Performance tests should compare startup and throughput before and after enabling instrumentation.

**Three events must be kept distinct:**

- Log "transformer registered" only proves registration succeeded.
- Log "selected ... major=61" proves the class passed the filter and the classfile header was inspected.
- **Actual instrumentation** is only proven when the transformer returns valid new bytes and the application exhibits the expected behavior.

## 12. Review questions

**1.** There are two classes with the same name `com.acme.Payment`, defined by two different loaders. Is an exact name filter enough?

> No. The internal name is the same, but JVM type identity differs. A loader/module/origin policy is needed to distinguish the right class.

**2.** Does `module.getName()` returning `null` prove this is an application class?

> No. The class belongs to an unnamed module; many loaders and libraries can own unnamed modules. Additional checks are required.

**3.** If `protectionDomain.getCodeSource()` is `null`, must the agent instrument it?

> No. When policy requires a known origin, skipping that class is appropriate. If generated classes must be supported, an explicit alternative mechanism must be defined.

**4.** Why use `Path.equals` or `Path.startsWith(Path)` according to policy, instead of `String.startsWith` on the URL?

> Because paths have segment boundaries and handle URI/encoding properly. An exact file policy differs from a subtree policy; a string prefix can mistakenly match directory names.

**5.** When may the bytecode parser be invoked?

> After `className`, defining loader, module, and code source have passed all required guards. If metadata alone is insufficient, return `null`.

**6.** Is the copy of `sample.target.ReceiptService` loaded by `URLClassLoader` in the example selected?

> No. Despite having the same full binary name and directory origin, its defining loader differs from the system loader, so it is rejected before reading bytes.

**7.** Does `return null` mean no class will be defined anymore?

> No. The JVM continues with the current bytes and subsequent transformer/verification steps. This callback simply does not modify the bytes.

**8.** If a callback passes the filter but the bytecode is corrupted, can the filter be considered buggy?

> Not necessarily. The filter determines **scope**; classfile parsing/transformation is a subsequent responsibility that can fail due to format, version, or unsupported modifications.

## 13. Official documentation

- Java 17 `ClassFileTransformer`: `transform` parameters, load/redefine/retransform events, `return null` and byte array contract: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java 17 `Instrumentation`: `addTransformer` and capability-based registration: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java 17 `ProtectionDomain`: `getCodeSource()` and class loader metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- Java 17 `CodeSource`: location URL and signing metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- Java 17 `Module`: named/unnamed modules, module name and layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- JVM Specification (Java SE 17): class loading, identity, and classfile: https://docs.oracle.com/javase/specs/jvms/se17/html/index.html
