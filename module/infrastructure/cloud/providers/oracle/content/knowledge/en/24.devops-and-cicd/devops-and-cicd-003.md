# Building, testing, and packaging Java applications

## Lesson objectives

In the **DevOps and CI/CD on OCI** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson builds a workflow that transforms Java source code into a tested, identifiable application package ready for deployment.

The workflow sits within an OCI tenancy with an appropriate compartment, IAM, and network access. The application can later run on Compute, Kubernetes, or use Oracle storage and databases; the build step itself focuses on producing a valid, verified artifact that carries no runtime environment secrets.

After this lesson, you will be able to:

- Distinguish compilation, unit testing, integration checking, packaging, and artifact publishing.
- Set up a Java 17/Maven project with consistent verification commands between a local workstation and OCI.
- Write unit tests and verify running the generated JAR file directly.
- Declare `build_spec.yaml` for OCI DevOps Managed Build.
- Produce a JAR, test reports, checksum, and traceability metadata.
- Identify toolchain errors, artifact path issues, IAM permission gaps, and dependency connectivity failures.

The example uses a small command-line application with no runtime dependencies and requires no Compute instance or database provisioning. All source files below are sample content for learners to create in their own application repository.

## 1. From commit to deployment-eligible artifact

A good build pipeline must answer four questions:

1. Which code was built?
2. Which JDK, tools, and dependencies were used?
3. Which checks actually ran, and what were the results?
4. Which file will be handed over for deployment?

~~~mermaid
flowchart LR
    A["Commit in Git"] --> B["OCI Managed Build fetches code"]
    B --> C["Verify JDK and Maven"]
    C --> D["Compile and unit test"]
    D --> E["Package JAR"]
    E --> F["Run check against JAR"]
    F --> G["Prepare artifact, reports, checksum"]
    G --> H["Deliver Artifacts"]
    H --> I["Artifact repo for deployment"]
    D --> J["Failure: do not promote package to deployment"]
    F --> J
~~~

Packaging and testing do not always follow a strict "finish all tests before creating the file" order. Unit tests usually run before packaging, whereas startup or integration checks may require the packaged file itself. What must be guaranteed is **only promoting artifacts to the publishing step when all mandatory checks have passed**.

| Activity | Inputs | Output | What it does not prove |
| --- | --- | --- | --- |
| Compilation | Java source and compile dependencies | Bytecode | Correct logic or that the app can start |
| Unit tests | Code units and test dependencies | Small-scope logic test results | IAM or Database connectivity on OCI |
| Packaging | Bytecode, resources, and packaging config | JAR/WAR or other format | That the file has everything needed to run |
| Package check | Newly packaged file | Evidence of running that package | Production workload readiness |
| Artifact publish | Package that passed checks | Version stored in repository | That the workload is deployed |
| Deployment | Artifact and environment config | Running application version | That all business requirements are met |

Do not treat a "green" pipeline as a substitute for checking test types, test counts, and the actual artifacts produced.

## 2. Selecting the toolchain and build lifecycle

### 2.1. Aligning build JDK and runtime

Example choices:

| Component | Illustrative choice |
| --- | --- |
| Language and bytecode | Java 17 |
| JDK running Maven | JDK 17 |
| Build tool | Maven 3.9.x |
| Test framework | JUnit Jupiter 5.13.1 |
| Unit test runner | Maven Surefire 3.5.3 |
| Integration test runner | Maven Failsafe 3.5.3 |
| Output package | Executable JAR, no external runtime dependencies |

This is a concrete version set for the example, not a list of the latest releases. Real projects must keep versions updated per the team's dependency management process.

OCI provides Managed Build environments with preinstalled JDK and build tools; versions may change. Always consult [Build Runner Runtime Details](https://docs.oracle.com/en-us/iaas/Content/devops/using/runtime_details.htm) and record `java -version`, `javac -version`, and `mvn -version` in logs.

Choose the **Oracle Linux 8** build runner for this lesson. Oracle has announced the end of support for the Oracle Linux 7 build runner; do not copy OL7 configurations from older examples. See [Service Change Announcements](https://docs.oracle.com/en-us/iaas/Content/servicechanges.htm).

`JAVA_HOME` affects which JDK Maven uses; the `java` binary on `PATH` might point elsewhere. Read `mvn -version` to see Maven's actual JDK rather than relying only on what an IDE shows.

The property `maven.compiler.release=17` instructs compilation targeting Java 17. It neither installs a JDK nor enables JDK 11 to compile code requiring Java 17. A package compiled for Java 17 needs a compatible runtime; JRE 11 can throw `UnsupportedClassVersionError`.

### 2.2. Key Maven phases

| Command/phase | Scope |
| --- | --- |
| `mvn compile` | Compiles main source code |
| `mvn test` | Runs through the unit test phase |
| `mvn package` | Runs prior phases and packages |
| `mvn verify` | Runs through checks in the verify phase, including integration tests when configured |
| `mvn install` | Installs the artifact into the local Maven repository |
| `mvn deploy` | Publishes the artifact to the configured remote Maven repository |
| `mvn clean verify` | Cleans old build outputs and runs through verify |

`mvn deploy` does not mean deploying the application to OCI Compute or Kubernetes. Furthermore, invoking `verify` does not automatically generate integration tests unless the corresponding plugin and tests are configured. See [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle).

Primary command for this lesson:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify
~~~

There is no need to run `compile`, `test`, `package`, and `verify` separately because later phases include earlier ones. Repeated runs waste time and make it harder for log readers to tell which test run belongs to which artifact.

## 3. Sample application repository

Project layout:

~~~text
oci-java-demo/
├── pom.xml
├── build_spec.yaml
├── .gitignore
└── src/
    ├── main/
    │   └── java/
    │       └── vn/example/ocijava/
    │           ├── GreetingService.java
    │           └── Main.java
    └── test/
        └── java/
            └── vn/example/ocijava/
                ├── GreetingServiceTest.java
                └── PackagedAppIT.java
~~~

`target/` is generated by Maven; `dist/` will hold the bundle exported by the pipeline. Do not commit either directory.

`.gitignore`:

~~~gitignore
target/
dist/
.idea/
*.iml
.env
.env.*
*.pem
*.key
settings-private.xml
~~~

Dependencies, plugins, and tests are declared in the POM. Credentials for accessing private repositories must never be embedded in the POM or committed with code.

### 3.1. Application code

`src/main/java/vn/example/ocijava/GreetingService.java`:

~~~java
package vn.example.ocijava;

public final class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
~~~

`src/main/java/vn/example/ocijava/Main.java`:

~~~java
package vn.example.ocijava;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "OCI" : args[0];
        System.out.println(new GreetingService().greet(name));
    }
}
~~~

Do not add OCI service connections to this example just to prove a build works. A unit test verifying greeting formatting does not need Object Storage read permissions, a VCN, or database passwords.

### 3.2. POM with explicit plugin and test versions

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>oci-java-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.13.1</junit.version>
        <test.plugins.version>3.5.3</test.plugins.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <finalName>oci-java-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>check-toolchain</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${test.plugins.version}</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.ocijava.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>${test.plugins.version}</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <app.jar>${project.build.directory}/${project.build.finalName}.jar</app.jar>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Key points to understand:

- Enforcer catches wrong JDK or Maven versions right in the `validate` phase. The `[17,18)` range accepts only JDK 17 in this example; if the project upgrades JDKs, update the rule intentionally.
- JUnit has `test` scope so it does not become an application runtime dependency.
- Surefire runs unit tests. Failsafe is bound to `integration-test` and `verify` to run tests after the JAR exists and determine the build outcome.
- `failIfNoTests=true` prevents false success when no tests are discovered in a mandatory test suite.
- `finalName` fixes the file path to `target/oci-java-demo.jar`; it does not alter the Maven coordinates `vn.example:oci-java-demo:1.0.0`.
- The manifest declares `Main-Class` so `java -jar` can be used.

Configuring JUnit with Surefire/Failsafe is documented in [JUnit 5 User Guide](https://docs.junit.org/5.13.1/user-guide/index.html). Tool version constraints follow [Enforcer Version Ranges](https://maven.apache.org/enforcer/enforcer-rules/versionRanges.html), and the JAR entry point follows [Maven Archiver: Make The Jar Executable](https://maven.apache.org/components/shared/maven-archiver/examples/classpath.html).

This package runs standalone because the main code only uses Java SE. Adding `Main-Class` does not automatically bundle external libraries into the JAR. If you later add a JDBC driver, HTTP client, or framework, select an appropriate dependency distribution strategy.

## 4. Writing tests for logic and the packaged artifact

### 4.1. Unit tests independent of OCI infrastructure

`src/test/java/vn/example/ocijava/GreetingServiceTest.java`:

~~~java
package vn.example.ocijava;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void stripsWhitespaceFromName() {
        assertEquals("Hello, OCI!", service.greet("  OCI  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class, () -> service.greet(" "));
    }
}
~~~

Both tests verify specific behavior: normalizing names and rejecting blank inputs. They do not test whether the pipeline can read credentials, nor do they need to call OCI APIs.

Class names end in `Test` so Surefire detects them by convention. When there are multiple modules, define which modules require tests; do not mechanically apply a "fail if no tests" rule to modules containing only documentation or static resources.

### 4.2. Testing execution of the JAR file itself

`src/test/java/vn/example/ocijava/PackagedAppIT.java`:

~~~java
package vn.example.ocijava;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PackagedAppIT {
    @Test
    void startsPackagedApplication() throws Exception {
        Path jar = Path.of(System.getProperty("app.jar"));
        assertTrue(Files.isRegularFile(jar), "Packaged JAR must exist");

        boolean windows = System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win");
        String executable = windows ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", executable);

        Process process = new ProcessBuilder(
                java.toString(), "-jar", jar.toString(), "OCI")
                .redirectErrorStream(true)
                .start();

        try {
            assertTrue(process.waitFor(10, TimeUnit.SECONDS),
                    "Application did not exit in time");

            String output = new String(
                    process.getInputStream().readAllBytes(),
                    StandardCharsets.UTF_8).strip();

            assertEquals(0, process.exitValue(), output);
            assertEquals("Hello, OCI!", output);
        } finally {
            process.destroyForcibly();
        }
    }
}
~~~

This test can catch a missing JAR, missing entry point, startup failure, or wrong output. `ProcessBuilder` takes individual arguments so it does not depend on how a shell handles spaces in paths.

The name `PackagedAppIT` matches Failsafe's `*IT` convention. Reference on naming conventions: [Failsafe Test Inclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html).

Because the sample app prints only one line, waiting for the process and then reading output works for this example. For services that emit heavy logs or run continuously, read output concurrently, perform readiness checks, and actively terminate the process; do not copy this CLI test verbatim for a web server.

This tests the packaged application in a separate process; it is not yet an integration test against Oracle Database, Object Storage, or other OCI services. When adding such tests, prepare dedicated test resources, timeouts, IAM permissions, and cleanup mechanisms.

### 4.3. Running and reading results

From the directory containing the POM:

~~~bash
java -version
javac -version
mvn -version
mvn --batch-mode --no-transfer-progress clean verify
java -jar target/oci-java-demo.jar OCI
~~~

Expected application run output:

~~~text
Hello, OCI!
~~~

With the exact sample code, expect two unit tests and one packaged-app test to execute, with none skipped. Reports are located at:

~~~text
target/
├── oci-java-demo.jar
├── surefire-reports/
└── failsafe-reports/
~~~

Do not only look for `BUILD SUCCESS`. Inspect test counts, errors, failures, and skips in both report sets. Failsafe evaluates the outcome during `verify`; therefore, use `mvn verify` rather than stopping at `mvn integration-test`. See [Failsafe verify goal](https://maven.apache.org/components/surefire/maven-failsafe-plugin/verify-mojo.html).

Flags such as `-DskipTests`, `-Dmaven.test.skip=true`, or `-DskipITs` skip different layers of checks. They do not belong in the release command of this lesson. Do not add skip flags just to make a pipeline pass.

## 5. Choosing the right package type

| Package type | Fits when | What to check |
| --- | --- | --- |
| Standard JAR with entry point | Small application, or dependencies distributed separately | `Main-Class` and classpath |
| Fat/uber JAR | Want to bundle runtime dependencies | Resource collisions, service loaders, licenses, and merge rules |
| Framework executable JAR | Framework has its own packaging mechanism | Repackage/boot task plugin and the exact file to run |
| WAR | Deploying to an appropriate application server | Java/Jakarta APIs and server version |
| Container image | Distributing application together with runtime environment | Base image, JRE, architecture, user, and image digest |
| Native executable | Strict startup/resource requirements | Native toolchain, dynamic libraries, and target platform |

Renaming a file extension to `.jar` does not create a valid Java archive. Placing a JAR into an image also does not turn a JAR missing dependencies into a runnable package.

For framework-based applications, do not blindly copy `target/*.jar`: the directory may contain a regular JAR, executable JAR, sources JAR, or `original` artifact. Identify the exact artifact produced by the plugin and test that exact file.

The current example only publishes `target/oci-java-demo.jar`. JUnit is a test dependency and does not need to be carried into the runtime artifact.

## 6. Build specification for OCI DevOps

### 6.1. Role of the build spec

`build_spec.yaml` describes commands executed on the build runner; the POM describes how to build the Java project. Keeping Java build logic in the POM lets local workstations and CI use the same command.

The build spec below sits at the root of the primary source. It has three steps: inspect the toolchain, run `clean verify`, and prepare the artifact bundle. `outputArtifacts` declares four concrete files for downstream stages.

~~~yaml
version: 0.1
component: build
timeoutInSeconds: 1800
shell: bash
failImmediatelyOnError: true

steps:
  - type: Command
    name: Inspect toolchain
    timeoutInSeconds: 120
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      test -f pom.xml
      java -version
      javac -version
      mvn -version

  - type: Command
    name: Compile test package and verify
    timeoutInSeconds: 1200
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      mvn --batch-mode --no-transfer-progress clean verify
    onFailure:
      - type: Command
        timeoutInSeconds: 60
        command: |
          cd "${OCI_PRIMARY_SOURCE_DIR}"
          printf '%s\n' 'Maven failed; inspect test output and available reports.'
          find target/surefire-reports target/failsafe-reports             -maxdepth 1 -type f -name '*.txt' -print 2>/dev/null || true

  - type: Command
    name: Prepare verified artifacts
    timeoutInSeconds: 180
    command: |
      set -euo pipefail
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      test -s target/oci-java-demo.jar
      : "${OCI_PRIMARY_SOURCE_COMMIT_HASH:?Missing primary source commit}"
      : "${OCI_BUILD_RUN_ID:?Missing build run identifier}"
      mkdir -p dist
      cp target/oci-java-demo.jar dist/app.jar
      tar -czf dist/test-reports.tar.gz         -C target surefire-reports failsafe-reports
      (
        cd dist
        sha256sum app.jar > app.jar.sha256
      )
      printf 'sourceCommit=%s\nbuildRunId=%s\njavaRelease=17\napplicationVersion=1.0.0\n'         "${OCI_PRIMARY_SOURCE_COMMIT_HASH}"         "${OCI_BUILD_RUN_ID}" > dist/build-metadata.properties

outputArtifacts:
  - name: java-app
    type: BINARY
    location: dist/app.jar

  - name: java-app-checksum
    type: BINARY
    location: dist/app.jar.sha256

  - name: java-test-reports
    type: BINARY
    location: dist/test-reports.tar.gz

  - name: java-build-metadata
    type: BINARY
    location: dist/build-metadata.properties
~~~

Syntax, built-in variables, and output declarations follow [OCI DevOps Build Specification](https://docs.oracle.com/en-us/iaas/Content/devops/using/build_specs.htm). Step names and Maven commands in the example are this lesson's design.

### 6.2. Details that ensure meaningful results

- `set -euo pipefail` makes Bash stop on command failure, unset variables, or failures inside a shell pipeline.
- Each step explicitly runs `cd` into `OCI_PRIMARY_SOURCE_DIR`, without relying on working directory state left over from the previous step.
- `clean verify` must succeed before copying the JAR into `dist`.
- `test -s` verifies that the file to be exported exists and is non-empty.
- `java-app` is the logical name referenced by downstream stages; `dist/app.jar` is the local file path.
- SHA-256 is computed on the exact JAR copy being published.
- Metadata records the commit of the **primary source**, avoiding grabbing the commit of a repository that only fired a trigger.
- Test reports are archived into a single file for clean export.

`|| true` appears only in the failure-handler command listing reports so that a missing report directory does not obscure diagnostics. Never place it after Maven or publishing commands.

Renaming `oci-java-demo.jar` to `app.jar` only copies bytes; it does not rebuild. Do not use file renaming as a versioning mechanism.

Four files in `dist`:

~~~text
dist/
├── app.jar
├── app.jar.sha256
├── test-reports.tar.gz
└── build-metadata.properties
~~~

If Maven fails, the artifact preparation step does not run. Do not expect the success path's report bundle to appear on a failed build; inspect Maven logs and design separate failure-report retention if your team requires it.

### 6.3. Build spec not at repository root

If the application lives under `services/greeting`, synchronize three places:

| Configuration spot | Example adjustment |
| --- | --- |
| Build spec path in Managed Build | `services/greeting/build_spec.yaml` |
| Command execution directory | `cd "${OCI_PRIMARY_SOURCE_DIR}/services/greeting"` |
| Output path relative to primary source | `services/greeting/dist/app.jar` |

Moving the build spec location does not automatically make paths inside the file relative to the new location. With multiple build sources, designate which source is primary; do not pick a directory by guessing the repository name.

## 7. Moving the project onto OCI Managed Build

### 7.1. Preparing the project, source, and logs

Prepare in the lab region and compartment:

1. An OCI DevOps project with build logging configured to monitor runs.
2. A repository containing the POM, Java code, tests, and `build_spec.yaml`.
3. A build pipeline with a Managed Build stage.
4. Permissions for operators and the pipeline identity.
5. Network connectivity to download dependencies/plugins.
6. An Artifact Registry repository if storing packages after build.

You can use OCI Code Repository or a service-supported Git provider. If using an external repository, configure an external connection and corresponding credentials; do not substitute Resource Manager's configuration source provider for an OCI DevOps external connection. Those are two integrations belonging to different services.

In the Managed Build stage, select the build source and primary source, build spec path, Oracle Linux 8 image, and appropriate runner resource shape. With the sample layout, both the POM and build spec sit at the root of the primary source. Adding the stage is described in [Adding a Managed Build Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/add_buildstage.htm).

The first run should be triggered manually against a specific branch/commit to verify the configuration. Automatic triggers are a separate setup; creating a pipeline does not mean every commit automatically starts a build. Enable triggers only after the manual flow works properly.

### 7.2. Separating human permissions and pipeline permissions

| Identity | Permissions serving its role |
| --- | --- |
| DevOps configurator | Manage projects, pipelines, stages, and source connections within assigned scope |
| Build pipeline via resource principal | Read OCI repositories or needed sources, access OCI services during build steps |
| Artifact-publishing pipeline | Write to the exact target artifact repository |
| Pipeline needing secrets | Read specific Vault secrets per policy |
| Deployed application | Separate runtime permissions to Object Storage, Database, or other services |

Console login permissions of a human user are not automatically inherited intact by the build runner. OCI describes using dynamic groups and IAM policies for pipelines in [DevOps Policies](https://docs.oracle.com/en-us/iaas/Content/devops/using/devops_iampolicies.htm). Scope permissions by compartment and resource; avoid granting tenancy-wide access just to test a build.

The sample app calls no OCI services, so the compile/test step needs no permissions to manage Compute, VCN, or Database. Only if the pipeline publishes packages does it need appropriate permissions on the target repository.

Do not place OCI API signing keys into images or the POM to run CLI commands in a build. When a build step needs to call OCI services, use the authorized service identity and verify its scope.

### 7.3. Dependency download networking is a build prerequisite

Maven must reach repositories hosting both application dependencies and Maven plugins. This may require:

- DNS capable of resolving repository hostnames.
- Routing and egress compatible with the runner configuration.
- Corporate proxies/mirrors and valid TLS trust.
- Credentials for private dependency repositories.
- Private network access if integration tests call services in a VCN.

A Service Gateway serves supported OCI services; it does not automatically provide access to every Maven repository on the Internet. If using a runner with private network access, design egress or mirrors according to your network architecture.

Plugin download failures occurring before Java compilation can also be caused by DNS, proxy, certificate, or authentication issues. Do not randomly edit the POM when logs clearly indicate a connectivity error.

Private repository credentials should come from a secret management system and be passed to Maven via a protected configuration. Never print the full `settings.xml` or environment variables to logs. When integration tests use Oracle Database, never use production credentials for pull request builds.

## 8. From build outputs to durably stored artifacts

### 8.1. Output artifacts are not yet a release repository

`outputArtifacts` passes results to the next stage within a build run. To persist and consume them after the build, add **Deliver Artifacts** with the right destination repository:

| Product | Destination repository |
| --- | --- |
| JAR, ZIP, reports, or metadata files | OCI Artifact Registry, generic artifact |
| Container image | OCI Container Registry |
| Maven module resolved by coordinates in other projects | Configured Maven-compatible remote repository |

Do not assume a generic artifact repository is a Maven endpoint for `mvn deploy`. Uploading a single JAR file and providing a Maven repository structure are two different requirements.

For this example, create a DevOps artifact reference pointing to the location in Artifact Registry, then add Deliver Artifacts after Managed Build. The **Build config/result Artifact name** must match `java-app` in the build spec; do not enter `dist/app.jar` into that logical name field.

If you want to keep checksums, reports, and metadata under the same version, configure separate mappings for `java-app-checksum`, `java-test-reports`, and `java-build-metadata`. Creating and mapping are documented in [Adding a Deliver Artifacts Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/add_deliverartifact.htm).

### 8.2. Artifact version and identity

Separate three distinct values:

| Value | Example | Purpose |
| --- | --- | --- |
| Version in POM | `1.0.0` | Application/Maven version |
| Version stored in repository | `1.0.0-gabc123def456-b42` | Identifies a single release |
| File SHA-256 | Hex digest of the JAR | Verifies actual bytes |

In the repository version example, `g...` represents an abbreviated commit and `b42` is a team-defined build number; these are not built-in variables to copy literally into the Console.

Teams need non-colliding versioning rules and parameter substitution when automating releases. OCI allows configuring artifact versions via pipeline parameters or exported variables; that must be declared and mapped explicitly. See [Configuring Delivered Artifact Version](https://docs.oracle.com/en-us/iaas/Content/devops/using/deliverartifact-stage.htm).

The lesson's build spec intentionally keeps file paths stable; **it does not yet auto-generate release repository versions**. During the lab, pick a distinct repository version for each Deliver run and record its link to the build run. Never rely on a single `latest` label as the sole identifier for a deployable package.

### 8.3. Verifying integrity after retrieving the package

After downloading the JAR and checksum from the same repository version, on Linux you can verify:

~~~bash
sha256sum --check app.jar.sha256
java -jar app.jar OCI
~~~

The checksum file was created relative to `app.jar`, so run the command inside the directory containing both files.

A checksum detects byte corruption during transfer or selecting the wrong package; it does not by itself prove the publisher is trustworthy. If origin authentication is required, add artifact signing and govern where signatures/metadata are stored per team policy.

Promote the exact verified artifact from dev to test and production. Swap runtime configuration appropriate to each environment instead of rebuilding the same commit per environment and treating the resulting binaries as identical.

## 9. Controlling quality, duration, and cost

### 9.1. Additional quality gates to add as needed

| Check | What it catches | Limitation |
| --- | --- | --- |
| Unit tests | Logic errors in small scopes | May miss interactions with external services |
| Packaged JAR run test | Wrong entry point, missing startup components | Does not test full business workflows |
| Integration tests with external systems | Wrong queries, protocols, connection configs | Needs test environments and resource cleanup |
| Static analysis/formatting | Code rule violations and common bugs | Does not replace behavioral testing |
| Coverage gate | Portions of code exercised by tests | High coverage does not guarantee strong assertions |
| Dependency/vulnerability scan | Dependencies with known issues | Needs vulnerability databases and triage rules |
| SBOM and metadata | Package components and provenance | Does not automatically block running defective packages |

Additional gates must be configured as checks with clear failure criteria. Do not claim the sample lesson performs vulnerability scanning, coverage enforcement, or SBOM generation: the current POM and build spec only perform compilation, unit tests, JAR verification, and artifact preparation.

For Java services using Oracle Database, integration tests must verify the right driver version, schema migrations, and access contracts. Dedicate a separate test compartment or environment, inject secrets from an appropriate secret manager, set timeouts, and clean up resources even when tests fail.

### 9.2. Caching speeds up builds but is not a source of truth

Maven downloads dependencies into a local repository; a fresh runner may not have that cache. Never assume `~/.m2` from a previous build run still exists on the next run.

If the team implements caching or a repository mirror:

- Key caches by relevant toolchain and dependency configuration.
- Separate credential-bearing data from shared cache data.
- Test builds from a clean environment on a team-defined cadence.
- Avoid depending on artifacts that exist only on a single developer's workstation.

`clean` deletes project build outputs, not the entire Maven local repository. Therefore, "ran clean" does not mean all dependencies were freshly downloaded.

### 9.3. Runner sizing, timeouts, and test resources

Start with a runner shape sufficient for a small application, measure per-step duration, and only then increase CPU/RAM. Insufficient memory can cause the OS to kill the JVM or test processes; increasing timeouts will not fix that root cause.

Oracle describes billing based on runner compute resources during build execution in [Managed Build Stage](https://docs.oracle.com/en-us/iaas/Content/devops/using/managed_buildstage.htm). Actual costs also depend on configuration and services used; do not infer from a successful build that the entire lab is free.

For large projects, consider running independent tests in parallel once sufficient resources are measured. Avoid setting Maven thread counts or test fork counts too high on small runners. Set timeouts for tests, build steps, and the overall stage according to the workload.

A build failing after provisioning a test database can leave ongoing costs behind without cleanup. Conversely, tearing down a shared test environment when one build finishes can break other running builds. Resource ownership and lifecycles must be explicit.

Production availability must be validated in deployment design, health checks, and rollout/rollback strategies. The build step contributes a reliable artifact; it does not create workload redundancy by itself.

## 10. Troubleshooting common errors

| Symptom | Cause to investigate | Remediation |
| --- | --- | --- |
| Enforcer reports wrong Java/Maven | `JAVA_HOME`, `PATH`, or runner image differs from expected | Check `mvn -version` and select the right toolchain |
| `release version 17 not supported` | Compiler JDK is too old | Use a JDK supporting the chosen release level |
| `UnsupportedClassVersionError` at runtime | Runtime is older than bytecode | Align bytecode target and runtime version |
| Build succeeds but no tests run | Class naming, test engine, plugin, or skip flags | Check configuration and actual test reports |
| `no main manifest attribute` | Entry point not declared or wrong JAR selected | Inspect manifest and selected artifact file |
| `ClassNotFoundException`/`NoClassDefFoundError` | Missing runtime dependency or wrong classpath | Check packaging strategy and dependency scopes |
| Dependency/plugin download fails | DNS, proxy, TLS, mirror, or credentials | Check network path and repository permissions |
| Output artifact not found | Wrong path, filename, or build did not produce package | Compare file location against `outputArtifacts.location` |
| Managed Build passes but Deliver fails | Logical name mismatch, IAM, or wrong destination repo | Check mapping and pipeline identity permissions |
| `Permission denied` on wrapper | Missing executable bit or CRLF line endings | Fix permissions/file in Git and use LF for Linux scripts |
| JVM/test process killed | Out of memory or too many concurrent processes | Check logs and reduce parallelism or resize runner |
| Integration test hangs | Missing timeout, dependent service not ready | Add readiness checks, timeouts, and cleanup |

If using Maven Wrapper, commit the necessary wrapper files, pin the distribution, and review the download URL. On Linux use `./mvnw`; on Windows use `mvnw.cmd`. If replacing preinstalled Maven with the wrapper in a pipeline, verify the executable bit, line endings, and distribution reachability first.

With Gradle, keep the same principles: specify the toolchain explicitly, ensure tests actually execute, and choose the right packaging task. `./gradlew clean build` typically includes checks wired into `check`, whereas custom integration test tasks run only when configured; `jar`, `bootJar`, and `war` do not automatically produce the same kind of output. Never switch build tools just to bypass test failures.

## 11. Lab completion criteria

A complete lab has the following evidence:

- The repository contains the POM, source code, tests, and build spec; no credentials or local outputs are committed.
- Logs confirm the required JDK and Maven versions.
- Two unit tests and one JAR execution test pass with none skipped.
- `target/oci-java-demo.jar` runs via `java -jar`.
- Managed Build prepares artifacts only after `clean verify` passes.
- The output JAR, checksum, test reports, and metadata correspond to the build run.
- If Deliver Artifacts is configured, the package is stored under a specific version and can be downloaded and verified.
- Intentionally break an assertion on a lab branch to verify the build fails and does not proceed to publishing; then revert the code.
- Auxiliary integration-test resources are cleaned up, and artifacts/logs are retained per team retention windows.

This lab does not require deploying the application to Compute or provisioning a Database. If you added those resources as an extension, verify ownership before cleaning them up; keep artifacts still needed for verification or rollback.

The required outcome is a clear chain of evidence: **identified commit → identified toolchain → passing checks → identified artifact**. That serves as the input for subsequent CI/CD steps to deploy the Java application on OCI in a controlled way.
