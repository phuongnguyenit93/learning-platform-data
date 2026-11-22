# Root modules and the initial module set

## 1. The module path is not synonymous with the loaded module set

When running a JPMS application, the module path directory may contain many modular JARs. However, the presence of a JAR on the module path only means the module system can find it. That module is not necessarily part of the running module configuration.

Three concepts should be distinguished:

- **Observable module**: a module that the active `ModuleFinder` instances can locate, such as modules on the system module path or application module path.
- **Root module**: a module selected as a starting point for the resolution process.
- **Resolved module**: a module that has been included in the `Configuration` after the module system resolves the roots and their related dependencies.

Module resolution starts from a set of root modules. From that initial set, the module system follows `requires` directives to find and include the necessary dependencies in the configuration. Therefore, not every module present on disk is automatically resolved.

For example, the module path contains:

~~~text
mods/
  com.acme.app.jar
  com.acme.api.jar
  com.acme.impl.jar
  com.acme.tools.jar
~~~

If the application only declares:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

then `com.acme.app` and its dependency `com.acme.api` are placed into the graph along with their subsequent dependencies. `com.acme.impl` and `com.acme.tools` do not automatically become resolved modules just because they reside in the `mods` directory.

## 2. A root module is the starting point of module resolution

A root module is a module from which the resolution process begins. It is not a special kind of module, nor is it a parent-module concept in a directory structure.

For an application launched by module name:

~~~bash
java --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

the module `com.acme.app` is the main root module of the application. The module system reads its descriptor, locates the required modules, and then continues processing the dependencies of those modules.

Additional root modules can be added using the `--add-modules` option:

~~~bash
java --module-path mods \
  --add-modules com.acme.plugin \
  --module com.acme.app/com.acme.app.Main
~~~

In this example, both `com.acme.app` and `com.acme.plugin` are starting points of the resolution process. The plugin is included in the configuration even though the main application does not declare `requires com.acme.plugin`.

This approach is useful when an application needs a module to be loaded for use via reflection, a custom registry, or another plugin mechanism where the dependency is not expressed via a direct `requires`.

## 3. How is the initial module set formed?

The initial root set depends on how the application is launched and what options the runner provides.

### Launching a modular application

When using `-m` or `--module` to specify the main module, the specified module is a root. Additional modules can be included with `--add-modules`.

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

In this case, there is no need to put every module in `mods` into the root set. Declared dependencies will be resolved starting from the main module.

### Launching an application on the classpath

When running a traditional application via the classpath, application code belongs to the unnamed module. So that classpath code can use appropriate module APIs, the launcher by default selects as roots the observable modules that export at least one package unconditionally (not restricted by a qualified export).

This means a module that only exports packages to a specific module is not automatically selected as a default root just because it is present on the module path.

Necessary modules can be added using `--add-modules` if the classpath application needs to access them.

### java.base is always a root

`java.base` is the foundational module containing core APIs such as `java.lang`, `java.util`, and many fundamental types. Every named module reads `java.base`, and this module is always considered a root during resolution. There is no need to declare `requires java.base` in individual descriptors.

## 4. requires expands the resolved module set

Suppose there are three modules:

~~~text
com.acme.app
  requires com.acme.service

com.acme.service
  requires com.acme.domain

com.acme.domain
  (no application dependencies)
~~~

When `com.acme.app` is the root, the module system resolves in a chain:

1. Start with the root `com.acme.app`.
2. Read the descriptor and locate `com.acme.service`.
3. Include `com.acme.service` in the graph, then read its descriptor.
4. Locate and include `com.acme.domain` in the graph.
5. Continue until no required dependencies remain to be resolved.

The result is a resolved module set containing app, service, domain, and the necessary foundational dependencies.

A `requires` edge creates a direct dependency and readability from the declaring module to the required module. `requires transitive` further allows modules that read the intermediate module to also read the dependency passed through the API.

For example:

~~~java
module com.acme.service {
    requires transitive com.acme.domain;
}
~~~

If app only declares `requires com.acme.service`, app has readability to both service and domain. However, `requires transitive` is not a new root module; it affects the readability of modules that depend on service. Domain is still included in the configuration through service's dependency.

## 5. Optional modules and requires static

A module can declare an optional runtime dependency:

~~~java
module com.acme.reporting {
    requires static com.acme.pdf.api;
}
~~~

`requires static` requires the module to be present at compile time. At runtime, if the optional module is not provided, the module system can proceed without resolving that dependency. If the module is present and found, it can be resolved as a dependency.

Keep in mind:

- `requires static` does not automatically add an unrelated module to the root set.
- If the optional module is absent, running code must not assume its classes always exist.
- If the feature actually needs that module, the application must ensure the module is provided and resolved in the corresponding configuration.
- If the dependency is only loaded by class name or reflection, check the root set and runtime configuration instead of relying solely on the JAR sitting in a directory.

## 6. Using --add-modules to select additional roots

The launcher option:

~~~bash
--add-modules module[,module...]
~~~

allows adding one or more modules to the root set. The modules must be observable through module finders and resolvable along with their dependencies.

Example adding two modules:

~~~bash
java --module-path mods \
  --add-modules com.acme.plugin,com.acme.metrics \
  -m com.acme.app/com.acme.app.Main
~~~

The following special names can also be used with `--add-modules`:

| Value | Meaning |
|---|---|
| `ALL-DEFAULT` | Adds all default root modules |
| `ALL-SYSTEM` | Adds all observable system modules |
| `ALL-MODULE-PATH` | Adds all modules found on the module path |

Example:

~~~bash
java --module-path mods \
  --add-modules ALL-MODULE-PATH \
  -m com.acme.app/com.acme.app.Main
~~~

This command instructs resolution to start additionally from all modules on the module path. It is useful for certain test environments or applications that need broad module discovery, but should not be used as a default for production applications if only specific plugins are needed.

When putting the entire module path into the root set, issues such as duplicate module names, split packages, or conflicting dependencies can cause resolution to fail. Selecting specific roots usually keeps the configuration easier to understand and less dependent on extraneous modules.

## 7. Distinguishing ALL-DEFAULT, ALL-SYSTEM, and ALL-MODULE-PATH

The three special values serve three different scopes:

- `ALL-DEFAULT` refers to the launcher's default root set in the current execution context.
- `ALL-SYSTEM` selects modules belonging to the system module finder, including foundational modules that are not necessarily default roots.
- `ALL-MODULE-PATH` selects modules found on the application module path.

For example, an application module may only need one advanced system module:

~~~bash
java --module-path mods \
  --add-modules jdk.crypto.ec \
  -m com.acme.app/com.acme.app.Main
~~~

If you want to add all system modules, you can use `ALL-SYSTEM`; if you want to add application-packaged modules on the module path, use `ALL-MODULE-PATH`.

Do not confuse `ALL-SYSTEM` with `ALL-MODULE-PATH`: system modules belong to the JDK, whereas the module path typically contains application modules or third-party libraries. A module residing on the module path does not become a system module just because it is present at runtime.

## 8. Service providers can expand the graph via service binding

An application can declare a service using `uses`, while a provider module registers an implementation with `provides ... with ...`.

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentProcessor;
}
~~~

~~~java
module com.acme.payment.card {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentProcessor
        with com.acme.payment.card.CardPaymentProcessor;
}
~~~

If the application wants module resolution to bind service providers, the launcher supports:

~~~bash
java --bind-services --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

With service binding, matching provider modules can be brought into the graph even if they are not direct `requires` dependencies of the root. The provider's dependencies continue to be resolved as well.

In the API for creating custom module layers, `Configuration.resolveAndBind(...)` can be used instead of `resolve(...)` when automatic provider binding is needed. If only `resolve(...)` is used, do not assume every observable provider will be added to the graph.

Service binding does not replace `uses`, `provides`, or providing modules on the module path. The consumer still needs to declare the service it uses, the provider needs to declare its implementation, and the artifact must be present in an appropriate module finder.

## 9. A module is on the module path but is not resolved

These are common causes when an application uses plugins or modules loaded by name:

- The JAR is in the directory but does not belong to the dependency closure of the roots.
- The application calls `Class.forName` with a plugin class name, but the module containing the class has not been included in the configuration.
- The consumer declares `uses`, but the provider is not bound because service binding is not enabled or the layer was created without resolve-and-bind.
- The module name passed to `--add-modules` does not match the actual module name.
- The module is excluded from the observable set by launcher configuration.

If a module is always needed, declare a `requires` dependency when it is a true dependency, or add the module to the root set with `--add-modules`. For SPI, use appropriate service binding.

## 10. --limit-modules is not the same as --add-modules

`--add-modules` adds root modules. Conversely, `--limit-modules` restricts the set of observable modules that the launcher can consider.

For example:

~~~bash
java --limit-modules java.base,java.logging \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

If the application or a dependency needs a module excluded from the observable set, resolution may fail with a missing module error.

Therefore:

- Use `--add-modules` when you need to expand the root set.
- Use `--limit-modules` when you want to narrow the set of observable modules, such as creating a smaller runtime or verifying whether a dependency is genuinely needed.
- Do not use `--limit-modules` to try to bring a plugin into the graph; this option serves the opposite purpose.

## 11. Creating a custom module configuration and layer

When an application manages plugins using a dedicated module layer, code can explicitly choose roots:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
    ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("com.acme.plugin"));

ModuleLayer layer =
    ModuleLayer.boot().defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
~~~

In this example:

- `ModuleFinder.of(Path.of("plugins"))` locates plugin modules.
- `Set.of("com.acme.plugin")` is the root set for the new configuration.
- `resolve(...)` resolves the roots and dependencies according to `requires` directives.
- `defineModulesWithOneLoader(...)` creates a new layer from the resolved configuration.

If you want service providers to be bound automatically, use the appropriate `resolveAndBind(...)` overload. After creating the layer, services can be looked up from that layer using `ServiceLoader.load(layer, PaymentProcessor.class)`.

Each module layer has its own configuration. Having a module resolved in the boot layer does not automatically mean plugins in a child layer have been created; verify the exact layer from which the application loads classes or services.

## 12. Observing the resolved module set

The following commands aid diagnostics:

~~~bash
java --list-modules
~~~

Lists the modules observable by the runtime in the launcher context.

~~~bash
java --show-module-resolution --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Displays the module resolution process, including the selected modules and processed dependency relationships.

To inspect the module name of a JAR:

~~~bash
jar --describe-module --file mods/com.acme.plugin.jar
~~~

To analyze bytecode dependencies:

~~~bash
jdeps --print-module-deps --module-path mods app.jar
~~~

When reading the output, distinguish between observable modules and modules actually resolved. A JAR appearing in the module list does not prove that module is part of the running application's graph.

## 13. A predictable root module selection workflow

For a typical modular application:

1. Identify the main module and use it as a root.
2. Declare direct dependencies using `requires` in the descriptor.
3. Only add `--add-modules` for plugins or modules that genuinely need to be present without being expressed through dependencies.
4. If using SPI, declare `uses` and `provides`, then enable service binding when the configuration requires it.
5. Avoid adding the entire module path if only a few specific modules are needed.
6. Use `--show-module-resolution` to confirm the actual graph.
7. If creating a custom layer, explicitly specify the root set and choose between `resolve` and `resolveAndBind`.

Transparent root selection helps avoid implicit reliance on modules that happen to be present in the development environment. Build, test, and production should use matching module paths and root selections.

## Conclusion

Root modules are the seed set from which JPMS begins module resolution. From the roots, the module system follows `requires` dependencies to build the resolved graph. A module merely residing on the module path is not guaranteed to be included in the graph; if the application needs a standalone module such as a plugin, select it as a root using `--add-modules` or use service binding where appropriate.

Clearly understanding observable modules, root modules, and resolved modules helps control module configurations, design plugin layers, and diagnose missing-module errors at runtime.