# Shrinking Runtime Images with jlink --limit-modules

## 1. Objectives

A full JDK provides many modules, but an application usually only needs a subset of them. When deploying an application on a server or container, carrying the entire JDK can make the runtime larger than necessary.

The `jlink` tool creates a **custom runtime image** consisting of the Java runtime and selected modules. The `--limit-modules` option restricts the set of modules the resolver is allowed to observe while creating the image. Combining it with `--add-modules`, we can specify the application's root modules and narrow down the candidate module set used to resolve dependencies.

Two things must be distinguished:

- `--add-modules` specifies the root modules to include in the image.
- `--limit-modules` limits the universe of observable modules used during resolution; required transitive dependencies of modules in the limited set are still taken into account.

`--limit-modules` does not simply mean copying only the listed names and dropping all dependencies. The resolver still needs the modules that the roots require directly or indirectly. If a required dependency is missing on the module path, the linking process will fail.

After this lesson, you will be able to create a runtime image for a modular application, select root modules, limit the observable module set, inspect the image, and troubleshoot errors when a required module is missing.

## 2. What Does jlink Produce?

`jlink` takes compiled modules from the module path, resolves dependencies of the root modules, and creates a runtime image that can run standalone on the corresponding platform.

An image typically has a structure like:

~~~text
runtime/
├── bin/
│   ├── java
│   └── keytool
├── conf/
├── legal/
├── lib/
└── release
~~~

The linked modules reside inside the image. Modular applications can also be packaged into the image, so at runtime there is no need to provide the application JARs again via an external module path.

Basic prerequisites:

- Use a JDK that has the `jlink` tool, not a minimal runtime image that has stripped out the linker.
- The application and its required dependencies must be valid named modules.
- The module path must contain the modules that the resolver needs to find.
- The runtime image is created for the platform corresponding to the JDK/toolchain in use; do not treat `jlink` as an arbitrary cross-compilation tool across operating systems or architectures.

## 3. Preparing a Modular Application

For example, an application has two modules:

- `com.example.api`: provides the API.
- `com.example.app`: contains the main class and uses the API.

Directory structure after compilation:

~~~text
project/
├── mods/
│   ├── com.example.api.jar
│   └── com.example.app.jar
└── runtime/
~~~

API module:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

~~~java
package com.example.api;

public final class Greeting {
    public static String message() {
        return "Hello from a custom runtime";
    }
}
~~~

Application module:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

~~~java
package com.example.app;

import com.example.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Suppose both modules have been packaged into modular JARs:

~~~text
mods/com.example.api.jar
mods/com.example.app.jar
~~~

The JAR filename may differ from the module name; the actual module name is taken from the module descriptor.

## 4. Basic jlink Syntax

General syntax:

~~~bash
jlink --module-path <module-path> --add-modules <root-modules> --output <directory>
~~~

Key options:

| Option | Role |
| --- | --- |
| `--module-path` | Where to find source modules, usually including the JDK's `jmods` directory and the directory containing the application's modular JARs. |
| `--add-modules` | Selects one or more root modules to include in the image. |
| `--limit-modules` | Restricts the observable module set during resolution. |
| `--output` | Output directory for the runtime image. |
| `--bind-services` | Links matching service provider modules along with their dependencies. |

On Linux/macOS, you can link the application as follows:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
~~~

Where:

- `$JAVA_HOME/jmods` contains JDK modules in JMOD format.
- `mods` contains the application's modular JARs.
- `com.example.app` is the root module.
- `runtime` is the generated custom runtime image.

Because `com.example.app` declares `requires com.example.api`, the resolver includes both `com.example.api` and its required dependencies in the image. `java.base` is also present because regular named modules fundamentally depend on this module.

## 5. Using --limit-modules to Narrow the Observable Module Set

Syntax:

~~~bash
jlink --module-path <module-path> --add-modules <root-modules> --limit-modules <module-list> --output <directory>
~~~

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --output runtime
~~~

Here:

- `com.example.app` is the root module being linked.
- `java.base`, `com.example.api`, and `com.example.app` are the modules listed in the observable limit.
- Required transitive dependencies of modules in this set are still considered by the resolver.
- Modules outside the limited set and not belonging to the required dependency closure will not be treated as observable modules for this link run.

In the small example, the limit list explicitly states the app, API, and platform module the application needs. For real projects, you must also consider indirectly required modules, system modules used by libraries, and service providers that need to be bound.

If `--limit-modules` excludes a module that the application truly needs, `jlink` will report a resolution error instead of silently creating an image missing dependencies.

## 6. --add-modules and --limit-modules Do Not Replace Each Other

The two options answer two different questions:

| Question | Option |
| --- | --- |
| Which modules are the roots to include in the image? | `--add-modules` |
| Which set of modules is the resolver allowed to observe? | `--limit-modules` |

Example specifying roots:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
~~~

Example specifying roots and limiting the universe:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --output runtime
~~~

Having only `--limit-modules` without selecting appropriate roots does not by itself tell the tool which application modules must be included in the image. Conversely, `--add-modules` is not a blocklist against all other modules; it selects roots, and the resolver computes the dependency closure.

## 7. Service Providers in a Runtime Image

If the application uses `ServiceLoader`, provider modules must be accounted for during packaging.

For example, the consumer declares:

~~~java
module com.example.app {
    requires com.example.api;

    uses com.example.api.GreetingService;
}
~~~

The provider declares:

~~~java
module com.example.provider {
    requires com.example.api;

    provides com.example.api.GreetingService
        with com.example.provider.FormalGreetingService;
}
~~~

If the provider is not a direct `requires` dependency of a root, you can use `--bind-services` so the linker finds and links matching provider modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output runtime
~~~

When combining with `--limit-modules`, make sure the needed provider modules are in the observable module set or in the dependency closure of that set. If the limit excludes the provider from the universe, the linker cannot bind that provider.

Including a provider module in the image does not mean a service instance is already created at link time. Instances are requested when the application runs and calls ServiceLoader.

## 8. Further Optimizing Runtime Image Size

After selecting the right module set, you can use `jlink` plugins to reduce image size.

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --limit-modules "java.base,com.example.api,com.example.app" --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Meaning:

- `--strip-debug`: strips debug information from classes in the image.
- `--no-header-files`: excludes native header files from the image.
- `--no-man-pages`: excludes manual pages from the image.
- `--compress=2`: compresses resources in the image at the supported compression level.

These plugins are packaging optimization options; they do not replace identifying the right dependency modules. Before dropping headers or man pages, confirm that the image will not be used as a native development JDK or reference documentation on the target machine.

You can view the list of available plugins with:

~~~bash
jlink --list-plugins
~~~

The plugin list and details depend on the JDK version in use.

## 9. Verifying the Runtime Image After Linking

After the `jlink` command finishes, use the launcher inside the image itself to check the module list:

~~~bash
runtime/bin/java --list-modules
~~~

The output will list the modules present in the custom runtime image. You can inspect the application module descriptor:

~~~bash
runtime/bin/java --describe-module com.example.app
~~~

Run the application with the new runtime:

~~~bash
runtime/bin/java --module com.example.app/com.example.app.Main
~~~

On Windows, the launcher is usually located at:

~~~powershell
runtime\bin\java.exe --list-modules
runtime\bin\java.exe --module com.example.app/com.example.app.Main
~~~

Practical verification should include:

- The application starts successfully using the launcher inside the image.
- Every API used is present.
- Required provider modules are bound if the application uses services.
- Resources, locales, security providers, logging, and runtime configurations work as expected.
- The image runs on the target environment with the same operating system platform and architecture.

Do not just check that the link command succeeded. Run critical functional flows on the final image.

## 10. Common Errors

**Module not found**

A module specified in `--add-modules` or `--limit-modules` was not found. Check the module path, the module name in the descriptor, and the presence of JDK `jmods`.

**Missing required module**

A root or one of its dependencies requires a module that is not on the module path or is no longer observable after limiting. Add the right module to the module path and adjust the limit so the dependency closure is valid.

**Module is limited but needed by the application**

If a module is outside the limited set and not in the dependency closure of the listed modules, the resolver cannot use that module. Update the limit list or remove `--limit-modules` to determine whether the limit is the cause.

**Automatic modules cannot be linked**

`jlink` requires the modules to be linked to fit the modular image model; an automatic module from a JAR without a descriptor is not a direct substitute input for an explicit named module. Upgrade the library, create a valid modular JAR, or package the dependency appropriately before linking.

**Service provider does not appear in the image**

Check that the consumer has `uses`, the provider has `provides`, and the provider is on the module path and observable. If you want the linker to bind matching providers automatically, consider `--bind-services`; if using `--limit-modules`, do not exclude needed providers from the observable set.

**Image is created but application fails at runtime**

Recheck module roots, module resolution, service binding, and resources needed at runtime. Run with `runtime/bin/java` itself rather than the development JDK to catch modules or resources accidentally present only in the build environment.

## 11. Controlled Image Creation Workflow

1. Compile and package the application into explicit modular JARs.
2. List the application's module dependencies via `module-info.java` and check library descriptors.
3. Identify root modules, usually the module containing the application.
4. Identify required provider modules if the application uses ServiceLoader.
5. Choose a module path containing JDK `jmods` and the application's modular JARs.
6. Run `jlink` with `--add-modules` to select roots.
7. Add `--limit-modules` when needed to limit the observable module set, while keeping the full dependency closure.
8. Add size-reduction plugins after the module set is correct.
9. Check `--list-modules`, `--describe-module`, and run tests on the resulting image.
10. Package the image for the exact target operating system and architecture.

## 12. Key Takeaways

- `jlink` creates a custom runtime image from compiled modules.
- `--add-modules` selects root modules to link.
- `--limit-modules` restricts observable modules during resolution; required transitive dependencies are still resolved.
- The module path must contain JDK modules and the application's modular JARs.
- Use `--bind-services` when you want the linker to link matching service provider modules.
- Plugins such as `--strip-debug`, `--no-header-files`, `--no-man-pages`, and `--compress=2` can reduce size, but do not replace selecting the right dependencies.
- Use the launcher inside the image to check the module list and run the actual application.

Start by identifying the root modules and dependency closure of the application. Then use `--limit-modules` to narrow the set of modules the resolver can see, link the image, and test that exact image in the deployment environment.
