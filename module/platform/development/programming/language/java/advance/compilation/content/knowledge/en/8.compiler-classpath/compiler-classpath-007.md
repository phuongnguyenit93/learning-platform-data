# Limitations of Wildcards in Dependency Paths (Java Classpath)

## 1. What Problem Does the Classpath Wildcard Solve?

When compiling or running Java with a **classpath**, a program often needs multiple libraries packaged as JARs. You can list each library individually:

~~~bash
java -cp 'build/classes:lib/alpha.jar:lib/beta.jar' demo.app.Main
~~~

This is exact yet inconvenient when a directory holds many JARs. The **classpath wildcard** syntax lets you replace a list of JARs directly inside a directory with the `*` character as the **final component of the path**, for example:

~~~bash
java -cp 'build/classes:lib/*' demo.app.Main
~~~

The command above uses a classpath with two logical entries: the application's class directory and the set of JARs expanded from `lib/*`. This wildcard is **not an arbitrary file-matching mechanism**; it does not download dependencies from the internet, read Maven version metadata, or recursively collect JARs inside subdirectories.

This lesson focuses on wildcard limitations in **dependency paths** when using `javac` and `java` with JDK 17+; it also explains when explicit paths or build tools are needed to avoid hard-to-reproduce errors.

## 2. Supported Syntax: Entries Whose Basename Is *

In the Java launcher's classpath, an entry of the form `lib/*` represents **files ending in `.jar` or `.JAR` located directly in the `lib` directory**. An entry consisting solely of `*` represents JARs directly in the current working directory.

Example directory:

~~~text
project/
├── lib/
│   ├── alpha.jar
│   ├── beta.JAR
│   ├── .hidden.jar
│   ├── old.zip
│   ├── Extra.class
│   ├── classes/
│   │   └── demo/Helper.class
│   └── nested/
│       └── gamma.jar
└── build/
    └── classes/
        └── demo/app/Main.class
~~~

When using `lib/*`, here is what happens:

| Path | Matched by `lib/*`? | Reason |
| --- | --- | --- |
| `lib/alpha.jar` | Yes | JAR directly inside `lib` |
| `lib/beta.JAR` | Yes | `.JAR` extension is also supported |
| `lib/.hidden.jar` | Yes | Hidden JAR files are still in scope |
| `lib/old.zip` | No | Wildcard selects only `.jar`/`.JAR`, though ZIPs can be listed explicitly in classpath |
| `lib/Extra.class` | No | Does not collect loose `.class` files |
| `lib/classes/demo/Helper.class` | No | Does not add class directories to classpath |
| `lib/nested/gamma.jar` | No | Does not recursively scan subdirectories |
| `build/classes/demo/app/Main.class` | No | `build/classes` is a separate entry, not inside `lib/*` |

The syntax `lib/*.jar` **is not a Java-defined classpath wildcard pattern**; the asterisk of the classpath feature is an entry *basename* `*`, not a user-written suffix filter pattern. Likewise, `lib/**`, `lib/a*.jar`, and `lib/{a,b}.jar` are not JAR wildcard syntaxes provided by the Java launcher. If a command with such patterns appears to work, the shell or a wrapper tool likely expanded them **before** Java received the arguments.

**Practical consequence:** if the application needs loose classes inside `lib/classes`, add that directory as a **separate entry**; if it needs JARs in `lib/nested`, also declare `lib/nested/*` or specific JAR paths.

## 3. What Is "Wildcard Expansion" and When Does It Happen?

The classpath is a list of locations that class loaders/compiler tools use to locate matching classes or resources under classpath rules. Each entry can be a class directory, a supported JAR/ZIP file, or a JAR wildcard entry.

For the command:

~~~bash
java -cp 'build/classes:lib/*' demo.app.Main
~~~

The Java launcher expands `lib/*` into the list of JARs directly inside `lib` **before entering the `main` method**. Diagram explanation:

~~~text
Input classpath       build/classes : lib/*
                            |
                            v
Java launcher      lists JARs directly inside lib/
                            |
                            v
Runtime classpath  build/classes : lib/alpha.jar : lib/beta.JAR : ...
                            |
                            v
                     loads demo.app.Main
~~~

The `:` in the diagram is the separator on Linux/macOS. Windows uses `;`. When JARs exist, the JVM's `java.class.path` property typically reflects the expanded path list; **do not rely on the ordering of that string as a stable contract**.

A new JAR placed in `lib` after the JVM has started **is not automatically picked up again by the wildcard**. Expansion occurs before running the application, not each time a class loader searches for a class. Changing the library set of a running process requires an appropriate class-loading mechanism or restarting with a new classpath.

Distinguish this as a feature of the **Java launcher/JDK tools**. An application embedding the JVM or building a custom class loader is not required to support wildcards in its own input strings.

## 4. Shell Wildcards Differ from Java Classpath Wildcards

There are two completely different processors that both use `*`:

- **Shell expansion/globbing:** before launching the program, the shell may replace `lib/*` with multiple filenames and directories.
- **Java classpath expansion:** the Java launcher receives **a single classpath argument** containing `*`, then expands JARs by its own rules.

On Bash, **quote the entire classpath**:

~~~bash
# Bash/Linux/macOS: recommended syntax
javac -cp 'lib/*' -d build/classes src/demo/app/Main.java
java -cp 'build/classes:lib/*' demo.app.Main
~~~

Using single quotes here makes Bash pass the literal string `lib/*` or `build/classes:lib/*` to Java. Without quotes, the shell may expand `lib/*` beforehand into multiple separate arguments. Then `-cp` consumes only one argument as the classpath, while subsequent filenames may be misinterpreted as the main class, source file, or invalid arguments; the outcome depends on the shell and directory contents.

In PowerShell on Windows, you should also quote:

~~~powershell
# Windows: separator between classpath entries is a semicolon.
javac -cp 'lib/*' -d build/classes src/demo/app/Main.java
java -cp 'build/classes;lib/*' demo.app.Main
~~~

The `;` character is PowerShell syntax outside strings, so quote the entire classpath expression. On Windows when invoking `java.exe` and `javac.exe` directly, Java still handles the `lib/*` entry under Java launcher rules, even though PowerShell's wildcard handling differs from Bash.

**Three meanings of the asterisk that must not be confused:**

| Expression | Who processes it? | Meaning |
| --- | --- | --- |
| `lib/*` inside a quoted `-cp` argument | Java launcher/tool classpath | JARs directly inside `lib` |
| `src/*.java` in an unquoted shell command | Shell if it supports globbing | Source filename pattern passed to `javac` |
| `import demo.lib.*;` in Java source | Java compiler per import rules | On-demand import of eligible types in the package; does not scan directories/JARs or import subpackages |

In `javac`, **a classpath wildcard is not a wildcard for selecting source files**. The tool has its own source options and compilation unit selection rules; to compile all `.java` files, use a source set/build tool or an explicit file list, rather than inferring `-cp 'src/*'`.

## 5. Runnable Java 17+ Example: Packaging a JAR and Using a Wildcard

The following example creates **a dependency JAR** built by us, compiles an application against that JAR, and runs it with a classpath wildcard. No internet or external dependencies outside the JDK are needed.

Input structure:

~~~text
project/
├── src/
│   ├── library/demo/lib/Message.java
│   └── app/demo/app/Main.java
├── lib/            # receives JAR files after packaging
└── build/          # receives .class files after compilation
~~~

### 5.1. Library Source: `src/library/demo/lib/Message.java`

~~~java
package demo.lib;

public final class Message {
    private Message() {}

    public static String text() {
        return "JAR_OK";
    }
}
~~~

### 5.2. Application Source: `src/app/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

The two classes are in different packages. The app needs the library at **compile time** to resolve `demo.lib.Message`, and at **runtime** to execute the `Message.text()` call.

### 5.3. Running on Bash/Linux/macOS/Git Bash

From the `project/` directory containing `src/`, after creating the two files above:

~~~bash
mkdir -p build/library build/app lib

# Compile the library from source.
javac --release 17 -encoding UTF-8 -d build/library src/library/demo/lib/Message.java

# Package library classes into a JAR.
jar --create --file lib/message.jar -C build/library .

# Compile app: javac expands 'lib/*' to JARs directly inside lib/.
javac --release 17 -encoding UTF-8 -cp 'lib/*' -d build/app src/app/demo/app/Main.java

# Run: must include both app classes and dependency JARs.
java -cp 'build/app:lib/*' demo.app.Main
~~~

Stdout of the final `java` command is:

~~~text
JAR_OK
~~~

Successful `javac` and `jar` commands normally print no notable output lines. In this example, `lib/message.jar` contains `demo/lib/Message.class`, and `build/app` contains `demo/app/Main.class`.

You can inspect the library contents with:

~~~bash
jar --list --file lib/message.jar
~~~

The listing may include metadata entries such as `META-INF/` and `META-INF/MANIFEST.MF`, along with `demo/lib/Message.class`. The listing order is not what needs to be checked.

### 5.4. Running on Windows/PowerShell

Corresponding directory creation and classpath steps:

~~~powershell
New-Item -ItemType Directory -Force build/library, build/app, lib | Out-Null
javac --release 17 -encoding UTF-8 -d build/library src/library/demo/lib/Message.java
jar --create --file lib/message.jar -C build/library .
javac --release 17 -encoding UTF-8 -cp 'lib/*' -d build/app src/app/demo/app/Main.java
java -cp 'build/app;lib/*' demo.app.Main
~~~

Stdout:

~~~text
JAR_OK
~~~

Source file paths using `/` as shown above are accepted by Java tools and PowerShell in ordinary contexts; the main difference to watch is the **classpath separator**.

### 5.5. Two Intentional Errors to Distinguish Classpath Behavior

**Compilation error:** if `message.jar` is moved elsewhere and you run `javac -cp 'lib/*' ...`, the compiler cannot resolve `demo.lib.Message` because the wildcard finds no dependency. The exact message depends on the JDK, typically `package demo.lib does not exist` or `cannot find symbol`.

**Runtime error:** even when `lib/message.jar` still exists, the command below lacks an entry for **app classes**:

~~~bash
java -cp 'lib/*' demo.app.Main
~~~

In this example `demo.app.Main` resides only in `build/app`, so Java cannot load the main class. **The wildcard adds only the JARs inside `lib`, not all class outputs of the project.**

If the app can launch yet uses a library missing at runtime, it may hit `NoClassDefFoundError`, other linkage errors, or failures when execution reaches that code; do not conclude solely from successful compilation that runtime has all dependencies.

## 6. No Recursive Scanning and No Class Directory Collection

Example:

~~~text
lib/
├── core.jar
├── drivers/
│   ├── jdbc-one.jar
│   └── jdbc-two.jar
└── classes/
    └── sample/Plugin.class
~~~

`lib/*` only matches `core.jar`. To include the two JARs in `drivers` and the loose class in `classes`, list three logical entries:

~~~bash
# Bash/Linux/macOS:
java -cp 'build/app:lib/*:lib/drivers/*:lib/classes' demo.app.Main
~~~

Correspondingly on Windows:

~~~powershell
java -cp 'build/app;lib/*;lib/drivers/*;lib/classes' demo.app.Main
~~~

Explanation:

- `lib/*` → JARs directly inside `lib`.
- `lib/drivers/*` → JARs directly inside `lib/drivers`.
- `lib/classes` → **directory entry**, allowing `lib/classes/sample/Plugin.class` to be found by its package path.

Do not use `lib/**` expecting recursive globbing as in Bash, Gradle, or file-search tools; that is not how Java classpath wildcard expansion works. If the library layout has hundreds of subdirectories, manage dependencies via a build configuration with an explicit list rather than maintaining scattered wildcards.

A ZIP file containing bytecode and supported as a classpath archive by Java tools can be named **explicitly**, e.g., `lib/special.zip`. However, `lib/*` will not collect it, because the wildcard criterion is the **JAR filename extension**, not inspecting archive contents.

## 7. JAR Order Is Not Guaranteed: Risk of Duplicate Classes and Resources

This is a critical limitation when `lib/*` contains multiple JARs:

~~~text
lib/
├── api-v1.jar     # contains demo.api.Service
├── api-v2.jar     # also contains demo.api.Service
└── client.jar
~~~

If two JARs provide the same fully qualified class, a standard classpath class loader searches for the class in entry order. However, **the listing order of JARs expanded by `lib/*` is not specified to be stable**. Do not rely on alphabetical filenames or the order observed in one run to determine whether `api-v1.jar` or `api-v2.jar` wins.

Consequences can include:

- The app runs on one machine yet hits `NoSuchMethodError` or `NoSuchFieldError` on another because an unexpected class version is loaded.
- A resource with a duplicate name appears in multiple JARs; code calling `getResource`/class loaders may pick the first match in search order, leading to hard-to-diagnose differences.
- A class was compiled against one API version while runtime sees another, causing linkage errors during execution.

The solution is to ensure **only one valid version** of each required dependency is selected, and if priority ordering is needed, **list JARs explicitly** on the classpath or let Gradle/Maven's dependency resolver choose versions.

Example of a classpath with deterministic user-defined order (across the listed entries):

~~~bash
java -cp 'build/app:lib/api-v2.jar:lib/client.jar' demo.app.Main
~~~

In that example, every required class must actually exist in the listed JARs. Although explicit entry ordering gives you control over class lookup, do **not** rely on duplicate classes to handle versioning; eliminate duplicates and maintain a clean build dependency graph.

The wildcard also includes hidden JARs at that directory level. Thus, a `.hidden.jar`, backup JAR, or unvetted library with a matching extension in `lib` can silently enter the classpath. Manage the contents of `lib` rather than treating it as an "arbitrary JAR drop-box."

## 8. Wildcards Do Not Resolve Transitive Dependencies

Suppose `analytics.jar` calls APIs from `json.jar`:

~~~text
lib/
├── analytics.jar
└── json.jar
~~~

`lib/*` can place **both** on the classpath because they both sit directly in that directory. That does not mean Java understands that `analytics.jar` *depends on* `json.jar`. The launcher merely expands filenames; it does not read and resolve Maven POM/Gradle metadata to fetch missing JARs, choose compatible versions, or resolve version conflicts.

If `json.jar` is not in `lib` but sits under `lib/transitive/json.jar`, `lib`'s wildcard will not descend to find it. If a dependency requires native libraries, data files, configuration, or module service providers, merely adding the JAR may still not satisfy runtime requirements.

Therefore:

- For very small exercises or a pre-bundled set of JARs, `lib/*` is convenient.
- For projects with multi-layered dependency graphs or reproducibility requirements, use Gradle/Maven to pin and resolve dependencies, then supply the runtime classpath generated by the build tool.
- For distributable products, consider a valid manifest classpath, explicit startup scripts, or standard packaging per your tooling, instead of expecting wildcards to handle every dependency.

## 9. Both javac and java Need the Classpath in Their Respective Phases

`javac` needs the **compile classpath** to locate APIs used by the Java source. `java` needs the **runtime classpath** to load classes and resources when the program executes.

In the example from section 5:

~~~text
Compile library:
  source       src/library/demo/lib/Message.java
  output       build/library

Package library:
  input        build/library
  output       lib/message.jar

Compile app:
  source       src/app/demo/app/Main.java
  classpath    lib/*
  output       build/app

Run app:
  main         demo.app.Main
  classpath    build/app + lib/*
~~~

Adding `-cp 'lib/*'` at compile time does not embed JARs into the `build/app` output. `javac -d build/app` only writes classes generated by the compiler. At runtime you must add the dependency JARs to the classpath, unless you use another valid packaging mechanism that bundles dependencies.

Conversely, adding `build/app` to the runtime classpath does not bring JARs along; dependency failures appear only along code paths referencing missing classes. When replacing a library, re-verify both compile and runtime, not merely whether the launcher finds the main class.

**Do not confuse `sourcepath` and `classpath`:** `javac --source-path src/main/java` tells the compiler to search for **source files**; `javac -cp 'lib/*'` tells the compiler to search for **compiled classes inside JARs**. The special JAR classpath wildcard is not a general syntax for `--source-path`, `--module-source-path`, or package names.

## 10. java -jar, JAR Manifest, and Wildcard Limitations

The command `java -jar app.jar` runs in **executable JAR** mode. In this mode, a user classpath declared via `-cp` or the `CLASSPATH` environment variable does not become an extra class-search source as it does with `java -cp ... MainClass`. How dependencies are supplied depends on JAR packaging and the manifest.

The following **is not a reliable command to add `lib/*`** for an executable JAR:

~~~bash
java -cp 'lib/*' -jar app.jar
~~~

If `app.jar` requires external JARs, you can use the supported manifest `Class-Path` mechanism, or invoke the main class via `-cp` with both the app JAR and dependency JARs:

~~~bash
# Sample structure only: app.jar must actually contain demo.app.Main.
java -cp 'app.jar:lib/*' demo.app.Main
~~~

On Windows replace `:` with `;`.

**The classpath wildcard is not expanded in the manifest `Class-Path` attribute.** Writing:

~~~text
Class-Path: lib/*
~~~

is not equivalent to `java -cp 'lib/*'`. In the manifest, list individual JARs with proper relative syntax, for example:

~~~text
Class-Path: lib/alpha.jar lib/beta.jar
~~~

This snippet belongs to the **main section** of the manifest, not a complete manifest. Manifest paths are resolved relative to the JAR's location and the JAR spec's URL rules, not simply the shell's working directory. Do not manually add this entry if JAR distribution is already managed by a packaging plugin.

Also do not confuse the classpath wildcard with the `-jar` option or the `jar` command: `jar --create --file ...` is an archive creation tool, not a runtime dependency resolution mechanism.

## 11. Module Path (JPMS) Does Not Share Classpath Wildcard Syntax

Since Java 9, **named modules** can be located via `--module-path` (`-p`), while classpath code resides in the **unnamed module**.

- `--class-path 'lib/*'`: mechanism expanding direct classpath JARs.
- `--module-path lib`: declares **a directory containing modules** for the module system to locate and resolve by module name (when structured appropriately).
- `--module-source-path`: points to source locations following module layout, completely different from expanding JAR dependencies.

Do not casually turn `--module-path lib` into `--module-path 'lib/*'` assuming the asterisk behaves like on the classpath. The module path has its own directory/JAR module rules and resolves via `module-info.java`, `requires`, and `exports`; pass valid module paths. A JAR may act as an automatic module on the module path depending on its contents and naming rules, yet that does not make the classpath wildcard a module-resolution tool.

For plugins or libraries requiring JPMS, verify the module graph and whether each dependency is a named/automatic/unnamed module before choosing `-p` or `-cp`.

## 12. Gradle/Maven Have Their Own Dependency Selection Mechanisms

In Gradle (Groovy DSL), local libraries can be added as a file collection:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation fileTree(dir: 'lib', include: ['*.jar'])
}
~~~

This snippet sits in a `build.gradle` with the Java plugin and illustrates a **Gradle-selected file collection**. The `*.jar` pattern here is a **Gradle pattern**, not a classpath wildcard expanded by the Java launcher. This explains why `lib/*.jar` is valid in Gradle configuration while `java -cp 'lib/*.jar'` is not valid Java JAR wildcard syntax.

Once specific artifacts are known, declaring module dependencies by coordinates and version is much easier to manage:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.example:artifact-name:1.2.3'
}
~~~

`org.example:artifact-name:1.2.3` is only **illustrative coordinates**, not claiming that this artifact exists or is downloadable. In a real project, use the exact coordinates of your chosen dependency. Gradle builds compile/runtime classpaths using configurations and dependency resolution, without necessarily turning that setup into a `lib/*` string in a user-facing script.

In Maven, dependencies are managed via `<dependency>` declarations with `groupId`, `artifactId`, `version`, and the appropriate scope in `pom.xml`; do not replace version selection with a wildcard JAR directory. If local JARs are unavoidable, manage their provenance and distribution clearly.

**The problem with lumping all JARs together:** a `lib` directory might hold test tools, annotation processors, outdated JARs, or compile-only dependencies. Dumping them all onto the runtime classpath with `lib/*` bloats the classpath and obscures dependency scope. Build tools distinguish `implementation`, `runtimeOnly`, and `testImplementation` by lifecycle.

## 13. Diagnosing: Verifying That the Wildcard Actually Expanded

You can inspect the runtime classpath with a small standalone Java program `ShowClasspath.java`:

~~~java
public class ShowClasspath {
    public static void main(String[] args) {
        System.out.println(System.getProperty("java.class.path"));
    }
}
~~~

Compile:

~~~bash
javac --release 17 ShowClasspath.java
~~~

If the file is in the working directory and `lib` contains several JARs, run on Unix:

~~~bash
java -cp '.:lib/*' ShowClasspath
~~~

On Windows:

~~~powershell
java -cp '.;lib/*' ShowClasspath
~~~

The output is the classpath string reported by the Java runtime; **the exact value varies** with the present JARs, OS, separator, and expansion order. Do not assert a fixed stdout for this check. When valid JARs exist, you will typically see `lib/name.jar` files listed in place of the wildcard entry.

You can inspect a JAR directly with `jar --list --file lib/message.jar`; check class resolution via compiler/runtime errors or an appropriate class-loading inspection tool such as `java -Xlog:class+load=info` on HotSpot JDK 17+ (which produces lots of logs with an unstable format). These methods answer different questions:

1. **Does the classpath string contain the expected entries?**
2. **Does each archive contain the required classes/packages?**
3. **From which archive does runtime actually load the class?**
4. **Do multiple versions define the same class?**

An essential verification step is starting from **clean output**, keeping only the JARs the application needs, and re-running `javac` and `java` with an explicit classpath. Never take a program "accidentally working" on a machine with a long-lived `lib` folder as proof that dependencies are properly configured.

## 14. Summary of Limitations and Remedies

| Goal | Does `lib/*` support it? | Correct configuration |
| --- | --- | --- |
| All JARs directly inside `lib` | Yes | `-cp 'lib/*'` |
| Only JARs matching `a*.jar` | Not a classpath wildcard | List files or use a build tool pattern |
| Collect JARs across all subdirectories | No | Add each `dir/*` root or use a build tool |
| Collect loose `.class` files in `lib/classes` | No | Add `lib/classes` as a classpath entry |
| Collect `.zip` files in a directory via wildcard | No | List specific `.zip` files if appropriate |
| Choose order among multiple JARs with duplicate classes | No | List JARs in order and remove duplicates |
| Automatically resolve/transitively download dependencies | No | Use Gradle/Maven with appropriate lock/version policy |
| Apply `*` in manifest `Class-Path` | No | Write each JAR per manifest syntax |
| Apply the same `*` to module path | No | Use valid module paths and declare the module graph |
| Add libraries to `java -jar` via `-cp` | Not like `java -cp Main` | Use manifest, packaging, or invoke main with `-cp` |
| Automatically pick all `.java` files to compile | No | Select source files/source sets with `javac` or a build tool |

### Checklist Before Accepting a Command Using a Wildcard

- **Directory:** are the required JARs located directly inside the specified directory?
- **Extension:** do the files end in `.jar`/`.JAR` per Java rules, or are they `.zip`, `.class`, or subdirectories?
- **Shell:** is the classpath quoted so Bash/PowerShell does not misinterpret it?
- **Separator:** does the classpath list use `:` for Unix or `;` for Windows?
- **Main classes:** has the output containing the main class been added alongside the wildcard?
- **Compile vs runtime:** are dependencies present in both required phases or only one?
- **Duplicate:** does the directory contain multiple versions of the same class/resource?
- **Packaging:** are you running via `java -cp`, `java -jar`, or `--module-path`? They follow different rules.
- **Reproducibility:** are the versions and contents of the JAR directory controlled in CI/deployment?

### Practical Exercises

From the section 5 example, run sequentially:

1. Keep `message.jar` in `lib`, compile and run `java -cp 'build/app:lib/*' demo.app.Main`, and confirm `JAR_OK`.
2. Move `message.jar` into `lib/nested` in a test copy; observe that `lib/*` no longer detects the library. Add `lib/nested/*` to the classpath to fix it.
3. Try removing `build/app` from the runtime classpath and observe that the main class is not found.
4. Place a `.zip` or `.class` file inside `lib`; verify that the wildcard does not pick it up as a new dependency JAR.
5. Create `ShowClasspath.java` from section 13 to observe the actually expanded paths. Do not assert a fixed JAR string order.

**Core message:** the Java classpath wildcard is a shorthand for **the list of JARs directly inside a directory**. It does not replace source selection, recursive file matching, module resolution, or dependency management. Understanding this boundary helps prevent missing-class errors, wrong-version selection, and builds that only work by coincidence in a single environment.

## References

- [Oracle Java SE 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--class-path` syntax and JAR wildcard expansion rules.
- [OpenJDK — wildcard.c](https://github.com/openjdk/jdk/blob/master/src/java.base/share/native/libjli/wildcard.c): notes on `*` scope, non-recursiveness, exclusion of `.class`/`.zip`, JAR order, and limitations with manifests/module paths.