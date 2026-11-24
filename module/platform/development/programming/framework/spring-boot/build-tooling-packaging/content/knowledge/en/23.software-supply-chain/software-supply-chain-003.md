# Scanning Dependency Vulnerabilities and Reconciling Actual Versions in Artifacts

## 1. Why Must We Scan Both the Dependency Graph and the Artifact?

A Spring Boot application may declare only a few starters in Maven or Gradle, yet those starters pull in many *transitive dependencies*. The version written in the POM is not always the final version selected after applying the BOM, dependency management, profiles, exclusions, and conflict resolution.

When packaged as an executable JAR, Spring Boot typically places dependencies under **BOOT-INF/lib/**. An executable WAR places libraries under **WEB-INF/lib/** and may also include **WEB-INF/lib-provided/**. Therefore, to answer the question “which libraries and versions does the actual release contain?”, you must inspect the built archive itself, not just read the POM.

When packaging the application into a container image, the scope becomes even broader: the image may contain a JRE/JVM, OS packages, and native libraries from the run image. A dependency scanner looking only at the Maven graph cannot replace scanning the final image.

> **Three-layer verification process:**  
> **(1) Dependency graph** shows what the build tool resolved; **(2) artifact inventory** shows what the archive actually packaged; **(3) container image scan** shows both application libraries and OS/runtime packages present in the deployed image.

This lesson uses Java 17, Spring Boot 3.5.16, and Maven as the primary examples, with equivalent Gradle commands. Scanner plugins are pinned for reproducible examples, while CVE policies and vulnerability databases must be kept up to date at scan time.

### Learning Objectives

- Distinguish declared dependencies, resolved dependencies, dependencies packaged into JAR/WAR archives, and packages in container images.
- Use Maven dependency tree and Gradle dependencyInsight to determine final versions.
- Use OWASP Dependency-Check to detect published vulnerabilities in dependencies.
- Generate a CycloneDX SBOM to record components, versions, and dependency relationships.
- Use Trivy to scan JAR/WAR files, SBOMs, and container images.
- Read BOOT-INF/lib, WEB-INF/lib, WEB-INF/lib-provided, and META-INF/maven/**/pom.properties.
- Write a pure Java 17 program to list the GAV coordinates of nested JARs in an executable archive.
- Reconcile scanner outputs with actual versions, handle false positives, and upgrade dependencies safely.
- Establish CI quality gates and retain reports, SBOMs, image digests, and build evidence.

## 2. Four Types of Information to Distinguish

| Information type | Source | Question answered | Limitation |
|---|---|---|---|
| **Declared dependencies** | pom.xml, build.gradle(.kts), version catalog | Which libraries does the project request? | May omit explicit versions or hide transitive dependencies |
| **Resolved dependency graph** | Maven dependency:tree, Gradle dependencies/dependencyInsight | Which version did the build tool ultimately select and via which path? | Does not prove the component was packaged into the artifact |
| **Packaged components** | Nested JAR/WAR, pom.properties, SBOM, or archive-reading scanner | Which binaries does the release actually contain? | Shaded JARs or binaries missing metadata are harder to identify completely |
| **Runtime image components** | Trivy image scan, image SBOM, OCI metadata | Which OS packages, JRE, and application libraries are in the final container? | Does not replace runtime configuration checks and exploitability analysis |

### 2.1. Dependencies in the Graph That Are Not in the JAR

Examples:

- spring-boot-starter-test typically has test scope and is not packaged into the runtime JAR.
- Maven provided dependencies are not on the standard runtime classpath; an executable WAR may place some dependencies in WEB-INF/lib-provided/ to support embedded execution.
- Optional dependencies have different propagation rules to consumers than normal dependencies.
- A dependency excluded from one branch can still be pulled in via another branch.
- Libraries can be shaded/relocated into another JAR, removing their separate nested JAR structure.

Do not conclude “the scanner found a dependency in the POM, so that binary is definitely in the production archive.” Inspect scopes, packaging plugin settings, and the actual archive.

### 2.2. Components in the Image That Are Not in the Maven Graph

Examples:

- JRE/JVM provided by Paketo Java buildpacks.
- OpenSSL, libc, CA certificates, and OS packages from the run image.
- Native libraries added by buildpacks or image extensions.
- Tools/agents injected into the image via buildpack layers.

That is why the **final container image** must be scanned alongside the JAR/WAR. A Maven-generated SBOM typically describes components in the project graph; it does not automatically represent every OS package in the image.

## 3. Dependency Security Terminology

| Term | Meaning |
|---|---|
| **SCA (Software Composition Analysis)** | Analysis of third-party components, versions, licenses, and risks |
| **CVE** | Identifier for a publicly disclosed vulnerability |
| **CWE** | Classification of software weakness types |
| **CVSS** | Technical severity score for a vulnerability |
| **CPE** | Product/version identifier commonly used when matching vulnerabilities |
| **PURL** | Package URL, an ecosystem-standard package identifier |
| **SBOM** | Software Bill of Materials: inventory of components and relationships |
| **VEX** | Information on whether a vulnerability affects a specific product |
| **Fix version** | Version that contains a fix or falls outside the affected range |
| **False positive** | Scanner reports an issue, but the actual component/version is not affected |
| **False negative** | Vulnerability exists, but the scanner misses it or fails to link the component |

**Do not equate CVE, CVSS, and exploitability status.** A CVE is an identifier and CVSS is a severity score; neither tells you whether the application invokes the vulnerable code or whether the vulnerability is actively exploited in the wild. When prioritizing remediation, also check vendor advisories, CISA Known Exploited Vulnerabilities (KEV), network exposure, reachable code paths, and affected data.

### 3.1. Dependency Scanning Is Not Complete Security Testing

A dependency scanner focuses on **known vulnerabilities** in recognized components. It does not by itself prove:

- Application code has no SQL injection, authorization bugs, or business logic flaws.
- No secrets are committed or misconfigured.
- Every dependency has an acceptable license.
- Every binary is accurately identified when metadata is missing.
- No undisclosed vulnerabilities exist outside the database.
- Whether a CVE is exploitable given how the application uses the library.

Combine SCA with SAST, secret scanning, IaC/container misconfiguration scanning, DAST, or penetration testing as required.

## 4. How Does Maven Select the Actual Version?

### 4.1. BOM and dependencyManagement

The Spring Boot parent/BOM manages many dependency versions that have been tested together. A POM can declare a dependency without specifying a version:

§§§xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
§§§

Maven reads version management from the parent/BOM, resolves transitive dependencies, and applies mediation rules. A version written in a direct declaration is not always the final version across the entire graph; dependency management, direct dependencies, and transitive branches all affect the outcome.

**Do not upgrade an individual Spring dependency on your own just because a scanner suggests a higher version.** If the dependency belongs to the Spring Boot BOM, first check which Spring Boot patch release updates the corresponding dependency set. Overriding a single component can produce a framework combination outside Boot's compatibility matrix.

### 4.2. Inspecting the Resolved Dependency Graph

From the Maven project root:

§§§bash
# View the dependency hierarchy:
mvn dependency:tree

# Focus on runtime and show nodes omitted due to conflicts:
mvn dependency:tree -Dscope=runtime -Dverbose

# Filter for a specific dependency:
mvn dependency:tree -Dscope=runtime \
  -Dincludes=com.fasterxml.jackson.core:jackson-databind

# Save the graph:
mvn dependency:tree -Dscope=runtime -Dverbose \
  -DoutputFile=target/runtime-dependency-tree.txt
§§§

dependency:tree displays the hierarchy and versions actually used by the Maven build. With -Dverbose, the output shows nodes omitted due to conflicts and the selected version. Do not rely solely on direct dependency lines in the POM.

**Illustrative** output example:

§§§text
com.example:supply-chain-lab:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:3.5.16:compile
|  +- org.springframework.boot:spring-boot-starter:jar:3.5.16:compile
|  \- org.springframework:spring-webmvc:jar:<resolved-version>:compile
\- org.springframework.boot:spring-boot-starter-test:jar:3.5.16:test
   \- org.junit.jupiter:junit-jupiter:jar:<resolved-version>:test
§§§

`<resolved-version>` tokens are structural placeholders, not literal versions to copy. Actual versions depend on the BOM, profiles, dependency overrides, and build time.

### 4.3. Inspecting Effective POM and BOM Mismatches

§§§bash
# POM after parent inheritance, profiles, and property interpolation:
mvn help:effective-pom -Doutput=target/effective-pom.xml

# Check whether resolved dependency versions differ from dependencyManagement:
mvn dependency:analyze-dep-mgt

# Find used-but-undeclared or declared-but-unused dependencies:
mvn dependency:analyze
§§§

effective-pom helps you understand the actual version management. dependency:analyze-dep-mgt detects mismatches between resolved dependencies and dependencyManagement. dependency:analyze inspects bytecode to find dependencies that are used without being declared or declared without being used.

dependency:analyze may fail to recognize dependencies invoked via reflection, ServiceLoader, XML configuration, scripts, or plugin mechanisms. Never remove a dependency based solely on a warning without checking how the application uses it.

### 4.4. How Scopes Affect the Artifact

| Maven scope | Compile classpath | Runtime classpath | Packaging notes |
|---|---|---|---|
| compile (default) | Yes | Yes | Usually packaged in the executable JAR |
| runtime | Not needed for source compilation | Yes | Usually packaged in the executable JAR |
| provided | Yes | Not on standard Maven runtime classpath | Executable WAR may place it in WEB-INF/lib-provided/ |
| test | Yes during tests | No | Not packaged in the app runtime JAR |
| system | From local path | Per classpath config | Hard to reproduce; requires special review |
| optional | Per project declaration | May be present in current app | Not propagated to consumers like regular dependencies |

Scope is only part of the packaging rules. Inspect the Spring Boot Maven/Gradle plugin configuration and the resulting JAR/WAR file after building.

## 5. Reconciling Versions in a Spring Boot Executable JAR/WAR

### 5.1. Executable JAR Structure

The Spring Boot Maven/Gradle plugin typically creates an executable JAR with this structure:

§§§text
supply-chain-lab-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/supplychain/...
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-core-*.jar
    │   ├── jackson-databind-*.jar
    │   └── ... other runtime dependencies
    ├── classpath.idx       (if generated)
    └── layers.idx          (if layered packaging is enabled)
§§§

Application classes live in BOOT-INF/classes/; dependency JARs live in BOOT-INF/lib/. Spring Boot Loader handles this layout when running via java -jar.

**Reconciling versions:** nested JAR filenames typically follow artifactId-version.jar, but the filename is not the sole proof. You should also inspect the Maven metadata embedded inside each JAR and reconcile it with the dependency tree/SBOM.

### 5.2. Executable WAR Structure

§§§text
supply-chain-lab-1.0.0.war
├── META-INF/MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   │   └── ... dependency JARs
│   └── lib-provided/
│       └── ... dependencies for embedded execution
└── org/springframework/boot/loader/...
§§§

WEB-INF/lib/ holds standard dependencies. WEB-INF/lib-provided/ holds dependencies needed when running the WAR via an embedded container but not needed when deploying to a traditional servlet container. If the artifact is run in both modes, scan and verify the exact component set for each deployment mode.

### 5.3. Listing Nested Libraries with the JDK

Linux/macOS:

§§§bash
jar tf target/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'
§§§

Windows PowerShell:

§§§powershell
jar tf target/supply-chain-lab-1.0.0.jar |
  Select-String '^BOOT-INF/lib/'
§§§

For an executable WAR:

§§§bash
jar tf target/supply-chain-lab-1.0.0.war |
  grep -E '^WEB-INF/(lib|lib-provided)/'
§§§

These commands list archive paths and filenames. To inspect Maven metadata inside nested JARs, extract the libraries into a separate temporary directory:

§§§bash
mkdir -p target/archive-inspect
cd target/archive-inspect
jar xf ../supply-chain-lab-1.0.0.jar BOOT-INF/lib
find BOOT-INF/lib -name '*.jar'
§§§

Each JAR may contain:

§§§text
META-INF/maven/<groupId>/<artifactId>/pom.properties
META-INF/maven/<groupId>/<artifactId>/pom.xml
§§§

pom.properties typically records groupId, artifactId, and version. Some binaries lack this metadata; shaded/uber JARs may contain multiple descriptors or have metadata stripped. Handle UNKNOWN entries and cross-check with another scanner.

## 6. Java 17: Program to Inventory Versions in Nested JARs

The following program uses **only JDK 17**, with no extra dependencies. It opens an executable Boot JAR/WAR as a ZIP archive, finds nested JARs in BOOT-INF/lib/, WEB-INF/lib/, and WEB-INF/lib-provided/, reads META-INF/maven/**/pom.properties, and prints GAV coordinates alongside their archive paths.

Create BootArchiveInventory.java:

§§§java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

public final class BootArchiveInventory {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                "Usage: java BootArchiveInventory <app.jar|app.war>");
            System.exit(2);
        }

        try (ZipFile archive = new ZipFile(Path.of(args[0]).toFile())) {
            List<ZipEntry> libraries = new ArrayList<>();
            var entries = archive.entries();

            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                String name = entry.getName();

                boolean nestedLibrary =
                    name.startsWith("BOOT-INF/lib/")
                    || name.startsWith("WEB-INF/lib/")
                    || name.startsWith("WEB-INF/lib-provided/");

                if (!entry.isDirectory()
                        && nestedLibrary
                        && name.endsWith(".jar")) {
                    libraries.add(entry);
                }
            }

            libraries.sort(Comparator.comparing(ZipEntry::getName));
            System.out.println(
                "Nested dependency archives: " + libraries.size());

            for (ZipEntry library : libraries) {
                List<String> coordinates =
                    readCoordinates(archive.getInputStream(library));

                if (coordinates.isEmpty()) {
                    System.out.println(
                        "UNKNOWN\t" + library.getName());
                } else {
                    for (String gav : coordinates) {
                        System.out.printf(
                            "%s\t%s%n", gav, library.getName());
                    }
                }
            }
        }
    }

    private static List<String> readCoordinates(
            InputStream nestedJarBytes) throws IOException {

        List<String> result = new ArrayList<>();

        try (ZipInputStream nested =
                new ZipInputStream(nestedJarBytes)) {

            ZipEntry entry;

            while ((entry = nested.getNextEntry()) != null) {
                String name = entry.getName();

                if (name.startsWith("META-INF/maven/")
                        && name.endsWith("/pom.properties")) {

                    Properties properties = new Properties();
                    properties.load(nested);

                    String groupId = properties.getProperty("groupId");
                    String artifactId =
                        properties.getProperty("artifactId");
                    String version = properties.getProperty("version");

                    if (groupId != null
                            && artifactId != null
                            && version != null) {
                        result.add(
                            groupId + ":" + artifactId + ":" + version);
                    }
                }
            }
        }

        return result;
    }
}
§§§

Compile and run with Java 17:

§§§bash
javac BootArchiveInventory.java
java BootArchiveInventory target/supply-chain-lab-1.0.0.jar
§§§

For a WAR:

§§§bash
java BootArchiveInventory target/supply-chain-lab-1.0.0.war
§§§

Output **depends on the exact built artifact**; illustrative example:

§§§text
Nested dependency archives: <count>
org.springframework.boot:spring-boot-*:3.5.16    BOOT-INF/lib/spring-boot-*.jar
org.springframework:spring-core:<resolved>      BOOT-INF/lib/spring-core-<resolved>.jar
com.fasterxml.jackson.core:jackson-databind:<resolved>    BOOT-INF/lib/jackson-databind-<resolved>.jar
§§§

`<count>` and `<resolved>` are illustrative placeholders, not literal stdout. This code **inventories metadata**, it does not scan for CVEs. If a JAR has no pom.properties, the code prints UNKNOWN; inspect the filename, manifest, SBOM, Trivy JSON, or release source to investigate. For a shaded JAR containing merged classes from multiple components, a single descriptor cannot fully represent every shaded library.

## 7. OWASP Dependency-Check: Scanning CVEs in Maven Dependencies

OWASP Dependency-Check is an SCA tool that identifies components and checks them against publicly disclosed vulnerabilities, including data from the National Vulnerability Database (NVD). The Maven plugin provides the check goal per project and aggregate to consolidate modules across a reactor.

### 7.1. Configuring the Maven Plugin

Example pinning org.owasp:dependency-check-maven:13.0.0. This version requires Maven 3.8.1+ and JDK 11+; the example project uses Java 17 and Maven 3.9.x.

Add to build/plugins in the POM:

§§§xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>13.0.0</version>
    <configuration>
        <!-- Fail when CVSS >= 7.0; illustrative policy. -->
        <failBuildOnCVSS>7.0</failBuildOnCVSS>
        <formats>
            <format>HTML</format>
            <format>JSON</format>
        </formats>
    </configuration>
    <executions>
        <execution>
            <id>dependency-vulnerability-check</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
§§§

With this configuration, mvn verify invokes the check goal. HTML/JSON reports are typically written to target/. failBuildOnCVSS compares against the chosen threshold; if a finding meets or exceeds it, the build can fail.

**Note:** the default failBuildOnCVSS is 11, whereas standard CVSS ranges from 0–10, so the default will not fail a build on CVSS alone. Configure a threshold matching your policy; never assume that findings in a report automatically mean the pipeline blocked the release.

### 7.2. Running the Scan and Viewing Reports

§§§bash
# Run the goal directly:
mvn dependency-check:check

# Run the full lifecycle up to verify:
mvn clean verify
§§§

Common reports:

§§§text
target/dependency-check-report.html
target/dependency-check-report.json
§§§

Filenames may vary depending on outputDirectory, report formats, and plugin version. Read the goal logs to confirm the actual paths.

In the report, focus on the identified component/version, CVE/advisory, severity/CVSS, affected version range, fixed version, dependency path, and the evidence used by the analyzer.

### 7.3. NVD API Key and Cache

The first run can take considerable time because the plugin downloads and processes NVD data. OWASP Dependency-Check recommends maintaining a cache and considering a data mirror for operational integration.

If your organization provides an NVD API key, store the credential in Maven settings.xml under a server id and use Maven's password encryption mechanism; then configure the plugin to reference nvdApiServerId. Never write the API key directly in the POM, CI scripts, or command-line arguments that may show up in process logs. When using -X, avoid exposing credentials in debug output.

### 7.4. Suppression: Use Only for Investigated Findings

False positives can occur when a scanner misidentifies a component/version or library metadata is incomplete. Dependency-Check supports a suppression file, but suppressions must be controlled:

- Specify the exact misidentified package/CVE/version.
- Document the rationale and technical evidence.
- Assign a responsible owner and a review date.
- Narrow the scope; avoid ignoring an entire broad group/artifact unnecessarily.
- Remove the suppression when the component or advisory changes.

**Never suppress just to turn the build green** without verifying the component, version, and impact. If a finding is valid, upgrade the dependency or apply a verifiable mitigation.

### 7.5. Multi-Module Maven

In a multi-module reactor, dependency-check:check can generate per-module reports. The aggregate goal consolidates dependencies across child projects. Choose the goal matching your reactor structure and retain reports for that exact build; do not scan only the root POM and assume every module was analyzed.

## 8. CycloneDX: Generating an SBOM to Know What a Release Contains

**An SBOM is not a vulnerability scanner.** It is a structured inventory of components that can include versions, suppliers, identifiers, and dependency relationships. Scanners can consume an SBOM to match against vulnerability databases.

The CycloneDX Maven plugin generates a BOM containing direct and transitive dependencies. Example pinning 2.9.3, supporting CycloneDX 1.6:

§§§xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>generate-cyclonedx-bom</id>
            <phase>package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <outputFormat>json</outputFormat>
        <includeTestScope>false</includeTestScope>
    </configuration>
</plugin>
§§§

For a single module, the makeBom goal generates an SBOM for that module. In a multi-module reactor, use makeAggregateBom to produce an aggregate BOM at the build root. The default output is typically target/bom.json; check outputDirectory/outputName if customized in the POM.

Run:

§§§bash
mvn cyclonedx:makeBom
§§§

Or mvn clean package if execution is bound to the package phase.

### 8.1. Maven SBOM and Image SBOM Are Different

| SBOM | Typically describes | Should not be assumed to contain |
|---|---|---|
| Maven/CycloneDX makeBom | Dependencies per the Maven graph and configured scopes | All OS packages in the run image |
| Trivy JAR/WAR scan | Java components recognized inside the archive and nested JARs | Every OS package |
| Trivy image SBOM | Components recognized in the final OCI image, including OS and language packages | Full source dependency graph if metadata is missing |
| Aggregate multi-module SBOM | Components across multiple Maven modules | Tools/plugins/runtimes outside the BOM scope |

For container releases, retain both the **Maven SBOM and image SBOM**, or an SBOM generated directly from the image per policy. They answer two different questions: the project's graph and the final image's contents.

## 9. Trivy: Scanning JAR/WAR Files, SBOMs, and Container Images

Trivy supports Java JAR/WAR/PAR/EAR archives, pom.xml, and Gradle lockfiles. For JARs, Trivy reads pom.properties/MANIFEST.MF and can recognize inner JARs. When you need detailed nested dependency paths, use the JSON report because the table format may only display the root archive name.

### 9.1. Scanning the POM/Source Directory

§§§bash
trivy fs --scanners vuln .
§§§

Trivy can analyze the POM and dependency files in the project to build an inventory and find vulnerabilities. For Maven, POM analysis may require access to local/remote repositories to resolve metadata. If offline mode is enabled, dependencies missing locally may be skipped; the vulnerability database must still be updated.

### 9.2. Scanning the Executable JAR Directly

After running mvn clean package:

§§§bash
trivy fs --scanners vuln \
  --format json \
  --output target/trivy-jar-report.json \
  target/supply-chain-lab-1.0.0.jar
§§§

For an executable WAR:

§§§bash
trivy fs --scanners vuln \
  --format json \
  --output target/trivy-war-report.json \
  target/supply-chain-lab-1.0.0.war
§§§

Trivy's Java analyzer can inspect inner JARs. The JSON report is useful when reconciling BOOT-INF/lib/... or WEB-INF/lib/... against the application inventory.

### 9.3. Scanning the Final Container Image

If the application is packaged into an image:

§§§bash
trivy image --scanners vuln \
  --format json \
  --output target/trivy-image-report.json \
  supply-chain-lab:1.0.0
§§§

This command scans vulnerabilities in the image, covering OS packages and language-specific components recognized by Trivy. For multi-architecture images, specify the target platform when needed, such as --platform linux/arm64; do not assume linux/amd64 results represent an image running on ARM.

### 9.4. Generating and Scanning a Container Image SBOM

§§§bash
trivy image \
  --format cyclonedx \
  --output target/image-sbom.cdx.json \
  supply-chain-lab:1.0.0

trivy sbom target/image-sbom.cdx.json
§§§

By default, Trivy's CycloneDX output is an SBOM; vulnerability findings are not automatically embedded in that SBOM. If you need vulnerability data exported alongside a CycloneDX report, configure the scanner per Trivy documentation and clarify the file's purpose.

An SBOM created by another tool may lack custom metadata that Trivy uses to identify certain packages accurately. When SBOM scan results differ from an image/JAR scan, compare component identifiers, paths, and source metadata.

## 10. Complete Maven Java 17 Example for Running a Scan Pipeline

Let's create a minimal web application so we have a real executable JAR for the dependency graph, Dependency-Check, CycloneDX, archive inventory, and Trivy.

### 10.1. Project Structure

§§§text
supply-chain-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/supplychain/
    │   ├── SupplyChainApplication.java
    │   └── StatusController.java
    └── test/java/com/example/supplychain/
        └── StatusControllerTest.java
§§§

The example pins Spring Boot 3.5.16, Java 17, OWASP Dependency-Check 13.0.0, and CycloneDX Maven plugin 2.9.3. These versions are for illustration; before using them in a real project, verify compatibility and your organization's version policy.

### 10.2. pom.xml

§§§xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>supply-chain-lab</artifactId>
    <version>1.0.0</version>
    <name>Supply Chain Lab</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.owasp</groupId>
                <artifactId>dependency-check-maven</artifactId>
                <version>13.0.0</version>
                <configuration>
                    <failBuildOnCVSS>7.0</failBuildOnCVSS>
                    <formats>
                        <format>HTML</format>
                        <format>JSON</format>
                    </formats>
                </configuration>
                <executions>
                    <execution>
                        <id>dependency-vulnerability-check</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <outputFormat>json</outputFormat>
                    <includeTestScope>false</includeTestScope>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-cyclonedx-bom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
§§§

The Spring Boot plugin builds the executable JAR. Dependency-Check check runs at verify; CycloneDX makeBom runs at package. The CVSS 7.0 threshold is an illustrative policy only: projects must select thresholds based on risk, product type, and remediation SLAs.

### 10.3. Main Class

SupplyChainApplication.java:

§§§java
package com.example.supplychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SupplyChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupplyChainApplication.class, args);
    }
}
§§§

### 10.4. Controller with Deterministic Response

StatusController.java:

§§§java
package com.example.supplychain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "supply-chain-lab: OK\n";
    }
}
§§§

### 10.5. Unit Test

StatusControllerTest.java:

§§§java
package com.example.supplychain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusControllerTest {

    @Test
    void returnsStableStatus() {
        assertEquals(
            "supply-chain-lab: OK\n",
            new StatusController().status()
        );
    }
}
§§§

This is a unit test for the controller; it does not start an HTTP server. It verifies output logic and does not replace artifact scanning or container smoke testing.

### 10.6. Build and Generate Reports

From the root containing the POM:

§§§bash
java -version
mvn -version
mvn clean verify
§§§

Once the build finishes, typical outputs include:

§§§text
target/supply-chain-lab-1.0.0.jar
target/bom.json
target/dependency-check-report.html
target/dependency-check-report.json
target/runtime-dependency-tree.txt   (if tree was saved)
§§§

Report filenames depend on plugin configuration. If Dependency-Check finds issues meeting the threshold, mvn verify may end with BUILD FAILURE; the reports should still be retained for investigation. A build failing due to a CVE **does not mean compilation/packaging failed**.

### 10.7. Run Inventory and Trivy

§§§bash
# View the resolved graph:
mvn dependency:tree -Dscope=runtime -Dverbose \
  -DoutputFile=target/runtime-dependency-tree.txt

# List nested libraries:
jar tf target/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'

# Inventory GAVs with Java 17:
javac BootArchiveInventory.java
java BootArchiveInventory target/supply-chain-lab-1.0.0.jar

# Scan the executable JAR:
trivy fs --scanners vuln target/supply-chain-lab-1.0.0.jar

# Scan the Maven SBOM:
trivy sbom target/bom.json
§§§

If a container image was built:

§§§bash
trivy image --scanners vuln supply-chain-lab:1.0.0
§§§

Results depend on scan date, scanner version, vulnerability database, and artifact contents. Never hard-code “0 vulnerabilities” as expected sample output for an application with real dependencies.

### 10.8. Smoke-Test the Application

Run the JAR:

§§§bash
java -jar target/supply-chain-lab-1.0.0.jar
§§§

From another terminal, once Spring Boot is ready:

§§§bash
curl -fsS http://localhost:8080/status
§§§

The HTTP body returned by the controller is **exact**:

§§§text
supply-chain-lab: OK
§§§

The body has a trailing newline. Spring Boot startup logs may appear on the console. Smoke testing confirms the artifact starts; it does not prove dependencies have no CVEs.

## 11. Reconciling Results Across the Three Layers

After running the graph, archive inventory, and image scan, build a comparison table:

| Component | Maven resolved graph | Boot JAR/WAR | Container image | What to check |
|---|---|---|---|---|
| spring-core | Present with resolved version | Nested JAR in BOOT-INF/lib | Java component present | Compare GAV and CVEs |
| jackson-databind | Present if pulled in | Present/absent depending on runtime graph and packaging | Present/absent per artifact | Check transitive path |
| JUnit Jupiter | Test scope | Typically absent | Typically absent | If seen in runtime artifact, check packaging |
| Servlet container | Depends on starter/scope | WAR may have WEB-INF/lib or lib-provided | May live in Java layer | Determine embedded vs. external |
| Java runtime | Not a normal Maven dependency | Not necessarily inside the JAR | May live in buildpack launch layer | Scan image to see runtime |
| OpenSSL/CA packages | Not in Maven graph | Not in JAR | May live in OS base layers | Scan image OS packages |

### 11.1. Signs of Version Skew

**Scenario A — graph and archive match:** the resolved version appears in BOOT-INF/lib; this is the normal state.

**Scenario B — dependency is in the graph but missing from the archive:** check test/provided scope, optional flags, exclusions, plugin packaging, and stale artifacts. Do not immediately conclude the scanner missed a component.

**Scenario C — archive contains a JAR absent from the graph:** check manually copied nested dependencies, custom plugins, local modules, shaded/uber JARs, WEB-INF/lib-provided, or stale archives.

**Scenario D — filename and pom.properties differ:** the artifact may have been renamed/repackaged, contain an old descriptor, be a shaded JAR, or have wrong metadata. Record the checksum, check the repository source, and compare against resolved coordinates.

**Scenario E — image scan has OS CVEs absent from the Maven report:** these typically come from the run image, buildpack runtime layer, or native OS packages. Update the base/run image or compatible base packages; editing the POM will not fix every OS finding.

### 11.2. Distinguishing the Tools

- Maven dependency:tree: dependency tree and versions resolved by Maven.
- Maven dependency:analyze: dependencies used-but-undeclared or declared-but-unused.
- Maven dependency:analyze-dep-mgt: resolved versions differing from dependencyManagement.
- OWASP Dependency-Check: matches components against vulnerability advisories.
- CycloneDX: records component inventory and dependency relationships.
- Trivy: scans filesystems, JAR/WAR archives, SBOMs, and images per supported scanners.

No single command replaces all of them.

## 12. Gradle: Viewing runtimeClasspath, Locking Versions, and Verifying Artifacts

### 12.1. Viewing the Dependency Graph

§§§bash
# Runtime graph:
./gradlew dependencies --configuration runtimeClasspath

# Why a dependency was selected:
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath

# Compile graph:
./gradlew dependencies --configuration compileClasspath
§§§

dependencyInsight explains version selection reasons, constraints, and branches requesting the dependency. It is an essential tool when a BOM, version catalog, or transitive dependencies cause a different version to be selected than expected.

### 12.2. Dependency Locking

Gradle supports dependency locking to record resolved versions. Example in build.gradle:

§§§groovy
dependencyLocking {
    lockAllConfigurations()
}
§§§

After configuring, resolve the needed configurations and write the lock state:

§§§bash
./gradlew dependencies --write-locks
./gradlew build
§§§

Lock files keep builds reusing resolved versions and prevent dynamic versions from shifting between builds. Locking does **not** prove an artifact is safe or free of CVEs; it only pins dependency selection.

### 12.3. Dependency Verification

Gradle dependency verification supports checksums/signatures to verify the integrity and origin of downloaded artifacts:

§§§bash
./gradlew --write-verification-metadata sha256 help
§§§

The bootstrap command generates gradle/verification-metadata.xml. You must review the diff and verify checksums/signatures from trusted sources before accepting the metadata. Bootstrapping from a compromised repository can record the checksum of a malicious binary itself.

**Dependency verification differs from vulnerability scanning:** checksums/signatures verify whether an artifact has trusted content/origin; SCA checks components/versions against a known-vulnerability database. Both are needed when policy requires them.

### 12.4. Scanning the Gradle Artifact

After bootJar builds the archive:

§§§bash
./gradlew clean test bootJar

jar tf build/libs/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'

trivy fs --scanners vuln build/libs/supply-chain-lab-1.0.0.jar
§§§

The output path depends on archiveBaseName, archiveVersion, classifier, and Gradle configuration. Reconcile runtimeClasspath against BOOT-INF/lib of the exact JAR being released, not an older artifact in build/libs.

## 13. Evaluating Findings and Choosing Remediation

A high-CVSS finding does not automatically mean the application is exploitable; a low-CVSS finding does not automatically mean it is safe. Evaluate:

1. Is the component/version actually present in the deployed artifact/image?
2. Does the version fall within the advisory's affected range?
3. Is there a fixed version or vendor patch?
4. Is the vulnerable code path called by the application?
5. Is the endpoint exposed to the Internet or only to internal networks?
6. Is the vulnerability in CISA KEV or does a public exploit exist?
7. Are feasible mitigations available while waiting for a patch?
8. Will the upgrade break the Java baseline, Spring Boot compatibility, APIs, or serialization behavior?

### 13.1. Remediation Order

- **Confirm the component:** GAV, PURL, version, archive path, and checksum.
- **Confirm the advisory:** CVE, affected versions, fixed version, and release notes.
- **Find the dependency path:** direct or transitive, and which module pulls it in.
- **Select the fix:** upgrade the direct dependency, parent/BOM, starter, or remove an unnecessary dependency.
- **Test compatibility:** compile, unit/integration tests, smoke tests, and regression tests.
- **Rebuild:** never patch a JAR directly inside target/ and release it.
- **Rescan the artifact/image:** prove the new version is present and the finding is resolved.
- **Retain evidence:** reports, SBOM, commit, image digest, owner, and scan timestamp.

### 13.2. Example: Upgrading a Transitive Dependency

Suppose a report indicates org.example:example-parser is pulled in by a starter. Do not add a random version to the POM. Follow this sequence:

1. Run mvn dependency:tree -Dverbose -Dincludes=org.example:example-parser.
2. Identify the starter or direct dependency pulling in the component.
3. Check which version the Spring Boot BOM manages.
4. Check for a Spring Boot patch release or upstream release that fixes the vulnerability.
5. Prefer upgrading the BOM/parent accordingly.
6. If an override is unavoidable, document the rationale and test compatibility.
7. Rebuild, verify the version in BOOT-INF/lib, and rescan the JAR/image.

For framework dependencies, upgrading the entire tested framework version set is generally safer than overriding a single core component yourself.

### 13.3. Suppression Is Not Remediation

Suppression only adjusts how a scanner reports a finding; it **does not modify the binary** and does not patch the CVE. When using a suppression, record the false-positive justification or risk-acceptance rationale, scope it tightly to the exact package/version/CVE, require an approver, and set a review schedule. Never use broad suppressions just to make CI green.

## 14. Sources of False Positives and False Negatives

| Cause | Consequence | Investigation step |
|---|---|---|
| Inaccurate CPE match | False positive | Check GAV/PURL, vendor, version, and advisory |
| JAR missing pom.properties/manifest | Unidentified or misidentified version | Cross-check filename, repository, checksum, and SBOM |
| Shaded/uber JAR | One archive contains code from multiple components with incomplete metadata | Inspect shading config, SBOM, and analyzer |
| Vendor backported patch | Scanner may evaluate against upstream version without reflecting the patch | Read vendor advisory/package metadata |
| Outdated vulnerability DB | New findings do not appear yet | Update database and record scan timestamp |
| Scanner lacks format support | Package skipped | Scan with another tool and inspect the archive |
| Scope differs between POM and archive | Findings do not match expectations | Reconcile dependency tree, scopes, and BOOT-INF/lib |
| Manually copied dependency | Missing from the graph | Inventory the archive and trace binary origin |
| OS package in image | Absent from Maven report | Scan the final container image |
| Test/dev dependency | Present in source graph but absent from runtime artifact | Check scope and scanner policy |
| Overly broad suppression | Hides real findings | Review suppressions and remove stale rules |

**Never treat “0 vulnerabilities” as proof that software is secure.** The result only means the scanner found no issues given the database, analyzers, metadata, and scope of that particular scan.

## 15. CI/CD Integration: Blocking the Right Things and Retaining Evidence

A Spring Boot release pipeline can follow this order:

§§§text
1. Resolve dependencies
        |
2. Compile + unit/integration tests
        |
3. Generate executable JAR/WAR
        |
4. Dependency-Check + CycloneDX SBOM
        |
5. Inventory nested libraries and compare resolved versions
        |
6. Trivy scan JAR/WAR and SBOM
        |
7. Build OCI image
        |
8. Trivy scan final image (OS + application components)
        |
9. Review findings / enforce policy
        |
10. Publish immutable image digest + reports + SBOM
        |
11. Deploy the verified digest
§§§

### 15.1. Suggested Quality Gates

| Gate | Sample condition | Action |
|---|---|---|
| Build correctness | Compile/test/package succeed | Stop if failing |
| Dependency policy | No unapproved unresolved version conflicts | Investigate BOM/constraints |
| Vulnerability threshold | No findings meeting policy threshold | Fail or require approval |
| Critical/KEV | Actively exploited component or policy-banned risk | Block release per policy |
| Artifact consistency | GAV/versions in archive match resolved graph per scope | Fail on unexplained mismatch |
| SBOM | BOM generated for the exact build/artifact | Retain as release evidence |
| Image scan | OS/runtime/app findings pass policy | Block or create owner-approved exception |
| Integrity | Digest/checksum and provenance retained | Deploy only verified artifacts |
| Runtime smoke test | App starts and probe endpoint succeeds | Do not deploy if failing |

The CVSS >= 7.0 threshold in the POM is only an example. Organizations should incorporate exploitability, exposure, asset criticality, and remediation timelines. Never let a single numeric threshold replace risk review.

### 15.2. Files to Retain per Release

§§§text
release-evidence/
├── runtime-dependency-tree.txt
├── effective-pom.xml
├── dependency-check-report.html
├── dependency-check-report.json
├── bom.json
├── trivy-jar-report.json
├── trivy-image-report.json
├── image-sbom.cdx.json
├── artifact-sha256.txt
└── image-digest.txt
§§§

Report filenames and counts depend on the pipeline; the goal is end-to-end traceability from image digest back to source/build, dependency versions, scanner databases, and finding triage decisions.

### 15.3. Multi-Module Maven

In a multi-module reactor:

- Run dependency:tree in the target module to inspect its graph.
- dependency-check:aggregate can produce a consolidated report; keep per-module reports as well when identifying owners.
- CycloneDX makeAggregateBom consolidates modules in the reactor.
- Artifact inventory must run against the **exact executable JAR/WAR** of the released app.
- Never use an aggregate BOM as the sole proof that every binary was packaged into the app.
- When multiple applications are released independently, store separate SBOMs and image digests for each app.

## 16. Common Issues and Fixes

| Symptom | Common cause | Fix |
|---|---|---|
| dependency:tree shows a different version than the POM | BOM, mediation, or direct override | Check -Dverbose, effective POM, and dependency path |
| Dependency missing from BOOT-INF/lib | Test/provided scope, exclusion, or stale artifact | Check scope, exact JAR, and packaging plugin |
| JAR contains a library missing from the graph | Manual copy, shading, local module, or stale archive | Check plugins, build inputs, and checksums |
| Dependency-Check does not run during mvn package | Goal is bound to verify | Run mvn verify or invoke the goal directly |
| First scan takes very long | Downloading and processing vulnerability database | Use cache/mirror and supply API key securely |
| Dependency-Check reports duplicate findings | Same component appears via multiple paths | Group by GAV/CVE and inspect dependency paths |
| Trivy JAR fails to identify version | Missing pom.properties/manifest | Check archive, filename, SBOM, and hash |
| Trivy image reports OS CVEs absent from POM | Run image/OS package | Upgrade builder/run image or base packages |
| trivy sbom differs from image scan | SBOM lacks properties or targets a different artifact | Regenerate SBOM from the scanned image and compare digests |
| CVE has no fixed version | Patch not released yet or advisory outdated | Check vendor guidance, mitigations, and monitor |
| Dependency upgrade causes compile/runtime error | Version incompatible with framework/API | Upgrade matching BOM/Boot patch and run regression tests |
| Build fails due to failBuildOnCVSS | Finding reached threshold | Investigate finding; do not raise threshold to hide it |
| Report missing JSON | Only HTML configured or wrong output format | Check formats and plugin version |
| SBOM lacks OS packages | SBOM generated from Maven graph | Generate SBOM from the final container image |
| Scan passes yet deployed image is still outdated | Wrong tag/digest deployed | Compare image digest against release record |
| New CVEs appear after deployment | Database/advisories updated | Rescan released SBOMs/images |
| Dependency verification fails checksum | Binary differs from trusted checksum | Stop using it and verify source; do not auto-accept new checksum |

## 17. Pre-Release Checklist

- [ ] Exact executable JAR/WAR to be released identified.
- [ ] Maven runtime verbose dependency tree or Gradle runtimeClasspath inspected.
- [ ] BOM, effective POM, and version overrides checked.
- [ ] Direct/transitive dependency paths identified for key findings.
- [ ] OWASP Dependency-Check executed with updated database and explicit threshold.
- [ ] CycloneDX SBOM generated and retained with the build.
- [ ] BOOT-INF/lib, WEB-INF/lib, and WEB-INF/lib-provided inventoried as applicable.
- [ ] Versions in the archive reconciled against the resolved graph.
- [ ] Actual JAR/WAR scanned, not just the POM.
- [ ] Final container image scanned for OS/JRE/runtime packages.
- [ ] Findings evaluated against advisories, fixed versions, reachability, and exposure.
- [ ] Suppressions have rationale, owner, and review date.
- [ ] Rebuilt and rescanned after upgrading dependencies.
- [ ] Reports, SBOM, checksums, and image digest retained.
- [ ] Unit/integration tests and artifact/image smoke tests executed.
- [ ] Only the verified image digest deployed.

**Conclusion:** To know whether a Spring Boot application has vulnerable dependencies, combine **the resolved dependency graph**, **the actual binary versions in the JAR/WAR**, and **the components inside the container image**. Maven/Gradle tell you which versions were selected; OWASP Dependency-Check and Trivy match against vulnerability data; CycloneDX captures inventory; and reading nested archives proves the artifact packaged the expected versions. Only when all three layers align can a team trust that the release has been thoroughly scanned and traced.

### Official Documentation

- [Apache Maven Dependency Plugin — dependency tree and dependency analysis](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Spring Boot — Executable JAR and nested dependencies](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [OWASP Dependency-Check Maven Plugin — Usage](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/index.html)
- [OWASP Dependency-Check Maven Plugin — Configuration](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/configuration.html)
- [OWASP Dependency-Check — Plugin goals and requirements](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/plugin-info.html)
- [CycloneDX Maven Plugin — SBOM generation](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
- [CycloneDX — Specification overview](https://cyclonedx.org/specification/overview/)
- [Trivy — Java package coverage](https://trivy.dev/docs/latest/guide/coverage/language/java/)
- [Trivy — Filesystem scanning](https://trivy.dev/docs/latest/guide/target/filesystem/)
- [Trivy — Container image scanning](https://trivy.dev/docs/latest/guide/target/container_image/)
- [Trivy — SBOM generation and scanning](https://trivy.dev/docs/latest/supply-chain/sbom/)
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [NIST — National Vulnerability Database](https://nvd.nist.gov/)
- [CISA — Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)