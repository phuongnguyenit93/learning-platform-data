# `java -jar` Mode and Related Classpath Rules

`java -jar` is a mode for launching a Java application from an **executable JAR**. What matters is not just how to invoke the command, but **how the JVM determines the `main` class and the search path for other classes/dependencies**. When this mode is selected, standard classpath options are ignored; instead, the specified JAR together with the `Class-Path` attribute in the manifest (if present) determines the application entries on the class search path.

A brief model:

```text
java [JVM options] -jar app.jar [program arguments]
                             |
                             v
                 Read META-INF/MANIFEST.MF
                             |
                    Main-Class: demo.Main
                             |
                    Class-Path: lib/helper.jar
                             |
                 +-----------+-------------+
                 |                         |
             app.jar               lib/helper.jar
                 |                         |
          demo/Main.class        helper/Message.class
                 |                         |
                 +----- ClassLoader -------+
                             |
                       main(String[])
```

**Key takeaway:** `java -jar app.jar` differs from `java -cp app.jar demo.Main`. Both approaches can run the same bytecode, but **the mechanism for selecting the main class and configuring the classpath is not the same**.

## 1. Launch Modes That Must Be Distinguished

| Mode | Example | Entry Point Selection | Application Classpath |
|---|---|---|---|
| Main class | `java -cp "out:lib/*" demo.Main` | Explicitly specify the binary name of the class containing `main` | From `-cp` / `--class-path`, or `CLASSPATH` if no option is specified |
| Executable JAR | `java -jar app.jar` | Read `Main-Class` from the manifest of `app.jar` | The specified JAR, plus valid `Class-Path` entries in the manifest |
| Named module | `java --module-path mods -m my.module/demo.Main` | Module/main class according to JPMS rules | Module path and module resolution; not identical to classpath mode |

For the example in the first row, on **Windows** use `;` instead of `:` to separate classpath entries:

```powershell
java -cp "out;lib/*" demo.Main
```

Do not use `;` to separate entries in manifest `Class-Path`: manifest syntax differs from the `-cp` argument syntax.

### `java -jar` Syntax

```bash
java [JVM options] -jar path/to/app.jar [program arguments]
```

- `java`: the JVM launcher.
- JVM options, such as `-Xmx512m` or `-Dapp.env=dev`, are placed **before `-jar`**.
- `-jar`: switches to the mode that looks up the entry point from the manifest.
- `path/to/app.jar`: the executable JAR file.
- The tokens after the JAR name are **program arguments** received by `main(String[] args)`; they are no longer interpreted as JVM options of the launcher.

Example:

```bash
java -Xmx512m -Dapp.env=dev -jar app.jar alpha beta
```

The application receives two arguments, `alpha` and `beta`, while `app.env` is a system property set by the JVM. If you write `java -jar app.jar -Xmx512m`, then `-Xmx512m` will be passed to the program as an argument (unless the application handles it itself), and does **not** set the heap limit.

## 2. `Main-Class` Selects the Entry Point for `-jar`

A standard executable JAR contains a manifest at `META-INF/MANIFEST.MF`, for example:

~~~text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

~~~

`Main-Class: demo.Main` uses a **binary name**; the actual entry class in the archive is `demo/Main.class`. On Java 17, this lesson uses `public static void main(String[] args)`. Missing `Main-Class` typically reports `no main manifest attribute`, though it does not make a library JAR useless.

You can record the entry point using `jar --create --file app.jar --main-class demo.Main -C build/app .` or provide an explicit manifest via `--manifest MANIFEST.MF`. Neither approach **automatically embeds dependencies**. Detailed manifest format and packaging rules are covered in the lesson **JAR, manifest Main-Class and Class-Path**; this section focuses on how the launcher selects the run mode.

## 3. What Happens to `-cp` and `CLASSPATH` When `-jar` Is Used?

With `java -jar app.jar`, the launcher uses the specified JAR as the source of application classes, along with valid entries from `Class-Path` in the manifest. Other **standard classpath** configurations are not used to extend the user classpath in this mode.

| Configuration | `java -cp ... demo.Main` | `java -jar app.jar` |
|---|---|---|
| `-cp` / `-classpath` / `--class-path` | Used as the classpath | **Ignored** in `-jar` mode |
| `CLASSPATH` environment variable | Used if no alternative classpath option is provided | **Ignored** for finding user classes in `-jar` mode |
| `Main-Class` of `app.jar` | Not needed if the class is already specified on the CLI | **Required** to determine the main class |
| Manifest `Class-Path` | Can be applied to applicable JARs on the classpath | **Can be applied** to locate dependencies of the executable JAR |
| JVM options such as `-D...`, `-Xmx...` | Work when placed in the right position | **Still work** when placed before `-jar` |

A mistake-prone example:

```bash
java -cp "lib/*" -jar app.jar
```

Do not assume that `lib/*` will be used to add every JAR in the `lib` directory. When `-jar` is selected, `-cp "lib/*"` does not take effect as you might expect.

Similarly, merely setting `CLASSPATH=lib/helper.jar` in the environment and then running `java -jar app.jar` **does not replace** declaring dependencies properly.

**Distinction:** the rule above concerns the application classpath when launching with `-jar`, and **does not mean all other JVM options are disabled**. Mechanisms such as bootstrap/platform classes, native library path, the module system, Java agents, or framework launchers have their own rules.

### What About the `*` Wildcard?

With a normal CLI classpath:

```bash
java -cp "app.jar:lib/*" demo.Main
```

The launcher supports wildcards for **`.jar` files in a directory** according to classpath syntax. The separator in the example above is `:` on Linux/macOS; on Windows it is `;`. Classpath wildcards are non-recursive, and the order in which JARs are expanded should not be relied upon to guarantee dependency order.

However, manifest `Class-Path` uses a syntax of **space-separated relative URL entries**; there is no wildcard expansion like `-cp "lib/*"`. Therefore:

```text
Class-Path: lib/*
```

**Does not** equate to “load all JARs in the lib directory”. Valid files must be listed, for example:

```text
Class-Path: lib/helper.jar lib/json.jar lib/logging.jar
```

Libraries are written separated by spaces, **not** by `:`, `;`, or commas. Whether each entry can be found also depends on the path rules in the next section.

## 4. Manifest `Class-Path` When Running `-jar`

Suppose `release/app.jar` sits alongside `release/lib/helper.jar`. If the `app.jar` manifest declares `Class-Path: lib/helper.jar`, the dependency is resolved **relative to the location of `app.jar`**, even when launched from a different directory.

Do not confuse the separators of the two modes: with `java -cp`, Windows uses `;` while Unix uses `:`; manifest `Class-Path` uses a **space-separated list of relative URLs**. It **does not expand wildcards**: `Class-Path: lib/*` does not mean every JAR in the directory. An entry ending with `/` is used for a directory, while an entry not ending that way is used for a JAR; invalid/non-existent paths may be ignored. The manifest needs a valid main-section `Class-Path`; for overly long physical lines, the `jar` tool handles line-wrapping rules by UTF-8 bytes.

Distributing an executable JAR must therefore carry the exact library directory tree next to the JAR, or use another launcher/packaging approach. The previous lesson explains the URL/manifest standard in detail; the following example directly verifies that `-jar` ignores `-cp` using an external class `side.Extra`.

## 5. Complete Java 17+ Example: `-jar` Finds Dependencies via Manifest but Ignores `-cp`

The example creates two JARs:

- `app.jar`: contains the entry point class `demo.Main`.
- `lib/helper.jar`: contains the library class `helper.Message`.

We also separately compile `side.Extra` into the `extra/` directory to prove that the `-cp extra` classpath is ignored when using `-jar`. If run in standard classpath mode, the `side.Extra` class will be found.

### 5.1. Source Structure

```text
project/
  src/
    helper/
      Message.java
    demo/
      Main.java
    side/
      Extra.java
  MANIFEST.MF
  build/                 (created during compilation)
  extra/                 (created during compilation)
  lib/
    helper.jar           (created during packaging)
  app.jar                (created during packaging)
```

### 5.2. `src/helper/Message.java`

```java
package helper;

public final class Message {
    private Message() { }

    public static String text() {
        return "Hello from helper";
    }
}
```

### 5.3. `src/side/Extra.java`

```java
package side;

public final class Extra {
    private Extra() { }
}
```

`Extra` is not included in `app.jar` and is also not in the manifest `Class-Path`. It exists separately in `extra/` after compilation.

### 5.4. `src/demo/Main.java`

```java
package demo;

import helper.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println("message: " + Message.text());
        System.out.println("args: " + args.length);
        System.out.println("mode: "
                + System.getProperty("mode", "unset"));

        try {
            Class.forName("side.Extra");
            System.out.println("extra: visible");
        } catch (ClassNotFoundException ex) {
            System.out.println("extra: absent");
        }
    }
}
```

Purpose:

- `Main` needs `helper.Message` to compile and to execute.
- `Class.forName("side.Extra")` looks up the class by name; if it is not visible to the caller's loader, it throws `ClassNotFoundException`.
- Using `Class.forName` inside a `try/catch` lets the program **still run** even when Extra is not on the classpath.
- `args.length` makes it possible to see that arguments after `app.jar` are passed to the program.
- The `mode` property makes it possible to see that the `-Dmode=...` option must appear before `-jar`.

### 5.5. `MANIFEST.MF`

Create a text file **`MANIFEST.MF`** in the `project` directory:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

```

**A trailing newline is required (and ideally a final blank line)** for the main section. `Main-Class` uses the name `demo.Main`, while `Class-Path` points to `lib/helper.jar` relative to the location of `app.jar`.

### 5.6. Compiling and Packaging

The following commands use **Bash on Linux/macOS** (or an equivalent Bash environment on Windows) and are run from the `project` directory:

```bash
mkdir -p build/helper build/app lib extra

javac -d build/helper src/helper/Message.java
jar --create --file lib/helper.jar -C build/helper .

javac -cp lib/helper.jar -d build/app src/demo/Main.java
jar --create --file app.jar --manifest MANIFEST.MF -C build/app .

javac -d extra src/side/Extra.java
```

Explanation of the order:

1. Compile the `Message` library first.
2. Create `lib/helper.jar` from the library's `.class` files.
3. Compile `Main` with `-cp lib/helper.jar` so **javac** can see `helper.Message`.
4. Create the executable `app.jar` containing `demo.Main` and the manifest. **This is a packaging step**, and does not automatically copy `helper.jar` into `app.jar`.
5. Compile `Extra` into a separate directory to test both modes.

**Note:** `javac -cp ...` is the **compile-time classpath**. It does not automatically configure the classpath for a subsequent `java -jar` run. That is why the manifest needs `Class-Path`.

### 5.7. Running Properly in `-jar` Mode

```bash
java -jar app.jar
```

**Exact stdout:**

```text
message: Hello from helper
args: 0
mode: unset
extra: absent
```

The run finds `helper.Message` even though `app.jar` does not contain the library, because the manifest points to `lib/helper.jar`. Conversely, `side.Extra` residing separately in `extra/` is not on the search path.

Try adding `-cp extra` before `-jar`:

```bash
java -cp extra -jar app.jar
```

**Stdout remains identical:**

```text
message: Hello from helper
args: 0
mode: unset
extra: absent
```

`-cp extra` **does not** make the `side.Extra` class appear: `-jar` mode ignores classpath options. This is the difference the example is meant to demonstrate.

### 5.8. Running in Classpath Mode Instead of `-jar`

On Linux/macOS:

```bash
java -cp "app.jar:lib/helper.jar:extra" demo.Main
```

On Windows PowerShell/cmd, use `;`:

```powershell
java -cp "app.jar;lib/helper.jar;extra" demo.Main
```

**Stdout in this case:**

```text
message: Hello from helper
args: 0
mode: unset
extra: visible
```

Here, the launcher uses the classpath we specified and takes `demo.Main` from the CLI argument, so `side.Extra` is also found. The result proves that **the launch mode**, not the `.jar` file extension, determines how the classpath is configured.

### 5.9. Where Do JVM Options and Arguments Go?

```bash
java -Dmode=prod -jar app.jar alpha beta
```

**Stdout:**

```text
message: Hello from helper
args: 2
mode: prod
extra: absent
```

Because `-Dmode=prod` comes before `-jar`, the JVM receives this property. `alpha beta` comes after the JAR, so `args.length == 2`. If `-Dmode=prod` is moved after `app.jar`, the application will receive it as an argument and the `mode` property retains its default value `unset` (assuming no other configuration source exists).

## 6. When Libraries Are in a Different Location from the JAR

Suppose:

```text
dist/
  app.jar
  lib/helper.jar
```

The manifest in `app.jar` only needs to declare `Class-Path: lib/helper.jar`. The command:

```bash
java -jar dist/app.jar
```

will resolve the dependency relative to the location of **`dist/app.jar`**, meaning `dist/lib/helper.jar`, even if the user executes the command from the parent directory.

If `app.jar` is moved to another directory without moving the corresponding `lib` directory, the manifest becomes a broken reference. This is a common cause of “works on the build machine, fails on the deployment machine” errors.

### Does Manifest `Class-Path` Allow Nested JARs Inside a JAR?

Not with the default behavior of the Java launcher. If you package `lib/helper.jar` **as an entry inside `app.jar`**, the default JVM class loader does not automatically treat that nested JAR entry as an independent classpath entry.

Common packaging approaches:

1. **Thin JAR + external libraries:** use `Main-Class` and manifest `Class-Path` pointing to JARs in an adjacent directory.
2. **Uber/Fat JAR:** build tools typically merge dependency `.class` files and resources into a single appropriately structured JAR, while handling service resource conflicts when needed.
3. **Executable archive with a custom launcher:** a framework (such as a specialized launcher for nested JARs) provides its own way to locate dependencies; you must read the framework's rules rather than assuming default `java -jar` behavior applies to nested structures.

**Do not assume** every “fat jar” has the same structure. A JAR might run with `java -jar` via a framework launcher's `Main-Class` rather than the application class containing the `main` method you wrote.

## 7. Classpath, Class Loaders, and Class Visibility

For a standard classpath-based Java application, the executable JAR and manifest dependency entries are used to configure the **search path** for the application class loader (the system/application class loader in typical configurations).

```text
ClassLoader
    |
    | loadClass("helper.Message")
    v
Application searches for the class via the loader hierarchy and classpath
    |
    +-- app.jar               (does not contain helper/Message.class)
    |
    +-- lib/helper.jar        (contains helper/Message.class)
    |
    v
Runtime Class<helper.Message>
```

Declaring the search path does not mean every class is loaded immediately. When code runs `Message.text()`, the runtime needs the appropriate `helper.Message` class. If the library file cannot be found, an error may occur at the time the JVM needs to resolve/load the type, not necessarily immediately when `java` starts.

**Another point:** `java -jar` does not automatically reload or override platform Java classes provided by the bootstrap/platform loader. The class loader hierarchy, type identity `(binary name, defining loader)`, and JPMS restrictions still apply.

### Why Should You Not Mix Up `-jar` and `-cp` When Investigating Errors?

The two commands:

```bash
java -jar app.jar
java -cp "app.jar:lib/helper.jar" demo.Main
```

may produce the same output in simple examples, **but that does not prove the two modes are identical**. The first mode relies on `Main-Class` and manifest `Class-Path`; the second takes the class name and classpath directly from the CLI.

If `Class-Path` in the manifest is wrong, the second command may succeed because `-cp` is explicitly specified, whereas the first fails. This is a very useful cross-check when debugging packaging.

## 8. Relation to the Module Path (JPMS)

Java 9+ has a module system, but a clear distinction is needed:

- `java -jar app.jar` is **manifest-based JAR launching**, and regular application classes reside in the **unnamed module** of the associated loader.
- `java --module-path mods -m module.name/main.Class` is **module launching**, relying on the module descriptor/JPMS.
- A JAR can be placed on the classpath in one mode, whereas when run on the module path in another context it may become a named/automatic module according to the corresponding rules.
- The `--module-path` flag is not a direct replacement for `Class-Path` in the manifest, and whether a dependency requires JPMS resolution depends on the type of program.

For most Java Core learning applications using `-jar` + regular libraries, debug the **classpath of the executable JAR** first; only switch to module analysis when the project actually uses named modules.

## 9. Common Errors and How to Identify Their Causes

### 9.1. `no main manifest attribute, in app.jar`

**Cause:** `Main-Class` is missing from the main section of the manifest.

**Check:**

```bash
jar --describe-module --file app.jar
unzip -p app.jar META-INF/MANIFEST.MF
```

The `unzip -p` command is an optional OS utility; if unavailable, use `jar --extract --file app.jar META-INF/MANIFEST.MF` in a separate inspection directory and then open the manifest file. The `jar --describe-module` command is only useful for module information and **does not replace reading the manifest** to verify `Main-Class`.

**Fix:** create the JAR with `--main-class` or a manifest containing the properly named `Main-Class: demo.Main`, then repackage.

### 9.2. `Could not find or load main class demo.Main`

**Possible causes:** the manifest specifies an incorrect binary name, the package/directory layout inside the JAR is incorrect, the class was not packaged, the class cannot be loaded due to a missing dependency, or the class name in the run configuration is wrong.

**Check:**

```bash
jar --list --file app.jar
```

Inside the JAR there must be a class entry with the corresponding name, for example `demo/Main.class`. Do not confuse `Main-Class: demo.Main` with `Main-Class: demo/Main`.

### 9.3. `NoClassDefFoundError` or `ClassNotFoundException` for a Dependency

**Common causes:** `helper.Message` is not in `app.jar` and `Class-Path` does not point properly to `lib/helper.jar`, or a dependency of the helper itself is missing.

**Check in order:**

1. Identify the binary name of the class that failed to load.
2. Locate that class in the appropriate dependency JAR.
3. Inspect `Class-Path` in the manifest of the JAR that is actually being run.
4. Resolve the path **relative to the JAR**; confirm the file exists on the target machine.
5. Check the filename, case sensitivity, URL characters, read permissions, and that the manifest has no line-break formatting errors.
6. Compare `java -jar app.jar` with classpath mode explicitly specifying all JARs.
7. Inspect the root cause and stack trace; `NoClassDefFoundError` can also occur after a failed class initialization, not only when a JAR is missing.

### 9.4. `java -cp lib/* -jar app.jar` Still Fails to Find Classes

**Explanation:** standard classpath options do not take effect in `-jar` mode. Put the dependencies in manifest `Class-Path`, package appropriately, or switch completely to `java -cp ... demo.Main` mode.

### 9.5. Setting `Class-Path: lib/*` Still Fails to Find Libraries

**Explanation:** `-cp` wildcards do not carry over to manifest `Class-Path`. List each JAR as a valid relative URL, or use a build tool to generate the manifest.

### 9.6. Running from a Different Directory Fails

**Investigation:** if libraries are referenced from the manifest, URLs are resolved relative to the JAR's location; if the application opens configuration files using relative paths in Java code (for example, `Path.of("config/app.properties")`), code paths may instead be relative to the **working directory**. The two resolutions are different.

**Fix:** distinguish dependency URLs in the manifest from file system paths used by the application itself. Do not edit `Class-Path` when the error is actually in the code opening the configuration file.

### 9.7. Running from the IDE Succeeds, Released JAR Fails

IDEs typically configure all dependencies into their own classpath. When building an executable JAR, the manifest may be missing `Class-Path` or the packaged artifact may be missing contents.

**Fix:** inspect the JVM command used by the IDE, the final artifact's manifest, and the deployment directory structure; test running directly with `java -jar` in a clean environment.

## 10. Executable JAR Packaging Checklist

Before releasing:

- [ ] An actual JAR file exists and is readable.
- [ ] The manifest has a valid `Main-Class` in the main section.
- [ ] The package name and `.class` path inside the JAR match `Main-Class`.
- [ ] All runtime dependencies exist at the locations pointed to by a valid manifest `Class-Path`, or have been properly packaged using a fat/launcher approach.
- [ ] Running `java -jar` does not rely on `CLASSPATH`, `-cp`, or IDE-only paths.
- [ ] If manifest `Class-Path` is used, entries are space-separated, no wildcards are used, and relative paths are resolved relative to the JAR's location.
- [ ] JVM options are placed before `-jar`; program arguments are placed after the JAR.
- [ ] Test the program from a different working directory to catch working-directory confusion.
- [ ] Check module/custom launcher specifics if the project uses JPMS or an executable archive that does not follow a standard classpath JAR structure.
- [ ] Use a Java runtime compatible with the version of the `.class` files and libraries, and test-run the artifact after packaging.

## 11. Self-Check

**Question 1.** The manifest has `Main-Class: demo.Main` but no `Class-Path`. `demo.Main` uses a library JAR located at `lib/helper.jar`. Is `java -cp lib/helper.jar -jar app.jar` the proper way to add helper to the search path?

**Answer:** No. `-cp` is ignored in `-jar`. You need to configure manifest `Class-Path: lib/helper.jar`, package the dependency in another appropriate way, or switch to `java -cp ... demo.Main`.

**Question 2.** The manifest of `release/app.jar` specifies `Class-Path: lib/helper.jar`. The command is run from the parent directory. Which path is used?

**Answer:** `release/lib/helper.jar`, because manifest `Class-Path` resolves relative to the location of the JAR containing the manifest.

**Question 3.** Is writing `Class-Path: lib/*` the same as `java -cp "lib/*"`?

**Answer:** No. Wildcard expansion is a CLI classpath rule; the manifest requires valid relative URL entries, typically individual JAR files.

**Question 4.** Are the two commands `java -jar app.jar` and `java -cp app.jar demo.Main` always equivalent?

**Answer:** No. The first takes the entry point from the manifest and uses manifest dependencies; the second takes the class name and classpath from the CLI. They may only happen to exhibit the same behavior in a simple configuration.

**Question 5.** Do `java -Dmode=prod -jar app.jar hi` and `java -jar app.jar -Dmode=prod` set the same JVM property?

**Answer:** No. In the first command `-Dmode=prod` is a JVM option; in the second it is an argument to `main`.

**Question 6.** A JAR contains the file `lib/helper.jar` **inside the archive**. The manifest specifies `Class-Path: lib/helper.jar`. Does the default JVM automatically access that nested archive as a dependency?

**Answer:** No. A manifest entry is a relative URL referencing outside the JAR relative to the JAR's context; nested JARs require a special launcher/packaging mechanism or proper merging of classes/resources.

## 12. Decision Diagram When the Application Cannot Find a Class

```text
How is the program run?
             |
       +-----+---------+
       |               |
    java -jar         java -cp / --class-path
       |               |
Read manifest         Check CLI classpath
       |               |
Correct Main-Class?   Entries use OS separator?
       |
Class-Path has valid relative URLs?
       |
Resolve relative to the JAR's directory
       |
Does the dependency exist in the specified directory/JAR?
       |
Does the JVM/loader have access and compatible bytecode?
       |
If it still fails: check type name, modules, transitive dependencies,
class initialization, classloader, and root cause.
```

**Summary:** `java -jar` locates `main` via `Main-Class` and sets up the application search path from the executable JAR and `Class-Path` in the manifest. `-cp`/`CLASSPATH` are commonly used with classpath mode, but **do not extend the classpath of `-jar`**. Manifest `Class-Path` uses **relative URLs**, separated **by spaces** and resolved **relative to the JAR's location**, rather than shell wildcards/path separators.

### Official References

- [Java SE 17 — The java Command: launch modes and `-jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Java SE 17 — JAR File Specification: manifest and `Class-Path`](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Java SE 17 — ClassLoader API: system loader and JAR manifest classpath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
