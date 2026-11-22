# Avoiding Path and Sensitive Data Exposure via Diagnostics During Java Compilation

> **Context:** Java Advance – compilation → Safety and limits. This document is for builders of systems invoking `javac`, the Java Compiler API, annotation processors, or CI pipelines. The goal is retaining the diagnostic information **needed to fix errors** without inadvertently exposing machine paths, usernames, repository layout, source contents, customer details, tokens, and secrets in logs.

## 1. Problem: compilation errors are also a data-leakage channel

Diagnostics are information emitted by the compiler while reading, analyzing, and generating code. They typically include **severity**, **location**, **error code/message**, and **associated source**. That information helps developers, yet it can contain or allow readers to infer:

- Absolute paths: `/home/alice/projects/client-a/private/src/...`, `C:\Users\Alice\work\confidential\...`, CI temp directories, home directory names, and workspaces.
- Package, class, method, annotation, Java symbol names, or configuration values carrying sensitive customer/project names.
- Part of the **erroneous source line** printed by command-line `javac` or log-rendering tools; that line can contain string literals, internal endpoints, hardcoded dummy tokens, or test data.
- Information inside messages authored by **annotation processors**, compiler plugins, code generators, or custom file managers, which can write arbitrary strings.
- Stack traces and exception messages containing URIs, filesystem paths, compiler options, classpath/module path, or build-tool exceptions.
- CI metadata: branch names, artifact paths, runner names, and environment variables accidentally interpolated into commands, logs, and reports.

Example of a text-format error line (illustrative, **not a fixed standard output**):

```text
/home/alice/projects/client-a/private/src/demo/Bad.java:4:
error: incompatible types: java.lang.String cannot be converted to int
    int number = "TRAINING_SECRET_MARKER";
                 ^
```

Merely copying one diagnostic verbatim onto a web UI, Slack, issue tracker, or CI log can expose both **private paths** and **source line contents**. The string `TRAINING_SECRET_MARKER` here is an **entirely synthetic marker**, not a real credential. Never use real secrets to demonstrate or test redaction.

**Primary risk:** the diagnostic system runs with access to the source/build environment, yet its output may enter **less-trusted channels** (public logs, fork PRs, customer dashboards, support tickets, third-party telemetry). This data flow must be designed under the **least disclosure** principle.

## 2. Classifying data before deciding what to log

| Component | Diagnostic Value | Risk | Safe Display Strategy |
| --- | --- | --- | --- |
| `Diagnostic.Kind` | Distinguishes `ERROR`, `WARNING`, `NOTE` | Usually low | Allow enum values from a fixed set |
| `getLineNumber()`, `getColumnNumber()` | Pinpoints the error | Can reveal source layout in special contexts | Allow valid integers; use `?` if no position |
| `getSource().toUri()` | Identifies the file | Absolute path, username, tenant, workspace | **Map real URI → approved source ID** |
| `getCode()` | Compiler error category | Implementation-dependent; may hold unpredictable data in third-party tools | Allow codes from an allowlist only when truly needed |
| `getMessage(Locale)` | Fix hint | May include classes/variables/values/paths supplied by source or tools | Do not emit raw messages to public channels by default |
| `Diagnostic.toString()` | Quick diagnostic rendering | Uncontrolled formatting and contents | Do not use as a safe log record |
| Source line/caret/snippet | Clearly shows faulty expression | May contain source code, credentials, business logic | Display only in privileged private channels after checking and filtering |
| Exceptions/stack traces | Investigates compiler crashes | Paths, classpath, options, and plugin-written values | Safe generic message for viewers; raw evidence in protected channels |
| Build stdout/stderr | Investigates pipeline | May include raw compiler output, `-verbose`, shell commands | Capture/control before publishing or restrict access |

**Do not treat all logs alike.** An internal log with strong access control, retention, and access auditing can contain more diagnostic data than logs shown to source submitters. Even internal logs should avoid containing passwords/tokens/secrets whenever possible; read access to logs is often broader than read access to secrets/sources.

Recommended order: **minimize data at the source → build structured events from safe fields → filter/escape at the output layer → restrict readers and retention**. Regex string replacement after logs have already gone public is too late.

## 3. What does the Java Compiler API return?

Java 17 provides APIs in `javax.tools` (module `java.compiler`):

- `ToolProvider.getSystemJavaCompiler()` returns a compiler or `null` if the runtime lacks a system Java compiler.
- `JavaCompiler.getTask(...)` creates a compilation task; the `DiagnosticListener` parameter receives diagnostics in structured form.
- `DiagnosticCollector<JavaFileObject>` is a built-in listener; call `getDiagnostics()` after `task.call()`.
- `Diagnostic.getKind()` indicates severity; `getSource()` may return `null`; `getLineNumber()` and `getColumnNumber()` are **1-based** coordinates, or `Diagnostic.NOPOS` (value -1) when no position exists.
- `getPosition()/getStartPosition()/getEndPosition()` are character offsets, **not UTF-8 byte offsets**. If no position exists, they return `NOPOS`.
- `getCode()` may be `null` and is implementation-dependent; `getMessage(Locale)` is a localized message, also compiler-dependent.

Having a strongly typed API **does not mean every field is safe to emit**. Specifically:

```java
// DANGEROUS in public build logs: source/message may be sensitive.
System.out.println(diagnostic);
System.out.println(diagnostic.getMessage(Locale.ROOT));
System.out.println(diagnostic.getSource().toUri());
```

This **snippet illustrates behavior to avoid**, not a standalone program. `Locale.ROOT` can reduce language variance, yet **does not strip sensitive data** from messages. `toString()` has no security contract.

Safe data-flow diagram:

```text
Source/Compiler/Processor
         │
         ▼
DiagnosticCollector (raw, inside trusted boundary)
         │
         ▼
Policy + source URI allowlist + select safe fields
         │
         ▼
Structured event: kind / logicalSourceId / line / column / buildId
         │
         ├── Public CI / PR UI: restricted event
         │
         └── Protected debug: extra data if truly needed, access-controlled
```

**Important boundary:** calling `getMessage()` and then `replaceAll(...)` can miss secrets not matching the pattern, URL-encoded paths, Unicode strings, JSON escapes, or arbitrary strings emitted by processors. For public logs, use an **allowlist** of fields derived from structured data.

## 4. Java 17+ practice: emitting safe diagnostics

We intentionally create an invalid source, place it under a **URI simulating a private path**, containing a synthetic marker. The collector receives `ERROR`, yet the public record contains only:

- Error kind `ERROR`.
- An **approved logical filename**, independent of physical paths.
- Diagnostic line number.

The program self-asserts that the record does not contain the simulated sensitive path or synthetic marker. **No real secrets** are used.

### 4.1. Complete `SafeCompilerDiagnostics.java` file

```java
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class SafeCompilerDiagnostics {
    private static final String FAKE_MARKER = "TRAINING_SECRET_MARKER";
    private static final String PRIVATE_DIR = "/private-workspace/";
    private static final URI ORIGINAL_URI = URI.create(
            "string:///home/alice/private-workspace/demo/Broken.java");

    private static final class MemorySource extends SimpleJavaFileObject {
        private final String source;

        MemorySource(URI uri, String source) {
            super(uri, Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Requires a full JDK");
        }

        String sourceText = """
                package demo;
                class Broken {
                    void test() {
                        int number = "TRAINING_SECRET_MARKER";
                    }
                }
                """;
        JavaFileObject source = new MemorySource(ORIGINAL_URI, sourceText);
        Map<URI, String> aliases = Map.of(
                source.toUri(), "src/main/java/demo/Broken.java");
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();
        StringWriter internalOutput = new StringWriter();

        boolean succeeded;
        try (StandardJavaFileManager manager =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {
            succeeded = Boolean.TRUE.equals(compiler.getTask(
                    internalOutput,
                    manager,
                    collector,
                    List.of("--release", "17",
                            "-encoding", "UTF-8", "-proc:none"),
                    null,
                    List.of(source)).call());
        }

        Diagnostic<? extends JavaFileObject> expected =
                collector.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                        .filter(d -> d.getLineNumber() == 4)
                        .filter(d -> d.getSource() != null)
                        .findFirst()
                        .orElseThrow(() -> new AssertionError(
                                "Expected ERROR at line 4"));
        if (succeeded) {
            throw new AssertionError("Invalid source compiled");
        }

        String sourceId = aliases.getOrDefault(
                expected.getSource().toUri(), "<unknown-source>");
        long line = expected.getLineNumber();
        String safeRecord = expected.getKind() + " " + sourceId
                + ":" + (line == Diagnostic.NOPOS ? "?" : line);

        boolean leaked = safeRecord.contains(FAKE_MARKER)
                || safeRecord.contains(PRIVATE_DIR)
                || safeRecord.contains("home/alice");
        if (leaked) {
            throw new AssertionError("Private data entered public log");
        }
        System.out.println("Compilation successful: " + succeeded);
        System.out.println("Diagnostic: " + safeRecord);
        System.out.println("Private data leaked: " + leaked);
    }
}
```

### 4.2. Compiling and running

Save the file in UTF-8 encoding **without BOM**. In the directory containing the file, using JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -proc:none SafeCompilerDiagnostics.java
java SafeCompilerDiagnostics
```

**Stdout verified on OpenJDK 24.0.2 with `--release 17`:**

```text
Compilation successful: false
Diagnostic: ERROR src/main/java/demo/Broken.java:4
Private data leaked: false
```

Do not treat `Compilation successful: false` as a failure of the **test harness**: that is the **expected result** of the compilation task for an intentionally ill-typed source. The `SafeCompilerDiagnostics` program exits successfully if all assertions pass. If the source code is changed to valid code or the diagnostic is no longer on line 4, the program throws an error.

### 4.3. Important design points

1. `MemorySource` has URI `string:///home/alice/private-workspace/demo/Broken.java`, containing a **simulated** sensitive path. The purpose is proving that even though the diagnostic references that URI, **public logs do not need to record the raw URI**.
2. `aliases` maps from **URIs belonging to sources explicitly registered by the system** to the logical name `src/main/java/demo/Broken.java`. This name is controlled by the application; it is not taken carelessly from the original path.
3. `getOrDefault(..., "<unknown-source>")` guarantees that if the compiler reports a source **not in the map**, the log does not fall back to the raw path. This is a critical decision in systems with multiple sources/modules.
4. `Diagnostic.Kind.ERROR` and `getLineNumber()` are enum/numeric data; the program does not extract `getMessage()`, `toString()`, code snippets, or `getSource().getCharContent()` to send to public logs.
5. `StringWriter internalOutput` absorbs non-diagnostic information the compiler might write to `getTask(...)`'s `Writer`; the example **intentionally does not print this writer's contents**. In real systems, you must control all process, plugin, and build-tool stderr/stdout, not only JavaCompiler's writer.
6. `-proc:none` disables annotation processors for this simple fixture. This is **not** advice to disable processors in projects depending on Lombok/MapStruct or testing processors themselves.
7. `leaked` checks only three **known synthetic markers**. It is a regression check for the example; **it does not prove a general algorithm blocking every secret or path**. Testing real systems requires more cases and covering multiple log channels.
8. `getSystemJavaCompiler()` requires a JDK with a compiler; runtime images containing only a Java runtime can return `null`. Do not emit exception details into public logs if the exception contains sensitive values.

**Why use an in-memory source?** We can reproduce the error on the same JDK without creating source files under real sensitive paths. With physical files, `StandardJavaFileManager` creates `JavaFileObject` instances that may carry `file:///...`; in that case register safe mappings for each permitted URI instead of printing `getName()` or `toUri()` directly.

## 5. Safe path mapping when compiling real files

For build services accepting multiple Java files, a good practice is assigning a **logical ID** at the time compilation inputs are created, for example:

```text
file:///tmp/ci-worker-28/customer-private/repo/src/main/java/app/Order.java
  └── src/main/java/app/Order.java

file:///C:/Users/Example/Private-Workspace/src/main/java/app/Worker.java
  └── src/main/java/app/Worker.java

file:///untrusted/external/Different.java
  └── <unknown-source>
```

This is an **illustrative diagram**, not output from Java. Only the final logical name is allowed to reach public logs. Real paths on the left appear only inside the trusted boundary and simulated example documentation.

### 5.1. Do not rely solely on `Path.getFileName()`

If two different directories both contain `Config.java`, logging only `Config.java` can cause users to identify the wrong file. Conversely, calling `relativize` blindly on a path outside the repository can produce `../../secrets/...` and expose directory structure. Instead:

- Obtain the **trusted repository/working directory root** from system configuration, not arbitrary input.
- Normalize paths and verify sources reside within the approved root; on filesystems with symlinks, consider `toRealPath()` when accessible and require symlinks not to escape the root.
- Convert to forward slashes and validate logical names; **if invalid or outside the root, return an anonymous ID**.
- Handle case-insensitive/case-sensitive behavior, drive letters/UNC, URI percent encoding, Unicode, and identically named files across modules.
- Enforce source ID access control by tenant/project; one tenant must not read another tenant's aliases.
- Never put root paths, sensitive segments, query strings, or host credentials into URLs/logical names.

Note that `Path.normalize()` removes `.`/`..` syntactically, yet **does not prove** a path lies beneath the real root after traversing symbolic links. For services handling user files, filesystem boundary checks must be performed before granting permission to read sources.

### 5.2. Pattern for handling multiple sources

Instead of guessing aliases from `getSource()` when receiving diagnostics, build the mapping table **when constructing compilation inputs**. Example snippet (inside a method that already has a file manager, not a standalone program):

```java
Map<URI, String> sourceAliases = new java.util.HashMap<>();
for (Path file : approvedFiles) {
    JavaFileObject source = fileManager
            .getJavaFileObjectsFromPaths(List.of(file))
            .iterator().next();
    String alias = approvedLogicalIds.get(file);
    if (alias == null) {
        throw new IllegalArgumentException("Unregistered input");
    }
    sourceAliases.put(source.toUri(), alias);
    // Also add source to the JavaFileObject list for compilation.
}
```

The snippet assumes `approvedFiles` and `approvedLogicalIds` were **constructed with permission checks** beforehand. It only illustrates how to maintain the mapping, and does not mean mapping alone protects input paths or makes `fileManager` sufficient for security. Aliases must be validated to prevent newlines, control characters, or characters that break log structure.

## 6. Should `getMessage(Locale.ROOT)` be displayed?

It depends on sharing scope. In a web system that “compiles user-uploaded code”, users may need to read `javac` messages to fix errors. **Context** must still be controlled:

- **Only authors/teams authorized for the source** may view fuller messages; do not broadcast raw diagnostics onto public CI/PR logs.
- When messages must be displayed, use filtered data, truncate length, and **escape properly for HTML/JSON/terminal**, with per-request/user limits. Escaping to prevent XSS/log injection is **not equivalent** to secret redaction.
- Avoid emitting messages referencing another tenant's sources, paths inside compiler options, or system errors; also guard errors when file managers/processors throw exceptions.
- Enforce diagnostic viewing authorization per project/tenant matching the associated source. A single message can mention filenames, symbols, or snippets from multiple files.
- In production/public mode, emit only **allowlisted error codes, severity, logical source ID, line/column**, and generic messages. Technical details can appear in authenticated debug views with access control and clear retention.

**No regex redaction is perfect.** For example, “replace `/home/.*?`” misses Windows paths, UNC paths, escaped characters, URL-encoded paths, and cannot distinguish ordinary URLs from secrets; overly broad regexes obscure valid content. Pattern redaction is only a **secondary defense**, not a replacement for allowlist-based data design.

When helpful UI messages are needed in a private interface, one design pattern stores a **semantic error category** mapped from a pinned compiler's `getCode()`, then renders “Type mismatch at line 4” via an application-controlled template. `getCode()` is not standardized across compilers by Java SE; if a code is unrecognized, fall back to “Compilation failed at source location” instead of passing the raw message through.

## 7. Leakage channels other than `DiagnosticCollector`

### 7.1. Command-line `javac` and shell

A build script like:

```bash
javac -encoding UTF-8 --release 17 -d build/classes src/main/java/demo/App.java
```

has no separate collector; the compiler can print file paths, error lines, source snippets, carets, and messages to stderr. If CI exposes **all stdout/stderr** publicly, you have leaked raw diagnostics even without ever calling the Java Compiler API.

Solutions depending on the system:

1. If building a compilation service yourself, consider calling the **Compiler API** to receive structured `Diagnostic` objects and emit only approved fields.
2. If you must run `javac` in a subprocess, capture stdout/stderr into a separate rate-limited channel and classify afterward; avoid automatically streaming raw output to public pipelines. Keep accurate exit codes; do not ignore build errors.
3. Do not enable excessive verbosity flags in public CI (`-verbose`, detailed debug/trace), especially flags printing classpaths, dependency paths, or compiler internals.
4. Review shell tracing `set -x`, commands auto-printed by CI, and passing `-J-D...`, `-A...`, or secrets via arguments/env. **Never put secrets in compiler options** just for “convenient configuration”; shells/process lists/build logs can expose them.
5. With Gradle/Maven, compiler plugins and build-tool logging levels may keep printing raw diagnostics. Verify actual logs using fixtures with synthetic markers instead of assuming a compiler listener suppresses all output.

### 7.2. Annotation processors and compiler plugins

An annotation processor can call `Messager.printMessage(...)` and emit diagnostics with **arbitrary** contents, including annotation values, class names, file paths, or internal sources. A malicious processor can also write directly to stdout, open network connections, read environment variables, or write files; sanitizing `DiagnosticCollector` **does not isolate** those side effects.

- Declare processors **explicitly**, pinning versions and dependency graphs; avoid unexpected processors from the classpath.
- Run compilers/processors inside suitable isolation: restricted service accounts, filesystem sandboxes, and network restrictions when needed.
- Never place deployment/production credentials in the environment of untrusted compilation processes.
- Inspect `-A...` options; annotation processors can echo option values back into diagnostics.
- Log plugin failures per data policy, rather than defaulting to `logger.error("...", throwable)` with full stack traces exposed publicly.

**Key takeaway:** log masking reduces impact, yet third-party code running inside the compiler can access the underlying secret data itself; remove privileges/secrets from the environment before running untrusted tools.

### 7.3. IDEs, test reports, build caches, and artifacts

Diagnostics can appear in XML/HTML test reports, IDE problem panels, SARIF, static analysis reports, build scans, telemetry, build-cache metadata, artifact manifests, or PR comment bots. Therefore filtering only console output **is not enough**. Inventory every destination storing or forwarding compile results:

```text
javac / plugin
  ├── terminal stdout/stderr
  ├── CI job logs
  ├── test reports / JUnit XML
  ├── static-analysis reports / SARIF
  ├── artifacts / build scans
  ├── chat / issue / pull request bot
  └── observability collector / retention storage
```

The same data classification policy must apply at those output destinations; platforms have built-in secret-masking mechanisms, yet **you cannot rely on them to prevent leaking source code or paths**.

## 8. Structured event example for public logs

An example event permitted for output:

```json
{
  "event": "java_compilation_diagnostic",
  "severity": "ERROR",
  "sourceId": "src/main/java/demo/Broken.java",
  "line": 4,
  "column": null,
  "codeCategory": "TYPE_ERROR",
  "buildId": "build-42"
}
```

This is an **illustrative schema**, not JSON generated by `SafeCompilerDiagnostics.java`. In the lab, `getColumnNumber()` was available, yet we intentionally published only the line; the sample event sets `column: null` to illustrate a policy not disclosing column granularity. `TYPE_ERROR` is an **application-chosen label**, not a standard code from `javac`.

Requirements for the serializer:

- Forbid adding fields like `rawMessage`, `absolutePath`, `sourceText`, `stackTrace` to public events.
- `severity` comes from a controlled enum, never accepting arbitrary strings from processors.
- `sourceId` comes from the approved map with character/length validation; `buildId` is a harmless public identifier, **never a session token**.
- Line/column are numbers or null when `NOPOS`, validated within reasonable bounds before serialization.
- JSON encoders must escape `\n`, `\r`, quotes, and special characters. For text logs, use a reliable encoder instead of free-form string concatenation from inputs.
- Logs may be access-controlled per tenant/source permission; **syntactically valid JSON does not equal information security**.

Distinguish **event severity** and **classification**: an `ERROR` can be a type mismatch, while a `WARNING` can come from a deprecated method; both can still carry sensitive data in raw messages.

## 9. Preventing log injection when diagnostics contain untrusted input

Beyond leaking secrets, user-controlled data can contain newlines, tabs, ANSI escape sequences, or forged delimiters, making logs look like different events.

Illustrative simulated payload:

```text
Broken.java
[INFO] BUILD SUCCESS
```

If a path/filename contains a newline character and the system concatenates it directly into a log string, one diagnostic turns into **two lines**, skewing dashboards or misleading incident responders.

Countermeasures:

- Output only controlled aliases, restricting allowed characters—e.g. letters, digits, `/`, `.`, `_`, and `-`, with no newlines/control characters.
- Encode data strictly according to the log format; ideally use a logging framework with a structured JSON encoder.
- Enforce field length limits before storage; apply total event caps and rate limits to prevent log flooding.
- Never let content from compilation tasks act as event names, severities, or correlation IDs.
- Do not assume parameterized logging automatically stops CR/LF injection: an encoder or data validation is still required.

## 10. Designing two diagnostic visibility tiers

Public visibility and private debug visibility have different requirements.

| Policy | Public/PR/tenant lacking source permission | Authenticated debug, minimum necessary |
| --- | --- | --- |
| Build status | Yes | Yes |
| Diagnostic kind | Yes | Yes |
| Logical file alias | Yes when authorized | Yes within permitted project scope |
| Line/column | Depends on sensitivity | Yes when needed |
| Raw compiler message | **No** | Only after review/limits and content checks |
| Source line/code snippet | **No** | Only for users authorized to read source |
| Absolute path/username | **No** | Usually still unnecessary; replace with source mapping |
| Stack trace, classpath | **No** | Separate protected channel, short retention |
| Raw stdout/stderr | **No** | Only when necessary, with access control |
| Secret/token | **No** | **No**, even in debug |

Some teams operate tooling that stores raw compiler diagnostics for severe incident investigation. In that case, separate controls must apply: encryption at rest/in transit, least-privilege read access, access auditing, retention limits, scrubbing on export, deletion mechanisms, and exposure incident reporting. Do not leave raw logs indefinitely in CI artifacts.

### 10.1. Crucial reality: diagnostics are not a security boundary

A system processing **untrusted** sources cannot protect secrets solely by omitting `getMessage()`. Processors/compilers can execute code or access the filesystem depending on context. Establish the security boundary **before the compiler**:

- Container/VM with only required sources and dependencies, without mounting `~/.ssh`, credentials, home directories, or runner tokens.
- Grant only necessary read/write permissions; restrict network egress unless required.
- Isolate permissions across tenants; do not share readable working directories.
- Enforce resource limits on compilation processes (CPU/memory/time/disk); prevent log flooding.
- Keep log collectors outside the compile process or inside a trusted boundary, never forwarding raw outputs to public channels.

## 11. Anti-leakage test suite using synthetic data

The program in section 4 checks static markers. To elevate the demo into regression testing for a real pipeline, build a **simulated fixture suite** containing the following input types, never using real data:

| Fixture | Simulated String | Expectation |
| --- | --- | --- |
| Linux absolute path | `/home/tester/private-project/src/Bad.java` | Does not emit real path |
| Windows absolute path | `C:\Users\Tester\SecretRepo\Bad.java` | Does not emit home/drive/workspace |
| UNC path | `\\fileserver\private-share\Bad.java` | Does not expose internal share/server |
| URL encoded path | `file:///home/tester/private%20project/Bad.java` | Does not expose encoded path |
| Source literal | `"TRAINING_SECRET_MARKER"` | Marker does not appear in public diagnostics |
| Sensitive source variable name | `clientInternalIdentifier` | Does not emit raw code/message |
| Newline injection | `Bad.java\n[INFO] BUILD SUCCESS` | Does not forge a fake log line |
| ANSI control sequences | `\u001b[31m` (simulated escape string) | Does not manipulate terminal logs |
| Unknown source | Diagnostic absent from allowlist | `<unknown-source>` or neutral ID |
| Global diagnostic | `getSource() == null`, `NOPOS` | Does not crash, uses unknown location |
| Annotation processor | Processor emits message containing synthetic marker | Public log drops raw message |
| Throwing compiler/file manager | Exception has path in `getMessage()` | Exception details kept in protected channel |

A test suite should **capture the entire final output** at the exact places users see: CI job text, HTML/XML/JSON reports, PR comments, and downloaded artifacts. Assert the absence of synthetic markers, paths, or sensitive strings from the fixtures. Checking `safeRecord` in Java is necessary yet **insufficient** if the build shell still prints source paths or exception messages.

### 11.1. Positive and negative assertions

Negative tests ensure outputs **exclude** markers/paths; positive tests ensure useful information remains:

```text
PASS: public event has severity=ERROR
PASS: public event has approved sourceId
PASS: public event has line=4
PASS: public event excludes private path
PASS: public event excludes training marker
PASS: stdout/stderr/report exports obey same policy
```

This is an **expectation checklist**, not exact stdout from section 4's example. This prevents building a “safe” sanitizer by wiping out every diagnostic, leaving developers unable to locate errors. Disallowed fields must be stripped; allowed fields must remain accurate.

### 11.2. Mutation tests for the protection mechanism itself

Create a code variant that intentionally **calls `System.out.println(d.getMessage(Locale.ROOT))`** in the public channel and ensure the anti-leakage test detects the synthetic marker (may require a compiler/processor fixture emitting a message containing the marker). Create another variant that **falls back to `d.getSource().toUri()`** when an alias does not exist; ensure the test detects the path. If tests stay green on both dangerous variants, the tests are not observing the right leakage channel.

Do not rely on exact message strings as a portable assumption. Compilers and JDKs can change messages; proactively build fixtures with a processor or stub `Diagnostic` containing markers to test the formatter unit in isolation, then run integration tests with the real compiler.

## 12. Common implementation mistakes

### 12.1. Replacing only `/home/user` with `***`

Replacing a familiar prefix misses Windows/UNC paths, symlink-resolved paths, URI-encoded paths, Docker roots, artifact metadata, and identifiers in source code. Solution: **never emit raw paths**; replace them with valid aliases from a registry.

### 12.2. Assuming `Locale.ROOT` makes messages safe

`getMessage(Locale.ROOT)` only selects the locale used for message phrasing. It can still contain data from symbols, sources, options, or processors. Solution: separate application-controlled localizable UI messages from raw compiler messages.

### 12.3. Passing raw exceptions to loggers

Example **to avoid in public channels**:

```java
// Do not use when throwable may contain paths/sources/secrets.
logger.error("Compilation failed", exception);
```

This illustrative snippet uses a hypothetical project logger, not a standalone Java class. Frameworks may print stack traces and `exception.getMessage()` containing paths. Use public error IDs/categories, store incident details in a suitably restricted system, and avoid storing unnecessary secrets.

### 12.4. Assuming every diagnostic comes from the standard compiler

The JDK compiler follows certain contracts, yet processors/plugins can emit arbitrary warning/error messages. Enabling `-proc:full` or configuring processors also means **running third-party code**. Evaluate dependency supply chains, sandboxing, and permissions before processing outputs.

### 12.5. Masking only in the UI while leaving raw data in artifacts

A dashboard displaying `<redacted>` may still upload raw log files to broadly readable storage. Verify **the actual persisted/uploaded/shared output**, not just the rendering component.

### 12.6. Ignoring diagnostics lacking source/line

A command-option error or internal compiler error may have no attached `JavaFileObject`. Do not force `getSource().toUri()` when `getSource() == null`, and do not treat `NOPOS=-1` as a real line number. Use `<unknown-source>`, without printing full exceptions to “compensate” for missing locations.

### 12.7. Sharing the full command line for debugging

The executed command may contain `-classpath` pointing to private repositories, `-Apassword=...`, or directory/tenant names. Instead of logging the entire command, log **approved flags** (e.g. `--release=17`) and toolchain IDs; never dump all environment variables.

## 13. Checklist for Java build pipelines

- [ ] Enumerate all diagnostic output paths: API listeners, writers, stdout/stderr, build plugins, reports, CI, PR bots, telemetry.
- [ ] Public logs contain only events/schemas with allowlisted fields; never use `Diagnostic.toString()` or raw `getMessage()`.
- [ ] Source URIs are mapped to logical IDs with permission and character validation; unknown sources always fall back neutrally.
- [ ] Line/column handling accounts for `NOPOS`; emit positions only in accordance with viewing permissions.
- [ ] Never log raw source snippets, secrets, environments, classpaths, absolute paths, and exception stack traces to broadly accessible places.
- [ ] Compilers/processors receive least privilege, with no production credentials or private home directories in the sandbox.
- [ ] Emitted fields are properly encoded for JSON/text and bounded in size to prevent CR/LF injection/log flooding.
- [ ] Test with synthetic markers/paths across Linux, Windows, UNC, URI-encoded, and Unicode; audit build artifacts and reporting endpoints as well.
- [ ] CI jobs fail when policies are violated; include mutation tests proving the test suite detects leaks.
- [ ] Systems retaining raw diagnostics for debugging, if any, enforce restricted access, audit logs, encryption/retention, and deletion mechanisms.
- [ ] Data-exposure incidents are handled via security procedures; never paste raw diagnostics into public tickets/chats.

## 14. Real-world scenario: multi-user code-testing platform

Suppose a platform lets learners upload Java sources and returns compile results. Sources carry usernames or exercise content; runners have directories like `/runner/work/tenant-123/...`. When compilation fails:

1. **Input gateway** authenticates the user and submission permissions, assigning an internal `submissionId` and logical paths (e.g. `Submission.java`). Never embed usernames or private tenant IDs into public source aliases.
2. **Compiler worker** processes the source inside a secret-free sandbox; processors are disabled if exercises do not need them. The Compiler API sends structured diagnostic events to a trusted service.
3. **Formatter** selects only `kind`, logical source ID, line/column, and approved categories. Unknown sources yield generic results; never auto-fill paths.
4. **API response** returns only events belonging to the submission the user is authorized to view; if snippets uploaded by the user themselves are needed, the API checks source ownership and bounds data before sending.
5. **Public CI/monitoring** stores only error/warning counts, build status, execution duration, and harmless event IDs; never automatically retains raw messages.
6. **Incident debugging** upon compiler crashes surfaces only an incident ID on the UI; investigation data resides in an access-restricted system with retention limits and scrubbing before export.

This structure still tells the learner “ERROR at `Submission.java:4`” to fix their mistake, while nobody else sees runner paths or source snippets.

## 15. Self-assessment questions

1. Why is `Diagnostic.Kind.ERROR` generally safer than `Diagnostic.getMessage(Locale.ROOT)`? Are there cases where kind/line must also be restricted?
2. Why can `getSource().toUri().getPath()` not be logged directly merely by stripping a `/tmp/` prefix?
3. In the Java example, why is `aliases.getOrDefault(..., "<unknown-source>")` an important choice when the compiler returns an unregistered source?
4. If an annotation processor directly calls `System.err.println("...")`, can `DiagnosticCollector` stop that log? Where must the security boundary be changed?
5. Why does the unit test `safeRecord.contains(FAKE_MARKER) == false` not prove the entire CI log is safe? Which other output points must be tested?
6. If raw messages must be displayed to the source author, how would you enforce per-source/tenant authorization, escape output, and manage retention?
7. How can you retain severity/location useful enough for developers while preventing leakage of source text, absolute paths, and log injection?

**Learning outcome:** ability to identify sensitive data in compiler diagnostics, design an allowlist-based formatter, self-test with synthetic markers covering relevant logging/CI endpoints, and distinguish **filtering emitted information** from **isolating code-executing compilers/processors**.

## References

- Oracle Java SE 17 – `javax.tools.Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Oracle Java SE 17 – `JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Oracle Java SE 17 – `DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Oracle Java SE 17 – `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Oracle Java SE 17 – `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- MITRE CWE-532 – Insertion of Sensitive Information into Log File: https://cwe.mitre.org/data/definitions/532.html
- OWASP – Implement Security Logging and Monitoring: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/