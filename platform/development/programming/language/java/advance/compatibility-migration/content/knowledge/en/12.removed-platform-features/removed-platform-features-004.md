# Pack200 and Migrating to Alternative Artifact Distribution Mechanisms

During a Java upgrade from JDK 8 to modern versions, failures do not occur only when compiling source code. A pipeline can still build successfully yet fail during release packaging, downloading libraries to clients, or unpacking artifacts. A common cause in long-lived systems is reliance on **Pack200**: a specialized JAR compression mechanism previously included in the JDK that has since been removed.

The `pack200` and `unpack200` commands, along with the `java.util.jar.Pack200` API, were used to compress multiple class files inside a JAR into a smaller format, especially in certain network-based Java distribution scenarios. Starting in JDK 14, the JDK's Pack200 components no longer exist. Consequently, replacing an older JDK with JDK 17, 21, or 25 can cause a legacy packaging script or artifact downloader to stop working, even if the application never imports `Pack200` in business code.

This lesson explains how to identify Pack200 dependencies, distinguish compression formats from distribution formats, evaluate suitable replacement options, transition pipelines to JARs and artifact repositories or other deployment models, and verify integrity and compatibility after migration.

## 1. What Is Pack200?

### 1.1. Original Purpose

Pack200 is a compression format specifically designed for JAR contents containing Java class files. Unlike merely applying a general-purpose compression algorithm to a byte stream, Pack200 exploits class-file structure and repetitive characteristics across classes in the same archive to reduce transfer size.

Pack200 was particularly meaningful in an era of limited bandwidth, when a Java application or a large set of JARs had to be downloaded over the network. It was once tied to deployment mechanisms such as Java Web Start and pipelines optimizing distributed library sizes.

A legacy workflow can be visualized as follows:

```text
Java source code
    |
    v
Compile and package into application.jar
    |
    v
pack200 creates application.pack.gz
    |
    v
Upload to server or release repository
    |
    v
Client downloads application.pack.gz
    |
    v
unpack200 reconstructs application.jar
    |
    v
JVM loads classes from application.jar
```

The `.pack` or `.pack.gz` format is not a regular JAR and cannot be placed directly on the classpath expecting the JVM to read it as a ZIP/JAR archive. The receiving machine must have an appropriate tool or library to convert it back into a JAR before use.

### 1.2. How Does Pack200 Differ from JAR?

A JAR is fundamentally a ZIP-based archive and typically supports compressing individual entries with DEFLATE. Pack200 does not replace JAR as a long-term classpath format; it is an optimized representation intended for packaging/transfer and then unpacked back into a JAR.

| Aspect | Regular JAR | Pack200 |
|---|---|---|
| Purpose | Directly usable application/library archive | Specialized compressed representation for JAR contents |
| Structure | ZIP entries, manifest, classes/resources | Dedicated packed stream format |
| Direct JVM classpath usage | Yes | No; requires unpacking back to JAR |
| Modern JDK tooling | `jar` remains supported | `pack200` and `unpack200` removed since JDK 14 |
| Runtime dependency | Primarily by class files and APIs used | Depends on availability of a compatible packer/unpacker |
| Common modern distribution | Maven/Gradle repository, JAR download, container image | Legacy pipeline requiring migration |

This distinction is crucial: when Pack200 disappears, **the ability to run JARs does not disappear**. Only the specialized Pack200 compression/decompression step is no longer provided by the JDK.

### 1.3. Common Filenames

Legacy systems may use:

- `library.pack`: packed stream without an outer gzip layer.
- `library.pack.gz`: packed stream with an additional gzip compression layer.
- `library.jar.pack.gz`: naming convention helping identify the original JAR.
- `application.jar`: regular JAR before packing or after unpacking.

The filename is only a hint; you must identify the actual format and the artifact creation process. A file ending in `.gz` could be a gzipped plain JAR or a gzipped Pack200 stream, and these two cases are **not the same**.

Example:

```text
gzip(application.jar)
    -> application.jar.gz
    -> gunzip returns application.jar

gzip(pack200(application.jar))
    -> application.pack.gz
    -> only gunzip + unpack200 returns application.jar
```

Merely changing the `.pack.gz` extension to `.jar.gz` does not convert the contents.

## 2. History of Pack200 Support Across JDK Releases

To plan the migration, you need to determine precisely at which step the change occurs.

| Version | Pack200 Support Status | Impact |
|---|---|---|
| JDK 8 and many older JDKs | Pack200 tools and API are available | Legacy builds or clients may depend on them |
| JDK 11 | JEP 336 deprecates Pack200 tools and API, marked for removal | Need to inventory and plan replacements |
| JDK 14 | JEP 367 removes Pack200 tools and API | `pack200`, `unpack200`, and `java.util.jar.Pack200` no longer exist in the JDK |
| JDK 17, 21, 25 | Pack200 is not restored in the JDK | Pipelines must use another mechanism or an explicitly supported external tool |

Do not assume that JDK 9 or JDK 11 deleted all of Pack200. The actual removal point is **JDK 14**, under JEP 367. Prior deprecation gave systems time to prepare for migration.

Pack200 is an example of an API lifecycle:

```text
Previously supported API/tool
       |
       v
Deprecated for removal (JDK 11)
       |
       v
Removed (JDK 14)
       |
       v
Application must change packaging/distribution
```

Codebases that do not use Pack200 directly can still be affected by Maven/Gradle plugins, Ant tasks, release scripts, CI images, third-party libraries, or client-side programs invoking the old tool.

## 3. Error Symptoms When Upgrading the JDK

### 3.1. `pack200` or `unpack200` Command Does Not Exist

A legacy shell script might contain illustrative commands:

```shell
pack200 dist/app.pack.gz dist/app.jar
unpack200 dist/app.pack.gz dist/app-restored.jar
```

These commands only work in older JDK environments containing the corresponding tools. When run on JDK 14+, the shell may report an unrecognized command or executable not found.

On Windows, scripts may reference a fixed path such as `%JAVA_HOME%\bin\pack200.exe`. On Linux, scripts may call `$JAVA_HOME/bin/pack200`. When switching `JAVA_HOME` to the new JDK, the executable path no longer exists.

Do not fix this by simply dropping a random old executable into `PATH` without managing the tool's version, provenance, and compatibility. Both the artifact-producing pipeline and artifact-consuming pipeline must be reviewed.

### 3.2. Code Referencing the `java.util.jar.Pack200` API Fails to Compile

Legacy code may look like:

```java
// Legacy example - does not compile on JDKs where Pack200 has been removed.
import java.util.jar.Pack200;

Pack200.Packer packer = Pack200.newPacker();
```

When compiling with JDK 14+, the compiler cannot find `Pack200`. Changing source/target levels cannot make an API removed from the JDK reappear.

Software using Pack200 via reflection may not fail at compile time, yet will encounter a runtime error when attempting to look up the class by name.

### 3.3. Build Plugins or Tasks Fail

Even when application code is completely valid, the pipeline can still fail at a final task:

```text
compileJava     SUCCESS
test            SUCCESS
jar             SUCCESS
packDistribution FAILED
publish         NOT RUN
```

That task may invoke `pack200` directly, call the Pack200 API, or rely on an old plugin that assumes the tool is always present in the JDK.

Read the stack trace and logs of the **packaging/publish step**, not just compilation results. Changing the Gradle or Maven version does not automatically replace the Pack200 algorithm; you must identify which task or plugin is applying it.

### 3.4. Clients Cannot Read New Artifacts

A system might deploy a new server while keeping old clients. If clients always download `.pack.gz` and call `unpack200`, switching the server to serve plain JARs can cause clients to report format errors. Similarly, an old Pack200 artifact in a repository or cache does not automatically become a JAR compatible with modern JDKs.

Therefore, migration must consider **both producers and consumers**, including caches, CDNs, proxies, application updaters, and offline devices.

## 4. Before Choosing a Solution: Identify Actual Requirements

Many projects used Pack200 simply because it was the transfer optimization already built into legacy builds. When replacing it, answer:

1. Is the distributed artifact a **library**, **JVM application**, **desktop application**, **container service**, or **client update**?
2. Does the consumer read JARs directly or require an intermediate format?
3. Is the primary requirement reducing size, speeding up downloads, verifying integrity, auto-updating, or version management?
4. Are artifacts downloaded from a Maven repository, an HTTP server, object storage, a CDN, a container registry, or a file share?
5. Is there support for multiple OSes/architectures, native libraries, or a bundled JVM runtime?
6. Is there a requirement to run offline or through proxy systems/resource-constrained devices?
7. Are there JAR signing, release signing, SHA-256 checks, or download-source authentication mechanisms?
8. Is there a need to retrieve historical artifacts to reproduce a release or roll back?

Pack200 is a compression tool, not a complete solution for versioning, security, or deployment. Removing it is an opportunity to eliminate redundant packaging steps and choose the distribution mechanism suited to the product type.

## 5. Replacement Options by Artifact Type

There is no single tool that replaces all previous needs served by Pack200.

| Need | Suitable Solution | Notes |
|---|---|---|
| Distributing Java libraries to other applications | Maven repository and regular JARs | Maven/Gradle manage coordinates and dependencies |
| Distributing standalone JVM applications | Executable JAR or JAR directory bundle + startup script | Requires a compatible Java runtime |
| Distributing services on container infrastructure | OCI container image | Provides image layers, registry, and deployment tooling |
| Distributing a custom runtime | `jlink` | Creates a runtime image for modular applications |
| Packaging desktop applications for end users | `jpackage` | Creates OS-specific application images/installers |
| Only reducing bytes transferred over HTTP | HTTP compression, gzip, or an appropriate compression format | Consumers must support the same encoding/format |
| Releasing direct downloads/updates | HTTPS/CDN + version manifest + checksums/signatures | Watch out for caching and atomic updates |
| Long-term archiving | Original JAR with metadata, checksums, and signatures | Does not depend on a removed unpacker |

The options above address different layers. For instance, `jlink` creates an optimized Java runtime but does not replace distributing library artifacts by dependency coordinates; an OCI image manages container deployment but does not solve a Java client needing to dynamically load libraries from a Maven repository.

## 6. Distributing Regular JARs: The Simplest Path

### 6.1. JARs Still Support Compression

Some engineering teams worry that removing Pack200 means every JAR becomes an uncompressed file. That is untrue. A JAR is a ZIP archive, and the `jar` tool can create compressed entries in the ZIP/JAR format.

Example of creating a JAR from a compiled classes directory:

```shell
jar --create --file dist/example.jar -C build/classes .
```

The illustrative command uses modern `jar` syntax and is only valid if the input directory exists. If the project uses Maven or Gradle, let the build tool produce the archive along with the manifest, resources, and dependency metadata rather than invoking `jar` manually in a production pipeline.

List archive contents:

```shell
jar --list --file dist/example.jar
```

The JVM, IDEs, build tools, and most Java libraries understand JARs directly. No `unpack200` step is required.

### 6.2. "Thin" JARs and "Fat" JARs

When distributing applications, distinguish:

- **Thin JAR:** contains the application's classes and resources; dependencies are supplied separately via the classpath/module path.
- **Fat/Uber JAR:** bundles multiple dependencies into a single large archive for deployment convenience.
- **Executable JAR:** includes appropriate launch information in the manifest or launcher; can be thin or fat depending on design.
- **Application distribution:** a directory containing the application, dependent libraries, resources, and startup scripts.

Each approach has trade-offs. A fat JAR is easy to ship as a single file but can introduce resource, `META-INF/services`, and signature conflicts when merging dependencies. A thin JAR makes swapping library versions convenient but requires an explicit classpath setup mechanism.

Do not treat migrating from Pack200 to a fat JAR as mandatory. If the system currently distributes a `lib/*.jar` directory, you can keep that structure and simply remove the Pack200 step.

### 6.3. Example of a Runnable Distribution

```text
dist/
  app.jar
  lib/
    core.jar
    database-driver.jar
    logging.jar
  config/
    application.properties
  bin/
    start.sh
    start.ps1
```

The application can launch with a classpath consisting of `app.jar` and `lib/*`, or via a launcher generated by the build tool. Paths and separators must be verified on each target OS.

For libraries, publish the JAR along with POM/module metadata rather than handing over a loose directory for consumers to manage dependencies manually.

## 7. Maven Repository Instead of Self-Distributing Pack Streams

### 7.1. Why Is a Repository the Right Model?

If an artifact is used by multiple other Java applications, a Maven-compatible repository typically offers capabilities that Pack200 lacks:

- Identification via `groupId`, `artifactId`, and `version`.
- Dependency metadata and dependency transitivity.
- Managed release and snapshot repositories.
- Access permissions, retention policies, and auditing.
- Integration with CI and dependency resolution tools.
- Ability to include checksums, signatures, and release documentation.

Example consumer dependency:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core-api</artifactId>
    <version>2.4.0</version>
</dependency>
```

Consumers do not need to know the library used to be transferred as Pack200. The build tool retrieves the JAR and POM by coordinates from the configured repository.

### 7.2. Example Publishing with Maven

For a Maven project, basic metadata:

```xml
<groupId>com.example</groupId>
<artifactId>core-api</artifactId>
<version>2.4.0</version>
<packaging>jar</packaging>
```

The target repository can be declared in the `distributionManagement` section:

```xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
</distributionManagement>
```

Then the pipeline can run:

```shell
mvn --batch-mode clean verify
mvn --batch-mode deploy
```

The URL is an illustrative address, not a real endpoint. Credentials must be configured via an appropriate Maven/CI security mechanism rather than hardcoding usernames/passwords in the POM.

`mvn deploy` publishes the artifact according to Maven metadata, without needing Pack200. If the project previously had a "pack" plugin running before `deploy`, remove or replace that plugin after confirming consumers can use the new artifact.

### 7.3. Example Publishing with Gradle

With the Gradle Groovy DSL:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '2.4.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            url = uri('https://repo.example.invalid/maven/releases')
            credentials {
                username = providers.environmentVariable('REPO_USER').orNull
                password = providers.environmentVariable('REPO_PASSWORD').orNull
            }
        }
    }
}
```

This is an illustrative configuration template; the Gradle version and plugins in use must be verified against their corresponding documentation. CI needs to supply environment variables securely. Do not print credentials to build logs.

Publishing step:

```shell
./gradlew build publish
```

On Windows, `gradlew.bat` can be used. Depending on the pipeline, tests and publishing can run in separate stages so that only artifacts passing verification are released.

### 7.4. Immutable Versions and Provenance Control

Do not overwrite a release already downloaded by consumers with different content under the same version. Increment the version, store provenance of the source commit/build, and record checksums for each artifact.

If two different artifacts share the same coordinates/version, Maven/Gradle caches may retain the old file, making incidents hard to reproduce. The immutable release principle helps determine exactly which build was tested and deployed.

## 8. Packaging JVM Applications Without Pack200

### 8.1. Executable JAR

For a server or CLI application running on Java:

```shell
java -jar dist/application.jar
```

The artifact needs an appropriate manifest/launcher. If the application depends on multiple JARs and does not bundle dependencies inside the same file, supply the corresponding classpath or distribution layout. `java -jar` does not automatically download dependencies just because the POM declares them.

For a release, you should include:

- Artifact and commit version.
- Minimum JDK requirement, such as Java 21 or 25.
- Startup script or launch command instructions.
- List of runtime dependencies.
- Checksums and optional signatures.
- Configuration and rollback instructions.

### 8.2. `jlink` for Creating Custom Runtime Images

If an application is organized with JPMS and requires a smaller runtime than a full JDK, `jlink` can create a Java runtime image containing only the necessary modules.

Illustrative example:

```shell
jlink --module-path mods --add-modules com.example.app --output image/runtime
```

The prerequisite is that modules and dependencies on the module path must resolve according to the proper configuration. The command does not automatically turn every classpath JAR into a valid named module.

Keep in mind:

- `jlink` is not a codec to replace Pack200.
- A runtime image is OS/architecture-dependent.
- The runtime must be updated whenever JDK security patches are released.
- Download size may increase when shipping a bundled runtime, though self-containment and operability may improve.
- Test on the target OS/architecture, not only on the build machine.

### 8.3. `jpackage` for Desktop Applications

`jpackage` can create application images or installers for supported operating systems. It is a more suitable option than Pack200 if end users need to install/update a Java application like a desktop application.

General workflow:

```text
Build classes/JAR
    |
    v
Package dependencies
    |
    v
Specify main class or main module
    |
    v
jpackage creates app image/installer
    |
    v
Sign package, release, and test installation/uninstallation
```

Installers and native bundles are not portable like plain JARs. If supporting Windows, macOS, and Linux, build and verify packages for each platform. Installer signing, notarization, and auto-updating are separate operational concerns not automatically solved by `jpackage`.

### 8.4. OCI Container Images for Services

For web services or batch services running in containers, artifact distribution can transition to OCI images:

```text
Source -> JAR -> Container image -> Registry -> Deployment
```

Minimal Dockerfile example:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

This is an illustrative example: the JAR name and path must match the actual output, runtime dependencies may need to be packaged separately, and the base image should be pinned according to organizational policy. Do not rely on a mutable image tag as the sole evidence for reproducing a release; record the image digest and provenance.

OCI images provide layering, registries, image pulling mechanisms, and caching. This is a different distribution model from Pack200 and does not require a JDK with `unpack200` at runtime.

## 9. If You Only Need to Reduce Download Size

Not every system needs to replace its entire deployment tooling. If Pack200 was used **solely for transfer compression**, you can choose a common compression format agreed upon by client and server.

### 9.1. Gzip of a JAR

A simple approach is to build `application.jar` and apply additional compression at the transport/storage layer:

```text
application.jar
    |
    +-- gzip --> application.jar.gz
                         |
                         +-- gunzip --> application.jar
```

`.jar.gz` in this case is a gzipped JAR, **not a Pack200 stream**. Consumers must decompress exactly one gzip layer before running.

On Unix-like systems:

```shell
gzip -k application.jar
```

`gzip -k` is an example of an OS utility, not a JDK command, and is not guaranteed to exist on Windows. You can use a Java library, build plugin, or other packaging tool as appropriate.

### 9.2. HTTP Compression

When downloading over HTTP, the server can support encodings negotiated by both sides. The HTTP `Content-Encoding` mechanism operates at a different layer from the artifact format stored in the repository.

Example:

```text
Stored artifact: application.jar
Response encoding: gzip (if supported by client and configured on server)
Client receives decoded representation: application.jar
```

Do not assume every client automatically handles every Content-Encoding. Check HTTP libraries, proxies, CDNs, range requests, cache keys, and how the downloader writes files. Some artifacts are already compressed, so applying additional gzip may yield limited gains.

### 9.3. Other Compression Algorithms

Algorithms or formats such as Zstandard and Brotli can be useful in certain infrastructures. However, they are not mandatory Java JAR compression tools, and clients require corresponding support.

Before choosing, measure with real data:

| Criterion | Why It Matters |
|---|---|
| Compressed artifact size | Affects bandwidth and download time |
| Compression CPU | Affects CI and release frequency |
| Decompression CPU and RAM | Important on low-spec devices |
| Cross-platform support | Avoids relying on rare or unmaintained binaries |
| Stream/range download capability | Affects client updates and resume |
| Reproducibility | Needed to verify exact checksums/released artifacts |
| Deployment complexity | More custom codecs mean more components that can fail |

**There is no guarantee that gzip, Brotli, or Zstandard will always compress a JAR smaller than Pack200.** The optimal choice depends on artifact characteristics and system goals; prefer long-term supported formats and easily operated distribution workflows.

## 10. JAR Signatures, Checksums, and Post-Migration Integrity

### 10.1. Do Not Equate Functional Equivalence with Byte-for-Byte Identity

Pack200 can transform the representation of class/JAR entries during packing and unpacking. Therefore, do not assume the unpacked output is byte-for-byte identical to the original JAR. For signed JARs, differences in content bytes or entry metadata can affect signature verification.

When migrating:

1. Determine whether the input JAR is digitally signed.
2. If retaining historical Pack200 artifacts, unpack them using an appropriate environment/tool before inspecting.
3. Verify classes/resources and run application tests on the JAR to be distributed.
4. Sign the **final released artifact** according to project policy.
5. Verify signatures and checksums on the consumer side or within the release pipeline.

Do not copy signatures or checksum files from `.pack.gz` verbatim and attach them to a new `.jar`. Signatures/checksums validate a specific artifact rather than proving two different formats carry the same meaning.

### 10.2. Generating Checksums for Released Artifacts

Example on PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\\dist\\application.jar"
```

Example on Linux or environments with `sha256sum`:

```shell
sha256sum dist/application.jar
```

Checksums detect unintended alterations during transfer or storage. However, a checksum **does not by itself prove who published the artifact** if both the checksum value and the file come from an untrusted source. When origin authentication is needed, use artifact signatures or an appropriately managed provenance mechanism.

### 10.3. Verifying Signed JARs

The JDK provides `jarsigner` to sign and verify JAR signatures according to the appropriate key/certificate configuration. Verification example:

```shell
jarsigner -verify -verbose -certs dist/application.jar
```

The command existing and completing does not by itself satisfy all trust policy requirements. Check certificates, chains, expiration dates, algorithm policies, and the system's trust procedures. For JARs that previously went through Pack200, verify the final JAR itself after all transformation steps.

## 11. Reproducible Builds and Avoiding Uncontrolled Differences

Removing Pack200 can simplify the pipeline, yet differences between JAR builds can still arise from:

- Timestamps inside ZIP entries.
- Entry ordering inside the archive.
- Manifest attributes.
- Generated sources/resources containing timestamps or build IDs.
- File encoding and line endings.
- Compiler, plugin, and dependency versions.
- Duplicate resource names or merge order from multiple dependencies.

Reproducible builds help verify that the same inputs and toolchain produce byte-equivalent artifacts, making it easier to detect unintended modifications.

With the Gradle Groovy DSL, you can configure JAR tasks based on the principles of controlling timestamps and entry order:

```groovy
tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Actual options and behavior depend on the Gradle version; the example illustrates the concept. With Maven, the `project.build.outputTimestamp` mechanism and plugins/archivers supporting reproducible builds can be used.

Do not confuse reproducibility with compatibility: two JARs with identical SHA-256 hashes can still contain code that fails to run on the target JDK if the bytecode target or dependencies are wrong. Both aspects must be checked.

## 12. Auditing Source Code, Builds, and Infrastructure for Pack200

### 12.1. Java Source Code

Look for signs such as:

- `import java.util.jar.Pack200`.
- `Pack200.newPacker()` or `Pack200.newUnpacker()`.
- String-based reflection for `java.util.jar.Pack200`.
- Custom adapters/codecs named `Pack200`.
- Java utilities invoking external binaries via `ProcessBuilder`.

Some legacy code paths may not be exercised in tests yet remain inside the artifact and cause errors when building with a new JDK.

### 12.2. Scripts and Build Configuration

Inspect:

- `build.gradle` / `build.gradle.kts` or custom plugins/tasks.
- Maven `pom.xml` and packaging plugins.
- Ant `build.xml` and custom tasks.
- Shell, batch, and PowerShell scripts.
- Dockerfiles and CI images.
- Release jobs in Jenkins, GitHub Actions, GitLab CI, or similar tools.
- Release scripts running on dedicated build servers.
- Artifact caches, object storage, or old release directories.

Search with `rg` if the project has ripgrep:

```shell
rg -n -i "pack200|unpack200|java[.]util[.]jar[.]Pack200" .
rg -n -i "[.]pack[.]gz|[.]pack" .
rg -n -i "packDistribution|unpackDistribution|pack-jars" .
```

The third pattern only shows common example task names, not standard Maven/Gradle task names. If no results are found in the source repository, inspect CI scripts managed outside the repository and binary dependencies of plugins.

### 12.3. Inspecting Published Artifacts

You can check:

- Are there `.pack` or `.pack.gz` files in the distribution directory?
- What MIME type, filename, or response headers is the HTTP endpoint returning?
- Are there update manifests pointing to Pack200?
- Does the repository store regular JARs or only packed streams?
- Does the client have an unpacking step before placing the JAR on the classpath?
- Does a cache/CDN store old artifacts under fixed URLs?

In particular, an update system might retain Pack200 as a "shortcut" activated only when the client supports it. Without end-to-end testing on real clients, it is very easy to miss.

## 13. Converting Legacy Pack200 Artifacts

### 13.1. Distinguishing Creating New Artifacts from Reading Historical Artifacts

Two different problems:

- **New artifacts:** remove Pack200 from the pipeline and publish JARs or the new distribution format.
- **Historical artifacts:** you may still need to read `.pack.gz` from an old release for auditing, reproduction, or data migration.

For historical artifacts, an older JDK environment or compatible Pack200 tool may be needed to unpack them once. Do not revert the entire production runtime to an older JDK merely because a few archive files remain.

### 13.2. Controlled One-Time Conversion Procedure

1. List the packed artifacts to retain, along with versions, sources, and existing checksums.
2. Verify artifact origins and access permissions.
3. Prepare an isolated conversion environment with controlled tool versions.
4. Unpack the artifacts into regular JARs.
5. Inspect contents, manifests, and resources.
6. Run tests or smoke tests appropriate for the artifact type.
7. Sign/verify and publish the new JARs following standard artifact procedures.
8. Store the mapping from historical packed artifacts to converted JARs, along with checksums and metadata.
9. Remove the unpack dependency from new consumers.

Historical command example in an old environment with `unpack200`:

```shell
unpack200 legacy-library.pack.gz legacy-library.jar
```

The command **does not exist in JDK 14+**. If the organization uses an external tool, explicitly verify compatibility, licensing, provenance, and security procedures. Do not grab an unverified binary just to unpack artifacts.

### 13.3. Do Not Assume Converted JARs Have New Bytecode

Unpacking Pack200 only reconstructs class/JAR contents; it does not recompile the program for a newer Java version. A JAR built for Java 8 may still contain class-file version 52 after conversion.

If the application needs to move to JDK 21 or 25, check removed APIs, module encapsulation, native dependencies, and runtime behavior separately. Pack200 migration addresses the **distribution format**, not every Java compatibility issue.

## 14. Migration When Server and Client Are Not Updated Simultaneously

### 14.1. Downloader Compatibility

An old client may only know:

```text
GET /downloads/app.pack.gz
download()
unpack200()
startApplication()
```

If the server immediately returns `app.jar` at the same URL while the client still calls `unpack200`, the migration fails. Both format selection and download logic must be updated.

Safe rollout approach:

- Release new clients capable of accepting regular JARs.
- Use manifests/metadata to announce artifact types and checksums.
- If transition is needed, serve both old and new formats for a controlled period.
- Monitor the proportion of clients still requesting Pack200.
- Retire the Pack200 endpoint only after no committed supported consumers remain.
- Provide notices and a handling path for long-offline clients.

If Pack200 on the server side was only a static compression step, it can be removed sooner. If an endpoint device has fixed firmware or runtime, backward compatibility must be carefully evaluated.

### 14.2. Version Manifest for Update Mechanisms

A modern updater should fetch metadata before downloading artifacts. Illustrative JSON structure example:

```json
{
  "version": "3.2.0",
  "artifact": "application-3.2.0.jar",
  "format": "jar",
  "sha256": "<digest-of-published-file>",
  "minJava": 21
}
```

The `sha256` value here is only a placeholder. A real manifest must place the computed digest of the released artifact. Higher-security systems need to authenticate the manifest itself with a signature or trusted release channel.

An updater should not guess the format by file extension when the protocol provides explicit metadata. It should also verify version, size limits, checksum, runtime compatibility, and swap files using an appropriate atomic/rollback mechanism.

### 14.3. Caches and CDNs

When changing distribution formats, change the artifact URL or use explicit versioned URLs. Do not overwrite `app.pack.gz` with JAR contents while proxies/CDNs and clients still cache under the old format.

Identifying artifacts by immutable content or version helps avoid scenarios where:

- A client receives an old file from cache paired with new metadata.
- An old filename carries the new format and is decoded incorrectly.
- Checksums in the manifest do not match the cache.
- Some CDN nodes have updated while others have not.

## 15. Practical Migration Procedure

### Phase 1: Record the Legacy Pipeline Baseline

Collect at least:

| Information | Illustrative Example |
|---|---|
| JDK used for building | JDK 8 or 11 |
| Task creating Pack200 | `packDistribution` in the legacy pipeline |
| Input | `app.jar`, `lib/*.jar` |
| Output | `app.pack.gz` |
| Storage location | HTTP server, file share, or repository |
| Consumer | Launcher/updater/desktop client |
| Unpack step | `unpack200` or Pack200 API |
| Safety checks | Signature, SHA-256, manifest |
| Artifact scale | Number of JARs, total MB, and download time |

Measure actual download sizes and times before removing Pack200 to establish a basis for evaluation. Do not use an unusually small JAR as representative of the entire product.

### Phase 2: Inventory Pack200 Dependencies

Find all direct and indirect calls to the tool/API. Note that build plugins may invoke the tool via `JAVA_HOME` without the string Pack200 appearing in application source code.

Categorize each finding:

- Required for runtime functionality.
- Only a distribution size optimization.
- Only serves archived/historical artifacts.
- Only in test environments or legacy builds.
- No longer used but not yet removed from configuration.

This categorization helps select a reasonable replacement approach without over-engineering upgrades.

### Phase 3: Design the Final Artifact

Select the target:

- Library: Maven coordinates and JAR.
- CLI/server: executable JAR or application distribution.
- Container service: OCI image.
- Desktop: `jpackage` or a supported installer/update mechanism.
- Modular runtime: `jlink` combined with a distribution channel.
- Direct download: JAR + HTTPS + checksum/signature + versioned manifest.

Specify parameters:

```text
Artifact format     : jar / zip / OCI / installer
Build tool          : Maven / Gradle / other tools
Java compatibility  : release target and minimum runtime
Distribution target : repository / registry / HTTPS / CDN
Integrity           : SHA-256 / signature
Client support      : required version and capabilities
Rollback            : how to revert to the previous artifact
```

### Phase 4: Remove the Pack200 Step

Do not simply delete the final command in a script if consumers still expect the packed format. Update both producer and consumer according to the design from the previous phase.

Example legacy flow:

```text
compile -> jar -> pack200 -> upload .pack.gz
                              |
                              v
                       download + unpack200
```

New flow for libraries:

```text
compile -> test -> jar -> sign/checksum -> publish repository
                                           |
                                           v
                                   Maven/Gradle resolve
```

New flow for services:

```text
compile -> test -> jar -> build OCI image -> scan/sign -> push registry
                                                         |
                                                         v
                                                  deploy image
```

No Pack200 step is needed in the new flows.

### Phase 5: Validate the Release in the Target Environment

Verify:

1. Artifact is uploaded in the correct format and version.
2. Consumer downloads the artifact and verifies the checksum.
3. Java runtime can read the JAR or image.
4. Manifest, resources, service providers, and classpath/module path work.
5. Signed JARs still verify cleanly after all packaging steps.
6. Native libraries are packaged for the right OS/architecture.
7. Legacy clients within the supported scope are not broken.
8. Download and startup metrics meet product requirements.
9. Rollback pipeline can restore the previous artifact.
10. No remaining tasks invoke the Pack200 executable/API on the target JDK.

### Phase 6: Monitor and Clean Up

Monitor server and updater logs for requests to `.pack.gz`. Remove old configuration and documentation once evidence shows consumers have finished migrating. Historical artifacts may be kept in read-only storage with proper metadata, but do not leave an old Pack200 tool as a mandatory component of the daily release pipeline.

## 16. Producer/Consumer Test Matrix

An upgrade across multiple services or clients may require testing the following combinations:

| Producer | Consumer | Goal |
|---|---|---|
| Legacy pipeline producing Pack200 | Legacy client | Pre-migration baseline |
| New pipeline producing JAR | New client | Target flow must succeed |
| Legacy pipeline producing Pack200 | New client with legacy support | Verify transition period if needed |
| New pipeline producing JAR | Legacy client | Clearly determine whether supported or rejected with a notice |
| New repository | Current build tool | Dependency resolution and metadata |
| OCI registry | New deployment | Pull/start/healthcheck/rollback |

Do not expect every combination to be compatible. What matters is clearly documenting supported combinations, and having tests reflect the actual rollout strategy.

### 16.1. JAR Functional Tests

Basic test suite:

- `jar --list` to inspect entries and manifest.
- `java -jar` or classpath/module-path startup tests.
- Resource loading via `getResourceAsStream`.
- `ServiceLoader` discovering providers.
- Reflection/annotation/bytecode tools reading classes.
- Library consumers compiling and running with the new JAR.
- Native integration tests if applicable.

If Pack200 previously altered JAR representation, new consumers might rely on different ZIP entry ordering or signature details. Check those points instead of only comparing file sizes.

### 16.2. Download and Resume Tests

For HTTP/CDN:

- Large files and slow networks.
- Mid-transfer connection drops.
- Range requests or resume if supported.
- Cache invalidation/versioned URLs.
- Checksum mismatches and truncated downloads.
- Proxies altering Content-Encoding.
- Offline clients and updating across multiple versions at once.

This test suite is usually more important than forcing the artifact size to hit a specific compression number.

### 16.3. JDK Compatibility Tests

At a minimum, verify the new artifact on the JDKs the product commits to supporting. For example:

- Build with JDK 21 yet `--release 17` if consumers must use Java 17.
- Run on JDK 21 and 25 if both are targets.
- Verify class-file versions and APIs used in the artifact.
- Check `jdeps`, framework dependencies, native access, and module encapsulation.

Removing Pack200 does not automatically upgrade class-file versions or fix unsupported APIs. These are two separate groups of migration issues.

## 17. Post-Migration Troubleshooting

### Case A: Command Not Found

```text
pack200: command not found
```

**Possible cause:** The target JDK removed the tool or the script points to the wrong `JAVA_HOME`.

**Resolution:** identify the task invoking the tool, remove it, or replace it with the new packaging. Do not reinstall an old JDK across all of production by default.

### Case B: `java.util.jar.Pack200` Not Found

```text
cannot find symbol: class Pack200
```

**Cause:** source or dependency compiled against the old Pack200 API on JDK 14+.

**Resolution:** remove/rewrite the code branch, update the dependency, or replace the codec with a supported solution. Do not merely tweak the `--release` flag.

### Case C: `.pack.gz` Downloaded but Cannot Be Unpacked

**Cause:** modern consumer lacks a Pack200 unpacker, or the file has the wrong format/is truncated.

**Resolution:** identify magic bytes/format using a trusted tool, verify checksums, convert historical data in a controlled environment, or update the server to distribute regular JARs.

### Case D: New JAR Downloaded but JVM Fails to Run

**Possible cause:** bytecode target is higher than the runtime, missing dependencies, wrong manifest main class, or module/native library errors.

**Resolution:** check `java -version`, class-file version, `jar --list`, startup command, and runtime dependencies. Do not assume it is caused by removing Pack200.

### Case E: Invalid JAR Signature

**Possible cause:** JAR was modified after signing or the signature still belongs to the old artifact.

**Resolution:** re-sign the final artifact according to policy, run `jarsigner -verify`, and check chains and metadata. Do not mechanically transfer signatures from a packed stream to a new JAR.

### Case F: Download Size Increased

**Cause:** Pack200 compressed specific sets of class files efficiently; regular JAR/ZIP or gzip may produce larger files.

**Resolution:** measure bandwidth, caching, deduplication, and CDN behavior; try consumer-compatible encodings, prune unnecessary dependencies, and consider OCI layers or splitting artifacts by module. Do not pick an obscure codec just for good compression on a small benchmark.

### Case G: Maven/Gradle Cannot Fetch Artifact

**Cause:** incorrect dependency coordinates, metadata, credentials, proxy, or repository versioning.

**Resolution:** verify `group/artifact/version`, repository URL, access permissions, POM/module metadata, checksums, and caches. Do not misattribute this to the Pack200 tool, which is no longer part of standard download flows.

### Case H: Legacy Client Fails After Endpoint Change

**Cause:** client still attempts to unpack Pack200 even though the endpoint returns a JAR, or the cache serves an old file.

**Resolution:** implement version negotiation/manifests, roll out client updates in phases, use immutable URLs, and clearly announce the deprecation date of the old format.

## 18. Mistakes to Avoid

**Assuming Pack200 and JAR ZIP are the same format.** JAR uses ZIP and the JVM reads it directly; Pack200 is a distinct format that must be unpacked first.

**Merely changing the file extension.** Renaming `.pack.gz` to `.jar.gz` does not turn a Pack200 structure into a gzipped JAR.

**Assuming `--release 8` brings back the Pack200 API.** A compiler target does not restore tools/APIs removed from the current JDK.

**Replacing it with `System.gc()` or a JVM flag.** Pack200 is a distribution format issue, completely unrelated to the garbage collector.

**Grabbing an old Pack200 executable and stuffing it into a production image.** This introduces legacy dependencies, maintenance/security risks, and poor version control.

**Fixing only the producer.** If consumers still require `unpack200`, the migration is incomplete.

**Assuming every new JAR must be packaged as a fat JAR.** Choose thin JAR, fat JAR, or distribution layout based on needs, not habit.

**Forgetting to sign or verify the final artifact.** Changing formats can render old checksums/signatures invalid.

**Using fixed version filenames that can be overwritten.** Caching and rollback become hard to manage if the same URL/coordinates serve different contents.

**Judging success solely by the build.** You must test downloading, resource loading, startup, and real update flows.

**Treating `jlink`, `jpackage`, and OCI images as equivalent compression codecs.** They solve runtime packaging, installation, or deployment; they do not share Pack200's purpose or output.

## 19. Checklist for Completing Migration Off Pack200

### Inventory

- [ ] Located all invocations of `pack200`, `unpack200`, and `java.util.jar.Pack200`.
- [ ] Checked Maven/Gradle/Ant plugins, shell scripts, CI, and Dockerfiles.
- [ ] Identified all `.pack` / `.pack.gz` artifacts currently being published.
- [ ] Determined which consumers depend on Pack200 unpacking.
- [ ] Recorded historical artifacts needing conversion or archiving.

### New Distribution Design

- [ ] Selected target format by product type: JAR, repository, OCI, or installer.
- [ ] Distinguished JAR compression from HTTP/transport compression.
- [ ] Published minimum Java runtime and runtime dependencies.
- [ ] Established versioned artifacts, provenance, and rollback mechanisms.
- [ ] Selected checksums/signatures and receiving-side verification procedures.
- [ ] Planned transition roadmap for legacy clients if not upgraded simultaneously.

### Pipeline and Validation

- [ ] New pipeline does not invoke Pack200 tools/API on JDK 14+.
- [ ] Final artifact can be downloaded and used directly in the published format.
- [ ] Checked JAR manifest, resources, services, and classpath/module path.
- [ ] Verified signed artifacts and checksums after the final packaging step.
- [ ] Build tools and repository metadata work with real consumers.
- [ ] Ran network, cache, resume, and corrupted download tests where applicable.
- [ ] Compared download size, download time, and operational complexity against baseline.
- [ ] Tested rollback or restoration of a previous release.

### Cleanup

- [ ] Removed all instructions requiring `unpack200` in the new environment.
- [ ] Old Pack200 endpoints have a clear deprecation/retirement plan.
- [ ] Historical archives have conversion metadata and do not require an old JDK in production.
- [ ] Build/deploy documentation and release notes reflect the new distribution mechanism.

## 20. Practice Exercises

### Exercise 1: Identifying Pack200 Dependencies

Given a pipeline with the steps:

```text
gradle assemble
pack200 web/app.pack.gz build/libs/app.jar
upload web/app.pack.gz
```

Identify which step will fail if the pipeline moves to JDK 21, and which components on the client side need to be checked before removing that step.

**Hint:** `gradle assemble` alone does not prove consumers support JARs. Locate the launcher/updater and actual download format.

### Exercise 2: Designing an Approach for a Shared Library

A library is used by five services and is currently packaged as `core.pack.gz` and copied to each server. Design an approach using a Maven-compatible repository:

1. Define `groupId`, `artifactId`, and `version`.
2. Publish the JAR and dependency metadata.
3. Update each consumer's dependency declaration.
4. Establish checksum verification and artifact immutability.
5. Propose a rollout/rollback approach without manual file copying.

### Exercise 3: Comparing Size and Correctness

For an application with many classes/resources, build artifacts using the options supported in your environment:

- Regular JAR.
- Gzipped JAR.
- Application distribution or OCI image if appropriate for the product type.

Measure size, CPU, and download time; run the same smoke test suite on the exact target JDK. Do not simply pick the smallest artifact if it makes consumer deployment difficult or lacks a safe update mechanism.

### Exercise 4: Plan for Handling Historical Artifacts

An archive repository still holds `.pack.gz` files from last year's release, while all current servers already run JDK 21. Design a one-time offline conversion workflow covering source verification, tool environment, unpacking, validation, checksums, version mapping, and post-conversion artifact storage.

## Conclusion

Pack200 was a specialized JAR compression solution during an earlier era of Java's evolution, yet was deprecated for removal in JDK 11 and removed from JDK 14 under JEP 367. Therefore, applications upgrading to modern JDKs can no longer rely on `pack200`, `unpack200`, or `java.util.jar.Pack200` as guaranteed parts of the JDK.

A sustainable migration path is not simply finding a replacement codec with a similar compression ratio, but clarifying distribution needs: use JARs and Maven-compatible repositories for libraries; executable JARs or OCI images for services; `jpackage` for desktop; `jlink` for modular runtimes; and HTTPS/CDN, versioned manifests, and checksums/signatures for direct downloads. For each option, update both producer and consumer, inspect the final artifact, and maintain a transition path for legacy data.

By removing Pack200 from the pipeline in a controlled manner, the system avoids relying on discontinued APIs and tools while simplifying builds, updates, provenance verification, and deployment on newer Java versions.
