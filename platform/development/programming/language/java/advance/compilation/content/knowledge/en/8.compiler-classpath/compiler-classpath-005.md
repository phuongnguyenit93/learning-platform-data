# Distinguishing Compile-Time Dependencies from Runtime Dependencies in Java

When compiling a Java application, `javac` needs to find the **types, methods, and fields** referenced by the source code; when running, the JVM needs to find **the classes and resources actually used**. These two sets of needs are closely related yet not identical. Therefore, a program can compile successfully and then fail with `NoClassDefFoundError` when running; conversely, a plugin loaded via reflection may not need to appear on the application's compile classpath yet is required to be present when loading the plugin.

Within the **Classpath** knowledge group of Java Advance – compilation, this lesson explains the boundary between compile-time dependencies and runtime dependencies, how `javac` and `java` find classes, direct/indirect dependency cases, binary compatibility, dynamic loading, and how to organize dependencies in real projects. Examples are written for **Java 17 and above**, with verified hands-on commands and outputs.

## 1. Two Stages, Two Different Questions

**A compile-time dependency** is a component the compiler needs to verify type names, method signatures, access constraints, generics, annotations, or other compilation requirements. In a simple application, that is typically a directory containing `.class` files or a JAR on `javac`'s classpath.

**A runtime dependency** is a component the JVM, class loader, or application execution mechanism needs to load/link/initialize classes, invoke methods, access resources, or perform actual functionality. A component may be needed at runtime without being needed directly to compile the application source.

| Question | Compiling with javac | Running with java/JVM |
|---|---|---|
| Primary input | `.java` files along with related type/API declarations | `.class` bytecode, JARs, resources, and runtime configuration |
| Responsibility | Name resolution, type checking, signature selection, bytecode generation | Class loading, linking, initialization, bytecode execution |
| Commonly used paths | `javac -cp ...`, `-sourcepath ...`, `--module-path ...` | `java -cp ...`, `--module-path ...`, module/class loaders |
| When a component is missing | `package ... does not exist`, `cannot find symbol`, or other compile errors | `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, resource errors, or initialization errors |
| When detected? | Before running the program | When the JVM or application logic actually needs the corresponding component |

A way to visualize the regular classpath case:

~~~text
Application source .java --(javac + compile classpath)--> .class
                                                            |
                                                            v
                                                (java + runtime classpath)
                                                            |
                                                            v
                                                     Program runs
~~~

**There is no rule requiring the two classpaths to be identical.** What must be ensured is that each stage has the appropriate set of dependencies, and that the library versions used by the bytecode are compatible at runtime.

### 1.1. Directly Referenced Types and Indirectly Arising Dependencies

If source code calls `Greeter.message("Java")`, `javac` needs to know `Greeter` and the signature `message(String)`. If execution reaches that call, the JVM also needs to locate `Greeter` with a matching method. This is a case **needed at both stages**.

If an application only uses `Class.forName("ext.Extension")` with the class name as a string, the code does not need a direct reference to the type `ext.Extension` at compile time. However, if runtime execution reaches the class-loading call, the component containing `ext.Extension` must be findable by the corresponding class loader. This is an example of a **runtime-only dependency**.

If the compiler uses an annotation processor to generate code during the build, the processor may only need to appear during the compilation stage, while the compiled application code does not need the processor at runtime. This is a form of **build/compile-only tool dependency**, provided that other APIs/classes the program actually uses are supplied appropriately.

## 2. Understanding What the Classpath Really Is

**Classpath** is the set of search roots for classes and resources on the class path. An element can be the root directory of a package tree or a JAR file. For example, if a class declares:

~~~java
package lib;
public final class Greeter { }
~~~

then a classpath directory `lib-classes` must contain `lib-classes/lib/Greeter.class`. If using a JAR, inside the JAR there must be an entry `lib/Greeter.class`. The classpath **does not** point to the `lib` package directory underneath the root, and the fully qualified type name is `lib.Greeter`.

`-classpath`, `-cp`, and `--class-path` are forms of specifying the classpath. They must be supplied to the right process:

~~~sh
javac -cp artifacts/greeter.jar -d app-classes app-src/app/Main.java
java -cp "<runtime-classpath>" app.Main
~~~

In the first command, `-cp` belongs to **javac** and serves compilation. In the second command, `-cp` belongs to **java** and serves execution. The `javac -d app-classes` option only specifies where to write bytecode; it **does not automatically make** `app-classes` the runtime classpath for the subsequent `java` command.

The separator between **classpath elements** differs by operating system:

- Windows: `;` — for example `"app-classes;artifacts/greeter.jar"`.
- Linux/macOS: `:` — for example `"app-classes:artifacts/greeter.jar"`.

Place strings containing separators inside quotes. The examples below explicitly show commands for both environments so `:` is not confused with drive-letter colons on Windows.

**The classpath does not automatically search every JAR in every subdirectory.** A wildcard like `libs/*` can be used for JARs directly inside the `libs` directory under Java launcher/compiler rules, yet does not recurse through subdirectories; JAR expansion order should not be relied on as a version-selection guarantee. Specifying each JAR explicitly or letting a build tool manage them is usually clearer.

## 3. Complete Example: Dependency Needed at Both Compile Time and Runtime

Create the following structure in a directory named `project`:

~~~text
project/
├── lib-src/
│   └── lib/
│       └── Greeter.java
├── app-src/
│   └── app/
│       └── Main.java
├── lib-classes/            # created during practice
├── app-classes/            # created during practice
└── artifacts/
    └── greeter.jar         # created during practice
~~~

### 3.1. Library Code

File `lib-src/lib/Greeter.java`:

~~~java
package lib;

public final class Greeter {
    public static String message(String name) {
        return "Hello, " + name;
    }
}
~~~

This is a public class with a static method returning `String`. The fully qualified name to reference it is `lib.Greeter`.

### 3.2. Application Code

File `app-src/app/Main.java`:

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Before call");
        System.out.println(Greeter.message("Java"));
    }
}
~~~

`Main` has a **direct static dependency** on `lib.Greeter`: the source code has an `import` line and a call to that type's method. `import` only participates in name resolution; by itself it does not add a JAR to the build.

### 3.3. Compiling the Library Class and Packaging the JAR

Open a terminal in the `project` directory. On Linux/macOS:

~~~sh
mkdir -p lib-classes app-classes artifacts
javac --release 17 -encoding UTF-8 -d lib-classes lib-src/lib/Greeter.java
jar --create --file artifacts/greeter.jar -C lib-classes .
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path lib-classes, app-classes, artifacts | Out-Null
javac --release 17 -encoding UTF-8 -d lib-classes lib-src/lib/Greeter.java
jar --create --file artifacts/greeter.jar -C lib-classes .
~~~

The `jar` tool comes with the JDK. The `-C lib-classes .` option packages the package-structured class tree, so the JAR contains `lib/Greeter.class`. These commands assume `javac` and `jar` are on PATH and use a JDK supporting `--release 17`.

### 3.4. Compiling the Application with the Dependency

The command is identical on both operating systems because the compile classpath has only one element:

~~~sh
javac --release 17 -encoding UTF-8 -cp artifacts/greeter.jar -d app-classes app-src/app/Main.java
~~~

`javac` must read the signature `Greeter.message(String)` inside `artifacts/greeter.jar` to know the call is valid and returns `String`. The application compilation output is `app-classes/app/Main.class`.

### 3.5. Running with the Right Runtime Dependency

Windows PowerShell or cmd:

~~~powershell
java -cp "app-classes;artifacts/greeter.jar" app.Main
~~~

Linux/macOS:

~~~sh
java -cp "app-classes:artifacts/greeter.jar" app.Main
~~~

**Exact stdout**:

~~~text
Before call
Hello, Java
~~~

At runtime, the JVM needs both `app.Main` and `lib.Greeter`. The fact that `javac` just used `greeter.jar` earlier does not automatically transfer it onto the runtime classpath. The two commands have **independent** classpath configurations.

## 4. Missing Dependency at Compile Time: Compile-Time Failure

Keep the source files as-is, yet try compiling the application **without providing Greeter** on the compile classpath/source path:

~~~sh
javac --release 17 -encoding UTF-8 -d app-classes app-src/app/Main.java
~~~

If `lib.Greeter` is not on another class/source search path in the environment (for example a pre-set `CLASSPATH` variable), the compiler rejects it. Representative verified messages:

~~~text
error: package lib does not exist
error: cannot find symbol
~~~

The compiler cannot find the type declaration to check `Greeter.message("Java")`. **This is a compile-time error**: the program does not yet have valid new application bytecode to run.

Fix: add the path to the library `-cp artifacts/greeter.jar`, or pass a matching set of sources to the same `javac` invocation, or configure the dependency with a build tool. Merely adding the JAR to `java`'s runtime classpath **cannot fix** `javac`'s error from that compilation run.

Do not conclude the classpath is missing from a `cannot find symbol` line alone: typos, wrong packages, wrong letter casing, or access permissions can also be causes. Read the full symbol name and where the compiler is searching.

## 5. Missing Dependency at Runtime: Runtime Linkage Failure

After compiling `Main.class` successfully per section 3, intentionally **omit `greeter.jar` from the runtime classpath**, while keeping `app-classes`:

~~~sh
java -cp app-classes app.Main
~~~

Output when running the program on the JDK used for verification:

~~~text
Before call
Exception in thread "main" java.lang.NoClassDefFoundError: lib/Greeter
~~~

The stack trace also typically includes a cause such as:

~~~text
Caused by: java.lang.ClassNotFoundException: lib.Greeter
~~~

**Exact explanation:** `app.Main` was loaded and executed its initial part. When the JVM needed to resolve the reference to `lib.Greeter`, the class loader could not find the class definition. `NoClassDefFoundError` is a `LinkageError` at runtime; `ClassNotFoundException` may appear in the cause. The timing of when the JVM resolves symbolic references has leeway under the specification, so you should not guarantee every JVM prints a line before failing across all program structures. This specific example was verified to print `Before call` and then fail.

Proper fix: run with `app-classes` **and** `artifacts/greeter.jar` on the runtime classpath. Simply recompiling the application without supplying the JAR at runtime does not solve the missing class definition situation.

### 5.1. How Does ClassNotFoundException Differ from NoClassDefFoundError?

- `ClassNotFoundException` is a **checked exception**, typically occurring when code/the program invokes an API to load a class by name, such as `Class.forName("ext.Extension")`, and the class loader cannot find it.
- `NoClassDefFoundError` is an **Error** when the JVM needs to define a class yet cannot obtain that class under the required loading/linking mechanism; the cause can be a class missing at runtime, or a prior class initialization failure. Seeing `NoClassDefFoundError` does not always guarantee someone forgot to add a JAR.
- `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, and `IncompatibleClassChangeError` can indicate that **bytecode was compiled against one API yet sees a different API/structure at runtime**.

Examine the `Caused by` section and full signatures in the stack trace. A class-loading failure during initialization can raise `ExceptionInInitializerError` on first use and `NoClassDefFoundError` on subsequent uses, even if the `.class` file still exists.

## 6. JAR Present at Runtime But Wrong Version: Binary Compatibility

Suppose the application in section 3 was compiled against the API:

~~~java
public static String message(String name)
~~~

Yet at runtime, the application accidentally receives a different JAR in which `lib.Greeter` changed to:

~~~java
public static String message()
~~~

The class name `lib.Greeter` still exists, yet **the method signature no longer matches the old calling bytecode**. The JVM may report `NoSuchMethodError`.

### 6.1. Experimenting with an Incompatible v2 Library

Create `lib-v2-src/lib/Greeter.java`:

~~~java
package lib;

public final class Greeter {
    public static String message() {
        return "changed API";
    }
}
~~~

Create the directory `lib-v2-classes`, then compile/package a differently named JAR:

~~~sh
javac --release 17 -encoding UTF-8 -d lib-v2-classes lib-v2-src/lib/Greeter.java
jar --create --file artifacts/greeter-v2.jar -C lib-v2-classes .
~~~

Note that `lib-v2-classes` must be created before running the command; use `mkdir -p lib-v2-classes` on Linux/macOS or `New-Item -ItemType Directory -Force -Path lib-v2-classes` in PowerShell. **Do not recompile** `app.Main`: we want to keep the bytecode compiled against the v1 API.

Windows:

~~~powershell
java -cp "app-classes;artifacts/greeter-v2.jar" app.Main
~~~

Linux/macOS:

~~~sh
java -cp "app-classes:artifacts/greeter-v2.jar" app.Main
~~~

The command fails with **`java.lang.NoSuchMethodError`**, because at runtime `lib.Greeter` no longer has the static method with the name, parameter, and return type referenced by the old bytecode. This is **not** a compile-time `cannot find symbol` error, because application compilation succeeded against the v1 API.

A differently versioned JAR does not always cause an error; errors occur when changes **break binary compatibility** with the portion of bytecode actually used. Adding a new method usually differs in impact from removing/changing the signature of a method being called. Do not guess compatibility solely from a "v2" label or semantic versioning numbers.

## 7. Dependencies Needed Only at Runtime: Reflection and Plugins

An application may know a class name only as a string and load the class at runtime. Because the class name is not mentioned as a **Java type** in declarations/calls, `javac` does not need to read the target class's definition to check the `Class.forName` statement.

### 7.1. Plugin Class

Create `plugin-src/ext/Extension.java`:

~~~java
package ext;

public final class Extension {
    @Override
    public String toString() {
        return "plugin loaded";
    }
}
~~~

Compile and package the plugin:

~~~sh
javac --release 17 -encoding UTF-8 -d plugin-classes plugin-src/ext/Extension.java
jar --create --file artifacts/extension.jar -C plugin-classes .
~~~

Create the `plugin-classes` directory before invoking `javac`.

### 7.2. Application Not Importing the Plugin Type

Create `reflect-src/app/ReflectMain.java`:

~~~java
package app;

public final class ReflectMain {
    public static void main(String[] args) throws Exception {
        System.out.println(
            Class.forName("ext.Extension")
                .getDeclaredConstructor()
                .newInstance()
        );
    }
}
~~~

Compile the application **without needing** `extension.jar` on the compile classpath:

~~~sh
javac --release 17 -encoding UTF-8 -d reflect-classes reflect-src/app/ReflectMain.java
~~~

Create `reflect-classes` before compiling. The code only uses Java APIs such as `Class` and reflection; the name `ext.Extension` is a data string in source. `javac` does not treat this string as a type declaration to resolve.

When running, the plugin JAR must be provided. Windows:

~~~powershell
java -cp "reflect-classes;artifacts/extension.jar" app.ReflectMain
~~~

Linux/macOS:

~~~sh
java -cp "reflect-classes:artifacts/extension.jar" app.ReflectMain
~~~

Verified stdout:

~~~text
plugin loaded
~~~

If `extension.jar` is omitted and you run `java -cp reflect-classes app.ReflectMain`, the application encounters:

~~~text
java.lang.ClassNotFoundException: ext.Extension
~~~

This example demonstrates a **runtime-only dependency** in an application. In a real plugin system, the plugin class may be loaded by a separate class loader or a Java module layer rather than the application classpath; you must still ensure that loader can find the class definition. Calling `Class.forName` with an existing class name also does not automatically guarantee a public constructor, module access, or all of the plugin's dependencies are available.

### 7.3. ServiceLoader and Implementation Discovery

Java `ServiceLoader` is another example of runtime extensibility. An application usually compiles against a **service interface**, while implementations can be added at runtime and registered via `META-INF/services/<service-interface>` in a JAR on the classpath, or declared via `provides ... with ...` in a named module.

Important conditions:

- The API/interface must be known to the application at compile time if code references that interface directly.
- The provider implementation and registration metadata must be available at runtime in the appropriate class loader/module environment.
- Failing to find a provider can result in an empty provider list; misconfiguration or a provider failing to load/initialize can lead to `ServiceConfigurationError`.

Do not equate every runtime-only dependency with reflection: configuration resources, logging backends, JDBC drivers, native libraries, and providers/plugins can also belong to the set of dependencies that arise only on a specific execution path or dynamic loading mechanism.

## 8. Dependencies Serving Compilation That Are Not Needed at Runtime

The reverse direction also exists. Certain tools/dependencies are used to generate or check bytecode, and then are unnecessary when running the properly compiled application.

### 8.1. Annotation Processors

An annotation processor runs during the compilation process to read annotations/models and can generate Java files or resources. For example, a processor generates classes, generates mapping code, or checks compile-time rules. Once the generated code is compiled, the **processor implementation** usually does not need to be on the runtime classpath. However, classes directly referenced by the generated code **must still** be present at runtime.

In project configuration, distinguish the **annotation processor path** from the application compile classpath. With `javac`, `-processorpath` (or `--processor-path`) specifies where to look for annotation processors on the classpath; when using Java modules there are separate processor module path options depending on the JDK. Configuring a processor does not mean adding all of the processor's dependencies to runtime.

JDK 17 has default behaviors for processor discovery that differ from some newer JDKs; when reproducible builds are needed, declare the processors to run explicitly instead of relying on machine settings or assuming a single default across all JDKs.

### 8.2. Source-Only APIs and Guarantees

A dependency containing an annotation with only `RetentionPolicy.SOURCE` may be needed for the compiler to process source, yet that annotation is not written into the class file for runtime lookup. Similarly, a tool API or code-generation library may only be needed during the build if no runtime bytecode depends on it.

**Be careful:** just because code compiles cleanly using a library does not mean that library is unneeded at runtime. In particular, annotation APIs with `RUNTIME` retention, bytecode containing type references, or generated code may still need that dependency. You must verify the actual needs of the bytecode, reflection mechanisms, and class loading.

Build tool items such as `compileOnly` are only appropriate when the runtime environment **already provides the required API/classes** (for example, a container/server), or when they are genuinely no longer used at runtime. Declaring `compileOnly` for a library that application code still calls at runtime easily creates missing-class errors.

## 9. Direct, Transitive Dependencies, and Deploying Multiple JARs

Suppose:

~~~text
Application
    |
    v
library-a.jar  --->  library-b.jar
                     |
                     v
                 library-c.jar
~~~

The application only imports the class `a.Service`, yet when `a.Service` runs it needs `b.Parser` and then `c.Codec`. **The runtime dependency set** must include all components genuinely needed on the executed branches. Adding `library-a.jar` does not make the class loader automatically have `library-b.jar` or `library-c.jar`.

A normal JAR contains its own bytecode/resources; it **does not automatically embed** all Maven/Gradle dependencies unless packaged as a fat/uber JAR or special packaging mechanism. An artifact's `pom.xml` file is used for dependency resolution in build tools, yet the JVM `java -cp path/to/lib.jar` does not automatically fetch transitive libraries from Maven Central merely by reading the JAR filename.

### 9.1. Why Can Compilation Succeed Even When Runtime Lacks a Transitive Dependency?

The compiler can check a call needing only the API present in `library-a.jar`, without needing to inspect every implementation or runtime branch that `a.Service` may execute. During execution, code inside A triggers a class in B; if B is not loaded, runtime can raise an error.

Conversely, `javac` **may also need an indirect dependency right at compile time** if public signatures, superclasses, interfaces, annotations, or generic information that the compiler must process contain types from B. Thus there is no rule that "transitive dependencies are only needed at runtime". You must consider the actual API and the classes `javac` must read.

### 9.2. Same Class Name in Multiple JARs: Do Not Rely on Order

If two JARs both contain `lib.Greeter`, runtime may load a different definition than the version the compiler used, depending on the class loader, classpath order, and environment configuration. There is no guarantee that "the newest version wins". This is a source of hard-to-diagnose errors such as `NoSuchMethodError`.

To avoid this:

1. Allow only one appropriate version of each library to appear on the corresponding loading path, unless the design requires isolation.
2. Keep compile and runtime resolution consistent; use dependency locking/BOM/version constraints appropriate for your build tool.
3. Inspect the dependency tree and the actual packaged artifacts.
4. For plugins needing multiple parallel versions, consider class loader isolation, shading/relocation, or properly designed and tested module boundaries.

### 9.3. Do JDK Classes Need to Be Put on the Classpath?

APIs belonging to the Java platform, such as `java.lang.String` and `java.util.List`, come from Java platform modules (for example `java.base`) included in the appropriate JDK/runtime; there is no need to copy Java 8's `rt.jar` onto a JDK 17 classpath. With Java 9+, system modules and `--release` manage platform APIs under the modern model.

However, **third-party libraries** such as a specific JDBC driver, an HTTP client outside the JDK, or a framework do not automatically become part of the Java runtime. Do not confuse the standard `java.sql` API with the driver JAR for a specific database.

## 10. Distinguishing Classpath and Module Path

The examples in sections 3–7 run on the **classpath** (unnamed module). When a project has `module-info.java`, the Java Platform Module System (JPMS) adds rules for **module readability, exports/opens, and module resolution**.

~~~java
// Illustrative example of module-info.java, not a file from the runnable example above.
module app.module {
    requires lib.module;
}
~~~

Depending on the project, the module `lib.module` may `exports lib.api;` so other modules can use the API. `requires` indicates a module dependency; `exports` determines which API packages are accessible at compile time and runtime under module rules. Deep reflection may require `opens` or appropriate opening configuration.

- Compile modules with `javac --module-path ...` and appropriate source/module configuration.
- Run modules with `java --module-path ... -m app.module/<main-class>`.
- Do not assume `-cp` and `--module-path` are interchangeable.
- A module existing on the module path is not necessarily resolved for a given run configuration.
- In JPMS, a module dependency can be a requirement at compile time, runtime, or both, depending on `requires`, `requires static`, the resolution mechanism, and how the program uses the module.

This is an illustration of conceptual scope; the complete example in section 3 has no `module-info.java`. Topics such as automatic modules, qualified exports, and module layers require examining the application's actual configuration.

## 11. When Running with a JAR: -cp Differs from -jar

For a program invoking a main class directly:

~~~sh
java -cp "app-classes:artifacts/greeter.jar" app.Main
~~~

(the separator example is Linux/macOS), the application classpath is determined by `-cp`. However, when running:

~~~sh
java -jar app.jar
~~~

The Java launcher uses the **entry point** from the JAR's manifest (for example `Main-Class`) and ignores specifying a user classpath via `-cp` for `-jar` launches. Valid `Class-Path` entries in the manifest can provide additional paths, yet cannot be replaced by "attaching `-cp` before `-jar`".

A framework's fat JAR/bootable JAR may use its own launcher/class loader to load nested JARs. Therefore, you cannot assert that every `app.jar` behaves like a plain JAR. To analyze runtime dependencies, you need to know the **actual packaging method and launch mechanism**.

Do not confuse the runtime classpath with relative resource paths based on the working directory. A file `config/application.properties` on the filesystem must be accessed according to the program's path rules; resources placed inside a JAR should be loaded with an appropriate resource/class loader API.

## 12. Dependency Scopes in Gradle and Maven

Build tools help classify different needs, avoiding blindly attaching every JAR to both classpaths. The following examples are **illustrations of build syntax**, not part of the small Java project in section 3.

### 12.1. Gradle Java Plugin

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:core:1.0'
    compileOnly 'org.example:provided-api:1.0'
    runtimeOnly 'org.example:runtime-provider:1.0'
    annotationProcessor 'org.example:code-generator:1.0'
}
~~~

The `org.example` coordinates above only illustrate configuration meaning, **not artifacts guaranteed to exist on Maven Central**.

| Configuration | Primary meaning |
|---|---|
| `implementation` | Library used for the module's own compile classpath and usually present on the module's runtime classpath |
| `compileOnly` | Needed when compiling, not automatically added to runtime |
| `runtimeOnly` | Needed when running, not automatically added to the compile classpath |
| `annotationProcessor` | Dependency for the compilation process's annotation processor path |
| `testImplementation` | For compiling/running tests per the Java plugin configuration |
| `testRuntimeOnly` | Specifically for test runtime |

If using the `java-library` plugin, `api` helps declare a dependency that belongs to the **public API** which consumers also need when compiling. `implementation` typically represents implementation details that consumers should not be forced to depend on directly. Choosing `api`/`implementation` relates to how dependencies are exposed across projects/modules, **and is not synonymous** with distinguishing runtime-only.

You can inspect classpaths and dependency resolution with Gradle tasks:

~~~sh
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows, use `gradlew.bat` instead of `./gradlew` where appropriate. Actual configuration names may vary by plugin/source set. Dependency tree output shows what the build tool selected; you still need to check the actual distribution if packaged by another plugin.

### 12.2. Maven Scopes

Maven uses `scope` to describe a dependency's purpose in the build model. Common scopes:

| Maven Scope | General meaning |
|---|---|
| `compile` | Default; usually present on compile, test, and runtime classpaths |
| `provided` | Present when compiling/testing; the runtime environment is expected to provide the dependency, not packaged into the artifact in the usual way |
| `runtime` | Not needed to compile the module's direct sources; present at runtime/test |
| `test` | Serves only test source/classpath, not a runtime dependency of the main application |
| `system` | Requires a separately specified system path; usually best avoided due to poor reproducibility |

Maven and Gradle have different transitivity, conflict resolution, and packaging rules. Do not apply a single table of "this scope is always in the JAR" to every packaging plugin. For instance, a plain JAR created by the Java plugin does not automatically embed all runtime dependencies; a Spring Boot executable JAR has its own layout and launcher.

## 13. Diagnosing Errors When Compile and Run Differ

| Symptom | Stage and possible cause | How to verify |
|---|---|---|
| `package lib does not exist` | Compile: `javac` cannot find the package | Compare `javac -cp`, sources, and the JAR containing `lib/Greeter.class` |
| `cannot find symbol: Greeter` | Compile: symbol cannot be resolved | Check imports, package, classpath/sourcepath, and accessibility |
| `NoClassDefFoundError: lib/Greeter` | Runtime: the JVM lacks the class definition when needed, or a prior class initialization error | Check `java -cp`, JAR contents, `Caused by` |
| `ClassNotFoundException: ext.Extension` | Runtime: loading class by name failed | Check class name, class loader, plugin JAR/module, and load path |
| `NoSuchMethodError` | Runtime linkage: referenced method signature does not exist in the class seen at runtime | Verify compile API and runtime binary/version |
| `NoSuchFieldError` | Runtime linkage: field was changed/removed or mismatched | Check binary compatibility and JARs with duplicate types |
| `IllegalAccessError` | Runtime: access requirement violated at link time after binary/module change | Compare compile/runtime access and module/API changes |
| `UnsupportedClassVersionError` | Runtime: class file bytecode was produced for a higher Java version than runtime supports | Check `javac -version`, `java -version`, `--release` |
| `ServiceConfigurationError` | Runtime: ServiceLoader could not process a configured provider | Check provider metadata, constructors, class loader, and dependencies |
| Runs in IDE but fails in terminal | Different classpath/working directory/JDK | Compare exact commands, dependency tree, and run configuration |

### 13.1. Practical Diagnostic Command Set

The following commands are appropriate when working in the example project:

~~~sh
javac -version
java -version
jar --list --file artifacts/greeter.jar
~~~

Look for the `lib/Greeter.class` entry in the JAR listing. On classpath-based systems, inspect how classes are loaded using `-verbose:class` when genuinely needed:

~~~sh
java -verbose:class -cp "<application-and-library-classpath>" app.Main
~~~

This option can print many lines. Replace the placeholder string with the **actual classpath of your environment**, using the OS-appropriate separator. You can use `javap` to inspect compiled class signatures:

~~~sh
javap -classpath artifacts/greeter.jar lib.Greeter
~~~

If it displays `message(java.lang.String)` in the JAR used at compile time yet only `message()` in the JAR used at runtime, you have evidence of a binary mismatch. Use `javap -c` when you need to see which method the bytecode calls; do not judge solely by JAR filename.

### 13.2. Effective Investigation Order

1. **Distinguish compile error from runtime error.** If `javac` fails, do not jump to conclusions about the runtime classpath.
2. **Identify the class/field/method being sought.** Read the full name in the message and stack trace.
3. **Check JDK and paths.** Do `java` and `javac` target the same version; is the working directory right?
4. **Check actual classpaths.** What `-cp` does the compile command pass? What `-cp` does the run command pass? Does `CLASSPATH` or a build tool inject values?
5. **Check JAR contents and versions.** Is the classpath entry in the right position? Are there two JARs containing the same class?
6. **Check indirect dependencies.** Does runtime implementation A call B/C? Are dependencies distributed with the application?
7. **Check dynamic loading mechanisms.** Do reflection, ServiceLoader, plugin class loaders, containers, or module layers have their own search scopes?
8. **Rebuild/repackage consistently.** Avoid running stale bytecode/JARs after an API changes; if output needs clearing, clean only the build's generated directories.

## 14. Misconceptions to Avoid

**"Once a class is imported, the JVM automatically finds the JAR."** False. `import` is source syntax; the JVM executes bytecode, and the class loader must have a path to the actual class.

**"Compile passes means running will definitely pass."** False. Runtime may lack classes, lack resources, hit initialization failures, linkage errors, exceptions, or logic bugs.

**"A runtime-only library is a library unused in Java."** False. It can be used via reflection, provider APIs, or another library's implementation.

**"All transitive dependencies are only needed at runtime."** False. A library's public API may cause the compiler to need a type from a transitive dependency right at compile time.

**"Simply copying a new JAR with the same name into the libs directory is safe."** False. The compiled binary may be incompatible with the runtime binary even though JAR/package/class names remain identical.

**"With Java 17, the classpath automatically has every library."** False. Java platform APIs differ from third-party library JARs.

**"When running -jar, just add -cp and it works."** False for standard launcher behavior: `-jar` obtains the entry point and classpath via launch/manifest mechanisms rather than the `-cp` user classpath of normal main-class execution.

**"A class can only be loaded right at startup."** False. The JVM can load/link lazily when needed, and applications can proactively load classes dynamically; failure timing can depend on the execution path.

## 15. Hands-On Exercises

### Exercise 1 — Omitting the JAR at Each Stage

Use the project from section 3. Try three scenarios:

1. Have `greeter.jar` on the compile classpath yet omit it from the runtime classpath.
2. Omit the JAR from the compile classpath while the JAR file still exists on the machine.
3. Have the JAR at both stages.

Predict which run fails in `javac`, which fails in `java`, and which prints the two output lines. Explain why merely **having the file on disk** is not enough; the program must be configured to find that file.

### Exercise 2 — Changing the API Without Recompiling the Application

Compile the application against `greeter.jar` v1, then switch runtime to `greeter-v2.jar` as in section 6. Explain why `NoSuchMethodError` differs from `ClassNotFoundException`: in this case the `Greeter` class was found, yet the method signature expected by bytecode is gone.

### Exercise 3 — Runtime-Only Plugin

Compile `ReflectMain.java` without `extension.jar`. Run with and without the plugin JAR. Predict when the JVM processes the string name `ext.Extension` and the error type when the class cannot be found. Try misspelling the class name string by one letter; observe the result.

### Exercise 4 — Dependency Tree

With a Gradle/Maven project having several libraries, list compile and runtime dependencies. Pick a library used only through a provider, a library imported directly by the application, and a processor. Explain why the three libraries are configured differently.

### Exercise 5 — Checking JARs with Duplicate Classes

Create two JARs both containing `lib.Greeter` yet with different signatures. Try running with one JAR at a time. Then inspect contents using `jar --list` or `javap`. In real applications, use dependency resolution to select a single appropriate version instead of hoping on classpath order.

## 16. Checklist Before Handing Off a Java Application

- **Compile:** Provided all APIs, types, annotation processors, source paths, or module paths that `javac` genuinely needs.
- **Run:** Packaged/provided all classes, implementations, and resources used by critical execution paths.
- **Version:** Compile and runtime dependencies are binary/API compatible; no unintended duplicate-class JARs.
- **Launch:** Confirmed whether the application uses `java -cp`, `java -jar`, module path, or a custom class loader and configured loading paths according to the exact mechanism.
- **Environment:** Runtime JDK supports the bytecode; working directory and environment configuration are appropriate.
- **Validation:** Tested both `javac` success **and** launch/runtime scenarios with dynamic dependencies, rather than stopping at build success.
- **Reproducibility:** Used Gradle/Maven, locked or managed required versions, and verified the released artifact.

Distinguishing the two kinds of dependencies helps you ask the right question when an error occurs: **does `javac` lack a definition to understand the source code, or does the JVM lack (or receive the wrong) definition to execute the bytecode?** Answering that question is the first step toward properly handling the classpath, build configuration, and application packaging.