# Troubleshooting Incorrect Classpath in Java

## 1. What is the classpath?

The classpath is the list of locations that Java uses to find classes and resources when compiling or running an application. Each entry can be:

- A root directory containing `.class` files following the package structure.
- A JAR or ZIP file containing classes and resources.
- Multiple directories/JARs combined in order.

Example project:

~~~text
project/
├── src/
│   └── com/example/Main.java
├── build/
│   └── classes/
│       └── com/example/Main.class
└── lib/
    └── helper.jar
~~~

If the class's fully qualified name is com.example.Main, the classpath must point to the build/classes directory, i.e., the directory directly above the com package. Do not point to build/classes/com/example.

The classpath is not the path to a specific class file. It is the set of root locations from which the JVM can find packages, classes, and resources.

## 2. Distinguishing between compile-time classpath and runtime classpath

Two different phases require a classpath:

- **Compile time:** javac needs to find classes that the source imports or references.
- **Runtime:** The JVM needs to find classes loaded while the program is running, including directly called dependencies, transitive dependencies, reflection, or plugins.

For example, Main.java imports com.example.lib.Helper. If Helper is in helper.jar, the compiler must see that JAR during compilation. At runtime, the JVM must also find Helper on the runtime classpath.

Successful compilation does not prove that the runtime classpath is complete. This is why an application can compile normally but throw NoClassDefFoundError when run.

## 3. Understanding package structure and classpath root correctly

Suppose the file is generated at:

~~~text
build/classes/com/example/Main.class
~~~

The class name is com.example.Main and the classpath root is:

~~~text
build/classes
~~~

Correct command:

~~~bash
java -cp build/classes com.example.Main
~~~

Incorrect command:

~~~bash
java -cp build/classes/com/example com.example.Main
~~~

The incorrect command causes the JVM to look for the class at:

~~~text
build/classes/com/example/com/example/Main.class
~~~

The package path is duplicated, so the JVM cannot find the class.

General rule: strip the package part from the class file path to determine the classpath root. For com.example.service.UserService, the root must contain the com/example/service directory.

## 4. Compiling and running a small program

Create the file src/com/example/Main.java:

~~~java
package com.example;

public final class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Classpath is correct");
        System.out.println("target=" + target);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/com/example/Main.java
~~~

Run:

~~~bash
java -cp build/classes com.example.Main test
~~~

Exact stdout:

~~~text
Classpath is correct
target=test
~~~

The -d option specifies the destination directory for class files. Because the source declares package com.example, javac creates the file at build/classes/com/example/Main.class.

You can use relative classpath paths when you are at the project root. If running from another directory, you must adjust the paths or use absolute paths.

## 5. -cp and --class-path syntax

The following two forms are equivalent:

~~~bash
java -cp build/classes com.example.Main
java --class-path build/classes com.example.Main
~~~

With javac:

~~~bash
javac -cp lib/helper.jar -d build/classes src/com/example/Main.java
javac --class-path lib/helper.jar -d build/classes src/com/example/Main.java
~~~

The classpath is the value of a single option. When multiple entries are needed, join them using the operating system's path separator.

Example:

~~~bash
java -cp "build/classes:lib/helper.jar" com.example.Main
~~~

This is Linux/macOS syntax. On Windows, the separator is a semicolon:

~~~powershell
java -cp "build\classes;lib\helper.jar" com.example.Main
~~~

Wrap the entire classpath in quotes so the shell does not split components containing spaces or special characters.

## 6. Classpath separators by operating system

This is a common mistake when porting scripts between Windows and Linux/macOS.

| Operating System | Separator | Example |
|---|---|---|
| Windows | ; | classes;lib/a.jar;lib/b.jar |
| Linux | : | classes:lib/a.jar:lib/b.jar |
| macOS | : | classes:lib/a.jar:lib/b.jar |

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar" com.example.Main
~~~

Do not use : to separate classpath entries on Windows. The : character appears in drive letters like C:, so it is not the Windows classpath separator.

When creating cross-platform scripts, let Maven/Gradle manage the runtime classpath or use an API/tool to generate the classpath instead of concatenating strings with a hardcoded separator.

## 7. Relative paths and the working directory

Relative classpaths are resolved from the process's working directory, not automatically from the directory containing the source file, class file, or JAR.

Check the working directory:

~~~powershell
Get-Location
~~~

Linux/macOS:

~~~bash
pwd
~~~

In Java:

~~~java
System.out.println(System.getProperty("user.dir"));
~~~

For example, if the working directory is the project root, the classpath build/classes may work. If you run the same command from the scripts directory, the JVM will look for scripts/build/classes and fail.

How to fix:

- Run the command from a known directory.
- Use a relative classpath calculated from the current working directory.
- Or use an absolute path.
- In an IDE/CI, set the working directory explicitly.

Do not confuse the working directory with the directory containing the JAR. The two directories can be different.

## 8. Handling paths with spaces

If the project is located at a path such as:

~~~text
C:\Users\Developer\Java Projects\demo\
~~~

The classpath must be properly quoted.

PowerShell:

~~~powershell
java -cp "C:\Users\Developer\Java Projects\demo\build\classes;C:\Users\Developer\Java Projects\demo\lib\helper.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "/home/developer/Java Projects/demo/build/classes:/home/developer/Java Projects/demo/lib/helper.jar" com.example.Main
~~~

Do not quote individual parts separately and let the shell split the expression. Quoting the entire classpath value ensures the shell passes it as a single argument.

If a script builds paths dynamically, use the path-joining mechanism of the shell or build tool. Avoid manually concatenating slashes and separators across operating systems.

## 9. Adding multiple JARs to the classpath

When an application needs multiple dependencies, you can list all JARs:

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar;lib\logging.jar;lib\json.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar:lib/logging.jar:lib/json.jar" com.example.Main
~~~

The classpath can combine class directories with JARs. Entry order matters: when multiple classes have the same name, the class loader may load the first one found according to the classpath order.

Avoid having two different versions of the same library appear together on the classpath. This can cause confusing errors such as NoSuchMethodError, AbstractMethodError, or order-dependent behavior.

## 10. Using wildcards for the lib directory

The Java launcher supports wildcards for JARs directly inside a directory.

Windows:

~~~powershell
java -cp "build\classes;lib\*" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/*" com.example.Main
~~~

The wildcard lib/* does not search recursively into subdirectories. For example, lib/plugins/a.jar is not automatically added to the classpath if only lib/* is specified.

Do not rely on the order of JARs expanded by a wildcard to resolve duplicate class names. If order matters, list dependencies explicitly or let a build tool produce a controlled runtime classpath.

The Java launcher's wildcard differs from shell-expanded wildcards. Wrapping the classpath in quotes lets the Java launcher handle the JAR directory wildcard itself.

## 11. Error: Could not find or load main class

Common message:

~~~text
Error: Could not find or load main class com.example.Main
Caused by: java.lang.ClassNotFoundException: com.example.Main
~~~

This error usually means the JVM could not find the requested main class. Check:

1. Has the class been compiled?
2. Is the classpath root correct?
3. Do the package and class name match in case?
4. Is the working directory correct?
5. Was the classpath passed via -cp/--class-path?
6. Was a separator from another OS accidentally used?

Check the file:

~~~powershell
Test-Path .\build\classes\com\example\Main.class
~~~

Linux/macOS:

~~~bash
test -f build/classes/com/example/Main.class && echo "class exists"
~~~

If the file exists but still cannot be found, check whether the classpath points to build/classes. Do not pass build/classes/com/example when the class name is com.example.Main.

## 12. Distinguishing between ClassNotFoundException and NoClassDefFoundError

These two errors are related but typically appear in different situations.

| Error | Common Meaning | Example |
|---|---|---|
| ClassNotFoundException | An API loading a class by name could not find the class. | Class.forName("com.example.Plugin"). |
| NoClassDefFoundError | The JVM needed a class during linking or execution but could not find the required definition. | Main calls Helper, but helper.jar is missing at runtime. |

Example of a missing runtime dependency:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/lib/Helper
Caused by: java.lang.ClassNotFoundException: com.example.lib.Helper
~~~

If javac used helper.jar but java did not, compilation succeeds while runtime fails.

The fix is to add the dependency to the runtime classpath or use an appropriate packaging/distribution method. Check transitive dependencies as well, not just libraries that the source imports directly.

## 13. Compile-time dependencies do not automatically become runtime dependencies

For example, Main.java references Helper.java. Compile:

~~~bash
javac -cp lib/helper.jar -d build/classes src/com/example/Main.java
~~~

This command only helps the compiler find Helper. It does not automatically copy helper.jar into build/classes, nor does it automatically add helper.jar to the run command.

When running with a classpath, you must provide both:

Windows:

~~~powershell
java -cp "build\classes;lib\helper.jar" com.example.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/classes:lib/helper.jar" com.example.Main
~~~

With Maven, the dependency scope must match its runtime usage. With Gradle, check runtimeClasspath and configurations such as implementation and runtimeOnly. Do not use compileOnly for libraries that the application actually needs at runtime.

## 14. Understanding the difference between -cp and -jar

This is one of the most common causes of classpath errors.

When running:

~~~bash
java -cp "app.jar:lib/helper.jar" com.example.Main
~~~

The JVM uses the classpath passed via -cp.

However, when running:

~~~bash
java -cp "lib/helper.jar" -jar app.jar
~~~

The classpath from -cp is ignored. With -jar, Java reads the entry point from Main-Class in the manifest and uses the manifest's Class-Path to locate additional dependencies.

Therefore, you cannot add dependencies to an executable JAR by placing -cp before -jar. Choose one of two approaches:

- Run the main class directly using -cp.
- Use -jar and declare dependencies in the manifest's Class-Path, or package dependencies into an appropriate artifact.

## 15. Declaring dependencies in the manifest Class-Path

An executable JAR can reference dependencies located alongside it.

Structure:

~~~text
dist/
├── app.jar
└── lib/
    └── helper.jar
~~~

Manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/helper.jar
~~~

Run:

~~~bash
java -jar dist/app.jar
~~~

Paths in the manifest Class-Path are URLs relative to the location of the JAR containing the manifest. Use forward slashes / in the manifest even when running on Windows.

The manifest only references dependencies; it does not copy libraries into app.jar. Ensure lib/helper.jar exists relative to app.jar and is readable.

If dependencies are located elsewhere, update the manifest or redistribute the application directory with the proper structure. When a single artifact is needed, consider a shaded/fat JAR and verify merging of service descriptors, resources, and signatures.

## 16. Classpath and module path are not the same

The classpath serves the classpath/unnamed module. Applications using the Java Platform Module System may require the module path.

Module path example:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

The --module option can be shortened to -m:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

If a named module is placed only on the classpath, its module descriptor is not used as it would be when running on the module path. Conversely, module dependencies need to be resolved according to the module graph.

Inspect modules:

~~~bash
jar --describe-module --file lib/helper.jar
java --list-modules
~~~

If you encounter FindException or ModuleNotFoundException, check the module path, module name, module descriptor, and module dependencies. Do not resolve module errors by randomly adding JARs to the classpath if the application is designed for the module system.

## 17. Default classpath and the CLASSPATH variable

If neither -cp nor --class-path is passed, the Java launcher may use the CLASSPATH environment variable or the default classpath.

Check on Windows PowerShell:

~~~powershell
$env:CLASSPATH
~~~

Linux/macOS:

~~~bash
echo "$CLASSPATH"
~~~

A global CLASSPATH variable can easily make a project work on a developer's machine while failing on CI or another machine. It can also silently introduce an outdated dependency version into the application.

In scripts, IDE Run Configurations, and CI, specify the classpath explicitly or let Maven/Gradle manage it. An explicit classpath via -cp overrides the default user classpath for that run.

Do not put all dependencies of every project into the system CLASSPATH.

## 18. Classpath order and duplicate classes

If two JARs both contain com.example.util.Version, the result may depend on classpath order. The JVM typically loads the first class found during the search.

Example:

~~~bash
java -cp "lib/old.jar:lib/new.jar:app.jar" com.example.Main
~~~

The example above is for Linux/macOS. Windows uses semicolons.

If old.jar and new.jar both define the same class, the one appearing first may be loaded. This is a source of binary incompatibility errors.

How to resolve:

- Remove the older dependency version.
- Use dependency management/BOM to unify versions.
- Run Maven or Gradle's dependency tree/report.
- Inspect the process's actual classpath.
- Avoid manually copying multiple versions of a JAR into lib.

If you encounter NoSuchMethodError even though the class was found, check which version of the class is actually being loaded, not just whether the JAR file exists.

## 19. Classpath for resources

The classpath contains not only .class files, but also packaged resources such as properties, XML, templates, and configuration files.

Example:

~~~java
var stream = Main.class.getResourceAsStream("/config/app.properties");
~~~

If the resource is on the classpath at config/app.properties, it can be read using the class resource API. A path starting with / is interpreted from the classpath root.

Distinguish between resources packaged inside a JAR and external files. External config files outside a JAR are usually resolved relative to the working directory or an absolute path, and are not automatically on the classpath.

Inspect resources inside an archive:

~~~bash
jar --list --file app.jar
~~~

If the class is found but the resource returns null, check whether the resource was copied into the output directory/JAR and whether the path matches in case.

## 20. Diagnosing classpath issues with JDK tools

You can use the following tools to observe and inspect:

List JAR contents:

~~~bash
jar --list --file lib/helper.jar
~~~

View the classpath received by the launcher:

~~~bash
java -XshowSettings:properties -version
~~~

Find loaded classes and their sources:

~~~bash
java -verbose:class -cp "build/classes:lib/*" com.example.Main
~~~

Modern JDKs also support class loading logging:

~~~bash
java -Xlog:class+load=info -cp "build/classes:lib/*" com.example.Main
~~~

Analyze dependencies:

~~~bash
jdeps --multi-release 17 --class-path "lib/*" app.jar
~~~

Inspect bytecode/class name:

~~~bash
javap -classpath app.jar -verbose com.example.Main
~~~

On Windows, replace : in the classpath with ;. Verbose output can be very long; filter by the package/class name under investigation and avoid sharing logs containing sensitive information.

## 21. How do Maven and Gradle manage the classpath?

In a Maven project, declare dependencies in pom.xml instead of manually assembling the classpath for each run. Maven distinguishes compile/runtime/test scopes. Dependencies with only compileOnly or provided scope may not be present in the application's runtime the way you expect.

Inspect the dependency tree:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency helper --configuration runtimeClasspath
~~~

If using the Gradle Application Plugin, the run task uses the runtime classpath managed by the plugin. For an executable JAR, you still need to ensure dependencies are distributed via manifest, application distribution, or a fat JAR.

Do not assume the compile classpath is the default for runtime. Check the configuration/task actually used when the application runs.

## 22. Configuring IDE Run Configurations

IDEs typically build their own classpath from the module/project configuration. If running from the terminal succeeds but the IDE fails, check:

- Full main class name.
- Selected module or project.
- Whether dependencies have been imported/resolved.
- Project SDK and language level.
- Whether the Run Configuration uses the correct module classpath.
- Working directory.
- Test/runtime scope of dependencies.
- Generated sources and resource directories.

In IntelliJ IDEA, check the Run/Debug Configuration and module classpath. In Eclipse, check the Java Build Path and launch configuration. In VS Code, check the project import and Java runtime/classpath managed by the extension.

If the IDE uses stale output, clean/rebuild the project and run again. Do not manually edit the classpath with a long list of JARs if a build tool can already manage dependencies.

## 23. Step-by-step diagnostic procedure

When encountering a classpath error, follow this order:

1. Record the exact java or javac command that was run.
2. Verify the Java executable and version with java --version.
3. Determine the working directory.
4. Determine the entry point: class, JAR, source file, or module.
5. Locate the .class file or JAR containing the class to run.
6. Determine the classpath root based on the package.
7. Check the OS-specific separator.
8. Check quoting for paths with spaces.
9. Check runtime dependencies, not just compile-time ones.
10. If using -jar, check Main-Class and manifest Class-Path.
11. If using module path, check the module descriptor and module graph.
12. Use -verbose:class or jdeps to inspect actual classes/dependencies.
13. Compare the launch commands in the terminal, IDE, and CI.

Do not change multiple variables at once. Change one factor, rerun the same command, and compare the error message to isolate the cause.

## 24. Lab: reproducing and fixing an incorrect classpath error

Create two source files.

Main.java:

~~~java
package com.example;

import com.example.lib.Helper;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Classpath demo started");
        System.out.println(Helper.message());
        System.out.println("argument.count=" + args.length);
    }
}
~~~

Helper.java:

~~~java
package com.example.lib;

public final class Helper {
    public static String message() {
        return "helper loaded";
    }
}
~~~

Compile Helper:

~~~bash
javac --release 17 -d helper-classes src/com/example/lib/Helper.java
jar --create --file lib/helper.jar -C helper-classes .
~~~

Compile Main against Helper:

~~~bash
javac --release 17 -cp helper-classes -d app-classes src/com/example/Main.java
~~~

Run with the correct classpath on Windows:

~~~powershell
java -cp "app-classes;dist\lib\helper.jar" com.example.Main first "two words"
~~~

Linux/macOS:

~~~bash
java -cp "app-classes:dist/lib/helper.jar" com.example.Main first "two words"
~~~

Output:

~~~text
Classpath demo started
helper loaded
argument.count=2
~~~

If helper.jar is omitted from the runtime classpath, the program compiles successfully but throws NoClassDefFoundError at runtime. If the classpath mistakenly points to app-classes/com/example instead of app-classes, the JVM cannot find com.example.Main.

## 25. Verified lab results

The fixture was compiled with Java 17 target and run on Windows 11 with Azul Zulu JDK 24.0.2; the same valid classpath also runs on Amazon Corretto 17.0.15.

| Scenario | Actual Result |
|---|---|
| Explicit classpath with app-classes and helper.jar | PASS |
| Wildcard lib/* | PASS |
| Incorrect classpath root | Could not find or load main class; exit code 1 |
| Missing helper.jar at runtime | NoClassDefFoundError; exit code 1 |
| Passing -cp with -jar to add helper.jar | Still NoClassDefFoundError; -cp is ignored |
| Manifest Class-Path pointing to lib/helper.jar | PASS |
| Running classpath from a directory with spaces | PASS |
| Same classpath on Corretto 17.0.15 | PASS |

Message when setting an incorrect classpath root:

~~~text
Error: Could not find or load main class com.example.Main
Caused by: java.lang.ClassNotFoundException: com.example.Main
~~~

Message when a dependency is missing:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: com/example/lib/Helper
Caused by: java.lang.ClassNotFoundException: com.example.lib.Helper
~~~

These results show that main class errors and runtime dependency errors are two distinct issues that must be fixed in the right place.

## 26. Checklist before delivering an application

- [ ] Main class/package is accurately identified.
- [ ] Classpath root points to the correct directory containing the package tree.
- [ ] All runtime dependencies are provided.
- [ ] Separator matches Windows or Linux/macOS.
- [ ] Paths containing spaces are quoted.
- [ ] Working directory is clearly defined.
- [ ] No reliance on a global CLASSPATH.
- [ ] Wildcards are not used when JAR order control is required.
- [ ] No duplicate versions of the same library.
- [ ] -cp is not used with -jar to add dependencies.
- [ ] Manifest Class-Path is correct if running with java -jar.
- [ ] Module path is configured if the application is modular.
- [ ] Smoke test runs from a clean directory on the minimum supported runtime.
- [ ] CI uses the same tested dependency graph and launch command.

## 27. References

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [JAR File Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html)
- [ClassLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html)
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)

An incorrect classpath can prevent the JVM from finding the main class, cause missing dependencies, or load the wrong class version. Identify the correct package root, working directory, OS separator, and runtime dependencies; then verify the actual launch command rather than looking only at the compile configuration.
