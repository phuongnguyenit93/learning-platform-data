# Reproducible Builds with Java and Maven

A reproducible build is the ability to recreate the exact same binary artifact from the same source code and defined build inputs. When two independent builds produce a JAR/WAR file that is identical byte for byte, you can compare their SHA-256 digests to verify the result. This helps verify release integrity, detect unexpected changes in the build pipeline, and support supply chain incident investigations.

With Maven, reproducible builds require controlling many inputs: source revision, JDK, Maven, plugins, dependencies, repositories, timestamps, encoding, locale, timezone, operating system, and code generation tools. Simply adding a single timestamp property to the POM is not enough. This guide explains how to pin inputs, standardize outputs, verify with the Maven Artifact Plugin, and compare artifacts independently.

## 1. What Is a Reproducible Build?

A build is considered reproducible when a third party can take the same source code, build environment, and build instructions, and produce a bit-for-bit identical copy of the reference artifact.

For example:

- Build A produces `application-1.0.0.jar`.
- Build B runs independently from the same commit and configuration.
- Both files have the same size and SHA-256 hash.
- When extracted, their contents, entry order, and required metadata are also identical.

A reproducible build does not merely mean the program behaves the same at runtime. Two JARs can execute identically yet differ byte for byte because of different timestamps, manifests, file ordering, or metadata. The goal of a reproducible build is to produce an identical binary artifact.

## 2. Distinguishing Repeatable, Reproducible, and Deterministic Builds

These terms are sometimes used interchangeably. In this guide, we use the following practical distinctions:

| Term | Meaning |
|---|---|
| Deterministic build | The same set of inputs is processed in a deterministic manner and produces the same output |
| Repeatable build | A build can be re-run in the same environment and produce consistent results |
| Reproducible build | An independent environment can recreate a byte-for-byte identical artifact from published inputs and instructions |

A build may be repeatable on a developer's machine yet not reproducible on CI due to differences in paths, timezones, or JDKs. Reproducible builds require explicitly defining inputs and performing independent verification.

A container helps control the environment, but using a container alone does not automatically make a build reproducible. Images, architectures, toolchains, dependencies, and nondeterministic external sources outside the container can still cause the output to vary.

## 3. Why Reproducible Builds Matter

Reproducible builds provide the following benefits:

- **Artifact verification:** Others can rebuild and compare against the published release.
- **Detecting anomalous changes:** If the same source produces a different artifact, there may be hidden inputs or unexpected changes in the build pipeline.
- **Increased release trust:** Released binaries can be matched against the published source revision.
- **Audit support:** Provides clearer evidence of the path from source to artifact.
- **Regression investigation:** Differences between two builds can point to a changed plugin, dependency, or environment.
- **Improved CI maintainability:** Stable builds reduce "works on one machine" failures.

Reproducibility is a property of the artifact creation process. It supports provenance and integrity checks, but it does not by itself prove that the source code is secure or free of vulnerabilities.

## 4. Inputs That Can Cause Artifacts to Differ

A Maven build has many more inputs than just Java files:

| Input Group | Examples That Can Cause Differences |
|---|---|
| Source | Different commit, uncommitted files, generated sources, line endings |
| JDK | Vendor, major/patch version, javac, annotation processors |
| Maven | Maven distribution, core extensions, Maven Wrapper |
| Plugin | Plugin version, plugin dependencies, default configuration |
| Dependency | Version ranges, SNAPSHOTs, artifacts overwritten in a repository |
| Archive | Timestamps, entry order, manifest, compression |
| Environment | OS, architecture, locale, timezone, encoding, paths |
| Build script | Auto-activated profiles, environment variables, dynamic properties |
| Generator | Random seeds, current time, file traversal order |
| Native tool | C/C++ compiler, linker, system libraries, and build flags |

Think of a build as a function with many inputs. If an input is not recorded or pinned, the output can change even when the source does not.

## 5. Pinning Source Revision and Repository State

Start with a clean source tree and a specific commit.

Principles:

- Build from a specific commit, not from a working tree with uncommitted changes.
- Check whether untracked or ignored files participate in the build.
- Pin submodule versions if the project uses Git submodules.
- Make generated sources part of a reproducible generation process.
- Do not derive versions from branch names or the current time.
- If you need to record a revision in the artifact, use the commit ID of the source revision.
- Do not let the build pull arbitrary files from working directories outside the repository.

Check Git status:

~~~bash
git status --short
git rev-parse HEAD
git submodule status
~~~

`git status --short` helps detect uncommitted changes. `git rev-parse HEAD` identifies the commit being built. `git submodule status` displays submodule revisions.

Building from two clean checkouts of the same commit helps uncover accidental dependencies on absolute paths, usernames, or leftover workspace contents.

## 6. Pinning the JDK and Maven Runtime

Compilers, annotation processors, Javadoc, plugins, and certain generators can produce different outputs depending on the JDK.

You should specify:

- JDK vendor.
- Required JDK major and patch versions.
- Maven version.
- Operating system and architecture if they affect the artifact.
- Native toolchain if the build includes native components.

Check the runtime:

~~~powershell
java -version
javac -version
mvn -version
~~~

`mvn -version` displays the Maven version, Java version, and Java home used by the Maven process.

If using Maven Toolchains, pin the toolchain JDK used by the Compiler Plugin or other plugins. The Maven runtime JDK and the compiler toolchain JDK may differ; both should be recorded.

### 6.1. Using Maven Enforcer to Check Conditions

The Maven Enforcer Plugin can fail the build early when the Maven or Java runtime does not satisfy a version range.

Example requiring Maven 3.9.9 and JDK 17:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.6.3</version>
  <executions>
    <execution>
      <id>enforce-build-environment</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9.9,4.0.0)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[17,18)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

The version ranges in the example reflect project policy. If your organization uses a different JDK or Maven version, adjust the ranges and keep them in sync with Maven Wrapper/CI.

Enforcer checks the runtime version, but it does not automatically install the JDK or Maven, nor does it guarantee that the JDK comes from a trusted source.

## 7. Pinning Maven with Maven Wrapper

Maven Wrapper ensures every developer and CI runner uses the same Maven distribution without relying on a globally installed Maven.

Initialize the wrapper, for example selecting Maven 3.9.9:

~~~powershell
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Then use the wrapper:

~~~powershell
mvnw.cmd -version
mvnw.cmd clean verify
~~~

On Linux/macOS:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

The `.mvn/wrapper/maven-wrapper.properties` file contains `distributionUrl` pointing to the chosen Maven distribution. Commit the wrapper scripts and required configuration files to source control so everyone uses the same version.

Maven Wrapper pins the Maven distribution; it does not automatically pin the JDK runtime. Use Enforcer, CI images, or toolchains to control the JDK separately.

### 7.1. Verifying Wrapper and Maven Distribution Checksums

Maven Wrapper supports SHA-256 checksums for the wrapper JAR and Maven distribution:

- `wrapperSha256Sum`: checksum of the wrapper JAR.
- `distributionSha256Sum`: checksum of the Maven distribution.

Obtain checksums from a trusted official distribution source, store them alongside the wrapper configuration, and update them when upgrading versions. Do not generate a checksum from a file downloaded from an unknown source and treat it as independent verification.

## 8. Pinning Dependencies and Managing Repositories

Dynamic dependencies are one of the main causes of non-reproducible builds.

Recommendations:

- Declare explicit versions for direct dependencies.
- Use `dependencyManagement` or a pinned BOM.
- Inspect transitive dependencies with `mvn dependency:tree`.
- Avoid version ranges when stable output is required.
- Avoid `SNAPSHOT`, `LATEST`, and `RELEASE` in release builds.
- Use a repository manager with a policy that disallows overwriting release artifacts.
- Pin mirrors/repositories and resolution order.
- Verify checksums of downloaded artifacts.
- Record the BOM and dependency graph of the release.

Inspect the dependency graph:

~~~powershell
mvn dependency:tree
~~~

Inspect the effective POM after parent and profile inheritance:

~~~powershell
mvn help:effective-pom
~~~

These two commands help uncover versions or configurations that differ from what the concise POM appears to show.

### 8.1. Checking Checksums When Downloading Artifacts

You can instruct Maven to fail on checksum mismatches:

~~~powershell
mvn -C clean verify
~~~

The `-C` option enables strict checksum checking. Checksums must come from a trusted repository or source. If a repository allows overwriting both the artifact and its checksum, a checksum alone from that same source does not prove artifact provenance.

Do not use mutable repositories to store release versions. A Maven coordinate such as `groupId/artifactId/version` should always point to the same content throughout the release lifecycle.

## 9. Pinning Maven Plugins, Parent POMs, and Extensions

Plugins are also build inputs. If versions are omitted, Maven may use default versions from the Super POM or resolve them through other mechanisms.

You should pin:

- Parent POM version.
- Build plugin versions.
- Reporting plugin versions if reports are published.
- Maven extension versions in `.mvn/extensions.xml`.
- Annotation processor versions.
- Plugin dependency versions.
- Code generator and schema compiler versions.

You can use `pluginManagement` in a parent POM to manage shared versions. Plugins still need to be declared under `build/plugins` in the modules where they should run; `pluginManagement` only defines default configuration and does not execute plugins automatically.

Do not only pin direct plugins. Also check the dependencies pulled in by plugins and the actual resolved versions.

## 10. Standardizing Archive Timestamps

JAR, WAR, ZIP, and other archives typically store timestamps for each entry. If timestamps are taken from the build time, two builds at different times can produce byte-different files even when the class contents are identical.

Maven supports the following property:

~~~xml
<properties>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

This is a fixed timestamp used for archive outputs by plugins that support reproducible output. In a real project, choose a stable value tied to the source revision or release policy; every rebuild of the same source must use the same value.

Some plugins also accept an integer representing seconds since the Unix epoch, similar to the `SOURCE_DATE_EPOCH` convention.

Do not use `maven.build.timestamp` to write the current time into manifests, resources, or generated sources if byte-for-byte identical artifacts are the goal. That value represents the build start time and therefore changes between runs.

Since Maven 3.10.0 and Maven 4.0.0-beta-5, reproducible mode is enabled by default according to current Maven documentation. Declaring `project.build.outputTimestamp` in the POM remains useful to set an explicit fixed timestamp and override inherited defaults.

## 11. Using Plugins That Support Reproducible Archives

Not all plugin versions normalize archives in the same way. Upgrade to versions that support reproducible builds and configure timestamps consistently.

Example JAR Plugin configuration:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.5.0</version>
  <configuration>
    <archive>
      <manifest>
        <mainClass>demo.App</mainClass>
      </manifest>
    </archive>
  </configuration>
</plugin>
~~~

The JAR Plugin supports `outputTimestamp` and defaults to reading it from `project.build.outputTimestamp`. Other archive plugins such as WAR, EAR, Assembly, Source, and Shade should be checked against their respective versions and documentation.

Maven provides the following command:

~~~powershell
mvn artifact:check-buildplan
~~~

This goal inspects the build plan and identifies which plugins need to be upgraded to support reproducible builds. The required list depends on the plugins in use; address each warning rather than assuming all plugins already support it.

## 12. Standardizing Encoding, Locale, Timezone, and File Ordering

Environment settings can affect generated resources, reports, filenames, and archive contents.

You should explicitly define:

- Source/resource encoding, typically UTF-8.
- Timezone, typically UTC for build data.
- Locale/language/country if generators format numbers or dates.
- Line endings for sources and resources.
- How files and entries are sorted inside archives.
- Path case sensitivity rules.
- File permissions if archives are built across different systems.

Example `.mvn/jvm.config`:

~~~text
-Dfile.encoding=UTF-8
-Duser.timezone=UTC
-Duser.language=en
-Duser.country=US
~~~

In the POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

Do not rely on filesystem traversal order if that order can differ across OSes or filesystems. Generators should sort inputs with a deterministic comparator before writing outputs.

You can use `.gitattributes` to enforce consistent line endings for text files:

~~~text
*.java text eol=lf
*.xml text eol=lf
*.properties text eol=lf
~~~

Choose a line-ending policy suitable for your repository. What matters is that sources and resources are checked out according to a consistent rule.

## 13. Eliminating Nondeterministic Data from Generated Output

Some plugins or scripts may write environment information into the artifact:

- Current time.
- Username or hostname.
- Absolute workspace path.
- Branch name or working tree status.
- Random UUIDs or unseeded random values.
- Results of network queries at build time.
- Filesystem-dependent file ordering.
- Dynamically resolved dependency versions.
- Uncontrolled environment variable values.

If you need to include build metadata in the artifact, choose stable data such as commit ID, release version, or source revision. Avoid embedding personal data and local machine paths.

For generators that use randomness, supply a fixed seed and ensure algorithms do not depend on iteration order. If randomness is an intentional part of the product, separate it from artifact creation or derive the seed from the source revision.

## 14. Controlling Profiles, Tests, and Code Generation

Maven profiles can be activated by OS, JDK, properties, files, or environment variables. Two machines may run different profiles even when using the same POM.

For reproducible builds:

- Explicitly specify required profiles in CI.
- Avoid auto-activated profiles based on unrecorded environment state.
- Record any `-D` properties that affect the artifact.
- Pin annotation processors and code generation plugins.
- Use the same schemas, OpenAPI specs, protobuf definitions, or codegen inputs.
- Control input ordering for generators.
- Use a fixed clock or fixed seed for tests and generators when appropriate.

Test flakiness can cause builds to pass or fail differently even when compiled artifacts are identical. For tests involving time, randomness, or concurrency, use a mock clock, fixed seed, and explicit synchronization.

If a plugin generates report files containing execution timestamps, usernames, or absolute paths, those report artifacts may also be non-reproducible even when the main JAR is stable.

## 15. Controlling CI and the Build Environment

CI must recreate the same set of inputs on every runner.

Useful practices:

1. Use Maven Wrapper to pin Maven.
2. Use a JDK image or toolchain with an explicit version.
3. Pin container images by digest rather than relying only on mutable tags.
4. Pin OS and CPU architecture when builds depend on native tools.
5. Use the same Maven settings, mirrors, and repository policies.
6. Do not let builds depend on files already present in the local cache.
7. Create a clean workspace from a specific commit.
8. Lock down environment variables and Maven profiles that affect output.
9. Record tool versions and the dependency graph.
10. Run an independent build on another runner to verify.

Containers help recreate nearly identical environments. However, you still need to pin the image digest, architecture, and internal toolchain. Native libraries or compilers can depend on the runner's kernel, linker, system packages, and CPU architecture.

## 16. Complete Maven Example Producing a Fixed-Timestamp JAR

This example builds a Java 17 JAR. Maven, lifecycle plugins, the compiler, and the JAR plugin all have pinned versions; encoding and the archive timestamp are explicitly declared.

Structure:

~~~text
reproducible-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          App.java
~~~

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>reproducible-demo</artifactId>
  <version>1.0.0</version>
  <name>Reproducible Demo</name>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-clean-plugin</artifactId>
        <version>3.4.0</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-resources-plugin</artifactId>
        <version>3.3.1</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>demo.App</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Create `src/main/java/demo/App.java`:

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Reproducible Maven build.");
    }
}
~~~

Run the build:

~~~powershell
mvn clean package
~~~

Run the JAR:

~~~powershell
java -jar target/reproducible-demo-1.0.0.jar
~~~

Application stdout:

~~~text
Reproducible Maven build.
~~~

The example fixes archive entry timestamps and pins the plugins that produce the main artifact. When run on the same JDK 17 and the same Maven/runtime inputs, two clean builds can produce byte-for-byte identical JARs.

This POM illustrates archive configuration. To prove independence across two environments, you also need to verify dependencies, JDK patch/vendor, Maven distribution, OS/architecture, environment settings, and any other plugins/extensions used by a real project.

## 17. Checking Reproducibility with Maven Artifact Plugin

Maven provides `maven-artifact-plugin` to compare the current artifact against a reference build.

How to check two builds within the same local Maven repository:

~~~powershell
mvn clean install
mvn clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
~~~

The first command builds and installs the reference artifact. The second cleans and rebuilds, and the `compare` goal compares the new output against the installed artifact.

The `compare` goal can generate a `.buildcompare` file containing the results. If there are differences, the log indicates which artifact to investigate. This goal is not thread-safe; avoid running it in parallel Maven builds.

You can use `artifact:check-buildplan` to detect plugins that need upgrading and `artifact:buildinfo` to record information about the build and artifacts.

Checking on the same machine is a useful screening step, but it does not prove that a third party can recreate the artifact. Both runs may still share the same cache, paths, OS, user, and JDK.

## 18. Independent Comparison Using SHA-256

To verify across two environments:

1. Check out the same commit into two clean workspaces.
2. Use the same Maven Wrapper and specified JDK.
3. Use the same dependency repositories and build arguments.
4. Run `clean package` in both workspaces.
5. Compute the SHA-256 hash of each artifact.
6. Compare the two digests.

On Windows PowerShell:

~~~powershell
Get-FileHash target\reproducible-demo-1.0.0.jar -Algorithm SHA256
~~~

On Linux:

~~~bash
sha256sum target/reproducible-demo-1.0.0.jar
~~~

If the SHA-256 hashes match, the two files are byte-for-byte identical with very high confidence. If the hashes differ, find what changed rather than merely re-checking the source.

A hash only confirms that two files are identical; it does not by itself prove that both were built from trusted sources. For independent verification, a third party must fetch the source revision, recreate the environment, and run the build themselves.

## 19. Investigating Differing Artifacts with diffoscope

When hashes differ, use `diffoscope` to inspect differences inside JAR, ZIP, TAR, or other supported binary formats.

Example:

~~~bash
diffoscope build-a/target/reproducible-demo-1.0.0.jar build-b/target/reproducible-demo-1.0.0.jar
~~~

Common differences:

- Entry timestamps in the archive.
- File ordering inside the JAR.
- Manifest or `pom.properties`.
- Generated resource contents.
- Build metadata containing usernames, paths, or timestamps.
- Different class files due to JDK/compiler/annotation processors.
- Different dependency or plugin versions.
- Different compression or native tool versions.

Investigation workflow:

1. Compare file sizes and entry lists.
2. Use `diffoscope` to identify the differing entries.
3. Determine which plugin or generator produced that entry.
4. Check the plugin's version and configuration.
5. Check source inputs and environment variables.
6. Fix the source of nondeterminism.
7. Rebuild in two independent workspaces and compare hashes.

Do not exclude differing files from the comparison just to make the report pass. If an artifact is being released, any meaningful difference must be explained.

## 20. Common Issues

| Symptom | Common Cause | Resolution |
|---|---|---|
| JAR hash changes on every build | Archive entry timestamps change | Set `project.build.outputTimestamp` and use supporting plugins |
| Local machine and CI produce different JARs | Different JDK, Maven, plugin, or OS | Pin toolchain, Maven Wrapper, and CI image |
| Different manifest | Unstable build metadata or manifest-generating plugin | Check archive/manifest configuration |
| Different resource contents | Filtering uses timestamps, environment, or different encoding | Use fixed properties and UTF-8 |
| Different generated sources | Generator uses randomness, time, or file order | Fix seed, clock, and sort inputs |
| Different dependency graph | SNAPSHOT, version ranges, or mutable repositories | Pin versions and use immutable repositories |
| Build passes locally but fails on CI | Different caches, profiles, or environment | Build from a clean workspace and compare effective POMs |
| Different Maven version | Developer invokes global `mvn` | Use `mvnw`/`mvnw.cmd` |
| `artifact:compare` reports differences | Non-reproducible entry or different build environment | Read `.buildcompare`, use `diffoscope` |
| Different hashes but identical classes | Different timestamp, manifest, archive order, or compression | Compare archive contents and metadata |

## 21. Security and Limitations of Reproducible Builds

Reproducible builds strengthen supply chain verifiability, but it is important to understand their limitations:

- Two identical builds do not prove the source is free of vulnerabilities.
- The same malicious dependency can be rebuilt completely reproducibly.
- Signed artifacts may contain timestamps or signatures that depend on the signing time and process.
- Builds with native outputs often depend on the OS, architecture, compiler, and linker.
- Plugins that do not support reproducible output can cause parts of an artifact to differ.
- Containers do not eliminate all external factors such as kernel, architecture, or network dependencies.

Separate the unsigned artifact build step from the signing/release step if the signing process introduces timestamps or variable data. Record the source revision, toolchain, dependency graph, checksums, and build environment so others can verify.

## 22. Workflow for Implementing Reproducible Builds

1. Choose a clean source commit and pin the revision.
2. Pin Maven using Wrapper and verify the distribution checksum.
3. Pin the JDK vendor/version and specify the architecture.
4. Use Enforcer to check the Maven/JDK runtime.
5. Pin the parent POM, dependencies, BOM, plugins, extensions, and annotation processors.
6. Avoid `SNAPSHOT`, version ranges, and mutable repositories in release builds.
7. Set a fixed `project.build.outputTimestamp`.
8. Upgrade archive plugins and run `artifact:check-buildplan`.
9. Standardize encoding, locale, timezone, line endings, and file ordering.
10. Remove timestamps, usernames, absolute paths, and random data from generated outputs.
11. Build in a clean CI workspace with a pinned image and toolchain.
12. Run `artifact:compare` to screen for differences between two builds.
13. Build independently from the same commit in another workspace or machine.
14. Compare SHA-256 hashes and use `diffoscope` if they differ.
15. Store build metadata, checksums, and verification results alongside the release.

## 23. Reproducible Build Checklist

- [ ] Source commit is specified and working tree is clean.
- [ ] Submodules and generated sources are controlled.
- [ ] Maven Wrapper pins the exact Maven distribution.
- [ ] Wrapper JAR/distribution checksums are verified.
- [ ] JDK vendor, version, and architecture are specified.
- [ ] Maven Enforcer checks the Maven/JDK runtime.
- [ ] Parent POM, dependencies, and BOM have explicit versions.
- [ ] No `SNAPSHOT` or dynamic dependency versions in release builds.
- [ ] Maven plugins, extensions, and annotation processors have pinned versions.
- [ ] Repository does not overwrite release artifact contents.
- [ ] Strict checksum checking is used where appropriate.
- [ ] `project.build.outputTimestamp` is fixed.
- [ ] Archive plugins support reproducible output.
- [ ] Build timestamps, usernames, or absolute paths are not embedded in artifacts.
- [ ] Encoding, locale, timezone, and line endings are standardized.
- [ ] Generators have deterministic input ordering and random seeds.
- [ ] CI image/toolchain and environment variables are controlled.
- [ ] Builds from two clean workspaces have been compared.
- [ ] Artifact SHA-256 hashes match across builds.
- [ ] Differences are investigated with `.buildcompare` or `diffoscope`.
- [ ] Build metadata and checksums are stored with the release.

Reproducible builds require controlling all inputs that produce an artifact, not just the source code. In Maven, pin Maven/JDK/dependencies/plugins, normalize timestamps with `project.build.outputTimestamp`, use plugins that support reproducible archives, and control the environment. Then rebuild from an independent workspace, compare SHA-256 hashes, and investigate any differences with the Maven Artifact Plugin or `diffoscope`. This provides independently verifiable evidence that the released artifact truly corresponds to the published source revision.

## References

- Apache Maven, Configuring for Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Apache Maven, Guide to Configuring Archive Plugins: https://maven.apache.org/guides/mini/guide-archive-configuration.html
- Apache Maven, Maven Wrapper: https://maven.apache.org/tools/mavenwrapper.html
- Apache Maven Wrapper, Checksum Verification: https://maven.apache.org/tools/wrapper/
- Apache Maven Artifact Plugin, artifact:compare: https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html
- Apache Maven Artifact Plugin, artifact:check-buildplan: https://maven.apache.org/plugins/maven-artifact-plugin/plugin-issues.html
- Apache Maven Enforcer Plugin, Require Maven Version: https://maven.apache.org/components/enforcer/enforcer-rules/requireMavenVersion.html
- Apache Maven JAR Plugin, jar:jar: https://maven.apache.org/plugins-archives/maven-jar-plugin-3.5.0/jar-mojo.html
- Reproducible Builds Project: https://reproducible-builds.org/