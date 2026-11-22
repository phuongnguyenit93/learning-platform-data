# Adjusting javac diagnostic verbosity without depending on fixed message formats

When Java fails to compile, `javac` emits **diagnostics**: information about errors, warnings, or notes during program analysis and compilation. Learners often look only at the `error:` or `warning:` lines in the terminal, but for build systems, IDEs, or CI, it is necessary to distinguish **content meant for human reading** from **signals that can be processed reliably by programs**.

`javac` lets you vary the verbosity level of messages using several options: `-Xdiags:compact`, `-Xdiags:verbose`, `-Xlint`, `-Xmaxerrs`, `-Xmaxwarns`, `-verbose`, and `-Werror`. They serve different purposes; some affect the volume of generated warnings, the number of displayed messages, or build-failure policies. None of these options turns the entire diagnostic text into a machine-readable format that is stable across all JDKs, locales, and compiler implementations.

This lesson explains how to use the options for debugging and how to build tooling **without checking errors via regex on stderr**. Examples use Java 17+ and apply directly to JDK 21. When integrating the compiler programmatically, we leverage `javax.tools.JavaCompiler` and `DiagnosticCollector` instead of trying to guess the structure of each line of text.

## 1. What is a diagnostic?

A diagnostic can describe:

- **Compilation error** (*error*): the program does not satisfy Java rules, such as a nonexistent variable, wrong type, or syntax error.
- **Warning** (*warning*): the compiler may still emit class files, yet detects a notable issue such as raw types, unchecked conversions, or using a deprecated API.
- **Note** (*note*): additional information from the compiler or an annotation processor.
- **Related location**: source name, line, column, or offset, if the diagnostic has an identifiable location.
- **Explanatory content**: human-readable explanation that may vary by locale, verbose/compact setting, JDK version, and compiler type.

For example, the following Java code has an intentional type error:

```java
class BadAssignment {
    int count = "ten";
}
```

`javac` typically reports an error that `String` cannot be converted to `int`. The message may include the file path, line number, caret position, `incompatible types` explanation, and error count. These elements **should not be treated as a stable protocol** for automated applications.

A tool may need to know "whether compilation succeeded", "how many ERROR diagnostics exist", "which source a diagnostic belongs to", and "what the line/column is". There are proper APIs to retrieve that information without slicing stderr strings based on a fixed pattern.

## 2. Distinguishing verbosity changes from policy changes

`javac` options serve different purposes:

| Option | Main effect | What not to infer |
| --- | --- | --- |
| `-Xdiags:compact` | Selects the concise diagnostic presentation mode | Does not make the program more valid or guarantee a fixed output format |
| `-Xdiags:verbose` | Selects a more detailed diagnostic mode | Does not turn message text into a schema/API |
| `-Xlint`, `-Xlint:<keys>` | Enables lint warning categories | Does not mean printing more details for an already existing error |
| `-Xmaxerrs N` | Limits the number of **printed errors** | Does not give the total error count in source by counting printed lines |
| `-Xmaxwarns N` | Limits the number of **printed warnings** | Does not guarantee no other warnings remain |
| `-verbose` | Prints compiler activity, such as loaded classes and compiled sources | Not a verbose mode specifically for diagnostics |
| `-Werror` | When warnings exist, compilation fails under this policy | Does not automatically turn a warning into a specific source error |
| `-nowarn` / `-Xlint:none` | Suppresses corresponding warning messages | Does not fix unsafe code and does not silence real errors |
| `-deprecation` | Requests more detailed diagnostics on deprecated API usages per javac's mechanism | Does not replace `-Xlint` for other warning categories |

Flags beginning with `-X` are **extended `javac` options**. Check the compiler version with `javac -version` and the flag list with `javac -X` or the corresponding JDK documentation. Options, lint key lists, and presentation levels can vary across versions.

**Distinguish build outcome from diagnostic text:** a type-valid compilation can fail when using `-Werror` if warnings exist; conversely, reducing displayed warnings does not make a type error disappear. For reliable CI, rely on **success/failure status**, a clear warning policy, and structured diagnostic data.

## 3. Adjusting display detail with -Xdiags

Two supported values in the JDK 21 `javac` documentation are:

```bash
javac -Xdiags:compact BadAssignment.java
javac -Xdiags:verbose BadAssignment.java
```

Both invocations intentionally fail because `BadAssignment.java` assigns `String` to `int`. They differ in **the level of error detail** presented; they do not change Java rules, source input, or the compiled class name.

When investigating errors:

1. Start with the normal/compact presentation for readability.
2. If the compiler reports hard-to-read inference, overload, conversion, or generic bounds errors, try `-Xdiags:verbose` for additional context.
3. Read the full error reason and source location instead of copying only the first output line.
4. Record the actual JDK/toolchain because diagnostics change when the compiler changes.

Do not write code like:

```text
if (stderr.includes("incompatible types: String cannot be converted to int")) {
    // Label error of type X...
}
```

This is **pseudocode illustrating a fragile approach**, not runnable Java. Message wording can vary due to verbose/compact mode, locale, JDK version, expression types, inference constraints, or error location.

If a tool needs to classify error sources under its own taxonomy, it must use a structured diagnostic API and map well-defined kinds/properties, along with handling for unmapped cases.

## 4. Enabling useful warnings with -Xlint

`-Xlint` enables compiler-recommended warnings. When focusing on specific categories, use a list of lint keys:

```bash
javac -Xlint:rawtypes,unchecked RawTypeWarning.java
```

Complete `RawTypeWarning.java` file example:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeWarning {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("Java");
        System.out.println(raw.size());
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked RawTypeWarning.java
java RawTypeWarning
```

Program runtime stdout:

```text
1
```

Compiler warnings appear separately when running `javac`, normally on stderr; **exact warning text, underlined line count, or diagnostic ordering are not fixed**. `rawtypes` relates to using `List` and `ArrayList` missing type arguments; `unchecked` can report the `add` operation through a raw reference. The code can compile and run, yet the compiler does not guarantee element types as when using `List<String>`.

Fix the design with generics:

```java
List<String> words = new ArrayList<>();
words.add("Java");
System.out.println(words.size());
```

This snippet is **inside a method with `java.util.List` and `java.util.ArrayList` imported**, not a standalone file. If you replace `main`'s logic in `RawTypeWarning.java` with this snippet, stdout remains `1` and the rawtypes/unchecked warnings in the example disappear.

You can use:

```bash
javac -Xlint:all RawTypeWarning.java
javac -Xlint:all,-rawtypes RawTypeWarning.java
javac -Xlint:none RawTypeWarning.java
```

The `all` mode enables the lint warning categories supported by the compiler; the `-rawtypes` notation after the comma **specifically excludes the rawtypes category from the all selection**. `none` disables lint categories. Which specific lint keys exist must be checked per JDK version; `-Xlint:all` does not promise to catch every business-logic bug.

You can ignore a specific warning at a defined location using `@SuppressWarnings` when there is technical justification and you know the exact lint key supported by the compiler. Do not apply `@SuppressWarnings("all")` across the whole system just to turn CI green.

## 5. -Werror: warnings become a condition that fails the build

In CI environments, sometimes a development team wants **no compiler warnings to be allowed**. Use:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked -Werror RawTypeWarning.java
```

With source code still using raw types as in section 4, the compiler emits warnings; `-Werror` fails the entire compilation. Diagnostic phrasing depends on the JDK, but build systems should rely on a **non-zero exit status** or `CompilationTask.call() == false` when using the API.

Fix code to eliminate warnings or deliberately adjust the lint policy; `-Werror` does not automatically turn raw calls into type-safe ones. Conversely, `-nowarn` is not a substitute for fixing code if a warning indicates a runtime risk.

A practical note: when upgrading the JDK, the set of supported warnings can change. If a project uses `-Werror`, verify both the toolchain and lint policy on CI. Record the compiler version and compiler arguments to trace changes in build success conditions.

## 6. -Xmaxerrs and -Xmaxwarns: limiting printed output volume

A source file with many errors can produce a large log. When you want a quick view, you can use:

```bash
javac -Xmaxerrs 3 BadAssignment.java
javac -Xmaxwarns 5 -Xlint:all RawTypeWarning.java
```

**Warning:** `-Xmaxerrs` and `-Xmaxwarns` limit the number of **printed** messages according to JDK documentation; they do not establish a canonical report that the program has exactly N errors/warnings. Once the limit is reached, other diagnostics may not be printed completely.

Therefore, do not use an algorithm that "counts lines containing `error:` in stderr" as the canonical error count of a repository. That counter can be affected by print limits, multi-line diagnostic contents, summaries, tools/plugins, and how the compiler formats output.

Operational tip: daily CI logs can use a moderate limit for readability; when investigating hard-to-reproduce errors, rerun once in a diagnostic environment with a larger limit. However, **build status** and automated test decisions must still rely on real signals, not printed line counts.

## 7. -verbose is compiler activity, not -Xdiags:verbose

The following two commands serve different purposes:

```bash
javac -verbose RawTypeWarning.java
javac -Xdiags:verbose RawTypeWarning.java
```

`-verbose` prints activity such as parsing files, loading classes, and compiling/writing output according to compiler behavior. It is useful when you need to understand **which sources or classes the compiler read** and helps diagnose differences in classpath/sourcepath.

`-Xdiags:verbose` requests more detail for **diagnostic explanations**; when there are no errors/warnings, the difference may be minimal or negligible.

Do not enable `-verbose` by default on large projects just to "log more errors", because the log volume is huge and usually does not answer questions about error kinds. When tracking down a missing dependency, `-verbose` can help; when dealing with generic inference, `-Xdiags:verbose` is usually the more appropriate direction.

## 8. Why you must not depend on a fixed diagnostic format

There are at least six reasons:

1. **JDK/toolchain:** a different `javac` version may improve messages, reorder reasons, or add hints.
2. **Locale:** the same error can be expressed in different localized messages depending on distribution and compiler configuration.
3. **Presentation mode:** compact/verbose and related options change how explanations are rendered.
4. **Locations and paths:** relative/absolute paths, file separators, tabs/newlines/Unicode in source change the displayed string.
5. **Multi-line diagnostics:** caret positions, source excerpts, generic error types, and summaries can span multiple lines.
6. **Implementation:** `javac`, ECJ, or another compiler does not always share the same format/phrasing.

Example of a fragile regex:

```text
^(.+\.java):(\d+): error: (.*)$
```

This regular expression illustrates an **unreliable parsing approach**, not the formal grammar of all Java diagnostics. With multi-line messages, filenames containing colons (Windows), different locales, or different diagnostic modes, it can lose information or misinterpret output.

When structured data is needed, use `javax.tools.Diagnostic`; if simply running `javac` from a shell, read the **exit code** for success/failure and save the full log for human inspection without tying business logic to specific wording.

## 9. Java Compiler API and DiagnosticCollector

The standard `java.compiler` module provides an API to invoke the compiler within a Java process:

- `javax.tools.ToolProvider.getSystemJavaCompiler()` retrieves the system compiler if the environment has a suitable JDK compiler.
- `JavaCompiler.getTask(...)` creates a compilation task with options, source files, and a diagnostic listener.
- `DiagnosticCollector<JavaFileObject>` collects `Diagnostic` instances to inspect as objects.
- `Diagnostic.Kind` is an enum including `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`.
- `Diagnostic.getSource()`, `getLineNumber()`, `getColumnNumber()`, and `getPosition()` provide location details when available.
- `Diagnostic.getMessage(Locale)` returns human-readable text; the text remains implementation-dependent.
- `Diagnostic.getCode()` returns a diagnostic code, which may be `null`; **this code is not guaranteed by the JDK to be stable across compilers/versions**.

This is the core difference between using a programmatic interface and parsing logs.

### Standalone Java 17+ example: collecting structured errors

Save the complete file `StructuredDiagnosticDemo.java`:

```java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class StructuredDiagnosticDemo {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        JavaFileObject source = new SimpleJavaFileObject(
                URI.create("string:///BadSource.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return "class BadSource { int count = \"ten\"; }\n";
            }
        };

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        JavaCompiler.CompilationTask task = compiler.getTask(
                null,
                null,
                collector,
                List.of("-proc:none", "-Xdiags:verbose"),
                null,
                List.of(source)
        );

        boolean success = Boolean.TRUE.equals(task.call());
        boolean hasError = collector.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

        System.out.println("success=" + success);
        System.out.println("hasError=" + hasError);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StructuredDiagnosticDemo.java
java StructuredDiagnosticDemo
```

Exact stdout on a Java-compliant compiler:

```text
success=false
hasError=true
```

The program creates an **in-memory** source file containing an assignment error from `String` to `int`. `JavaCompiler` detects the error, `task.call()` returns `false`, and `DiagnosticCollector` contains at least one diagnostic of kind `ERROR`. We only print **signals with stable semantics**; we do not compare exact error wording.

`-proc:none` is used to avoid accidental annotation processor execution in the demo; it does not change the cause of the type error. `-Xdiags:verbose` is passed as an option to show that choosing the presentation mode does not force the program to parse stderr. In a runtime-only environment without a compiler, `getSystemJavaCompiler()` may return `null`; run with an appropriate JDK.

Even though the source is held in memory, the compiler may produce output files if compilation succeeds and no file manager/destination is specified; in this demo the source has a type error so there is no class output for `BadSource`. When building real tools, use an explicitly configured file manager/output location.

## 10. Using Diagnostic without turning messages into business keys

In code processing `Diagnostic<? extends JavaFileObject> diagnostic`, you can access these fields:

```java
Diagnostic.Kind kind = diagnostic.getKind();
long line = diagnostic.getLineNumber();
long column = diagnostic.getColumnNumber();

if (line != Diagnostic.NOPOS && column != Diagnostic.NOPOS) {
    // Line/column position is present; can link to editor.
}

String displayMessage = diagnostic.getMessage(java.util.Locale.ROOT);
String compilerSpecificCode = diagnostic.getCode();
```

This is a **snippet inside a method receiving a `diagnostic` variable**, not a standalone runnable file.

Respect these API boundaries:

| Field | Can be used for | Note |
| --- | --- | --- |
| `getKind()` | Classifying error/warning/note | API enum; suitable for counting and filtering |
| `getSource()` | Associating diagnostic with a source file | May return `null` |
| `getLineNumber()`, `getColumnNumber()` | Displaying position in an editor | **1**-based numbering; may be `Diagnostic.NOPOS` |
| `getPosition()` | Character offset in source | **0**-based offset; may be `NOPOS` |
| `getStartPosition()`, `getEndPosition()` | Describing the relevant span | Position may be unknown; check `NOPOS` |
| `getCode()` | Displaying/logging compiler code | Implementation-dependent code; may be `null` |
| `getMessage(Locale)` | Displaying human-readable text | Implementation-dependent text; do not use as a protocol |

Even if the API returns a `compiler.err.*` code from `javac`, that code still belongs to the implementation; do not claim it as a stable standard Java SE error catalog. If a product wants a stable error taxonomy, define your own taxonomy, publish its support scope, and include a fallback branch for unmapped diagnostics.

For example, a machine-readable report may define **application-level** fields: `severity`, `sourceUri`, `line`, `column`, `messageForDisplay`, `compilerId`, `toolchainVersion`. Only `severity` and API-provided location serve as a general basis; `messageForDisplay` is a string for human readers, not a decision key.

## 11. Testing the compiler by behavior rather than stderr snapshots

A good compiler test should separate:

**Relatively durable valid signals:** whether code compiles or fails, whether errors exist, whether `WARNING`/`MANDATORY_WARNING` diagnostics exist, whether the compiler produces expected artifacts, and whether the example's API semantics are correct.

**Signals suitable as supplementary info:** source/line/column if the use case actually cares about location, compiler-specific diagnostic codes, and full explanatory messages.

**Signals brittle under exact assertion:** entire stderr output, whitespace counts, the word "error", single-line source excerpts, caret `^` counts, English phrasing, diagnostic ordering, full paths, note prefixes, or summary error counts.

For example, with `StructuredDiagnosticDemo`, tests should expect the two lines `success=false` and `hasError=true`. If the application later prints `getMessage(Locale.ENGLISH)`, do not lock that exact message as a mandatory snapshot across all JDKs.

In cases where a specific diagnostic must be verified on a specific compiler version (for example, a plugin supporting only JDK 21.0.x), a dedicated integration test can detect plugin regressions. In that case, **pin the toolchain and explicitly label it as an implementation-specific test**, without promoting the format as a general Java standard.

## 12. When using the CLI, read exit codes properly

In a shell, a successful `javac` run normally returns exit code `0`. When compilation errors occur or `-Werror` fails the build, the exit code is non-zero. Use process exit status instead of string matching:

```bash
javac -encoding UTF-8 -Xlint:rawtypes,unchecked -Werror RawTypeWarning.java
if [ $? -ne 0 ]; then
    echo "Compilation failed"
fi
```

The snippet above is for **Bash**. In other shells, syntax for reading exit codes differs; PowerShell uses `$LASTEXITCODE` for native processes. Note that in real Bash, `$?` must be read **immediately after the `javac` command** before another command overwrites the status.

With Gradle/Maven, rely on the task/build result (success/failure) provided by the tool; do not grep compiler logs to decide "green build" yourself. Plugins may aggregate/reformat diagnostics or run incremental compilation, making text parsing even less stable.

## 13. When to increase logs and when to reduce logs

| Goal | Recommended approach |
| --- | --- |
| Hard-to-understand generics/overload error | Try `-Xdiags:verbose` and minimize the example |
| Want to find which sources/classes the compiler read | Use `-verbose` for a specific diagnostic run |
| Want to detect code prone to runtime type errors | `-Xlint:unchecked,rawtypes`, then fix the code |
| Want to address deprecated APIs | `-Xlint:deprecation` or `-deprecation` |
| CI wants zero tolerance for warnings | Enable appropriate lint policy and `-Werror` |
| Terminal prints too many errors | `-Xmaxerrs` to limit printed output, but do not use line count as total errors |
| IDE wants to highlight source spans | `Diagnostic` with source/line/column/position via API |
| Reports for humans | Record contextual message, compiler version, options, file, and location |
| Automated reporting | Use application-defined kind/status/schema; message is explanatory only |

The right detail level depends on the consumer. Developers fixing bugs need **sufficiently deep reasons**; CI needs results that are **easy to classify and track**; dashboards need **structured data with clear stability guarantees**. No verbose mode can replace a clean data interface design.

## 14. Scenarios prone to misunderstanding

### One: "Adding -Xdiags:verbose introduces new errors"

Verbose mode can make a diagnostic expose constraints, candidate methods, and expected vs. actual types. That **does not necessarily** prove the compiler found new semantic errors. Compare status, locations, and the nature of the program; do not equate log line count with diagnostic count.

### Two: "-Xmaxerrs 1 means the source has only one error"

Incorrect. This is a limit on the number of errors **printed**. Fixing the first error may expose subsequent ones. Use it to manage log size, not for overall quality statistics.

### Three: "Zero warnings means the code is completely safe"

Incorrect. Disabling warnings or changing lint policy only affects visibility into certain compile-time issues. The compiler does not prove that all business logic, concurrency, null safety, or data validation is correct.

### Four: "Diagnostic code is a standard Java SE code"

`Diagnostic.getCode()` is defined by Java SE as an API method, but the code value is **implementation-dependent and may be null**. Do not write portable logic requiring a specific internal `javac` code.

### Five: "Line/column numbers exist for every diagnostic"

The API allows `NOPOS`, and `getSource()` can be `null`. For example, compiler configuration errors, option errors, or issues not tied to a specific source location may lack source coordinates. Tools should display "unknown" instead of fabricating line `0`.

### Six: "-verbose and -Xdiags:verbose are equivalent"

Incorrect: `-verbose` describes compiler activity; `-Xdiags:verbose` adjusts how the compiler explains diagnostics. They answer two different debugging questions.

### Seven: "A stderr regex working on JDK 17 will work on all versions"

Not guaranteed. Wording, language, paths, column numbers, multiline formatting, and compiler implementations can all change. Use the API if structured data is needed, or check exit status if only pass/fail is needed.

## 15. Guide to building diagnostic reports for a real project

A practical deployment workflow:

1. **Pin the toolchain**: specify JDK version/vendor, `--release`, classpath/module path, compiler flags, and relevant plugins/processors.
2. **Choose a lint policy**: determine which warning categories should be enabled locally/in CI and whether `-Werror` is used.
3. **Set a sensible print level**: compact normally; verbose when analyzing hard cases; `-Xmaxerrs`/`-Xmaxwarns` solely for log management.
4. **Capture an explicit outcome status**: process exit code or `CompilationTask.call()`.
5. **If integrating the compiler**, use `DiagnosticCollector`; store kind, source and coordinates when present, and message for human readers.
6. **Do not lock logic to internal messages/codes**: if deep classification is needed, publish compiler-specific adapters with fallbacks and test against the exact toolchain.
7. **Keep full logs when needed**: for debugging, without assuming they are portable structured data.
8. **Test against a known error case**: create source missing a symbol or having a type mismatch and check pass/fail and kind; do not assert every space of stderr.
9. **Keep annotation processing effects separate**: processors may emit additional warnings/notes; CI results and log ordering must account for configured processors.
10. **Review when upgrading JDK**: lint key names, diagnostic text, and warning behavior may change; update policy based on the actual JDK running.

If you want to build a clean UI for diagnostics, the **application** formatter should handle presentation based on parsed objects, such as "Error — BadSource.java — line 1", and print the message underneath. When changing the UI, core data can still retain meaningful fields without needing to edit regexes coupled to compiler output.

## 16. Practice exercises and answers

**Exercise 1.** Run `javac -Xdiags:compact BadAssignment.java` and `javac -Xdiags:verbose BadAssignment.java`. Is either valid? **No**; the String-to-int assignment error still exists. What changes is the level of presentation detail.

**Exercise 2.** With `RawTypeWarning.java`, enable `-Xlint:rawtypes,unchecked`. Can the code run? **Yes**, and the example prints `1`. The warnings indicate weakened generic type safety, even though this specific program throws no error at runtime.

**Exercise 3.** Add `-Werror` to a compilation command that has warnings. Should you guess whether a stderr line contains the word "error" to know it failed? **No**. Check the exit code or compilation task result.

**Exercise 4.** `-Xmaxerrs 2` makes the terminal print two errors. Can you conclude the whole program has only two errors? **No**. It limits the number of printed errors; the source may contain others.

**Exercise 5.** In `Diagnostic`, which way is more portable to tell whether a diagnostic is an error: `getKind() == ERROR` or `getMessage(Locale.US).contains("error")`? **`getKind()`**, because it is an API enum.

**Exercise 6.** A diagnostic is not tied to a file. How must `getSource()` and `getLineNumber()` be handled? **Allow null and `NOPOS`**, without faking a path or line number with a default string.

**Exercise 7.** Why shouldn't `getCode()` be used as a standard error catalog across JDK and ECJ? Because codes are implementation-dependent and may be null; only use per a custom contract if the compiler/toolchain is pinned and a fallback exists.

**Exercise 8.** When investigating which classes the compiler is loading, choose `-verbose` or `-Xdiags:verbose`? **`-verbose`** helps observe loading/compiling activity; `-Xdiags:verbose` shows more detailed diagnostic explanations.

## 17. Conclusion and official documentation

Diagnostic verbosity and data-interface stability are two separate problems. Use `-Xdiags:verbose` to read error reasons, `-Xlint` to select warnings, `-Xmaxerrs`/`-Xmaxwarns` to control log volume, `-verbose` to observe compiler activity, and `-Werror` to set policy. For automation, use **compilation outcome** and the **Diagnostic API** semantically, without relying on a specific formatted error string.

Documentation for verifying exact details by JDK:

- [JDK 21 javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — lists `-Xdiags`, `-Xlint`, `-Werror`, `-Xmaxerrs`, and `-Xmaxwarns`.
- [Java SE 21 Diagnostic API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html) — describes `Kind`, `NOPOS`, positions, codes, and implementation-dependent messages.
- [Java SE 21 DiagnosticCollector](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — collects diagnostics via a listener.
- [Java SE 21 JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html) — `CompilationTask` interface and programmatic compilation.