# java --show-module-resolution

When running a modular application, the JVM must resolve a set of modules before launching the main class. This process determines the root modules, the dependencies declared via `requires`, the location where each module is found, and the provider modules added through service binding.

The `java --show-module-resolution` option instructs the Java launcher to print information about the resolution process during startup. This is a useful tool when an application runs on one machine but fails on another, when the module path contains multiple library versions, or when a service provider unexpectedly appears in or disappears from the runtime graph.

This lesson uses JDK 21 and an application with a module named `com.acme.app`. Paths and module names in the sample output may vary depending on the operating system, JDK, and packaging.

## 1. Basic Syntax

General syntax:

~~~bash
java --show-module-resolution --module-path <module-path> --module <module-name>/<main-class>
~~~

Options:

- `--show-module-resolution`: prints module resolution information when the application starts.
- `--module-path` or `-p`: specifies directories or JAR files containing named modules.
- `--module` or `-m`: specifies the module containing the application; may include the main class after a slash.
- `--add-modules`: adds root modules in addition to the root selected by the launcher based on how the application is started.
- `--limit-modules`: limits the set of observable modules during resolution, which is useful for certain runtime configurations but can cause dependencies to no longer be found.

Example:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Short form:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

In this example, `com.acme.app` is the root module being launched. The Java launcher locates the module in `mods`, resolves its dependencies, builds a configuration, and then runs `com.acme.app.Main`.

If the module descriptor declares a main class, you can launch the module without writing the class after the slash. However, specifying `module/main-class` explicitly makes the command easier to read and avoids confusion when learning or debugging.

## 2. Reading Output: root and requires

Suppose the application has the following modules:

~~~text
mods/
├── com.acme.api/
│   └── module-info.class
└── com.acme.app/
    └── module-info.class
~~~

Application descriptor:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

API descriptor:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

A condensed output might look like:

~~~text
root com.acme.app file:///project/mods/com.acme.app/
com.acme.app requires com.acme.api file:///project/mods/com.acme.api/
com.acme.app requires java.base jrt:/java.base
com.acme.api requires java.base jrt:/java.base
~~~

How to read it:

- `root` indicates which module was selected as the starting point of the configuration.
- `requires` indicates which module needs another module according to its descriptor.
- The path after the module name indicates where the module was found.
- `jrt:/...` is a URI referring to a module located in the JDK's runtime image.
- `file:/...` or a similar file URI typically indicates a module found on the module path.

In this graph, `com.acme.app` is the root. It requires `com.acme.api`; both modules implicitly depend on `java.base`. Thus, even though the application only declares one direct dependency, the graph also includes foundational dependencies resolved from descriptors.

Line labels and ordering in the output should not be treated as a stable interface for automated parsing. Read them as diagnostic information for humans; if automated processing is needed, use the Java Module API instead of parsing console text.

## 3. How Are Root Modules Selected?

Root modules are the starting point of the resolution process. The root set directly affects the final graph.

When running:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

the `com.acme.app` module is selected as a root.

You can add another root:

~~~bash
java --show-module-resolution   --module-path mods   --add-modules com.acme.tools   --module com.acme.app/com.acme.app.Main
~~~

Now `com.acme.tools` is also included in the root set. If that module has its own dependencies, those dependencies can appear in the output even though `com.acme.app` does not directly require `com.acme.tools`.

Some special values of `--add-modules`:

- `ALL-MODULE-PATH`: selects all observable modules on the module path as roots.
- `ALL-SYSTEM`: selects all observable system modules in the runtime image.
- Specific module name: adds that module to the root set.

Do not use `ALL-MODULE-PATH` merely to "fix" missing dependency errors without finding the root cause. It can enlarge the graph significantly, obscure the application's actual dependencies, and cause the runtime to include unnecessary modules.

## 4. Reading Module Locations in the Output

Module locations help identify which module the launcher is using when multiple sources exist:

| Location Pattern | Common Meaning |
|---|---|
| `jrt:/java.base` | Module located in the JDK runtime image |
| `file:/.../mods/com.acme.api/` | Exploded module found on the module path |
| `file:/.../lib/com.acme.api.jar` | Modular JAR or JAR recognized as a module |
| `jrt:/java.sql` | System module `java.sql` from the runtime image |

If you have two JARs with the same name in two different directories, the output helps determine which one was selected. Compare that path against your module path configuration and the artifacts produced by your build tool.

Do not confuse module locations with source code locations. The Java launcher resolves packaged or compiled modules; it does not use `.java` source paths to run the application.

## 5. Service Binding and `binds` Lines

In addition to `requires` dependencies, the module graph can be expanded via service binding.

The consumer declares the service:

~~~java
module com.acme.app {
    requires com.acme.api;
    uses com.acme.api.Codec;
}
~~~

The provider declares the implementation:

~~~java
module com.acme.codec.json {
    requires com.acme.api;

    provides com.acme.api.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

When the configuration performs service binding, matching providers can be added if the provider module is in the set of observable modules. Resolution output can show this relationship using a `binds` line, as illustrated below:

~~~text
root com.acme.app file:///project/mods/com.acme.app/
com.acme.app requires com.acme.api file:///project/mods/com.acme.api/
com.acme.app binds com.acme.codec.json file:///project/mods/com.acme.codec.json/
com.acme.codec.json requires com.acme.api file:///project/mods/com.acme.api/
~~~

The `binds` line helps identify providers added due to service binding. A provider module can pull in its own dependencies; if the provider uses another service, binding can continue expanding the graph.

Several important points:

- The consumer must be in the graph and declare `uses` for the service being looked up.
- The provider must declare `provides ... with ...` for the matching service type.
- The provider must be observable via the module finder/module path and not excluded from the resolved module set.
- If a provider is selected as a root or required via `requires`, it still appears even without needing service binding.
- Multiple providers can be added together for the same service. Service binding is not a mechanism for picking a single implementation.

Exact output depends on the JDK version and the graph. If there is no `binds` line, do not immediately conclude that the provider descriptor is wrong; check the root set, service type, module path, and resolution limits.

## 6. Comparing Root Sets and Module Graphs

To understand why a module appears, run the same application with different root sets.

Application root only:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

Adding a module as a root:

~~~bash
java --show-module-resolution   -p mods   --add-modules com.acme.tools   -m com.acme.app/com.acme.app.Main
~~~

Putting all modules on the module path into the root set:

~~~bash
java --show-module-resolution   -p mods   --add-modules ALL-MODULE-PATH   -m com.acme.app/com.acme.app.Main
~~~

Compare the outputs:

1. Record the `root` lines.
2. Find the `requires` lines to identify regular dependencies.
3. Find the `binds` lines if service binding added providers.
4. Compare module locations to see whether a module comes from the runtime image or the module path.
5. For each module that only appears in the second run, determine whether it was added by the new root, a dependency of that root, or service binding.

This approach is useful when a module "unexpectedly" shows up in an application. Do not merely compare total module counts; trace the specific path that caused the module to be resolved.

## 7. Combining with Other Diagnostic Tools

`--show-module-resolution` focuses on the module graph. You can combine it with the following commands to check other aspects.

### Listing Observable Modules

~~~bash
java --module-path mods --list-modules
~~~

This command lists modules observable by the runtime in the runtime image and module path. That list does not mean all of those modules were resolved into the application's graph.

### Describing a Module's Descriptor

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

Use this command to view `requires`, `exports`, `opens`, `uses`, and `provides` of a module. It answers what a module declares, whereas `--show-module-resolution` helps show which modules are actually resolved when running the application.

### Viewing Class Loading

~~~bash
java -Xlog:class+load=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

If the error involves class loading, the classpath, or where a class is loaded from, class loading logs are more suitable. Module resolution does not log individual loaded classes.

### Checking Static Dependencies with jdeps

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

`jdeps` assists in checking module dependencies and certain issues related to module descriptors. It provides supplemental static analysis information; it does not replace observing the graph when the launcher runs.

## 8. Distinguishing the java Launcher from jlink

Both tools work with the module graph, but serve different points in time:

| Tool | Timing | Purpose |
|---|---|---|
| `java --show-module-resolution` | At launch time | Observe modules resolved for an application run |
| `jlink` | When creating a runtime image | Link a set of modules into a deployable runtime |
| `jlink --bind-services` | When creating a runtime image | Add service provider modules into the linked graph |

Example:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --bind-services   --output runtime-app
~~~

Then observe the runtime image:

~~~bash
runtime-app/bin/java   --show-module-resolution   --module com.acme.app/com.acme.app.Main
~~~

In the first step, `jlink --bind-services` affects which modules are packaged into the image. In the later step, `java --show-module-resolution` shows the graph resolved by the launcher when the application starts on that runtime. The two outputs belong to two different stages, so they should not be treated as the same report.

## 9. Limitations of --show-module-resolution

This option is very useful, but it does not answer every question about an application:

- It shows the module graph, not every class that has been loaded.
- It does not prove a provider has been instantiated or a provider's method has been invoked.
- It does not show the business processing order of providers in the application.
- It does not fully display all package access rules, reflection rules, or runtime errors occurring after `main` starts.
- The output is diagnostic text; you should not rely on line ordering or parse it as a stable machine-readable format.

If the application fails to start, combine resolution information with the full exception, the descriptors of the involved modules, the module path, and class loading logs. If the application starts but cannot find a service, check `uses`, `provides`, provider visibility, and how configurations are created.

## 10. Practical Debugging Workflow

When a module or provider does not appear as expected, you can follow this order:

1. Identify the main module and the actual root set from the `java` command.
2. Re-run with `--show-module-resolution` to record the roots and `requires` edges.
3. Use `--describe-module` on the consumer to verify `requires` and `uses`.
4. Use `--describe-module` on the provider to verify `provides` and its dependencies.
5. Use `--list-modules` or inspect the module path to confirm the provider is observable.
6. Check whether `--limit-modules` or any module path setting excludes the provider from the resolved set.
7. If using a runtime image, check how the image was built and whether `jlink --bind-services` was enabled.
8. Compare outputs after each small change to pinpoint the exact root, dependency, or service binding that alters the graph.

Do not add all modules to the root set just to make an error disappear. That can mask the underlying cause and create a runtime graph larger than necessary.

## 11. Exercises

1. Create modules `com.acme.api`, `com.acme.app`, and `com.acme.codec.json` with `requires`, `uses`, and `provides` descriptors as shown in the examples.
2. Place the compiled modules into the `mods` directory.
3. Run `java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main` and record the root, requires, binds, and module locations.
4. Re-run with `--add-modules com.acme.codec.json`. Determine whether the provider appears due to the root or service binding.
5. Run with `--add-modules ALL-MODULE-PATH`. Compare the root count and graph with the previous two runs.
6. Use `java --describe-module` to read the consumer/provider descriptors, then compare them with the resolution output.
7. Create a runtime image with `jlink --bind-services`, run the application on that image with `--show-module-resolution`, and compare the link-time graph with the launch-time graph.

When reading `java --show-module-resolution`, distinguish modules selected as roots, dependencies via `requires`, providers added via service binding, and the actual location of each module. With that information, you can explain why the graph has its current composition, spot incorrect module paths, and control your modular runtime on a sound basis.
