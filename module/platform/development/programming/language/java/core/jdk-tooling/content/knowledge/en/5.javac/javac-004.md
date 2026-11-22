# Source path in javac

The source path is the list of root directories that the Java compiler uses to locate source files when it needs to resolve types or classes that are referenced but not passed directly in the input list. When a project splits its source code across multiple packages or multiple source roots, configuring the source path helps javac find the right .java files, compile the required source dependencies, and generate bytecode into the proper directory structure.

The source path is especially useful when a project has multiple source directories, auto-generated code, or when you want to separate source code from already-compiled libraries. Misconfiguration often leads to errors such as package does not exist, cannot find symbol, or file not found even though the source files exist on disk.

## 1. What is the source path?

In Java, a class is typically declared inside a package. For example:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

If the package is com.acme.model, the source file is typically placed under a root directory following this structure:

~~~text
src/main/java/
└── com/
    └── acme/
        └── model/
            └── Customer.java
~~~

The directory src/main/java is the source root. The relative path beneath the source root reflects the package name: com/acme/model corresponds to the package com.acme.model.

When another class references Customer, javac needs to find either the source file or the bytecode of that class. The source path specifies the source roots so that javac can locate the necessary .java files.

For example, if Main.java imports com.acme.model.Customer, javac can locate the source file at:

~~~text
src/main/java/com/acme/model/Customer.java
~~~

The key point is that the source path normally points to the root directory containing the packages, not directly to the final package directory itself. If the source root is src/main/java, javac automatically appends the package path com/acme/model to find Customer.java.

## 2. Distinguishing source path, classpath, and output directory

These three concepts often appear together, but they solve three different problems:

| Option | Role |
|---|---|
| -sourcepath | Locate the .java source files needed for compilation. |
| -classpath or -cp | Locate already-compiled classes, JARs, and libraries that the source code depends on. |
| -d | Specify the destination directory where compiled .class files are written. |

Example:

~~~bash
javac -sourcepath src/main/java -classpath lib/api.jar -d out src/main/java/com/acme/app/Main.java
~~~

In this command:

- javac receives Main.java as an explicit input source file.
- -sourcepath src/main/java allows it to find additional .java files referenced by Main.
- -classpath lib/api.jar allows it to find compiled classes in the api.jar library.
- -d out writes the .class files into the out directory following the package structure.

The source path is not the directory that holds output .class files. Conversely, -d does not tell javac where to find input source code.

If -sourcepath is not specified, javac defaults to searching for source files and user classes in the user class path. The default classpath is usually the current directory, unless changed via the corresponding option or environment variable. When specifying a source path explicitly, treat it as the place to look for source code; the classpath still serves to locate compiled classes and libraries.

If source files are already listed explicitly on the command line, javac does not need to locate those same files again via the source path. The source path remains useful for finding source classes referenced by those input files.

## 3. Project structure with multiple source roots

A project can split its source code across multiple directories, such as main code and auto-generated code:

~~~text
source-path-demo/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/acme/app/Main.java
│   └── generated/
│       └── java/
│           └── com/acme/generated/BuildInfo.java
├── src-model/
│   └── com/acme/model/Customer.java
└── out/
~~~

Each source root is a separate starting point. In the example above:

- src/main/java contains the package com.acme.app.
- src/generated/java contains the package com.acme.generated.
- src-model contains the package com.acme.model.

When Main uses Customer and BuildInfo, javac must be able to find all three source roots. Multiple source roots can be declared in a single -sourcepath value.

You should not set the source path to a subdirectory that is too deep. If you declare src/main/java/com/acme, javac will search for packages relative to that directory; when a class declares package com.acme.model, the lookup structure will no longer match the intended source root.

## 4. Practical example: compiling dependencies from multiple source roots

Create the following directory structure:

~~~text
source-path-demo/
├── src/main/java/com/acme/app/Main.java
├── src-model/com/acme/model/Customer.java
├── src-generated/com/acme/generated/BuildInfo.java
└── out/
~~~

File src-model/com/acme/model/Customer.java:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

File src-generated/com/acme/generated/BuildInfo.java:

~~~java
package com.acme.generated;

public final class BuildInfo {
    public static final String VERSION = "2026.11";

    private BuildInfo() {
    }
}
~~~

File src/main/java/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.generated.BuildInfo;
import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Linh");

        System.out.println("Application: source-path-demo");
        System.out.println("Customer: " + customer.name());
        System.out.println("Build: " + BuildInfo.VERSION);
    }
}
~~~

Run the commands from the root directory source-path-demo.

On Linux or macOS, the separator between source path entries is a colon:

~~~bash
mkdir -p out

javac -d out -sourcepath "src/main/java:src-model:src-generated" src/main/java/com/acme/app/Main.java

java -cp out com.acme.app.Main
~~~

On Windows PowerShell, the separator between path entries is a semicolon:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac -d out -sourcepath "src/main/java;src-model;src-generated" src/main/java/com/acme/app/Main.java

java -cp out com.acme.app.Main
~~~

Exact output of the program:

~~~text
Application: source-path-demo
Customer: Linh
Build: 2026.11
~~~

In this example, only Main.java is passed directly to javac. When resolving Customer and BuildInfo, the compiler searches for the corresponding source files across the declared source roots. The source classes are found and compiled into out.

After compilation, the output structure will look like this:

~~~text
out/
└── com/
    └── acme/
        ├── app/Main.class
        ├── generated/BuildInfo.class
        └── model/Customer.class
~~~

The java command uses out as the classpath root and the fully qualified class name com.acme.app.Main to run the application.

This example demonstrates how javac locates and compiles dependent sources. For real-world projects, you can choose to pass all source files explicitly or let javac find dependent sources via the source path. Listing them explicitly often makes build inputs easier to control when a project has a large build process.

## 5. Syntax and how to pass -sourcepath

Basic syntax:

~~~bash
javac -sourcepath <source-path> <source-files>
~~~

You can also use the long form:

~~~bash
javac --source-path <source-path> <source-files>
~~~

The source path value is one or more directories separated by the operating system's path separator.

| Operating system | Multi-directory separator |
|---|---|
| Windows | Semicolon ; |
| Linux | Colon : |
| macOS | Colon : |

Example on Windows:

~~~powershell
javac -sourcepath "src/main/java;src/generated/java" -d out src/main/java/com/acme/app/Main.java
~~~

Example on Linux/macOS:

~~~bash
javac -sourcepath "src/main/java:src/generated/java" -d out src/main/java/com/acme/app/Main.java
~~~

Enclose the value in quotes when paths contain spaces or characters with special meaning to the shell. Quotes ensure the shell passes the entire source path list as a single argument to javac.

Do not confuse the separator between directories with the separator between package components. The package com.acme.model maps to the directories com/acme/model on the filesystem; the dots in a package name are not source root list separators.

## 6. Relative paths, absolute paths, and working directory

Relative paths are resolved based on the current working directory of the javac process. They are not necessarily based on the location of the Java file or the build file.

For example, with the structure:

~~~text
project/
├── src/
│   └── com/example/Main.java
└── out/
~~~

If the terminal is inside project, you can use:

~~~bash
javac -sourcepath src -d out src/com/example/Main.java
~~~

If the terminal is in the parent directory of project, you must adjust the paths:

~~~bash
javac -sourcepath project/src -d project/out project/src/com/example/Main.java
~~~

You can use absolute paths to reduce dependence on the working directory, especially in CI scripts. However, hardcoded absolute paths tied to a personal machine often make a project difficult to share. It is better to use relative paths from the project root in build configurations, or construct paths from a project root variable.

On Windows, paths may contain spaces, such as C:/Users/Dev User/Projects/demo/src. When passing them in PowerShell or Command Prompt, enclose the path in double quotes.

On Linux/macOS, filesystems are typically case-sensitive. Packages com.acme and com.Acme can lead to two different paths. On Windows, filesystem case-sensitivity behavior often differs; therefore, keep package names and directory names consistent to avoid errors that only appear on Linux CI.

## 7. Source path and package must match

With the declaration:

~~~java
package com.example.service;
~~~

The source file normally resides at:

~~~text
<source-root>/com/example/service/Service.java
~~~

If the source root is src/main/java, the full path is typically:

~~~text
src/main/java/com/example/service/Service.java
~~~

If you set the source root to src/main/java/com/example/service, javac will treat that directory as the starting point for package lookup. When another class references the package com.example.service, the lookup path may repeat the package components and fail to find the file.

Another mistake is when the package declared in the file does not match the directory structure. Check both: the package line in the source code and the relative path from the source root. The filename of the top-level public class must also match the class name; for example, a public class Service must be in Service.java.

A source root does not always have to be named src/main/java. That is just a common convention. A small project may use src; an older project may use source; a project with code generation may add generated-sources. What matters is that the source path points to the directory immediately above the package hierarchy.

## 8. When does javac automatically find and compile source files?

There are two ways to provide input to javac:

1. **Explicit sources:** directly listing the .java files to compile.
2. **Indirectly discovered sources:** javac detects a referenced type whose source exists without matching up-to-date bytecode, and then searches for the source file via the source path.

Example specifying a single file:

~~~bash
javac -sourcepath src -d out src/com/example/Main.java
~~~

If Main references com.example.model.Customer and Customer.java resides in the source root src, javac can find and compile that dependent source.

You can specify all sources explicitly:

~~~bash
javac -d out src/com/example/Main.java src/com/example/model/Customer.java
~~~

In this case, javac does not need to locate Customer.java via the source path because the file has been passed directly.

For large projects, a build tool typically manages source lists and dependencies. Manual javac commands are useful for understanding the mechanism, testing a small module, or diagnosing configuration errors. You should not rely on the compiler automatically discovering every source file when a project has code generation, multiple source sets, or complex build rules.

## 9. Source path is not source version

A common misconception is treating -sourcepath and -source as the same kind of option.

- **-sourcepath / --source-path** specifies where to find source files.
- **-source** selects the Java syntax/language version that the compiler accepts.
- **--release** selects the target Java version, including the corresponding language, bytecode, and platform APIs.
- **-target** selects the target bytecode version without automatically restricting platform APIs; for modern builds, prefer --release when appropriate.

For example, a newer JDK can use the source path src/main/java while compiling for Java 17:

~~~bash
javac --release 17 -sourcepath src/main/java -d out src/main/java/com/example/Main.java
~~~

Here, the source path still only indicates the location of the source code. --release 17 controls the target Java compatibility level. The two options solve two different problems and can be used together.

## 10. Source path in modular projects

For projects using the Java Platform Module System, each module typically has a module-info.java and its own package tree. When compiling multiple modules from a single source tree, the appropriate option is --module-source-path.

Example structure:

~~~text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/Customer.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Module descriptor for model:

~~~java
module com.acme.model {
    exports com.acme.model;
}
~~~

Module descriptor for app:

~~~java
module com.acme.app {
    requires com.acme.model;
}
~~~

Compile from the project directory:

~~~bash
javac --module-source-path src -d out --module com.acme.app
~~~

The --module-source-path option tells javac where to find the source trees of the modules. This mechanism is designed for module source trees, unlike the source path of a standard classpath project.

When a project already has compiled modules or modular JARs available, --module-path is used to locate compiled modules. Do not confuse --module-path with --module-source-path: one locates compiled modules, while the other locates module source code.

## 11. Source path and annotation processing / auto-generated source code

Some projects generate Java code during the build process, such as annotation processors generating metadata, mapper, or adapter classes. It is important to distinguish the related paths:

| Option | Purpose |
|---|---|
| -sourcepath | Locate input Java source code or dependent sources. |
| -processorpath | Locate compiled annotation processor classes. |
| -s | Specify the directory where .java files generated by annotation processors are written. |
| -d | Specify the directory where .class files are written. |

Example build command with an annotation processor:

~~~bash
javac -cp lib/api.jar -processorpath tools/code-generator.jar -s generated-src -d out -sourcepath src/main/java src/main/java/com/example/Main.java
~~~

In this command, generated-src is where generated source code is written; it does not automatically equate to the source path for input sources. Annotation processing has its own processing rounds, in which generated sources can be compiled in subsequent rounds of the same javac invocation.

If a project needs to use source code generated from a previous build, add that directory to the source path as an appropriate source root. If the code is generated during the current build, configure the processor path and the -s directory appropriately in the build tool or javac command.

Do not place a JAR containing an annotation processor on the source path expecting javac to run the processor automatically. A processor is executable code loaded through the annotation processing mechanism; -processorpath or the corresponding processor configuration specifies where to find the processor.

## 12. Common errors and how to fix them

| Message or symptom | Possible cause | How to fix |
|---|---|---|
| package ... does not exist | Wrong source root, mismatched package path, or dependency missing from classpath/module path. | Check the package declaration, source root, and library paths. |
| cannot find symbol | Class or member not found; could be missing source, missing classpath, or wrong import. | Identify which package the symbol belongs to; check the source path and classpath separately. |
| file not found | Input file path relative to a different working directory than expected. | Check the working directory and actual path; try an absolute path to diagnose. |
| javac does not automatically compile dependent class | Source path does not contain the proper source root, or other bytecode was found first. | Check the source path, classpath, and location of compiled classes. |
| Classes compiled into the wrong directory | Not using -d or looking at the wrong source root/output directory. | Use -d out and check the package path inside out. |
| Works on Windows but fails on Linux | Case-sensitivity differences or path separator differences. | Standardize package/directory names and use the platform-specific separator. |
| Paths with spaces are not recognized | The shell splits a single argument into multiple parts. | Enclose the entire source path in quotes. |
| Generated source code not found | Confusing the -s directory with the source path or not running the code generation step. | Check build order, processor path, and the source root of generated code. |

When you need to see where javac is searching for and loading sources/classes, you can enable verbose output:

~~~bash
javac -verbose -sourcepath src/main/java -d out src/main/java/com/example/Main.java
~~~

The verbose output is quite long, but it can show which source files and classes are being loaded. This is a useful way to distinguish source path issues from classpath issues.

You can view the options supported by your current javac version:

~~~bash
javac --help
javac -version
~~~

## 13. Source path configuration checklist

Before concluding that javac is at fault, check the following in order:

1. Identify the current working directory of the build command.
2. Identify the exact source roots of the project.
3. Verify the package declaration in each file and its corresponding directory path.
4. Verify that source files have the exact right name and casing.
5. Pass multiple source roots correctly using the operating system's separator.
6. Distinguish .java sources to locate from .class/JAR files to locate on the classpath.
7. Use -d to separate bytecode from the source tree.
8. If using modules, use module-source-path and module-path for their respective roles.
9. If using annotation processors, check the processor path and -s directory separately.
10. Use -verbose to see where javac actually searches for files.
11. Re-run the command from the proper project root or normalize paths in scripts/CI.

The source path is part of the input configuration when compiling Java. When you identify the right source roots, keep the package structure consistent, and separate the source path from the classpath, module path, and output directory, javac can locate dependent source code accurately and generate bytecode matching your intended project structure.
