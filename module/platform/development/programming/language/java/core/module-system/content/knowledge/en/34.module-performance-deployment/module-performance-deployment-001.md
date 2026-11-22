# Module Graph Resolution Cost at Startup

## 1. Where Does Module Resolution Sit in Startup?

When running a modular application, Java needs to build the **module graph** before loading the main class and executing the application. Starting from the root modules, the resolver finds the required modules via `requires` directives, checks readability relationships, package consistency, and module system constraints. The result is a `Configuration` used to create or define a module layer.

This is one part of startup, but not the entirety of startup. It is important to distinguish:

1. **Module discovery and resolution:** finding modules on the module path, reading metadata, resolving dependencies, and validating the graph.
2. **Module layer creation:** creating the layer and class loaders for the resolved modules.
3. **Class loading and linking:** loading, verifying, and linking the required classes.
4. **Service discovery and provider initialization:** finding and initializing providers when the application iterates over `ServiceLoader`.
5. **Application initialization:** running static initializers, creating objects, opening connections, reading configuration, and performing application work.

If startup time increases, you should not assume the cause is module resolution by default. An application with a small graph can still start slowly due to class loading, framework initialization, I/O, or external connections.

## 2. Factors That Affect Resolution Cost

### Number of Observable Modules

The resolver needs to search for modules in the provided sources, such as the runtime image and the module path. A module path containing many unrelated JARs or module directories can increase discovery and metadata inspection work, depending on how the finder and filesystem operate.

Keep the module path clean, containing only the artifacts needed for runtime. Avoid placing an entire library repository, intermediate build directories, or multiple versions of dependencies on the same module path.

### Breadth of the Dependency Graph

The resolver starts from root modules and follows `requires` dependencies. The wider or deeper the graph, the more modules and relationships need to be processed and validated.

Causes of graph bloat include:

- Adding unnecessary root modules.
- Using `--add-modules ALL-MODULE-PATH`, which turns many modules on the module path into roots.
- Large transitive dependencies or a facade module propagating readability across many dependencies.
- Provider modules and their dependencies being pulled into the graph via service binding.
- Frameworks or applications creating multiple module layers with their own configurations.

The number of JARs is not the only metric. A single module with many transitive dependencies can produce a larger graph than many small modules that are not resolved.

### Service Binding

For a configuration created with `Configuration.resolveAndBind`, the module system also inspects service types declared by modules in the graph via `uses`, finds modules with matching `provides`, and adds those providers along with their dependencies.

This is useful for SPI, but it can widen the graph. An added provider may also have its own dependencies and service uses, causing the binding process to keep expanding the graph.

Distinguish between pulling a provider module into the graph and instantiating the provider. Resolution/service binding handles the module graph; `ServiceLoader` is what actually finds and instantiates implementations when the application iterates over providers.

### Repeated Module Layer Creation

A plugin application may create custom `ModuleLayer` instances at runtime. Each time a configuration is resolved and a layer is defined, it incurs its own cost in addition to the initial boot layer cost.

If the application repeatedly creates the same layer for the same set of modules, the costs of discovery, resolution, class loaders, and initialization can repeat. When semantics and lifecycle permit, reuse the created layer instead of rebuilding it on every request.

## 3. Measure Startup Before Optimizing

Measure the time from process start to a meaningful readiness milestone for the application, such as a `READY` log line after completing necessary initialization. The time from invoking `java` until the main method begins does not fully reflect when the application can serve requests.

Measurement design:

- Use the exact same JDK, JVM flags, module path, configuration, and data as the target environment.
- Run multiple times in fresh processes; record the median and p95 instead of a single run.
- Separate cold start and warm filesystem cache if both matter.
- Keep CPU, heap size, container limits, and background load stable.
- Measure process start, main start, and application ready separately if possible.
- Do not mix build time, artifact download, or external infrastructure initialization into resolution measurements if the goal is to understand the module graph alone.

Example on Linux:

```bash
/usr/bin/time -f 'elapsed=%e s' \\
  java --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

On PowerShell:

```powershell
Measure-Command {
    java --module-path mods -m com.acme.app/com.acme.app.Main
}
```

These commands measure total process time. To measure application ready time, have the application emit a clear log/metric milestone and use an external harness to record the time from launch to that milestone.

Do not compare two configurations if one enables debug logging, JFR, or module resolution printing while the other does not. Diagnostic tools can introduce additional I/O and overhead.

## 4. Observing the Actual Module Graph

Enable `--show-module-resolution` to see which modules are selected as roots, which are resolved via `requires`, and which are bound via services:

```bash
java --show-module-resolution \\
  --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

Illustrative output:

```text
root com.acme.app file:///opt/app/mods/com.acme.app.jar
com.acme.app requires com.acme.api file:///opt/app/mods/com.acme.api.jar
com.acme.api requires java.logging jrt:/java.logging
com.acme.app binds com.acme.provider.json file:///opt/app/mods/com.acme.provider.json.jar
```

How to read it:

- `root`: module chosen as a starting point for resolution.
- `requires`: dependency brought into the graph according to the module descriptor.
- `binds`: provider module added through service binding.

This output helps identify unwanted modules, large transitive dependencies, and bound providers. It is not a timing report for individual resolution steps; you cannot look at a `binds` line and conclude how many milliseconds that provider cost.

You can use `--list-modules` to see the modules the launcher can list in the current configuration:

```bash
java --module-path mods --list-modules
```

This is the list of observable modules; it does not mean all of them are resolved into the application's graph.

## 5. Using jdeps to Reduce Unnecessary Dependencies

`jdeps` analyzes static dependencies of class files and JARs. It helps explain why the module graph needs certain modules and detect dependencies that are no longer needed.

Summarize dependencies:

```bash
jdeps --module-path mods --summary mods/com.acme.app.jar
```

List module dependencies:

```bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

Print comma-separated list of module names:

```bash
jdeps --module-path mods \\
  --print-module-deps mods/com.acme.app.jar
```

Check descriptor:

```bash
jdeps --module-path mods --check com.acme.app
```

These results help find unnecessary static dependencies or overly broad module descriptors. However, jdeps cannot always detect classes loaded via reflection, class names in configuration, dynamic plugins, or all service providers. Do not remove `uses`, `provides`, or dependencies solely because they do not appear in bytecode reports.

## 6. Optimizing Module Path and Root Modules

### Put Only Required Dependencies on the Module Path

Organize a dedicated runtime directory containing the exact JAR versions being deployed. Do not use a shared directory with multiple versions or experimental build artifacts.

Example:

```text
runtime/
├── app/
│   └── com.acme.app.jar
└── mods/
    ├── com.acme.api.jar
    ├── com.acme.spi.jar
    └── com.acme.provider.json.jar
```

Keep the module path consistent across environments to avoid resolution having to process different sets of artifacts and to reduce errors from duplicate module names.

### Avoid Adding All Modules as Roots When Unnecessary

`--add-modules ALL-MODULE-PATH` can be useful for testing or certain plugin environments, but turning every module on the module path into a root can significantly expand the graph.

In production, only add the root modules you actually need. Modules required via `requires` will be found by the resolver following the dependency closure.

### Maintain Explicit Dependencies

Prefer module descriptors that reflect actual dependencies. Avoid adding `requires transitive` if the public API does not need to propagate readability to consumers. Broad transitive dependencies can force downstream modules to read additional unnecessary modules.

Automatic modules are helpful during migration, but explicit module descriptors give clearer control over `requires`, `exports`, `uses`, and `provides`. Converting to explicit modules does not guarantee automatic speedup; the main benefit is a clearer graph and API boundaries.

## 7. Controlling Service Binding and Providers

If the application uses SPI, check which providers actually need to be included at runtime. Do not leave experimental providers or unused plugins on the module path.

With `jlink`, the `--bind-services` option instructs the linker to link service providers along with their dependencies. This can cause the runtime image to include extra provider modules. Only enable it when the application needs those providers.

Example:

```bash
jlink \\
  --module-path "$JAVA_HOME/jmods:mods" \\
  --add-modules com.acme.app \\
  --bind-services \\
  --output runtime-image
```

If you do not need all observable providers, review the set of modules and services the application actually uses before enabling service binding in the image. Testing is needed to ensure required providers are not accidentally omitted.

At runtime, avoid creating multiple custom layers or iterating and initializing all providers when only one implementation is needed. If a service needs an explicitly configured provider, apply an appropriate selection policy instead of relying on iteration order.

## 8. Using jlink to Build a Lean Runtime Image

`jlink` creates a runtime image containing the selected set of modules and their required dependencies. A smaller image can reduce the number of system modules that need to be deployed and make the runtime environment more stable.

Basic example:

```bash
jlink \\
  --module-path "$JAVA_HOME/jmods:mods" \\
  --add-modules com.acme.app \\
  --output runtime-image
```

Running with the image:

```bash
runtime-image/bin/java \\
  --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

On Windows, the executable is `runtime-image\\bin\\java.exe` and the separator for entries in the module path is a semicolon.

`jlink` performs most of the module selection work at build time and produces a custom runtime image. It does not eliminate all application resolution costs at launch, because application modules and layers still need to be processed. The actual impact on startup depends on image size, module graph, filesystem, and how the application runs.

Use `jdeps --print-module-deps` to help identify static dependencies, but add modules used via reflection, service binding, or dynamic configuration before linking the image. Test the image with realistic functional flows.

## 9. Distinguishing Resolution from Class Loading and CDS

If startup is slow, the time-consuming part may lie after module resolution:

- Class loading and verification of many classes.
- Static initializers doing heavy work.
- Frameworks scanning the classpath/module path or annotations.
- Initializing logging, dependency injection, and serializers.
- Connecting to databases, DNS, TLS, or remote services.
- JIT compilation and code warm-up.

Class Data Sharing (CDS) can reduce part of JVM initialization and class loading cost by sharing archived metadata/class data. CDS does not replace module resolution and does not make the dependency graph disappear.

When testing CDS, measure configurations with and without the archive separately, keeping all other factors identical. Do not conclude that module resolution became faster solely because total startup decreased; the reduction may come from class loading or other stages.

## 10. Measure and Compare Each Change

Change one factor at a time to see its impact:

| Experiment | What to Keep Constant | What to Observe |
|---|---|---|
| Reduce number of JARs on module path | JDK, roots, application code | Discovery and total startup |
| Remove unnecessary roots | Module path and service behavior | Graph size, startup |
| Reduce transitive dependencies | API behavior and tests | Resolved modules and compatibility |
| Reduce bound providers | Service contract and output | Number of providers/modules in graph |
| Reuse custom layers | Plugin lifecycle and semantics | Layer creation time, startup/request latency |
| Use jlink image | JDK version and functionality | Image size, startup, deployment behavior |
| Enable CDS | Same module graph and workload | Class loading and total startup |

Each configuration should be run multiple times in fresh processes. Record JDK vendor/version, OS, CPU, container memory/CPU limits, module path, JVM flags, number of resolved modules, and the application ready milestone.

Use median and p95 to avoid drawing conclusions from an anomalous single run. If you only measure total startup, call the result total startup; do not attribute the entire difference to module resolution without evidence.

## 11. Common Optimization Mistakes

- **Enabling `--limit-modules` just hoping for faster startup:** this option changes the observable module universe and can cause missing dependencies or providers. It is not a general speedup switch; only use it when the limited module set has been identified and tested.
- **Using `ALL-MODULE-PATH` in production unnecessarily:** this option can expand the root set and graph.
- **Removing modules based on jdeps output without checking reflection/SPI:** this can make plugins or providers disappear.
- **Creating a new layer for every request:** repeats resolution and layer definition costs.
- **Enabling diagnostic logging in benchmarks:** console output can skew measurements.
- **Assuming jlink eliminates resolution completely:** the image is smaller, but the application still needs to initialize the required module graph/layers.
- **Optimizing module count while ignoring initialization:** framework scanning, I/O, and static initializers can often account for a significant portion of startup.

## 12. Practical Optimization Workflow

1. Measure the baseline from process start to application ready with production configuration.
2. Re-run with `--show-module-resolution` to understand roots, dependencies, and service bindings.
3. Use `jdeps` to find unnecessary static dependencies and validate descriptors.
4. Check whether the module path, root modules, and providers included in the graph match actual needs.
5. Check whether any custom layer or service provider is being initialized repeatedly.
6. If the runtime image is large, try `jlink` with the identified module set and test thoroughly.
7. Analyze class loading, framework initialization, and I/O if total startup is still slow.
8. Re-run the same benchmark and compare median/p95 before accepting changes.

## Takeaways

- Module resolution is one part of startup, separate from layer creation, class loading, provider initialization, and application initialization.
- Cost depends on module discovery, dependency graph breadth, service binding, and the number of custom layers created.
- `--show-module-resolution` helps observe the graph but does not measure timing for each step.
- `jdeps` helps reduce static dependencies; dynamic and service dependencies must be added manually.
- Keep the module path small, roots explicit, providers limited to what is needed, and reuse layers where appropriate.
- `jlink` and CDS can reduce different parts of the cost; measure separately to determine actual effectiveness.
- Do not attribute every startup improvement to module resolution if measurements have not isolated the stages.
