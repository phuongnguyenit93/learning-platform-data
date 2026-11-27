# SBOMs, Library Inventories, and Reporting Capabilities by Toolchain

## Lesson Objectives

A Spring Boot application compiled into a **GraalVM Native Image** still depends on Java libraries, frameworks, the runtime, OS libraries, and the base image. When a CVE is discovered or component provenance must be proven, operations teams must know the exact dependencies used to build the binary and container.

A **Software Bill of Materials (SBOM)** is a structured inventory of software components, typically containing names, versions, package identifiers, dependency relationships, licenses, and checksums. SBOMs help with inventorying, vulnerability matching, license checks, and tracing changes in the software supply chain.

There is no single SBOM covering every layer of the build process. Maven/Gradle, Spring Boot executable archives, GraalVM Native Image, and container buildpacks can produce reports with different scopes. You need to choose tools based on the questions you need to answer.

After this lesson, you will be able to:

- Distinguish SBOMs for dependency graphs, native executables, and container images.
- Generate CycloneDX SBOMs using Maven and Gradle.
- Extract SBOMs packaged inside Spring Boot executable JAR/WAR archives.
- Enable, export, and extract GraalVM Native Image SBOMs when supported by the toolchain.
- Generate SBOMs for container images using buildpacks or Syft.
- Read components, versions, pURLs, CPEs, dependency relationships, and hashes.
- Understand the limitations of SBOMs when scanning CVEs and integrate reporting into CI/CD.

## 1. What is an SBOM and what is it used for?

### 1.1. An SBOM describes software components

An SBOM can list:

- **Component:** application, library, module, OS package, or build component.
- **Version:** distributed or detected version.
- **Package URL (pURL):** ecosystem-specific package identifier, e.g., Maven.
- **CPE:** Common Platform Enumeration product identifier when mappable.
- **License:** declared or tool-detected license.
- **Hashes:** checksums for integrity verification.
- **Dependencies:** relationships between a component and the components it depends on.
- **Metadata:** creation timestamp, generating tool, application name/version, and build info.

For example, a Maven component can be identified as:

```text
group:    org.springframework
name:     spring-context
version:  6.x.y
pURL:     pkg:maven/org.springframework/spring-context@6.x.y
```

The value 6.x.y merely illustrates the structure. Real SBOMs must record the exact version resolved and included in the artifact.

### 1.2. What tasks does an SBOM support?

| Task | Information provided by SBOM |
|---|---|
| Vulnerability management | Components/versions to match against CVEs and advisories |
| License compliance | Declared/detected licenses of dependencies |
| Incident response | Locating artifacts that contain an affected library |
| Dependency governance | Identifying outdated, duplicate, or unapproved libraries |
| Supply-chain traceability | Linking artifacts to versions, builds, and dependency graphs |
| Release inventory | Recording the component inventory of each release |

An SBOM is input data for the activities above. On its own, an SBOM does not prove software is secure, free of vulnerabilities, or built from trusted sources.

### 1.3. Distinguishing an SBOM from a vulnerability report

- **SBOM** answers: which components make up the software?
- **Vulnerability scan** answers: do those components/versions match any known advisories or CVEs?
- **Vulnerability triage** answers: does a finding affect the specific product and deployment, and what is its remediation priority?
- **Provenance/attestation** answers: from which sources, builders, and workflows was the artifact produced, and is that data signed/verified?

An SBOM does not replace a scanner. Nor can a scanner detect dependencies missing from an SBOM. For an accurate assessment, you must verify both inventory completeness and vulnerability data quality.

## 2. Report formats and scopes

### 2.1. CycloneDX

CycloneDX is an SBOM format supported by Native Image and many Maven/Gradle plugins. JSON and XML are the two common interchange forms. A CycloneDX SBOM can describe components, dependencies, licenses, hashes, pURLs, and related attributes.

GraalVM Native Image currently supports CycloneDX for SBOMs generated directly by Native Image. CycloneDX plugins for Maven/Gradle also generate reports in this format.

### 2.2. SPDX

SPDX is another SBOM standard, commonly used in component inventorying and license compliance. Some container/buildpack scanning tools can output SPDX JSON. The Native Image SBOM generator does not output SPDX by default; if an organization requires SPDX, you can use another tool supporting that format or convert using a verified workflow.

### 2.3. Syft JSON and tool-specific formats

Syft has its own JSON format to preserve package metadata fields collected by Syft. Paketo also previously offered a proprietary schema, though current documentation marks the Paketo-specific format as deprecated; Syft, SPDX, and CycloneDX JSON formats are the primary choices.

Do not rename a file from .cdx.json to .spdx.json assuming you have converted the format. You must use an exporter or converter that genuinely produces the target schema.

### 2.4. Each SBOM generation layer answers a different question

| SBOM source | Typical scope | Appropriate question |
|---|---|---|
| Maven/Gradle CycloneDX plugin | Resolved dependency graph per project config/scopes | Which libraries does the project declare and resolve? |
| Spring Boot executable archive | SBOM packaged with the JAR/WAR if generated and packaged by the build | What inventory does the distributed JVM artifact carry? |
| GraalVM Native Image | Components linkable to reachable code in the native executable per builder-readable metadata | Which libraries was the native binary built from? |
| Buildpack SBOM | Dependencies by layer/buildpack and image; may separate build-time/launch-time | Which components do the container image and build process use? |
| Syft container scan | Packages detectable in the image's filesystem/layers | Which Java and OS packages does the final image contain? |

Reports can differ without necessarily indicating an error. The dependency graph may include libraries with no reachable code in the native executable; the native SBOM may omit OS packages; the container SBOM may omit build-time-only dependencies no longer present in the final image.

## 3. Generating a CycloneDX SBOM with Maven

### 3.1. Using cyclonedx-maven-plugin

Spring Boot currently guides using cyclonedx-maven-plugin to generate an SBOM. If a project uses spring-boot-starter-parent, the parent POM already configures the plugin; you still need to declare the plugin/execution according to how the project wants to run and publish reports.

Example binding the aggregate goal to the package phase:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.cyclonedx</groupId>
            <artifactId>cyclonedx-maven-plugin</artifactId>
            <executions>
                <execution>
                    <phase>package</phase>
                    <goals>
                        <goal>makeAggregateBom</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

The plugin can generate an SBOM per module via makeBom, or a combined report for the Maven reactor via makeAggregateBom. Choose the goal suited to your multi-module structure.

### 3.2. Running the build and locating output

Example:

```bash
./mvnw clean package
```

With the common default configuration, the plugin generates files in the target directory:

```text
target/bom.json
target/bom.xml
```

Output filenames, schema versions, formats, and directories may change depending on plugin configuration. Check Maven logs and the actual configuration before writing artifact upload steps.

### 3.3. Selecting dependency scopes

The Maven plugin can include or exclude compile, provided, runtime, system, and test scopes via configuration. The common default excludes test scope.

When generating an SBOM for production distribution:

- Include compile/runtime dependencies that actually go into the artifact.
- Explicitly decide whether provided/system scopes are needed.
- Do not mix test dependencies into a runtime SBOM without a specific purpose.
- For multi-module projects, decide whether an aggregate BOM for the entire reactor is needed.

Keep build/test SBOMs separate if the organization needs to inventory the entire CI supply chain.

### 3.4. Storing and publishing SBOMs

The Maven plugin can attach the BOM as an additional artifact during install/deploy. Store the SBOM alongside the application version and build metadata; do not let every release overwrite a single bom.json file.

The SBOM must correspond accurately to the released binary/container. If dependencies or profiles change after BOM generation, regenerate the SBOM from the exact final build.

## 4. Generating a CycloneDX SBOM with Gradle

### 4.1. Applying the plugin

Groovy DSL example:

```groovy
plugins {
    id 'org.cyclonedx.bom' version '3.6.1'
}
```

Or Kotlin DSL:

```kotlin
plugins {
    id("org.cyclonedx.bom") version "3.6.1"
}
```

The plugin version must be compatible with the project's Gradle wrapper and build JVM. Plugin 3.x currently requires Gradle 8.4 or higher; check the plugin version compatibility table before upgrading.

### 4.2. Generating an aggregate SBOM

Run from the root project:

```bash
./gradlew cyclonedxBom
```

With current default configuration, outputs typically include:

```text
build/reports/cyclonedx/bom.json
build/reports/cyclonedx/bom.xml
build/reports/cyclonedx-direct/bom.json
build/reports/cyclonedx-direct/bom.xml
<subproject>/build/reports/cyclonedx-direct/bom.json
<subproject>/build/reports/cyclonedx-direct/bom.xml
```

cyclonedxBom generates an aggregate SBOM from the direct SBOMs of the root project and enabled subprojects. cyclonedxDirectBom generates a direct report for each project. This organization is useful for Gradle multi-project builds.

### 4.3. Selecting configurations to include in the BOM

Gradle SBOMs depend on the configurations resolved by the plugin. Inspect include/exclude configurations so you do not confuse test dependencies, plugin dependencies, or non-runtime dependencies with production libraries.

For native applications, store separately:

- The project's dependency graph SBOM.
- The native executable's SBOM if supported by GraalVM.
- The final container image's SBOM.

Do not treat an aggregate project BOM as proof that every component was included in the native binary.

## 5. Extracting an SBOM from a Spring Boot executable JAR/WAR

### 5.1. SBOM packaged in the executable archive

Spring Boot supports printing an SBOM packaged inside an uber JAR/WAR using jarmode tools:

```bash
java -Djarmode=tools -jar target/payment-service.jar sbom
```

You can save the output to a file for pipeline ingestion:

```bash
java -Djarmode=tools -jar target/payment-service.jar sbom \
  > target/payment-service-archive-sbom.json
```

This command only prints the SBOM if the archive already contains a packaged SBOM and the Spring Boot version supports the corresponding jarmode. It does not resolve dependencies on its own or generate a new SBOM from an arbitrary JAR.

### 5.2. Comparing the archive SBOM with the build-tool SBOM

The build-tool SBOM is generated from Maven/Gradle dependency resolution. The archive SBOM is data packaged inside the executable archive. Verify:

- Same project name/version and source revision.
- Same dependency versions.
- Whether any components are missing or added.
- Whether the SBOM was generated before or after the repackage step.
- Whether build profiles and dependency scopes match.

If the archive does not contain an SBOM, revisit the CycloneDX generation step in the build and inspect how the plugin/artifact packages it. Do not assume Spring Boot automatically embeds every SBOM created by external plugins.

## 6. GraalVM Native Image SBOM

### 6.1. Support conditions

GraalVM Native Image can generate an SBOM based on static analysis results, but the built-in SBOM feature is currently available only in **Oracle GraalVM**. GraalVM Community Edition does not provide this feature.

The default supported format is CycloneDX. When enabled, the builder embeds a compressed SBOM into the native executable by default. If using an unsupported distribution, do not assume --enable-sbom will produce a report; use Maven/Gradle CycloneDX and artifact/container scanning tools instead.

### 6.2. Enabling export and classpath SBOM

Example:

```bash
native-image \
  --enable-sbom=classpath,export \
  -jar target/payment-service.jar
```

The SBOM is embedded by default; classpath adds the file to the classpath at META-INF/native-image/sbom.json, while export writes the SBOM JSON as a build artifact. Check build output to see where the file is created.

You can disable the feature with --enable-sbom=false, though you should only do so with a clear reason and after ensuring another pipeline stage preserves an appropriate inventory.

### 6.3. Extracting the SBOM from a native executable

Using the Native Image Utils Tool:

```bash
$JAVA_HOME/bin/native-image-utils extract-sbom \
  --image-path=target/payment-service
```

The command outputs the SBOM content in JSON format. The binary path must be a native executable built with an embedded SBOM.

Syft can be used to extract an embedded SBOM:

```bash
syft scan target/payment-service -o cyclonedx-json
```

Syft can also list Java libraries detected inside a native executable:

```bash
syft target/payment-service
```

Check the Syft version and native-image toolchain in use, because the ability to read embedded SBOMs depends on version format support.

### 6.4. What does the Native Image SBOM reflect?

The Native Image SBOM is constructed by recovering version information observable in external library manifests for classes included in the native executable. It can list the application component and third-party libraries linkable to the corresponding classes/packages.

The dependency tree in the SBOM is inferred from Native Image's static analysis/call graph. This helps trace why a component appears in the binary.

However, the SBOM may contain **unassociated types**: certain classes/interfaces/annotations that cannot be mapped to a component. If a library containing those classes has a CVE, a scanner may fail to recognize the corresponding component. Check the number of unassociated types in the build output/security report and address them before considering the inventory complete.

If the application's entry point class is linked to exactly one component, SBOM metadata can record the application component along with its GAV. If the application is built as a shared library or the entry point cannot be uniquely mapped, the application component field may not appear. Check metadata and coordinates before concluding the SBOM is missing the application.

### 6.4.1. Reading the SBOM in build output and Build Report

When supported and enabled, Native Image build output can indicate:

- Whether an SBOM was generated.
- Whether the SBOM was embedded, added to the classpath, or exported.
- The number of recognized components and size of the embedded SBOM.
- The number of types that could not be linked to a component.

Build Report has an SBOM section to view the inventory and download CycloneDX JSON data. If this section is missing, check the GraalVM edition/version, build arguments, and SBOM status in build output.

Native Image's build output/Build Report describes the executable-level SBOM. It does not replace the SBOM for the container base image and OS packages in other layers.

### 6.5. Improving component mapping for fat JARs

With fat/shaded JARs, packages/classes can be hard to map back to the exact Maven component. The Native Image Maven plugin can generate a baseline SBOM using cyclonedx-maven-plugin, identifying which packages belong to which components so Native Image links them more accurately.

According to GraalVM documentation, this integration has been available since GraalVM Native Build Tools Maven plugin 0.10.4 and is enabled by default when using --enable-sbom. Check the plugin version and logs to confirm the baseline SBOM is generated.

Ensure the project has standard GAV coordinates and manifest metadata. If a component lacks clear group/artifact/version coordinates, accuracy in linking classes to dependencies can drop.

### 6.6. Hashes and strict mode

You can instruct the SBOM to include hashes:

```bash
native-image \
  --enable-sbom=hashes,strict \
  -jar target/payment-service.jar
```

hashes adds SHA-256/SHA-512 digests for components the toolchain can hash. strict causes the build to fail if classes/components cannot be mapped as required or hashes cannot be generated.

Hashes help verify dependencies against trusted sources, but they do not by themselves prove the entire supply chain is secure. For instance, a fat JAR is hashed as a combined artifact; that hash does not necessarily match the hash of each individual JAR on Maven Central. Compare matching artifact types.

### 6.7. Class-level metadata

Native Image has a class-level metadata option to include module, class, interface, record, annotation, constructor, field, and method details in the SBOM. This data can assist in investigating CVEs that affect only a specific class or method.

In return, the SBOM can grow significantly larger. GraalVM documentation also notes a limitation: Syft does not preserve all nested class-level component metadata upon extraction. Enable this only when downstream scanners and workflows genuinely require that level of detail.

## 7. SBOMs from Buildpacks and container images

### 7.1. Buildpacks can report different layers

Cloud Native Buildpacks can generate SBOMs in Syft JSON, SPDX JSON, and CycloneDX JSON formats. With Paketo, SBOMs can describe dependencies of buildpacks, the application, and image layers.

Download the SBOM from an app image:

```bash
pack sbom download payment-service --output-dir build/sbom/paketo
```

Then inspect the files in the SBOM layer directories. Exact formats and layers depend on the builder/buildpacks used.

### 7.2. Distinguishing build-time and launch-time dependencies

SBOMs pulled from an app image generally focus on launch-time dependencies. Dependencies needed only during the build may not appear in the SBOM set downloaded from the final image.

With Paketo, you can request exporting SBOMs at build time:

```bash
pack build payment-service \
  --sbom-output-dir build/sbom/paketo-build
```

Inspect the files in the layers/sbom/build directory to see build-time dependencies. Keep build-time and launch-time inventories separate because they serve two different security goals: protecting the build environment and protecting the runtime artifact.

### 7.3. Scanning the final container image with Syft

Syft can scan an image to detect packages in the filesystem/layers, including Java archives and OS packages:

```bash
syft registry.example.com/payment-service:1.2.3 \
  -o cyclonedx-json=build/sbom/payment-service-image.cdx.json \
  -o spdx-json=build/sbom/payment-service-image.spdx.json
```

Syft supports multiple sources such as Docker/OCI images, archives, filesystems, and single files. If scanning a local image via Docker/Podman, ensure Syft reads the correct image store or tag under inspection.

The container SBOM supplements base image packages and OS layers not covered by Maven/Gradle or native executable SBOMs.

### 7.4. Do not mechanically merge reports of different scopes

When aggregating SBOMs:

- Preserve the generating source and timestamp of each report.
- Clearly note whether a report describes source dependencies, the native binary, or the container image.
- Avoid double-counting the same component merely because it appears across multiple layers.
- Do not drop a component just because another report omits it.
- Keep build-time dependencies separate from launch-time dependencies.

If a combined SBOM is required, use a tool that supports merging/aggregating and verify dependency relationships, component identities, versions, and provenance after merging.

## 8. Scanning for vulnerabilities from an SBOM

### 8.1. Using Grype with a native SBOM

You can pipe an extracted SBOM directly into Grype:

```bash
native-image-utils extract-sbom \
  --image-path=target/payment-service | grype
```

Or scan an exported SBOM file:

```bash
grype sbom:build/sbom/payment-service-native.sbom.json
```

Verify the `sbom:` syntax for your installed Grype version. Results typically include the component, installed version, fixed version, advisory/CVE, and severity according to the vulnerability database.

### 8.2. Scanning the final image

You can scan the image directly:

```bash
grype registry.example.com/payment-service:1.2.3
```

Scanning the image checks both OS packages and components detected in the filesystem. Scanning the native SBOM focuses on Java components recognized by Native Image. Use both when the goal is evaluating the complete container artifact.

### 8.3. Reading results and prioritizing remediation

When findings appear:

1. Confirm the component name/version and pURL/CPE.
2. Check the advisory, affected version range, and fixed version.
3. Determine whether the component resides in the native executable, container base layer, or only at build time.
4. Check whether the application exercises the affected code path, if the advisory specifies concrete exploit conditions.
5. Upgrade the dependency or base image, then rebuild and generate a new SBOM.
6. Rescan the new artifact and archive the results.

Do not rely on severity alone. Exploitability, exposure, privileges, network access, mitigations, and deployment environment all influence priority.

### 8.4. SBOMs can have false positives or omissions

Common causes include:

- Incomplete or unreadable version metadata.
- Shading/relocation breaking the relationship between packages and original artifacts.
- Unassociated types not linked to any component.
- Incorrect or insufficiently precise CPE/pURL mappings.
- Scanner database lacking newly published advisories.
- Component present in the SBOM but not on an exploitable code path.
- Dependencies dynamically loaded after build time missing from build-time inventories.

A more complete SBOM reduces blind spots, though it does not eliminate the need for manual review of critical findings.

## 9. Integrating SBOMs into CI/CD

### 9.1. Generating reports from the same build

A pipeline should generate and store:

- Maven/Gradle CycloneDX SBOM.
- Spring Boot archive SBOM if an archive artifact is packaged.
- Native Image SBOM if supported by Oracle GraalVM and the toolchain.
- Container image SBOM.
- Build metadata: source commit, application version, GraalVM/JDK version, plugin versions, target OS/architecture, and image digest.

All reports must be tied to the same release/build ID. Never reuse an SBOM from a previous build for a new binary.

### 9.2. Checking completeness

You can enforce conditions such as:

- The SBOM file exists and parses cleanly.
- Expected application metadata and version are present.
- Component versions and pURLs are present where source data supports them.
- Native Image unassociated type count does not exceed policy thresholds.
- Container SBOM includes base image packages.
- No banned components or policy-violating licenses are present.
- Vulnerability scans have no findings exceeding release-blocking thresholds.

If the toolchain does not support a given SBOM type, record the reason explicitly and use an alternative source with matching scope. Never create empty files to make the pipeline look as if reports exist.

### 9.3. Storing artifacts and access control

Store SBOMs as immutable release artifacts alongside binary/image digests. Ensure investigators can retrieve the SBOM for any released version.

SBOMs can disclose internal library names, framework versions, and dependency structures. Grant access in line with security policy; do not assume every internal SBOM should be public.

### 9.4. Tracking changes between releases

Compare SBOMs between the current release and the previous release to detect:

- Added or removed dependencies.
- Version changes.
- New or changed licenses.
- Components appearing in the native image that were absent from the baseline.
- Operating system package changes when upgrading the base image.

SBOM diffs are signals for review. A new dependency may be valid, but it should have a clear rationale and owner.

## 10. Reporting capability matrix by tool

| Tool | Input | Format/output | Primary scope | Limitations to remember |
|---|---|---|---|---|
| CycloneDX Maven Plugin | Maven project/dependency graph | CycloneDX JSON/XML | Direct/transitive dependencies by scope | Not an exact inventory of reachable code in the native image |
| CycloneDX Gradle Plugin | Gradle project/configurations | CycloneDX JSON/XML | Direct/aggregate dependency graph | Must configure projects and configurations accurately |
| Spring Boot jarmode tools | Executable JAR/WAR with packaged SBOM | Prints archive SBOM to stdout | Inventory packaged inside the archive | Does not generate an SBOM if the archive lacks one |
| Oracle GraalVM Native Image | Native Image static analysis + library metadata | CycloneDX embedded/classpath/export | Components linked to reachable code | Oracle GraalVM only; may have unassociated types |
| Paketo Buildpacks | Buildpack layers/app image | Syft JSON, SPDX JSON, CycloneDX JSON | Buildpack and app layers; build/launch dependencies | Build-time SBOM must be captured separately |
| Syft | Binary, image, filesystem, archive | Syft JSON, CycloneDX, SPDX, and other supported formats | Packages detected in input | Depends on catalogers and scan target |
| Grype | SBOM or image | Vulnerability findings | Matches components against vulnerability databases | Does not replace an SBOM and findings require triage |

## 11. Complete practical workflow

### Step 1 — Generate dependency SBOM

Choose the Maven or Gradle CycloneDX plugin. Generate the appropriate aggregate/direct BOM and verify the output has accurate dependency versions.

### Step 2 — Inspect the Spring Boot archive

If building an executable JAR/WAR with an SBOM, use jarmode tools to print the report and compare it against the dependency SBOM.

### Step 3 — Build the native executable

With Oracle GraalVM, enable SBOM export/classpath per configuration. Check build output to verify the SBOM was embedded/exported and inspect component and unassociated type counts.

### Step 4 — Extract the native SBOM

Use Native Image Utils or Syft to extract the CycloneDX JSON. Verify component metadata, dependency relationships, and versions.

### Step 5 — Generate the container SBOM

Scan the final image with Syft or download the SBOM from the buildpack. Check base OS, shared libraries, and packages across layers.

### Step 6 — Scan and triage

Use Grype or your organization's scanner to match CVEs. Classify whether findings belong to app dependencies, native components, OS packages, or build-time dependencies.

### Step 7 — Archive and compare releases

Link every SBOM to the source revision, build ID, and image digest. Store reports immutably, compare against the prior release, and review changed components.

## 12. Example release artifact layout

A release can store reports in the following layout:

```text
release/
  payment-service
  payment-service-image.tar
  metadata/
    build-info.json
    image-digest.txt
  sbom/
    dependencies.cdx.json
    spring-boot-archive-sbom.json
    native-image.sbom.json
    container-image.cdx.json
    container-image.spdx.json
  security/
    native-image-grype.json
    container-grype.json
```

This is a suggested structure. Store only files that were actually generated; record tool/version and scope in metadata or artifact names to avoid confusing reports.

## 13. Common issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| No native SBOM produced | Using GraalVM Community Edition or feature not enabled | Confirm Oracle GraalVM and --enable-sbom |
| Native SBOM missing components | Missing manifest/GAV metadata or fat JAR mapping difficulty | Use Native Build Tools Maven baseline SBOM and inspect unassociated types |
| Maven/Gradle SBOM has more dependencies than native SBOM | Build graph includes components with no reachable code in the native image | Compare scope and purpose of each report |
| Container SBOM missing build tools | Tool only scans runtime image | Export build-time SBOM separately from buildpack/CI |
| Spring Boot jarmode finds no SBOM | Archive contains no SBOM or version does not support jarmode | Generate and package SBOM first, check Spring Boot version |
| Scanner reports CVE with unclear component | Incomplete or mis-mapped pURL/CPE/version | Inspect metadata and cross-check original package |
| Cannot compare SBOMs across releases | Missing serial/version/source/build metadata | Link SBOM to commit, build ID, and image digest |
| SBOM hash mismatch | Comparing fat JAR against individual dependency hashes or altered artifact | Compare matching artifact types and trusted download sources |

## 14. SBOM review checklist

- Was the SBOM generated from the exact source revision and dependency lock/resolution of the release?
- Is it clear whether the report covers the dependency graph, archive, native executable, or container image?
- Are direct and transitive dependencies included in the right scope?
- Does a multi-module project have an appropriate aggregate SBOM?
- Does Native Image use a GraalVM edition and version that support SBOMs?
- Does build output show unassociated types, and have they been investigated?
- Do components have names, versions, pURLs, and hashes where supported by the tools?
- Does the container SBOM cover operating system packages and the base image?
- Are build-time dependencies inventoried separately when needed?
- Does the vulnerability scanner use an up-to-date database and have results been triaged?
- Is the SBOM stored immutably alongside the binary/image digest and build metadata?
- Have component changes been compared against the previous release?

### Self-check questions

1. Why does a Maven/Gradle dependency SBOM differ from a native executable SBOM?
2. Why might a native SBOM miss components if classes cannot be mapped back to a GAV?
3. Which format does GraalVM Native Image SBOM support, and which edition provides this feature?
4. When should a container image SBOM be used in addition to a native executable SBOM?
5. Why should build-time dependencies be inventoried separately from launch-time dependencies?
6. How does an SBOM differ from a vulnerability report and provenance?
7. Why do hashes in an SBOM not replace artifact signatures and build provenance?
8. How do you accurately tie an SBOM to a published release?

## References

- [GraalVM — Software Bill of Materials in Native Image](https://www.graalvm.org/latest/security-guide/native-image/sbom/)
- [GraalVM — Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [Spring Boot — Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/how-to/build.html#howto.build.generate-cyclonedx-sbom)
- [CycloneDX Maven Plugin](https://github.com/CycloneDX/cyclonedx-maven-plugin)
- [CycloneDX Gradle Plugin](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [Paketo — Access the Software Bill of Materials](https://paketo.io/docs/howto/sbom/)
- [Anchore Syft](https://github.com/anchore/syft)
- [Anchore Grype — Supported Scan Targets](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/)

**Key takeaway:** generate SBOMs at the exact layer you need to inventory. Maven/Gradle describes the dependency graph; the Spring Boot archive stores the packaged inventory; Native Image describes components mappable to reachable code; buildpacks/Syft describe packages in the final image. Use multiple sources for a complete picture, inspect unassociated components, scan for CVEs, and store each report alongside the exact published release.
