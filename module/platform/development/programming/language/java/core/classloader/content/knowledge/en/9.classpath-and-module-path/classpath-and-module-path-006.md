# JAR, Manifest Main-Class, and Class-Path in the Java Class Lookup Mechanism

A **JAR (Java ARchive)** file packages `.class` files, resources, and metadata into a ZIP-format archive. For a typical **executable JAR**, the JVM launcher uses the `META-INF/MANIFEST.MF` file in the JAR to determine the **startup class** via the `Main-Class` attribute. The `Class-Path` attribute in the same manifest can specify **dependent JARs/directories** so the class loader extends its search path.

Example:

```text
app/
├── app.jar
└── lib/
    ├── helper.jar
    └── parser.jar
```

Manifest inside `app.jar`:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar lib/parser.jar

```

After proper packaging, the `java -jar app.jar` command locates `demo.Main`, invokes `public static void main(String[] args)`, and can find dependent classes in `lib/helper.jar` and `lib/parser.jar`. The `Class-Path` entries are interpreted **relative to the location of the JAR containing the manifest**, not simply relative to the terminal's working directory.

These are three distinct components:

- **JAR**: stores bytecode and resources by entry name such as `demo/Main.class`.
- **`Main-Class`**: specifies the class containing the application entry point used by `java -jar`.
- **`Class-Path`**: adds search paths for classes/resources when the loader processes the JAR containing the manifest.

## 1. What Does a JAR Contain?

A JAR is typically created with the JDK's `jar` tool. It is a ZIP archive with metadata conventions for Java.

Example internal structure:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── demo/
│   ├── Main.class
│   └── Config.class
└── application.properties
```

The `demo/Main.class` file is a **JAR entry** corresponding to the binary name `demo.Main`. The `application.properties` resource located at the root of the JAR can be found using resource APIs when the JAR is within an appropriate lookup scope.

Do not use `Main-Class: demo/Main.class` or `Main-Class: demo.Main.class`. `Main-Class` accepts a **class name**, such as `demo.Main`, rather than a `.class` resource path.

For the classloader, the flow can be understood as:

```text
java -jar app.jar
        |
        v
Read META-INF/MANIFEST.MF
        |
        +--> Main-Class: demo.Main
        |          |
        |          v
        |     locate demo/Main.class in app.jar
        |
        +--> Class-Path: lib/helper.jar
                   |
                   v
              add class/resource search source
                   |
                   v
            invoke demo.Main.main(String[])
```

This is a learning model. On Java 9+, the runtime also has modules, bootstrap/platform loaders, and JVM/JDK details; the diagram does not mean that all platform classes are only searched in external JARs.

## 2. What Is a Manifest?

The standard manifest resides at the exact path **`META-INF/MANIFEST.MF`** inside the JAR. It is a text file with its own syntax, consisting of a **main section** and optional per-entry sections.

A minimal manifest for `java -jar`:

```text
Manifest-Version: 1.0
Main-Class: demo.Main

```

- `Manifest-Version` indicates the manifest format version; it should be placed at the top of the file.
- `Main-Class` is the binary name of the startup class, **without `.class`**. The class must be within the search scope and have a valid `main` entry point.
- A blank line after the attributes is used to terminate the **main section**. When creating a manifest manually, ensure there is a trailing newline at the end of the last line; use the `jar` tool to merge and normalize the manifest if possible.

Example with additional dependencies:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar lib/parser.jar

```

Manifest attribute names have the syntax `Name: value`, **separated by a colon and a space**. Attribute names are case-insensitive according to the specification, but they should be written in the standard `Main-Class` and `Class-Path` form for readability.

For long manifests, the physical line length limit is **72 bytes when UTF-8 encoded**, not 72 characters. Long content must be **wrapped**, with the continuation line starting with a single space; that space is a line-continuation marker, not an arbitrary character added to the path. Let `jar` or a standard manifest tool handle line wrapping. Do not manually insert a newline in the middle of a path and expect the JVM to stitch it back together as intended.

**Important distinction:** metadata in the manifest does not mean the loader automatically runs all classes. `Main-Class` selects the entry point for the launcher; other classes are typically loaded only when the program/JVM actually needs them.

## 3. Main-Class: Specifying the Entry Point

Given the Java source:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");
    }
}
```

After compilation, the class file must have the entry:

```text
demo/Main.class
```

If `Main-Class: demo.Main` is specified, the launcher can locate the main class and invoke the method:

```java
public static void main(String[] args)
```

For Java 17 in this lesson, this is the entry point signature to use. `main` must be `public`, `static`, return `void`, and accept a `String[]` array. A constructor of `Main` is not required to be invoked.

The two commands have different semantics:

```bash
java -cp out demo.Main
java -jar app.jar
```

- With `-cp`/`--class-path`, the user **explicitly specifies the main class on the command line** and defines the classpath.
- With `-jar`, the launcher **obtains the main class from the JAR's manifest**; the JAR name is the argument passed to the launcher.
- Arguments **after** the JAR name are program arguments passed to `main(String[] args)`.

Example:

```bash
java -jar app.jar input.txt --verbose
```

Inside `main`, `args[0]` is `input.txt`, and `args[1]` is `--verbose`. The words after the JAR name must not be interpreted as the JVM `-cp` option.

### When Main-Class Is Missing

A library `utils.jar` is still completely usable even without `Main-Class`: other applications can include it on the classpath to use the classes inside.

However, if you run `java -jar utils.jar` when the manifest does not declare an entry point, the launcher may report:

```text
no main manifest attribute, in utils.jar
```

That is a **packaging/launch** error; it does not prove that the JAR is corrupted or that none of the classes inside it can be loaded.

## 4. How Is Class-Path in the Manifest Interpreted?

According to the *JAR File Specification*, the `Class-Path` value is a list of **relative URLs** pointing to dependent JARs or directories, separated by one or more spaces.

Example:

```text
Class-Path: lib/helper.jar lib/parser.jar config/
```

In a distribution:

```text
dist/
├── app.jar
├── config/
│   └── config.properties
└── lib/
    ├── helper.jar
    └── parser.jar
```

The entries correspond to the location of the JAR containing the manifest:

| Manifest entry | Corresponding lookup source when JAR is at `dist/app.jar` |
|---|---|
| `lib/helper.jar` | `dist/lib/helper.jar` |
| `lib/parser.jar` | `dist/lib/parser.jar` |
| `config/` | `dist/config/`, a resource/class directory |

These paths **do not depend on where you are when typing `java -jar`**. If you run `java -jar /opt/app/dist/app.jar` from the `/tmp` working directory, `lib/helper.jar` is still interpreted relative to `/opt/app/dist/app.jar`.

Several important rules from the specification:

1. `Class-Path` is declared in the **main section**, and there should be only **one `Class-Path` header** in a manifest; multiple entries are listed under the same attribute.
2. Each entry is a valid **relative URL**, which can be a JAR or a directory. The `/` character is the URL separator; do not replace it with Windows `\`.
3. An entry **ending with `/`** is interpreted as a directory; an entry not ending with `/` is assumed to be a JAR.
4. Each entry is resolved against the URL of the **context JAR**, meaning the JAR containing the manifest currently being processed.
5. Invalid, missing, or duplicate URLs may be ignored while constructing the search path. Therefore, a mistyped path might only result in an error when a class is actually used.
6. Safe URL rules prefer dependencies located under the directory containing the context JAR. Some compatibility exceptions apply when the JAR is loaded from the file system (including cases involving `../` and `file:`), but you should not rely on them if you want a simple and portable deployment package.

**Do not put the wildcard character** `lib/*` in the manifest expecting it to behave like the wildcard in the `java -cp` option. Manifest `Class-Path` uses a list of URLs and **has no wildcard expansion mechanism like the command-line classpath**. List `lib/a.jar lib/b.jar` explicitly or use another packaging/deployment tool.

Paths containing spaces must be represented as valid URLs (for example, using percent-encoding where appropriate), not simply wrapped in quotes using shell syntax. A more reliable approach is to name dependent files/directories without spaces and package them with a fixed structure.

## 5. Java 17+ Practice: Creating an Executable JAR with Separate Dependencies

The following exercise clearly demonstrates how `Main-Class` selects the entry point and `Class-Path` extends the search path to a library located **outside** the main JAR.

Create the source structure:

```text
jar-demo/
├── src/
│   ├── demo/
│   │   └── Main.java
│   └── util/
│       └── Message.java
└── app.mf
```

### 5.1. Write the Dependent Class

File **`src/util/Message.java`**:

```java
package util;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "Dependency OK";
    }
}
```

### 5.2. Write the Main Class

File **`src/demo/Main.java`**:

```java
package demo;

import util.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Main class: " + Main.class.getName());
        System.out.println(Message.text());
        System.out.println("Main resource visible: "
                + (Main.class.getClassLoader()
                        .getResource("demo/Main.class") != null));
    }
}
```

Here `demo.Main` references `util.Message`. When running the application, the class loader needs to find `util/Message.class`. We will put that class into `helper.jar` instead of embedding it in `app.jar`.

### 5.3. Create the Manifest

File **`app.mf`**:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

```

Keep the newline after the last line and the blank line ending the main section when writing the file manually. When creating the archive, the `jar` tool will handle manifest formatting.

### 5.4. Compile and Package

On **Bash** (Linux/macOS/Git Bash), from the `jar-demo` directory:

```bash
mkdir -p classes/helper classes/app dist/lib

javac --release 17 -d classes/helper src/util/Message.java
jar --create --file dist/lib/helper.jar -C classes/helper .

javac --release 17 -cp dist/lib/helper.jar -d classes/app src/demo/Main.java
jar --create --file dist/app.jar --manifest app.mf -C classes/app .

java -jar dist/app.jar
```

On **Windows PowerShell**, replace the first directory-creation step with:

```powershell
New-Item -ItemType Directory -Force -Path classes/helper, classes/app, dist/lib | Out-Null
```

The subsequent `javac`, `jar`, and `java` commands have the same syntax as above (as long as the JDK is already on `PATH`).

Output on JDK 17+ for this example:

```text
Main class: demo.Main
Dependency OK
Main resource visible: true
```

Meaning of the commands:

- `javac --release 17` compiles with compatibility for the Java 17 API/class-file target.
- `-d classes/helper` and `-d classes/app` place the class files in their respective package directory trees.
- `jar --create --file dist/lib/helper.jar -C classes/helper .` packages the library containing `util/Message.class`.
- `javac -cp dist/lib/helper.jar ...` lets the **compiler** find `util.Message` when compiling `Main`.
- `jar --create --file dist/app.jar --manifest app.mf ...` packages the application and includes the manifest attributes in the archive.
- `java -jar dist/app.jar` uses `app.jar`'s manifest, then locates the dependency via `Class-Path: lib/helper.jar`.

**Important:** `-cp` in the `javac` command is the **compile-time classpath**; it does not automatically become the runtime classpath. In this example, the runtime program can find the dependency because of the **manifest `Class-Path`**, not because the compiler previously received the `-cp` argument.

Output structure:

```text
dist/
├── app.jar
└── lib/
    └── helper.jar
```

If you copy the entire `dist` directory to another machine with a compatible JRE/JDK, the `lib/helper.jar` path relationship remains intact. If you copy only `app.jar` and forget `lib/helper.jar`, when the code uses `util.Message`, the runtime will be unable to find the required class definition.

### 5.5. Inspecting JAR Contents

Use the built-in JDK tool:

```bash
jar --list --file dist/app.jar
jar --list --file dist/lib/helper.jar
```

Important entries you should see:

```text
# In app.jar
META-INF/
META-INF/MANIFEST.MF
demo/Main.class

# In helper.jar
META-INF/
META-INF/MANIFEST.MF
util/Message.class
```

Actual `jar --list` output may contain other entries or a different ordering; the block above **only lists the entries to verify**, not the complete fixed stdout of the command. What you need to check is that the entry names correspond accurately to the package/binary names.

To inspect the manifest contents with a ZIP/JAR viewer, open `META-INF/MANIFEST.MF` inside `app.jar`. When using `jar --extract`, extract into a **separate working directory** so metadata files do not get mixed into the current source tree.

## 6. What Happens If Class-Path Is Omitted?

Keep `app.jar` and `helper.jar` as in the exercise, but create a manifest containing only:

```text
Manifest-Version: 1.0
Main-Class: demo.Main

```

Running `java -jar dist/app.jar` in normal classpath mode will no longer have the manifest path to `lib/helper.jar`. When the code starts using `util.Message`, you may see an error like:

```text
java.lang.NoClassDefFoundError: util/Message
Caused by: java.lang.ClassNotFoundException: util.Message
```

This is a **sample of the exception/cause header**, while the actual stack trace depends on where the class is used and the runtime. It indicates that the JVM could not resolve the dependent class at runtime. `Main-Class` can still be correct.

Distinguish between:

| Observation | Common Issue |
|---|---|
| `no main manifest attribute` | Missing or incorrect `Main-Class` in the executable JAR |
| `Could not find or load main class ...` | Main class is not in the right location, has the wrong name, or encounters a related error while loading the main class |
| `ClassNotFoundException` | An explicitly invoked loader API could not find the class along the search path |
| `NoClassDefFoundError: util/Message` | The JVM needs a dependency class, but no suitable definition is available when it is used |
| `UnsupportedClassVersionError` | The class file was compiled for a newer Java version than the running runtime |
| `NoSuchMethodError` | The dependency was found, but the binary version no longer has the method referenced by the code |
| `SecurityException` regarding sealing/signature | Package sealing or JAR signing constraints are not satisfied |

**Do not assume that every `NoClassDefFoundError` is caused by a missing dependency JAR.** A class that failed during static initialization can also result in `NoClassDefFoundError` on subsequent uses. You must read the message and the cause.

## 7. Why Doesn't java -jar Use -cp in the Usual Way?

This is one of the most important points about **search paths**.

According to the JDK 17 `java` command documentation, when running in **`-jar`** mode, the specified JAR is the primary source of user classes; **other classpath settings are ignored** for this launch mode. Additional dependency sources can come from the **manifest `Class-Path`** and appropriate JVM/module mechanisms.

For example, if you want to add `other.jar` by writing:

```bash
java -cp other.jar -jar dist/app.jar
```

then you **cannot rely on `-cp other.jar`** to extend the class search path in `-jar` mode. The standard approach in this exercise is to specify `Class-Path: lib/helper.jar` in the manifest or choose a different launch mode.

When you want to control the classpath and main class directly, omit `-jar` and explicitly specify the class name:

```bash
# Linux/macOS
java -cp "dist/app.jar:dist/lib/helper.jar" demo.Main
```

```powershell
# Windows PowerShell
java -cp "dist/app.jar;dist/lib/helper.jar" demo.Main
```

**Note on separators:** Windows uses `;` and Linux/macOS use `:` for classpath elements in the `java -cp` command. This is a difference in the **command-line classpath**; it does not change the rule of using `/` inside the manifest `Class-Path` attribute.

With the `-cp` launch mode, the name `demo.Main` on the command line selects the entry point. `Main-Class` in `app.jar`'s manifest no longer determines the entry point for that command. However, if a JAR contains a manifest `Class-Path` and the loader in use supports the manifest class-path, dependencies in the manifest can still be processed through that mechanism; `-cp` mode should not be understood as "disabling all JAR metadata".

## 8. How Do Class-Path and Class Loaders Interact?

The `Class-Path` entries affect the **sources that the application class loader can search** in the normal classpath/JAR model. They do not replace the **parent delegation** rule:

```text
Application loader needs demo.Main
        |
        +--> parent/bootstrap/platform first (if applicable)
        |
        +--> app.jar
        |
        +--> lib/helper.jar (per manifest Class-Path)
```

When code invokes:

```java
Class<?> type = Class.forName("util.Message");
```

that call uses the defining loader of the **calling class** according to the one-argument overload contract. If `demo.Main` is defined by the application loader in the example model, that loader can find `util.Message` via the `lib/helper.jar` entry. However, having a path to a JAR in the manifest **does not automatically load all classes** as soon as the JVM starts.

Three concepts to keep separate:

- **Class path:** the JAR/directory sources for finding classes/resources.
- **Class loader:** the object/mechanism that performs lookup, delegation, and class definition.
- **Runtime class identity:** `(binary name, defining class loader)`. Two different loaders can define two classes with the same name that do not share the same runtime type.

This is why placing two copies of `shared.api.Service` in JARs belonging to different loaders can cause casting errors, even when each JAR declares a valid `Class-Path`. Manifest `Class-Path` specifies a search path; it **does not unify the namespaces of two defining loaders**.

## 9. Common Points of Confusion

### 9.1. Relative Paths Are Resolved Relative to the JAR, Not the Terminal

Suppose:

```text
/opt/demo/app.jar
/opt/demo/lib/helper.jar
```

Run:

```bash
cd /tmp
java -jar /opt/demo/app.jar
```

When the manifest has `Class-Path: lib/helper.jar`, the dependency is still searched relative to `/opt/demo/app.jar`. If you move `app.jar` alone to `/tmp/app.jar` without bringing `lib` along, the path relationship is no longer valid.

### 9.2. Wildcards Do Not Work the Same Way in a Manifest

The line:

```text
Class-Path: lib/*
```

is not equivalent to the `java -cp "lib/*"` option. When using a manifest, list each required URL entry explicitly, such as `lib/a.jar lib/b.jar`. For the CLI, wildcard classpaths have the launcher's own JAR expansion rules.

### 9.3. Correct JAR Name but Wrong Package Entry

Suppose the code requires `org.example.Tool`, but the archive only contains `Tool.class` at the root. That is not the corresponding entry name; the classloader expects a resource path like `org/example/Tool.class` in a regular JAR. You need to compile and package from the **root of the package tree**, for example `jar -C classes .`, instead of accidentally packaging the `classes` directory itself as an entry inside.

### 9.4. Forgetting Dependencies at Runtime

The `javac -cp lib/helper.jar` command only helps with **compilation**. If the application JAR does not contain that dependency, lacks a valid manifest `Class-Path`, and the launcher is not configured with an appropriate classpath, the runtime may throw an error when the `util.Message` class is resolved.

### 9.5. Writing a Path Instead of a Binary Name in Main-Class

Incorrect:

```text
Main-Class: demo/Main.class
```

Correct:

```text
Main-Class: demo.Main
```

You should also not use the canonical name `Outer.Inner` when the entry point is a nested class with binary name `Outer$Inner`; for nested classes, the manifest requires the binary name that the launcher can resolve. In practice, you should use a top-level main class for the application to keep things simple.

### 9.6. A JAR Containing Multiple Main Classes

An archive can contain `demo.Main`, `demo.AdminMain`, and `demo.BatchMain`, but the manifest `Main-Class` selects **one** default entry point for `java -jar`. When you want to launch a different entry point, you can use `java -cp app.jar demo.BatchMain` (with appropriate dependencies) or create a separate executable JAR/launcher.

### 9.7. Dependency Conflicts and Search Order

If multiple JARs contain classes with the same binary name, the class loader generally selects according to its search policy (classpath ordering, parent delegation, module mapping, custom loader). Do not expect `Class-Path` to resolve version conflicts. It only describes the URLs of dependent libraries; which version of the class is actually used must be checked according to the active loader/classpath.

### 9.8. Executable JARs Differ from Fat JARs / Nested JARs

The standard executable JAR in this lesson directly contains `demo/Main.class`; the dependency is placed externally under `lib/helper.jar` and referenced by the manifest.

A **fat/uber JAR** can merge the contents of multiple libraries into a single flat JAR. A common **Spring Boot executable JAR**, on the other hand, arranges classes and nested JARs in a structure such as `BOOT-INF/classes` and `BOOT-INF/lib`, using a specialized launcher/classloader. Do not assume that the default JVM launcher will automatically scan all nested JARs inside a regular ZIP JAR.

The `Main-Class` of a framework packaging format may be the framework's **launcher**, while the business entry point is described by separate metadata. Those attributes are mechanisms of the packaging tool, not general rules of every Java JAR.

### 9.9. Manifest and JPMS

In a **module path** application using named modules, the module resolution mechanism, the `module-info.class` module descriptor, and module access rules differ from the traditional classpath. An executable JAR's `Main-Class` and manifest `Class-Path` cannot replace JPMS `requires`, `exports`, or `opens`. If running a module with `java --module-path ... -m module[/mainclass]`, you must analyze startup and the module-path according to the contract of that mode.

## 10. Creating a JAR with jar --main-class Instead of a Manual Manifest File

When you do not need the `Class-Path` attribute or special metadata, the `jar` tool supports writing the main class directly during packaging:

```bash
jar --create --file app.jar --main-class demo.Main -C classes/app .
```

It generates an appropriate manifest so the launcher knows the entry point. However, if the application requires `Class-Path: lib/helper.jar` as in the practice exercise, you must **ensure this attribute is present** (for example, by providing `--manifest app.mf`).

Some traditional shorthand options of `jar`:

```bash
jar cfm dist/app.jar app.mf -C classes/app .
```

The command above is equivalent in purpose to `jar --create --file dist/app.jar --manifest app.mf -C classes/app .` in this lesson; the characters `c`, `f`, and `m` stand for create, file, and manifest, respectively. For beginners, the long syntax makes the role of each argument clearer.

**Do not declare duplicate `Main-Class` attributes across multiple manifest sources** and assume that every tool merges them in the order you want. Choose one clear packaging configuration mechanism and inspect the final manifest.

## 11. Quick Checks and Deployment Troubleshooting

When `java -jar dist/app.jar` fails, you can follow this sequence:

1. **Identify which JAR is running.** Are the file path and working directory correct? Does the command use `-jar`?
2. **Inspect `META-INF/MANIFEST.MF`.** Does `Main-Class` have the exact binary name? Does `Class-Path` contain the required entries?
3. **Check the class entries in the JAR.** Does `jar --list --file dist/app.jar` show `demo/Main.class` at the right package root?
4. **Check dependency files.** Does `dist/lib/helper.jar` exist? Does `jar --list --file dist/lib/helper.jar` contain `util/Message.class`?
5. **Check how paths are resolved.** `Class-Path: lib/helper.jar` is tied to the location of `app.jar`, not whatever directory you `cd` into.
6. **Do not try to "fix" `-jar` using `-cp`.** If you want to specify the classpath explicitly, run something like `java -cp ... demo.Main`.
7. **Read the actual throwable/cause.** Missing classes, wrong class versions, and binary mismatches can have different solutions.
8. **Check classloaders/modules when frameworks or plugins are involved.** A class with the same binary name might be getting loaded by an unintended loader.

To observe where code is being loaded from, inside a method you can use:

```java
System.out.println(Main.class.getClassLoader());
System.out.println(Main.class.getProtectionDomain()
        .getCodeSource().getLocation());
```

This is an **illustrative snippet** assuming `Main` exists and a suitable code source is present, not a standalone program. `getCodeSource()` or the source information may be absent in some environments, so production code needs `null` checks. The loader/URL output depends on the runtime and has no fixed stdout.

## 12. Self-Check Questions

**1. Is a JAR required to contain `Main-Class`?** No. Library JARs typically do not have an entry point. `Main-Class` matters when you want to launch the JAR with `java -jar`.

**2. Does `Main-Class` contain `demo/Main.class` or `demo.Main`?** It contains the binary name `demo.Main`, without the `.class` suffix.

**3. Which directory is `Class-Path: lib/x.jar` resolved relative to?** Relative to the URL/location of the JAR containing the manifest, i.e., the **context JAR**.

**4. Does `Class-Path` allow `lib/*` like `java -cp "lib/*"`?** No; the manifest uses relative URL entries, not CLI-style classpath wildcards.

**5. Does `javac -cp helper.jar` automatically make `java -jar app.jar` find helper.jar?** No. Compile-time and runtime lookup are two separate configurations.

**6. If `java -jar` reports `no main manifest attribute`, does that mean the bytecode in the JAR is unusable?** No. It may simply be a library JAR, or the packaging step may be missing an entry point.

**7. Why does running `java -jar app.jar` from a different working directory still find `lib/helper.jar`?** Because manifest relative URLs are based on the context JAR, not the current working directory.

**8. Does `Class-Path` guarantee that a class is loaded by the intended loader?** No. The classpath provides the search source; definition/delegation is determined by the class loader and the runtime environment.

**9. Does a regular JAR automatically understand libraries embedded under `lib/x.jar` inside its own ZIP?** No. You need flat class packaging, external dependencies via the manifest, or a specialized launcher/classloader if using nested JARs.

**10. Does using `java -cp ... demo.Main` read `Main-Class` to choose the main class?** No. The entry point is determined by the name `demo.Main` on the command line.

## 13. Official References

- *JAR File Specification*, sections **JAR Manifest**, **Main Attributes**, **Class-Path Attribute**, and URL resolution rules (Java 17): https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Java SE 17, *The java Command*: `-jar`, `-cp`/`--class-path` modes, and entry point: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17, *The jar Command*: `--create`, `--file`, `--manifest`, `--main-class`, `--list` options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Java SE 17 API, `java.lang.ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

**Key takeaway:** `Main-Class` explains **where to start running**, while `Class-Path` indicates **where to look for dependent classes/resources** in the classpath model. For `java -jar`, package the `demo/Main.class` entry properly, declare `Main-Class: demo.Main`, list dependencies using relative URLs such as `lib/helper.jar`, and distribute the complete directory structure alongside the main JAR.
