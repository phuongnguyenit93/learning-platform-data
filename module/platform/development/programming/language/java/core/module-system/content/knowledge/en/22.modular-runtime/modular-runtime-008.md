# Runtime Errors from Unresolved Modules

## 1. Module Resolution Happens Before Running the Application

For an application using the Java Platform Module System (JPMS), the JVM must build the **module graph** before loading the main class and executing the program. The graph starts from the root modules, and then the resolver finds the modules they require directly or indirectly via **requires** directives.

A modular launch command typically looks like:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Where:

- **--module-path mods** specifies where Java looks for named modules and automatic modules.
- **-m com.acme.app/com.acme.app.Main** requests running the main class belonging to module **com.acme.app**.
- Module descriptors and dependencies of the root module are checked before the main class begins running.

If a required module is not found, the module graph has a conflict, or a module cannot be resolved, the program stops before entering `main`. This is a category of errors that must be resolved in the module path configuration and module descriptors.

## 2. Minimal Modular Application Example

Suppose the application has two modules:

~~~text
src/
├── com.acme.api/
│   ├── module-info.java
│   └── com/acme/api/Message.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

API module:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

API class:

~~~java
package com.acme.api;

public record Message(String value) {
}
~~~

Application module:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.api.Message;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("JPMS is running");
        System.out.println(message.value());
    }
}
~~~

Compile the modules from the source tree:

~~~bash
javac --module-source-path src \
  -d mods \
  -m com.acme.api,com.acme.app
~~~

Run the application module:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
JPMS is running
~~~

If the launch command cannot find `com.acme.api`, check the module path and module name before changing source code.

## 3. Classifying Errors by Message

The following errors commonly occur when the module graph cannot be built or when the runtime moves into the class loading phase:

| Symptom | Common Meaning | Where to Check |
|---|---|---|
| java.lang.module.FindException: Module X not found | The resolver cannot find the required module X | Module path, module name, JAR/module directory location |
| FindException: Error reading module or descriptor read error | Corrupted artifact, invalid descriptor, or unreadable | JAR, module-info.class, artifact format |
| ResolutionException | The module graph is inconsistent or unresolvable | Dependencies, package overlap, versions, and module boundaries |
| LayerInstantiationException | Cannot create a layer from the resolved configuration | Module graph, package/class loader constraints, and layer creation |
| Could not find or load main class | The module may have been found, but the main class is wrong or missing from the artifact | Main class name, package, JAR contents, and `-m` command |
| ClassNotFoundException or NoClassDefFoundError | Class loading failure later or during execution | Whether the class is in the artifact, dependencies/class loader |
| IllegalAccessError | Runtime does not allow accessing a type/member across a module boundary | `exports`, readability, and whether runtime artifacts match compile time |
| InaccessibleObjectException | Deep reflective access blocked by module encapsulation | `opens` and how the framework accesses the type |

Do not lump every runtime error together as "unresolved module". For example, `FindException` happens while finding or resolving modules, whereas `ClassNotFoundException` can occur after the module graph has already been built successfully.

## 4. Common Error: Missing Module on the Module Path

Suppose `com.acme.app` declares:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

However, when running, the command only puts the application on the module path:

~~~bash
java --module-path app.jar \
  -m com.acme.app/com.acme.app.Main
~~~

If `com.acme.api` resides in `api.jar` and is not placed on the module path, the resolver may report:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.acme.api not found,
required by com.acme.app
~~~

The fix is to provide both artifacts:

~~~bash
java --module-path "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

On Windows, the separator between module path elements is a semicolon:

~~~powershell
java --module-path "app.jar;api.jar" -m com.acme.app/com.acme.app.Main
~~~

If the modules are already placed in the same `mods` directory, you can use:

~~~bash
java --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Make sure `mods` actually contains modular JARs or exploded module directories. Simply having a JAR on disk does not make the JVM find it automatically.

## 5. Placing a Dependency on the Classpath by Mistake

A common migration error is having a dependency on the classpath while the application module declares `requires` on it.

Example:

~~~bash
java -cp "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

The classpath serves the classpath/unnamed module. It does not replace the module path to satisfy a named module's `requires com.acme.api` dependency.

For a modular application, place dependencies on the module path:

~~~bash
java --module-path "app.jar:api.jar" \
  -m com.acme.app/com.acme.app.Main
~~~

If a dependency is a JAR without `module-info.class`, placing it on the module path allows it to be treated as an **automatic module**. The module name is usually derived from the JAR filename unless the JAR declares `Automatic-Module-Name`. Check the actual name instead of guessing from the filename.

## 6. Module Name Does Not Match Filename or Package Name

The module name is declared in the descriptor:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

The consumer must use that exact name:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

A module name is not a package name and does not necessarily match the literal JAR filename. For an explicit module, the descriptor is the source defining the module name. For an automatic module, you can inspect the derived name or the name declared in the manifest.

Use the following command to view a JAR's descriptor:

~~~bash
jar --describe-module --file mods/acme-api.jar
~~~

If the displayed module name differs from the name in `requires`, fix the dependency or packaging configuration to align them.

## 7. Inspecting the Module Path and Observable Modules

Several useful commands:

List modules recognized by the runtime:

~~~bash
java --list-modules --module-path mods
~~~

View the descriptor of a JAR:

~~~bash
jar --describe-module --file mods/acme-api.jar
~~~

Validate modules on the module path:

~~~bash
java --validate-modules \
  --module-path mods \
  --add-modules ALL-MODULE-PATH
~~~

Check module dependencies:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

These commands serve different purposes: listing modules, viewing descriptors, checking the module graph, and analyzing dependencies. One command succeeding does not guarantee every class will load at runtime, so integration tests on the module path are still necessary.

## 8. Enabling Detailed Output for the Resolution Process

When running the application with the Java launcher, add **--show-module-resolution** to see the resolved modules:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

The displayed information helps identify:

- Which root modules were requested.
- Which modules were found and resolved.
- Which dependencies were included in the graph.
- Which service bindings may have brought provider modules into the graph.

If the command stops before printing application output, read the message right after the resolution output to locate the missing module or conflict.

You can increase class-loading diagnostics with:

~~~bash
java -Xlog:class+load=info \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
~~~

Class loading logs help investigate errors occurring after the module graph has been constructed, such as a missing class or a class loaded from an unexpected source. They do not replace `--show-module-resolution`.

## 9. Options That Can Alter the Module Graph

When reading a launch command, pay attention to the following options:

- **--module-path**: specifies which modules can be discovered.
- **--add-modules**: adds root modules beyond the default root. You can specify module names or `ALL-MODULE-PATH`.
- **--limit-modules**: restricts the set of observable modules; a dependency that could otherwise be found may become unavailable.
- **--upgrade-module-path**: provides replacement modules for certain system modules under upgrade module path rules.
- **--add-reads**: adds readability edges at runtime.
- **--add-exports**: opens access to a package's public API for target modules.
- **--add-opens**: allows deep reflective access into a package at runtime.

`--add-reads`, `--add-exports`, and `--add-opens` change access boundaries; they do not make a missing JAR magically appear on the module path. If the message is `Module X not found`, fix module discovery first.

`--add-modules` also cannot locate modules outside the sources observable by the module finder/runtime. It asks the resolver to include a module that is already discoverable into the graph.

## 10. Runtime Errors Are Not Always Resolution Errors

After the module graph resolves successfully, the application can still fail in subsequent phases:

- The main class does not exist or the class name in `-m` is wrong.
- A dependency class is missing from the JAR or not found by the class loader.
- Runtime artifacts are older than or different from the artifacts used at compile time.
- A public package is not exported or a module does not read a dependency as expected.
- A framework uses deep reflection, but the package has not been opened with `opens`.
- Bytecode was compiled with a newer JDK than the running runtime, leading to `UnsupportedClassVersionError`.

Therefore, when you see an error, determine whether it happens before or after the module graph is built. Do not add `--add-opens` or change `requires` if the actual error is a misspelled main class name or a missing class in the JAR.

## 11. Practical Diagnostic Workflow

When receiving a module-related runtime error, proceed step by step:

1. **Read the first exception.** Distinguish `FindException`, `ResolutionException`, layer creation errors, and class loading errors.
2. **Verify the main module.** Check the module name in the `-m` command and the artifact's module descriptor.
3. **Check the module path.** Confirm the directory/JAR containing the root module and all `requires` dependencies are provided.
4. **Verify the module name.** Use `jar --describe-module` to inspect the actual name.
5. **Print module resolution.** Re-run with `--show-module-resolution` to inspect the graph.
6. **Validate the graph.** Use `java --validate-modules` and `jdeps --check` as needed.
7. **Check class loading.** If resolution succeeded, move on to checking JAR contents, classpath/module path, class loaders, `exports`/`opens`, and JDK version.
8. **Run integration tests on the module path.** Do not test only on the classpath if the final artifacts are released as named modules.

## 12. Release Checklist Example

A pipeline can run the following commands on the final staging directory:

~~~bash
jar --describe-module --file dist/acme-app.jar

java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH

java --show-module-resolution \
  --module-path dist \
  -m com.acme.app/com.acme.app.Main
~~~

In CI, configure these steps as required checks. If a module is not found or the graph is invalid, the pipeline should stop before publishing artifacts.

For the actual runtime environment, verify the exact set of deployed JARs, actual JVM options, environment variables, and startup scripts. A local launch command with a different module path from production can mask packaging errors.

## Takeaways

- The module graph is resolved before the main class runs.
- `FindException: Module X not found` usually points to the module path, module name, or search sources.
- `requires` dependencies of a named module must be discoverable on the module path or in an appropriate parent configuration.
- `--show-module-resolution`, `--list-modules`, `jar --describe-module`, `java --validate-modules`, and `jdeps --check` assist diagnostics from different angles.
- `--add-modules` selects additional observable root modules; it does not fix an incorrect module path.
- Distinguish resolution errors from main class, class loading, access, reflection, and bytecode compatibility errors.
