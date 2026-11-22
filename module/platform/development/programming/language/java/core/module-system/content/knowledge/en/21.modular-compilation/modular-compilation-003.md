# javac -d Generating Output by Module

## Objectives

After this lesson, you will be able to:

- Explain the role of the `javac -d` option when compiling Java.
- Read the source tree structure of a modular project.
- Use `--module-source-path` and `-m` to compile one or more modules.
- Identify the exact locations of `module-info.class` and `.class` files after compilation.
- Distinguish compiling via module source path from passing individual module source files directly.
- Use the output directory as the module path for running the application.

## 1. Role of javac -d

`javac` is the Java compiler. When compiling source code, the compiler needs a place to write output files, primarily `.class` bytecode files and the compiled descriptor `module-info.class`.

Option:

~~~bash
javac -d <output-directory> <source-files>
~~~

Where:

- `-d` is short for `--directory`.
- `<output-directory>` is the root directory where the compiler writes the output.
- The compiler automatically creates the necessary subdirectories according to the package structure and how sources/modules are passed to the command.
- If `-d` is omitted, `javac` writes class files alongside their corresponding source files.

Key point: `-d` specifies the destination directory. It does not automatically infer all modules in a project and always create subdirectories by module name. How output is split per module depends on how you supply module sources—especially `--module-source-path`—or whether you explicitly choose a separate output directory for each module.

## 2. Source Tree of a Modular Project

Suppose an application has two modules:

- `com.acme.common`: provides shared APIs.
- `com.acme.app`: the main application, which depends on `com.acme.common`.

Source structure:

~~~text
project/
└── src/
    ├── com.acme.common/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── common/
    │               └── Version.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Each directory directly under `src/` is a module source root. The module directory name matches the module name declared in `module-info.java`.

Example descriptor for the common module:

~~~java
module com.acme.common {
    exports com.acme.common;
}
~~~

Exported class:

~~~java
package com.acme.common;

public final class Version {
    private Version() {
    }

    public static String value() {
        return "1.0";
    }
}
~~~

Descriptor for the application module:

~~~java
module com.acme.app {
    requires com.acme.common;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.common.Version;

public class Main {
    public static void main(String[] args) {
        System.out.println("Common version: " + Version.value());
    }
}
~~~

Each module has its own descriptor. `module-info.java` is the source descriptor; after compilation, the compiler produces `module-info.class` inside that module's output.

## 3. Compiling Multiple Modules with --module-source-path

Once the source tree is organized by module, you can instruct `javac` to locate module sources using `--module-source-path`.

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

Meaning of each part:

| Component | Role |
|---|---|
| `javac` | Launches the Java compiler |
| `-d out` | Chooses `out/` as the output root |
| `--module-source-path src` | Tells the compiler where the modules' source trees are located |
| `-m com.acme.common,com.acme.app` | Specifies the modules to compile |

In this example, `-d out` combined with the module source path causes the compiler to create one output directory per module. The result looks like:

~~~text
project/
├── src/
│   ├── com.acme.common/
│   │   ├── module-info.java
│   │   └── com/acme/common/Version.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── out/
    ├── com.acme.common/
    │   ├── module-info.class
    │   └── com/acme/common/
    │       └── Version.class
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/
            └── Main.class
~~~

The output structure can be read by this rule:

~~~text
<output-root>/
    <module-name>/
        module-info.class
        <package-path>/
            <ClassName>.class
~~~

For example:

- `out/com.acme.common/module-info.class` is the compiled descriptor of common.
- `out/com.acme.common/com/acme/common/Version.class` is the bytecode of the `Version` class.
- `out/com.acme.app/module-info.class` is the compiled descriptor of app.
- `out/com.acme.app/com/acme/app/Main.class` is the bytecode of the `Main` class.

Thus, the output root `out/` can be used as a module path containing multiple exploded modules. Each subdirectory corresponds to one compiled module.

## 4. Running the Application from the Output Directory

After compiling successfully, you can use the output root as the module path:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Where:

- `--module-path out` tells the JVM where to find compiled modules.
- `-m com.acme.app/com.acme.app.Main` selects the `com.acme.app` module and the `com.acme.app.Main` main class.

Output:

~~~text
Common version: 1.0
~~~

The JVM finds the app module in `out/`, reads its descriptor to see that app requires the common module, and then resolves the module graph. Both modules are present on the module path, so the application can run.

Workflow:

~~~text
src/
  com.acme.common/
  com.acme.app/
        |
        | javac -d out
        | --module-source-path src
        | -m com.acme.common,com.acme.app
        v
out/
  com.acme.common/
  com.acme.app/
        |
        | java --module-path out
        | -m com.acme.app/com.acme.app.Main
        v
     Application
~~~

## 5. Compiling Each Module with Its Own Output Directory

Using `--module-source-path` is not mandatory. You can also pass source files directly and choose a separate output directory for each module.

For example, compile common first:

~~~bash
javac -d mods/com.acme.common ^
    src/com.acme.common/module-info.java ^
    src/com.acme.common/com/acme/common/Version.java
~~~

Then compile app, using the output root `mods/` as the module path so the compiler can find common:

~~~bash
javac --module-path mods ^
    -d mods/com.acme.app ^
    src/com.acme.app/module-info.java ^
    src/com.acme.app/com/acme/app/Main.java
~~~

The example above uses the Windows Command Prompt line-continuation symbol. In PowerShell or other terminals, you can write each command on a single line or use the line-continuation character appropriate for your shell.

Final output structure:

~~~text
mods/
├── com.acme.common/
│   ├── module-info.class
│   └── com/acme/common/Version.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

With this approach, the compiler does not need to create subdirectories by module name from a module source path on its own. The build commands themselves choose `mods/com.acme.common` and `mods/com.acme.app` as the respective output directories.

You can run the application using the same module path:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Both ways of organizing have the same goal: each exploded module has a root directory containing `module-info.class` and the module's package tree.

## 6. Distinguishing -d, --module-source-path, and -m

These three options have different responsibilities:

| Option | Question Answered | Example |
|---|---|---|
| `-d` | Where to write output? | `-d out` |
| `--module-source-path` | Where to find module sources and in what structure? | `--module-source-path src` |
| `-m` / `--module` | Which modules to compile? | `-m com.acme.common,com.acme.app` |

Do not confuse `-d` with `--module-source-path`:

- `-d` controls output.
- `--module-source-path` describes the location and structure of module sources.
- `-m` selects the modules to compile from the module source path.

Example with only `-d out`:

~~~bash
javac -d out src/com/acme/app/Main.java
~~~

This is a standard source-file compilation command. The compiler preserves the package structure under the output root, such as `out/com/acme/app/Main.class`. There is no module source path information for `javac` to automatically organize multiple modules into `out/<module-name>/...`.

Example with a module source path:

~~~bash
javac -d out --module-source-path src -m com.acme.app
~~~

This command uses the module source structure to generate output by module. When there are multiple modules, each module is placed in its corresponding subdirectory under the output root.

## 7. Output Directory and Module Path

An exploded module is a directory containing a compiled descriptor and the module's contents. For example:

~~~text
mods/
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

When using `--module-path mods`, the module path can contain:

- The direct directory of an exploded module.
- A parent directory containing multiple exploded modules.
- A modular JAR.
- Other valid module locations supported by the Java module system.

With an output root containing multiple modules such as `out/` or `mods/`, the JVM scans the child modules according to the module path structure. You do not need to pass each module directory separately in the run command.

This makes `javac`'s output the direct input for the run step:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

In a release workflow, exploded modules can also be packaged into modular JARs. Packaging is a separate step; `javac -d` only creates the output directory and bytecode.

## 8. What to Check When Output Is Incorrect

### Module Output Placed in the Wrong Location

Check:

- Does the source tree follow the module source path structure?
- Does the module directory name match the name declared in `module-info.java`?
- Does the command include `--module-source-path` when you want the compiler to organize output by module automatically?
- Does `-d` point to the intended output root?

### Dependency Module Not Found

If the app module has:

~~~java
module com.acme.app {
    requires com.acme.common;
}
~~~

then the common module must exist in a finder accessible to the compiler, such as the module source path or the compiled module path.

When compiling app separately after common has already been compiled:

~~~bash
javac --module-path mods -d mods/com.acme.app <app-source-files>
~~~

Check that `mods/com.acme.common/module-info.class` exists and that the module path points properly to `mods/`.

### Main Class Not Found at Runtime

Check:

- Does the app module's output contain `module-info.class` and the package tree?
- Does the module name after `-m` match the descriptor?
- Is the main class name fully qualified with its package?
- Does the module path point to the parent directory containing the modules?

### Stale Classes Remain in Output

`javac` overwrites corresponding class files when recompiling, but you should not assume it automatically deletes stale classes that no longer have matching source files. If classes or packages are deleted or renamed, stale output may retain bytecode that no longer belongs to the current source.

For reproducible builds, let Gradle/Maven or a build script clean the output directory before recompiling. For example:

~~~bash
rm -rf out
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

On Windows PowerShell, you can run `Remove-Item -Recurse -Force out` before executing the `javac` command. Only delete the specific output directory managed by the build.

### module-info.class Missing

Module sources need `module-info.java` at the module root. If the project is compiled like a traditional classpath project or the source descriptor is omitted from the compilation pass, the output may lack `module-info.class` as expected.

## 9. Sample Workflow from Source to Runtime

For the two-module project in the earlier section, the basic workflow is:

1. Create a separate source root for each module.
2. Write `module-info.java` to declare the module name, dependencies, and exported packages.
3. Use `javac -d out --module-source-path src -m ...` to compile the modules.
4. Verify that the output has a separate directory for each module, each containing `module-info.class`.
5. Use `java --module-path out -m module/main-class` to run.
6. When the source structure changes, clean the output directory and recompile.

Illustrative command set:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Once you understand the output structure, you can quickly verify a build by opening the output directory and confirming:

- There is exactly one directory per compiled module.
- Each module contains `module-info.class`.
- The package paths in the output match the packages declared in the source.
- Dependency modules are present on the module path at compile time and runtime.

## Conclusion

`javac -d` specifies the root directory for writing compilation results. When combined with `--module-source-path` and `-m`, `javac` organizes output into separate directories named after each module, with `module-info.class` and the bytecode package tree inside each directory. If you pass source files directly, you can choose a separate output directory for each module.

Remember the three roles: **`-d` chooses where to write, `--module-source-path` describes where to find module sources, and `-m` selects the modules to compile.** The output root can then be used as the module path for the JVM.
