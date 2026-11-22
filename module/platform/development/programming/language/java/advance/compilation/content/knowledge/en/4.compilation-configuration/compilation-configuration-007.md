# Classifying Standard, Extra, and Internal Options of `javac`

`javac` is the tool that compiles Java source code into class files. Besides the list of `.java` files, the `javac` command accepts **options** to choose language version, platform APIs, dependency paths, bytecode output location, warnings, annotation processing, diagnostics, and compiler behavior.

Three groups must be distinguished: **standard**, **extra/extended**, and **internal/hidden**. The classification reflects the tool's interface and publication level, and **cannot be inferred completely from the number of dashes or option prefixes**.

## 1. Overview

| Group | How to Find | Purpose and Usage Level | Examples |
| --- | --- | --- | --- |
| **Standard** | `javac --help`; *Standard Options* section in the exact JDK's manual | Primary CLI interface to configure routine compilations; publicly documented, used in scripts and build tools | `--release 17`, `-d out`, `-cp libs/api.jar`, `-encoding UTF-8`, `-g`, `-Werror` |
| **Extra / extended** | `javac --help-extra` or `javac -X`; *Extra Options* section | Advanced options for diagnostics, lint, annotation processing, plugins, module adjustments; publicly documented yet may differ across releases | `-Xlint:unchecked`, `-Xdiags:verbose`, `-XprintRounds`, `-Xmaxerrs 50`, `--add-exports` |
| **Internal / hidden** | Usually not listed by either help screen; only verifiable from implementation or specialized documentation | For compiler experimentation/debugging/development; no compatibility guarantee at the public CLI interface level | The `-XD...` family in OpenJDK `javac`; other options marked hidden by the implementation |

**Note on the word “standard”:** “standard option of `javac`” is how tool options are grouped in the JDK. That does not mean every flag is required by the Java Language Specification to be implemented by every third-party compiler. Conversely, “extra” does not mean “secret”: many extra flags have official documentation sections and are used routinely in code checking.

In OpenJDK source, options are categorized by the tags `STANDARD`, `EXTENDED`, `HIDDEN`. This is a detail for understanding OpenJDK `javac`'s interface structure; the compiler's internal source code does not itself become a stable API.

## 2. Looking Up Option Groups Directly on Your Machine

Use the exact compiler that the project actually runs:

```sh
javac -version
javac --help
javac --help-extra
javac --help-lint
```

- `javac -version` shows the actual version. Commands in terminal, IDE, and CI may point to three different JDKs.
- `javac --help`, which also has aliases `-help`/`-?`, displays **standard options**.
- `javac --help-extra` or `javac -X` displays **extra options** published by the tool.
- `javac --help-lint` lists valid **lint keys** for `-Xlint` on that exact JDK version.

Example:

```text
javac -X
```

The command above only **prints help** about extra options; it **does not enable all `-X` flags**. Whereas:

```text
javac -Xlint:unchecked Example.java
```

asks the compiler to check the `unchecked` warning group on source. Do not equate standalone `-X` with `-Xlint` or `-Xdiags`.

Flag names and support can change between releases, so when a flag is unrecognized, cross-check **version**, help screens, and documentation for the JDK in use before modifying build configuration.

## 3. Standard Group: Configuring What Is Compiled and Emitted

| Task Group | Common Standard Options | Meaning |
| --- | --- | --- |
| Platform target | `--release 17`; `--source 17`; `--target 17` | Constrains platform API, source syntax, or class-file version per each flag's scope |
| Output | `-d out`, `-s generated`, `-h headers` | Where to generate class files, generated sources, native headers |
| Dependencies | `--class-path path` / `-cp path`, `--source-path path` | Where to find classes/JARs and dependency sources |
| Named modules | `--module-path path`, `--module-source-path path`, `--module name` | Declares modular environment and compilation mode |
| Source reading/debug | `-encoding UTF-8`, `-g`, `-g:none` | Source encoding and metadata for debugging |
| Warnings | `-Werror`, `-nowarn` | Decides whether warnings fail the build or are displayed |
| Annotation processing | `-processor name`, `--processor-path path`, `-proc:none` | Declares and controls processors |
| Reflection metadata | `-parameters` | Stores formal parameter names so reflection can read them |
| CLI utilities | `--help`, `--version`, `@argfile` | Help, version, loading arguments from a file |

Flags are components of a command; **source file names** like `src/demo/Main.java` are operands, not options. Do not put every string after `javac` into a list of flags.

### Choosing Java Target: `--release` Differs from `--source` and `--target`

- `--source N`: allows/checks syntax and language features matching Java level `N`.
- `--target N`: chooses the target class file version.
- **`--release N`**: combines constraints on syntax, class file target, and **supported platform APIs** for Java `N`, when the compiler allows that target.

Example on a JDK supporting Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
```

This is usually the right choice if the product must run on Java 17. Writing only `-source 17 -target 17` in a newer JDK can accidentally permit calling APIs that only exist in the newer JDK. `--release` does not automatically guarantee external libraries or the application's runtime environment are compatible: separate verification is needed.

**Do not place `--release` together with `--source`/`--target`** in one `javac` invocation. Nor is the compiler required to support every imaginable release number; check the targets listed by that JDK.

### `-Werror` and `-nowarn` Are Standard, Despite Relating to Warnings

`-Werror` treats warnings that occur as compilation errors. `-nowarn` disables warnings per documented mechanism (equivalent to `-Xlint:none`). Meanwhile, `-Xlint` **keys** belong to the extra group. Both kinds of options can be combined: `-Xlint` selects warning categories, `-Werror` fails the build when warnings appear.

### `-d`, `-s`, and `-h` Have Different Targets

`-d out` emits `.class` into a package-structured directory tree, `-s generated` is for source code generated by annotation processors, and `-h headers` is for native headers when requested. `-d` does not mean `javac` creates a JAR or copies all resources automatically.

## 4. Extra Group: Diagnostics and Advanced Tasks

| Extended Option | Effect | Use Case |
| --- | --- | --- |
| `-Xlint` | Enables lint warnings recommended by the compiler | Quality checks |
| `-Xlint:unchecked` | Warns on generic operations not fully checkable | Raw types, unchecked conversions |
| `-Xlint:deprecation` | Warns about deprecated API usage | Library/API migration |
| `-Xlint:all` | Enables all valid lint categories | Auditing source when able to handle warnings |
| `-Xdiags:verbose` | Shows more detailed diagnostics | Generic, overload, and type inference errors |
| `-Xmaxerrs 50` | Limits number of printed errors | Reducing cascading error logs |
| `-Xmaxwarns 50` | Limits number of printed warnings | Reducing build logs |
| `-XprintRounds` | Prints annotation processing rounds | Debugging processors/generation |
| `-XprintProcessorInfo` | Prints information about processors handling annotations | Analyzing active processors |
| `-Xprefer:source` | Prefers source when both source and class can be found in certain cases | Investigating implicit compilation |
| `-Xplugin:<name>` | Requests loading the corresponding `javac` plugin | Integrating advanced analysis tools |
| `--add-exports`, `--add-reads`, `--patch-module` | Modifies module visibility/configuration in compilation environment | Advanced modular tasks |

**Two observations to remember:** Extra options are officially documented, and **not every extra option starts with `-X`**: the `--add-exports`/`--patch-module` group is also extra in `javac` documentation. Conversely, standalone `-X` is a request to show help, not compilation configuration.

Extra options should be added with a **clear purpose**. Turn on `-Xdiags:verbose` to understand hard errors, `-Xlint:unchecked` to detect risky generic operations; do not add a mysterious set of flags and then not know which flag made changes.

### Example Combining Standard and Extra

```sh
javac --release 17 -encoding UTF-8 -Xlint:unchecked -Xlint:deprecation -Werror -d out src/demo/Main.java
```

Here:

- `--release`, `-encoding`, `-Werror`, `-d` are **standard**.
- The two `-Xlint:...` flags are **extra**, enabling targeted warnings.
- If the compiler emits matching warnings, `-Werror` can fail the build; if there are no errors or warnings, the build can succeed.

`-Xlint` supplements diagnostics; syntax errors and basic type checking still run without it.

### What Does `-Xdiags:verbose` Do?

```sh
javac --release 17 -Xdiags:verbose -d out src/demo/Main.java
```

It displays more details in diagnostics; it does not automatically fix code, change Java target, run `main`, or guarantee different bytecode when code is valid.

### Does Annotation Processing Need Extra Options to Run?

Not necessarily. A processor can be configured via standard options like `-processor`, `--processor-path`, and `-proc:none`. `-XprintRounds`/`-XprintProcessorInfo` only **observe** processing when a matching processor exists; `-Xplugin:<name>` requires the plugin to actually exist. Default processor discovery changes across JDKs; builds need explicit configuration for reproducibility.

## 5. Internal/Hidden Group: Why Is `-XD` a Different Boundary?

In the OpenJDK implementation of `javac`, `-XD` is an entry point to the internal option table. Representation syntax at the implementation level can be:

```text
-XDkey=value
-XDkey
```

OpenJDK source handles `-XDkey=value` by putting the key/value pair into the internal option table; the `-XDkey` form has special handling to create an entry. **That is an implementation characteristic**, not an interface with a stable contract for every Java program or every compiler.

Do not infer “having `-XD...` syntax means every key is valid and effective”: an entry not read by the compiler may have no effect. To understand a specific key, you must read **the exact source code, commit/build, and JDK version** where it is used.

### Risks When Putting Internal Flags into a Project

1. **Lack of compatibility guarantees:** names, semantics, or affected compiler phases can change without going through deprecation like public APIs.
2. **Can break build assumptions:** experimental flags used to stop phases, log, change processing order, or inspect internals can make output non-representative of production builds.
3. **Implementation dependence:** another compiler, or another vendor's JDK, may not recognize the flag or interpret it differently.
4. **Hard to maintain:** CI/IDE maintainers cannot find the flag in `--help-extra` and do not know why it is present.

If investigating a compiler bug itself, you can study internal options **in an isolated environment**, record distribution/version/commit, read the corresponding code, and remove the flag from the main build after investigation. **Hidden** also does not mean everything is `-XD`; implementations can mark other debug flags hidden.

### Table Distinguishing “Extra” and “Internal”

| Question | Extra (e.g. `-Xlint`) | Internal (e.g. `-XDkey`) |
| --- | --- | --- |
| Present in `--help-extra`? | Usually yes | Usually no |
| Has official description for use? | Yes, per JDK version | Not a general user contract |
| Should be used in builds? | Can be, if needed and tested | Avoid, except controlled compiler research |
| Can change between JDKs? | Yes; must check version | Yes, including detail changes without announcement |
| Can prefix alone identify group? | No; there are `--...` extras | No; hidden has multiple forms |

## 6. `-J`: Standard Option Forwarding Flags to the JVM Running the Compiler

`-J` is a **standard launcher option of `javac`**, used to pass an argument to **the JVM executing the compiler**. Do not confuse it with options controlling Java output or compiler extra options.

Example:

```sh
javac -J-Xmx512m --release 17 -d out src/demo/Main.java
```

- `-J-Xmx512m` tells the launcher to pass `-Xmx512m` to the compiler's JVM (maximum heap limit in JVM syntax).
- `--release 17` determines the Java target level.
- `-d out` determines where class files are written.

The heap of the JVM running **`javac`** differs from the heap of the JVM running the **`java`** application afterward. If you want to set runtime heap, configure it separately at run time: e.g., `java -Xmx512m -cp out demo.Main`.

The `-J` syntax attaches directly to the JVM option: `-J-Xmx512m`. Per the `javac` manual, `-J` must not be placed in an `@argfile` argument file. With the Compiler API or build tools running the compiler **in the same process**, JVM configuration must fit the host process rather than assuming `-J` will be interpreted like the CLI launcher.

## 7. Java 17 Practice: Using Both Standard and Extra Flags

Create a file `src/demo/Main.java`:

```java
package demo;

import java.util.List;

public final class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        for (String name : names) {
            System.out.println(name);
        }
    }
}
```

From the project directory, with a JDK supporting Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out -g -Xlint:all -Werror src/demo/Main.java
java -cp out demo.Main
```

With the code above, `javac` succeeds and emits `out/demo/Main.class`. The `java` command prints the **exact stdout**:

```text
Lan
Minh
```

Grouping in the example:

| Component | Group | Role |
| --- | --- | --- |
| `--release 17` | Standard | Java 17 target |
| `-encoding UTF-8` | Standard | Read source file as UTF-8 |
| `-d out` | Standard | Location to create class files |
| `-g` | Standard | Write fuller debug information |
| `-Xlint:all` | Extra | Enable lint warnings |
| `-Werror` | Standard | Emitted warnings fail the build |
| `src/demo/Main.java` | Operand | Source file, not an option |

**No internal `-XD` flag is needed** for this workflow. Standard and extra groups coexist in one valid command.

### Second Example: Verifiable Generic Warnings

File `src/demo/Warnings.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

public final class Warnings {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("one");
        System.out.println(raw.get(0));
    }
}
```

Compile command:

```sh
javac --release 17 -Xlint:rawtypes,unchecked -d out src/demo/Warnings.java
java -cp out demo.Warnings
```

The compiler emits warnings related to raw types and unchecked method invocation. Exact wording, line numbers, and warning positions can vary by JDK. Without `-Werror`, compilation can still succeed and the program's stdout is:

```text
one
```

Add `-Werror`:

```sh
javac --release 17 -Xlint:rawtypes,unchecked -Werror -d out src/demo/Warnings.java
```

When a warning is emitted, compilation fails. Do not use the **continued existence** of `out/demo/Warnings.class` to claim the new compilation succeeded, because files from an earlier run may not have been deleted. Inspect the **exit code** and diagnostics corresponding to the compilation being examined.

## 8. Syntax Rules That Are Easy to Confuse

### Aliases and Number of Dashes

`--class-path`, `-classpath`, and `-cp` are different names for the classpath mechanism; `--source` and `-source` may also both be accepted. Therefore, the number of dashes **does not determine** whether an option belongs to standard or extra. `--add-exports` looks like standard flags starting with `--` yet is classified as extra.

Parameter-passing syntax depends on each flag. For eligible long flags, you can write `--release 17` or `--release=17`. With `-Xlint:unchecked`, the colon is part of the syntax. `-d out` requires a directory argument. Do not swap `=`, `:`, and spaces arbitrarily.

### Path Separators Differ by Operating System

Path lists like classpath accept `;` on Windows and `:` on Linux/macOS. This is an OS and path-option detail, not a difference between standard and extra. Paths containing spaces must be quoted properly per shell.

### Version-Dependent Option Support

Java 8 lacks module-system options introduced in Java 9 onward. `--release` only accepts releases supported by the compiler. An option can appear in one release and change, become restricted, or be removed in another release. `--help-extra` listing a flag in JDK 21 does not guarantee every other JDK accepts it with the same semantics.

### `@argfile` Does Not Change Classification

File `compile.args` can contain:

```text
--release 17
-encoding UTF-8
-d out
-Xlint:all
src/demo/Main.java
```

Invoke:

```sh
javac @compile.args
```

`@argfile` is a standard mechanism for passing long argument lists. `-Xlint:all` **remains extra** even when placed in an argument file. Paths inside the file are usually relative to **the working directory of the compiler invocation**, not the argument file's location. `-J` cannot be passed via an argument file per launcher specification.

The `JDK_JAVAC_OPTIONS` variable can also automatically prepend arguments to `javac`. When compile behavior differs between terminal and CI, check this environment variable, `PATH`, `JAVA_HOME`, toolchain configuration, and actual arguments before blaming the compiler itself.

## 9. How to Choose Flags in a Project

1. **State the required purpose:** Java 17 compatibility, clear output path, generic errors, or debugging annotation processing?
2. **Start from the appropriate standard group**: `--release`, `-d`, `-encoding`, classpath/module path, annotation processor settings.
3. **Add extras intentionally:** `-Xlint` to scan warnings; `-Xdiags:verbose` when needing to understand errors; `-XprintRounds` when investigating processors.
4. **Avoid internals on the main build path:** use `-XD...` only in compiler research with an identified version and controlled environment.
5. **Record the toolchain:** `javac -version`, actual build commands, options affecting the compiler, and options sent to the JVM via `-J`.
6. **Verify output:** exit code, logs, new class files, test runs on the target JVM; do not rely on leftover artifacts.

### Common Misconceptions

- **“`-X...` is always an internal option.”** False: `-Xlint` and `-Xdiags` are publicly documented extras.
- **“Without a leading `-X`, it must be standard.”** False: there are `--...` options in the extra group.
- **“`javac -X` enables all lint.”** False: it prints help; `-Xlint` is what controls lint.
- **“`-J-Xmx512m` gives the compiled app a 512 MB heap.”** False: it configures the JVM running the compiler.
- **“`-XD...` is a good way to replace a missing option.”** False: internal keys are not public APIs and cannot replace unsupported features.
- **“Documented extra options never change.”** False: always check the manual and help of the actual toolchain version.
- **“The `.class` file still exists, so every compile flag worked.”** False: the file could be output from an earlier run.

## 10. Checklist for Self-Classification

- [ ] Ran `javac -version` locally and in CI?
- [ ] Cross-checked `javac --help` and `javac --help-extra`?
- [ ] For `-Xlint`, looked up `javac --help-lint`?
- [ ] Distinguished flags read by the compiler, `-J` flags sent to the compiler JVM, and flags of the `java` command running the app?
- [ ] Understood whether an option affects source, bytecode, diagnostics, or processors?
- [ ] Avoided combining `--release` with `--source`/`--target`?
- [ ] Are there any hidden flags in the build that need removal or verification against the exact version/source?
- [ ] Confirmed exit code, warnings, and class files of the exact compilation run?

**Takeaway:** The **standard** group is the primary configuration interface of `javac`; the **extra** group provides **published** advanced options; the **internal/hidden** group reflects implementation details and has no stability contract. Classify options based on **the exact JDK's help/manual**, rather than guessing from prefixes.

### Official References

- Oracle JDK 21, *The javac Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — sections *Standard Options*, *Extra Options*, *Command-Line Argument Files*, and *Environment Variables*.
- OpenJDK `Option.java`: https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/classes/com/sun/tools/javac/main/Option.java — implementation code illustrating the `STANDARD`/`EXTENDED`/`HIDDEN` groups and the `-XD` entry point. The `master` branch may change over time; when researching, always cross-check code for the exact release.