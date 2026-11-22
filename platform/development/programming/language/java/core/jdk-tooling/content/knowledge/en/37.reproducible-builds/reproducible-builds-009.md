# Comparing Output in Reproducible Builds

## 1. Objective

In a reproducible build, the same source code and the same controlled inputs must produce byte-for-byte identical artifacts, even when built at different times or in different directories.

Comparing outputs helps confirm that a build is reproducible, detect timestamps or local machine paths leaking into artifacts, investigate differing checksums across CI agents, and verify released artifacts.

An identical checksum is very strong practical evidence that two files share the exact same bytes. If checksums differ, you need to locate the differing region before concluding that the program's behavior has changed.

## 2. Four Levels of Comparison

| Level | Question | Tools |
|---|---|---|
| Byte-for-byte | Do the two files have the exact same bytes? | SHA-256, cmp, fc /b |
| Archive structure | Do the two JARs have the same entries and metadata? | jar, unzip, zipinfo, diffoscope |
| Entry-level content | Which class, resource, or manifest differs? | Hash, javap, diff |
| Behavior | Do the two artifacts run the same way? | Test, stdout, integration test |

Byte-for-byte equality is the strongest goal. Semantic comparison is useful when hashes differ—for example, when two JARs contain the same classes but have different ZIP timestamps. Two programs that print the same stdout in a small test can still behave differently on other inputs.

## 3. Controlling Inputs

Before comparing, confirm that both builds use the same commit, Gradle Wrapper, JDK/compiler toolchain, dependency and plugin versions, build arguments, generated sources, resources, and build profile. Record the OS, architecture, locale, timezone, and encoding if the build depends on the environment.

If two builds use different JDKs, the compiler may emit different bytecode even with the same --release flag. --release 17 controls the language/API target and bytecode version, but does not force two different compiler builds to produce the exact same bytes.

```bash
./gradlew --version
./gradlew clean jar
```

On Windows:

```powershell
./gradlew.bat --version
./gradlew.bat clean jar
```

Record the version and artifact checksum. Do not compare a build using the Wrapper against an unpinned global Gradle installation.

## 4. Comparing SHA-256

SHA-256 produces a fixed fingerprint from a file's bytes. Changing a single byte will change the hash with overwhelming probability.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 ./build-a/build/libs/app.jar
Get-FileHash -Algorithm SHA256 ./build-b/build/libs/app.jar

$hashA = (Get-FileHash -Algorithm SHA256 ./build-a/build/libs/app.jar).Hash
$hashB = (Get-FileHash -Algorithm SHA256 ./build-b/build/libs/app.jar).Hash

if ($hashA -eq $hashB) {
    "BYTE-FOR-BYTE MATCH"
} else {
    "OUTPUTS DIFFER"
}
```

Linux/macOS:

```bash
sha256sum build-a/build/libs/app.jar
sha256sum build-b/build/libs/app.jar
```

Do not compare SHA-1 against SHA-256 or hashes of two different artifacts. A hash confirms the integrity of bytes; it does not prove who created the artifact or whether the release source is trustworthy.

## 5. Direct Byte Comparison

Windows:

```powershell
fc /b ./build-a/build/libs/app.jar ./build-b/build/libs/app.jar
```

Linux/macOS:

```bash
cmp build-a/build/libs/app.jar build-b/build/libs/app.jar
```

cmp returns exit code 0 when the files are identical. Do not use standard text diff on JAR, class, or ZIP files because they are binary files.

## 6. Comparing JAR Structure

JAR files are based on ZIP. When checksums differ, inspect the entry list:

```bash
jar --list --file build-a/build/libs/app.jar
jar --list --file build-b/build/libs/app.jar
jar --list --verbose --file build-a/build/libs/app.jar
unzip -l build-a/build/libs/app.jar
unzip -t build-a/build/libs/app.jar
zipinfo -v build-a/build/libs/app.jar
```

Compare entry names and counts, ordering, timestamps, compression methods, compressed sizes, permissions, manifest, META-INF, and ZIP extra fields.

jar --validate primarily checks the consistency of multi-release JARs; it is not a general-purpose diff tool. Use unzip -t to verify ZIP CRCs.

## 7. Extracting and Comparing Entries

```bash
mkdir -p compare/a compare/b
(cd compare/a && jar --extract --file ../../build-a/build/libs/app.jar)
(cd compare/b && jar --extract --file ../../build-b/build/libs/app.jar)
```

Compare the list of relative paths, then compare the hash of each file. File timestamps after extraction can be ignored if the goal is only to compare entry contents; timestamps inside the archive still affect the JAR bytes.

Example of generating a per-file hash manifest using PowerShell:

```powershell
$root = (Resolve-Path ./compare/a).Path

Get-ChildItem -LiteralPath $root -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($root.Length).TrimStart([char]92, [char]47)
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        "$hash  $relative"
    } | Set-Content ./compare/a.sha256
```

Repeat for the compare/b directory, then use Compare-Object or diff to find differing entries. This hash list helps distinguish added or removed entries from entries whose contents changed.

## 8. Comparing Classes with javap

```bash
javap -classpath build-a/build/libs/app.jar -c -p demo.Main
javap -classpath build-b/build/libs/app.jar -c -p demo.Main
javap -classpath build-a/build/libs/app.jar -v -p demo.Main
```

javap -c displays bytecode; javap -v additionally shows the constant pool, annotations, source file, line numbers, and debug attributes. Identical disassembly does not guarantee that class files are byte-for-byte identical; hashing the .class files confirms exact bytes.

## 9. Comparing Resources

Check encoding, UTF-8 BOM, LF/CRLF line endings, whitespace, key ordering, timestamps, build numbers, absolute paths, hostname, locale, and timezone.

Only normalize line endings, whitespace, or key ordering if those differences are not meaningful. Do not normalize artifacts before computing checksums. Keep the original file hashes and document the rules clearly when creating copies for semantic comparison.

## 10. Using diffoscope

diffoscope analyzes differences between two files or directories, recognizes archives and binaries, and presents differences in their inner layers.

```bash
diffoscope build-a/build/libs/app.jar build-b/build/libs/app.jar
```

The tool can pinpoint ZIP entries with different timestamps, differing manifests, changed resources, differing class metadata, or differing nested JARs. If diffoscope is not installed, use jar, unzip, javap, per-entry hashing, and diff.

## 11. Common Sources of Non-Determinism

Two builds from the same source can still produce different outputs due to:

| Source | Example | Mitigation |
|---|---|---|
| Timestamp | File modification time inside JAR | Do not preserve file timestamps |
| File order | Filesystem returns entries in different order | Use reproducible file order |
| JDK/compiler | JDK patch emits different class bytes | Pin the Java toolchain |
| Gradle/plugin | Task or archive format changes | Use the Wrapper and pin plugins |
| Dependency | Dynamic version or SNAPSHOT changes | Dependency locking |
| Build path | Absolute path leaks into resources | Use relative paths or remapping |
| Locale/timezone | Dates and numbers formatted differently | Set locale/timezone explicitly |
| Encoding | Different default charset | Declare UTF-8 |
| Randomness | UUID or random seed | Use a deterministic seed |
| Permission | File mode inside archive | Fixed permission policy |
| Environment | Build number or branch name | Declare controlled inputs |
| Parallel generation | Output order depends on race conditions | Deterministic generators |

Pay special attention to tasks that generate build metadata. Inserting new Date(), Instant.now(), hostname, or an absolute path into a resource will cause the artifact to change on every build even when the source is unchanged.

## 12. Configuring Gradle for Reproducible Archives

Gradle 9.0 and later create archives with stable entry ordering, fixed timestamps, and stable permissions by default. Two key properties of AbstractArchiveTask are:

- preserveFileTimestamps = false: do not copy source file timestamps into the archive.
- reproducibleFileOrder = true: traverse files in a stable order, independent of the filesystem.

Groovy DSL:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Kotlin DSL:

```kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Explicit configuration is useful when a project supports older Gradle versions or wants to make the build policy clear. In Gradle 9+, these values are already the defaults unless overridden.

## 13. Pinning the JDK and Dependencies

Declare a Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchains allow Gradle to select the JDK compiler according to the declared version instead of using an arbitrary JDK from JAVA_HOME. options.release = 17 constrains the API and bytecode target, but does not replace pinning the compiler when byte-level reproducibility is required.

Dependency locking preserves resolved versions:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Generate or update the lock state:

```bash
./gradlew build --write-locks
```

Dependency verification confirms that downloaded dependency artifacts match trusted checksums or signatures:

```bash
./gradlew --write-verification-metadata sha256
```

Review gradle/verification-metadata.xml before committing. Locking fixes which versions are selected; verification checks the bytes of the received artifacts. The two mechanisms solve different problems.

## 14. Comparing Outputs Across Two Directories

Building the same source in two independent workspaces helps detect absolute paths, timestamps, and local state leaking into artifacts.

PowerShell example:

```powershell
$source = "C:/work/compare-demo"
$a = "C:/work/build-a"
$b = "C:/work/build-b"

Copy-Item -LiteralPath $source -Destination $a -Recurse
Copy-Item -LiteralPath $source -Destination $b -Recurse

Get-ChildItem -LiteralPath $b -Recurse -File |
    ForEach-Object {
        $_.LastWriteTimeUtc = [DateTime]::UtcNow.AddDays(-20)
    }

Push-Location $a
./gradlew.bat --no-daemon --offline clean jar
Pop-Location

Push-Location $b
./gradlew.bat --no-daemon --offline clean jar
Pop-Location

$jarA = Join-Path $a "build/libs/compare-demo-1.0.0.jar"
$jarB = Join-Path $b "build/libs/compare-demo-1.0.0.jar"

$hashA = (Get-FileHash -Algorithm SHA256 $jarA).Hash
$hashB = (Get-FileHash -Algorithm SHA256 $jarB).Hash

Write-Output $hashA
Write-Output $hashB
Write-Output ($hashA -eq $hashB)
```

The two workspaces have different paths and source file timestamps. If the toolchain and inputs are identical, the two JARs must still have the same SHA-256 hash.

--offline tells Gradle to use dependencies and plugins already in the cache; it does not replace dependency locking or verification. If dependencies are missing, pre-fetch them in a trusted environment or omit --offline while keeping controlled repositories and versions.

## 15. Complete Example: Creating a JAR and Comparing Two Builds

Project structure:

```text
compare-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            └── app.properties
```

File settings.gradle:

```groovy
rootProject.name = 'compare-demo'
```

File build.gradle:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Version': project.version
        )
    }
}
```

File src/main/java/demo/Main.java:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("missing app.properties");
            }
            properties.load(input);
        }

        System.out.println(
                "build-output=" + properties.getProperty("message"));
    }
}
```

File src/main/resources/app.properties:

```properties
message=stable
```

Build two copies in two different directories. Once the builds complete, run:

```powershell
java -jar $jarA
java -jar $jarB
```

Both must print:

```text
build-output=stable
```

In a test run on Gradle 9.2.1 and OpenJDK Zulu 24.0.2, the Java 17 release project was built from two different directories with source timestamps 20 days apart. Result:

```text
BUILD_A_SHA256=3504E0FDE71D7E5D8670EB430F259F7553F18E33108D79E4777F4CE6E5A289B9
BUILD_B_SHA256=3504E0FDE71D7E5D8670EB430F259F7553F18E33108D79E4777F4CE6E5A289B9
HASH_MATCH=True
ENTRY_LIST_MATCH=True
JAVAP_MATCH=True
RUN_OUTPUT_MATCH=True
RUN_OUTPUT=build-output=stable
```

Then change the resource in workspace B to:

```properties
message=changed
```

Rebuild B. The hash changes to:

```text
CHANGED_SHA256=33E93388B2E199AC15649887528DB4F322F8C2D5C212D1955E50C57959CEE706
HASH_DIFFERENT_AFTER_RESOURCE_CHANGE=True
CHANGED_OUTPUT=build-output=changed
OUTPUT_DIFFERENT=True
```

The two specific hashes above are the result of a single run on the stated environment; another machine or compiler may produce different hashes. What needs to be verified is that two builds with the same inputs produce equal hashes, while an actual resource change causes both the hash and the application output to change.

## 16. Distinguishing Metadata Differences from Code Differences

When hashes do not match, do not jump to the conclusion that the source code is wrong. Investigate in order:

1. Compare the entry list to see if any files were added or removed.
2. Compare timestamps, entry order, permissions, and ZIP metadata.
3. Compare the manifest and generated resources.
4. Hash each entry to find files with differing contents.
5. Run javap -c -v on differing classes.
6. Check compiler version, dependencies, and plugins.
7. Check paths, locale, timezone, encoding, and environment variables.
8. Run diffoscope if multi-layer archive analysis is needed.
9. Run tests on both artifacts to determine behavioral differences.

| Observed Result | Initial Interpretation |
|---|---|
| Hashes match | Artifacts are byte-for-byte identical |
| Hashes differ, entry list matches | Metadata or entry contents may differ |
| Only entry timestamps differ | Archive is not yet reproducible; JAR bytes still differ |
| Manifest differs | Unstable build metadata or manifest configuration |
| Only resources differ | Check generators, encoding, environment, and inputs |
| Class bytes differ, javap matches | Debug info, constant pool, or unprinted attributes may differ |
| Bytecode differs | Check compiler, source, annotation processors, and compiler flags |
| Artifacts match but runtime output differs | Check runtime JDK, environment, external services, and data |

A metadata difference is still a reproducibility bug if byte-for-byte equality is required. However, it may not be a functional regression. Reports should clearly state the type of difference rather than lumping everything together as a "broken build".

## 17. Comparing Test Results and Runtime Output

Byte-identical artifacts do not automatically guarantee that the application works correctly. After confirming hashes, you still need to run tests and runtime checks as required.

You can compare unit tests, integration tests, stdout/stderr on the same input, exit codes, generated files, API responses, database migrations, and performance metrics.

For text output:

```powershell
java -jar $jarA *> ./compare/a-output.txt
java -jar $jarB *> ./compare/b-output.txt

Compare-Object (Get-Content ./compare/a-output.txt) (Get-Content ./compare/b-output.txt)
```

Ensure both runs use the same input, working directory, timezone, locale, environment, and external service state. If the output contains request IDs, timestamps, or random values, decide whether they are meaningful data or noise before normalizing.

Do not strip volatile fields just to make tests pass if they are part of the output contract. Document clearly which fields are allowed to differ and why.

## 18. Signed JARs and Artifacts with Time Metadata

A JAR signature depends on the archive contents and signature metadata. If any entry is modified after signing, the signature may no longer be valid.

Timestamps in the signature, certificate, or signing process can cause two signed files to differ even when the unsigned JARs are identical. Therefore:

1. Compare the unsigned JARs to confirm reproducible packaging.
2. Check the signing configuration and timestamp authority.
3. Verify the signature independently on the released artifact.
4. Do not modify the archive after signing.
5. Record checksums separately for unsigned and signed artifacts.

Verify the signature:

```bash
jarsigner -verify -verbose -certs build/libs/app.jar
```

Matching hashes do not replace signature verification. A hash tells you whether bytes match a known fingerprint; a signature verifies that the artifact was signed by the corresponding key and that its contents have not been modified after signing.

## 19. Automating Comparison in CI

CI can run two clean builds from the same commit in independent workspaces, then compare their SHA-256 hashes. If the hashes differ, archive the artifacts and logs for investigation.

A minimal pipeline should:

1. Check out the same commit into two clean workspaces.
2. Use the same Gradle Wrapper and JDK toolchain.
3. Lock dependencies and verify dependency artifacts.
4. Build with the same arguments.
5. Compute the SHA-256 hash of the artifact.
6. Fail the reproducibility step if the hashes differ.
7. Save both artifacts, hashes, Gradle/JDK versions, and build logs.
8. When differences occur, generate an entry-level or diffoscope report.

Do not use the same output directory for two parallel builds because they can overwrite each other's artifacts. Each build needs an independent workspace and output path.

For released artifacts, use a clean and trusted CI environment. Caching is useful for regular builds when configured properly; reproducibility checks should actively exclude stale state that could obscure provenance.

## 20. Checklist When Two Outputs Do Not Match

- [ ] Do both builds use the same commit and the same source contents?
- [ ] Are the Gradle Wrapper and plugin versions identical?
- [ ] Are the JDK vendor, version, and compiler toolchain identical?
- [ ] Are dependency versions locked and verified?
- [ ] Are archive entry timestamps and ordering stable?
- [ ] Does the manifest contain build time, hostname, or build number?
- [ ] Do generated resources use randomness, clocks, or absolute paths?
- [ ] Are encoding and line endings consistent?
- [ ] Do file permissions and archive metadata differ?
- [ ] Does any task read environment variables or depend on filesystem order?
- [ ] Have per-entry hashes and disassembly been compared?
- [ ] Have both artifacts been run with the same inputs and environment?

## 21. Summary

Output comparison is the step that confirms the same build inputs produce the same artifact, while also helping pinpoint the root cause when results differ.

Key takeaways:

- Use SHA-256 for a fast check of byte-for-byte equality.
- Use cmp or fc /b when direct byte comparison is needed.
- Use jar --list, unzip, per-entry hashing, and javap to analyze structure.
- Use diffoscope when you need to explain complex binary differences.
- Distinguish metadata differences, class/resource content differences, and runtime behavior.
- Keep archive timestamps and ordering stable; Gradle 9+ enables reproducible archives by default.
- Pin Gradle, JDK, plugins, and dependencies; control locale, timezone, encoding, paths, and generated files.
- Compare two builds in independent workspaces to detect machine-dependent data.
- Preserve original artifact hashes; only normalize copies when performing semantic comparison.
- Verify signatures separately; checksums do not prove provenance or publisher identity.

**Official References:**

- [Gradle — Best Practices for Security: Build Output Should Be Byte-for-Byte Reproducible](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle — Working With Files: Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle DSL — Jar](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle DSL — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Oracle Java SE 24 — The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Oracle Java SE 24 — The javap Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html)
- [Oracle Java SE 24 — JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
