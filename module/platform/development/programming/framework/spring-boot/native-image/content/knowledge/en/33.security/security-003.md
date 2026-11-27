# Native Binaries Still Require Vulnerability Management and Dependency Scanning

## 1. Why does a native executable still carry dependency risk?

GraalVM Native Image creates an executable independent of the traditional JVM runtime, but that does not mean the application has eliminated all dependencies or is immune to security vulnerabilities. The binary still contains code from Java libraries, frameworks, runtime support, and may link against operating system libraries. The container image also includes a base image, CA certificates, native libraries, and other system files.

A vulnerability in Jackson, Spring Framework, an HTTP client, a database driver, or an image-processing library can still affect the native executable if the vulnerable code is included in the binary and reachable. Similarly, CVEs in glibc, OpenSSL, or other native libraries can have an impact if the executable or image uses those components.

In the **SPRING_BOOT_NATIVE_IMAGE** module, you need to maintain a dependency management workflow end-to-end across source, build, native binary, and container image. This lesson explains how to generate and read an SBOM, scan Java dependencies and system libraries, understand scanner limitations for native binaries, triage CVEs, update/rebuild, and integrate checks into CI/CD.

## 2. Native Image changes packaging, not the origin of vulnerabilities

Native compilation may eliminate some unreachable classes from the executable, but it does not automatically prove the remaining dependencies are safe. Risks include:

- Vulnerable code remains in the reachability graph.
- A vulnerability resides in a method only invoked along rare payloads/branches.
- Statically or dynamically linked native libraries have CVEs.
- The base image contains vulnerable operating system packages.
- Dependencies have outdated versions even though the JAR was turned into a binary.
- Packaged metadata or resources contain data that should not be distributed.
- The build toolchain or builder image has supply-chain vulnerabilities.

You cannot infer from a smaller binary size that the attack surface has been reduced proportionally. Reachability is a build property; exploitability also depends on code paths, input data, configuration, and the runtime environment.

## 3. Classifying dependencies to track

A native service has multiple dependency layers:

| Layer | Examples | Inspection source |
|---|---|---|
| Application dependencies | Jackson, Apache HttpClient, partner SDKs | Maven/Gradle dependency graph |
| Spring ecosystem | Spring Boot, Spring Framework, Spring Data | BOM/plugins and dependency reports |
| Native Image toolchain | GraalVM, Native Build Tools | Builder image/toolchain inventory |
| Native libraries | OpenSSL, zlib, database client libraries | ELF linkage, package inventory, SBOM |
| OS/runtime packages | glibc, CA certificates, timezone data | Base image package database |
| Build plugins/actions | Maven/Gradle plugins, CI actions | Plugin graph and CI supply chain |
| Generated artifacts | AOT output, metadata, generated source | Build manifest and artifact provenance |

Do not scan only the JAR file. If the final image contains native libraries or OS packages, you need a scanner capable of identifying those components. If the build stage and runtime stage differ, track both because they carry different risks and purposes.

## 4. Maven and Gradle dependency graphs

Before native compilation, capture the dependency graph in an inspectable form.

With Maven:

```bash
./mvnw dependency:tree
```

You can export the dependency list in a format suited to your project's plugins/reporting tools. Record both direct and transitive dependencies; many CVEs live in transitive libraries that the source code does not declare directly.

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To see which path pulls in a specific dependency:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

These commands help identify resolved versions, though they are not yet vulnerability scan results. Store dependency locks/BOMs and reports per commit to compare during upgrades.

## 5. Why must transitive dependencies also be scanned?

An application may only declare a Spring Boot starter, yet the starter pulls in many other libraries. A vulnerability can sit in a parser, compression library, logging implementation, or HTTP client at the transitive layer.

When a scanner reports a CVE:
1. Identify the artifact coordinates and actual version.
2. See which library pulls the dependency in.
3. Check the resolved version in runtimeClasspath.
4. Determine whether the artifact is present in the native binary or final image.
5. Inspect the features/code paths using the dependency.
6. Assess exploitability and impact.
7. Upgrade the dependency/BOM or apply a time-bound mitigation.

Do not ignore a CVE simply because a dependency is not declared directly. Also do not automatically upgrade a transitive library by overriding its version if that version is incompatible with the Spring Boot BOM or consuming dependencies.

## 6. An SBOM is an inventory of an artifact's components

A Software Bill of Materials (SBOM) describes the software components present in an artifact or set of artifacts. An SBOM can include:

- Component name and version.
- Package URL (PURL) or equivalent identifier.
- Supplier/publisher.
- License.
- Dependency relationships.
- Hashes or identifying metadata.
- Metadata about the generating tool and timestamp.

Common formats include SPDX and CycloneDX. Choose the format based on your scanner, registry, and organizational policy; ensure consumers can parse and link the SBOM to the exact artifact.

An SBOM does not by itself prove an artifact is secure. It is an inventory input for vulnerability analysis, license review, and supply-chain tracking. An SBOM missing components or not tied to the exact image digest diminishes its control value.

## 7. Generating an SBOM for Java dependencies

You can generate an SBOM from a Maven/Gradle project using a plugin or dedicated tool. Maven CycloneDX plugin example:

```bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom
```

Gradle CycloneDX plugin example:

```bash
./gradlew cyclonedxBom
```

Goal/task names, plugin versions, and output locations depend on configuration. Pin the plugin version in your build and verify the SBOM file is generated properly. Do not use unpinned plugin versions in production CI.

An SBOM from a project dependency graph typically describes resolved Java packages. It may not fully reflect system libraries copied into the container, linked native libraries, or the toolchain inside the builder image. Supplement it with SBOMs/image scans for the container and build environment.

## 8. SBOMs for native binaries and container images

A native executable is a binary file and no longer preserves the JAR/dependency graph structure in a way ordinary Java scanners can fully read. Therefore, your workflow should build inventories at multiple points:

- SBOM from the Maven/Gradle project to identify Java components.
- SBOM of the builder image/toolchain to manage the build environment.
- SBOM or package inventory of the final container image.
- Metadata linking the binary to its source revision and dependency lock.
- Native library linkage reports to supplement gaps when scanners do not detect everything.

Do not treat an SBOM from a JAR as a complete SBOM for the final native container. Native compilation changes packaging and may drop some code, but OS libraries and runtime files still must be tracked.

## 9. Scanners can miss dependencies inside binaries

Scanners typically identify components in different ways:
- Scanning Maven/Gradle manifests and lockfiles.
- Parsing JAR/package metadata.
- Scanning the OS image's package database.
- Recognizing binary files by signatures or version strings.
- Analyzing ELF dependencies and shared libraries.
- Matching SBOMs against vulnerability databases.

A scanner that only reads Maven manifests may not detect glibc or native libraries in the final image. An image scanner may detect OS packages but fail to accurately recover every Java component compiled into the binary.

Therefore, use multiple appropriate inventory sources and document coverage. Do not interpret "zero vulnerabilities" as "no vulnerabilities exist" if the scanner cannot detect certain dependency layers.

## 10. Scanning the final container image

The final image is the deployed artifact and must be scanned after building. The tool can be a scanner in your registry, CI, or organizational security platform.

A general workflow:

```text
Build native executable
        |
        v
Create final container image
        |
        v
Generate image SBOM
        |
        v
Scan OS + application components
        |
        v
Review vulnerabilities and policy
        |
        v
Sign/attest and promote image digest
```

Exact scan commands depend on the tool in use; there is no single syntax across all scanners. Configure the scanner to check OS packages, language packages where possible, native libraries, and image configuration.

Scan the exact image digest that will be released. If the image is rebuilt after scanning, the digest may change and prior scan results no longer represent the new artifact.

## 11. CVEs in Java dependencies still apply to native binaries

A CVE in a Java library does not disappear merely because bytecode was compiled into machine code. If the vulnerable code is included in the executable and the exploit path remains, the native application can still be affected.

For example, a parser handling untrusted data can still have a denial-of-service or memory exhaustion bug. Native Image does not automatically fix parser logic. Likewise, an authorization flaw in Spring code remains an application bug even though the executable contains no separate JAR.

When receiving a CVE:
- Identify the package/version in the dependency graph.
- Check the advisory and patched versions.
- Identify the APIs/features the application uses.
- Check reachability if reliable data is available, but do not use "unreachable" as an excuse to ignore it without evidence.
- Upgrade the version and run regression/native tests.
- Rebuild, rescan, and release a new artifact.

## 12. CVEs in the OS and native libraries

A binary may depend on shared libraries such as libc, libstdc++, OpenSSL, or vendor libraries. The final image also contains OS packages like the CA bundle and timezone database.

Determine whether the binary is dynamically or statically linked:

```bash
file orders-service
readelf -l orders-service
readelf -d orders-service
ldd orders-service
```

Use `ldd` only with trusted binaries and in a compatible environment. For untrusted binaries, prefer static ELF analysis. With static linking, a final image package scanner may not see libraries embedded inside the binary; you need SBOM/build provenance and tools supporting binary analysis.

Updating the base image does not necessarily update libraries statically linked into the executable. In that case, you must rebuild the binary using a toolchain containing the patched library, then build a new image.

## 13. The builder image is also part of the supply chain

Multi-stage builds typically strip compilers and build packages from the final image, yet the builder can still:
- Run malicious scripts or plugins.
- Resolve dependencies from untrusted repositories.
- Contain vulnerable GraalVM/JDK versions.
- Use compromised CI actions or build plugins.
- Leak credentials via build logs/cache/artifacts.

Managing the builder:
- Pin the builder image by digest.
- Scan the image and OS packages.
- Pin Maven/Gradle plugins and CI actions per policy.
- Use repository mirrors/allowlists.
- Supply minimal credentials only for the duration needed.
- Isolate caches by trust boundary.
- Store provenance for the native binary and image.

Do not scan only the runtime image and conclude the pipeline is safe. The build environment has the authority to produce artifacts and is therefore a critical part of the supply-chain threat model.

## 14. Reachability does not replace vulnerability management

Native Image can prune unreachable classes from the executable. This can reduce packaged code, but it does not replace updating dependencies.

Reasons include:
- Reachability can change when code, config, or profiles change.
- A seemingly unused class may be reachable via reflection or framework hooks.
- Scanners may not determine which specific code was eliminated.
- The vulnerability may reside in still-reachable code.
- A CVE may affect a shared library or OS package outside Java reachability.

If using reachability analysis to assist triage, archive the corresponding reports and build inputs. Do not create automated exception policies solely because a dependency appeared uncalled in one test run.

## 15. Assessing severity and exploitability

Not every CVE carries the same risk for a service. Triage should examine:

- Severity score and vendor advisory.
- Whether public exploits or active exploitation exist.
- Whether the dependency is present in the deployed artifact.
- Whether the code path is reachable from untrusted input.
- What privileges and network access the service runs with.
- Whether mitigations or safe configurations exist.
- Whether a compatible patch exists.
- The service's exposure and business impact.

Do not ignore a CVE merely because a scanner rates it "low" if it sits on a sensitive data-processing path. Conversely, do not block every release over an advisory that does not apply to the artifact without a documented verification process.

Triage must have an accountable owner, rationale, remediation deadline, and review conditions.

## 16. Vulnerability build gate policies

CI can enforce policies based on severity, exploitability, age, and artifact type. Example:

| Condition | Illustrative action |
|---|---|
| Critical with exploit affecting runtime | Block promotion/release |
| High with compatible patch | Create mandatory remediation within SLA |
| Medium without exploit, mitigation available | Track and set deadline |
| Finding inapplicable with evidence | Approved exception with expiry |
| Scanner cannot identify native components | Supplement inventory/tooling or document coverage gap |

This is an example policy, not a mandatory threshold for every organization. Security teams need to define SLAs and exception processes.

The gate should scan:
- Java dependency graph/SBOM.
- Builder image.
- Final container image.
- Native library inventory.
- Licenses/policies if applicable.
- Artifact signature/provenance prior to promotion.

## 17. Updating dependencies and rebuilding native artifacts

When a patch is available, update source/build configuration and regenerate the native executable. You cannot swap a JAR inside the container filesystem to update a library already compiled into the binary.

Workflow:
1. Identify affected direct/transitive dependencies.
2. Select a patched version compatible with the Spring Boot BOM.
3. Update lockfiles/BOMs/plugins as needed.
4. Run JVM unit/integration tests.
5. Run Spring AOT and native build.
6. Run relevant native integration tests.
7. Generate a new SBOM.
8. Scan the final image and builder image.
9. Attach digest/provenance and release.
10. Retain rollback artifacts per policy.

If the CVE is in a dynamically linked shared library, updating the runtime image may suffice in some cases, provided ABI/version compatibility is verified. If the library is statically linked, the executable must be rebuilt with the patched library.

## 18. Post-release vulnerability monitoring

Security scanning does not run just once at build time. New advisories can be published after an image has been deployed. You must retain SBOMs, image digests, and component inventories so scanners can re-evaluate running artifacts.

An ongoing workflow:
- Registry scan on push.
- Scheduled rescans of still-deployed images.
- Monitoring advisories from vendors/dependency maintainers.
- Mapping CVEs to service owners and image digests.
- Identifying which environments an image is running in.
- Creating remediation tickets/deadlines.
- Rebuilding and rolling out patches.
- Confirming old digests have been replaced or retired from environments.

If only mutable tags are recorded, it is hard to know which binary an instance is running. Use digests for accurate traceability.

## 19. SBOMs, provenance, and artifact signing

An SBOM states components; provenance states which source/build inputs produced an artifact; signatures verify the artifact came from a trusted publisher.

A release record should link:
- Source commit.
- Dependency lock/BOM.
- GraalVM/JDK and Native Build Tools versions.
- Builder image digest.
- Build arguments and profiles.
- Native executable hash.
- Final image digest.
- SBOM.
- Test reports and scan results.
- Signatures/attestations if supported by the pipeline.

Do not store an SBOM in isolation without linking it to an image digest. If an image is rebuilt, generate a new SBOM/provenance; never reuse reports from a previous digest.

## 20. Diagnosing false or incomplete findings

| Situation | Possible cause | Resolution |
|---|---|---|
| Scanner does not see Java dependencies in native binary | Code was compiled into the executable, no JAR manifest remains | Scan project dependency graph and SBOM in parallel |
| Scanner does not see glibc/OpenSSL | Static linking or missing package metadata | Inspect ELF, builder inventory, and binary SBOM |
| CVE reported on builder but absent from final image | Package only exists in the build stage | Document scope; still address build supply-chain risk |
| CVE reported on base image | OS package in final image | Update base image and retest |
| Scanner version differs from dependency lock | Scanner misidentification/missing metadata | Cross-check package URL, hash, and resolved graph |
| CVE claimed unreachable | Reachability report lacks full coverage | Archive evidence, review code paths and exception policy |
| Image was scanned but digest changed | Rebuild or tag overwrite | Rescan the exact release digest |
| Static library has patch but binary is old | Library was embedded in executable | Rebuild Native Image |

Do not dismiss a finding simply because a scanner does not understand the binary. Record the coverage gap and add appropriate data sources.

## 21. Hands-on lab: building a vulnerability workflow for Order API native

**Scenario:** Order API is built as a native executable, packaged in a distroless container, and released multiple times per week.

**Step 1 — Save the dependency graph.** Export the Maven/Gradle runtime dependency report and pin the BOM/lockfile.

**Step 2 — Generate Java SBOM.** Use a pinned CycloneDX/SPDX plugin; store the SBOM alongside the build ID and commit.

**Step 3 — Scan the builder.** Scan the GraalVM/JDK builder image, OS packages, and CI tooling per policy.

**Step 4 — Build native.** Run AOT/native compilation with a pinned toolchain; archive build logs and executable hash.

**Step 5 — Build the final image.** Use an appropriate minimal runtime base image, record the image digest, and generate the image SBOM.

**Step 6 — Scan native/runtime components.** Scan the final image, OS packages, shared libraries, and add ELF/linkage inventory where scanner coverage is incomplete.

**Step 7 — Triage CVEs.** Identify component, version, exploitability, reachability evidence, mitigations, and SLA.

**Step 8 — Build gate.** Block promotion according to approved policy; exceptions must have an owner, rationale, and expiry.

**Step 9 — Post-release monitoring.** Schedule rescans for running digests and create remediations when new advisories appear.

**Step 10 — Patch drill.** Upgrade a test dependency, rebuild the native binary, generate a new SBOM, scan, and promote the new digest.

Completion criteria: Java/native/system dependencies are inventoried; SBOMs are tied to artifacts; builder and final images are scanned; CVEs are triaged with owners/SLAs; native rebuilds and post-release rescans are repeatable.

## 22. Conclusion

Native Image does not eliminate vulnerability management responsibilities. Java dependencies can still contain exploitable code; native executables can depend on system libraries; builder images, compilers, and CI plugins are also part of the supply chain. Scanners that only read JARs or manifests are insufficient to evaluate the entire binary and final container.

Maintain dependency graphs and SBOMs for Java components, scan builder/final images, inspect native library linkage, link all results to image digests and provenance, and triage CVEs by exploitability and impact. When updating dependencies or system libraries, regenerate the native artifact, run tests, and rescan before promotion. Scheduled post-release rescans help detect new advisories in the exact images currently running.
