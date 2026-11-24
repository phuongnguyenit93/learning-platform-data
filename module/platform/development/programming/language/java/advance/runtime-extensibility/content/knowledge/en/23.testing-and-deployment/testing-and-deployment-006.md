# Verifying Environments Missing a Compiler, Scripting Engine, or Required Module

## 1. Why Check Runtime Capabilities?

An extensible Java application at runtime may compile user-provided source code, execute scripts via JSR 223, discover providers with SPI, or load named modules via JPMS. Those capabilities **are not guaranteed just because the program runs on Java 17+**. A runtime image built with `jlink` may intentionally omit `jdk.compiler`, `jdk.jshell`, `java.scripting`, or other modules; even a full JDK does not include a JavaScript engine by default.

Therefore, before activating a plugin, the host needs to check the required capabilities in **the exact process, module graph, and class loader being used**, and distinguish between:

- **Missing module/API**: the runtime does not contain or resolve the required module.
- **API present but missing implementation/provider**: for example, `java.scripting` is present, yet `ScriptEngineManager` finds no JavaScript engine.
- **Provider present but unusable**: errors in version, dependency, class loader, module access, native library, or initialization.
- **Capable but disallowed by policy**: the organization forbids running untrusted compilers/scripts inside the host process.

A good preflight should produce clear results so deployment or the UI can decide whether to fail fast or degrade by feature. Never wait until the first request arrives to discover that the compiler or engine is missing.

## 2. Capability Check Matrix

| Capability | Related Module/API | Quick Check | Correct Interpretation |
|---|---|---|---|
| Runtime Java compiler | `java.compiler` API, implementation usually `jdk.compiler` | `ToolProvider.getSystemJavaCompiler()` | `null` means the system compiler is unavailable in the current runtime |
| JSR 223 script engine | `java.scripting` | `new ScriptEngineManager(loader).getEngineFactories()` | Empty list: no factory found via that manager/loader |
| Specific language engine | Language's JSR 223 provider | `getEngineByName("...")` | `null`: no engine with that alias within the manager's scope |
| Embedded JShell | `jdk.jshell` | `ModuleLayer.boot().findModule("jdk.jshell")` and attempt to create a session when applicable | Module presence does not equate to successful execution provider startup |
| Named module/plugin | JPMS `ModuleFinder`, `ModuleLayer` | Check `findModule`, resolve graph, or path finder | A module existing on disk is not necessarily resolved |
| SPI service provider | `ServiceLoader` | Iterate providers in the appropriate loader/layer | Correct module, `uses`/`provides`/service descriptor, and class identity all matter |

**Distinguish availability from readiness:** an API being present does not mean the provider works. When business requirements are critical, perform a small, controlled probe (compile probe, create engine, resolve module) rather than checking only whether a class name exists.

## 3. Compiler: API May Exist While Compiler Is Absent

The Java Compiler API is `javax.tools`. Call:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    // System compiler cannot be used in this runtime.
}
```

The snippet above is illustrative and requires importing `javax.tools.JavaCompiler` and `javax.tools.ToolProvider`. A standard JDK includes `jdk.compiler`, but a minimal runtime image or another JRE/runtime distribution may not support it. Do not rely solely on `Class.forName("javax.tools.JavaCompiler")`: that is an API interface and does not prove a compiler implementation is available.

### 3.1. Compile Probe and Policy

When `compiler != null`, if compilation is a mandatory capability, the host can attempt to compile a small Java unit in a controlled temporary directory. Set `-proc:none` to avoid unnecessary annotation processors, restrict the output directory, collect diagnostics, close the file manager, and clean up temporary files after the probe.

Distinguish `compiler unavailable`, `compile probe failed`, and `compiler disabled by policy` instead of reporting a generic 'Java error'. If the compiler is absent but the product only loads precompiled plugin JARs, disable dynamic compilation and continue normal operation.

## 4. Script Engine: `java.scripting` Does Not Bundle Languages

JSR 223 provides the `ScriptEngine`, `ScriptEngineFactory`, and `ScriptEngineManager` interfaces. Concrete engines are supplied by providers via the class path/module path or another appropriate deployment mechanism.

```java
ScriptEngineManager manager =
        new ScriptEngineManager(Thread.currentThread().getContextClassLoader());
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    // The JavaScript alias is not provided by any current provider.
}
```

This is an illustrative snippet requiring `import javax.script.*`. Since JDK 15, Nashorn was removed from the JDK; thus on a typical JDK 17 installation, `getEngineByName("JavaScript")` returns `null` unless a compatible engine is installed. Never assume every Java 17 machine has JavaScript.

Additional checks:

1. Iterate `manager.getEngineFactories()` to report actual language metadata and aliases instead of guessing names.
2. Choose the right class loader for JSR 223 provider discovery; a manager created with another loader may fail to see engines inside plugin JARs.
3. If the provider resides in a custom `ModuleLayer`, consider `ServiceLoader.load(layer, ScriptEngineFactory.class)` because the manager does not automatically scan arbitrary layers.
4. Quickly evaluate `engine.eval(...)` with a small expression in the actual language **only when the engine is trusted and preflight permits executing code**.

Do not use a client-supplied script as a startup probe; engine testing must use fixed source with minimal side effects and resource limits.

## 5. Required Modules: Present on Path Does Not Mean Resolved

JPMS separates **finding modules** (`ModuleFinder`) from the **resolved module graph** (`Configuration`) and the **live runtime modules** (`ModuleLayer`).

```java
boolean inBoot = ModuleLayer.boot().findModule("jdk.jshell").isPresent();
boolean inImage = java.lang.module.ModuleFinder.ofSystem()
        .find("jdk.jshell").isPresent();
```

This is an illustrative snippet: `inImage` indicates whether the module exists in the set of system modules visible to the finder; `inBoot` indicates whether the module is in the boot layer or searched ancestors. The two can differ if a module exists in the image but is not part of the resolved set. When a plugin lives in a child layer, check `pluginLayer.findModule(...)` instead of inspecting only the boot layer.

### 5.1. Required Checks Before Defining a Child Layer

Suppose the `plugins/` directory contains modular JARs. The host can use:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
boolean found = finder.find("demo.plugin").isPresent();
```

This snippet requires importing `java.lang.module.ModuleFinder` and `java.nio.file.Path`. Having a JAR file is not enough: the module descriptor may be invalid, the module name may differ from expectations, a required dependency may be missing, or split packages/module conflicts may cause resolution to fail.

To know whether a plugin can truly run, resolve a configuration against its parent, verify dependencies, and instantiate the layer according to policy. Failures should be reported under categories such as missing module, resolution conflict, or layer instantiation failure instead of being silently ignored.

### 5.2. JDK Diagnostic Commands

```bash
java --list-modules
java --describe-module jdk.jshell
java --show-module-resolution --module-path mods \
  --module demo.host/demo.host.Main
```

The last command is a **syntax template**, requiring an actual `mods` directory and `demo.host` module. `--list-modules` shows the observable modules in the launcher environment, while `--show-module-resolution` lets you observe the graph at startup. Do not infer that a listed module has been resolved into every layer.

## 6. Complete Java 17+ Example: Runtime Preflight Report

The following example uses APIs available in a full JDK 17. It **does not require a specific script engine** and does not evaluate untrusted scripts. Instead of printing machine-varying lists, it prints booleans so outputs can be compared across configurations.

Create `RuntimePreflight.java`:

```java
import java.lang.module.ModuleFinder;
import java.util.List;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.tools.ToolProvider;

public final class RuntimePreflight {
    public static void main(String[] args) {
        boolean compiler = ToolProvider.getSystemJavaCompiler() != null;
        System.out.println("compiler available: " + compiler);

        boolean scriptingModule = ModuleFinder.ofSystem()
                .find("java.scripting").isPresent();
        System.out.println("java.scripting in image: " + scriptingModule);

        boolean jshellModule = ModuleFinder.ofSystem()
                .find("jdk.jshell").isPresent();
        System.out.println("jdk.jshell in image: " + jshellModule);

        ScriptEngineManager manager = new ScriptEngineManager();
        List<ScriptEngineFactory> factories = manager.getEngineFactories();
        boolean javascriptEngine = manager.getEngineByName("JavaScript") != null;
        System.out.println("javascript engine available: " + javascriptEngine);
        System.out.println("factory count nonnegative: " + (factories.size() >= 0));

        boolean javaBaseResolved = ModuleLayer.boot()
                .findModule("java.base").isPresent();
        System.out.println("java.base resolved: " + javaBaseResolved);
    }
}
```

Compile and run with JDK 17+ where the relevant module APIs are present:

```bash
javac RuntimePreflight.java
java RuntimePreflight
```

On a **standard, full JDK 17 without any additional JavaScript engine installed**, a typical output is:

```text
compiler available: true
java.scripting in image: true
jdk.jshell in image: true
javascript engine available: false
factory count nonnegative: true
java.base resolved: true
```

This output corresponds to a **specific assumed environment**; actual results differ if using a minimal runtime image, extra engine providers, removed modules, or a different class loader. The `javac` command in the example also cannot run if the environment completely lacks a compiler. In an environment without `java.scripting`, a program that imports `javax.script` may itself fail to link or run; therefore this test suits a **full build**, not a universal probe runnable on every image.

### 6.1. Designing a Truly Safe Preflight for Missing Modules

If an application must run on an image **without `java.scripting`**, do not place all engine checks in a main entrypoint that has static imports or mandatory execution paths referencing it. Separate a small bootstrap module using minimal Java SE, detect modules first, and load JSR 223 adapter classes only when the API is available. Feature adapters can be organized as optional JARs/modules, or use controlled reflection to avoid hard linkage on code paths that must execute when the API is absent.

Similarly, for `jdk.jshell` and `jdk.compiler`, importing and instantiating directly dependent classes can cause the host to fail when the runtime image omits those modules; design clear loader/feature boundaries and test against each actual runtime image.

## 7. Testing Missing Capabilities with an Environment Matrix

Do not run tests only on a developer machine with a full JDK. Build a test matrix across different images and execution permissions:

| Environment | Expectation |
|---|---|
| Full JDK 17+, no extra script engine | Compiler is usually present; JavaScript engine may be absent |
| Custom `jlink` image without `jdk.compiler` | Dynamic compilation feature must report unavailable or fail fast per policy |
| Custom image without `java.scripting` | Script feature is disabled; core host continues working if boundaries are properly isolated |
| Image has `java.scripting` but no provider | No execution engine available; report missing provider |
| Engine JAR present but wrong loader | Factory is not discovered; do not misreport as a script syntax error |
| Missing required named module | Resolution/activation is blocked; do not partially load and continue |
| Module present but provider constructor fails | Provider status is failed; clean up and record the root cause |

To create a real runtime image, `jlink` requires a valid module closure. Example (illustrative; exact module set depends on the application):

```bash
jlink --add-modules java.base,java.logging \
  --output runtime-min
```

This image lacks compiler or script APIs unless they are added along with their dependency closure. A host with a static dependency on `java.scripting` will not run on the image above; you must isolate the feature and rebuild an appropriate image configuration. Do not use a simplistic `jlink` invocation to claim that any removed Java SE API can be detected by code that directly imports it.

## 8. Architecture for Handling Missing Features

For each capability, define the policy upfront:

**Fail-fast:** If the product strictly requires runtime Java compilation or an essential module contract to boot, return a startup error with the cause and remediation instead of continuing with a half-working system.

**Graceful degradation:** If scripting is only an optional feature, disable that button/feature, report the clear reason, and keep the rest of the host operational. Never silently swap the engine for another language or fall back to executing with incompatible semantics.

**Retry after installing add-ons:** Adding a JAR to the filesystem while the JVM is already running does not automatically update existing class loaders or the module graph. You must create a new manager with the appropriate loader or resolve/create a corresponding child layer; in some cases a restart is required for a new module/runtime image.

### Error Details to Expose

A structured preflight result should include: capability name, required/optional, status (`AVAILABLE`, `MISSING_API`, `MISSING_PROVIDER`, `BROKEN_PROVIDER`, `DISABLED_BY_POLICY`), technical cause, version, and remediation steps. Avoid logging full environment variables, classpaths containing secrets, or unnecessary user paths.

## 9. Common Pitfalls and How to Avoid Them

| Mistake | Consequence | Fix |
|---|---|---|
| `javax.tools.JavaCompiler` exists so compiler must exist | System compiler can still be `null` | Check `ToolProvider.getSystemJavaCompiler()` |
| `java.scripting` exists so JavaScript must run | JDK 17 does not include Nashorn | Look up engine provider by alias/factory and verify practically |
| JAR exists in `mods/` so module is loaded | Module may not have been resolved | Check `ModuleLayer`, `Configuration`, and resolution |
| Calling `Class.forName` on optional API at startup | App can fail before capability check runs | Isolate feature adapters and use lazy loading |
| Using `ScriptEngineManager` with the wrong loader | Engine not found even though JAR exists | Pass the right loader or use `ServiceLoader` by layer |
| Silently ignoring all provider errors | Hides broken deployments | Distinguish missing from broken; preserve diagnostics |
| Testing only on a full JDK | Misses failures when deploying a `jlink` image | Test on images matching production |

## 10. Implementation Checklist

- [ ] Document which compiler, script engines, JShell, and named modules are required vs. optional.
- [ ] Module APIs, provider implementations, and the runtime image are checked separately.
- [ ] Class loader/module layer used for preflight matches the actual execution path.
- [ ] Distinct messages exist for missing API, missing provider, broken provider, and policy denial.
- [ ] Tested on both minimal images and production images.
- [ ] All optional features are isolated from the bootstrap path if modules can be absent.
- [ ] Untrusted plugin code is never loaded or executed during the capability probe step.
- [ ] Clear fail-fast/graceful-degradation and rollout/rollback policies are defined.

**Conclusion:** In a Java runtime extensibility system, environment verification must go beyond checking for module or class names. The host must verify the compiler implementation, scripting provider, module graph, and actual loader, while separating required capabilities from optional ones. Building these checks into deployment preflight prevents late failures and produces clear status when the runtime image is missing components.
