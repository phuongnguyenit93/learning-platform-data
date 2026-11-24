# Comparing Dependency Graphs, Artifact Contents, and Test Results After a Spring Boot Upgrade

## 1. Goal: Proving What the Upgrade Changed

Within **Tooling Upgrades**, this lesson explains how to compare a Spring Boot application before and after upgrading Spring Boot, the JDK, Maven/Gradle plugins, or the dependency platform. An upgrade might edit only one version in a build file yet alter many transitive dependencies, executable JAR contents, the manifest, runtime behavior, and test results.

Do not conclude an upgrade succeeded merely because the build command exited with code 0. Collect and cross-check three independent categories of evidence:

1. **Dependency graph:** which libraries are resolved, which versions are selected, which scopes/configurations use them, and why those versions were picked.
2. **Artifact contents:** which classes, resources, nested libraries, metadata, and manifest entries the final JAR/WAR actually contains.
3. **Test results:** which tests ran, pass/fail/error/skipped counts, integration tests, smoke tests, and post-upgrade runtime errors.

The goal is not to make two builds byte-for-byte identical. When versions change, dependency JARs and some metadata naturally change. The goal is to explain every difference, confirm expected changes, catch unintended changes, and prove the application still satisfies its operational contract.

**Illustrative version set:** Java 17, Spring Boot 3.3.5, Maven 3.9.x or Gradle 8.5. This is a fixed version set for consistent examples; the same comparison process applies to other versions.

## 2. Three Evidence Layers That Must Be Compared Separately

| Evidence Category | Questions to Answer | Common Tools | Saved Output |
| --- | --- | --- | --- |
| **Dependency graph** | Which direct/transitive dependencies are selected? Are there evictions, conflicts, overrides, or scope changes? | Maven `dependency:tree`/`effective-pom`; Gradle `dependencies`/`dependencyInsight` | JSON/text graph, effective POM, lockfile |
| **Artifact contents** | Does the archive contain the right classes, resources, launcher, manifest, and runtime libraries? | `jar tf`, `unzip`, `javap`, checksum | Entry list, nested library list, manifest, SHA-256 |
| **Test results** | Which test suites actually ran? Did failures/errors/skips change? Does the app start and pass smoke tests? | Surefire/Failsafe, Gradle Test, JUnit XML, smoke test | XML/HTML reports, logs, summary |

The three layers are related but do not substitute for one another:

- The dependency graph shows **what the build tool resolved**.
- Artifact inspection shows **what was packaged into the file**.
- Test results show **what behavior was verified**.

For instance, the dependency graph may contain a test-scoped dependency that is not packaged into the executable JAR. Conversely, a JAR may lack a library due to packaging/exclusions even though the runtime dependency graph looks right. Passing tests also do not prove every dependency was packaged properly if tests never hit that code path.

## 3. Understanding the Impact of the Spring Boot BOM Before Comparing

Spring Boot provides a curated set of dependency versions managed and tested together with each release via the **spring-boot-dependencies** BOM. When upgrading Spring Boot, many Spring and third-party dependencies upgrade in lockstep, even when direct dependency declarations in the project do not change.

This produces two types of changes:

- **Direct changes:** the team edits the version of Spring Boot, a plugin, the JDK, or a specific dependency.
- **Transitive/managed changes:** the BOM or resolution rules select new versions for dependencies the project does not declare directly.

For example, a project declares **spring-boot-starter-web** without specifying versions for **spring-web**, **spring-core**, Jackson, or Tomcat. Those library versions are managed by Spring Boot's dependency management. Upgrading the BOM can change the dependency graph accordingly.

### 3.1. Do Not Override Versions Without Understanding the BOM

A direct override can push a dependency out of alignment with the version set tested by Spring Boot. Only override when there is a clear rationale such as a security fix, compatibility requirement, or verified bug; document the reason and corresponding tests.

In Maven, check `dependencyManagement`, properties, and the effective POM. In Gradle, check `platform`/BOM, constraints, resolution rules, and `dependencyInsight`.

### 3.2. Distinguish Plugin Versions from Library Versions

These versions can be independent:

- Spring Boot application/BOM version.
- Spring Boot Maven Plugin or Gradle Plugin version.
- Maven/Gradle wrapper version.
- JDK distribution/version.
- Analysis, test, coverage, packaging, and security scanning plugins.

Upgrading multiple groups simultaneously makes it hard to pinpoint the cause of a regression. When possible, split into separate steps: upgrade the JDK, upgrade the build tool, upgrade Spring Boot/BOM, then upgrade auxiliary plugins.

## 4. Setting Up a Fair Before/After Comparison

### 4.1. Pick Two Traceable Revisions

Create two revisions:

- **Before:** stable commit prior to the upgrade.
- **After:** commit containing only the upgrade change under evaluation.

Ideally use two Git worktrees or two separate checkouts so outputs do not overwrite each other. Example:

~~~bash
git worktree add ../catalog-before COMMIT_BEFORE_UPGRADE
git worktree add ../catalog-after COMMIT_AFTER_UPGRADE
~~~

Replace the two sample commit names with real repository SHAs. If you prefer not to create worktrees, use two separate branches/checkouts and copy evidence to an independent directory before running `clean`.

### 4.2. Hold Out-of-Scope Conditions Constant

For a meaningful comparison, pin or record:

- The same application source commit, except for the build/version changes being evaluated.
- The same JDK major version and distribution; if upgrading the JDK, track that as an independent variable.
- The same Maven/Gradle commands, profiles, properties, and test filters.
- The same OS/architecture when native dependencies or platform-specific resolution matter.
- The same repository mirrors, credentials policy, and artifact sources.
- The same test environment, database/schema, service containers, and environment variables.
- The same dependency locking/verification rules.
- The same executable JAR/WAR creation method and classifier.

Do not pass **-DskipTests**, **-Dmaven.test.skip=true**, **-x test**, or a test-skipping profile on one side and compare directly against the other. Do not arbitrarily add **-U** to one Maven run because it forces snapshot/repository metadata updates and can unintentionally alter the dependency graph.

### 4.3. Record Each Build's Environment

Linux/macOS:

~~~bash
git rev-parse HEAD
java -version
./mvnw --version
./gradlew --version
~~~

Run only the wrapper command matching the project's build system. Save stdout/stderr alongside that revision's evidence.

Also record:

- Commit SHA and branch/tag.
- Spring Boot/BOM version.
- Maven/Gradle wrapper and plugin versions.
- JDK vendor, version, and architecture.
- Build profiles/tasks/flags.
- Test results.
- Artifact filename and SHA-256.

**If upgrading Java 17 to Java 21 alongside Spring Boot**, treat this as a multi-variable upgrade. When a regression occurs, build an intermediate revision changing only one variable to isolate the cause.

## 5. Maven: Capturing the Effective POM and Dependency Graph

Maven offers two key views:

- **Effective POM:** the merged result of parent POM, properties, dependency management, plugin management, and active profiles.
- **Dependency tree:** the dependency graph resolved by Maven for the built module, including direct and transitive relationships.

### 5.1. Effective POM

Command:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

**-Dverbose** adds comments pointing to the source of elements in the effective POM. This file helps identify:

- The Spring Boot parent/BOM version being applied.
- Managed dependency versions.
- Properties overriding versions.
- Active profiles.
- Maven plugin versions/configurations.
- The Spring Boot `repackage` execution.
- Inherited exclusions, scopes, and plugin configurations.

If the project is multi-module and `app` depends on local modules, build the reactor according to the project workflow first; the effective POM should be captured for the actual application module being packaged. Do not inspect only the root aggregator and assume the app's effective configuration is identical.

### 5.2. Dependency Tree in JSON Format

Using Maven Dependency Plugin version 3.11.0 in the example:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

JSON output is supported from Maven Dependency Plugin 3.7.0 onward. **-Dverbose** includes nodes omitted due to conflict mediation; this information is useful when investigating why a version was selected.

For a multi-module project depending on other reactor modules, run from the root and include required modules:

~~~bash
./mvnw -pl app -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

**-pl app** selects the application module, and **-am** builds required reactor modules. If the module name or path differs, substitute your project's selector. Check whether the output was written under `app/target/` or the module's target directory per your working directory.

### 5.3. Distinguishing the Full Graph from the Runtime Graph

The full graph exposes all scopes; the runtime graph focuses on dependencies that can participate at runtime:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependency-tree.txt
~~~

You can additionally capture compile/test graphs depending on the investigation goal, but use identical parameters before and after. Do not compare a default graph from one revision with a runtime-only graph from the other.

### 5.4. Reading Maven Output

Illustrative output structure:

~~~text
com.example:catalog-app:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:...
|  +- org.springframework:spring-web:jar:...
|  \- com.fasterxml.jackson.core:jackson-databind:jar:...
\- org.springframework.boot:spring-boot-starter-test:jar:...:test
~~~

Items to compare:

- Direct dependencies added or removed.
- Transitive dependencies appearing or disappearing.
- Selected versions changing.
- Dependencies omitted due to conflicts.
- Scope changes among compile/runtime/test/provided.
- Exclusions or optional dependencies altering branches.
- Dependency versions overridden relative to the Boot BOM.
- Multiple versions of the same artifact appearing across different modules.

Maven uses dependency mediation to choose a version when multiple paths request the same artifact. Verbose lines like **omitted for conflict with ...** explain dropped versions; do not treat every omitted node as an error. Verify whether the chosen version is appropriate and backed by regression tests.

### 5.5. Investigating a Specific Dependency

For example, investigating Jackson:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Change `includes` to the `groupId`/`artifactId` you want to check. You can run the same command for Spring Framework, Tomcat, Logback, Netty, Hibernate, or internal libraries.

### 5.6. Maven dependency:analyze Is Only Supplementary Evidence

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

This goal finds dependencies declared yet unused, or used yet undeclared, based on bytecode analysis. It can produce false positives for reflection, annotation scanning, `ServiceLoader`, Spring auto-configuration, or indirectly invoked code. Use it for investigation, not to automatically delete dependencies just because the analyzer reports them unused.

## 6. Gradle: Capturing the Dependency Graph and Selection Reasons

Gradle provides the **dependencies** task to inspect the dependency tree and **dependencyInsight** to explain how a specific module was selected.

### 6.1. Exporting the Graph by Configuration

At the root of the Gradle project:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath --console=plain > evidence-compile.txt
./gradlew :app:dependencies --configuration runtimeClasspath --console=plain > evidence-runtime.txt
./gradlew :app:dependencies --configuration testRuntimeClasspath --console=plain > evidence-test-runtime.txt
~~~

Configurations have distinct meanings:

- **compileClasspath:** dependencies needed to compile main sources.
- **runtimeClasspath:** dependencies needed when running the application.
- **testRuntimeClasspath:** dependencies used to run tests, including test frameworks and app runtime dependencies.

Compare identical configurations across the two revisions. Do not compare pre-upgrade `compileClasspath` with post-upgrade `runtimeClasspath`.

### 6.2. dependencyInsight: Why Was This Version Selected?

Example inspecting Spring Core:

~~~bash
./gradlew :app:dependencyInsight --dependency org.springframework:spring-core --configuration runtimeClasspath
~~~

Or Jackson:

~~~bash
./gradlew :app:dependencyInsight --dependency com.fasterxml.jackson.core:jackson-databind --configuration runtimeClasspath
~~~

Output can show:

- Direct or transitive requested versions.
- Which version conflict resolution chose.
- How constraints/BOM participated.
- Whether a version was forced or selected by rule.
- Which modules pulled the dependency into the graph.
- Requested and provided variant attributes.

This is a major difference from only reading `implementation` lines in `build.gradle`: declarations do not show the full resolution outcome.

### 6.3. Reading Markers in the Gradle Graph

Gradle dependency reports use symbols such as:

- **(*)**: a repeated dependency subtree already expanded elsewhere.
- **(c)**: a dependency constraint, not an independent dependency artifact.
- **(n)**: a dependency/configuration that cannot be resolved.

A repeated node with `(*)` does not mean the dependency was dropped. A constraint `(c)` does not mean the archive contains an extra JAR. Read the graph alongside `dependencyInsight` to determine actual versions.

### 6.4. Dependency Locking

When you need to keep dependency resolution stable, Gradle supports dependency locking. Example in `build.gradle`:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate or update lock state when resolving configurations:

~~~bash
./gradlew :app:dependencies --write-locks
~~~

Generated lockfiles must be reviewed and committed per project process. When upgrading Spring Boot/BOM, the lock state may need updating because managed versions change. Do not manually edit lockfiles to hide conflicts; resolve the graph, understand the changes, and record lock state from a passing build.

**Limitation:** dependency locking fixes resolved versions, but does not turn mutable SNAPSHOT/changing modules with the same coordinates into immutable bytes. For dependencies whose contents change over time, use appropriate repository/version policies and checksums.

### 6.5. Comparing Version Catalogs, Platforms, and Constraints

If the project uses **libs.versions.toml**, platforms/BOMs, dependency constraints, or resolution rules, save those files in your evidence. A version catalog edit can affect multiple configurations. `dependencyInsight` reveals selected versions, while build scripts/lockfiles document declared policies.

## 7. Reading and Interpreting the Post-Upgrade Dependency Graph

### 7.1. Categorizing Changes

| Change Type | Example | Action |
| --- | --- | --- |
| Version bump via BOM | Spring Framework or Jackson managed by Boot | Verify compatibility and regression tests |
| New dependency | A starter pulls in an extra transitive library | Identify reason, runtime footprint, and security impact |
| Removed dependency | New plugin/starter no longer pulls old module | Confirm code paths no longer need it |
| Conflict resolved differently | Two branches request different versions | Use `dependencyInsight`/verbose tree to find root cause |
| Scope/configuration change | Dependency moves from compile to runtime or test | Check compile/runtime classpaths and packaging |
| Override outside BOM | POM property/Gradle constraint forces version | Confirm intentionality and check compatibility |
| Platform-specific variant | Gradle picks variant by JVM/OS attributes | Compare under matching environments/attributes |

### 7.2. Do Not Only Count Dependencies

Fewer nodes does not automatically mean a better dependency graph. A new dependency may pull in more libraries legitimately. Conversely, a library dropped from the runtime graph may leave the application missing classes at runtime.

Examine:

- GAV and selected version.
- Direct vs. transitive relationship.
- Runtime vs. test/compile scope.
- Selection reason and conflicts.
- Excluded/optional dependencies.
- Which modules use it.
- Whether the library ends up in the final artifact.
- Whether new vulnerability/license policies need handling.

### 7.3. Cross-Checking the Dependency Graph Against the BOM

The Spring Boot BOM manages a compatible set of versions. If the post-upgrade graph has a library at a different version than expected from the BOM, inspect:

- Explicit versions in dependency declarations.
- Property overrides.
- Parent/BOM import order.
- Dependency management from a corporate parent.
- Gradle `platform`/`enforcedPlatform`/constraints.
- Resolution strategies or component selection rules.
- Unupdated stale lockfiles.

Do not mechanically force versions back to the BOM if there is an approved compatibility/security reason; however, document and test every override.

## 8. Comparing Executable JAR/WAR Contents

The dependency graph describes resolution. Artifact inspection confirms what was actually packaged.

### 8.1. Listing All JAR Entries

Maven:

~~~bash
jar tf target/catalog-app-1.0.0.jar | sort > evidence-jar-entries.txt
~~~

Gradle:

~~~bash
jar tf build/libs/catalog-app-1.0.0.jar | sort > evidence-jar-entries.txt
~~~

Work in a separate evidence directory per revision. `jar tf` lists ZIP/JAR contents without extracting or modifying the archive.

### 8.2. Comparing the Nested Libraries List

For an executable Spring Boot JAR:

~~~bash
jar tf target/catalog-app-1.0.0.jar | grep '^BOOT-INF/lib/.*\.jar$' | sed 's#BOOT-INF/lib/##' | sort > evidence-runtime-libraries.txt
~~~

Do the same for the after build. Then diff:

~~~bash
diff -u before/runtime-libraries.txt after/runtime-libraries.txt
~~~

This compares **nested JAR filenames**. It shows which libraries were added, removed, or changed versions. If a filename stayed identical while its internal bytes changed, compare checksums of the nested JARs after extraction.

### 8.3. Comparing Manifests

~~~bash
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF > evidence-manifest.txt
~~~

An executable Boot JAR manifest typically contains:

- **Main-Class:** Boot launcher.
- **Start-Class:** application main class.
- Build metadata or attributes added by the plugin.

After upgrading, the launcher class may change per Boot version. What matters is that the manifest still points to a valid launcher for the archive and `Start-Class` remains the intended entry point.

If `unzip` is unavailable, use `jar xf` in a temporary directory to extract `META-INF/MANIFEST.MF`, then read the file. Do not extract into a directory containing existing files with the same names you need to keep.

### 8.4. Inspecting Application Classes and Resources

In a Boot JAR, application code normally lives under:

~~~text
BOOT-INF/classes/
~~~

Dependency JARs normally live under:

~~~text
BOOT-INF/lib/
~~~

Compare key entries:

- Main class and application packages.
- `application.properties`/`application.yml` and profile resources.
- Migration scripts such as Flyway/Liquibase.
- Templates, static assets, and required resources.
- `META-INF/services/` if using Java `ServiceLoader`.
- Spring auto-configuration metadata.
- `BOOT-INF/classpath.idx` or `BOOT-INF/layers.idx` if the archive is configured to generate them.

Not every archive is required to have `classpath.idx` or `layers.idx`; they depend on packaging configuration. When a file was present in the baseline yet disappears after upgrading, investigate why instead of assuming a failure automatically.

### 8.5. WARs Have a Different Structure from JARs

If the deliverable is a WAR, inspect:

- **WEB-INF/classes/**: application classes/resources.
- **WEB-INF/lib/**: web application dependencies.
- **WEB-INF/lib-provided/**: may hold provided dependencies in an executable Spring Boot WAR.
- **META-INF/MANIFEST.MF**: archive manifest.

Do not apply `BOOT-INF/lib` filtering commands to a WAR. Compare the archive according to its packaging type and exact deployment contract.

## 9. Artifact Hashes and Sizes: Using Them Correctly

### 9.1. Computing SHA-256

Linux/macOS:

~~~bash
sha256sum target/catalog-app-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "target\catalog-app-1.0.0.jar"
~~~

Save the before and after hashes alongside the artifact name, commit SHA, and build metadata.

### 9.2. Different Hashes Are Not Automatically Errors

After an upgrade, the whole-JAR SHA-256 will almost certainly change if dependency versions, manifest, build metadata, or timestamps change. Hashes are used to:

- Verify the downloaded/deployed file is the exact tested file.
- Identify a specific artifact.
- Detect unexpected tampering between stages.
- Store release evidence.

Do not use **before hash must equal after hash** as an acceptance criterion for a dependency upgrade. Two archives with different dependency versions must have different bytes.

### 9.3. Comparing Sizes

Record the file size and nested libraries. A larger archive can result from new dependencies or added resources; a smaller archive can result from dropped dependencies, compression changes, or removed resources. Size is only an indicator, not a standalone quality gate.

## 10. Checking Bytecode and Java Compatibility

If upgrading the JDK/compiler, check the bytecode target of application classes:

~~~bash
javap -verbose -classpath target/classes com.example.catalog.CatalogApplication
~~~

Find the **major version** line. For Java 17, the class file major version is **61**. If the target is still Java 17 yet application classes show a higher major version, the build may have used the wrong target/toolchain.

Do not infer that all nested dependencies must have major version 61. A dependency may support multiple Java versions, contain a multi-release JAR, or be compiled with another target. Inspect application bytecode and the compatibility of any library with special requirements.

If upgrading Spring Boot while staying on Java 17, confirm:

- Build tool and plugins support JDK 17.
- Compiler release/Gradle toolchain remains accurate.
- Production runtime uses a compatible JRE.
- New dependencies do not require a higher Java version than the supported runtime.
- Native libraries/agents contain binaries matching the OS/architecture.

## 11. Comparing Test Results After Upgrading

### 11.1. Maven Surefire and Failsafe

Run:

~~~bash
./mvnw -B -ntp clean verify
~~~

- **Surefire** typically runs unit tests during the `test` phase.
- **Failsafe** runs integration tests if the project configures the plugin and binds appropriate goals to `integration-test`/`verify`.
- **verify** runs earlier phases and configured verification goals.

Reports usually reside at:

~~~text
target/surefire-reports/
target/failsafe-reports/
~~~

JUnit XML reports contain key attributes such as tests, failures, errors, skipped, and runtime duration. Compare both directories if the project has integration tests.

Do not assume `mvn verify` automatically runs integration tests if the POM lacks Failsafe or a matching test profile. Check the effective POM and plugin execution logs.

### 11.2. Gradle Test

Run:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- **test** runs unit tests.
- **check** aggregates tests and verification tasks wired into the lifecycle.
- **bootJar** builds the executable Spring Boot JAR.

Reports usually reside at:

~~~text
build/test-results/test/
build/reports/tests/test/
~~~

If the project has a separate integration test task, confirm that task is wired into `check` or invoked explicitly. A task that exists yet is not in the task graph will not run automatically just because test files exist in the repository.

### 11.3. Comparing Test Counts, Failures, Errors, and Skips

Create a before/after table:

| Metric | Before | After | How to Evaluate |
| --- | --- | --- | --- |
| Test suites | Suite count in report | Suite count in report | Any discrepancy needs explanation |
| Tests executed | Total tests | Total tests | Must not drop silently |
| Failures | Assertion failures | Assertion failures | Investigate every regression |
| Errors | Exception/setup errors | Exception/setup errors | Check API/config/runtime |
| Skipped | Skipped tests | Skipped tests | Confirm skips are intentional |
| Duration | Execution time | Execution time | Investigate major performance regressions |

**Passing tests with a reduced count** can be a dangerous warning sign: test source sets not recognized, profiles changed, test filters excluding tests, or the test engine no longer picking up older tests. Compare report filenames and suite lists, not just `BUILD SUCCESSFUL`.

### 11.4. Why Might Tests Fail After an Upgrade?

- Spring Framework changed validation, binding, transactions, or lifecycle behavior.
- Jackson changed serialization/deserialization behavior.
- Hibernate changed SQL generation or type mapping.
- Security framework changed default configuration or matcher behavior.
- Logging bridge/backend changed classpath or binding.
- Servlet/container API changed namespace/behavior.
- JUnit/Surefire/Gradle test engine changed discovery or extension behavior.
- Database driver changed defaults, timezone, SSL, or transaction behavior.

Categorize failures: compile error, test discovery, assertion, context startup, integration/environment, linkage/classloading, or runtime behavior. Fix the root cause rather than merely loosening assertions to make tests green.

### 11.5. Handling Flaky Tests

If a test fails intermittently, save logs, test reports, seeds/timezones, and environment info. Re-run in a controlled manner to identify flaky tests, without erasing the initial failure from evidence. Distinguish:

- Consistent regression: reproduces under identical conditions.
- Flaky: unstable across runs.
- Environment failure: service container, network, clock, credentials, or resources.
- Test discovery change: test did not run or was skipped.

## 12. Runtime Smoke Tests and Contract Tests

A green test suite does not prove the executable artifact runs in the target environment. Run the packaged artifact:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

For CLI applications, inspect output and exit code. For web services:

1. Start the JAR in a test environment.
2. Wait for the readiness/health endpoint within a reasonable timeout.
3. Call critical endpoints with test data.
4. Verify status codes, response contracts, and logs.
5. Shut down the process cleanly.

If Spring Boot Actuator is present, check that the health endpoint is enabled and exposed per security policy. Do not assume every project has `/actuator/health`.

Add consumer/API compatibility tests if the upgrade could affect contracts with other systems. Dependency graphs and JAR layouts do not detect every change in JSON schemas, SQL behavior, or HTTP semantics.

## 13. Minimal Java 17 Example to Verify App and Test

### 13.1. Application Class

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner upgradeProof() {
        return args -> System.out.println("UPGRADE_SMOKE_OK");
    }
}
~~~

This is a complete Java 17 application class. Once the context starts successfully, the code prints:

~~~text
UPGRADE_SMOKE_OK
~~~

Spring Boot may print a banner and other logs; the line above is the output produced by `CommandLineRunner`.

### 13.2. Context Test

File **src/test/java/com/example/catalog/CatalogApplicationTests.java**:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public class CatalogApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

This test only verifies that the context initializes. A real project must verify business behavior, repositories, HTTP/APIs, security, database migrations, and key integrations. Do not treat a `contextLoads` test as proof of whole-system compatibility.

## 14. Process for Storing Evidence and Diffing Before/After

Each revision should have its own evidence directory:

~~~text
upgrade-evidence/
├── before/
│   ├── environment.txt
│   ├── effective-pom.xml
│   ├── dependency-tree.json
│   ├── runtime-libraries.txt
│   ├── jar-entries.txt
│   ├── manifest.txt
│   ├── tests/
│   └── artifact.sha256
└── after/
    ├── environment.txt
    ├── effective-pom.xml
    ├── dependency-tree.json
    ├── runtime-libraries.txt
    ├── jar-entries.txt
    ├── manifest.txt
    ├── tests/
    └── artifact.sha256
~~~

Filenames depend on the project. What matters is keeping each revision's outputs separate and not overwriting the baseline with a subsequent build's `clean`.

Diff meaningful files:

~~~bash
diff -u upgrade-evidence/before/runtime-libraries.txt upgrade-evidence/after/runtime-libraries.txt
diff -u upgrade-evidence/before/jar-entries.txt upgrade-evidence/after/jar-entries.txt
diff -u upgrade-evidence/before/manifest.txt upgrade-evidence/after/manifest.txt
~~~

For JSON dependency graphs, use a JSON-aware diff if serialization ordering differs while graph contents match. For text graphs, keep the command and plugin version identical; if output includes paths or timestamps, normalize transient parts before diffing without stripping version/selection reasons.

**Do not normalize away evidence.** Do not strip versions, scopes, selection reasons, classifiers, or file paths just to make diffs shorter.

## 15. Post-Comparison Decision Matrix

| Result | Interpretation | Decision |
| --- | --- | --- |
| Graph changes explained, archive valid, tests pass | Upgrade has consistent evidence | Can proceed to release gate |
| Graph changes version yet runtime JAR lacks required library | Packaging/exclusion or scope issue | Block release, fix packaging |
| Graph barely changed yet tests fail | Possible behavior/plugin/JDK/test-engine change | Investigate test/runtime first |
| JAR entries changed without graph explanation | Resource/generated output/packaging/plugin changed | Check manifest, plugins, and build inputs |
| Tests pass yet test count dropped | Test discovery/filter/skip changed | Block until explained |
| Whole-JAR hash changed, all other checks pass | Expected normal outcome of an upgrade | Record new hash; do not treat hash mismatch as regression |
| Runtime smoke test fails though unit tests pass | Artifact or runtime environment differs from test classpath | Inspect executable package and configuration |
| Unexplained version override outside Boot BOM | Unclear dependency alignment | Review override and compatibility tests |

### 15.1. Minimum Acceptance Criteria

- Before/after dependency graphs saved and all significant changes explained.
- No unintended dependency conflicts/overrides.
- Runtime dependency graph matches libraries inside the archive.
- Manifest, launcher, and application `Start-Class` are correct.
- Required application classes/resources are inside the artifact.
- Important test suites ran without silent skips.
- Zero failures/errors, or approved exceptions via a clear process.
- Smoke/integration tests pass in an appropriate environment.
- SHA-256 of the post-upgrade artifact is recorded and used to verify the exact file deployed.
- Security/license/SBOM checks run per organizational release policy.

Do not set a universal maximum dependency count delta for all projects. Every change should be evaluated by the library's role and runtime risk.

## 16. Common Pitfalls When Comparing After an Upgrade

**1. Comparing dependency declarations instead of resolved graphs.** POM/`build.gradle` does not show all transitive dependencies. Use `dependency:tree` or Gradle `dependencies`.

**2. Not saving the effective POM.** Parent, BOM, and active profiles can alter actual versions. Save `effective-pom` before/after.

**3. Maven graph missing omitted nodes.** Omitting `-Dverbose` hides conflict mediation. Enable verbose mode when investigating.

**4. In Gradle, looking only at direct dependencies.** Selected versions can come from transitive paths, constraints, or rules. Use `dependencyInsight`.

**5. Comparing the wrong configuration.** `compileClasspath` differs from `runtimeClasspath`/`testRuntimeClasspath`. Compare matching graph types.

**6. Upgrading only Spring Boot without checking plugin versions.** Maven/Gradle plugins also affect packaging. Record each plugin's version.

**7. Overriding versions outside the BOM without tests.** Dependencies can drift from what Boot tested. Record reasons and compatibility tests.

**8. Lockfiles not updated after upgrading.** Gradle may continue using old versions or report conflicts. Review and record intentional lock states.

**9. Using mutable SNAPSHOTs in comparisons.** Identical coordinates can return different bytes across builds. Use immutable releases or record actual checksums.

**10. Accidentally building before and after with different JDKs.** Bytecode/test differences may not come from Spring Boot. Pin and record the JDK.

**11. Running different Maven profiles.** Dependency graphs and test sets can differ. Save active profiles and exact commands.

**12. Running different Gradle tasks.** `bootJar` does not prove `check` ran. Use `clean check bootJar` or a clearly defined task graph.

**13. Running `mvn package` and assuming integration tests ran.** Failsafe typically requires lifecycle up to `verify` plus plugin configuration. Check effective POM and reports.

**14. Test count drops while the build stays green.** Tests may be skipped or undiscovered. Compare XML reports and test filters.

**15. Comparing whole-JAR hashes and concluding the upgrade failed.** Dependency bytes changed. Use hashes to identify artifacts, not to demand identical before/after bytes.

**16. Checking only `jar tf` without reading the manifest.** Entries may exist while `Start-Class`/launcher is wrong. Read `META-INF/MANIFEST.MF`.

**17. Comparing `BOOT-INF/lib` against the full dependency graph.** The graph contains test/provided/compile scopes; only appropriate runtime packages enter the executable archive. Compare the right scope.

**18. Library missing from graph without realizing an exclusion caused it.** Check `dependency:tree`/`dependencyInsight` and dependency declarations.

**19. Nested JAR has the same filename yet different bytes.** Filename alone does not prove contents. Extract nested archives and compute checksums when needed.

**20. Artifacts overwritten between builds.** Store baseline and candidate in separate directories or worktrees.

**21. Reading stale reports left over after clean/build.** Verify timestamps, run IDs, and commit SHAs in reports; run `clean` before each capture.

**22. Skipping the runtime smoke test.** Unit tests may not boot the executable artifact. Run the exact packaged JAR/WAR.

**23. App passes on the test classpath yet fails from `java -jar`.** Nested dependencies, profiles, or resources may differ. Inspect the actual archive.

**24. Not checking class file versions.** The build might inadvertently target a JDK newer than the runtime. Use `javap` and confirm the Java target.

**25. Not checking auto-configuration/service metadata.** Dependency upgrades can change metadata or `ServiceLoader` resources. Inspect relevant nested JARs when behavior shifts.

**26. Hiding test failures with skip flags.** `-DskipTests`, `maven.test.skip`, or Gradle `-x test` destroys evidence. Record all skips and never count them as test passes.

**27. Reading only aggregated test summaries and overlooking individual test classes.** A failing suite can be obscured by aggregation. Check per-module XML reports.

**28. Not separating regressions from environment issues.** Databases/networks/credentials/timezones can break tests. Record the environment and reproduce under identical conditions.

**29. Counting dependencies only.** Fewer is not automatically better. Evaluate versions, scopes, selection reasons, and runtime impact.

**30. Released artifact differs from tested file.** Rebuilding in a deploy job or copying the wrong file. Deploy the exact uploaded artifact, verify its checksum, and store commit provenance.

## 17. Upgrade Acceptance Checklist

- [ ] Clear before and after commits exist.
- [ ] Only upgrade changes within the defined scope are present.
- [ ] JDK, OS, build wrapper, profiles, and environment are recorded.
- [ ] Maven: effective POM and dependency tree saved.
- [ ] Gradle: compile/runtime/test dependency reports saved.
- [ ] Conflicts, overrides, exclusions, and transitive changes are explained.
- [ ] Boot BOM and plugin versions confirmed.
- [ ] Lockfiles reviewed/updated if the project uses dependency locking.
- [ ] Before/after artifacts saved separately.
- [ ] JAR/WAR entry lists diffed.
- [ ] Nested runtime libraries compared.
- [ ] Manifest launcher and `Start-Class` are accurate.
- [ ] Critical resources/configs/migrations remain in the archive.
- [ ] Bytecode target matches the runtime JDK.
- [ ] Surefire/Failsafe or Gradle test reports saved.
- [ ] Test counts, failures, errors, and skipped counts compared.
- [ ] Integration tests and smoke tests run on the post-upgrade artifact.
- [ ] SHA-256 of the new artifact saved.
- [ ] Security/license/SBOM scans run per release policy.
- [ ] Deployed artifact is the exact file that passed testing and checksum verification.
- [ ] Release sign-off is based on evidence, not `BUILD SUCCESSFUL` alone.

## 18. Official Reference Documentation

- Spring Boot 3.3 — Build Systems and Dependency Management: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Apache Maven Dependency Plugin — tree output formats: https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Gradle 8.5 — Viewing and Debugging Dependencies: https://docs.gradle.org/8.5/userguide/viewing_debugging_dependencies.html
- Gradle 8.5 — Dependency Locking: https://docs.gradle.org/8.5/userguide/dependency_locking.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven Surefire — Reports: https://maven.apache.org/surefire/maven-surefire-plugin/
- Gradle 8.5 — Java Testing: https://docs.gradle.org/8.5/userguide/java_testing.html
- Oracle Java 17 — jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java 17 — javap tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Conclusion:** Comparing a Spring Boot upgrade must rely on three sources of evidence: **resolved dependency graph, packaged artifact contents, and post-build test/runtime results**. Keep environments and build commands consistent, store the baseline separately, explain all version/scope/packaging changes, verify the manifest and nested libraries, and compare test counts alongside failures/skips. SHA-256 identifies the exact tested and deployed file; it is not a requirement that before and after versions have identical bytes.
