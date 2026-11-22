# Classpath Wildcards and Search Limits

> **Topic:** Java Core → ClassLoader → Search Paths. This lesson clarifies the `*` syntax in the **application classpath**, what is searched, when wildcards are expanded, directory/JAR limits, class loading order, and differences from the module path, manifest, and custom class loaders. Examples run on Java 17+.

## 1. Real-World Problem: Why Does lib/* Still Cause ClassNotFoundException?

Suppose an application has the directory:

```text
project/
├── app-classes/
│   └── demo/App.class
└── libs/
    ├── core.jar
    ├── helper.JAR
    ├── tools.zip
    ├── loose/Loose.class
    └── nested/
        └── plugin.jar
```

A familiar command:

```bash
java -cp "app-classes:libs/*" demo.App
```

By the Java launcher contract, the `libs/*` element is expanded into **files with the `.jar` or `.JAR` extension located directly in `libs`**. It does not mean "find every file and every subdirectory."

In the diagram:

| Item | Included directly in the classpath by `libs/*`? | Why |
| --- | --- | --- |
| `libs/core.jar` | Yes | JAR directly inside the specified directory. |
| `libs/helper.JAR` | Yes | `.JAR` extension is supported. |
| `libs/tools.zip` | No | Wildcards only list JARs; a ZIP can still be added to the classpath via an explicit path if appropriate. |
| `libs/loose/Loose.class` | No | `*` does not automatically add the directory containing loose class files. |
| `libs/nested/plugin.jar` | No | Does not recursively search for JARs in subdirectories. |
| `app-classes/demo/App.class` | Yes, via `app-classes` | This is a separate classpath element, not the result of `libs/*`. |

Therefore, if `demo.App` tries `Class.forName("plugin.Main")` while that class only resides in `libs/nested/plugin.jar`, the command above **does not automatically find** it. Similarly, `loose.Loose` under `libs/loose/Loose.class` requires adding **`libs`** as a *directory classpath root*.

## 2. The Classpath Is a List of Search Roots, Not a Scan of Every Class

The classpath (`-cp`, `-classpath`, or `--class-path`) consists of elements pointing to:

- **A root directory** containing a package structure; for example, `classes` contains `classes/com/acme/Thing.class`, whose binary name is `com.acme.Thing`.
- **A JAR file** storing classes/resources under their corresponding entry names; for example, `lib/tool.jar` contains `com/acme/Thing.class`.
- **A ZIP archive** when explicitly declared as a classpath element; `*` itself does not list ZIP files.

The Java launcher uses these elements to set up the class/resource search environment for the application. It does **not** pre-run a task to "load all classes from all JARs"; a loader typically locates and defines a class **when the program needs it**. Having a path to a JAR does not guarantee that every class in the JAR will be loaded, linked, initialized, or accessible.

Converting a binary name into a resource path:

```text
Binary name:      com.acme.Thing
Class entry:      com/acme/Thing.class

Root:             classes
Full path:        classes/com/acme/Thing.class

Root:             lib/tool.jar
JAR entry:        com/acme/Thing.class
```

Do not put `classes/com/acme` on the classpath and expect the loader to find `com.acme.Thing`: the correct root must be `classes`. Resource lookup (`getResource`, `getResources`) has its own rules and typically uses `/`-delimited paths; do not confuse a resource path with a binary name.

## 3. Exact Wildcard Syntax

For the Java launcher:

- `libs/*`: all JAR files directly inside `libs` with the `.jar` or `.JAR` extension.
- `*`: all JARs directly inside the **current working directory** (if the classpath element path is just `*`).
- `classes:libs/*` (Linux/macOS), or `classes;libs/*` (Windows): combines a classes directory with a JAR wildcard.
- `libs/*:libs` or `libs;libs/*`: combines both JARs and loose classes in the `libs` directory; the order of the two elements can matter when classes/resources have duplicate names.

The specification does **not** allow `*` to be interpreted as a general glob. Usages without corresponding "automatic listing" semantics for classpath wildcards:

| Desired Syntax | Wrong Expectation | Use Instead |
| --- | --- | --- |
| `libs/foo*.jar` | Match by `foo` prefix | List the specific JAR files, or manage dependencies with a build tool. |
| `libs/**/*.jar` | Recursive JAR search | Build the classpath from each permitted directory/JAR, or use a build tool. |
| `libs/*/plugin.jar` | Search in all subdirectories | Explicitly specify `libs/nested/plugin.jar` or another classpath root. |
| `libs/*` | Find all loose `.class` files in `libs` | Add `libs` as a separate element. |
| `libs/*` | Find `.zip` files in `libs` | Add the specific ZIP path. |
| `libs/*` | Find libraries inside JARs nested within another JAR | Use an appropriate packaging loader mechanism; the standard Java launcher does not extract nested JARs automatically. |

A JAR starting with a dot (*hidden file*) can still be listed if it matches the JAR extension. Wildcard expansion is handled **early by the launcher before running `main`**, not as dynamic syntax parsed by `ClassLoader.loadClass` on each class lookup.

**The order of JARs within a wildcard is not guaranteed.** Even if `libs` contains `a.jar` and `b.jar`, do not infer which one is searched first solely from the file names. If both JARs contain different versions of `com.acme.Widget`, the result may depend on the environment or expansion order. To achieve a deterministic precedence order, list the JARs explicitly or use a controlled dependency resolution mechanism.

## 4. Different Separators Between Linux/macOS and Windows

A wildcard element stays `libs/*` on both operating systems; the important difference is the **separator character between classpath elements**:

| Operating System | Separator | Example Command |
| --- | --- | --- |
| Linux/macOS | `:` | `java -cp "classes:libs/*" demo.App` |
| Windows PowerShell/CMD | `;` | `java -cp "classes;libs/*" demo.App` |

Use double quotes around the **entire classpath string**, especially in Unix shells: if `*` is left unquoted, **the shell may expand it before the Java launcher**, causing the command line to be split/interpreted differently from what was intended. A reliable example:

```bash
java --class-path "classes:libs/*" demo.App
```

On Windows:

```powershell
java --class-path "classes;libs/*" demo.App
```

Relative paths in the classpath are resolved against the **working directory at launch time**, not automatically relative to the location of `.class` files or the directory containing a JAR. If you launch from an IDE, a service/container, or run a script from a different directory, `libs/*` may point elsewhere. When debugging, check the working directory:

```java
System.out.println(System.getProperty("user.dir"));
```

This is a snippet to place inside a method; `user.dir` only helps diagnose path context and does not guarantee that the active classpath can be updated by reassigning the property.

## 5. When Wildcards Are Expanded and the Meaning of java.class.path

The Java launcher expands `libs/*` into a sequence of concrete JAR paths **before `main` starts**. Therefore, inside the program you can inspect:

```java
System.out.println(System.getProperty("java.class.path"));
```

For example, if `libs` contains `a.jar` and `b.jar`, a string equivalent to the following may appear:

```text
classes:libs/a.jar:libs/b.jar
```

This is only an **illustrative order**, not a fixed output: the JAR order may differ; on Windows the separator is `;`. More importantly, the value of `java.class.path` may already be the **expanded list**, whereas `System.getenv("CLASSPATH")` (if present) is only the initial environment string.

Do not treat `java.class.path` as an API for modifying the classpath at runtime:

- `System.setProperty("java.class.path", "...")` only modifies **the property value in the process**; it has **no contract** requiring the application class loader to update the sources it uses.
- Custom loaders, separately loaded plugin JARs, manifest dependencies, and named modules may fall outside this string.
- On JDK 9+, the default built-in application loader is not a `URLClassLoader`; do not cast `ClassLoader.getSystemClassLoader()` to `URLClassLoader` just to call `getURLs()`.
- The JVM may be running inside a container/framework whose loader delegation differs from a plain `java` launch environment.

When you need to **change dependencies**, decide at launch/build time or create a dedicated loader with explicit sources, rather than modifying the property and waiting for new classes to appear.

## 6. Java 17+ Example Reproducing Three Search Limits

The experiment uses one JAR directly inside the `libs` directory, one JAR inside a subdirectory, and one loose `.class` file. The program checks them via `Class.forName` without any libraries outside the JDK.

### Source Structure

Create the files:

```text
src/demo/PathDemo.java
src/greet/example/Greeter.java
src/extra/deep/Extra.java
src/loose/loose/Loose.java
```

**File `src/demo/PathDemo.java`:**

```java
package demo;

public class PathDemo {
    public static void main(String[] args) {
        for (String name : new String[]{
                "example.Greeter", "deep.Extra", "loose.Loose"}) {
            try {
                Class.forName(name);
                System.out.println(name + ": FOUND");
            } catch (ClassNotFoundException e) {
                System.out.println(name + ": MISSING");
            }
        }
    }
}
```

**File `src/greet/example/Greeter.java`:**

```java
package example;
public class Greeter {}
```

**File `src/extra/deep/Extra.java`:**

```java
package deep;
public class Extra {}
```

**File `src/loose/loose/Loose.java`:**

```java
package loose;
public class Loose {}
```

### Preparing Artifacts and Running (Linux/macOS)

Run from the directory containing `src`. Compile three classes into three different locations, then package two JARs:

```bash
mkdir -p libs/nested
javac -d app-classes src/demo/PathDemo.java
javac -d build/greet src/greet/example/Greeter.java
javac -d build/extra src/extra/deep/Extra.java
javac -d libs src/loose/loose/Loose.java
jar --create --file libs/greet.jar -C build/greet .
jar --create --file libs/nested/extra.jar -C build/extra .

java -cp "app-classes:libs/*" demo.PathDemo
```

**Exact stdout of the first run, verified on OpenJDK 21:**

```text
example.Greeter: FOUND
deep.Extra: MISSING
loose.Loose: MISSING
```

Explanation: `example.Greeter` is inside `libs/greet.jar` (a JAR directly in `libs`), whereas `deep.Extra` is inside `libs/nested/extra.jar` and `loose.Loose` is in `libs/loose/Loose.class`. Neither of the latter two sources is automatically listed by `libs/*`.

Run a second time, **explicitly adding** the wildcard for the subdirectory and the root of the loose class:

```bash
java -cp "app-classes:libs/*:libs/nested/*:libs" demo.PathDemo
```

**Exact stdout of the second run:**

```text
example.Greeter: FOUND
deep.Extra: FOUND
loose.Loose: FOUND
```

The source code did not change; **only the class search path configuration changed**. This is proof that each classpath element creates a search root and `*` does not scan recursively.

### Equivalent Execution on Windows PowerShell

After creating the same source structure, prepare `libs\nested` (if it does not exist yet) and run the `javac`/`jar` commands as above; PowerShell also accepts `/` for file names in Java commands. The commands to run the application are:

```powershell
java -cp "app-classes;libs/*" demo.PathDemo
java -cp "app-classes;libs/*;libs/nested/*;libs" demo.PathDemo
```

The `FOUND/MISSING` results match the two runs above. Do not replace `:` with `;` inside package names, binary class names, or resource paths; this separator is **only used between classpath elements**.

## 7. Classpath Order, Duplicate Class Names, and Duplicate Resource Names

The classpath is generally organized as **an ordered list**. When equivalent sources contain the same class name, path order and delegation affect which class is found:

```text
-cp "app-classes:lib/new.jar:lib/old.jar"

- app-classes first
- new.jar next
- old.jar last
```

In this illustrative example, if both `new.jar` and `old.jar` contain `com/acme/Client.class`, the default loader's classpath lookup typically prioritizes the earlier entry **provided parent delegation does not load that class first**. However, if `lib/*` is used instead of the two explicit file names, **the order among JARs in a wildcard is unspecified by the contract**.

For classes with the same binary name, runtime identity also depends on the **defining class loader**. Multiple distinct loaders can load two classes with the same name and produce two incompatible types; classpath wildcards do not unify classes defined by separate loaders.

Resources also carry the risk of name collisions:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader != null) {
    var resources = loader.getResources("config.properties");
    while (resources.hasMoreElements()) {
        System.out.println(resources.nextElement());
    }
}
```

This snippet goes inside a method that declares `throws IOException` or handles the exception. `getResources` can list multiple URLs if identically named resources exist across sources visible to the loader; the order and set depend on the loader/module and the actual classpath order. If you only use `getResource`, it typically returns the first resource found according to the loader's rules, so **you may pick up the wrong configuration file** when multiple JARs package the same `config.properties` file.

Do not resolve collisions merely by renaming JAR files alphabetically and relying on wildcards; it is better to remove the duplicate dependency, place the resource in its own namespace, or configure the classpath order explicitly.

## 8. CLASSPATH, -cp, java -jar, and JAR Manifest

### CLASSPATH Environment Variable

If `-cp`/`-classpath`/`--class-path` is not used, the Java launcher can read the classpath from the `CLASSPATH` environment variable. Classpath wildcards are supported in this variable in the same way as when passing the `-cp` option.

However, **when an explicit `-cp` option is provided, it overrides `CLASSPATH`** rather than automatically appending to the environment variable. For applications/CI, configuring `-cp` explicitly or using a build tool is generally clearer than relying on a machine-wide environment variable.

### When Using java -jar

`java -jar app.jar` launches an executable JAR based on the manifest's `Main-Class`. According to the launcher documentation, in this mode **other classpath settings are ignored**. For example:

```bash
java -cp "libs/*" -jar app.jar
```

This does not guarantee loading `libs/*` for the application; the `-cp` configuration does not take effect the way someone writing that command might expect. If you want to control the classpath yourself, use the form:

```bash
java -cp "app.jar:libs/*" demo.Main
```

Assuming `demo.Main` is the binary name of the main class, this is the Linux/macOS command. On Windows, use `"app.jar;libs/*"`. This is a configuration pattern, **not a standalone program**; the JAR name and main class must be replaced with actual artifacts.

An executable JAR can also declare dependencies using **`Class-Path` in the manifest** or use a framework's own launcher/loader. Those mechanisms differ from Java classpath wildcards.

### Class-Path in the JAR Manifest

Example manifest:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/a.jar lib/b.jar
```

This header lists URLs relative to the JAR containing the manifest. **The `*` wildcard is not supported** as on the command line: `Class-Path: lib/*` does not mean loading every JAR in `lib`. You must list each valid JAR individually or use a packaging tool/launcher that supports the application's dependency model.

Manifest paths are also subject to normalization rules, URL/path restrictions, and access constraints of the JAR Specification; do not infer unrestricted filesystem traversal from them.

## 9. Classpath Wildcards Differ from the Module Path

Since Java 9, JPMS adds the **module path**, specified by `--module-path` or `-p`:

```bash
java --module-path mods --module com.acme.app/com.acme.Main
```

The classpath and module path address two different scopes:

| Aspect | Classpath | Module Path |
| --- | --- | --- |
| Option | `-cp`, `-classpath`, `--class-path` | `--module-path` or `-p` |
| Listing JARs directly in a directory with `libs/*` | Yes, as a classpath wildcard | **Do not apply classpath wildcard syntax** to guess how modules are located. |
| Directory containing multiple artifacts | For the classpath, you must list JARs or `libs/*`; `libs` itself is a root for class files | For the module path, a directory **containing modules** can be a module path element. |
| How modules are used | Classpath classes belong to the unnamed module of the appropriate loader | Named modules must be discovered, resolved (`resolution`), and have appropriate readability/exports. |
| Lookup | Based on classpath entries and loader behavior | Based on the module finder/graph, module layers, and associated class loaders. |

Usually `--module-path mods` alone is enough if `mods` is a directory containing modular JARs or exploded modules; do not write `mods/*` out of classpath habit. Beyond the path existing, a named module must also be **resolved** into the configuration; a module merely sitting in the directory does not mean all its classes load automatically or all its packages are exported.

Classpath wildcards do not bypass `module-info.java`, `exports`, `opens`, module readability, or access checks. If you encounter `ClassNotFoundException` or `IllegalAccessError` with named modules, distinguish between search path errors and module configuration/accessibility errors.

## 10. The Actual Limits of Search Scope Are Determined by the Class Loader

The `-cp` option configures the search path for the application loader in a standard launcher environment; the JVM also has bootstrap/platform loaders and may have multiple **custom loaders**.

Common model:

```text
Code calls Class.forName / loadClass
             |
             v
          Caller loader
             |
             | parent-first delegation if the loader uses that policy
             v
       Parent / platform / bootstrap
             |
             '--- classes in application / classpath managed by the appropriate loader
```

Even if `libs/greet.jar` is expanded into the application classpath, **an isolated plugin loader may not see it** if it does not delegate or use the corresponding source. Conversely, a custom `URLClassLoader` can have its own URLs/JARs **that do not appear** in `java.class.path`.

Key APIs:

- `ClassLoader.getSystemClassLoader()`: usually the application loader, though its implementation type is not guaranteed by Java SE; it can be customized.
- `clazz.getClassLoader()`: identifies the **defining loader** of type `clazz`; returns `null` for bootstrap classes such as `java.lang.String`.
- `Thread.currentThread().getContextClassLoader()`: the context loader, commonly used by SPIs/frameworks; it may differ from the system loader or be `null`.
- `Class.forName(name, false, chosenLoader)`: explicitly requests loading via the specified loader, **without initializing** the class as a result of this call.
- `loader.getResource("com/acme/config.properties")` and `getResources`: query resources; they are not guaranteed to find every module/JAR source outside the loader's scope.

Beyond locating the bytes, the JVM must check the name, class-file version, linking, dependencies, visibility, and certain package/module access rules. A class may exist inside a JAR **yet still be unusable** due to missing transitive dependencies, API changes, loader conflicts, or module access issues.

A launcher/framework that packages nested JARs inside an executable JAR can implement its own loader to read them; **the standard Java launcher classpath wildcard does not automatically open a JAR inside another JAR**.

## 11. Common Errors and How to Inspect Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `ClassNotFoundException: plugin.Main` | `plugin.jar` is in `libs/nested`; `libs/*` does not scan recursively. | Add `libs/nested/*` or the path to that JAR. |
| `ClassNotFoundException: loose.Loose` | Only `libs/*` was used; `libs/loose/Loose.class` is not inside a JAR. | Add the classpath root `libs`. |
| `Could not find or load main class demo.App` | The root containing `demo/App.class` was not added to the classpath, or launched from a different working directory. | Add `app-classes` and verify the package path. |
| Works on Linux, fails on Windows | Using `:` instead of `;` between classpath elements. | Use the OS separator and quote the classpath. |
| Works when invoked directly, fails in a shell script | Shell expanded `*` or quoted the classpath incorrectly. | Quote the entire `-cp` value and check the executed command. |
| `NoClassDefFoundError` when code references a class | Missing transitive dependency, initialization failure, or binary incompatibility. | Read `Caused by`; inspect runtime JARs and loaders, not only the main JAR. |
| Resource loaded from a different JAR | Multiple duplicate resource entries exist, and wildcard JAR enumeration order is nondeterministic. | Resolve the conflict / list the classpath deterministically. |
| `java -jar` ignores JARs declared in `-cp` | Other classpath settings are ignored when using `-jar`. | Use manifest `Class-Path`, the proper launcher, or run by main class name with `-cp`. |
| Manifest has `Class-Path: lib/*` but dependencies are missing | The header does not perform launcher wildcard expansion. | List specific JAR URLs. |
| Added a JAR after startup but the loader does not see it | Wildcards were already expanded before `main` ran, and the loader has fixed search sources. | Restart with the updated classpath or design a dedicated dynamic loader. |
| `ClassCastException` between two types with the same name | Two different defining class loaders. | Check `clazz.getClassLoader()`, and share APIs through an appropriate parent loader. |
| JAR contains the class, yet the module still reports an access error | JPMS visibility/readability/exports/opens rules. | Check the module configuration instead of expanding the classpath arbitrarily. |

### Repeatable Debugging Workflow

1. Print the **actual Java command** in the script/container/IDE, `java -version`, the working directory, and the `-cp` and `CLASSPATH` values.
2. Inspect `System.getProperty("java.class.path")` to see the classpath entries initialized at startup; keep in mind it does not describe all modules/custom loaders.
3. Inspect JAR contents with `jar --list --file libs/greet.jar` (or `jar tf libs/greet.jar`). Look for the exact entry `example/Greeter.class`, distinguishing the archive root from the package path.
4. Check whether the JAR lies **directly inside** the wildcard directory or in a subdirectory; distinguish `.jar/.JAR` from `.zip` and loose classes.
5. If there are duplicate classes/resources, try **listing each JAR in explicit order**; resolve conflicts via the dependency graph instead of relying on wildcards.
6. If it still fails, compare the caller's loader with that of the target type, parent delegation, and module configuration; do not assume a JAR visible on the OS will automatically be visible through every loader.
7. On HotSpot, you can use `-Xlog:class+load=info` to diagnose class loading, though the log **is not guaranteed** to show the entire resource resolution process or every failed lookup path.

Example diagnostic commands (Linux/macOS; replace with the actual class name):

```bash
jar tf libs/greet.jar
java -Xlog:class+load=info -cp "app-classes:libs/*" demo.PathDemo
```

`-Xlog` prints many extra JVM lines, so **do not use this command's output as the exact output in the Section 6 experiment**.

## 12. Self-Check

1. **Does `libs/*` load `libs/sub/helper.jar`?** No, classpath wildcards do not traverse recursively.
2. **Does `libs/*` include `libs/Thing.class`?** No, `*` is used to list JAR files; for loose classes, add `libs`.
3. **Is the order of `libs/a.jar` and `libs/b.jar` in wildcard expansion fixed?** It is unspecified; list JARs explicitly if order matters.
4. **Why might `System.getProperty("java.class.path")` no longer contain `*`?** The launcher expands wildcards before `main` runs.
5. **Does `java -cp "libs/*" -jar app.jar` guarantee loading JARs from `libs`?** No. `-jar` mode ignores other classpath settings.
6. **Can you write `Class-Path: libs/*` in a manifest to list JARs?** No; the manifest `Class-Path` does not use launcher wildcards.
7. **How does `--module-path mods` differ from `-cp "mods/*"`?** One configures the finder/graph for named modules, while the other expands JARs into classpath entries for appropriate application classes.
8. **Why can a program have the right JAR and still throw `ClassNotFoundException`?** It could be a wrong working directory, binary name, loader, module visibility, or dependency; you must examine the actual search path and triggering code.
9. **If you change `java.class.path` via `System.setProperty` and re-run `Class.forName`, must the JVM see the new JAR?** There is no such contract.
10. **Do two plugin loaders seeing the same JAR file necessarily share the same class identity?** No. If they each define the same binary name independently, they are two different runtime types.

## 13. Official References

- [Java SE 21 — `java` launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--class-path`, `-jar`, classpath wildcards, and the module path.
- [Oracle — Understanding class path wildcards](https://docs.oracle.com/javase/8/docs/technotes/tools/windows/classpath.html): wildcards only search for JARs, non-recursively, with no guaranteed order, plus `CLASSPATH` and manifest behavior.
- [Java SE 21 — `javac`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-cp`, `--class-path`, source/class output roots.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): `Class-Path` in the manifest and relative URLs.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource`, `getResources`, parent delegation.
- [Java SE 21 — Module System / `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module configuration and class loaders of named modules.
