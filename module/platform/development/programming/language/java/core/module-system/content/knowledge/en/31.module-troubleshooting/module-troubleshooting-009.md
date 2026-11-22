# How to Read --show-module-resolution and jdeps Output

## 1. Two tools answer two different questions

When debugging a modular Java application, you need to know which modules are brought into the module graph at launch and which modules the classes inside an artifact reference.

Two commonly used tools are:

- **`java --show-module-resolution`** prints module resolution details for the actual launch. It helps inspect root modules, resolved `requires` relationships, and bound service providers.
- **`jdeps`** analyzes static dependencies from class files, JARs, or modules. It helps uncover which modules/packages/classes bytecode references, missing dependencies, and descriptors that may need adjustment.

These are complementary perspectives. `--show-module-resolution` tells you what the module system resolved in that run; `jdeps` tells you which static references bytecode contains. Neither tool by itself proves that every dynamic execution path of the application is sound.

## 2. Enabling --show-module-resolution

Run the modular application with this option:

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Where:

- `--show-module-resolution` asks the launcher to print resolution details.
- `--module-path mods` points to the directory containing application modules and dependencies.
- `-m com.acme.app/com.acme.app.Main` selects the main module and main class.

It can be combined with other options used in the real environment, such as `--add-modules`, `--limit-modules`, `--upgrade-module-path`, or additional module paths. When debugging, keep the launch command matching the failing environment so you observe the exact module graph.

## 3. Reading root, requires, and binds lines

Output typically includes lines showing each module's role during resolution. Illustrative example:

```text
root com.acme.app file:///opt/app/mods/com.acme.app.jar
com.acme.app requires com.acme.api file:///opt/app/mods/com.acme.api.jar
com.acme.api requires java.logging jrt:/java.logging
com.acme.app binds com.acme.provider.json file:///opt/app/mods/com.acme.provider.json.jar
```

Meaning:

- **`root`**: module selected as a root for this launch, typically via `-m` or `--add-modules`.
- **`requires`**: module needing another module according to a dependency in its module descriptor; the resolver locates and includes that dependency in the graph.
- **`binds`**: module brought into the graph through service binding, typically because an already-resolved module declares `uses` for a service type supplied by a provider via `provides`.

Displayed module names and paths depend on the JDK, module finder, and module sources. The example above illustrates how to read the role of each line, not a fixed output for every application.

A module appearing in the output does not mean main code has invoked every class in that module. Resolution takes place at the module level before the application executes specific code paths.

## 4. Using the output to trace dependencies

Suppose the application reports a missing `com.acme.api` module. Look for the `requires` line leading to that module:

```text
root com.acme.app ...
com.acme.app requires com.acme.api ...
```

Then check:

1. Is module `com.acme.api` actually present on the module path?
2. Does the name in `requires` match the module name in the JAR?
3. Does the launch command's module path match the build/test configuration?
4. Is `--limit-modules` used in a way that excludes the module or dependency from the universe?
5. Is the module a provider discovered via service binding that is missing from observable module sources?

If the output contains a `binds` line, that signals service binding added a provider to the graph. If a provider does not appear, check that the consumer declares `uses`, the provider declares `provides`, and the provider resides in the module finders/parent configuration observed by the resolver.

Do not assume every module absent from the output is missing by mistake. That module may simply not be a root or a required dependency for the current run.

## 5. Using jdeps for an overview of dependencies

`jdeps` is a static dependency analyzer for class files and JARs. To view a module/package-level dependency summary, run:

```bash
jdeps --summary app.jar
```

Example output:

```text
app.jar -> java.base
app.jar -> java.logging
app.jar -> com.acme.api
```

How to read it:

- The left column is the artifact being analyzed.
- The right column is the module that the artifact statically depends on.
- `java.base` is the foundational dependency appearing in nearly all Java code.
- `java.logging` shows that bytecode references APIs belonging to that module.
- `com.acme.api` is an application dependency that must be provided on the module path or appropriate analysis environment.

Actual output may display JAR names, module names, or package names depending on flags and artifact type.

When analyzing a modular JAR alongside dependencies on the module path:

```bash
jdeps --module-path mods --summary mods/com.acme.app.jar
```

`--module-path` helps jdeps locate dependent modules to map references. If a dependency is absent from the module path, the report may flag an unresolved package or module.

## 6. Listing module-level dependencies

To view module dependencies:

```bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

Illustrative output:

```text
   java.base
   java.logging
   com.acme.api
```

Use `--print-module-deps` when you need a comma-separated list of module names, often useful when building a runtime image with `jlink`:

```bash
jdeps --module-path mods \
  --print-module-deps mods/com.acme.app.jar
```

Example:

```text
java.base,java.logging,com.acme.api
```

This list is derived from static dependencies detected by jdeps. If the application loads modules via reflection, class names read from configuration files, ServiceLoader, or dynamic plugin mechanisms, inspect further because those dependencies may not appear completely in bytecode analysis.

## 7. Viewing class-level dependencies

When you need to find which class creates a dependency, use verbose mode:

```bash
jdeps -verbose:class --module-path mods mods/com.acme.app.jar
```

Illustrative output:

```text
com.acme.app.Main -> com.acme.api.Customer com.acme.api
com.acme.app.Main -> java.lang.Object java.base
com.acme.app.Main -> java.util.logging.Logger java.logging
```

Each line indicates the source class referencing the target class and the associated module/package according to the JDK version's format.

How to read it:

- Check the left-hand class to see which piece of code creates the dependency.
- Check the right-hand class to find the referenced API.
- Verify that the module owning the target class is on the module path and read by the consumer.

You can use `-verbose:package` to inspect dependencies at the package level, or `-verbose:module` at the module level. Verbose modes produce longer output; use them when tracing the origin of a dependency.

## 8. Finding missing dependencies

When suspecting a JAR references packages absent from the supplied modules, run:

```bash
jdeps --missing-deps --module-path mods mods/com.acme.app.jar
```

Depending on the artifact and JDK, the output may indicate the source class and unfound target class. Illustrative example:

```text
com.acme.app.Main -> com.acme.legacy.LegacyClient not found
```

This indicates bytecode has a static reference to a class that jdeps cannot resolve within the current analysis scope.

Distinguish among:

- **Module not found at resolution:** the module graph cannot resolve a declared dependency.
- **Class/package not found in jdeps:** the tool cannot locate the target class from the analyzed artifact and module path.
- **ClassNotFoundException/NoClassDefFoundError at runtime:** the class cannot be found or defined/loaded in the class loader on the actual execution path.

These three situations are related yet not synonymous. Use the actual error message, module path, classpath, and class loader to determine the cause.

## 9. Checking module descriptors with jdeps --check

For a named module, you can check descriptors and dependencies:

```bash
jdeps --module-path mods --check com.acme.app
```

Depending on the JDK version and module setup, the report can show:

- The current module descriptor.
- Dependencies inferred by jdeps from bytecode.
- Dependencies that need further review or could be removed.
- Differences between the descriptor and static dependencies.

Do not blindly replace all of `module-info.java` with the tool's suggestions. Descriptors also express intentional module API contracts such as `requires transitive`, `requires static`, `uses`, and `provides`; some service relationships or dynamic dependencies cannot be inferred from bytecode alone.

In particular, jdeps analyzes static references and does not decide for the developer which modules must be exported to consumers. When seeing a package-not-visible error, you still need to inspect `requires` and `exports` in module descriptors.

## 10. Combining both tools to diagnose

Suppose an application launches yet lacks a provider or reports a missing dependency:

**Step 1: inspect the actual module graph**

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Record the roots, `requires` dependencies, and providers added via `binds`.

**Step 2: analyze static dependencies**

```bash
jdeps --module-path mods \
  --summary mods/com.acme.app.jar
```

Compare the modules referenced by bytecode against the modules actually in the graph.

**Step 3: locate the class creating the dependency**

```bash
jdeps -verbose:class --module-path mods mods/com.acme.app.jar
```

Use the output to identify the source and target classes.

**Step 4: check for missing dependencies**

```bash
jdeps --missing-deps --module-path mods mods/com.acme.app.jar
```

**Step 5: inspect descriptors**

```bash
jdeps --module-path mods --check com.acme.app
jar --describe-module --file mods/com.acme.api.jar
```

Match dependencies against `requires`, packages needed by consumers against `exports`, and service types against `uses`/`provides`.

## 11. What jdeps cannot conclude

`jdeps` is static analysis. It does not execute the application and cannot always detect:

- Classes loaded via `Class.forName` with names read from config files or databases.
- Plugins discovered dynamically in directories outside the initial module path.
- Service providers discovered via `ServiceLoader` when the service relationship cannot be inferred from bytecode.
- Dependencies appearing only in an unanalyzed execution path or runtime data.
- Behavior of custom class loaders, instrumentation, or frameworks.

Similarly, `--show-module-resolution` describes module resolution only for a specific launch. It does not list every loaded class, every executed method, or every latent dependency of all other configurations.

Therefore, results from both tools should be combined with module descriptors, runtime configurations, integration tests, and actual error logs.

## 12. Quick reference table

| Goal | Command |
|---|---|
| View module graph at launch | `java --show-module-resolution ...` |
| View dependency overview | `jdeps --summary app.jar` |
| List module dependencies | `jdeps --list-deps app.jar` |
| Print comma-separated module dependencies | `jdeps --print-module-deps app.jar` |
| View dependencies by class | `jdeps -verbose:class app.jar` |
| View missing dependencies | `jdeps --missing-deps app.jar` |
| Check module descriptor | `jdeps --check module.name` |
| Inspect JAR descriptor and packages | `jar --describe-module --file app.jar` |

When running commands that need to resolve dependencies, add `--module-path mods` pointing to the directory containing the relevant modules.

## Key takeaways

- `--show-module-resolution` shows the roots, dependencies, and service bindings of a launch.
- `requires` lines represent module dependencies; `binds` lines represent providers added via service binding.
- `jdeps` analyzes static dependencies from class files/JARs; `--summary`, `--list-deps`, `--print-module-deps`, and `-verbose:class` provide varying levels of detail.
- `--missing-deps` helps find unresolved class references within the analysis scope.
- `jdeps --check` helps compare descriptors against static dependencies, yet does not replace module design decisions.
- Both tools complement each other; also check reflection, ServiceLoader, dynamic plugins, and runtime tests.