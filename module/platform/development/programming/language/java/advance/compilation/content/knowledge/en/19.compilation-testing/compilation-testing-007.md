# Testing Missing Dependencies, Type Conflicts, and Module Configurations in Java

## 1. Objectives and Scope

A small change in **classpath**, library version, or **Java Platform Module System (JPMS)** configuration can make the same Java source code compile successfully in one environment yet fail in another. Compilation testing for these cases must prove both directions: a **valid configuration must be accepted**, while an **intentionally invalid configuration must be rejected for the right reason**.

After this lesson, learners can:

- Distinguish compile-time missing dependencies from runtime class-loading errors.
- Design pairs of cases with/without required libraries on **--class-path**.
- Test type conflicts caused by two incompatible API versions and distinguish them from duplicate class names or ambiguous simple names.
- Design JPMS cases for **requires**, **exports**, **--module-path**, and **--module-source-path**.
- Write an automated runner invoking **javac**, reading exit codes and diagnostic messages, isolating each compile run, and verifying negative cases do not "false PASS".
- Identify limits of the tests: do not infer runtime errors, Gradle/Maven dependency resolution, or binary compatibility solely from one compilation result.

Throughout the lesson, **JDK 17 or newer** is used with the **--release 17** option. Compiling with a newer JDK still checks standard Java 17 syntax/APIs; paths and library JARs are created by the exercises themselves, without depending on external services.

## 2. Test Model: Change One Condition per Case

A reliable test must hold unrelated variables fixed and change only the condition being tested:

| Group | Case that must be accepted (positive) | Case that must be rejected (negative) | Expected cause |
| --- | --- | --- | --- |
| Missing dependency | API library is on classpath | Remove that JAR from classpath | Cannot resolve package/symbol |
| API signature conflict | Client compiles against API v1 returning String | Switch to API v2 returning int | Return type incompatible with client |
| Ambiguous type name | Explicitly specify java.util.Date | Import two packages containing Date and use unqualified Date | Type name is not uniquely resolved |
| JPMS requires | Application module declares requires library | Remove requires | Application module does not read module containing API |
| JPMS exports | Library module exports API package | Remove exports | Package exists yet is not exported to calling module |
| Module path | Module is supplied on a valid module path | Remove/change path containing module when compiling separately | Required module not found |

**A PASS result is not synonymous with "any error occurred".** For negative cases, observe **javac failing** and the error relating to the exact rule under test. If code is already broken beforehand due to filename, braces, encoding, another secondary dependency, or an invalid javac command, rejection does not prove the hypothesis being tested.

Each case should have metadata including **ID, source code, JDK/compiler options, classpath/module path, ACCEPT/REJECT expectation, expected cause, actual result, and diagnostics**. For multi-JDK tests, pin **--release** and record JDK vendor/version because some messages and diagnostic codes are implementation details of javac.

## 3. Classpath: Testing Present and Missing Dependencies

### 3.1. Three Minimal Java Sources

Create the structure:

~~~text
source/
  v1/com/example/api/VersionApi.java
  v2/com/example/api/VersionApi.java
  app/com/example/app/Client.java
~~~

**source/v1/com/example/api/VersionApi.java** (valid API for client):

~~~java
package com.example.api;

public final class VersionApi {
    private VersionApi() {}

    public static String version() {
        return "v1";
    }
}
~~~

**source/v2/com/example/api/VersionApi.java** (same API name yet signature changed):

~~~java
package com.example.api;

public final class VersionApi {
    private VersionApi() {}

    public static int version() {
        return 2;
    }
}
~~~

**source/app/com/example/app/Client.java** (kept unchanged across all compilation passes):

~~~java
package com.example.app;

import com.example.api.VersionApi;

public final class Client {
    public static String value() {
        return VersionApi.version();
    }
}
~~~

When using API v1, the return value is **String** and the client is valid. With API v2, **VersionApi.version()** returns **int**, so the expression cannot be assigned to **String**. When removing the JAR, package **com.example.api** does not appear on the dependency path, so the compiler cannot resolve the import.

### 3.2. Building Two Independent Libraries

In the terminal at the directory containing **source/**, create the output directories and run:

~~~bash
mkdir -p out/v1 out/v2 out/dep-ok out/no-dep out/type-conflict

javac --release 17 -encoding UTF-8 -d out/v1 source/v1/com/example/api/VersionApi.java
jar --create --file out/v1.jar -C out/v1 .

javac --release 17 -encoding UTF-8 -d out/v2 source/v2/com/example/api/VersionApi.java
jar --create --file out/v2.jar -C out/v2 .
~~~

The **mkdir -p** snippet is for Linux/macOS. In PowerShell, create the equivalent directories with the command:

~~~powershell
New-Item -ItemType Directory -Force -Path out/v1,out/v2,out/dep-ok,out/no-dep,out/type-conflict | Out-Null
~~~

The **javac** and **jar** commands are identical on both operating systems. With one JAR on the classpath, no path separator is needed; if later there are multiple entries, separate with **:** on Linux/macOS and **;** on Windows.

### 3.3. Three Test Cases Using the Same Client.java

**D01 — Correct library present: must compile**

~~~text
javac --release 17 -classpath out/v1.jar -d out/dep-ok source/app/com/example/app/Client.java
~~~

**D02 — Missing library: must be rejected**

~~~text
javac --release 17 -classpath out/no-dep -d out/no-dep source/app/com/example/app/Client.java
~~~

**D03 — Wrong API signature: must be rejected**

~~~text
javac --release 17 -classpath out/v2.jar -d out/type-conflict source/app/com/example/app/Client.java
~~~

| Case | Expected exit status | Common diagnostic group | Meaning |
| --- | --- | --- | --- |
| D01 | 0 | No ERROR | Library v1 satisfies the API used by client |
| D02 | Non-zero | Package does not exist / cannot find symbol | Missing API definition at compile time |
| D03 | Non-zero | Incompatible types: int cannot be converted to String | API present, yet signature incompatible |

**Note:** the error descriptions in the table are paraphrases of meaning, not mandatory verbatim strings across every JDK/locale. Check the exit code **immediately after each javac invocation**. In Bash/Zsh you can use **echo $?**; in PowerShell use **$LASTEXITCODE**. Compilation failure does not automatically mean test infrastructure is healthy: check both stderr/diagnostics and dependency generation status.

### 3.4. Why Is This a "Type Conflict", and Not Yet a Runtime Test?

Case D03 keeps the client unchanged and swaps only the API in the compilation environment. **javac** sees a method signature differing from the type required by the client and therefore rejects it. This is a form of directly reproducible *source incompatibility*.

If the client compiled against v1 and then runs against v2 without recompiling, a runtime linkage error such as **NoSuchMethodError** can appear. That is a different question: *binary compatibility/linkage*. You must not treat the fact that the client compiled successfully against v1 as proof it will run correctly against every replacement version.

Similarly, when **two JARs both contain a class with the same fully qualified name** on the classpath, **javac** does not necessarily report "duplicate class"; which class is found can depend on path ordering and input layout. Do not use a duplicate-FQCN case as default proof that the compiler always detects conflicts. Instead, pin ordering/classpath, check the actual API used, or design specific cases testing resolution.

## 4. Type Name Conflicts: Ambiguity Errors Differ from API Incompatibility Errors

Another type conflict occurs when multiple types share the same **simple name** within import scope. For example, both **java.util** and **java.sql** have **Date**.

**NameConflict.java — must be rejected:**

~~~java
import java.util.*;
import java.sql.*;

public class NameConflict {
    Date createdAt;
}
~~~

With two wildcard imports, the unqualified reference **Date** is ambiguous. Control **NameResolved.java — must compile:**

~~~java
public class NameResolved {
    java.util.Date createdAt;
}
~~~

The control explicitly specifies the full type name. Create separate output directories, then run:

~~~text
javac --release 17 -d out/name-conflict NameConflict.java
javac --release 17 -d out/name-resolved NameResolved.java
~~~

Before the two commands, create **out/name-conflict** and **out/name-resolved**. The first case is expected to fail with **reference to Date is ambiguous**; the second succeeds. If omitting imports makes Date not found, that is *missing symbol*, not *ambiguous type*; distinguish them by diagnostic cause.

## 5. JPMS: Distinguishing Finding Modules, Reading Modules, and Exporting Packages

Since Java 9, modules can define compilation boundaries via **module-info.java**. Four concepts must be separated:

1. **--module-path** indicates where javac searches for compiled modules or modular JARs. It does not replace the classpath of code on the unnamed module.
2. **--module-source-path** indicates a multi-named-module source structure so javac compiles modules from source.
3. **requires com.example.library;** declares that the current module reads the dependent module; merely having a module on the path is not enough for every named module to read it automatically.
4. **exports com.example.api;** permits other modules to access **public** types in the exported package. **requires** does not bypass the **exports** barrier. A **public class** in an unexported package still cannot be used directly from another module.

Do not equate **exports** with **opens**: **opens** is mainly for deep reflection at runtime and does not automatically grant ordinary compile-time Java API access. **exports ... to ...** can also restrict the list of accessible modules. Mechanisms like **--add-reads**, **--add-exports**, **--patch-module** are special options that can alter test behavior; do not enable them silently when trying to verify JPMS boundaries.

### 5.1. Standard Module Set: Must Compile Successfully

Create four files in the source tree below:

~~~text
modules/ok/
  com.example.library/
    module-info.java
    com/example/api/Util.java
  com.example.consumer/
    module-info.java
    com/example/app/Main.java
~~~

**modules/ok/com.example.library/module-info.java**:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

**modules/ok/com.example.library/com/example/api/Util.java**:

~~~java
package com.example.api;

public final class Util {
    private Util() {}

    public static int answer() {
        return 42;
    }
}
~~~

**modules/ok/com.example.consumer/module-info.java**:

~~~java
module com.example.consumer {
    requires com.example.library;
}
~~~

**modules/ok/com.example.consumer/com/example/app/Main.java**:

~~~java
package com.example.app;

import com.example.api.Util;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Util.answer());
    }
}
~~~

Create the output directory and compile both named modules from source:

~~~text
javac --release 17 --module-source-path modules/ok -d mods/ok -m com.example.library,com.example.consumer
~~~

Mandatory condition: **mods/ok** already exists before invoking the command. **--module-source-path modules/ok** works here because subdirectories are named after the modules. The compilation command must succeed, creating per-module output directories under **mods/ok**. Test run after compiling (optional, only for observation):

~~~text
java --module-path mods/ok -m com.example.consumer/com.example.app.Main
~~~

Stdout when running:

~~~text
42
~~~

The **42** output is a supplementary execution check; the main PASS criterion of the compilation test remains javac succeeding.

### 5.2. Case M02 — Removing requires: Must Be Rejected

Copy the entire four-file set **modules/ok/** to **modules/no-requires/**. Replace only the content of **modules/no-requires/com.example.consumer/module-info.java** with:

~~~java
module com.example.consumer {
}
~~~

Keep the library module, Util class, Main class, and compiler command unchanged (changing only source root and output root):

~~~text
javac --release 17 --module-source-path modules/no-requires -d mods/no-requires -m com.example.library,com.example.consumer
~~~

Create **mods/no-requires** first. Javac must reject it because module **com.example.consumer** does not read **com.example.library** even though the API package exists and is exported. Common diagnostics state the package is not visible because the consumer does not read that module. If also modifying Main source or dropping the library module at the same time, we no longer have an isolated negative case.

### 5.3. Case M03 — Removing exports: Must Be Rejected

Copy the standard set to **modules/no-exports/**. Keep **requires** in the consumer module, yet replace only **modules/no-exports/com.example.library/module-info.java** with:

~~~java
module com.example.library {
}
~~~

Keep class Util **public**. Run:

~~~text
javac --release 17 --module-source-path modules/no-exports -d mods/no-exports -m com.example.library,com.example.consumer
~~~

After creating **mods/no-exports**, javac must reject it: the consumer *does read the library module*, yet **com.example.api** is not exported. The error usually contains phrasing like "package ... is not visible" along with the reason that the package is not exported. This is a different cause from M02 even though the beginning of the message may look similar.

### 5.4. Missing Module Path Case When Compiling Separately

If the consumer module is compiled **in a separate pass** from the library module, javac needs to find the library module via **--module-path**. Control procedure:

1. Compile **com.example.library** first into a separate output directory.
2. Compile **com.example.consumer** with **--module-path** pointing to the directory containing the compiled library module: must succeed.
3. Change only **--module-path** to an empty directory, keeping consumer source and **requires** unchanged: must fail with a diagnostic meaning roughly "module not found: com.example.library".

Do not merge this case with M02: missing a module artifact on the path and missing **requires** are two different configuration errors. In Gradle/Maven, the module path is sometimes inferred automatically by the build tool; to verify **javac**'s JPMS rules, record the actual command/paths the compiler receives.

## 6. Automated Test Runner Calling javac Using Java 17+

After creating the fixture files and JARs in sections 3–5, a runner can be used so you do not have to read each command's exit code manually. The program below invokes the current JDK's own javac via **ProcessBuilder**, creates a separate temporary output directory for each case, and prints PASS results. Because it uses **ProcessBuilder(List<String>)**, it does not have to manually assemble shell command strings or worry about escaping spaces in paths.

Save as **CompileChecks.java** in the same top-level directory containing **source/**, **modules/**, and **out/**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CompileChecks {
    record Check(String name, boolean expectedSuccess, List<String> flags) {}

    static int invokeJavac(Path executable, Path workspace, List<String> flags)
            throws IOException, InterruptedException {
        List<String> command = new ArrayList<>();
        command.add(executable.toString());
        command.addAll(flags);

        Process process = new ProcessBuilder(command)
                .directory(workspace.toFile())
                .redirectErrorStream(true)
                .start();
        String log;
        try (var input = process.getInputStream()) {
            log = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            System.err.println("javac diagnostics (" + exitCode + "): " + log.strip());
        }
        return exitCode;
    }

    public static void main(String[] args) throws Exception {
        Path workspace = Path.of(".").toAbsolutePath().normalize();
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javac = Path.of(System.getProperty("java.home"), "bin",
                windows ? "javac.exe" : "javac");
        if (!Files.isRegularFile(javac)) {
            throw new IllegalStateException("Chạy bằng JDK có javac: " + javac);
        }

        Path root = Files.createTempDirectory("compilation-case-");
        List<Check> cases = List.of(
            new Check("dependency-present", true,
                List.of("--release", "17", "-cp", "out/v1.jar", "-d",
                    root.resolve("dep-ok").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("dependency-missing", false,
                List.of("--release", "17", "-cp", "out/no-dep", "-d",
                    root.resolve("dep-missing").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("api-signature-conflict", false,
                List.of("--release", "17", "-cp", "out/v2.jar", "-d",
                    root.resolve("api-conflict").toString(),
                    "source/app/com/example/app/Client.java")),
            new Check("modules-valid", true,
                List.of("--release", "17", "--module-source-path", "modules/ok",
                    "-d", root.resolve("module-ok").toString(),
                    "-m", "com.example.library,com.example.consumer")),
            new Check("modules-missing-requires", false,
                List.of("--release", "17", "--module-source-path",
                    "modules/no-requires", "-d",
                    root.resolve("module-no-requires").toString(),
                    "-m", "com.example.library,com.example.consumer")),
            new Check("modules-missing-exports", false,
                List.of("--release", "17", "--module-source-path",
                    "modules/no-exports", "-d",
                    root.resolve("module-no-exports").toString(),
                    "-m", "com.example.library,com.example.consumer"))
        );

        try {
            for (Check check : cases) {
                int index = check.flags().indexOf("-d");
                Files.createDirectories(Path.of(check.flags().get(index + 1)));
                int status = invokeJavac(javac, workspace, check.flags());
                if ((status == 0) != check.expectedSuccess()) {
                    throw new AssertionError(check.name() + " exited " + status);
                }
                System.out.println(check.name() + ": PASS");
            }
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Run:

~~~text
javac -encoding UTF-8 CompileChecks.java
java CompileChecks
~~~

Expected stdout (negative diagnostics are printed separately to stderr):

~~~text
dependency-present: PASS
dependency-missing: PASS
api-signature-conflict: PASS
modules-valid: PASS
modules-missing-requires: PASS
modules-missing-exports: PASS
~~~

This runner has been verified with **javac JDK 21**: **6/6 cases PASS**; additionally, the **NameConflict/NameResolved** pair in section 4 was verified independently. Note: the runner's source code executes on JDK 17+, yet the invoked compiler itself must support **--release 17**.

**Analyzing harness limitations:** comparing **(status == 0) != expectedSuccess** checks acceptance/rejection; it **does not itself prove the right diagnostic cause**. stderr is printed for learners to compare. In a stricter CI system, put expected causes into each case, capture diagnostics, and fail if causes do not match. Do not treat "javac failed to launch", timeouts, missing fixture files, permission errors, or invalid arguments as a valid REJECT case. You can build a harness using **javax.tools.JavaCompiler** with **DiagnosticCollector** to check **Diagnostic.Kind.ERROR**, **getCode()**, **getSource()**, **getLineNumber()**, and **getMessage(Locale)**; detailed messages/codes may differ across compiler versions/implementations.

## 7. Oracle Design and Avoiding False PASSes

An **oracle** is the criterion deciding PASS/FAIL. A good suite has multiple verification layers:

| Verification layer | Minimum condition | Purpose |
| --- | --- | --- |
| Setup | Fixture source/JAR/module files have right names and create successfully | Do not confuse data-preparation errors |
| Positive case | javac exits 0; target source was genuinely compiled | Confirm valid environment |
| Negative case | javac exits non-zero and has appropriate compilation diagnostics | Confirm constraint is enforced |
| Right cause | Missing package differs from wrong type; missing requires differs from missing exports | Avoid false negative passes |
| Isolation | Clean output, explicitly declared classpath/module path | Avoid stale classes or stray dependencies |
| Reverse check | Change a REJECT case to valid code or flip expectation, suite must fail | Verify effectiveness of the test harness |

For example, if case D02 is supposed to fail because **VersionApi** is not found, yet the client code has a brace typo, checking only **exit != 0** gives a false PASS. Fix the client to a valid version first and then test configurations one by one.

To evaluate diagnostics robustly:

- **Error kind:** source cases that must be rejected usually require **Diagnostic.Kind.ERROR** if using the JavaCompiler API.
- **Source and context:** inspect the error-causing file, violated relationship kind, and related module/package/symbol names when appropriate.
- **Message code:** **javac**-specific diagnostic codes can be useful in version-pinned test suites yet are not an immutable contract of the Java Language Specification.
- **Message string:** do not snapshot the entire stderr verbatim as the sole condition because locale, JDK, line/column, temporary paths, and diagnostic order can change.
- **Infrastructure errors:** classify separately when failing to spawn a JVM process, missing JDK, unsupported **--release** version, unbuilt JAR, unwritable directory, or abnormal process termination.

Return PASS for a negative case only after verifying **compilation actually ran** and the error originated from the controlled condition. Control pairs changing one parameter are usually the strongest evidence.

## 8. Classpath, Module Path, and Build Tools: Common Pitfalls

### 8.1. Mixing Up Classpath and Module Path

Classpath suits normal code on the **unnamed module**; named modules have their own package reading/exporting mechanism. **--class-path** and **--module-path** are not two equivalent spellings. Modular JARs, automatic modules, and regular JARs can be treated differently depending on which path they are placed on. When testing JPMS, document which path each library is placed on and what kind of module is being compiled.

### 8.2. Opening Packages for Reflection Yet Forgetting Exports

Adding **opens** so a reflection framework can access internals does not mean other clients can directly import types in that package. Compile-time API access tests need **exports**, and named consumers need **requires**. Do not use a program running successfully due to runtime options like **--add-opens** as proof that compilation satisfied proper module boundaries.

### 8.3. Confusing Compile-Time Missing Dependencies with Runtime Transitive Dependencies

Code can compile when public interfaces/classes are present yet fail at runtime because an implementation dependency or another dynamic link is missing. Conversely, if a needed class is absent from **javac**'s classpath, the error is compile-time. You must pinpoint the phase of the error: resolution in build tool, javac, module resolution, class loading, or method execution.

### 8.4. Stale Build Data and Unintended Dependencies

A pre-compiled class in **target/classes**, **build/classes**, an IDE directory, or a JAR automatically placed on the classpath can mask a missing dependency. Compile into clean output, specify **-cp/--class-path** and **--module-path** explicitly, and avoid relying on an IDE setup that "currently runs". With Gradle/Maven, inspect the actual compiler command and resolved dependency set, not just dependency names in the build file.

### 8.5. Annotation Processing and Generated Sources

If a processor generates required classes, a "missing class" test can pass/fail differently depending on processor path, **-proc** options, and generated sources. For tests of basic Java rules, disable processors when needing isolation; for processor tests, declare processor path and check generated outputs as a separate condition. Avoid accidentally feeding old generated sources into the compilation pass.

### 8.6. --release Configuration and Running JDK

**--release 17** specifies the standard Java 17 source/API level, without guaranteeing compatibility with every third-party library version. When errors stem from mismatched JAR versions, pin the actual artifact and record its SHA-256 or used version. Do not conclude "Java 17 does not support API" when the cause is a dependency missing from the classpath.

## 9. CI Integration and Expanding Practice Exercises

In real projects, intentionally broken fixtures can be stored under **src/test/resources/compile-fixtures/** (or an equivalent data tree) instead of placing them directly into the default Java source set. Tasks/harnesses will prepare libraries, compile each fixture, and collect results. Do not let intentionally broken Java files be compiled by Gradle/Maven alongside the test runner before tests have a chance to execute.

Suggested metadata for a case can be stored in YAML/JSON or test code structures:

~~~yaml
id: M03
title: Named module does not export API package
jdkRelease: 17
sourceRoot: modules/no-exports
expected: REJECT
expectedReason: com.example.api is not exported by com.example.library
compilerOptions:
  - --release
  - "17"
  - --module-source-path
  - modules/no-exports
~~~

Manifest only describes data; there must be an actual runner creating clean output, invoking the compiler, reading diagnostics, and matching causes. When updating JDK or libraries, rerun both control pairs before changing expectations.

**Practice Exercise A — missing module path:** split building the library and consumer in section 5 into two passes. Let the consumer read the library via the right **--module-path**, then intentionally swap it with an empty directory. Record the **module not found** diagnostic, distinguishing it from the case removing **requires**.

**Practice Exercise B — overload change:** create API v1 with method **parse(String)** and a consumer calling **parse("42")**. Create API v2 with only **parse(int)**, keeping the client unchanged. Test the ACCEPT/REJECT pair under the same classpath test D01–D03, then explain why the message differs from changing the return type.

**Practice Exercise C — testing the harness:** edit **VersionApi v2** so **version()** returns **String** like v1, and rebuild JAR v2. The "api-signature-conflict" case in the harness **must report FAIL** because the code is now valid. Restore API v2, flip the expectation of "modules-missing-exports" to ACCEPT; the harness must also report FAIL. That is proof the test suite genuinely detects rule changes.

Completion criteria:

1. There is at least one positive/negative pair for missing classpath dependencies, type conflicts, and JPMS.
2. Each pair changes only one relevant condition, keeping other files unchanged.
3. Every positive case is accepted by javac; every negative case is rejected for the expected reason.
4. Do not equate Javac errors, infrastructure errors, build tool errors, runtime errors, and JPMS errors with one another.
5. The test suite uses clean output, declares JDK/release/paths, records diagnostics for debugging, and fails when intentionally breaking an expectation.

**Expert conclusion:** testing compilation configurations must prove the same source code passes or is blocked by specific *dependency, type, and module accessibility boundaries*. A failed exit code is only a signal; the learning value lies in explaining **why the compiler rejects it** and verifying that a valid control configuration is still accepted.