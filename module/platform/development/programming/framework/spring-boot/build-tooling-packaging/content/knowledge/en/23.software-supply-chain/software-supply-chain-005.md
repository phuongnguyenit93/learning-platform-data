# Distinguishing Java Application SBOMs from Container Image SBOMs in Spring Boot

## 1. Two SBOMs Answer Two Different Questions

An **SBOM (Software Bill of Materials)** is a structured inventory of the software components that make up a product. An SBOM can record package names, versions, suppliers, licenses, hashes, dependency relationships, generating tools, and subject metadata.

For a Spring Boot service, you must distinguish:

- **Application SBOM:** the Java application and the Java libraries resolved/packaged by the build, such as Spring Framework, Jackson, Tomcat, and logging libraries.
- **Container image SBOM:** the final deployed filesystem, including the JRE, OS packages, native libraries, CA certificates, and the Java application copied into the image.

```text
Maven dependency graph
        |
        v
 Application SBOM
 ├── release-demo (root component)
 ├── Spring Boot dependencies
 ├── Spring MVC / Jackson / Tomcat
 └── Direct + transitive Java dependencies
        |
        v
 executable Spring Boot JAR
        |
        +----------------------------+
                                     |
Base image (Linux + JRE + native libs)
        |                            |
        +-------------+--------------+
                      |
                      v
             final OCI image
                      |
                      v
           Container image SBOM
           ├── OS packages
           ├── JRE/runtime packages
           ├── native libraries
           ├── Java application JAR
           └── Java dependencies if recognized by scanner
```

**An Application SBOM does not automatically list OS packages or the base image's JRE. A Container image SBOM can detect Java libraries inside an executable JAR, but detection depth depends on the tool's catalogers and nested archive support.** The two inventories complement each other.

An SBOM is an inventory, **not a vulnerability scan result** and not a certification of “zero vulnerabilities.” Scanners take package identities/versions from an SBOM or image and match them against advisory databases; results still depend on identification quality, vulnerability data, and usage context.

## 2. Scope Comparison

| Criterion | Application SBOM | Container image SBOM |
| --- | --- | --- |
| Subject | Java application or executable JAR | A specific OCI/Docker image |
| Inputs | Maven/Gradle dependency graph, source manifests, JAR/WAR | Image filesystem, manifest/layers, OS package databases, archive scanners |
| Java components | Direct and transitive dependencies | Java packages found by scanner inside JARs/nested JARs |
| JRE | Typically absent if generated only from Maven project model | Can be detected inside the final image |
| OS packages | Absent from a typical Java dependency graph | Can include Debian/Ubuntu, Alpine, RPM packages |
| Native libraries | Only when declared/recognized in app sources | Can include libc, OpenSSL, zlib, JNI libraries |
| Build tools | Maven plugins/compiler require a separate inventory | Absent if the builder stage is excluded from the final stage |
| Dependency graph | Typically clear from Maven/Gradle model | Scanner-dependent; many image SBOMs focus on installed package inventory |
| Subject identity | GAV, JAR filename/version/hash, source commit | Image repository + manifest/index digest + platform |
| Security question | Which Java dependencies have CVEs/license issues? | Which JRE, OS, native packages, and app components exist in the image? |

### 2.1. Examples of Component Identities

An Application SBOM may contain PURLs such as:

```text
pkg:maven/com.example/release-demo@0.1.0
pkg:maven/org.springframework.boot/spring-boot@3.5.0
pkg:maven/org.springframework/spring-webmvc@...
pkg:maven/com.fasterxml.jackson.core/jackson-databind@...
pkg:maven/org.apache.tomcat.embed/tomcat-embed-core@...
```

These are **illustrative package URLs**, not the output of a specific build. Actual versions must come from dependency resolution and plugin output.

A Container image SBOM can add OS/runtime packages:

```text
pkg:deb/<distro>/libc6@<version>
pkg:deb/<distro>/ca-certificates@<version>
pkg:deb/<distro>/openssl@<version>
pkg:maven/org.springframework.boot/spring-boot@3.5.0
```

The values `<distro>` and `<version>` are illustrative placeholders. Do not infer actual packages/versions solely from a base image tag; inspect the SBOM of the built image.

## 3. Three Perspectives When Creating an Application SBOM

### 3.1. Project/Dependency SBOM

Generated from the Maven or Gradle dependency model:
- Knows direct and transitive dependencies.
- Can express component-to-component relationships.
- Records the exact versions resolved by the build tool after conflict resolution, constraints, dependency management, and exclusions.
- Can distinguish compile/runtime/test/provided.
- Does not automatically know the container's JRE or OS packages.

CycloneDX Maven Plugin reads the Maven project/dependency graph and produces an SBOM containing direct and transitive dependencies. The `makeBom` goal generates a per-project BOM; `makeAggregateBom` aggregates a multi-module reactor.

### 3.2. Binary/Archive SBOM

Scans the **actual JAR/WAR file** after packaging:
- Confirms which libraries were actually packaged into the archive.
- Can locate Maven metadata (`pom.properties`, `pom.xml`, manifest) inside JARs.
- Can detect shaded/embedded packages depending on the scanner.
- Helps uncover discrepancies between the declared dependency graph and the final archive contents.

A Spring Boot executable JAR has a nested layout:

```text
release-demo-0.1.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/release/ReleaseDemoApplication.class
    └── lib/
        ├── spring-boot-3.5.0.jar
        ├── spring-web-....jar
        ├── jackson-databind-....jar
        └── tomcat-embed-core-....jar
```

A scanner that does not read nested JARs may only recognize the outer executable JAR and miss the Java packages inside. Choose a tool with a Java archive cataloger that supports nested archives and verify the actual output.

### 3.3. Application SBOM for a Released Product

An SBOM attached to an executable JAR should record:
- Application name/version.
- GAV or release version.
- Git commit/build reference.
- Dependency graph and component identities.
- Hash of the tested JAR.
- SBOM generator tool/version and schema version.
- Supplier, license, timestamp, and external references metadata when available.

**The goal is to bind the SBOM to the exact released binary**, not merely to a POM file that might change later.

## 4. What Does a Container Image SBOM Include?

A container image is a filesystem packaged as layers, plus metadata/config and a manifest. The SBOM should reflect the **actual final image being deployed**.

### 4.1. OS Packages and Runtime

Depending on the base image, a scanner can identify:
- Debian/Ubuntu packages from the `dpkg` database.
- Alpine packages from the `apk` database.
- RPM packages from the `rpm` database.
- Java runtime distribution/version.
- Native shared libraries, CA certificates, timezone data, and TLS packages if present.

OS packages carry advisories per **distro**. A security fix may be backported into a Debian package without incrementing the upstream version string in the usual way. Use scanners that understand distro metadata rather than comparing upstream version strings alone.

### 4.2. Java Application and Dependencies

If a scanner can read Spring Boot executable JARs, it can recognize the app artifact, nested `BOOT-INF/lib/*.jar`, and dependency Maven coordinates/versions. How completely dependency relationships are reconstructed depends on the scanner.

Syft's Java archive cataloger recursively searches for Maven evidence inside Java archives, even when a JAR contains other JARs. For other tools, verify cataloger/version/configuration and reconcile against the Application SBOM.

### 4.3. Multi-Stage Builds: The Builder Is Absent from the Final Image

Example:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp clean package

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

The SBOM of the **final runtime image** typically does not contain Maven/JDK or packages that existed only in the builder stage, because that stage is not copied into the final filesystem. Therefore:
- The Application SBOM describes the app's Java dependencies.
- The final image SBOM describes the JRE/OS and app components in the runtime image.
- The builder image/build toolchain is a separate subject if an inventory is required.
- Build provenance records the builder/toolchain and the process used to produce the binary.

Do not use a final image SBOM to claim you have fully inventoried the entire build environment.

## 5. When Do You Need One SBOM, and When Both?

| Situation | Recommended SBOM |
| --- | --- |
| Java library published to a Maven repository | Application/project SBOM of the library |
| Spring Boot JAR distributed to run via java -jar | Application SBOM + binary/archive verification |
| Spring Boot service running in Docker/Kubernetes | Application SBOM + final container image SBOM |
| Need to check CVEs in the JRE or OS base image | Container image SBOM |
| Need to analyze transitive Spring/Jackson/Tomcat dependencies | Application SBOM from Maven/Gradle, reconciled with archive SBOM |
| Need to evaluate native libraries or distro packages | Container image SBOM |
| Need to inventory Maven plugins/compiler/build image | Separate build-environment SBOM/provenance |
| One service with both AMD64/ARM64 images | Per-platform/manifest SBOMs or a composite model preserving platform relationships |
| Multi-module Maven repo with multiple apps | Separate BOM per deployable app; aggregate BOM for the reactor when needed |

**Recommendation for containerized Spring Boot:** generate an Application SBOM from the dependency graph; scan the packaged JAR to confirm actual packages; then scan the final OCI image to inventory the JRE/OS/native libraries and Java archives inside the image.

## 6. Format Standards: CycloneDX and SPDX Do Not Determine Scope

An SBOM is a concept of inventory and relationships; CycloneDX and SPDX are standard formats for representing that data.

### 6.1. CycloneDX

CycloneDX can represent:
- BOM metadata and the component being described.
- Component identities, versions, suppliers, licenses, hashes.
- Dependency graph and direct/transitive relationships.
- Services, external references, and composition/completeness.
- Vulnerability information, VEX, and provenance-related information according to schema/version support.

CycloneDX supports JSON and XML; JSON is generally convenient for automation, while XML remains supported by many enterprise systems.

**Version note:** the CycloneDX specification currently has version 1.7, while CycloneDX Maven Plugin 2.9.x documentation lists schema 1.6. Never set `schemaVersion=1.7` solely because it is a newer spec; choose the version supported by both your **pinned plugin and SBOM consumers**.

### 6.2. SPDX

SPDX is an international open standard for describing packages, files, licenses, copyrights, relationships, and supply chain data. SPDX 3.0 expands the model for software, services, datasets, AI/ML, and related domains.

Both SPDX and CycloneDX can represent an Application SBOM or a Container image SBOM. **Converting JSON from CycloneDX to SPDX does not automatically add missing OS packages**, and switching scanners does not guarantee complete scope if the input is wrong.

### 6.3. Component Identity

A good SBOM needs stable component identifiers:
- **PURL (Package URL):** identifies packages by ecosystem, e.g., `pkg:maven/org.springframework.boot/spring-boot@3.5.0`.
- **CPE:** identifies products using Common Platform Enumeration conventions when applicable.
- **Hash:** SHA-256 of the binary/package file when the scanner can compute or retrieve it.
- **Version + supplier:** assists when a package lacks a PURL/CPE.

Never compare by `name` alone because many packages share names across ecosystems. Use PURL, version, supplier, qualifiers, and hash when available.

## 7. Hands-On Example: Generating an Application SBOM for Spring Boot Java 17

Let's create a small web application and generate a CycloneDX SBOM with Maven. The example uses Java 17, Spring Boot 3.5.0, Maven 3.9.x, CycloneDX Maven Plugin 2.9.3, and CycloneDX schema 1.6 compatible with 2.9.x plugin documentation. These versions are a fixed set for consistent examples; in real projects, pin and update per your organization's policy.

### 7.1. Project Structure

```text
release-demo/
├── pom.xml
├── Dockerfile
├── .dockerignore
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
```

### 7.2. Complete pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <executions>
                    <execution>
                        <id>application-sbom</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <includeCompileScope>true</includeCompileScope>
                    <includeRuntimeScope>true</includeRuntimeScope>
                    <includeProvidedScope>false</includeProvidedScope>
                    <includeTestScope>false</includeTestScope>
                    <outputFormat>all</outputFormat>
                    <outputName>bom</outputName>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Why is it configured this way?**
- `makeBom` creates a BOM for this Maven project.
- `projectType=application` accurately describes the root component type.
- `compile` and `runtime` scopes are included in the inventory.
- `provided` is excluded in the example because this is an executable Spring Boot JAR carrying appropriate runtime dependencies. If the deployment platform actually supplies a `provided` dependency, record that environmental component per policy rather than ignoring it by default.
- `test` scope is excluded from the Application Runtime SBOM; if you need an inventory of build/test dependencies, generate a separate SBOM for the build environment.
- `outputFormat=all` produces both JSON and XML.
- Plugin 2.9.x documents CycloneDX schema 1.6; verify release/schema support before upgrading the plugin.

### 7.3. Runnable Java Application

**`src/main/java/com/example/release/ReleaseDemoApplication.java`:**

```java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
```

### 7.4. Build and Generate the Application SBOM

From the `release-demo` root directory:

```bash
java -version
mvn -version
mvn -B -ntp clean verify
```

Maven runs tests/lifecycle through `verify`, while the CycloneDX plugin produces:

```text
target/bom.json
target/bom.xml
target/release-demo-0.1.0.jar
```

Filenames follow `outputName=bom`; the default output directory is the Maven project's `target` directory. The JAR is an executable Spring Boot archive thanks to `spring-boot-maven-plugin`.

Inspect:

```bash
jar tf target/release-demo-0.1.0.jar
```

Representative entries:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/release/ReleaseDemoApplication.class
BOOT-INF/lib/spring-boot-3.5.0.jar
BOOT-INF/lib/spring-web-....jar
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

The `....` notation is an abbreviation, not a literal filename. You can read the BOM using `jq`:

```bash
jq -r '.metadata.component |
       [.type, .name, (.version // "")] | @tsv' target/bom.json

jq -r '.components[]? |
       [.type, .name, (.version // ""), (.purl // "")] | @tsv' \
       target/bom.json
```

If consumers only need one format, configure `outputFormat` accordingly instead of `all`. Never edit the JSON file by hand and call it a new SBOM; every change must be regenerated from build inputs or a traceable toolchain.

### 7.5. Checking the Dependency Graph and Scopes

```bash
mvn -B -ntp dependency:tree -Dscope=runtime
```

This command helps reconcile the Maven dependency graph against components in the BOM. If a component does not appear as expected, check:
- Active Maven profiles.
- Dependency scopes and exclusions.
- Dependency management/version mediation.
- `optional` flags and transitive dependencies.
- CycloneDX scope include/exclude configuration.
- Plugin version and output schema.
- Whether the Spring Boot plugin included or excluded the dependency from the executable archive.

**An SBOM from the Maven model and an SBOM scanned from a JAR will not necessarily be identical.** One describes resolved project dependencies by scope; the other describes packages the scanner found in the actual binary.

### 7.6. Checking SBOMs for Multi-Module Maven

In a multi-module reactor:
- `makeBom` creates a BOM per Maven project.
- `makeAggregateBom` creates an aggregate BOM at the root, combining the modules included in the build.
- Create a dedicated BOM for each deployable application to capture that service's exact dependency set.
- An aggregate BOM is useful for repository-wide inventory, but it may include library/test modules that are not packaged into a given executable JAR.

You can invoke the aggregate goal from the root:

```bash
mvn -B -ntp org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
```

Use the goal and configuration matching your pinned plugin version; inspect outputs per module as well as the aggregate rather than checking only a single file named `bom.json`.

## 8. Building the Final Container Image from the Exact Built JAR

To prevent a Docker job from rebuilding source and producing a different binary than the one QA tested, this example **builds the JAR first**, and the Dockerfile only copies the existing JAR.

**`Dockerfile`:**

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app

COPY target/release-demo-0.1.0.jar /app/app.jar

USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**`.dockerignore`:**

```dockerignore
.git
.idea
.vscode
.env
*.pem
*.key
*.p12
```

Do not ignore `target/` because the Dockerfile needs the JAR inside it. The `17-jre` base tag keeps the demo readable; production releases should control base images by approved digest/policy and apply tested patches.

Build the image:

```bash
docker build -t release-demo:0.1.0 .
```

Run:

```bash
docker run --rm -p 127.0.0.1:8080:8080 release-demo:0.1.0
```

Another terminal:

```bash
curl -fsS http://localhost:8080/ready
curl -fsS http://localhost:8080/version
```

Response bodies respectively:

```text
ready
release-demo:0.1.0
```

Stop the container with Ctrl+C. If port 8080 is busy, change the host port, e.g., `-p 127.0.0.1:9090:8080`.

**Key takeaway:** the final image contains the JRE/base filesystem and the built JAR; it does not contain the Maven compiler/toolchain. Thus the container image SBOM adds the runtime base image inventory that the Application SBOM knows nothing about.

## 9. Generating SBOMs from the Executable JAR and the Final Image

### 9.1. Scanning the JAR Archive

Use Syft to scan the executable archive:

```bash
syft target/release-demo-0.1.0.jar \
  -o cyclonedx-json=target/application-archive.cdx.json
```

Syft's Java archive cataloger searches for Maven evidence in JAR/WAR/EAR archives and can traverse nested archives recursively. This output is a **binary/archive SBOM** for verifying which packages actually exist inside the built file. Scanners must be kept updated and properly configured; always inspect the component list and completeness.

### 9.2. Scanning the Final Container Image

After `docker build` succeeds:

```bash
syft release-demo:0.1.0 \
  -o cyclonedx-json=target/container-image.cdx.json
```

Syft's image catalogers inventory the packages detected inside the final image. Depending on the base image, results may include OS packages and runtime packages alongside Java packages recognized from nested archives.

You can also use Docker Scout:

```bash
docker scout sbom \
  --format cyclonedx \
  --output target/container-scout.cdx.json \
  local://release-demo:0.1.0
```

`local://` instructs it to use the image in the local image store without querying a registry. Docker Scout SBOM supports images, OCI layouts, archives, and local directories/files; output can be JSON, SPDX, or CycloneDX.

**Do not assume Syft and Docker Scout outputs are byte-for-byte identical.** The two tools differ in catalogers, metadata, package identification, graph modeling, and versions. Inspect tool/version, component sets, and source evidence.

### 9.3. Inspecting the Image Inventory

View PURLs in the image SBOM:

```bash
jq -r '.components[]?.purl // empty' \
  target/container-image.cdx.json | sort -u
```

To check OS packages, look for ecosystem PURLs like `pkg:deb/...`, `pkg:apk/...`, or `pkg:rpm/...` depending on the distro. To check Java packages, look for `pkg:maven/...`.

Having no `pkg:deb` packages in an SBOM **does not automatically prove the image has no OS components**: the base may use another distro, lack a package manager database, or go unrecognized by the scanner. Inspect the image metadata and active catalogers.

### 9.4. Comparing the Three Inventories

| File | What does it prove? | What does it not prove? |
| --- | --- | --- |
| `target/bom.json` | Maven project/dependency graph per selected scopes/config | JRE/OS packages in the container |
| `target/application-archive.cdx.json` | Java packages found by the scanner inside the actual JAR | Image OS/JRE |
| `target/container-image.cdx.json` | Packages recognized by the scanner in the final image | Build tools used in the builder stage or undetected dependencies |

If the Application SBOM contains Spring/Tomcat/Jackson yet the image SBOM is missing them, inspect the Java archive cataloger and nested JAR support before concluding the image lacks those dependencies. Conversely, if the image SBOM lists JRE/OS packages absent from the Application SBOM, that is an expected scope difference.

## 10. Reading Relationships and Completeness, Not Just Counting Components

A useful SBOM should include:
- A root component representing the described product.
- Clear component identities (PURL, version, supplier).
- Dependency relationships when supported by the tool.
- Metadata about the tool, timestamp, serial number, or BOM reference.
- Hashes when computable/discoverable.
- External references and provenance/source references.
- Composition/completeness when supported by the format/tool.

### 10.1. BOM Root and Component List

An Application BOM typically has a root component like `com.example:release-demo:0.1.0`, followed by Maven dependencies. A Container image BOM may describe the subject as the image or its root component, along with packages found in the filesystem.

Do not judge solely by line count:
- 100 components is not automatically better than 60 components.
- An SBOM full of duplicate packages or incomplete package identities can be harder to use.
- A BOM lacking dependency relationships limits impact analysis for a library.
- A BOM lacking hashes/provenance makes it hard to prove which exact binary is described.

### 10.2. Using PURLs to Reconcile

Example of a Maven package PURL:

```text
pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.x.y
```

An image SBOM can represent that same dependency using the same Maven PURL, while the base image contributes OS PURLs:

```text
pkg:deb/<distro>/libc6@<version>
pkg:deb/<distro>/ca-certificates@<version>
```

When comparing:
1. Normalize PURLs, versions, qualifiers, and namespaces.
2. Compare hashes if both tools provide compatible hashes.
3. Distinguish duplicate packages caused by multiple archive paths/copies.
4. Check for version conflicts and shaded dependencies.
5. Preserve each BOM's dependency relationships.
6. Never merge components by JAR filename alone.

### 10.3. Do Not Merge Two JSON Files by Concatenating Arrays

If you need a **combined/system SBOM** from an Application BOM and an Image BOM:
- Specify which deployment artifact (the image) contains which application component.
- Preserve provenance/source for each component.
- Deduplicate by package identity and version, not just name.
- Maintain valid dependency relationships and BOM references.
- Clearly mark completeness for each source.
- Use a merge/compose tool that supports the format/schema; validate the result with a schema validator.

Usually, storing **two separate SBOMs** with the release record is clearer. Only create a combined BOM when a consumer has a genuine use case and tooling can preserve relationships accurately.

## 11. Build-Time Dependencies Differ from Runtime Dependencies

A Java project has several categories of dependencies:
- **Compile/runtime libraries:** may go into the executable JAR.
- **Test libraries:** JUnit, Mockito, Testcontainers; typically excluded from the production JAR.
- **Build plugins:** Maven Compiler, Surefire, CycloneDX plugin, Spring Boot Maven Plugin.
- **Build runtime:** JDK, Maven distribution, OS packages in the builder container.
- **Application runtime:** JRE, base OS, native libraries, and app dependencies.

An Application Runtime SBOM generally should not mix all test/build tools into the same package set and call it the runtime app inventory. However, an organization may require a separate **build SBOM** to inventory compilers/plugins/build images.

Example Maven scopes:

| Scope | Common meaning | Include in runtime Application SBOM? |
| --- | --- | --- |
| `compile` | On compile and runtime classpaths | Usually yes |
| `runtime` | Needed at runtime, not compile time | Yes |
| `provided` | Expected to be supplied by platform/container | Deployment-dependent; excluded in sample above |
| `test` | Only for testing | Usually excluded from runtime BOM |
| `system` | Dependency tied to a local path | Requires manual review; lacks portability |

Do not rely on scope alone to assert whether a file is inside the Boot JAR; verify with `jar tf` and a binary/archive scanner.

## 12. Multi-Module Maven: App-Specific BOM vs. Repository Aggregate BOM

A large project may look like:

```text
reactor-root/
├── pom.xml
├── core-library/
├── service-api/
├── reporting/
├── boot-app/
└── integration-tests/
```

A root aggregate BOM can list many modules, including libraries and test modules. Yet a container image packages only the modules `boot-app` depends on and whatever is copied into the final image.

**Two distinct goals:**
- **Aggregate reactor BOM:** inventory of the entire Maven reactor.
- **Deployable application BOM:** inventory of the dependency set for the exact released module/application.

When publishing an image of `boot-app`, attach the app module's SBOM to that image. Do not use the root aggregate BOM as sole proof of final image contents if the aggregate includes unshipped modules.

If using the CycloneDX Gradle plugin, version 3.x can generate direct SBOMs per project and aggregate SBOMs via the `cyclonedxBom` task; `cyclonedxDirectBom` creates a project-specific BOM. Task and schema configuration must align with the plugin release compatible with your Gradle Wrapper.

## 13. SBOMs and Vulnerability Scans Are Related but Separate Steps

An SBOM answers **“which components exist?”**. A vulnerability scanner answers **“which advisories/vulnerabilities match those components?”**.

Flow:

```text
Application SBOM / Image SBOM
            |
            v
    Package identification
    (PURL, CPE, version, distro)
            |
            v
   Vulnerability/advisory database
            |
            v
      Matching + policy
            |
            +--> CVE findings
            +--> affected/fixed versions
            +--> severity / exploitability context
            +--> false-positive review / VEX
            |
            v
       CI release gate
```

Even a complete SBOM can still contain many CVEs. A scanner reporting zero CVEs may occur because:
- A component was not recognized.
- The advisory database is stale or lacks a mapping.
- Distro version backports are handled differently.
- A CVE is not yet published or lacks data.
- The scanner lacks a cataloger for a package ecosystem.
- A dependency lies outside the scanned scope.

Therefore:
- Generate SBOMs and attach them to the exact artifact subject.
- Scan the Application SBOM to review Java dependencies.
- Scan the final image to review JRE/OS/native components.
- Review findings against policy, not just raw CVE counts.
- Use VEX or justified security exceptions where supported by your organization; never delete packages from an SBOM just to clean up a report.

## 14. CI/CD: Generating and Attaching Both SBOMs to the Exact Release

A reference pipeline:

```text
Git commit
   |
   v
Maven clean verify
   |
   +--> executable app.jar
   +--> application bom.json / bom.xml
   +--> test reports
   |
   v
Archive scan app.jar
   |
   +--> application-archive.cdx.json
   |
   v
Build OCI image from exact verified app.jar
   |
   +--> image manifest / layers / digest
   |
   v
Scan final image
   |
   +--> container-image.cdx.json
   |
   v
Vulnerability + license policy gates
   |
   v
Publish / sign / attach provenance
   |
   v
Deploy using approved image digest
```

### 14.1. Sample Bash Pipeline

Once Maven, Docker, Syft, and the project from Section 7 are ready:

```bash
set -eu

mvn -B -ntp clean verify

syft target/release-demo-0.1.0.jar \
  -o cyclonedx-json=target/application-archive.cdx.json

docker build -t release-demo:0.1.0 .

syft release-demo:0.1.0 \
  -o cyclonedx-json=target/container-image.cdx.json

sha256sum \
  target/release-demo-0.1.0.jar \
  target/bom.json \
  target/application-archive.cdx.json \
  target/container-image.cdx.json
```

This pipeline illustrates task ordering; it omits registry credentials, SBOM signing, and organizational security gates. Actual SHA-256 values depend on binaries and tool outputs; there is no fixed checksum to copy from documentation.

### 14.2. Build Once, Promote the Same Bytes

To avoid testing one JAR in QA while packaging a different JAR into the image:
1. Build the executable JAR once.
2. Generate the Application SBOM from the resolved dependency graph.
3. Scan the JAR archive and compute its checksum.
4. Run tests/smoke tests against that exact JAR.
5. Build the image by `COPY`ing that exact verified JAR file.
6. Generate the Container image SBOM after the image is created.
7. Record the image digest and JAR SHA in the release record.
8. Publish/promote the exact tested binary/image.

If the Docker job reruns Maven itself, you must prove the new JAR matches the QA-tested JAR via checksum/reproducible build evidence; sharing a version string is not enough.

### 14.3. Where Should SBOMs Be Stored?

Common options:
- CI artifact store for reports linked to workflow run, build ID, and commit.
- Maven repository attaching the Application SBOM with an appropriate classifier when publishing Java artifacts.
- OCI registry/attestation store attaching the Container image SBOM to the image digest.
- Long-term release archive or evidence store for audits/rollbacks.

Do not store an SBOM merely under a generic name like `bom.json` without subject information. You must know **which JAR or which image digest** the BOM describes.

## 15. Linking Metadata and Provenance for Traceability

A solid release record should link:

| Metadata | Meaning |
| --- | --- |
| Git commit | Built source revision |
| Maven GAV | Java component identifier |
| JAR SHA-256 | Executable JAR bytes |
| Application SBOM serial/version | Application dependency inventory |
| Archive SBOM tool/version | Binary JAR scanning tool |
| OCI repository/tag | Human-readable image reference |
| OCI manifest/index digest | Exact identifier of the released image |
| Platform | `linux/amd64`, `linux/arm64`... |
| Container SBOM | Inventory of the specific final image |
| Base image digest | Actual JRE/OS base used |
| Builder/toolchain | Maven/JDK/plugins/build image |
| Test/security evidence | Test results, scans, approvals, and policies |

An SBOM does not by itself prove who built the binary. To increase trust:
- Sign SBOMs/attestations per supply-chain policy.
- Bind provenance to source commit and build identity.
- Retain JAR hashes and image digests.
- Restrict publish and edit permissions on release artifacts.
- Never reuse an old SBOM after changing the JAR, base image, or dependencies.
- Ensure recipients can verify signatures/attestations from an approved trust root.

## 16. Multi-Platform Images: SBOMs Must Account for Architecture

An image index can point to multiple manifests:

```text
release-demo:0.1.0
       |
       v
OCI image index
       |
       +--> linux/amd64 manifest
       |      ├── AMD64 JRE
       |      ├── AMD64 OS layers
       |      └── app JAR
       |
       +--> linux/arm64 manifest
              ├── ARM64 JRE
              ├── ARM64 OS layers
              └── app JAR
```

A pure Java application JAR may be identical across both platforms, yet OS/JRE/native components and layer digests can differ.

Therefore:
- One Application SBOM can apply to the binary JAR if the binary is truly identical.
- Container image SBOMs should attach to each child manifest/platform or an aggregate index with clear relationships.
- Scan every released platform, not just the default local laptop image.
- Use the OCI index digest as the shared identity while retaining child manifest digests and platform-specific scan evidence.
- If the app includes JNI/native-image, the application binary/dependencies may also differ by architecture.

Docker Scout provides a `--platform` option to choose the platform when analyzing an image. Inspect the manifest/index with Buildx first, then scan all variants supported in production.

## 17. Common Issues and Fixes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Application SBOM missing a used dependency | Incorrect scope/config/profile/exclusion | Check `mvn dependency:tree`, effective POM, and CycloneDX scope config |
| Application SBOM contains test libraries | `includeTestScope=true` or misconfigured plugin | Separate build/test BOMs; set test scope false for runtime BOM |
| Maven BOM includes `provided` but JAR omits it | Project model includes provided scope, while app archive omits it | Choose appropriate scope policy; cross-check `jar tf` |
| Maven BOM lacks JRE | Project dependency graph excludes runtime base | Scan the final container image |
| Image SBOM missing Spring/Tomcat | Scanner did not read nested Boot JAR or cataloger did not run | Use an archive-aware scanner, verify Syft Java cataloger, and scan JAR separately |
| Image SBOM contains only OS packages | Tool only reads OS package DB or fails on Java archives | Enable Java archive cataloger, scan executable JAR, and reconcile |
| Image SBOM missing OS packages | Minimal/distroless image lacks package DB or scanner lacks support | Check base image, cataloger support, and scan binaries/filesystem |
| Image SBOM still includes Maven/JDK | Build tools copied into final stage or scanned builder by mistake | Inspect final image layers and Dockerfile stages |
| Container SBOM differs after only changing base image | JRE/OS packages or base digest changed | Regenerate image SBOM and rescan |
| Old Container SBOM attached to a new tag | Mutable tag reused without regenerating BOM | Bind BOMs to manifest digests, not just tags |
| CVE scans differ between two tools | Advisory data, PURL/CPE matching, and distro logic differ | Inspect package identity, scanner version, and advisory source |
| SBOM lacks dependency relationships | Scanner only creates a flat inventory or lacks graph evidence | Use Maven/Gradle dependency SBOM for the graph |
| Aggregate BOM includes test modules | Root reactor contains test/support modules | Generate dedicated BOMs for deployable applications |
| Two BOMs duplicate many components | Same Java libraries appear in both app and image | Compare PURLs/versions/hashes; keep sources and subjects distinct |
| SBOM does not match released binary | Rebuilt in another job or artifact altered after QA | Compare JAR hash, commit, build ID, and provenance |
| JAR scan misses nested dependencies | Scanner/cataloger lacks archive format support or is disabled | Check Java cataloger and scan config; use nested-archive-aware tools |
| Multi-arch image has only one SBOM | Only scanned default platform | Scan every released platform/child manifest |
| Plugin reports unsupported schema | Schema version is newer than plugin release | Use a schema version supported by the plugin or upgrade the plugin |
| BOM JSON parses but consumer rejects it | Wrong schema/media type/version or missing required metadata | Validate with a schema-compatible validator |
| Vulnerability absent from SBOM findings | Package not cataloged, lacks PURL/CPE, or no advisory yet | Check file evidence/catalogers, package metadata, and scanner coverage |

### 17.1. Step-by-Step Debugging Workflow

1. Confirm the exact subject: Maven project, executable JAR, or final image.
2. Check Git commit, GAV, JAR SHA-256, and image digest.
3. Run `mvn dependency:tree` to verify dependency resolution.
4. Run `jar tf` to confirm which nested libraries are actually inside the Boot JAR.
5. Generate the Application SBOM from Maven/Gradle.
6. Generate the archive SBOM from the JAR and compare component identities.
7. Scan the final image; inspect OS/JRE/native packages and Java catalogers.
8. Verify the final image corresponds to the right Dockerfile stage/platform.
9. Compare PURLs/versions/hashes, not just package names.
10. Inspect SBOM tool version, schema version, scan configuration, and metadata.
11. Run vulnerability scanning separately; inspect advisory sources, distro mappings, and policies.
12. Bind results to the exact JAR/image digest; never overwrite an older release's SBOM.

## 18. Misconceptions to Avoid

1. **“An Application SBOM is enough for a container.”** No: it usually omits OS/JRE base image packages.
2. **“A Container SBOM always captures all Java dependencies.”** No: it requires a scanner supporting nested JARs and appropriate catalogers.
3. **“Both SBOMs should be identical.”** No: they describe different subjects and scopes.
4. **“An SBOM is a vulnerability report.”** No: inventory and advisory matching are two separate steps.
5. **“The Maven plugin scans everything in the final image.”** No: the plugin reads the Maven project/dependency model.
6. **“An image scanner understands every dependency graph like Maven.”** No: graph completeness depends on scanner evidence.
7. **“An image SBOM includes the Maven/Gradle builder.”** Not if the builder stage is excluded from the final image.
8. **“A JAR checksum is the image digest.”** No: a JAR file hash differs from an OCI manifest/index digest.
9. **“SPDX vs. CycloneDX determines whether an SBOM is application or container scoped.”** No: those are formats; scope is determined by subject and data source.
10. **“Having an SBOM means zero CVEs.”** No: an SBOM may list vulnerable components.
11. **“A high-severity CVE means the app is definitely exploitable.”** No: check affected package, configuration, reachability, and VEX/context.
12. **“One SBOM for a tag stays valid forever.”** No: a tag can move to another image; bind SBOMs to digests.
13. **“Scanning one local architecture is enough for multi-arch.”** No: check every platform manifest.
14. **“Merging two BOM files by concatenating components is enough.”** No: you must handle duplicate identities, BOM references, and dependency relationships.
15. **“An Application BOM defaults to runtime only.”** No: inspect scope configuration; the Maven plugin can include compile/provided/system depending on settings.
16. **“Build tool dependencies are runtime application dependencies.”** No: separate build SBOMs from runtime SBOMs.
17. **“The filename `bom.json` tells you what the BOM describes.”** No: read the metadata/subject and release linkage.
18. **“If a scanner didn't find a package, it isn't there.”** No: it could be due to cataloger, archive format, package DB, or coverage limitations.

## 19. Checklist for Spring Boot Releases

### Application SBOM

- [ ] Select the right module/deployable application.
- [ ] Use the resolved dependency graph from Maven/Gradle.
- [ ] Set project/component type to application when appropriate.
- [ ] Explicitly define compile/runtime/provided/test/system scopes.
- [ ] Confirm dependency versions and exclusions using the dependency tree.
- [ ] Choose a CycloneDX/SPDX schema supported by both producer and consumer.
- [ ] Generate the SBOM after the build determines the artifact version.
- [ ] Reconcile against the executable JAR and archive scanner.
- [ ] Record GAV, Git commit, JAR SHA-256, and SBOM tool/version.

### Container Image SBOM

- [ ] Scan the **final image**, not just the source directory or builder stage.
- [ ] Inventory base image OS/JRE/native packages.
- [ ] Ensure the Java archive cataloger reads nested Boot JARs when needed.
- [ ] Confirm the image scanner targets the exact image digest.
- [ ] Verify base image digest, runtime version, and platform.
- [ ] Scan every released architecture.
- [ ] Store the image SBOM bound to the manifest/index digest.
- [ ] Run vulnerability/license policy scans on the final image.
- [ ] Never reuse an old SBOM after changing the image/JAR/base.

### Supply Chain and CI

- [ ] Build/test one JAR and promote those exact bytes into the image.
- [ ] Store the Application SBOM, archive SBOM, and Container SBOM separately.
- [ ] Record the link Git commit ↔ JAR SHA ↔ image digest ↔ SBOM.
- [ ] Sign/attest SBOMs per policy when required.
- [ ] Store provenance/build toolchain separately when required.
- [ ] Maintain sufficient retention for releases, rollbacks, and audits.
- [ ] Update plugins, scanners, and advisory databases under change control.
- [ ] Validate schema and metadata before publishing.
- [ ] Never treat SBOM generation as the sole security gate.

## 20. Official Documentation

- CycloneDX – [Specification Overview](https://cyclonedx.org/specification/overview/): component model, metadata, dependencies, composition, and vulnerability representation.
- CycloneDX Maven Plugin – [Plugin Documentation](https://cyclonedx.github.io/cyclonedx-maven-plugin/): `makeBom`, `makeAggregateBom`, scope configuration, schemas, and artifact attachment.
- CycloneDX Maven Plugin – [makeBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html): compile/runtime/provided/test scopes and output configuration.
- CycloneDX Maven Plugin – [makeAggregateBom Goal](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeAggregateBom-mojo.html): aggregate reactor BOMs and module outputs.
- CycloneDX – [ECMA-424 Standard](https://ecma-international.org/publications-and-standards/standards/ecma-424/): the CycloneDX BOM standard.
- SPDX – [Specifications](https://spdx.dev/use/specifications/): SPDX 3.0 and earlier versions.
- Anchore Syft – [Java Package Analysis](https://oss.anchore.com/docs/capabilities/java/): Java archive cataloger, nested JAR scanning, and package metadata.
- Anchore Syft – [Package Catalogers](https://oss.anchore.com/docs/guides/sbom/catalogers/): cataloger differences for images and source directories.
- Anchore Syft – [Getting Started](https://oss.anchore.com/docs/guides/sbom/): generating SBOMs from container images, filesystems, and archives.
- Docker – [docker scout sbom](https://docs.docker.com/reference/cli/docker/scout/sbom/): scanning images/OCI archives and exporting JSON, SPDX, CycloneDX.
- Docker – [Docker Scout](https://docs.docker.com/scout/): image inventory and vulnerability analysis.
- Spring Boot 3.5 – [Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): executable JARs and `repackage`.
- Spring Boot 3.5 – [Executable Jar Nested Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html): `BOOT-INF/classes`, `BOOT-INF/lib`, and launcher layout.

**Remember:** An Application SBOM tells you **which Java packages compose the application according to the dependency/build model**; a Container image SBOM tells you **which packages are present in the final image filesystem**, including runtime and OS packages. With Spring Boot, generate a BOM from Maven/Gradle, verify the executable JAR, and then scan the final image. Link both with the Git commit, JAR checksum, and OCI digest so you know precisely which components belong to the application, which come from the base image, and which exact product each SBOM describes.