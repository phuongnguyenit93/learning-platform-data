# Integrating All JDK Tooling into CI

CI (Continuous Integration) automates the Java build lifecycle: selecting the JDK and build tool, compiling, testing, checking bytecode/dependencies, creating JARs, generating Javadoc, packaging the runtime/installer, signing artifacts, verifying checksums, and storing build evidence. When integrated properly, every commit is verified through the same process, and releases can be traced back to the exact source revision and toolchain that produced them.

Not every JDK command needs to run on every pull request. CI should be divided by purpose: fast checks on pull requests; compatibility checks and extended diagnostics on a schedule; native packaging and digital signing in the release pipeline. `jlink` is only used when a custom runtime from modules is needed; `jpackage` is only used when distributing an application image/installer; `jcmd` requires the target JVM to still be running; `jarsigner` only runs in releases with a valid signing certificate.

## 1. Overview of Tools in the Pipeline

| Stage | Tool | Result/Condition to Verify |
| --- | --- | --- |
| Environment preparation | java, javac, Gradle/Maven Wrapper | Record version, vendor, build JVM, compiler JDK, and OS |
| Compile | javac or Gradle/Maven compile task | Bytecode/API target matches the Java release |
| Test | java, Gradle Test, Maven Surefire/Failsafe | Unit/integration tests pass on supported JDKs |
| Artifact inspection | jar, javap | Manifest, archive contents, and class-file version are correct |
| Dependency analysis | jdeps, jdeprscan | No unintended use of JDK internal APIs; check deprecated APIs |
| Documentation | javadoc | API docs generate successfully, DocLint has no errors |
| Custom runtime | jlink | Image contains only required modules, launcher runs |
| Application image/installer | jpackage | Package matches OS/architecture, smoke test runs |
| Certificates and signing | keytool, jarsigner | Certificate chain is valid, signature and timestamp are verified |
| Diagnostics | jcmd, jfr, jstack, jmap, jstat | Thread dump, heap/JVM information, and Flight Recording when needed |
| Artifact storage | SHA-256, CI artifact upload, provenance report | JAR, docs, test reports, checksum, and build metadata are stored together |

A good pipeline uses the build tool as the primary path for compile/test/package, then invokes JDK tools directly to inspect the output. This ensures steps run in the right order and operate on the same artifact.

## 2. Defining the Build Contract Before Configuring CI

The repository needs to clearly specify:

- JDK distribution/vendor and supported Java versions.
- Java release target, for example Java 17.
- Gradle/Maven version via the Wrapper.
- Plugin versions and dependency versions/lock state.
- Standard build commands, test profiles, and artifact names.
- Target OS/architecture for creating native packages.
- Steps that only run on release: signing, timestamping, publishing, and attestation.

Distinguish between the **build-running JDK**, **compiler/test toolchain**, and **release target**. For example, a build can run on JDK 25, the compiler can use JDK 25, while `--release 17` produces bytecode and restricts the API to Java 17. `--release` does not select the JDK compiler; the toolchain determines the compiler and test launcher.

Use the Gradle/Maven Wrapper so CI does not depend on a pre-installed build tool on the runner. For Gradle, pin `distributionUrl` and configure `distributionSha256Sum` obtained from the official checksum. Inspect `gradle-wrapper.jar` whenever upgrading the Wrapper because this file is executed before in-build controls run.

## 3. Configuring Gradle for CI

An example `build.gradle` using Java 17 as the baseline, allowing CI to pass a JDK matrix via property, creating an executable JAR, and turning Javadoc warnings into errors:

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

def ciJdk = providers.gradleProperty('ciJdk')
    .map { Integer.parseInt(it) }
    .getOrElse(17)

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(ciJdk)
    }
}

application {
    mainClass = 'com.example.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
    options.compilerArgs.addAll(['-Xlint:all'])
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

tasks.withType(Javadoc).configureEach {
    options.addBooleanOption('Werror', true)
}

tasks.named('jar', Jar) {
    archiveBaseName = 'myapp'
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Version': project.version
        )
    }
}
```

With this configuration, the sample JAR file is `build/libs/myapp-1.0.0.jar`. Adjust `mainClass`, test framework, and version according to the project. The `check` task runs verification tasks attached to the lifecycle; `javadoc` needs to be invoked explicitly if you want CI to check API documentation on every build.

### Gradle Wrapper

Commit the files `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and `gradle/wrapper/gradle-wrapper.properties`. Example:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
distributionSha256Sum=<OFFICIAL_SHA256_OF_DISTRIBUTION>
```

Replace the checksum value with the official checksum of the exact pinned distribution. Do not generate a checksum from a freshly downloaded ZIP file and use that same value to verify the file.

Local and CI commands must use `./gradlew` or `gradlew.bat`, not a global `gradle`.

## 4. GitHub Actions: Pull Request Checks and Build Matrix

The workflow below runs on Java 17, 21, and 25. Each job uses the JDK in the matrix to compile/test, while `options.release = 17` keeps the compatibility baseline at Java 17.

Create `.github/workflows/java-ci.yml`:

```yaml
name: Java CI

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    name: Verify with JDK ${{ matrix.jdk }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}
          cache: gradle

      - name: Record toolchain
        run: |
          mkdir -p build/reports/toolchain
          {
            java --version
            javac --version
            jar --version
            javadoc --version
            jdeps --version
            jlink --version
            jpackage --version
            ./gradlew --version
            ./gradlew javaToolchains
            git rev-parse HEAD
            git status --short
          } > build/reports/toolchain/environment.txt 2>&1

      - name: Compile, test, document and package
        run: |
          ./gradlew --no-daemon \
            -PciJdk=${{ matrix.jdk }} \
            clean check javadoc jar

      - name: Inspect JAR with JDK tools
        run: |
          APP_JAR=build/libs/myapp-1.0.0.jar
          test -f "$APP_JAR"
          mkdir -p build/reports/jdk

          jar --validate --file "$APP_JAR"
          jar --list --verbose --file "$APP_JAR" \
            > build/reports/jdk/jar-contents.txt

          jdeps --multi-release 17 --jdk-internals "$APP_JAR" \
            > build/reports/jdk/internal-api-report.txt

          jdeprscan --release 17 "$APP_JAR" \
            > build/reports/jdk/deprecated-api-report.txt

          javap -classpath "$APP_JAR" -verbose com.example.Main \
            > build/reports/jdk/main-class.txt

          grep -q "major version: 61" \
            build/reports/jdk/main-class.txt

      - name: Upload JAR for release packaging
        if: ${{ matrix.jdk == '17' }}
        uses: actions/upload-artifact@v7
        with:
          name: myapp-jar
          path: build/libs/myapp-1.0.0.jar
          if-no-files-found: error

      - name: Upload reports and test results
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: java-ci-reports-${{ matrix.jdk }}
          path: |
            build/reports/**
            build/test-results/**
            build/docs/javadoc/**
          if-no-files-found: warn
```

In this workflow:

- `setup-java` installs the JDK, sets `JAVA_HOME`/`PATH`, and caches dependencies/wrapper appropriately.
- `./gradlew --version` records the Gradle version along with the JVM running Gradle; `javaToolchains` lists the JDKs discovered by Gradle.
- `check`, `javadoc`, and `jar` generate test results, API docs, and the artifact.
- `jar --validate` validates the archive; `jar --list` saves the contents for investigation when packaging is incorrect.
- `jdeps --jdk-internals` reports dependencies on JDK internal APIs. Save the report and apply a review/fail policy if the project prohibits these dependencies.
- `jdeprscan --release 17` checks deprecated API usage against the release target. Set warning thresholds according to the project's compatibility policy.
- `javap -verbose` checks the class-file major version. Java 17 has major version 61; therefore, the workflow fails if the sample class does not match the baseline.
- The JAR artifact is only uploaded from the Java 17 job so the release uses the exact binary that passed baseline verification; the remaining matrix jobs still verify compatibility.

If the application uses external libraries, provide the runtime dependency classpath to `jdeps` via `--class-path` (or module path for modular apps). Analyzing only a JAR without its dependencies can produce an incomplete report.

`actions/setup-java` supports multiple JDK distributions, version matrices, Maven/Gradle caching, Maven Toolchains, and checksum verification of JDK archives when the provider publishes checksums. For strict supply-chain requirements, pin GitHub Actions by verified commit SHA and verify the Gradle Wrapper JAR/distribution.

## 5. Maven: Integrating the Same Workflow

If the project uses Maven, run the Wrapper and `verify` to compile, run unit tests, run integration tests (when Failsafe is configured), package, and execute verification goals bound to the lifecycle.

Example plugin configuration section in `pom.xml`:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.6.3</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-javadoc-plugin</artifactId>
        <version>3.12.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </pluginManagement>

  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <executions>
        <execution>
          <id>enforce-build-environment</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <requireMavenVersion>
                <version>[3.9,4)</version>
              </requireMavenVersion>
              <requireJavaVersion>
                <version>[17,26)</version>
              </requireJavaVersion>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
      </configuration>
    </plugin>

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <configuration>
        <failOnWarnings>true</failOnWarnings>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Adjust the version range in Enforcer according to your support policy. `requireJavaVersion` checks the JVM running Maven. If the compiler or tests need a separate JDK, configure Maven Toolchains; do not confuse the Maven runtime with the compiler toolchain.

Corresponding Maven workflow:

```yaml
name: Maven Java CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}
          cache: maven

      - name: Record toolchain
        run: |
          java --version
          javac --version
          ./mvnw --version
          ./mvnw toolchains:display-discovered-jdk-toolchains

      - name: Verify
        run: |
          ./mvnw --batch-mode --no-transfer-progress clean verify
          ./mvnw --batch-mode --no-transfer-progress javadoc:javadoc

      - name: Inspect artifact
        run: |
          APP_JAR=target/myapp-1.0.0.jar
          jar --validate --file "$APP_JAR"
          jar --list --verbose --file "$APP_JAR"
          jdeps --multi-release 17 --jdk-internals "$APP_JAR"
          jdeprscan --release 17 "$APP_JAR"
```

`setup-java` can generate Maven Toolchains entries for installed JDKs. If the POM requires a specific toolchain version/vendor, ensure the action installs the right distribution and `~/.m2/toolchains.xml` provides the corresponding mapping. Use `./mvnw`, do not rely on a globally installed Maven.

Maven `verify` does not automatically run the Javadoc goal in every project; invoke `javadoc:javadoc` or bind the goal to the lifecycle if you want it to be a mandatory gate. Maven Compiler Plugin `release` restricts language/API/bytecode; Maven Toolchains selects the actual JDK used by toolchain-aware plugins.

## 6. Bringing jdeps, jlink, and jpackage into the Packaging Stage

These three tools serve different purposes:

- `jdeps` analyzes dependencies between classes, packages, JARs, and modules. Use `--print-module-deps` to get the module dependency list for `jlink`.
- `jlink` creates a custom runtime image from modules along with transitive dependencies. Use only when the application is modular or its dependency graph has been converted into suitable modules.
- `jpackage` creates an application image or native installer. If no runtime image is provided, `jpackage` can invoke `jlink` itself to create a runtime for the package.

### Creating a Runtime Image with jlink

Example for a modular app with module `com.example.myapp` and main class `com.example.Main`:

```bash
APP_JAR=build/libs/myapp-1.0.0.jar

MODULE_DEPS=$(jdeps \
  --module-path "$APP_JAR" \
  --print-module-deps \
  "$APP_JAR")

jlink \
  --module-path "$JAVA_HOME/jmods:$APP_JAR" \
  --add-modules "com.example.myapp,$MODULE_DEPS" \
  --launcher myapp=com.example.myapp/com.example.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime

build/runtime/bin/myapp
```

Replace the module and main class with actual names. `jdeps` returns the application's dependencies; the root module is explicitly added to `--add-modules`. Run the launcher in the runtime image as a smoke test before packaging. The runtime image must be updated when JDK security updates or module dependencies change.

With JDK on Windows, the module path separator is `;` instead of `:`. Use PowerShell or a separate script for Windows runners.

### Creating an Application Image/Installer with jpackage

For a non-modular application, the input directory contains the JAR and resources:

```bash
mkdir -p dist
cp build/libs/myapp-1.0.0.jar dist/

jpackage \
  --type app-image \
  --name MyApp \
  --app-version 1.0.0 \
  --input dist \
  --main-jar myapp-1.0.0.jar \
  --main-class com.example.Main \
  --dest build/package
```

Smoke test the application image by OS:

```bash
# Linux
./build/package/MyApp/bin/MyApp

# macOS
./build/package/MyApp.app/Contents/MacOS/MyApp
```

Windows PowerShell:

```powershell
$process = Start-Process -FilePath ".\\build\\package\\MyApp\\MyApp.exe" -Wait -PassThru -NoNewWindow
if ($process.ExitCode -ne 0) {
    exit $process.ExitCode
}
```

For modular apps, you can use `--module-path` and `--module` instead of `--input`, `--main-jar`, and `--main-class`. `app-image` creates a runnable directory for smoke testing; package types like MSI/EXE, DEB/RPM, or PKG/DMG are the next step.

**Native packages must be built on the target OS.** Use a matrix of Windows, Linux, and macOS runners to produce the right formats. Windows MSI/EXE requires appropriate packaging tools such as WiX; macOS distribution requires a Developer ID signing/notarization process; Linux packages require the distro's packaging tools. `jpackage` does not cross-compile native installers for other operating systems.

## 7. Signing Artifacts with keytool and jarsigner

`keytool` manages keystores, key pairs, and certificates. `jarsigner` signs JARs and verifies signatures/integrity. Generate or import release keys in a separate key management process; CI should only receive credentials from a protected secret store or HSM/KMS.

In the release job, run only after build/test has passed and sign only the exact JAR uploaded from the `verify` job. Example on a Linux runner:

```bash
mkdir -p dist
printf '%s' "$JAR_SIGNING_KEYSTORE_BASE64" \
  | base64 --decode > "$RUNNER_TEMP/release.p12"
chmod 600 "$RUNNER_TEMP/release.p12"

export JAR_STORE_PASSWORD
export JAR_KEY_PASSWORD

keytool -list -v \
  -keystore "$RUNNER_TEMP/release.p12" \
  -storetype PKCS12 \
  -storepass:env JAR_STORE_PASSWORD

jarsigner \
  -keystore "$RUNNER_TEMP/release.p12" \
  -storetype PKCS12 \
  -storepass:env JAR_STORE_PASSWORD \
  -keypass:env JAR_KEY_PASSWORD \
  -tsa "$JAR_TSA_URL" \
  -signedjar dist/myapp-1.0.0-signed.jar \
  dist/myapp-1.0.0.jar \
  "$JAR_SIGNING_ALIAS"

jarsigner -verify -strict -verbose -certs \
  dist/myapp-1.0.0-signed.jar

sha256sum dist/myapp-1.0.0-signed.jar \
  > dist/myapp-1.0.0-signed.jar.sha256
```

Declare `JAR_SIGNING_KEYSTORE_BASE64`, `JAR_STORE_PASSWORD`, `JAR_KEY_PASSWORD`, `JAR_SIGNING_ALIAS`, and `JAR_TSA_URL` in the release job's protected environment. `-storepass:env` and `-keypass:env` read passwords from environment variables, avoiding plaintext passwords in commands. Do not print secrets or keystores to logs/artifacts; delete the temporary keystore file after signing.

`jarsigner -verify -strict` turns severe certificate warnings into errors. Self-signed test certificates are only suitable for testing the pipeline; production requires a certificate chain trusted by recipients and a valid timestamp authority. JAR signatures and SHA-256 checksums serve different purposes: a signature verifies the signer/integrity under the certificate trust model, while a checksum verifies the file's bytes.

`jarsigner` signs JARs; it does not replace Authenticode for Windows executables or Developer ID signing/notarization for macOS app bundles. Native installer signing is a separate gate after `jpackage` completes.

## 8. Release Job: Packaging from Verified Artifacts

Example job creating an application image on each OS when pushing a release tag. The job downloads the JAR uploaded from the Java 17 matrix and packages it on the target runner:

```yaml
  package:
    if: ${{ startsWith(github.ref, 'refs/tags/v') }}
    needs: verify
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/download-artifact@v7
        with:
          name: myapp-jar
          path: dist

      - name: Create Windows app image
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          jpackage --type app-image --name MyApp --app-version 1.0.0 --input dist --main-jar myapp-1.0.0.jar --main-class com.example.Main --win-console --dest build/package

      - name: Create Linux or macOS app image
        if: runner.os != 'Windows'
        run: |
          jpackage --type app-image --name MyApp \
            --app-version 1.0.0 \
            --input dist \
            --main-jar myapp-1.0.0.jar \
            --main-class com.example.Main \
            --dest build/package

      - name: Smoke test Linux image
        if: runner.os == 'Linux'
        run: ./build/package/MyApp/bin/MyApp

      - name: Smoke test macOS image
        if: runner.os == 'macOS'
        run: ./build/package/MyApp.app/Contents/MacOS/MyApp

      - name: Smoke test Windows image
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          $process = Start-Process -FilePath ".\\build\\package\\MyApp\\MyApp.exe" -Wait -PassThru -NoNewWindow
          if ($process.ExitCode -ne 0) {
            exit $process.ExitCode
          }

      - uses: actions/upload-artifact@v7
        with:
          name: myapp-image-${{ runner.os }}
          path: build/package/**
          if-no-files-found: error
```

The `package` job should be at the same level as `verify` under `jobs` in the workflow. If the release requires MSI/DEB/RPM/PKG/DMG, replace `--type app-image` with the appropriate format and install the prerequisites on the runner. Only publish after each OS's smoke test and signing gate pass.

Do not rebuild the JAR in the release job. Use the tested artifact, sign that exact binary, then store the signed JAR, checksum, and application image. This preserves the link between CI results and the released file.

## 9. Diagnosing JVMs in CI with jcmd and JFR

`jcmd` is used to send diagnostic commands to a JVM running on the same host, usually under the same effective user/group. It is useful when CI runs an integration service or a test JVM remains alive after a timeout.

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> Thread.print \
  > build/reports/diagnostics/thread-dump.txt
jcmd <PID> GC.heap_info \
  > build/reports/diagnostics/heap-info.txt
```

Not all test runners keep the JVM alive long enough to attach. If the process has already exited, `jcmd` cannot recover a thread dump. For test timeouts, you can configure Surefire/Failsafe to collect thread dumps or enable JFR from startup.

Record JFR during a smoke/integration run:

```bash
mkdir -p build/reports/diagnostics

java \
  -XX:StartFlightRecording=filename=build/reports/diagnostics/ci.jfr,settings=profile,dumponexit=true \
  -jar build/libs/myapp-1.0.0.jar

jfr summary build/reports/diagnostics/ci.jfr
```

`profile` collects more detail than `default` and may increase overhead. Only enable it on jobs that need to investigate performance or flaky tests. Thread dumps, heap dumps, and JFRs can contain sensitive data; restrict their access, retention, and upload.

When a job fails, save `jcmd -l`, application logs, test reports, and dumps if the target JVM is still running. Do not treat an empty `jcmd -l` output as proof that a JVM never ran; the runner/container namespace might differ and the process may have already exited.

## 10. Recording Provenance and Generating Checksums for Each Build

Each artifact should be accompanied by a report containing:

- Git commit SHA, tag, and working tree status.
- Gradle/Maven Wrapper version and distribution checksum.
- JDK distribution/vendor/version, build JVM, and compiler/test toolchain.
- Java release target, OS, architecture, and runner/container image.
- Build command, test results, and plugin/dependency lock state.
- JAR manifest, module/dependency report, Javadoc output.
- SHA-256 of the JAR, signed JAR, and native package.
- Certificate identity, timestamp, and signature verification result on release.

Example on Linux:

```bash
java --version
javac --version
./gradlew --version
./gradlew javaToolchains
git rev-parse HEAD
sha256sum build/libs/myapp-1.0.0.jar
```

On Windows PowerShell:

```powershell
java --version
javac --version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
git rev-parse HEAD
Get-FileHash .\\build\\libs\\myapp-1.0.0.jar -Algorithm SHA256
```

Store the report, JAR, Javadoc, test results, dependency analysis, checksum, and package image as CI artifacts. Do not dump all environment variables into the report because they may contain credentials. Only record whitelisted required metadata and redact sensitive values.

To improve reproducibility, pin the Wrapper, JDK distribution/version, plugin/dependency versions, locale/timezone, and output timestamp. Gradle archive tasks support reproducible file order/timestamps; Maven can use `project.build.outputTimestamp`. Caching is only a time optimization: a cache hit does not replace version pinning, dependency verification, or checksum checks.

## 11. Arranging Quality Gates by Pipeline Type

| Gate | Pull request | Nightly/scheduled | Tag/release |
| --- | --- | --- | --- |
| JDK/build tool version | Required | Required | Required |
| Compile, unit test, integration test | Required | Required | Required |
| Javadoc/DocLint | Required for library/API | Required | Required |
| jar --validate, javap, jdeps, jdeprscan | Required per policy | Required | Required |
| Multi-JDK/OS matrix | Baseline + supported JDKs | Wider matrix | Approved release matrix |
| jlink custom runtime | When modules change | Can run regularly | When releasing runtime image |
| jpackage native image/installer | Can skip | Can test-build | Required if distributing installer |
| keytool/jarsigner | Do not use release private key | Can check public certificate | Sign and verify using protected secret |
| jcmd/JFR profiling | Only when diagnostics needed | Useful for flaky/performance tests | Monitor smoke/soak tests |
| Checksum/provenance/upload | Store tests/reports | Store full reports | Store signed artifact, checksum, and provenance |

Do not expose signing secrets to pull requests from forks or untrusted code. Use a protected GitHub environment for releases, restrict token permissions, pin actions by commit SHA when policy requires, and only allow the release job to read keys/certificates.

## 12. Common CI Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Local pass, CI fail | Different JDK distribution/version, OS, or build tool | Compare toolchain reports and Wrapper |
| Unsupported class file major version | Compiler/runtime/plugin bytecode mismatch | Check build JVM, plugins, and JDK toolchain |
| javac reports missing API | `--release` does not match baseline | Check `options.release` or `maven.compiler.release` |
| Javadoc -Werror fail | Missing comment/tag, invalid link or HTML | Fix Javadoc; do not disable DocLint just to make the build green |
| jdeps reports missing dependency | Full runtime classpath/module path not provided | Pass resolved dependency path or module path |
| jdeps --jdk-internals detects internal API | Code depends on unstable JDK APIs | Replace with supported APIs or record a time-bound exception |
| jdeprscan reports deprecated API | Code uses API deprecated in the release target | Review migration plan and deprecation policy |
| jlink reports module not found | Missing module path/JMOD or wrong module name | Check `jdeps --print-module-deps` and `module-info` |
| jpackage missing WiX/OS tools | Runner lacks native package prerequisites | Install corresponding tools on the right OS runner |
| jpackage image fails to run | Wrong input, main class, runtime, or native dependency | Run launcher from app-image and save config/logs |
| jarsigner -verify -strict fail | Untrusted/expired certificate chain or signature error | Use proper certificate chain, timestamp, and check alias |
| Corrupted signature after verify | JAR was modified after signing | Finalize all changes before re-signing the final artifact |
| jcmd cannot find PID | JVM already exited or in a different namespace | Keep process alive, run on same host/user/container, and get right PID |
| Hash differs between two builds | Different timestamp, dependency, or generated metadata | Check reproducible build settings and toolchain provenance |

## 13. JDK Tooling CI Completion Checklist

1. Commit Gradle/Maven Wrapper and pin distribution/checksum.
2. Choose JDK vendor/version, Java release target, and support matrix.
3. Record build JVM, compiler JDK, test launcher, and production runtime separately.
4. Pin plugin/dependency versions; enable appropriate lock/verification.
5. Run compile, unit tests, and integration tests via the Wrapper.
6. Run `javadoc` with DocLint and fail-on-warning per policy.
7. Inspect the JAR with `jar --validate`, `jar --list`, and `javap`.
8. Analyze internal/deprecated APIs and module dependencies with `jdeps` and `jdeprscan`.
9. Create a runtime image with `jlink` when a modular app needs a custom runtime.
10. Create and smoke test the application image/installer with `jpackage` on the target OS.
11. Sign release artifacts only in a protected job; verify with `jarsigner -verify -strict`.
12. Inspect certificates/keystores with `keytool`; do not put private keys into the repository.
13. Collect `jcmd`/JFR when the test JVM is still running and diagnostics are needed.
14. Generate SHA-256 checksums, provenance report, and upload JAR/docs/test/package outputs.
15. Only publish artifacts that passed all gates and keep the exact tested binary.

## 14. Key Takeaways

- The Wrapper and JDK toolchain create a consistent build environment; `--release` defines the API/bytecode baseline.
- Gradle `check` or Maven `verify` is the backbone of compile/test; invoke Javadoc and JDK analysis explicitly if they are release gates.
- `jar`, `javap`, `jdeps`, and `jdeprscan` inspect artifacts and dependencies after building.
- `jlink` creates runtime images from modules; `jpackage` creates application images/installers per target OS.
- `keytool` manages/inspects certificates; `jarsigner` signs and verifies JARs.
- `jcmd`/JFR help investigate running JVMs; they do not replace test assertions.
- Pull requests must not access release signing keys. Sign the exact verified artifact, verify chain/timestamp, then generate checksums.
- CI artifacts must include the JAR, test reports, Javadoc, toolchain/provenance, dependency reports, and checksums.
- Do not run every tool in every job mechanically; only enable `jlink`, `jpackage`, signing, and diagnostics when product goals require them.

When CI connects the entire lifecycle from toolchain to artifact, teams can verify quality across multiple JDKs, package for the right platforms, sign the right binaries, and trace back the environment that produced each release.

## References

- [JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html)
- [The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [The javadoc Command and DocLint](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [The jdeps Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [The jlink Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [The jpackage Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html)
- [The jarsigner Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- [Gradle: Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle: Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Compiler Plugin: Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire](https://maven.apache.org/surefire/)
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
