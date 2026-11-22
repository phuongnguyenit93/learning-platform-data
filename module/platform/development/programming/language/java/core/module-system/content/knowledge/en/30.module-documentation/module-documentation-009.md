# Minimal Buildable and Runnable Modular Example

This hands-on walkthrough builds a small yet complete **Java Platform Module System (JPMS)** application consisting of **two named modules**: one module providing a greeting API and an application module using that API. You will create `module-info.java` files, compile with `javac`, run with `java --module-path -m`, and then package into modular JARs that can run standalone from a distribution directory.

The entire example uses the standard JDK, **requiring no Maven, Gradle, or third-party libraries**. If you replicate the layout and source code exactly, the commands run on JDK 17 and later; JPMS was introduced in Java 9.

## 1. Expected outcome

When finished, you will have:

- Module `com.example.greeting` supplying a public `Greeter` class in an exported package.
- Module `com.example.app` declaring `requires com.example.greeting;` and calling `Greeter`.
- Two compiled module directories under `out/`.
- Two modular JARs under `dist/`.
- Launch commands using the module path and a root module.

Example run:

```shell
java --module-path out --module com.example.app/com.example.app.Main
```

Output:

```text
Hello, Java!
```

Passing a name via command-line argument:

```shell
java --module-path out -m com.example.app/com.example.app.Main Lan
```

Output:

```text
Hello, Lan!
```

This example clearly demonstrates two core concepts: **`requires` establishes readability between modules** and **`exports` exposes an API package**. If either is missing, the application module using the `Greeter` class is invalid under the JPMS access model.

## 2. Preparing the environment

A **JDK** must be installed, not merely a slimmed-down runtime lacking a compiler. Tools used:

- `java`: launches the application.
- `javac`: compiles Java sources and module descriptors.
- `jar`: packages modular JARs and inspects descriptors.
- `jdeps`: optional, used to analyze dependencies after building.

Verify the JDK in your terminal:

```shell
java -version
javac -version
jar --version
```

Example output might show `17`, `21`, or a newer JDK version. Importantly, `java` and `javac` should belong to the same appropriate toolchain, especially if multiple Java versions are installed.

If `javac` is not recognized, check that a JDK is installed and its `bin` directory is on `PATH`. On systems managing multiple JDKs, you can use full paths to `java`, `javac`, and `jar` instead of relying on `PATH`.

Commands in this walkthrough are run from the **project root directory**. Files must be created with the exact declared names and packages. On Windows you can use PowerShell; on Linux/macOS use a standard shell.

## 3. Project layout

Create a directory, e.g. `jpms-hello`, with this layout:

```text
jpms-hello/
└── src/
    ├── com.example.greeting/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greeting/
    │               └── api/
    │                   └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Notes:

1. `src/com.example.greeting` and `src/com.example.app` are **two module source roots**.
2. Each module has a `module-info.java` at the module root.
3. Subdirectories beneath each module root correspond to Java package names.
4. `out/` and `dist/` are created in later steps and do not belong in the source tree.

This layout matches the command:

```shell
javac --module-source-path src -d out -m com.example.greeting,com.example.app
```

If using a different source layout, adjust `--module-source-path` accordingly. The compiler does not automatically infer module structure from arbitrary directory layouts.

## 4. Creating the API provider module: com.example.greeting

### 4.1. Writing module-info.java

Create `src/com.example.greeting/module-info.java`:

```java
/**
 * Provides a simple greeting API.
 *
 * <p>Other modules use the Greeter class via the
 * com.example.greeting.api package.
 */
module com.example.greeting {
    exports com.example.greeting.api;
}
```

The module descriptor has two meanings:

- `module com.example.greeting`: names the named module.
- `exports com.example.greeting.api;`: allows other modules reading `com.example.greeting` to use `public` types in that API package.

This module does not need to declare `requires java.base;`, because every named module reads `java.base` implicitly. Fundamental types like `String` reside there.

### 4.2. Writing the Greeter class

Create `src/com.example.greeting/com/example/greeting/api/Greeter.java`:

```java
package com.example.greeting.api;

/**
 * API for creating a greeting with a recipient name.
 */
public final class Greeter {

    /**
     * Returns a greeting for the given name.
     *
     * @param name recipient name
     * @return greeting string
     */
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

The `Greeter` class is `public` and resides in the exported `com.example.greeting.api` package. Therefore, another module with appropriate readability can instantiate it and call `greet`.

If you omit `public` from the class declaration, other modules cannot use that class as a public API even though the package is exported. `exports` does not make package-private types or members public.

## 5. Creating the application module: com.example.app

### 5.1. Writing module-info.java

Create `src/com.example.app/module-info.java`:

```java
/**
 * Application demonstrating how to use another API module.
 */
module com.example.app {
    requires com.example.greeting;
}
```

The `requires com.example.greeting;` directive states that the app needs to read module `com.example.greeting`. When Java resolves the app as a root module, this dependency must be discoverable from the module path or an appropriate module source.

The app does not need `exports com.example.app;`, because `Main` serves only as the program entry point; no consumer module needs to import that package. An application's main class does not have to live in an exported package.

### 5.2. Writing Main.java

Create `src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "Java" : args[0];

        Greeter greeter = new Greeter();
        System.out.println(greeter.greet(recipient));
    }
}
```

Distinguish two elements:

- `import com.example.greeting.api.Greeter;` lets source code refer to the class by its short name `Greeter`.
- `requires com.example.greeting;` in the descriptor declares the dependency between modules.

`import` does not replace `requires`; nor does `requires` automatically make unexported packages accessible. The two modules in the example cooperate via **readability** on the app side and **exports** on the greeting side.

## 6. Compiling with javac --module-source-path

Open a terminal in the `jpms-hello` directory and run:

```shell
javac --module-source-path src -d out -m com.example.greeting,com.example.app
```

Explanation of arguments:

| Argument | Meaning |
|---|---|
| `--module-source-path src` | Directory containing module sources |
| `-d out` | Output directory for compilation |
| `-m com.example.greeting,com.example.app` | Source modules requested to compile |

Upon successful compilation, the output typically looks like:

```text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

`module-info.java` is compiled into `module-info.class`, containing the module descriptor as JVM-compatible metadata. Compiled modules inside `out/` are called **exploded modules**.

When using `--module-source-path`, the compiler can find source code for both the app module and the greeting dependency. If a module requires another module that is missing from the source path, module path, or system modules, the compiler reports an error.

### 6.1. Do not use javac -cp in the legacy way

The traditional way:

```shell
javac -cp libs/* ...
```

supplies libraries via the classpath. It does not establish a named-module configuration like `--module-source-path` or `--module-path`. In this walkthrough, both `module-info.java` and source code must be compiled into named modules to get true JPMS.

### 6.2. Two-pass compilation (for reference)

If you want to compile the dependency first and the app second, you can do:

```shell
javac -d out/com.example.greeting src/com.example.greeting/module-info.java src/com.example.greeting/com/example/greeting/api/Greeter.java
```

Then:

```shell
javac --module-path out -d out/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
```

The second pass uses `--module-path out` to locate the just-compiled exploded module `com.example.greeting`. This illustrates the difference between **module-source-path** (finding sources) and **module-path** (finding compiled modules).

The single-command approach at the start of this section is simpler for this walkthrough.

## 7. Running exploded modules directly

After compiling, run:

```shell
java --module-path out --module com.example.app/com.example.app.Main
```

Equivalent short form:

```shell
java -p out -m com.example.app/com.example.app.Main
```

Output:

```text
Hello, Java!
```

Running with an argument:

```shell
java -p out -m com.example.app/com.example.app.Main Minh
```

Output:

```text
Hello, Minh!
```

Here:

- `-p out` specifies the location of compiled modules.
- `-m com.example.app/com.example.app.Main` selects the startup module and the class containing `main`.
- `Minh` is the first element of the `String[] args` array, not part of the module name.

At startup, the Java launcher locates module `com.example.app`, reads its descriptor, discovers the `com.example.greeting` dependency, and resolves both modules. The app can then use `Greeter` through the exported package.

## 8. What happens during module resolution?

The module graph of this walkthrough:

```text
       com.example.app
              |
              | requires
              v
    com.example.greeting
              |
              | implicit requires
              v
           java.base
```

Module `java.base` already resides in the runtime image. There is no need to package or copy it into `out/`.

At launch:

1. Java finds `com.example.app` on the module path and selects it as a root module.
2. The resolver reads `requires com.example.greeting;`.
3. The resolver finds `com.example.greeting` on the module path.
4. Needed system modules, such as `java.base`, are handled under platform rules.
5. The module graph is formed; the runtime defines the modules and appropriate class loaders.
6. The launcher locates `com.example.app.Main` and invokes its `main` method.
7. The app uses the `Greeter` API from the greeting module.

Not every JAR present on the module path is automatically resolved. The resolver starts from root modules and dependency edges; options such as `--add-modules` can add extra root modules to the graph when needed.

## 9. Packaging into modular JARs

When distributing an application, each module is typically packaged into a JAR.

Create the `dist` directory.

On Linux/macOS:

```shell
mkdir -p dist
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path dist | Out-Null
```

Package the greeting module:

```shell
jar --create --file dist/com.example.greeting.jar -C out/com.example.greeting .
```

Package the app module:

```shell
jar --create --file dist/com.example.app.jar -C out/com.example.app .
```

The distribution directory becomes:

```text
dist/
├── com.example.greeting.jar
└── com.example.app.jar
```

Each JAR has `module-info.class` at its root, making it an **explicit modular JAR**. The module name comes from the descriptor, not automatically from the `.jar` filename. In this example, filenames match module names for clarity, though that is merely a convention.

Inspect contents:

```shell
jar --list --file dist/com.example.greeting.jar
jar --list --file dist/com.example.app.jar
```

You will see `module-info.class`, class files, and JAR metadata.

## 10. Running the application from modular JARs

Replace `out` with `dist` on the module path:

```shell
java --module-path dist --module com.example.app/com.example.app.Main
```

Expected output:

```text
Hello, Java!
```

To pass an argument:

```shell
java -p dist -m com.example.app/com.example.app.Main "Learn JPMS"
```

Output:

```text
Hello, Learn JPMS!
```

The quotes around `"Learn JPMS"` keep the phrase as a single command-line argument.

Another option is recording the **main class** when packaging the app module:

```shell
jar --create --file dist/com.example.app.jar --main-class com.example.app.Main -C out/com.example.app .
```

The command above recreates the app JAR with main class metadata. You can then run it without specifying the class name after `/`:

```shell
java --module-path dist --module com.example.app
```

If no main class was recorded in the module artifact, continue using `-m com.example.app/com.example.app.Main` to specify the program entry point.

## 11. Inspecting the module descriptor after packaging

Use `jar --describe-module` to inspect metadata:

```shell
jar --describe-module --file dist/com.example.greeting.jar
```

Details to note:

- Module name: `com.example.greeting`.
- Exported package: `com.example.greeting.api`.
- Relationship to `java.base`.

For the app:

```shell
jar --describe-module --file dist/com.example.app.jar
```

What you should see is the dependency on `com.example.greeting`; if packaged with `--main-class`, the descriptor displays the corresponding main class info.

Whenever `module-info.java` changes, you must **recompile and repackage** so the JAR contains the new descriptor. Editing the `.java` file after creating a JAR does not automatically update metadata inside the released artifact.

## 12. Observing module resolution at runtime

The Java launcher offers helpful options for inspecting configuration:

**List observable modules:**

```shell
java --module-path dist --list-modules
```

The list includes system modules and modules discoverable on the module path. It does not prove every module is resolved when running the app.

**Describe a module:**

```shell
java --module-path dist --describe-module com.example.app
```

**Print resolution steps:**

```shell
java --show-module-resolution --module-path dist -m com.example.app/com.example.app.Main
```

You can look for lines indicating the app module reading greeting. Detailed output varies by JDK version.

**Attempt module graph initialization without running main:**

```shell
java --show-module-resolution --dry-run --module-path dist -m com.example.app/com.example.app.Main
```

`--dry-run` is useful when checking resolution and module setup without executing logic inside `main`. It does not replace running the application to observe business results.

**Validate module path structure:**

```shell
java --module-path dist --validate-modules
```

This command helps detect issues such as duplicate module names or package conflicts. For a properly structured minimal example, no validation errors are expected.

## 13. Checking static dependencies with jdeps

`jdeps` reads class files/JARs and analyzes dependencies:

```shell
jdeps --module-path dist --list-deps dist/com.example.app.jar
```

When analyzing the app module, you expect to see the dependency on `com.example.greeting` and required system modules. This command is useful as a codebase grows and you want to see dependencies inferred from bytecode and metadata.

To see package-level dependencies:

```shell
jdeps --module-path dist -verbose:package dist/com.example.app.jar
```

`jdeps` does not fully detect dependencies loaded dynamically via reflection, `ServiceLoader`, or string class names. In this minimal example, dependencies are explicit, making them easy for the tool to observe.

## 14. Distinguishing module path and classpath

Two launch commands can look similar yet are not equivalent.

**Module path (JPMS):**

```shell
java --module-path dist -m com.example.app/com.example.app.Main
```

Java uses `module-info.class`, resolves `requires`, and enforces `exports` boundaries and module rules.

**Traditional classpath:**

```shell
java --class-path "dist/*" com.example.app.Main
```

When modular JARs are placed on the classpath as classpath libraries, classes are loaded under the unnamed module model of the corresponding class loader rather than an explicit module graph resolved from `--module-path`.

When both JARs are on the classpath, the code may still run, yet you are no longer testing the JPMS boundaries you designed. Because the goal of this walkthrough is a **modular** application, use `--module-path` and `-m`.

Similarly, `java -jar dist/com.example.app.jar` is not equivalent to `java -m com.example.app`: `-jar` uses the manifest `Main-Class` and JAR/classpath launch semantics, and does not make the JAR a root named module merely because it contains `module-info.class`.

## 15. Experimenting with descriptor edits to understand requires and exports

You can run small experiments after building and running successfully.

### 15.1. Removing requires from app

Change the app descriptor to:

```java
module com.example.app {
}
```

Keep `import com.example.greeting.api.Greeter;` in `Main.java` and recompile. The compiler will prevent the app module from using the greeting API in the normal way because `app` does not read `greeting`.

This is a **readability** error. Having the greeting JAR on the module path does not replace the `requires` relationship.

Restore:

```java
module com.example.app {
    requires com.example.greeting;
}
```

### 15.2. Removing exports from greeting

Keep `requires com.example.greeting;` in `app`, but change greeting's descriptor to:

```java
module com.example.greeting {
}
```

Recompile. `app` can read `greeting`, yet package `com.example.greeting.api` is not exported outward. The compiler will report that the package is not accessible to `app`.

This is a **package encapsulation** error, not a missing module.

Restore:

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

### 15.3. Misspelling the module name

If `app` declares:

```java
requires com.example.greeter;
```

while the actual module is `com.example.greeting`, the compiler/resolver will report the module cannot be found. JPMS uses exact **module names**, and does not substitute similar class or package names.

These three experiments help distinguish three failure modes: missing module, missing readability, and unexported package.

## 16. Common build/run errors

### Error 1: `javac: command not found`

Cause: no JDK compiler on `PATH`, or running in a runtime-only environment.

Fix: install an appropriate JDK, check `javac -version` and `java -version`. No source code changes are needed.

### Error 2: Module app not found

The message may look like:

```text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.app not found
```

Check:

- Did `javac` succeed?
- Does `out/com.example.app/module-info.class` exist?
- Does `--module-path` point to `out` rather than a wrong directory level?
- Does the module name in `-m` match the descriptor?
- If running modular JARs, is the app JAR inside `dist`?

### Error 3: Greeting dependency not found

`app` has `requires com.example.greeting;`, yet the greeting module is absent from the module path or was not compiled/packaged.

Check the `out/com.example.greeting` folder or `dist/com.example.greeting.jar`, then inspect its descriptor:

```shell
jar --describe-module --file dist/com.example.greeting.jar
```

### Error 4: Package not exported

If you see a message indicating a package belongs to another module but is not exported, check that greeting's descriptor has:

```java
exports com.example.greeting.api;
```

Do not try to work around the error by putting all classes on the classpath; that defeats the goal of learning JPMS.

### Error 5: Invalid main class

The following command uses the class's binary name:

```shell
java -p out -m com.example.app/com.example.app.Main
```

If the package is misspelled, `Main.class` is missing, or the class was renamed without updating the command, the launcher cannot find the entry point. Check the package declaration and output layout.

### Error 6: Wrong module source root level

With the command:

```shell
javac --module-source-path src -d out -m com.example.app,com.example.greeting
```

the compiler expects `src` to contain subdirectories matching each module, each with its own `module-info.java`. If you put a single `src/module-info.java` for both modules or misplace source files, the compiler may report source modules not found or source files outside expected modules.

### Error 7: Running on Windows using `:` for multiple paths

With a single module path such as `out` or `dist`, syntax is identical across OSes. When multiple paths are present:

Windows:

```powershell
java --module-path "dist;third-party" -m com.example.app/com.example.app.Main
```

Linux/macOS:

```shell
java --module-path "dist:third-party" -m com.example.app/com.example.app.Main
```

Do not confuse the module path separator with the `/` in `module/main-class` syntax.

## 17. An even smaller single-module version

Two modules clearly demonstrate `requires` and `exports`. If you just want to see how one named module runs on its own, a single-module version is even smaller:

```text
single/
└── src/
    └── com.example.simple/
        ├── module-info.java
        └── com/example/simple/Main.java
```

Descriptor:

```java
module com.example.simple {
}
```

Main:

```java
package com.example.simple;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello modular Java!");
    }
}
```

Compile from the `single` directory:

```shell
javac --module-source-path src -d out -m com.example.simple
```

Run:

```shell
java --module-path out -m com.example.simple/com.example.simple.Main
```

Output:

```text
Hello modular Java!
```

Why are there no `requires` and `exports`? The module only uses APIs from `java.base` and has no packages to expose to external modules. It is still an explicit named module because it has `module-info.java`.

However, the two-module version in earlier sections should serve as the main exercise when learning **module graphs** and dependency access.

## 18. How can this example be placed in a project README?

A practical README for a modular application should include these sections:

1. **Requirements:** minimum JDK version and build tool if any.
2. **Source layout:** module roots and actual module names.
3. **Module responsibilities:** which module provides APIs, which is the entry point.
4. **Build command:** one or a few commands runnable from the root directory.
5. **Run command:** exact `--module-path` and `-m module/main-class`.
6. **Expected output:** concrete output for readers to verify against.
7. **Packaging:** how to create modular JARs if distribution is needed.
8. **Troubleshooting:** module not found, exports, main class, and toolchain errors.
9. **Module inspection:** `jar --describe-module` and `--show-module-resolution`.
10. **Versioning:** JDK/toolchain versions the commands were designed to support.

When a project uses Maven or Gradle, manual `javac`/`jar` commands can be replaced with the corresponding build commands, while keeping the **`java -p ... -m ...` command or describing its equivalent clearly**. This proves the application truly runs in modular mode rather than accidentally running on the classpath.

## 19. Walkthrough verification checklist

- [ ] JDK installed and `java`, `javac`, `jar` run properly.
- [ ] Two module source roots match `com.example.greeting` and `com.example.app`.
- [ ] Each module has `module-info.java` at its root.
- [ ] Greeting exports `com.example.greeting.api`.
- [ ] App declares `requires com.example.greeting;`.
- [ ] `Greeter.java` and `Main.java` declare matching packages.
- [ ] `javac --module-source-path src -d out -m com.example.greeting,com.example.app` completes.
- [ ] `out` contains two exploded modules and corresponding `module-info.class` files.
- [ ] `java -p out -m com.example.app/com.example.app.Main` prints the greeting.
- [ ] Both JARs created in `dist`.
- [ ] `jar --describe-module` shows the right module names and directives.
- [ ] `java -p dist -m com.example.app/com.example.app.Main` runs cleanly.
- [ ] If using `-m com.example.app`, the app JAR has main class metadata.
- [ ] No `--add-exports` or `--add-opens` options needed for the basic example.

## Conclusion

A minimal JPMS example that still demonstrates real dependencies requires at least two named modules: one providing an API and one consuming that API. Module `com.example.greeting` declares `exports com.example.greeting.api;`, while `com.example.app` declares `requires com.example.greeting;` and has class `Main`.

With a modular source layout, a single command `javac --module-source-path src -d out -m com.example.greeting,com.example.app` compiles both. Then `java --module-path out -m com.example.app/com.example.app.Main` runs the exploded modules directly. When packaged into JARs, replace `out` with `dist` on the module path, keeping the root module and main class the same.

This example builds the foundation for learning subsequent JPMS topics such as `requires transitive`, qualified exports, `opens`, service binding, module layers, and migrating from the classpath. Mastering how to build and run a simple example makes it easier to distinguish source code errors from module resolution or package access errors in larger projects.
