# Why injected code may not be able to see the agent's helper

A Java agent can inject a call to `agent.ProbeHelper.hit()` into an application method. The agent itself calls `ProbeHelper.hit()` normally, and the transformed bytecode is valid, yet when the application method executes, the JVM throws `NoClassDefFoundError: agent/ProbeHelper`. The common reason is that **the injected code executes in the target class, while the helper is defined in a class loader space that the target class cannot look up**.

This article explains exactly where the JVM looks for a helper, why a transformer can see the helper while the instrumented method cannot, how to reproduce the error with Java 17+, how to choose where to deploy the helper, and how to diagnose it in applications with multiple class loaders or the Java Platform Module System (JPMS).

## 1. The agent seeing a class does not mean the target class sees it too

In a startup agent, Java Instrumentation typically involves two groups of classes:

- **Agent classes**: implement `premain`, `ClassFileTransformer`, configuration logic, and dependencies such as bytecode transformation libraries. According to the `java.lang.instrument` specification, classes from the agent JAR are loaded by the **system class loader**, in its corresponding unnamed module.
- **Instrumented application classes**: may be loaded by the system class loader, the bootstrap class loader, or a custom class loader created by a container/framework/plugin. Each class carries an identity consisting of **its binary name and its defining class loader**.

Suppose a transformer running inside the agent emits the following JVM instruction in the `demo.BusinessService.handle()` method:

```text
invokestatic agent/ProbeHelper.hit:()V
```

When the transformer generates bytecode, it is operating on a `byte[]` array. When the JVM loads or links the `BusinessService` class, the call above becomes a **symbolic reference** in the constant pool of `BusinessService` itself. To resolve the reference to `agent.ProbeHelper`, the JVM uses class linking rules based on **the defining loader of `BusinessService`** (and that loader's loading/delegation mechanism), and then checks access. The JVM does not redirect this call to the transformer object's class loader just because the transformer authored the injected bytes.

Here is the key difference:

| Operation | Determining environment |
| --- | --- |
| Agent calls `ProbeHelper.hit()` from `premain` | The class loader of the calling agent class |
| Transformer uses ASM to inject `INVOKESTATIC agent/ProbeHelper.hit` | The transformer only modifies bytes and the symbolic reference |
| `BusinessService.handle()` runs the injected instruction | The loader/module of **the `BusinessService` class** determines resolution and access checking |
| Agent calls `Class.forName("agent.ProbeHelper")` successfully | Only proves that the loader used in that test call can find the helper |

**Bottom line:** the presence of the helper on the agent's classpath does not automatically make the helper appear in every class loader in the JVM.

## 2. Example class loader hierarchy causing the error

Consider the following lookup tree:

```text
Bootstrap class loader
    |
    +-- java.lang.Object, java.lang.String, ...
    |
System / application class loader
    |
    +-- agent.Agent
    +-- agent.ProbeHelper
    |
Isolated URLClassLoader (parent = null)
    |
    +-- demo.BusinessService
        `-- invokestatic agent/ProbeHelper.hit:()V
```

This diagram represents **lookup and visibility relationships**, not that every loader necessarily forms a parent-first tree. In the example, the isolated `URLClassLoader` does not delegate to the system loader; it only has its own search path and access to bootstrap classes. Because `agent.ProbeHelper` only resides in the system loader, the call from `BusinessService` cannot find the helper.

A class belonging to the bootstrap class loader has a similar problem: for example, when an agent instruments a method of a JDK class defined by bootstrap while the helper only resides in the agent JAR loaded by the system loader. The lookup direction from bootstrap does not automatically go down to the system loader.

In practice, similar situations appear in:
- Plugin runtimes that use isolated class loaders so plugins do not share libraries.
- Application servers deploying multiple applications with different module/webapp loaders.
- Frameworks using child-first loaders or loaders with package filters.
- Instrumentation of JDK/Java platform classes loaded by bootstrap.
- Applications with multiple versions of the same class name or helpers defined by different class loaders.

**Parent-first delegation is just one common policy**; a custom class loader can load locally first, filter packages, or refuse to delegate. You cannot infer helper visibility solely from the class loader's name.

## 3. Why the error may only appear when running the method

The bytecode contains an `invokestatic` referencing the class/method name and descriptor. By linking rules, the JVM must resolve that reference before it can execute the call. The timing of resolution can be eager or lazy depending on the JVM and execution path, so you should not assume that `ClassFileTransformer.transform(...)` succeeding or `Class.forName("demo.BusinessService")` succeeding is proof that the helper has been linked.

Typical flow:

```text
Agent receives byte[] of BusinessService
    |
    v
Transformer adds invokestatic agent/ProbeHelper.hit:()V
    |
    v
JVM loads/defines BusinessService using isolated loader
    |
    v
handle() method is called
    |
    v
Resolve agent.ProbeHelper via BusinessService's loader
    |
    +-- found + valid access -------> call helper
    |
    +-- not found ------------------> NoClassDefFoundError
    |
    +-- found but access denied
                                   --> IllegalAccessError or appropriate linkage error
```

Depending on the specific details, the error may surface at the loading/linking stage before the first call, not necessarily right at the `invokestatic` instruction when inspecting logs. If resolving a symbolic reference has failed, the JVMS specifies that subsequent resolution attempts for the same reference fail with the same error. Therefore, **adding the helper to the search path after the error has occurred does not guarantee "fixing" that reference in the running class**. You should prepare the helper loading path before instrumenting or before the class uses the reference.

Distinguish two commonly confused errors:
- `ClassNotFoundException` is a checked exception from explicit class-loading APIs such as `ClassLoader.loadClass`/`Class.forName` when the class is not found.
- `NoClassDefFoundError` is a `LinkageError` commonly seen when the JVM cannot resolve a class referenced by bytecode (or a class definition fails to initialize). A `ClassNotFoundException` may be the cause of this error.

## 4. Running a Java 17+ example to reproduce and fix helper visibility

The example uses only the JDK, requiring no external libraries. `BusinessService.handle()` already contains the helper call in its source code **to simulate the exact `invokestatic` instruction that a real transformer would inject**. The goal is to isolate the linking and class loader rules; this example does not perform bytecode weaving itself.

Structure:

```text
helper-visibility/
|-- src/
|   |-- Launcher.java
|   |-- agent/
|   |   `-- ProbeHelper.java
|   `-- demo/
|       `-- BusinessService.java
`-- out/                # created during compilation
    |-- host/           # helper + Launcher; visible to system loader
    `-- target/         # BusinessService only; visible to isolated loader
```

### 4.1. Helper placed on the system loader's classpath

File `src/agent/ProbeHelper.java`:

```java
package agent;

public final class ProbeHelper {
    private ProbeHelper() {}

    public static void hit() {
        System.out.println("helper: hit");
    }
}
```

In a real system, this could be a class packaged in the agent JAR and called by the agent from `premain`. It is made public with a public static method to avoid confusing access-level errors with class-loading errors.

### 4.2. Target class carrying the symbolic reference to the helper

File `src/demo/BusinessService.java`:

```java
package demo;

public final class BusinessService {
    public void handle() {
        agent.ProbeHelper.hit();
    }
}
```

The Java compiler generates bytecode with a reference similar to the following injected code (illustrated using ASM; **this snippet is not a standalone ASM program**):

```java
methodVisitor.visitMethodInsn(
    org.objectweb.asm.Opcodes.INVOKESTATIC,
    "agent/ProbeHelper",
    "hit",
    "()V",
    false
);
```

Both directly compiled Java code and calls injected by ASM must obey the same symbolic reference resolution rules when the JVM runs the method.

### 4.3. Launcher testing three loading paths

File `src/Launcher.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Launcher {
    private static void attempt(String label, URL[] locations, ClassLoader parent)
            throws Exception {
        try (URLClassLoader loader = new URLClassLoader(locations, parent)) {
            try {
                Class<?> target = Class.forName("demo.BusinessService", true, loader);
                Object instance = target.getConstructor().newInstance();
                target.getMethod("handle").invoke(instance);

                // Compare Class identity: the same name does not necessarily mean the same class.
                Class<?> resolvedHelper =
                        Class.forName("agent.ProbeHelper", false, loader);
                boolean same = resolvedHelper == agent.ProbeHelper.class;
                System.out.println(label + ": OK, sameHelper=" + same);
            } catch (InvocationTargetException e) {
                Throwable cause = e.getCause();
                System.out.println(label + ": "
                        + cause.getClass().getSimpleName());
            } catch (LinkageError e) {
                // Some JVMs may resolve eagerly during class loading/linking.
                System.out.println(label + ": " + e.getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL targetDir = Path.of("out", "target").toUri().toURL();
        URL hostDir = Path.of("out", "host").toUri().toURL();

        attempt("isolated", new URL[]{targetDir}, null);
        attempt("delegate-to-system", new URL[]{targetDir},
                ClassLoader.getSystemClassLoader());
        attempt("helper-in-isolated", new URL[]{targetDir, hostDir}, null);
    }
}
```

Three cases:

1. `isolated`: the loader has `parent=null`, seeing only the directory containing `BusinessService` and bootstrap. The helper in `out/host` is not in the loading path.
2. `delegate-to-system`: the loader loads `BusinessService` from `out/target`, while `ProbeHelper` can be resolved through the system loader as its parent.
3. `helper-in-isolated`: the loader has no system parent, but the `out/host` directory is also on its own loading path. It defines its own `agent.ProbeHelper` that is **different** from the class of the same name already defined by the system loader.

### 4.4. Compiling and observing the results

Create the `out/host` and `out/target` directories. With bash on Linux/macOS:

```bash
mkdir -p out/host out/target
```

Or with Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/host, out/target | Out-Null
```

Then run the commands below from the `helper-visibility` directory using JDK 17+ (same `javac`/`java` syntax across operating systems):

```bash
javac -encoding UTF-8 -d out/host src/agent/ProbeHelper.java src/Launcher.java
javac -encoding UTF-8 -cp out/host -d out/target src/demo/BusinessService.java
java -cp out/host Launcher
```

Expected output:

```text
isolated: NoClassDefFoundError
helper: hit
delegate-to-system: OK, sameHelper=true
helper: hit
helper-in-isolated: OK, sameHelper=false
```

Analysis:
- Compilation succeeds because the compiler sees `ProbeHelper` via `-cp out/host`. However, **the compile-time classpath does not determine class lookup capability inside a custom loader at runtime**.
- With the isolated loader, `BusinessService.handle()` cannot resolve `agent.ProbeHelper`; reflection may wrap the error thrown inside the method in `InvocationTargetException`, so the launcher extracts `getCause()`.
- In the second case, the system parent provides the exact same helper class that is on the launcher's classpath, so `sameHelper=true`.
- In the third case, the isolated loader loads a separate copy of `ProbeHelper` from `out/host`; the call succeeds, but `sameHelper=false`. If the helper has static counters, caches, or callbacks, the isolated loader's copy **does not share static state** with the system loader's copy.

The `out/host` directory in the third case also contains the `Launcher` class, purely to reduce the number of build commands in the demo. In real-world deployments, you should package a dedicated helper JAR rather than exposing the entire agent classpath to plugin loaders.

## 5. Choosing a strategy to make the helper visible to instrumented code

There is no single strategy that fits every loader. Before injecting `invokestatic`, choose where the helper is defined, where instrumentation state lives, and how target classes reach the helper.

| Approach | When appropriate | What to check |
| --- | --- | --- |
| **Keep the helper in the system loader and let targets delegate to system** | Standard applications with an application class loader or a suitable hierarchy | Custom loaders may not delegate or may use child-first rules; bootstrap cannot look down into system |
| **Add a helper-only JAR to bootstrap search** via `Instrumentation.appendToBootstrapClassLoaderSearch` | Instrumentation points in JDK classes, or multiple loaders needing the same minimal bridge | The helper and all its dependencies must be resolvable by bootstrap; avoid putting the whole agent/ASM/libraries into bootstrap |
| **Inject the helper into the target's own loader** (loader-aware injection) | Isolated plugins/containers where each loader needs its own helper | Separate class identity/state per loader, package/module access, name collisions, and lifecycle/unloading |
| **Minimal bridge in bootstrap, rich processing in the agent** | Need widely visible hooks while keeping agent libraries isolated | The bridge must only use bootstrap-visible types; the forwarding mechanism must avoid recursion, manage loader references, and limit coupling |
| **Avoid injecting direct references to the helper** or use another suitable mechanism | Want to reduce linking dependencies in target classes | Check overhead, reliability, and dependency resolution of the alternative mechanism |

### 5.1. Bootstrap helper via Java Instrumentation

So that every class can find a simple helper through bootstrap, the agent can place a **JAR containing only helper classes designed for bootstrap** onto the bootstrap search path:

```java
// Snippet used inside premain(...), not a standalone Java file.
import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

JarFile helperJar = new JarFile("probe-bootstrap-helper.jar");
instrumentation.appendToBootstrapClassLoaderSearch(helperJar);
// Manage the JarFile lifecycle according to the agent lifecycle; do not close it arbitrarily
// while the JVM still needs to read unloaded entries from the JAR.
```

Register the JAR and ensure the helper class can be properly defined by bootstrap **before** target code attempts to resolve the helper. When instrumenting bootstrap classes, do not design a bootstrap helper that depends on libraries like ASM/Jackson/SLF4J or application classes loaded by system/child loaders, unless you prove the entire linking path is actually available. A public helper can simply push events into a safe queue and use minimal JDK APIs; advanced event processing should live elsewhere.

Note: adding a JAR to bootstrap search does not turn a `Class<?>` already defined by the system loader into a bootstrap class; two copies with the same name defined by different loaders may exist. The agent must actively control loading order, namespaces, and where state is stored. The specification also warns against packaging classes/resources not meant for bootstrap into this JAR so as not to accidentally "hijack" application class names.

### 5.2. The system loader is not globally visible

`appendToSystemClassLoaderSearch(JarFile)` only adds the JAR to the **system loader's** search path. It does not automatically create a delegation relationship from bootstrap or isolated loaders to the system loader. Similarly, `-javaagent:agent.jar` tells the JVM to load the agent, but does not guarantee that every target can resolve helpers from the agent JAR.

If a framework provides an official API to register or define helpers in a plugin/webapp loader, you should put the helper into that exact class loader **before** instrumenting classes that reference the helper. Avoid using reflection to force `ClassLoader#defineClass` into an arbitrary loader, because of access/module constraints, loading order, package protection, and potential conflicts with the framework.

### 5.3. JPMS: class visibility and access permissions are two different questions

Even when the helper is found, the JVM still must check module/package/class/method access. For example, if the helper resides in a **named module** whose package is not appropriately exported, the `invokestatic` call can throw `IllegalAccessError`; a non-`public` method can also be rejected. Opening a package (`opens`) generally pertains to deep reflection and does not substitute for the access requirements of a direct bytecode call.

With instrumentation via `java.lang.instrument`, the JVM provides special support: the module of a transformed class is arranged to read the unnamed module of the bootstrap loader and the unnamed module of the class loader that loaded the main agent. This **does not replace class loading** and does not make a helper in an unreachable loader suddenly appear. When the helper resides in another named module, you also need to consider appropriate read edges and package exports; `Instrumentation.redefineModule` can assist with permitted module graph adjustments. Merely adding `reads` when the class-loading path does not exist will not solve `NoClassDefFoundError`.

## 6. Accurate diagnostic workflow

When an error occurs, do not rush to add every JAR to the classpath. Verify the exact **definition of the target class** and the helper that the JVM needs to resolve:

1. **Read the root error:** extract the `cause` of `InvocationTargetException`, nested errors in the stack trace, the class name from `NoClassDefFoundError`, and the method location containing the injected bytecode.
2. **Identify the defining loader:** `targetClass.getClassLoader()`; a `null` value means bootstrap. Record the target module with `targetClass.getModule()`.
3. **Identify where the helper actually lives:** `helperClass.getClassLoader()`, `getModule()`, and the JAR location via `getProtectionDomain().getCodeSource()` if available.
4. **Test resolution with the target's loader:** `Class.forName("agent.ProbeHelper", false, targetLoader)` in an appropriate test environment. This test checks the class-name loading path, though it does not yet guarantee that descriptor, class identity, and access are all valid.
5. **Check the bytecode:** confirm that the internal name `agent/ProbeHelper`, name `hit`, descriptor `()V`, and opcode `INVOKESTATIC` actually match the helper class.
6. **Check deployment/modules:** whether the helper JAR is properly in the bootstrap/target loader, whether helper dependencies are on the same loading path, and whether the package is validly exported.
7. **Fix and verify with a clean startup:** test the target class through the right loader, invoke the method along the instrumented path, and confirm the probe produces a signal. Do not rely solely on the fact that the transformer returned bytecode.

A short diagnostic snippet you can place in test/diagnostic code holding `Class<?> targetClass`:

```java
// Diagnostic snippet: targetClass is the class actually being transformed.
ClassLoader targetLoader = targetClass.getClassLoader();
System.out.println("target loader=" + targetLoader);
System.out.println("target module=" + targetClass.getModule());

try {
    Class<?> helper = Class.forName(
            "agent.ProbeHelper", false, targetLoader);
    System.out.println("resolved helper loader=" + helper.getClassLoader());
    System.out.println("resolved helper module=" + helper.getModule());
} catch (ClassNotFoundException e) {
    System.out.println("target loader cannot find helper: " + e);
}
```

In the code example, `Class.forName(..., false, null)` tests loading capability from bootstrap; Java permits `loader=null`. Do not rely on `toString()` loader names to conclude two classes are the same; compare `Class<?>` directly whenever possible.

If you need to observe the JVM, JDK 17+ supports class-loading logs with the following command (this can produce a lot of output, so enable it in a test environment or with an appropriate scope):

```bash
java -Xlog:class+load=info -cp out/host Launcher
```

Logs show where a class was loaded from, but proving the specific loader and module should still rely on `Class<?>/ClassLoader` objects and the application's setup.

## 7. Distinguishing symptoms when the helper is unusable

| Symptom | Investigation direction |
| --- | --- |
| `NoClassDefFoundError: agent/ProbeHelper` | The target class's loader could not find the helper, or loading/linking the helper failed; read the cause |
| `ClassNotFoundException` when calling `Class.forName` | The passed loader has no search path for that class |
| `NoSuchMethodError` for `ProbeHelper.hit:()V` | A `ProbeHelper` class was found, but the method signature or version does not match the bytecode |
| `IllegalAccessError` | Class/package/method access is invalid; check access modifiers and JPMS exports/reads |
| `IncompatibleClassChangeError` | Bytecode expected a static method, but the runtime definition is incompatible, or a similar shape mismatch occurred |
| `ExceptionInInitializerError` / `NoClassDefFoundError: Could not initialize class...` | The class was found, but static initialization failed; a different cause from a missing class file |
| `ClassCastException` between two classes with the same name | Multiple loaders defined classes with the same name but different identities |
| `LinkageError` involving loader constraints | Loader constraints or version/type identities are incompatible |

There are cases where the helper itself loads, but **the helper depends on another class that fails to load**. The stack trace may name the dependency instead of the helper class. Do not ignore the cause and the full reference chain.

## 8. Designing helpers to avoid operational issues later

A helper used by multiple class loaders needs the following properties:

- **Minimal and stable public API:** keep package, binary name, descriptor, and parameter/return types compatible with the injected bytecode. For bootstrap helpers, prefer built-in JDK types and require no application types.
- **No circular dependencies:** if the helper calls back into a method that is also instrumented, it can cause infinite recursion or stack overflow. Filter helper/agent classes out of the transformer and use a reentrancy guard when needed.
- **Intentional state management:** a helper with multiple copies per loader will have separate static fields. If a shared counter/dataset is needed, design the bridge and data ownership clearly.
- **Do not retain loaders indefinitely:** maps from class loader to context must consider weak references, shutdown hooks, or plugin/container lifecycles; an improper strong-reference cache can prevent unloading.
- **Do not load the helper too late:** prepare the search path before classes are transformed or probe calls are resolved; record the deployed versions of the helper and the program.
- **Do not put the entire agent library into bootstrap:** avoid package collisions, non-bootstrap-visible dependencies, and the risk of unintended changes to class loading.
- **Test with the actual loaders:** test with bootstrap, system, child-first, isolated loaders, and multiple instances if the system supports them; exercise the real call path, not just transformer unit tests.
- **Clear error behavior:** collect linking/initialization errors and provide a way to safely disable instrumentation, rather than catching `Throwable` and silently swallowing it on the business path.

A practical design rule: **determine where the helper will be defined before deciding to inject an instruction referencing that helper**. Choosing a bootstrap, system, or per-loader helper is part of the instrumentation architecture, not merely a JAR packaging detail.

## 9. Self-check questions

1. Why does `Class.forName("agent.ProbeHelper")` succeeding inside `premain` not prove that `demo.BusinessService` can call the helper?
2. What is the difference between `URLClassLoader(..., null)` and `URLClassLoader(..., ClassLoader.getSystemClassLoader())` in the example?
3. Why does the `helper-in-isolated` scenario succeed in calling the helper yet report `sameHelper=false`? Are static counters in the two copies shared?
4. When instrumenting a class defined by the bootstrap loader, why is adding the helper only to the system classpath usually insufficient?
5. If `IllegalAccessError` is thrown instead of `NoClassDefFoundError`, what different things would you check?
6. Can you call `appendToBootstrapClassLoaderSearch` after a resolution error has already occurred and expect the existing call to work immediately? Why or why not?
7. When there are multiple plugin loaders, would you choose a singleton bootstrap bridge or a separate helper per loader? State the pros/cons and how to avoid memory leaks.

## 10. Authoritative references for further reading

- [Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): how agent classes are loaded and module-related notes.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, `redefineModule`.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation, loader identity, and class-loading APIs.
- [JVMS 21 — Loading, Linking, and Initializing, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): defining/initiating loaders, symbolic reference resolution, loader constraints, and access errors.
