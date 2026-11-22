# Packaging a Modular JAR and Running with java -m

After compiling a module, the output is typically a directory containing `module-info.class`, Java classes, and resources. To distribute the module, that directory can be packaged into a **modular JAR** using the `jar` tool. When running, place the modular JARs on the module path and use `java -m` (or `java --module`) to launch the module.

Unlike a regular JAR containing only classes/resources, a modular JAR has a module descriptor at the archive root. The descriptor specifies the module name, dependencies, exported/opened packages, and service metadata. This enables the Java launcher to resolve the module graph before invoking the main class.

This lesson builds an application with two modules: `com.acme.greeter` provides an API and `com.acme.app` uses that API.

## 1. Application source structure

Create the structure:

~~~text
project/
├── src/
│   ├── com.acme.greeter/
│   │   ├── module-info.java
│   │   └── com/acme/greeter/api/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── out/
└── mods/
~~~

The module directory name in the source path corresponds to the module name declared in the descriptor.

API module `com.acme.greeter`:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
~~~

File `src/com.acme.greeter/com/acme/greeter/api/Greeter.java`:

~~~java
package com.acme.greeter.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Application module `com.acme.app`:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.greeter.api.Greeter;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JPMS" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

Relationship between the two modules:

- `com.acme.greeter` exports the package containing the public API.
- `com.acme.app` declares `requires com.acme.greeter`.
- The application only needs to know the API module; there is no need to copy Greeter classes into the app module.

## 2. Compiling the modules

From the `project` root directory, compile both modules:

~~~bash
javac --module-source-path src -d out --module com.acme.greeter,com.acme.app
~~~

You can use the short form:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app
~~~

Javac finds module sources in `src`, resolves dependencies between the two modules, and writes class files into `out`.

Result:

~~~text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Each module has a separate output directory. The `module-info.class` file sits at the root of the module directory, ready to be placed at the root of a modular JAR.

If you want to compile the dependency first and the app second:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter
javac --module-path out --module-source-path src -d out -m com.acme.app
~~~

The second approach uses the compiled module output as the module path. Both approaches produce packageable module output.

## 3. Packaging each module into a modular JAR

Create a directory to store archives:

~~~bash
mkdir -p mods
~~~

Package the API module:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
~~~

Package the application module:

~~~bash
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
~~~

Options:

- `--create` or `-c`: create a new archive.
- `--file` or `-f`: specify the output JAR file.
- `-C <directory> .`: change into the specified directory and add all contents from that directory to the archive.

The key point is that `out/com.acme.greeter` and `out/com.acme.app` both contain `module-info.class` at the root. The `-C ... .` command keeps the descriptor at the archive root rather than putting it in a subdirectory.

Result:

~~~text
mods/
├── com.acme.greeter.jar
└── com.acme.app.jar
~~~

The two independent modular JARs can be distributed together. The app module still references the API module by name in `requires`, not via a fixed JAR file path.

## 4. Creating an executable modular JAR with main class metadata

You can record the main class in module metadata when creating the application JAR:

~~~bash
jar --create   --file mods/com.acme.app.jar   --main-class com.acme.app.Main   -C out/com.acme.app .
~~~

The `--main-class` (or `-e`) option specifies the module's entry point. For a modular JAR, the main class information is written into the archive's module descriptor. As a result, the launcher can determine the main class when only the module name is passed.

If the module descriptor already has appropriate main class metadata, there is no need to specify it again in the JAR creation command.

There are two ways to run:

- Specify the main class explicitly: `java -m com.acme.app/com.acme.app.Main`.
- Use the main class recorded in the descriptor: `java -m com.acme.app`.

The second approach requires the module's descriptor to have a main class. Without that metadata, the launcher will require specifying the class after the slash.

## 5. Inspecting modular JARs

Use `jar --list` to view entries:

~~~bash
jar --list --file mods/com.acme.greeter.jar
~~~

A properly structured modular JAR will have entries similar to:

~~~text
META-INF/
META-INF/MANIFEST.MF
module-info.class
com/acme/greeter/api/Greeter.class
~~~

Inspect the descriptor:

~~~bash
jar --describe-module --file mods/com.acme.greeter.jar
jar --describe-module --file mods/com.acme.app.jar
~~~

Abbreviated output may show:

~~~text
com.acme.greeter
exports com.acme.greeter.api
requires java.base mandated
~~~

And the app module:

~~~text
com.acme.app
requires com.acme.greeter
requires java.base mandated
~~~

If `--main-class` was used, the output describing the app module will show the corresponding main class. This confirms the metadata was written into the JAR.

You can ask the launcher to describe a module on the module path:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

If the command cannot find the module, check whether the module path points to the directory containing the JARs and whether the descriptor has the expected module name.

## 6. Running the application with java -m

From the project root directory:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Short syntax:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

Result:

~~~text
Hello, JPMS!
~~~

Passing arguments to the main class:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main "Java Modules"
~~~

Result:

~~~text
Hello, Java Modules!
~~~

If the app JAR already has main class metadata:

~~~bash
java -p mods -m com.acme.app
~~~

The launcher will read the main class from the descriptor. If the module does not declare a main class, use the full `module/main-class` syntax.

In Windows PowerShell, the commands are similar:

~~~powershell
java --module-path mods --module com.acme.app/com.acme.app.Main
java -p mods -m com.acme.app "Java Modules"
~~~

The module path separator when there are multiple directories is a semicolon on Windows and a colon on Linux/macOS. In this example, there is only one `mods` directory, so no multiple paths need to be joined.

## 7. How the Java launcher resolves modular JARs

When running:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

the launcher performs these main steps:

1. Finds module `com.acme.app` on the module path.
2. Reads `module-info.class` to obtain the module name, dependencies, and metadata.
3. Resolves `requires com.acme.greeter`.
4. Finds `com.acme.greeter` on the same module path.
5. Resolves platform dependencies such as `java.base`.
6. Verifies the module graph and package access permissions.
7. Loads the main class and invokes `main(String[] args)`.

The module path contains named modules. The launcher does not need to know the dependency's JAR filename in advance once the module name in the descriptor is determined. This is an important difference compared to managing the classpath via a list of JAR files.

You can view the graph at launch:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

The output helps identify root modules, resolved dependencies, and locations where modules were found.

## 8. Distinguishing a modular JAR from an executable JAR on the classpath

A JAR can be:

- **Regular JAR**: has no module descriptor; when run on the classpath, classes belong to the unnamed module.
- **Modular JAR**: has `module-info.class` at the archive root; has a module name and dependency declarations.
- **Executable modular JAR**: a modular JAR with main class metadata so the launcher knows the entry point.

For a modular application with multiple dependencies, the clear way to run it is:

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Do not confuse `java -m` with `java -jar`:

- `-m` / `--module` instructs the launcher to start a named module on the module path.
- `-jar` launches a JAR in executable JAR mode using the manifest entry point; it is not an equivalent substitute for resolving a module graph of multiple named modules on the module path.

When the goal is practicing JPMS, use `-m` to explicitly express module name, main class, and module path.

## 9. Updating modular JARs when source changes

When code changes, recompile the modules and recreate the archives. Do not edit classes inside a JAR by manually copying files if you want a reproducible build process.

Example:

~~~bash
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app

jar --create --file mods/com.acme.greeter.jar -C out/com.acme.greeter .
jar --create --file mods/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

The `jar --create` command requires the target file to be newly created; if the file already exists, delete or replace it under a controlled build process before recreating. You can use `jar --update` for certain archive updates, but changes to the module descriptor/main class should be done via proper build inputs and re-verified with `jar --describe-module`.

After packaging, check the JAR's timestamp/hash if you need to confirm the runtime is using the right new artifact. A module path may mistakenly point to an old build directory even though the source changed.

## 10. Organizing the distribution directory

A simple deployment layout:

~~~text
distribution/
├── app/
│   └── com.acme.app.jar
└── lib/
    └── com.acme.greeter.jar
~~~

Then run:

~~~bash
java --module-path "app:lib" --module com.acme.app/com.acme.app.Main
~~~

On Windows:

~~~powershell
java --module-path "app;lib" --module com.acme.app/com.acme.app.Main
~~~

Multiple modular JARs can be distributed in one shared directory for simplicity:

~~~text
distribution/
└── mods/
    ├── com.acme.app.jar
    └── com.acme.greeter.jar
~~~

Then:

~~~bash
java -p mods -m com.acme.app
~~~

The benefit of this structure is that dependencies can be replaced independently while keeping module names and contracts compatible. However, do not place two versions of the same module name on the same module path; that makes module resolution ambiguous or fail.

## 11. Common errors and how to handle them

**Module not found.** Check that `--module-path` points to the directory containing the JARs, not to a single JAR file if you intend to use multiple dependencies. Check the module name in the descriptor using `jar --describe-module`.

**Package is not visible.** The API module has not exported the needed package, or the app has not declared `requires` for the API module. Check the descriptors of both modules.

**Main class not found when running `java -m com.acme.app`.** The module descriptor does not yet have main class metadata. Run explicitly with `java -m com.acme.app/com.acme.app.Main` or recreate the modular JAR with `jar --main-class`.

**JAR is not a modular JAR.** `module-info.class` might not be at the root of the archive. Use `jar --list --file` to verify entries. If the descriptor was placed under a subdirectory, the launcher will not recognize it as the JAR's module descriptor.

**Module name differs from file name.** The module name resides in the descriptor or is derived by automatic module rules. Do not rename the file assuming the module name changed; check using `jar --describe-module`.

**Works in IDE but fails from terminal.** The IDE may automatically configure the module path, working directory, and runtime JDK. Re-run with an explicit command line, the right JDK, and the right distribution directory.

**Replaced JAR but app still uses old version.** Check whether the module path has duplicate directories or an older artifact appearing earlier in the configuration. Use `--show-module-resolution` to see module locations.

**Using `java -jar` for a multi-module app and missing dependencies.** `-jar` does not replace the module path graph of `-m`. Run modular applications using `--module-path` and `--module`.

## 12. Hands-on Practice

1. Create the two modules `com.acme.greeter` and `com.acme.app` following the example.
2. Compile both with `javac --module-source-path src -d out -m com.acme.greeter,com.acme.app`.
3. Package each module into a modular JAR inside the `mods` directory.
4. Use `jar --list` to confirm `module-info.class` is at the root of each JAR.
5. Use `jar --describe-module` to read `requires`, `exports`, and main class metadata.
6. Run with `java -p mods -m com.acme.app/com.acme.app.Main`.
7. Recreate the app JAR with `--main-class`, then try running with just `java -p mods -m com.acme.app`.
8. Try removing `requires com.acme.greeter` or removing `exports com.acme.greeter.api`; observe the compile/resolution errors and restore the descriptor.
9. Enable `--show-module-resolution` to see which modules are selected and from which locations.
10. Copy the `mods` directory to a new distribution directory and run the application from there to verify independence from the source tree.

When distributing a modular application, keep `module-info.class` at the root of each modular JAR, ensure dependencies are on the module path, and launch using `java -m`. If you want to omit the main class name in the run command, record the entry point in the descriptor with `jar --main-class`. This compile, package, inspect, and launch workflow helps verify the module graph clearly before deployment.