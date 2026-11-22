# Using jdeprscan in CI to Detect Deprecated Java APIs

**jdeprscan** is a tool bundled with the JDK to scan bytecode and find usages of Java SE APIs that have been marked deprecated. In CI, it can be run after compile/package to detect legacy APIs in a class directory or JAR before release.

The key point when turning it into a quality gate: **jdeprscan can find deprecated APIs and still return exit code 0**. Therefore, merely running the command and relying on its exit code will not fail the build when there are warnings. The pipeline needs to inspect the output, detect usage lines, and return a non-zero exit code according to the project's policy.

This guide covers:

- Understanding the scope and limitations of jdeprscan.
- Choosing the right JDK and Java SE release to scan against.
- Scanning class files, directories, and JARs.
- Distinguishing standard deprecated APIs from APIs deprecated for removal.
- Writing CI gates for Bash and PowerShell.
- Integrating after a Maven or Gradle build.
- Managing dependencies, multi-module projects, and scan results.

## 1. What does jdeprscan do?

jdeprscan reads compiled bytecode and searches for references to Java SE APIs marked deprecated in the list for the selected Java release.

For example, source code might call:

- java.util.Date.getYear().
- java.net.URL(String).
- Constructor of java.lang.Integer.
- java.lang.Thread.stop().

If an API is deprecated in the selected release, the scanner reports which class is referencing that API.

A result line has the form:

~~~text
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

If the API is marked deprecated for removal, the result includes:

~~~text
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

This helps development teams find:

- Internal code still calling legacy APIs.
- Libraries or modules that need upgrading.
- APIs approaching removal.
- References that need to be addressed before a JDK upgrade.

### jdeprscan does not replace other tools

| Tool | Role |
|---|---|
| javac -Xlint:deprecation | Warns when compiling source code |
| jdeprscan | Scans compiled bytecode for deprecated Java SE APIs |
| jdeps --jdk-internals | Finds references to JDK internal APIs |
| Unit/integration tests | Verifies application behavior |
| Dependency scanner | Checks dependency versions and vulnerabilities |

jdeprscan focuses on deprecated Java SE APIs. It is not a tool for checking every `@Deprecated` annotation across all third-party libraries, it is not a vulnerability scanner, and it does not replace tests.

If the goal is to find JDK internal APIs, use `jdeps --jdk-internals` as well. An API that is not deprecated can still be an unsupported internal API.

## 2. Why run it in CI?

Deprecated APIs may still work in the current JDK, but they may be removed in a future release. If a project lets usages accumulate over time, upgrading the JDK can become difficult because it is unclear which modules depend on legacy APIs.

Placing the scan in CI provides these benefits:

- Detects new usages immediately in pull requests.
- Keeps the count of deprecated APIs from growing over time.
- Prioritizes addressing APIs marked for removal.
- Tracks which module or dependency causes a warning.
- Produces compatibility verification evidence for JDK upgrades.

The scan should run after compile and package, because jdeprscan requires bytecode. You can scan the class output directory before packaging or scan the final JAR before publishing.

A basic pipeline:

~~~text
Checkout
   |
   v
Set up JDK
   |
   v
Compile and test
   |
   v
Package JAR
   |
   v
Run jdeprscan
   |
   +---- No deprecated usage ----> Continue publish
   |
   +---- Deprecated usage ------> Fail quality gate
~~~

## 3. Installing and verifying the right JDK

jdeprscan is distributed with the JDK. The CI agent must have a JDK installed that includes this tool; stripped-down runtime images may not include developer tools.

Check on Linux/macOS:

~~~bash
java -version
javac -version
jdeprscan --version
command -v jdeprscan
~~~

On Windows PowerShell:

~~~powershell
java -version
javac -version
jdeprscan --version
Get-Command jdeprscan
~~~

You can use the direct path from `JAVA_HOME`:

Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeprscan" --version
~~~

Windows:

~~~powershell
& "$env:JAVA_HOME\bin\jdeprscan.exe" --version
~~~

When running in CI, make sure `java`, `javac`, and `jdeprscan` come from the intended JDK. If `PATH` points to a different JDK, the scan results may use a deprecated API list that does not match your upgrade target.

JDK 24.0.2 was used to test this guide. The tool in that environment supports `--release` values from 8 to 24. Supported releases may vary by JDK version; check `jdeprscan --help` on the exact CI image.

## 4. Syntax and main options

General syntax:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Supported input types:

- Directory that is the root of a package hierarchy.
- JAR file.
- Class file.
- Fully qualified class name, for example `java.lang.Thread$State`.

Commonly used options:

| Option | Meaning |
|---|---|
| --release N | Selects the Java SE release providing the deprecated API list |
| --for-removal | Scans only APIs deprecated for removal |
| --class-path PATH | Path to help resolve dependent classes |
| --list | Lists deprecated APIs without scanning any input |
| --verbose | Prints additional information during processing |
| --version | Prints the short version |
| --full-version | Prints the full version |
| --help | Prints help |

View help:

~~~bash
jdeprscan --help
~~~

View the list of deprecated APIs:

~~~bash
jdeprscan --list
~~~

List only APIs for removal:

~~~bash
jdeprscan --list --for-removal
~~~

`--list` only prints the API list; it is not an artifact scan command. Do not pass a directory, JAR, or class when using `--list`.

## 5. Choosing the right --release

`--release` selects the deprecated API dataset for the Java SE release to check against. It does not modify bytecode and does not replace `javac`'s `--release` option.

For example:

~~~bash
jdeprscan --release 17 build/libs/app.jar
~~~

This command asks: does this artifact reference any API marked deprecated in Java SE 17?

If preparing to upgrade to Java 24:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

This can detect APIs that were only deprecated in releases after Java 17.

In JDK 24.0.2, `URL(String)` has been deprecated since Java 20. When scanning the same class:

- `--release 17` does not report `URL(String)`.
- `--release 24` reports `URL(String)`.

Therefore, choose the release based on your goal:

| Goal | Choice |
|---|---|
| Maintain compatibility with Java 17 | --release 17 |
| Prepare runtime migration to Java 21 | --release 21 |
| Prepare runtime migration to Java 24 | --release 24 |
| Track multiple target runtimes | Run a separate scan for each supported release |

If the installed JDK tool does not support the target release, upgrade the JDK used in CI. For example, JDK 24 cannot provide the dataset for an unsupported future release.

## 6. Distinguishing deprecated and deprecated for removal

Not all deprecated APIs carry the same level of urgency.

**Standard deprecated:** The API is no longer recommended; developers should look for a replacement, but there is no statement that the API will be removed.

**Deprecated for removal:** The API is explicitly marked with the intent to be removed in a future release. This is usually the group to prioritize.

Scan all deprecated APIs:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

Scan only APIs for removal:

~~~bash
jdeprscan --release 24 --for-removal build/libs/app.jar
~~~

Lines with `forRemoval=true` indicate APIs in this group.

A practical policy might be:

- Report all deprecated APIs so the team can plan remediation.
- Enforce a strict quality gate on APIs for removal.
- After reducing legacy usage, gradually transition to gating on all deprecated APIs.

`--for-removal` is a filter. It does not mean other deprecated APIs are safe or will stay forever.

## 7. Scanning class files, directories, and JARs

### Scanning a class file

~~~bash
jdeprscan --release 24 build/classes/java/main/com/example/LegacyClient.class
~~~

The class name in the bytecode still follows the package hierarchy. Do not pass `.java` source files because jdeprscan reads bytecode.

### Scanning a directory

~~~bash
jdeprscan --release 24 build/classes/java/main
~~~

The directory must be the root of the package hierarchy. The scanner traverses classes within that directory tree.

### Scanning a JAR

~~~bash
jdeprscan --release 24 build/libs/application.jar
~~~

This is the right choice for pipelines checking artifacts after packaging.

### Scanning multiple inputs

~~~bash
jdeprscan --release 24 module-a/build/classes/java/main module-b/build/classes/java/main build/libs/application.jar
~~~

Multiple directories, JARs, or classes can be passed in a single invocation. In a multi-module project, ensure all module outputs to be checked are included in the list.

### Scanning a class name

~~~bash
jdeprscan --release 24 java.lang.Thread$State
~~~

The class name must be fully qualified. For nested classes, use `$` as the separator.

## 8. Using --class-path to resolve dependencies

Some classes require dependencies for the scanner to resolve references. Use `--class-path` to provide the path for locating dependent classes:

Linux/macOS:

~~~bash
jdeprscan --release 24 --class-path "build/classes:lib/*" build/libs/application.jar
~~~

Windows:

~~~powershell
jdeprscan --release 24 --class-path "build\classes;lib\*" build\libs\application.jar
~~~

The class path separator depends on the operating system: colon on Unix-like systems and semicolon on Windows.

**Class path is used to resolve dependencies; it does not automatically turn every dependency into a scanned input.** If you want to check for deprecated usage inside a library, pass that library's JAR as a separate input.

Tested on JDK 24.0.2:

- `app.jar` calls a method in `legacy-lib.jar`.
- Scanning `app.jar` with `legacy-lib.jar` on `--class-path` does not report deprecated usage inside the library.
- Scanning `legacy-lib.jar` as a separate input detects `Date.getYear()`.

Therefore, the pipeline may need to scan both the project's artifacts and any dependencies the team wants to control. You do not always need to scan the entire dependency tree; define the scope based on ownership, policy, and class resolution needs.

## 9. Java 17+ example: creating an artifact with deprecated APIs

This example uses three APIs:

- `Date.getYear()`: long deprecated.
- `URL(String)`: deprecated since Java 20.
- `Integer(int)`: deprecated for removal.

### DeprecatedApiDemo.java

~~~java
package com.example;

import java.net.URL;
import java.util.Date;

public final class DeprecatedApiDemo {
    public static void main(String[] args) throws Exception {
        Date epoch = new Date(0L);
        URL url = new URL("https://example.com/");
        Integer boxed = new Integer(42);

        System.out.println("legacy year=" + epoch.getYear());
        System.out.println("host=" + url.getHost());
        System.out.println("boxed=" + boxed);
    }
}
~~~

### CleanApiDemo.java

~~~java
package com.example;

import java.time.Instant;

public final class CleanApiDemo {
    public static void main(String[] args) {
        System.out.println(Instant.ofEpochSecond(0).getEpochSecond());
    }
}
~~~

Compile:

~~~bash
mkdir -p build/classes

javac --release 17 -Xlint:deprecation -d build/classes src/com/example/DeprecatedApiDemo.java src/com/example/CleanApiDemo.java
~~~

`javac` emits warnings for APIs deprecated in the selected compile-time API view. You can also use project lint and compiler policies for early warnings at compile time.

Run the program:

~~~bash
java -cp build/classes com.example.DeprecatedApiDemo
~~~

Exact stdout:

~~~text
legacy year=70
host=example.com
boxed=42
~~~

The example uses `Date` with epoch 0 so the year output is deterministic. `URL` is only constructed to read its host; no network request is sent.

## 10. Scanning and reading the example output

### Scanning against Java 17

~~~bash
jdeprscan --release 17 build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

`URL(String)` was not deprecated in Java 17, so it does not appear.

### Scanning against Java 24

~~~bash
jdeprscan --release 24 build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/net/URL::<init>(Ljava/lang/String;)V
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

`URL(String)` appears because this API is deprecated in Java 24.

### Scanning only APIs for removal

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

### Scanning a clean class

~~~bash
jdeprscan --release 24 build/classes/com/example/CleanApiDemo.class
~~~

The command prints no deprecated usage lines. This is the expected output for a clean class.

### Packaging and scanning a JAR

~~~bash
jar --create --file build/libs/demo.jar -C build/classes .
jdeprscan --release 24 build/libs/demo.jar
~~~

The JAR output contains the same deprecated references in `DeprecatedApiDemo`. The scanner does not need to run the application to find these references.

The outputs above were verified on JDK 24.0.2. Paths in actual output will match the artifact location on the CI agent.

## 11. Important: jdeprscan does not fail the build on its own

When scanning an artifact with deprecated APIs, jdeprscan 24.0.2 prints `uses deprecated` lines but still returns exit code 0.

Verified:

| Input | Deprecated finding | jdeprscan exit code |
|---|---|---:|
| DeprecatedApiDemo.class | Yes | 0 |
| demo.jar containing deprecated class | Yes | 0 |
| CleanApiDemo.class | No | 0 |

This means the following pipeline step is not sufficient:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

CI will continue because the command returns 0 even when the output has findings. To create a quality gate, you must inspect the output and set a non-zero exit code when deprecated usage is detected.

A good gate should handle three cases:

1. Scanner runs successfully and has no findings: pass.
2. Scanner runs successfully but has deprecated usage: fail according to policy.
3. Scanner fails to run or has unresolved diagnostics: fail to avoid falsely concluding that the artifact is clean.

## 12. Creating a CI gate with Bash

Create `ci/check-jdeprscan.sh`:

~~~bash
#!/usr/bin/env bash

set -u

artifact="$1"
release=17
log=jdeprscan.log

if [ "$#" -ge 2 ]; then
    release="$2"
fi

if [ "$#" -ge 3 ]; then
    log="$3"
fi

jdeprscan --release "$release" "$artifact" > "$log" 2>&1
tool_status=$?

cat "$log"

if [ "$tool_status" -ne 0 ]; then
    echo "jdeprscan execution failed with exit code $tool_status"
    exit "$tool_status"
fi

if grep -Eq ' uses deprecated |^(Warning|Error):' "$log"; then
    echo "Deprecated API usage or unresolved scan diagnostic found in $artifact"
    exit 1
fi

echo "No deprecated API usage found in $artifact"
exit 0
~~~

Grant execute permission on Linux/macOS:

~~~bash
chmod +x ci/check-jdeprscan.sh
~~~

Run after Maven:

~~~bash
mvn -B package
./ci/check-jdeprscan.sh target/application.jar 17
~~~

Run after Gradle:

~~~bash
./gradlew clean jar
./ci/check-jdeprscan.sh build/libs/application.jar 17
~~~

The second argument is the Java SE release to check. To write the log to a different location, pass a third argument.

The script saves the output so the log can be uploaded as a CI artifact. It checks both the tool's exit code and lines reporting deprecated usage or diagnostics.

If you want to block only APIs for removal, replace the scan command in the script with:

~~~bash
jdeprscan --release "$release" --for-removal "$artifact" > "$log" 2>&1
~~~

With this policy, standard deprecated APIs can still be reported in another job without failing the build.

## 13. Creating a CI gate with PowerShell

For Windows runners, you can use the following script:

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [ValidateRange(8, 24)]
    [int]$Release = 17,

    [switch]$ForRemoval
)

$scanArgs = @('--release', $Release.ToString())

if ($ForRemoval) {
    $scanArgs += '--for-removal'
}

$scanArgs += $Artifact

$output = @(& jdeprscan @scanArgs 2>&1)
$toolExit = $LASTEXITCODE

$output | Tee-Object -FilePath 'jdeprscan.log'

if ($toolExit -ne 0) {
    Write-Output "jdeprscan failed with exit code $toolExit"
    exit $toolExit
}

$findings = @(
    $output | Where-Object {
        $_.ToString() -match ' uses deprecated '
    }
)

$diagnostics = @(
    $output | Where-Object {
        $_.ToString() -match '^(Warning|Error):'
    }
)

if ($findings.Count -gt 0 -or $diagnostics.Count -gt 0) {
    Write-Output "Deprecated API usage or unresolved scan diagnostic found."
    exit 1
}

Write-Output "No deprecated API usage found."
exit 0
~~~

Save it as `ci/check-jdeprscan.ps1`.

Run a strict scan:

~~~powershell
.\ci\check-jdeprscan.ps1 -Artifact 'target\application.jar' -Release 17
~~~

Check only APIs for removal:

~~~powershell
.\ci\check-jdeprscan.ps1 -Artifact 'target\application.jar' -Release 24 -ForRemoval
~~~

The wrapper was tested with a deprecated artifact and a clean class on Windows PowerShell:

- Deprecated artifact: gate exits 1.
- Clean class: gate exits 0.

This exit code is produced by the wrapper. jdeprscan itself still returns 0 in both cases if the scan runs successfully.

## 14. Integrating into a CI pipeline

### GitHub Actions

After the workflow sets up the appropriate JDK, you can add these steps:

~~~yaml
- name: Build application
  run: mvn -B package

- name: Scan deprecated Java APIs
  run: bash ci/check-jdeprscan.sh target/application.jar 17

- name: Upload scan report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: jdeprscan-report
    path: jdeprscan.log
    if-no-files-found: ignore
~~~

If using a PowerShell runner, invoke the `.ps1` script with `pwsh` instead of Bash.

### GitLab CI

~~~yaml
stages:
  - build
  - quality

build:
  stage: build
  script:
    - mvn -B package
  artifacts:
    paths:
      - target/application.jar

deprecated-api-scan:
  stage: quality
  script:
    - bash ci/check-jdeprscan.sh target/application.jar 17
  artifacts:
    when: always
    paths:
      - jdeprscan.log
~~~

### Jenkins Pipeline

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh 'mvn -B package'
            }
        }

        stage('Deprecated API scan') {
            steps {
                sh 'bash ci/check-jdeprscan.sh target/application.jar 17'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'jdeprscan.log',
                             allowEmptyArchive: true
        }
    }
}
~~~

The CI examples assume the JDK is installed and `jdeprscan` is in `PATH`. Use the appropriate shell for your runner. For Windows runners, use the PowerShell wrapper.

## 15. Multi-module projects and dependency policy

In a Maven multi-module project, each module can produce one or more JARs. Scan each artifact individually to identify which module has deprecated usage.

For example:

~~~bash
./ci/check-jdeprscan.sh module-a/target/module-a.jar 17
./ci/check-jdeprscan.sh module-b/target/module-b.jar 17
./ci/check-jdeprscan.sh module-c/target/module-c.jar 17
~~~

With Gradle:

~~~bash
./ci/check-jdeprscan.sh module-a/build/libs/module-a.jar 17
./ci/check-jdeprscan.sh module-b/build/libs/module-b.jar 17
~~~

If dependency JARs are managed separately, you can scan them as independent inputs:

~~~bash
jdeprscan --release 24 module-a/target/module-a.jar module-b/target/module-b.jar lib/legacy-client.jar
~~~

Clearly define which dependencies fall within the gate's scope:

- Team-owned code: usually gated strictly.
- Third-party libraries: can be reported separately, version-pinned, and tracked upstream.
- Unmaintained libraries: record a time-bound exception and a replacement plan.
- Unresolved dependencies: fix the classpath before treating the scan as reliable.

Do not ignore every finding just because it comes from a dependency. A deprecated library can force the project to upgrade or replace it before migrating JDKs.

## 16. Handling findings in a pull request

When CI detects a deprecated API, handle it in this order:

1. Identify the reported class and API.
2. Open the corresponding source or locate the dependency owning the class.
3. Read the deprecated API's Javadoc to understand the reason.
4. Find the recommended replacement API.
5. Check differences in behavior, null handling, exceptions, and performance.
6. Replace the usage and add/adjust tests.
7. Rebuild and run jdeprscan.
8. Record an exception if it cannot be replaced immediately.

Do not replace an API based solely on a similar name. The new API may have different semantics or different configuration requirements.

For APIs for removal, prioritize fixing early because the upgrade risk is higher. If it cannot be fixed yet, create a ticket with a clear owner, deadline, and technical reason.

## 17. Limitations of jdeprscan

jdeprscan analyzes compiled bytecode and matches discovered references against the deprecated Java SE API list for the selected release. It is a scoped check, not a binary compatibility analyzer or a tool that proves an application runs on a new JDK.

Limitations to keep in mind:

- **Scans only passed inputs:** if you do not pass dependency JARs, plugin JARs, or module artifacts as inputs, the scanner does not automatically scan every file that might appear on the runtime class path.
- **Does not analyze source code:** compile first, then scan the class directory or JAR. Uncompiled source code is out of scope.
- **Cannot infer dynamic calls:** class/method names constructed from strings, reflection, `MethodHandle`, service/plugin discovery, or runtime-generated bytecode may not produce static constant-pool references that the scanner can recognize.
- **Does not prove all branches execute:** a finding is a reference in bytecode, not confirmation that the branch will run; conversely, a clean scan does not prove every code path is safe.
- **Depends on the release database:** `--release` selects the deprecated API list for the target Java SE release. Results from an older release do not represent the list of a newer release. Use the exact release your organization is upgrading to.
- **Does not replace third-party library checks:** deprecation annotations on non-Java SE APIs are not necessarily part of the data jdeprscan uses.
- **Does not detect all compatibility changes:** behavior changes, default configurations, module access, internal APIs, native libraries, serialization, TLS, or security policies can cause failures even with no deprecated references.
- **Does not assess risk automatically:** a reference might be in rarely used code or on a critical path. Findings need to be tied to an owner, call path, impact level, and replacement plan.

A clean result only means no deprecated references were found within the scanned inputs and release. Combine jdeprscan with `jdeps` for dependency/module inspection, compiler warnings, integration tests on the target JDK, and migration testing. For APIs invoked via reflection or plugins, add runtime tests and verify the corresponding module loading configuration.

## 18. Common issues

### jdeprscan command not found

Check the installed JDK, `JAVA_HOME`, and `PATH`. A minimal runtime image may not contain the tool.

### Unsupported release

Run `jdeprscan --help` and check the list of supported releases. Use a newer JDK if you need to scan against a newer Java SE release.

### Scanning .java source files

jdeprscan reads bytecode. Compile first, then pass the class directory or JAR.

### No output even though source has deprecated annotations

Check whether the bytecode actually contains the reference. Code not compiled into the artifact or code paths generated only at runtime will not appear in the scan.

### --release 17 does not report APIs deprecated in Java 20

This is expected behavior. `--release` selects the Java SE 17 dataset. Use `--release 24` if preparing to upgrade to Java 24.

### --for-removal does not report all deprecated APIs

This is a filter mode that keeps only APIs marked for removal. Omit the option if you want to see all deprecated APIs.

### CI does not fail even with findings

jdeprscan can return exit code 0 when deprecated usage is found. Use a wrapper that inspects the output and produces a non-zero exit code according to policy.

### Scanning the application JAR misses dependencies

`--class-path` helps resolve dependent classes; it does not automatically scan every JAR on the class path. Pass dependency JARs as separate inputs if you want to check them.

### Scan reports class resolution errors

Provide the required dependencies via `--class-path`. Check the OS path separator and ensure dependency files exist in the CI workspace.

## 19. CI quality gate checklist

- [ ] Runner has a JDK with jdeprscan installed.
- [ ] `java`, `javac`, and `jdeprscan` come from the same intended JDK.
- [ ] The right Java SE release is selected for the check target.
- [ ] Artifacts are built before scanning.
- [ ] All class directories or JARs to be checked are scanned.
- [ ] Dependency JARs are scanned separately if required by policy.
- [ ] `--for-removal` is used if a separate gate is needed for APIs slated for removal.
- [ ] Scanner output is saved as a CI artifact.
- [ ] The exit code of jdeprscan is checked.
- [ ] `uses deprecated` lines are parsed to turn findings into build failures.
- [ ] The gate fails if the scanner fails to run or has class resolution diagnostics.
- [ ] The wrapper is tested with both an artifact containing findings and a clean artifact.
- [ ] Exceptions have an owner and a deadline.
- [ ] Tests are run after replacing deprecated APIs.
- [ ] The scan is re-run after upgrading the JDK or dependencies.

## 20. Commands to remember

~~~bash
# Check tool version and options
jdeprscan --version
jdeprscan --help

# List deprecated APIs
jdeprscan --list

# List APIs for removal
jdeprscan --list --for-removal

# Scan a compiled class directory
jdeprscan --release 17 build/classes

# Scan a class file
jdeprscan --release 24 build/classes/com/example/LegacyClient.class

# Scan a packaged JAR
jdeprscan --release 24 build/libs/application.jar

# Scan only APIs deprecated for removal
jdeprscan --release 24 --for-removal build/libs/application.jar

# Resolve dependencies while scanning the application artifact
jdeprscan --release 24 --class-path "build/classes:lib/*" build/libs/application.jar

# Scan project artifacts and a dependency separately
jdeprscan --release 24 build/libs/application.jar lib/legacy-client.jar

# Source-level deprecation warnings during compilation
javac --release 17 -Xlint:deprecation -d build/classes src/main/java/com/example/*.java

# CI gate
bash ci/check-jdeprscan.sh build/libs/application.jar 17
~~~

jdeprscan turns detecting deprecated Java SE APIs into a repeatable step in CI. Scan bytecode after building, choose the right `--release`, distinguish standard deprecated APIs from APIs for removal, and remember that findings do not automatically produce a non-zero exit code. A small wrapper inspecting the output turns scan results into a clear quality gate that can be tested and archived alongside pipeline artifacts.

## References

- [The jdeprscan Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [The javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [Java Language Specification: Deprecated APIs](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Deprecated.html)
