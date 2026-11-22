# --limit-modules: Limiting the Module Universe

## 1. Meaning of --limit-modules

When starting a modular application, Java must determine which modules can be seen and included in the module resolution process. The set of modules that the module system can observe is called the **universe of observable modules**.

The runtime option `--limit-modules` limits this universe. It accepts a list of module names and narrows the set of modules the resolver can consider down to:

- The modules listed directly.
- The modules required by those modules, following the `requires` dependency chain (including transitive dependencies).

Modules outside the limited set will no longer be observable during that run. Therefore, if a root module or dependency needs a module that was excluded from the universe, the resolution process can fail with a module-not-found error.

Important point: `--limit-modules` **limits the set of modules that can be seen**, not the list of modules the application will definitely instantiate. Which modules are actually resolved still depends on the root modules, `requires` directives, service binding, and other launcher options.

## 2. What Does the Module Universe Include?

Normally, Java can observe the system modules of the runtime image and the application modules found on the module path. When using `--limit-modules`, the universe is narrowed to the selected list along with its dependency closure.

Suppose there are modules:

```text
com.acme.app
  requires com.acme.api
  requires java.logging

com.acme.api
  requires java.base

com.acme.provider.json
  requires com.acme.api
  provides com.acme.spi.Formatter with ...
```

If limited by:

```bash
--limit-modules com.acme.app
```

then the universe will include `com.acme.app` and the modules needed along its `requires` dependencies, such as `com.acme.api`, `java.logging`, and `java.base`.

Module `com.acme.provider.json` does not automatically belong to the closure merely because it declares `provides` for a service. If the application needs this provider via service binding, you must ensure the provider remains in the observable universe. You can add it to the list:

```bash
--limit-modules com.acme.app,com.acme.provider.json
```

Limiting modules does not alter JAR contents, does not modify `module-info.java`, and does not delete modules from the module path directory. It affects only the module universe in the configured run.

## 3. Syntax on the Java Launcher

Syntax:

```bash
java --limit-modules module-name[,module-name...] ...
```

Example:

```bash
java --limit-modules java.base,java.logging \
  -m com.acme.app/com.acme.app.Main
```

In a real modular application, you must ensure the root module and all required dependencies are in the observable set. If `com.acme.app` needs `com.acme.api`, but the limit list does not contain app or a module whose dependency closure leads to app, the app module may no longer be observable.

A complete example with a module path:

```bash
java --module-path mods \
  --limit-modules com.acme.app \
  -m com.acme.app/com.acme.app.Main
```

Here:

- `--module-path mods` points to where the application modules are located.
- `--limit-modules com.acme.app` limits the universe to app and its dependency closure.
- `-m com.acme.app/com.acme.app.Main` selects the module and main class to run.

If the application uses a provider discovered only via SPI, consider including the provider module in the limit list:

```bash
java --module-path mods \
  --limit-modules com.acme.app,com.acme.provider.json \
  -m com.acme.app/com.acme.app.Main
```

Module names must be actual module names, not package names or class names. You can inspect module names in a JAR using `jar --describe-module`.

## 4. Distinguishing --limit-modules from --add-modules

The two options have different purposes:

| Option | Role |
|---|---|
| `--limit-modules` | Limits the universe of observable and resolvable modules |
| `--add-modules` | Adds the specified modules to the set of root modules to resolve |
| `--module-path` | Indicates where to find application modules |
| `--show-module-resolution` | Prints information about modules resolved at launch |

Example:

```bash
java --module-path mods \
  --add-modules java.sql \
  -m com.acme.app/com.acme.app.Main
```

`--add-modules java.sql` requests adding `java.sql` as a root module. It does not limit the universe of observable modules.

Conversely:

```bash
java --module-path mods \
  --limit-modules com.acme.app,java.sql \
  -m com.acme.app/com.acme.app.Main
```

`--limit-modules` only narrows the universe. It does not mean all modules in the list automatically become root modules. The application root is still selected via `-m`, `--module`, or the corresponding launch mechanism.

Both can be combined:

```bash
java --module-path mods \
  --limit-modules com.acme.app,java.sql \
  --add-modules java.sql \
  -m com.acme.app/com.acme.app.Main
```

In this example, `java.sql` is both within the allowed observable universe and added as a root module. When combining them, every module requested as a root must lie within the limited universe.

## 5. Impact on Module Resolution

Module resolution starts from root modules and follows `requires` dependencies. `--limit-modules` changes the input set of modules that the resolver can consider.

Suppose an application has the graph:

```text
com.acme.app
   |
   +-- requires com.acme.api
   |       |
   |       +-- requires java.base
   |
   +-- requires java.logging
```

If the universe contains `com.acme.app`, its required dependencies are also in the closure and the resolver can locate them, provided the corresponding modules are available in valid search sources.

If `com.acme.api` cannot be found in the universe or in valid module sources, resolution cannot complete. The error message usually indicates which module is missing; check both the module name and the limit list.

`--limit-modules` does not automatically fix missing dependencies, does not turn `requires` into optional, and does not export packages. It only determines which modules can be seen during the resolution process.

## 6. Impact on ServiceLoader and Provider Modules

In an SPI architecture, a consumer typically declares:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
```

A provider declares:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

When using service binding, the module system can consider only provider modules that it can observe. If `--limit-modules` excludes the provider from the universe, that provider cannot be automatically discovered and brought into the graph merely because it has a `provides` directive.

If the application needs a specific provider, add the provider module to the limit set:

```bash
java --module-path mods \
  --limit-modules com.acme.app,com.acme.provider.json \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

After launch, `ServiceLoader` can find only matching providers in the layer it is asked to search. Therefore, distinguish:

1. Is the provider in the observable module universe?
2. Was the provider brought into the configuration and layer by resolution/service binding?
3. Is the consumer searching for the provider in the right layer using `ServiceLoader`?

A provider sitting on disk but restricted from the universe cannot be automatically discovered by ServiceLoader from that layer.

## 7. Observing the Module Universe and Resolution

You can use `--list-modules` to view the list of modules the runtime can observe in the launcher configuration:

```bash
java --limit-modules java.base,java.logging --list-modules
```

You can use `--show-module-resolution` when running the application to observe which modules are resolved:

```bash
java --module-path mods \
  --limit-modules com.acme.app \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

To inspect a module's descriptor:

```bash
jar --describe-module --file mods/com.acme.api.jar
```

If you do not know the module name derived from a JAR, this command helps confirm the module name and declared directives. For a module already in the runtime image, you can use:

```bash
java --describe-module java.logging
```

When debugging, compare the list of observable modules, the modules actually resolved, and the modules added as roots. These three sets are related, not synonymous.

## 8. Common Errors

| Symptom | Cause to Check |
|---|---|
| `FindException` or module-not-found message | A required module was excluded from the universe, the module name is wrong, or it is absent from the module path |
| Root module not found | The `--limit-modules` list does not include the root module and no listed module requires it |
| Application missing SPI provider | The provider is not in the universe or was not brought into the layer |
| Added `--add-modules` but still reports module not found | The module was added as a root yet is not observable within the limited set |
| Application works with full configuration but fails when limit is enabled | There is an indirect dependency or provider not accounted for by the limit list |
| Module list differs from expectations | Confusing the observable universe with the actually resolved graph; use both `--list-modules` and `--show-module-resolution` |

When fixing, do not indiscriminately add all modules. Identify the missing module, check whether it is a required dependency, an SPI provider, or an intentional root module, and update the limit set according to actual needs.

## 9. When Should --limit-modules Be Used?

This option is useful when:

- You want to test the application with a small, controlled module universe.
- You want to detect dependencies inadvertently relying on modules outside the expected set.
- You want to reproduce a restricted runtime environment to verify application independence.
- You want to verify that provider modules and dependencies are explicitly declared in the architecture.

Do not treat `--limit-modules` as a way to package an optimized runtime or as a replacement for security checks. It does not remove modules from the JDK, does not alter bytecode, does not restrict file/network access, and does not guarantee the application will not use out-of-list APIs through other mechanisms.

If the goal is to create a small runtime image containing only the modules needed for deployment, consider `jlink`. `--limit-modules` is a runtime universe-limiting option; `jlink` builds a custom runtime image at build time.

## 10. Pre-Release Checklist

- Confirm the root module is inside the limited universe.
- Confirm all required `requires` dependencies can be found.
- Check whether SPI provider modules need to be listed separately.
- If using `--add-modules`, ensure the added roots are also observable.
- Run with `--show-module-resolution` to inspect the actual graph.
- Run integration tests with the exact `--limit-modules` set intended for production.
- Record the limit list alongside the launch configuration so deployment is reproducible.

## Key Takeaways

- `--limit-modules` narrows the observable universe to the listed modules and their `requires` dependencies.
- It does not automatically add every module in the list as a root; `--add-modules` handles adding root modules.
- Modules excluded from the universe cannot be used by the resolver during that run.
- SPI providers must also lie within the observable module scope for service binding to find them.
- Use `--list-modules` and `--show-module-resolution` to inspect the universe and the graph.
- To create a small runtime image, consider `jlink`; `--limit-modules` only limits the universe at runtime.
