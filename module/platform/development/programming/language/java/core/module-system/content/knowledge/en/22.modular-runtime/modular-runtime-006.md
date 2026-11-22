# java --describe-module

`java --describe-module` is a Java launcher option used to display the description of a module and then exit. Its short option is `-d`. It is a module lookup tool in the running Java environment, useful for checking module names, dependencies, exported packages, used services, or declared providers.

Basic syntax:

~~~bash
java --describe-module module_name
~~~

Or short form:

~~~bash
java -d module_name
~~~

The command does not run the module's main class. It asks the launcher to locate the module under the current module path configuration, print the module description, and exit. Therefore, it is a quick check when a modular application fails to resolve a module as expected.

## 1. Syntax and How It Works

General form:

~~~bash
java [launcher-options] --describe-module module_name
~~~

The `module_name` parameter is the module name, for example `java.base`, `java.sql`, or `com.example.payment`. This is the module name declared in `module-info.java`, not a package name, main class name, or JAR filename.

Examples:

~~~bash
java --describe-module java.base
java -d java.sql
~~~

The two commands above describe system modules. For an application module located on the module path, also pass `--module-path`:

~~~bash
java --module-path mods --describe-module com.example.payment
~~~

If the module is located in the `plugins` directory:

~~~bash
java --module-path "mods;plugins" --describe-module com.example.payment
~~~

On Windows, semicolons separate module path elements. On Linux and macOS, use colons:

~~~bash
java --module-path "mods:plugins" --describe-module com.example.payment
~~~

The `-p` option is the short form of `--module-path`:

~~~bash
java -p mods --describe-module com.example.payment
~~~

Launcher options must be placed before `module_name`. When `--describe-module` is specified, the launcher prints the description and exits rather than continuing to look for a main class to run the application.

## 2. Reading Module Description Output

For example, an application module may be described as follows:

~~~text
com.example.payment
exports com.example.payment.api
requires java.base mandated
requires com.example.customer
uses com.example.payment.spi.PaymentProvider
provides com.example.payment.spi.PaymentProvider
    with com.example.payment.internal.DefaultPaymentProvider
~~~

Meaning of common parts:

| Output Line | Meaning |
|---|---|
| Module name on the first line | Name of the described module; may include a version if provided by the descriptor |
| exports package | Package exported by the module so other modules can access public APIs |
| exports package to ... | Qualified export: only the named modules can access the package |
| opens package | Package opened for deep reflection according to module rules |
| opens package to ... | Qualified open intended for a specific group of modules |
| requires module | Module depends on another module |
| requires ... transitive | Dependency propagated onward to modules that depend on the current module |
| requires ... static | Dependency required only at compile time |
| uses service | Module declares consumption of a service |
| provides service with provider | Module declares an implementation provided for a service |
| mandated | Dependency implicitly required by language or runtime rules, commonly seen with java.base |

The output is a summary of the module descriptor recognized by the runtime. It helps verify what metadata a module was packaged with, but does not prove the entire application can start successfully. Issues such as missing other modules, provider initialization failures, or runtime configuration errors can still occur when running the application.

## 3. Checking System Modules

The JDK provides many system modules. You can describe a module directly:

~~~bash
java --describe-module java.base
java --describe-module java.logging
java --describe-module java.sql
java --describe-module java.xml
~~~

`java.base` is the foundational module and is implicitly depended on by every module. Modules such as `java.sql` or `java.xml` provide specialized APIs.

If you do not yet know the exact names of modules observable by the runtime, use:

~~~bash
java --list-modules
~~~

This command lists observable modules and exits. You can then pick a name from the list and pass it to `--describe-module`.

To filter the list in a shell:

~~~bash
java --list-modules | grep java.sql
~~~

In PowerShell:

~~~powershell
java --list-modules | Select-String java.sql
~~~

If the command returns a module name with a version, you can use the module name before the `@` character for the `--describe-module` option.

## 4. Describing Application Modules on the Module Path

Suppose the project has packaged the `com.example.payment` module into:

~~~text
build/
|-- mods/
    |-- com.example.payment.jar
    |-- com.example.customer.jar
~~~

Inspect the module:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

The launcher searches for the module by module name in the specified locations. It does not require the JAR filename to match the module name. A JAR named `payment-library.jar` can still contain a module named `com.example.payment`.

If the output reports that the module was not found, check step by step:

1. Did you pass the right directory containing modular JARs or exploded modules?
2. Does the JAR file have a valid `module-info.class` or an appropriate `Automatic-Module-Name`?
3. Does the module name passed in match the name in the descriptor?
4. Are there duplicate modules with the same name on the module path or upgrade module path?
5. Are you running the intended JDK and the expected module path configuration?

You can use `--list-modules` with the module path to see the modules recognized by the launcher:

~~~bash
java --module-path build/mods --list-modules
~~~

Then describe the module you need to inspect:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

## 5. Combining with the Upgrade Module Path

`--upgrade-module-path` specifies where to look for replacements for upgradeable modules in the runtime image. If the application replaces an upgradeable system module, account for this path when inspecting.

Example:

~~~bash
java --upgrade-module-path upgrades \
     --module-path mods \
     --describe-module java.xml
~~~

A module found via the upgrade module path can replace the corresponding module in the runtime image according to module system rules. If the description result differs from what you expect, inspect both the upgrade module path and the module path.

Do not add an upgrade module path just to fix a module not found error. First determine whether the module is an application module or an upgradeable system module.

## 6. Distinguishing `java --describe-module` and `jar --describe-module`

The two commands have similar names but serve two different inspection points.

| Command | Input | Purpose |
|---|---|---|
| java --describe-module module_name | Module name and launcher module path configuration | Describes the module that the runtime can locate under the current configuration |
| jar --describe-module --file library.jar | Specific JAR file | Describes the module descriptor or automatic module name of the archive |

Example of inspecting a JAR directly:

~~~bash
jar --describe-module --file build/mods/payment-library.jar
~~~

Example of inspecting the same module via the module path:

~~~bash
java --module-path build/mods \
     --describe-module com.example.payment
~~~

Use `jar` when the question is: "Which module descriptor or automatic module name does this archive contain?". Use `java` when the question is: "With the current module path and JDK, how does the launcher recognize this module?".

If the JAR is a modular JAR, `jar --describe-module` can print the descriptor taken from the archive. If the JAR has no `module-info.class` but has `Automatic-Module-Name`, the tool can display the automatic module name. If there is no declared name, the automatic module name can be derived from the filename according to naming rules.

## 7. Distinguishing from Related Launcher Options

| Option | Purpose |
|---|---|
| --describe-module or -d | Prints a module's descriptor and exits |
| --list-modules | Lists observable modules and exits |
| --module-path or -p | Specifies where to locate application modules |
| --upgrade-module-path | Specifies modules that replace upgradeable system modules |
| --add-modules | Adds root modules to the set of modules to be resolved |
| --show-module-resolution | Displays information about resolved modules at startup |
| --validate-modules | Checks for module conflicts and errors across module paths |

For example, to observe the resolution process when running an application:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

To check whether the module path has conflicts or configuration errors:

~~~bash
java --module-path mods --validate-modules
~~~

These two commands answer different questions from `--describe-module`. One command describes a single module's descriptor; the others provide information about resolution or validate the module graph.

## 8. Example Diagnostic Workflow

Suppose the application reports that the `com.example.payment.api` package cannot be accessed. You can inspect using the following workflow.

**Step 1: Determine whether the module is found.**

~~~bash
java --module-path mods --list-modules
~~~

If the module does not appear, check the JAR location, archive structure, and module path.

**Step 2: Describe the module.**

~~~bash
java --module-path mods --describe-module com.example.payment
~~~

Look for the `exports com.example.payment.api` line. If the package is not exported, other modules cannot access that package's public API under standard access rules.

**Step 3: Check qualified exports.**

If the output is:

~~~text
exports com.example.payment.api to com.example.app
~~~

Only the `com.example.app` module receives access to the package via the qualified export. Another module, even if it reads `com.example.payment`, still cannot access this package.

**Step 4: Check dependencies.**

Look for `requires` lines to see whether the module declares dependencies on the required modules. Distinguish `requires`, `requires transitive`, and `requires static` because they have different impacts on resolution and readability.

**Step 5: Check the overall configuration.**

If the descriptor is correct yet the application still fails to run, use `--validate-modules` and `--show-module-resolution` at launch time to find conflicts, missing modules, or an unexpected module graph.

## 9. Limitations and Common Mistakes

- **Using a JAR name instead of a module name:** the argument to `--describe-module` is the module name, not the JAR file path.
- **Forgetting the module path:** application modules not in the runtime image must be provided via `--module-path` or an appropriate module discovery mechanism.
- **Confusing a package with a module:** a module can export multiple packages; passing a package name will not describe the module.
- **Confusing `java` with `jar`:** `java` describes a module according to the launcher configuration; `jar` inspects a specific archive.
- **Expecting the command to launch the application:** `--describe-module` prints the descriptor and exits, without calling the `main` method.
- **Assuming `exports` and `opens` are the same:** `exports` grants API access across modules; `opens` allows deep reflection according to module system rules.
- **Assuming a correct descriptor means the application will run:** the command does not verify all initialization logic or runtime behavior of the application.
- **Ignoring alternative module paths:** the upgrade module path can affect which module the runtime uses.

## 10. Takeaways

`java --describe-module module_name` is a fast way to inspect the module descriptor that the Java launcher finds in the current configuration. Use `--module-path` when describing application modules, `--list-modules` to find module names, and `--validate-modules` or `--show-module-resolution` when you need to diagnose the module graph.

When inspecting an independent archive, use `jar --describe-module --file`. When inspecting a real application, use `java --describe-module` with the same module path that the application will use. Combining these two perspectives helps distinguish JAR packaging errors from module discovery errors in the runtime configuration.

## References

- Oracle Java Launcher — The java Command: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Oracle JDK 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
