# Generating SBOMs and Controlling Artifact Provenance

An organization deploys a Java/Spring Boot service to Azure Kubernetes Service (AKS). The application uses Maven, several Azure SDK libraries, a Java base image, numerous transitive dependencies, and pushes container images to Azure Container Registry (ACR). One day, the security team receives a vulnerability notice for a JSON library. The development team checks `pom.xml` and does not see it listed: it may have been pulled in via a transitive dependency, repackaged inside a library, or included in a container image component. Even after finding the dependency, the next question is: **was the running image genuinely built from an approved commit, by a trusted pipeline, without tampering after the build?**

Two categories of evidence answer these questions:

- **Software Bill of Materials (SBOM):** an inventory of components, versions, dependency relationships, and metadata for software or an artifact.
- **Artifact provenance:** evidence of an artifact's origin—from which source it was built, by which builder/pipeline, under what parameters, and how it links to an output with a specific digest.

This lesson belongs to the **CI/CD and Software Supply Chain** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, while guiding deployment, monitoring, security, and cost control on Azure. Here we connect SBOM/provenance with Git, Maven/Gradle, Azure DevOps or GitHub Actions, Azure Container Registry, Microsoft Defender for Cloud, Azure Key Vault, and workloads on AKS, Azure Container Apps, or App Service.

**Core principle:** an SBOM answers "what is inside the software?", provenance answers "where did this artifact come from and how was it built?", while signatures/attestations and policy verification decide "do we have sufficient grounds to trust and deploy this artifact?" **No single tool guarantees software is free of vulnerabilities or malware.**

> **Scope and versioning:** Examples illustrate Java, containers, and Azure. Syntax and capabilities of the CycloneDX Maven plugin, Syft, Cosign, ORAS, Docker Buildx, Azure CLI, ACR, Azure DevOps, GitHub Actions, SLSA, and admission controllers evolve over time. Do not treat plugin names, formats, SLSA levels, or flags as the latest supported defaults; always cross-check exact version docs and organizational policy. Build/push/sign commands in this lesson can create or alter artifacts and incur charges; run them only in an approved lab environment. No commands were executed while authoring this document.

## Learning objectives

After this lesson, learners will be able to:

1. Distinguish **SBOM, dependency lockfile, vulnerability report, license report, checksum, digital signature, provenance, and attestation**.
2. Understand **CycloneDX** and **SPDX**, component identity fields, package URLs (purl), hashes, and dependency relationships.
3. Generate SBOMs for **Maven multi-module**, Gradle, or **OCI container images**, recognizing detection limits.
4. Compare **source-level, build-resolved, binary-level, and image-level SBOMs**.
5. Explain **tags vs. immutable digests**, OCI image manifests, image indexes, and multi-platform builds.
6. Link SBOMs and provenance to the **exact artifact digest** in ACR.
7. Describe **SLSA provenance**, build identity, source revision, builder identity, workflow, and attestation predicates.
8. Distinguish artifact/attestation signing with **Cosign/Sigstore** from merely generating checksum files.
9. Build Azure DevOps or GitHub Actions pipelines applying **OIDC/workload identity federation, least privilege, and builder isolation**.
10. Design verification gates in CI/CD and AKS admission matching policy, with audited rollback and break-glass procedures.
11. Use SBOMs to evaluate **CVEs, licenses, dependency reachability, and incident response** without confusing vulnerability scans with provenance.
12. Construct operational checklists, safe lab practices, and incident scenarios tracing an artifact from AKS back to its Git commit.

## 1. What is the software supply chain?

A container image typically passes through multiple layers:

~~~text
Developer source code
      |
      v
Git repository / reviewed commit
      |
      v
Package manager and external repositories
  Maven Central / approved internal mirror
      |
      v
CI runner / compiler / build plugins
      |
      v
Java JAR/WAR + transitive dependencies
      |
      v
Docker/OCI image + OS packages + runtime
      |
      v
Azure Container Registry
      |
      v
AKS / Container Apps / App Service
      |
      v
Production requests and data
~~~

Every link carries risks: unmaintained dependencies, compromised publisher accounts, substituted packages, compromised build plugins, CI jobs holding overly broad credentials, image tags moved to new manifests, or clusters pulling from unapproved registries.

### Why is reviewing source code alone insufficient?

A repository may not contain source code for all **dependencies, base images, compilers, plugins, and operating-system libraries**. A single line in `pom.xml` neither reveals all bytecode/runtime classes that will run nor confirms the final image corresponds to the reviewed code.

## 2. Threat model: what needs protection?

| Attack target | Scenario | Primary countermeasures |
|---|---|---|
| **Source** | Malicious code commit or workflow file edit | Branch protection, reviews, signed/verified commits where required by policy |
| **Dependencies** | Malicious packages, dependency confusion, typosquatting | Approved repositories, pinned versions, integrity verification, SBOM |
| **Build environment** | Compromised runner, stolen secrets/tokens | Ephemeral/isolated runners, workload federation, least privilege |
| **Build output** | JAR/image swapped after build | Content digests, signed provenance, verification |
| **Registry** | Tag moved to a different digest | Immutable digest deployment, registry RBAC and policies |
| **Deployment** | Pulling unauthorized or unapproved release images | Admission policies, signatures/attestations, GitOps |
| **Runtime** | Known vulnerable libraries or container escapes | Scanning, patching, policies, hardening, Defender |
| **Audit trail** | Deleted or falsified provenance or SBOMs | Evidence retention, access controls, tamper-evident storage |

**An SBOM is declarative inventory data**, not a tamper-proofing mechanism when unprotected. If an attacker controls both the artifact and an unverified SBOM, they can emit a "clean" but false SBOM.

## 3. What is an SBOM?

A **Software Bill of Materials** is an inventory of components making up software and the relationships between them. Depending on tooling and coverage, an SBOM can record:

- Package names and versions.
- Supplier/publisher or source repository.
- Component type: library, application, operating-system package, container, framework.
- Package URL (**purl**) or other identifiers.
- Hashes/checksums when computed from artifact bytes.
- Direct/transitive dependencies and dependency graphs.
- Licenses, copyrights, and package manifest metadata.
- Build/document metadata: tool, timestamp, serial number/namespace.

~~~text
SBOM for checkout-service
    |
    +-- Java application checkout-service:1.8.0
    |     +-- azure-identity
    |     +-- azure-storage-blob
    |     +-- spring-boot-starter-web
    |            +-- transitive libraries
    |
    +-- Container runtime: JRE/JDK
    +-- Base image operating-system packages
    +-- Native libraries and utilities if detected
~~~

**An SBOM does not necessarily contain all of these items.** An SBOM generated from a Maven dependency graph may omit OS packages, while an image scanner may miss shaded/obfuscated libraries or dynamically loaded components at runtime.

## 4. What is an SBOM NOT?

| Artifact/Concept | Answers the question | Does NOT prove |
|---|---|---|
| **SBOM** | Which components does the artifact contain? | Components have no vulnerabilities or malware |
| **Lockfile** | How was dependency resolution pinned? | Exactly what the final image contains |
| **Vulnerability report** | Which CVEs/advisories match these components? | The build path was trustworthy |
| **License report** | Package metadata/license obligations? | Full compliance with all legal terms |
| **SHA-256 digest** | Do the bytes match a content ID? | Who created the bytes or whether the build is trusted |
| **Digital signature** | Which key/identity signed which bytes/statement? | Signed content is authentic/clean if signer is untrusted |
| **Provenance** | Where did the artifact originate and how was it built? | Source or dependencies themselves are bug-free |
| **Attestation** | An entity attests to a statement about an artifact | Statement is accurate without issuer/policy controls |

Therefore, combine **component inventory + identity/origin verification + policy + vulnerability scanning + testing + runtime observability**.

## 5. CycloneDX and SPDX

**CycloneDX** and **SPDX** are two widely adopted standards families for exchanging software component information. Each standard has its own specification versions and representation models.

| Criterion | CycloneDX | SPDX |
|---|---|---|
| Common focus | Software/component inventory, dependencies, and supply-chain metadata | Software package, licensing, and provenance-related document model |
| Representations | JSON/XML or formats supported by the spec | JSON, tag-value, RDF, and formats per spec version |
| Identity | `bom-ref`, `purl`, hashes, component metadata | `SPDXID`, package identifiers, `externalRefs`, checksums |
| Dependency links | `dependencies` graph | `relationship` statements/graph |
| License | Declared/license evidence per spec | License identifiers/expressions per spec |
| Ecosystem | CycloneDX Maven/Gradle tooling, Syft, scanners | SPDX generators, Syft, package/compliance tooling |

**Do not claim one format is universally "better" than the other.** Choose based on customer requirements, scanners, registries, compliance needs, and tool support. You can generate both, though converting between them can lose non-equivalent metadata.

### Minimum information to retain

1. Artifact identity and digest.
2. Stable component identifier, name, and version.
3. Dependency relationships where known.
4. SBOM generator tool name and version.
5. Timestamp and source/build reference.
6. Licenses and hashes where evidence exists.
7. Signature/attestation or metadata protecting the SBOM.

## 6. PURL and component identity

A **Package URL (purl)** identifies packages by ecosystem. Examples:

~~~text
pkg:maven/com.azure/azure-identity@<RESOLVED_VERSION>
pkg:maven/org.springframework.boot/spring-boot@<RESOLVED_VERSION>
pkg:deb/debian/libssl3@<RESOLVED_VERSION>?arch=amd64
~~~

PURLs help vulnerability scanners match packages, but they are not proof of package bytes. Two different artifact sources or packaging methods could share a name/version; hashes, repository trust, digests, and provenance fill that gap.

### What should be recorded?

- **Name/version** is the baseline information.
- **purl** supports ecosystem-level identification.
- **Hash** supports byte-level artifact matching when actually measured.
- **Source/repository** indicates expected distribution origin.
- **Dependency relationship** enables tracing transitive impact.

Never infer a package version solely from a JAR filename when builds use repackaging or shaded classes; scanners should record confidence levels and detection mechanisms.

## 7. Direct vs. transitive dependencies

~~~text
Direct pom.xml:
  spring-boot-starter-web
  azure-storage-blob
  azure-identity
         |
         v
Transitive graph:
  spring-web, logging, JSON parser, HTTP clients,
  azure-core, Netty/Reactor, auth libraries, ...
~~~

A **CVE in a transitive JSON library** can affect a project even when `pom.xml` does not declare it directly. A Maven BOM or Gradle platform aligns versions, yet **it is not an SBOM of the built artifact**.

### Impact investigation

1. Identify the affected library by purl/name/version.
2. Search for it across SBOMs of active releases.
3. Trace the dependency graph from the application to the package.
4. Verify the package actually exists inside the built binary/image.
5. Check advisories, fixed versions, exploitability/context, and runtime code paths.
6. Prefer upgrading parent dependencies/BOMs rather than forcing arbitrary overrides.

## 8. Source SBOM, build SBOM, and image SBOM

| Generation point | Input source | Detects well | May miss |
|---|---|---|---|
| **Source scan** | Manifests/`pom.xml`/lockfiles | Declared dependencies | Runtime-resolved graphs, downloaded deps |
| **Build-resolved scan** | Maven/Gradle graph | Resolved direct/transitive versions | Base OS packages, native tools, dynamic downloads |
| **Binary/JAR scan** | JAR/WAR and bundled classes | Actually packaged components, depending on scanner | Shaded/repackaged/obfuscated libs |
| **Image scan** | OCI image layers/filesystem | OS packages + JAR + common runtimes | Dynamic components, undetectable native libs |
| **Runtime inventory** | Workload observations | Actually loaded modules in some scenarios | Unexecuted paths, full dependency set |

### Combined strategy

Generate both a **build-resolved SBOM** and a **final-image SBOM** at the appropriate stages, linking both to **the same release**. Never merge them into one file without documenting scope and deduplication rules.

### Why scan timing matters

After Maven finishes building, a `Dockerfile` may copy extra shell tools, an APM agent, or native libraries. A Maven-only SBOM misses those components. Conversely, an image scanner may not capture full license or dependency-graph metadata from Maven.

## 9. What layers does a container image contain?

~~~text
OCI image: registry.example/checkout:1.8.0
    |
    +-- Manifest / image index
    |     +-- Config digest
    |     +-- Layer digests
    |
    +-- Base OS files/packages
    +-- JRE/JDK and native libraries
    +-- Spring Boot fat JAR
    +-- APM agent / init scripts
    +-- Application configuration defaults
~~~

A final image is an **artifact independent** of the source tree. Scanning it provides a truer view of shipped bytes, though still imperfect.

### Fat JARs and shaded JARs

Spring Boot repackages dependencies into **BOOT-INF/lib**. Shading can also rename packages and classes. A scanner lacking Maven metadata or unable to recognize shaded classes may misidentify or omit packages.

**Avoid claiming an "SBOM is 100% complete"** without a basis for evaluating coverage. Define minimum criteria, use multi-source verification, and document known gaps.

## 10. Standardizing SBOM identity and releases

Every SBOM generation run needs reconcilable metadata:

~~~text
Application: checkout-api
Release:     1.8.0
Git commit:  <FULL_GIT_SHA>
Build run:   <CI_RUN_ID>
Container:   registry.example/checkout-api@sha256:<DIGEST>
SBOM format: CycloneDX JSON (approved spec version)
Generator:   pinned tool name/version
Timestamp:   UTC
~~~

Without binding the SBOM to the **output digest**, it is hard to tell whether `sbom.json` belongs to the running image or an earlier test build.

**A release version/tag alone is insufficient as an identity**, because tags can move when registry permissions permit.

## 11. Maven: generating SBOMs with the CycloneDX plugin

A Java Maven project can use the **CycloneDX Maven Plugin**. Example configuration in **pom.xml** (replace the plugin version with an approved version; this snippet is a template):

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.cyclonedx</groupId>
      <artifactId>cyclonedx-maven-plugin</artifactId>
      <version>REPLACE_WITH_APPROVED_PLUGIN_VERSION</version>
      <executions>
        <execution>
          <phase>verify</phase>
          <goals>
            <goal>makeAggregateBom</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <outputFormat>json</outputFormat>
        <outputName>bom</outputName>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

### Notes before using

1. **REPLACE_WITH_APPROVED_PLUGIN_VERSION** is not runnable; replace it with an exact published version.
2. Plugin configuration and output paths vary by plugin version; consult official documentation.
3. **makeAggregateBom** targets multi-module aggregation; single-module projects can select the corresponding goal.
4. The plugin may output **target/bom.json** as configured, but never assume every version/goal uses the same output path.
5. Dependency resolution during builds may fetch JARs/metadata from repositories; run only with approved mirrors and network policies.

### Illustrative commands

~~~bash
# Run only in a Java lab project; do not run on workflow workers arbitrarily.
mvn -B -ntp verify

# Or invoke the goal directly with a pinned plugin version:
mvn -B -ntp \
  org.cyclonedx:cyclonedx-maven-plugin:REPLACE_WITH_APPROVED_PLUGIN_VERSION:makeAggregateBom
~~~

**The BOM describes only components identified during dependency resolution at runtime.** If build profiles, modules, classifiers, or build tool behavior differ from production, the SBOM may differ from the released artifact.

## 12. Multi-module Maven: how to avoid missing modules

Example:

~~~text
checkout-service/
    pom.xml (parent)
    api/pom.xml
    domain/pom.xml
    storage-adapter/pom.xml
    messaging-adapter/pom.xml
~~~

### Workflow

1. Run the build from the **root reactor** using the same Maven profiles as the release.
2. Use the aggregate SBOM goal/method matching your plugin version.
3. Verify the SBOM includes all key modules and runtime dependencies.
4. Inspect the Maven dependency tree if a dependency is missing.
5. Cross-check actual output JARs against the SBOM.
6. Record Maven/JDK/plugin versions, active profiles, and build run ID.

**Never run Maven inside each module separately assuming the sum of SBOM files represents the release**; modules may be missed or dependencies duplicated.

## 13. Gradle: SBOMs and resolved configurations

Gradle supports CycloneDX plugins and output artifact scanners. Because plugin APIs and task names evolve, **pin plugin versions** and verify output paths against current documentation.

~~~text
Gradle project
     |
     +-- compileClasspath
     +-- runtimeClasspath
     +-- testRuntimeClasspath
     |
     v
CycloneDX Gradle plugin / approved SBOM generator
     |
     v
SBOM for selected project/configuration(s)
~~~

### Do not mix scopes

A production release SBOM should prioritize **runtime dependencies**. Test frameworks (JUnit, Testcontainers) may warrant a separate build-environment SBOM, but test JARs do not all ship inside the running image.

### Inspecting the graph

~~~bash
# Inspect Gradle dependency graph (when learners practice locally):
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

These are instructional commands; **do not execute Gradle inside worker automation arbitrarily**. Use a pinned/controlled Gradle wrapper and trusted repositories.

## 14. Scanning final container images with Syft

**Syft** is a popular tool for generating software package inventories/SBOMs from images, filesystems, and supported sources.

Usage example:

~~~bash
# Run only after selecting an image digest and confirming pull permissions.
# Replace image reference/digest with a real lab artifact.
IMAGE="registry.example/checkout-api@sha256:<REAL_DIGEST>"

syft "$IMAGE" -o cyclonedx-json=sbom-image.cdx.json

# SPDX JSON can also be generated in the format supported by your Syft version:
syft "$IMAGE" -o spdx-json=sbom-image.spdx.json
~~~

### Notes

- **<REAL_DIGEST>** is a placeholder; replace it with a valid digest string.
- Syft may access registries or container runtimes; grant read-only credentials only to required registries.
- Output files may reveal internal dependencies, paths, and base images; enforce appropriate permissions and retention.
- Use a tested scanner version; package detection has false positives and false negatives.
- Scanning a local image tag does not guarantee it matches the final pushed digest, especially for multi-platform builds.

## 15. Source scans and final image scans can differ

Suppose the build-resolved SBOM contains:

~~~text
pkg:maven/org.springframework.boot/spring-boot@<VERSION>
pkg:maven/com.azure/azure-identity@<VERSION>
~~~

Image-level scanning also finds:

~~~text
pkg:deb/debian/openssl@<VERSION>
pkg:deb/debian/zlib1g@<VERSION>
JRE files/native libraries
~~~

### Two-way verification

- **From Maven to image:** is every expected runtime dependency actually present in the final app artifact?
- **From image to source:** which components were introduced by the base image, `Dockerfile`, APM agents, or build steps?

If a dependency appears only in the source SBOM and not in the image SBOM, it may reflect a different scope, scanner blindness, repackaging, or an unshipped dependency. Never remove it from the risk register without verification.

## 16. Verifying SBOM accuracy

An SBOM that "is valid JSON and parses cleanly" is not enough.

### Structural criteria

- Conforms to an approved JSON/XML schema and spec version.
- Includes metadata for the application/output component.
- Includes generator tool name/version and timestamp.
- No duplicate or broken identifiers (`bom-ref`/`SPDXID`).
- Valid dependency relationships.
- No meaningless placeholder fields injected by pipelines.

### Content criteria

- Versions of sample direct dependencies match the Maven/Gradle resolved graph.
- Expected critical runtime libraries appear.
- Base image packages appear when the SBOM scope is the final image.
- Dev/test-only dependencies are separated from runtime.
- Does not accidentally inventory every package installed on a laptop or CI host.
- No missing components from plugins skipping modules or build profiles.

### Release-binding criteria

The SBOM is generated and stored for **the exact released build artifact/image digest**—never reuse an earlier build's SBOM after code or dependencies change.

## 17. Where in the lifecycle are SBOMs used?

~~~text
PR / dependency review
    -> source/build SBOM and initial risk scan
             |
             v
Merge to protected branch
    -> clean build, final-artifact SBOM
             |
             v
Push image to ACR, record digest
    -> attach/publish SBOM + provenance
             |
             v
Staging admission / policy
    -> verify signer, subject, SBOM and approved registry
             |
             v
Production deployment
    -> digest pinning, monitor and rescan as advisories evolve
~~~

**An SBOM is not generated once and forgotten.** CVE databases and license standards evolve over time, so stored SBOMs can be rescanned whenever new advisories emerge.

## 18. SBOMs vs. vulnerability scanning

~~~text
SBOM:
  Package A v1.2
  Package B v4.5
  Package C v2.1
        |
        v
Advisory database (CVE, OSV, GHSA, vendor advisories)
        |
        v
Vulnerability matches + severity + affected ranges
        |
        v
Triage exploitability, reachability, context
        |
        v
Fix/mitigate + regenerate/reverify SBOM
~~~

### Why do scanner results differ?

- Advisory feeds and freshness.
- Package identity mapping (`purl`/CPE/vendor).
- OS package backports keeping older version numbers relative to upstream.
- Java shaded libraries or incomplete component metadata.
- False positives and false negatives.
- Policy severity thresholds and exclusions.

**Never treat "0 CVEs from one scanner" as a safety guarantee.** Coverage gaps or undisclosed advisories remain real risks.

## 19. SBOM-driven CVE remediation workflow

When an advisory is published:

1. Verify the official advisory and affected version ranges.
2. Search for the package purl/version across SBOMs of all active releases.
3. Determine whether the component sits in the JAR/runtime image or is test-only.
4. Trace dependency paths and remediation options (BOM/parent upgrade, patch, rebuild).
5. Assess workload exposure: API reachability, permissions, sandboxing, config, exploit prerequisites.
6. Prioritize remediation by severity, exploitability, and SLO.
7. Build a new artifact from fixed source and emit fresh SBOM/provenance.
8. Test, sign, verify, and deploy through release gates.
9. Monitor production digests and prove the vulnerable digest is no longer running.
10. Record an exception/temporary mitigation with owner and expiration if an immediate fix is impossible.

**Never "fix an SBOM" by deleting a package name or version to silence a scanner.** Fix the underlying component and build output.

## 20. SBOMs also support license governance

Dependencies may use licenses such as Apache-2.0, MIT, BSD-3-Clause, or other terms. An SBOM provides an **initial inventory** for legal/compliance analysis.

### What to check

- Does the package declare an SPDX license identifier/expression?
- Is the license **declared**, **concluded**, or inferred from metadata?
- Are there multiple licenses or dual-licensing?
- Are there notice or source-distribution obligations?
- Was third-party code copied manually without scanner visibility?
- Do the container base image and CLI tools carry separate licenses?

### Do not equate a license scanner with legal advice

An SBOM may report **NOASSERTION/UNKNOWN** when license metadata is absent. That does not mean the package is license-free or safe for commercial use. Maintain policy reviews, owners, and valid evidence—especially when distributing software to customers.

## 21. Choosing artifact identifiers: tags vs. digests

A container image can be referenced as:

~~~text
myregistry.azurecr.io/checkout-api:1.8.0
myregistry.azurecr.io/checkout-api:stable
myregistry.azurecr.io/checkout-api@sha256:<64_HEX_CHARACTERS>
~~~

A **tag** is a label pointing to a manifest/index; it can be repointed to different content if registry permissions allow. A **digest** is the content address of a manifest/index and stays constant for identical bytes.

~~~text
Tag 1.8.0  ------> Manifest digest A
Tag stable ------> Manifest digest A

Later:
Tag stable ------> Manifest digest B
Tag 1.8.0  ------> Manifest digest A
~~~

### Why digests matter

- Pinpoint the exact artifact that was signed and linked to an SBOM.
- Prevent deploying a tag whose target shifted.
- Support rolling back to a previously tested image manifest.
- Prove which components a production release contains.

**A digest does not prove provenance.** An attacker can build a malicious image and compute its digest. You must verify who/which build produced that digest and whether policy accepts it.

## 22. OCI manifests, image indexes, and multi-platform builds

An image tag can point to an **OCI image index** spanning multiple platform manifests:

~~~text
checkout-api:1.8.0
      |
      v
OCI image index @sha256:INDEX_DIGEST
      |
      +-- linux/amd64 manifest @sha256:AMD64_DIGEST
      |      +-- config + layers
      |
      +-- linux/arm64 manifest @sha256:ARM64_DIGEST
             +-- config + layers
~~~

### Implications for SBOM/provenance

- Attaching an SBOM to the **index digest** differs from attaching an SBOM to the **amd64 manifest**.
- OS/packages can differ across platforms.
- Build tools may emit provenance/SBOM per platform or at the index level depending on features.
- Admission controllers and scanners must know whether they verify the **index or a platform-specific manifest**.

**Never take a `linux/amd64` SBOM and claim it covers `linux/arm64`** without verification.

## 23. Azure Container Registry in the evidence chain

**Azure Container Registry (ACR)** commonly stores container images and OCI artifacts in Azure systems. Manage:

1. Registry identity, region, replication, and network access.
2. Repositories, tags, manifests, and immutable digest references.
3. Separated push and pull access.
4. Registry retention/cleanup and artifact retention policies.
5. Vulnerability scanning / Defender integration per supported tier.
6. Where SBOMs, provenance, and signatures live and how they are resolved by digest.

~~~text
Azure DevOps / GitHub Actions trusted build
        |
        v
Push final image
        |
        v
Azure Container Registry
   checkout-api@sha256:IMAGE_DIGEST
        |
        +--> SBOM linked to subject digest
        +--> Provenance attestation linked to digest
        +--> Signature / verification material
        |
        v
AKS pulls approved digest
~~~

### ACR does not turn every push into a trusted release

Anyone with push access to a repo can upload an unvetted artifact. Enforce **publisher identity, protected CI flows, verification gates, and cluster admission**. Placing ACR behind Private Link protects the network transport, not artifact origin.

## 24. Read-only ACR metadata queries

When holding read access to a **lab registry**:

~~~bash
az account show \
  --query "{subscription:id, tenant:tenantId}" \
  --output json

az acr repository list \
  --name "<LAB_ACR_NAME>" \
  --output table

az acr repository show-tags \
  --name "<LAB_ACR_NAME>" \
  --repository "checkout-api" \
  --output table
~~~

These read-only commands list repositories and tags, **without proving which digest a tag resolves to or whether an artifact is signed**. To inspect manifest digests, use the API/CLI/OCI tooling matching your ACR version and permissions, then record the immutable digest in the release ledger.

**Do not assume every legacy Azure CLI command remains unchanged.** Check `--help`/reference docs for your CLI version. When working across multiple registries or subscriptions, specify the exact target registry and scope explicitly.

## 25. What is artifact provenance?

Provenance is metadata proving **by which process and from which inputs an output artifact was created**.

~~~text
Source repository + commit
       |
       +-- Build workflow definition
       +-- Dependency/cache sources
       +-- Builder/runtime identity
       |
       v
Trusted CI builder / execution
       |
       v
Output artifact digest
       |
       v
Provenance statement
    subject: image digest
    source: repo + commit
    builder: workflow/service identity
    build parameters / materials
~~~

A provenance statement can be stored as an **attestation**, typically signed and bound to a content digest. It is not "an author writing a note saying the image is good"; verifiers must inspect **subject, builder identity, signature, and trusted workflow**.

## 26. Minimum contents of provenance

| Field group | Example | What to verify |
|---|---|---|
| **Subject** | OCI image `@sha256:...` | Digest matches the deployed artifact |
| **Source** | Repository URI | Source is on the allowlist |
| **Revision** | Full Git commit SHA | Commit belongs to a protected branch/release |
| **Builder ID** | Build service/workflow | Builder is trusted by the organization |
| **Invocation** | Workflow ID / run ID / parameters | Run complied with policy |
| **Materials** | Source, dependencies/base image where recorded | Inputs are accounted for |
| **Timestamp** | Start/finish UTC | Consistent and auditable |
| **Build type** | Kind of build process | Matches an approved workflow/template |
| **Signer/issuer** | Signing identity/authority | Certificate/key/issuer verified |

Exact fields depend on the **SLSA/in-toto predicate spec version** and generator tool. Table names are conceptual, not a strict 1-to-1 JSON schema across every version.

## 27. SLSA and provenance attestations

**Supply-chain Levels for Software Artifacts (SLSA)** is a framework for artifact origin and integrity assurance. Provenance describes the build process, source revisions, and outputs. Specific levels and requirements **vary across specification versions**.

### Distinguish

- **SLSA specification:** defines concepts and requirements.
- **SLSA provenance predicate:** schema expressing build origin.
- **Builder/attestor:** service generating the statement.
- **Verifier/policy:** consumer evaluating evidence to accept or reject an artifact.

**A self-labeled SLSA JSON file does not prove compliance with any SLSA level.** You need evidence of builder isolation, identity, immutable source, tamper resistance, and verification.

### Conceptual provenance example (NOT a valid SLSA schema)

~~~json
{
  "note": "Conceptual example, NOT a compliant attestation",
  "subjectDigest": "sha256:<IMAGE_DIGEST>",
  "sourceCommit": "<FULL_COMMIT_SHA>",
  "sourceRepository": "https://example.org/org/checkout-api",
  "builderIdentity": "<TRUSTED_WORKFLOW_ID>",
  "runId": "<CI_RUN_ID>"
}
~~~

In real releases, **use official generators** adhering to current SLSA/in-toto schemas rather than signing custom JSON and claiming SLSA provenance.

## 28. In-toto statements and attestations

An **attestation** is a statement about an artifact carrying a predicate such as:

- Provenance: which source/workflow built the artifact.
- SBOM: which components the artifact contains.
- Test results: assertions about testing from a trusted generator.
- Vulnerability scan results: which scanner ran when, and with which version.

~~~text
             Subject: image@sha256:D
                       |
           +-----------+------------+
           |                        |
           v                        v
      SBOM attestation        Provenance attestation
       predicate: ...           predicate: ...
           |                        |
           +-----------+------------+
                       |
                 Signature/bundle
                       |
                       v
               Policy verification
~~~

**An attestation does not imply a valid signature.** A statement might be unsigned or signed by an untrusted identity. Policies must verify both the content and the signer.

## 29. Artifact signing vs. attestation signing

Two related but distinct goals:

1. **Artifact signature:** confirms the signer signed the content digest of the image/artifact.
2. **Attestation signature:** confirms the signer signed a statement (SBOM/provenance...) bound to the subject digest.

### What signing helps with

- Detecting post-signing tampering of statements or digests.
- Tying evidence to a trusted identity or key.
- Allowing admission gates to verify exact releases.

### When signing fails to protect

- The signing key is leaked or the CI signer is compromised.
- An attacker tricks a trusted signer into signing malicious output.
- The verifier only checks "signature exists" without verifying signer identity.
- A provenance statement cites false sources because an untrusted tool emitted it.

**Build an explicit trust policy** instead of trusting signatures from arbitrary issuers.

## 30. Sigstore/Cosign and keyless signing

**Cosign** is a tool in the **Sigstore** ecosystem supporting signing and verification of container images and attestations across supported modes. One model is **keyless signing** backed by workload OIDC identities and certificate/attestation authorities.

~~~text
Trusted CI workflow
       |
       | OIDC identity claims
       v
Keyless signing authority / certificate workflow
       |
       v
Sign image digest / attestation
       |
       v
OCI registry + transparency/evidence mechanisms
       |
       v
Verifier checks signer identity/issuer and subject
~~~

### Do not adopt keyless in every CI blindly

- CI must support **OIDC** and compatible credential/issuer policies.
- Inspect Sigstore/Cosign versions, trust roots, certificate identity fields, transparency logs/bundles, and network paths.
- Keyless identities for PRs on untrusted branches differ from protected release workflows.
- Check not only the issuer domain, but the exact approved **repository/workflow/ref/build identity**.
- Private Sigstore instances or custom trust roots may be required; never assume every organization uses public Sigstore.

### With organization-managed signing keys

Managed keys such as Azure Key Vault / KMS can be used via supported integrations. Enforce key permissions, rotation, auditing, and verifier trust anchors. Never upload private keys into CI variables or commit them into repositories.

## 31. Transparency logs and offline verification

Signing/attestation ecosystems may use transparency logs and **verification bundles** to provide auditable evidence later.

### Three things to distinguish

- **Valid signature:** statement/digest has not been altered relative to the private key matching the public key/cert.
- **Trusted signer identity:** certificate/identity matches the organization's allowlist.
- **Trusted provenance:** statement was produced by a protected workflow/builder with authentic source and subject.

A transparency log aids auditability and tamper evidence by design, **but does not prove the code itself is benign**.

### Offline verification

If production clusters cannot reach external verification services on the Internet, design **pinned bundles/trust roots and an update lifecycle**. Never disable verification altogether merely because an external helper service is temporarily unreachable.

## 32. Attaching SBOM/provenance to artifact digests

One strategy is publishing SBOMs/provenance as **OCI artifacts/referrers** linked to the subject image digest when supported by the registry and tooling.

~~~text
ACR:
  checkout-api@sha256:D
       |
       +-- OCI SBOM artifact (subject = D)
       +-- OCI provenance attestation (subject = D)
       +-- Cosign signature / verification material
~~~

### Questions to resolve

1. Do registry and OCI tools support artifacts/referrers under current APIs/versions?
2. Which repository stores the metadata, and who holds push/read permissions?
3. Could retention/cleanup delete SBOMs/attestations independently of the image?
4. When copying images across registries/regions, are attestations copied along with them?
5. Do scanners, validators, and admission controllers resolve the exact subject digest?

**Attaching `sbom.json` as a pipeline artifact does not automatically store it beside the image in ACR.** Design explicit publication, storage, linkage, and verification.

## 33. ORAS and OCI artifacts

**ORAS** is a toolset/library for pushing, pulling, and copying OCI artifacts, useful for storing SBOMs and metadata when registries support it.

### Conceptual flow

~~~text
Generate SBOM JSON
        |
        v
Validate SBOM format
        |
        v
Use OCI tooling to attach/push as artifact
   subject: checkout-api@sha256:IMAGE_DIGEST
        |
        v
ACR registry
        |
        v
Pull/read/verify by policy tool
~~~

**Do not hardcode a single `oras attach` command across all versions**: ORAS CLI syntax, artifact types, subject support, and registry compatibility change. Check current ORAS/ACR docs and test against a lab image digest first.

### Standardize MIME/artifact types

CycloneDX JSON, SPDX JSON, SLSA provenance, and DSSE envelopes have distinct media types per specification. Use standard artifact/predicate types; avoid registering every JSON file generically as **application/json** without distinguishing metadata.

## 34. Combining OCI referrers with registry cleanup

Deleting an image digest can affect referrer artifacts depending on registry implementation and cleanup policies. Deleting old SBOMs/attestations destroys historical release investigation capability.

### Two-tier retention policy

- **Deployable images:** retain production digests, rollback digests, and policy-mandated releases.
- **Evidence artifacts:** retain SBOMs, provenance, signatures, and test reports for audit and incident-response windows.

Even after an older image is no longer pulled by production, its SBOM/provenance may still be required to prove past CVE remediation.

### Store outside the registry too?

You can archive evidence in immutable blob storage or an artifact archive with access controls, integrity checks, and retention if audits require it. **A copy disconnected from its digest or missing verification metadata remains hard to trust.**

## 35. Azure Key Vault and signing keys

If an organization uses long-lived key-based signing instead of keyless:

~~~text
Release signing workflow
       |
       | Entra workload federation / managed identity
       v
Azure Key Vault / supported signing integration
       |
       | Cryptographic signing operation
       v
Signature over artifact digest or attestation
       |
       v
Published signature and verification metadata
~~~

### Least privilege

- The signing identity needs only **sign** permission on the specific key—not Key Vault Administrator.
- Build/PR pipelines must not hold access to production release-signing keys.
- Separate dev/staging/prod keys according to risk policy.
- Audit signing events and anomalies.
- Maintain key rotation, revocation, and trust-anchor rollover plans.
- Manage Key Vault network/private endpoints if workflows require access.

**Azure Key Vault does not automatically make Cosign compatible with every key type or algorithm.** Verify plugin/provider/KMS URIs and supported algorithms before putting an untested Azure KMS command into production CI.

## 36. What must a trust policy verify?

Before allowing an image to run in production:

1. **Subject digest:** the deployed artifact is the exact signed image.
2. **Trusted signer identity:** belongs to an approved release pipeline.
3. **Trusted issuer/trust root:** reject arbitrary certificates/CAs.
4. **Source repo:** from an allowlisted organization/repository.
5. **Commit SHA/ref:** commit resides on a protected branch or approved release tag.
6. **Builder identity:** workflow/build service has controlled isolation and permissions.
7. **Provenance schema:** valid predicate type and format.
8. **SBOM link:** SBOM binds to the exact same subject digest and is verified.
9. **Vulnerability/license policy:** no unapproved blocking risks under active policy.
10. **Exception handling:** break-glass overrides have owner, expiration, audit, and review.

**Checking only whether a signature exists is not a release policy.**

## 37. Threat: valid signature on bytes from an untrusted source

~~~text
Attacker PR branch
      |
      v
CI workflow auto-signs every PR build
      |
      v
Malicious image carries valid signature
      |
      v
Cluster checks only "signature exists"
      |
      v
Malicious image accepted
~~~

### Remediation

- Never grant release-signing privileges to untrusted PR jobs.
- Never allow fork PRs to access secrets or production-capable OIDC identities without strict isolation.
- Verify **workflow identity + source repository + protected ref**.
- Publish production provenance solely from trusted release builders.
- Require approvals and policy checks before admitting images to the production allowlist.

**A trusted signer identity must be bound to a trusted release process**, not just any job running under the organization's name.

## 38. A Git repository is an input, not complete proof

A build usually records **repository URL** and **full commit SHA**. You must also answer:

- Was the commit merged via a reviewed pull request?
- Are release branches and tags protected against force-pushes?
- Which commit supplied the workflow definition itself?
- Was the build runner isolated from untrusted PRs?
- Where did dependencies and base images come from?
- Did any step `curl` and execute remote scripts without verification?
- Does the build output genuinely match the digest recorded in provenance?

### Commit signatures vs. artifact signatures

**Signed Git commits** verify claims about commit/author identity per policy, but do not prove a container image was built from that commit. **Signed images** confirm an identity signed a digest, but do not prove the source commit without trusted provenance. Both address different layers.

## 39. Workflow definitions must also be trusted

A GitHub Actions or Azure DevOps pipeline typically encompasses:

~~~text
Source code commit
     |
     +-- Workflow YAML / pipeline templates
     +-- External actions/tasks/plugins
     +-- Build scripts
     +-- Container builder/runtime
     +-- Secrets/identity permissions
     |
     v
Release builder
~~~

### Safeguards

1. Review and protect pipeline configs like source code.
2. Pin third-party actions to immutable commit SHAs where supported and maintain an update policy.
3. Pin build task/plugin versions and verify publishers.
4. Never run arbitrary untrusted PR code in jobs holding production credentials.
5. Restrict scripts fetching remote payloads without hash/signature verification.
6. Scope permissions per job instead of relying on broad default tokens.
7. Record source revisions of reusable workflows/templates when provenance formats support it.

**A green pipeline run does not guarantee the runner and scripts were trustworthy.**

## 40. Azure DevOps Pipelines and OIDC federation

In Azure DevOps, use **service connections** with **workload identity federation** under supported authorization modes instead of storing long-lived client secrets in pipelines.

~~~text
Protected Azure DevOps pipeline
       |
       v
Azure service connection (federated identity)
       |
       | Token exchange with Microsoft Entra ID
       v
Scoped Azure principal
       |
       +--> ACR push on approved registry/repository
       +--> Read approved Key Vault resources if essential
       +--> Deployment rights on staging/prod with approvals
~~~

### Permission principles

- **Build jobs** need source, dependencies, and build caches—not deploy permissions.
- **Publish jobs** push only to designated ACR repos/registries.
- **Signing jobs** use only signers/identities permitted by release policy.
- **Deploy jobs** modify only workloads in the target environment.
- **PR jobs** never receive production push or signing permissions.

Successful federation does not automatically grant ACR/AKS permissions to the Azure principal. Configure matching RBAC/registry repository permissions, network paths, and environment approvals.

## 41. Azure DevOps YAML: build and SBOM skeleton

This is an **illustrative pipeline skeleton** that intentionally neither pushes nor signs; adapt it to your real agent, Maven version, caches/mirrors, branch security, and plugin versions before use:

~~~yaml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

stages:
  - stage: BuildAndInventory
    displayName: Build Java and generate SBOM
    jobs:
      - job: Build
        steps:
          - checkout: self
            persistCredentials: false

          - script: |
              java -version
              mvn -version
              mvn -B -ntp verify
              test -s target/bom.json
            displayName: Build and verify SBOM presence

          - publish: target/bom.json
            artifact: sbom-java
            displayName: Publish build SBOM
~~~

### Prerequisites for this skeleton to run

- The Maven plugin is **configured in `pom.xml`** as in Section 11, outputting `target/bom.json`.
- For multi-module projects, SBOM paths may differ; do not point to an example path that does not exist.
- Runners must have matching JDK, Maven, permissions, and approved artifact repositories.
- Production CI still requires **schema validation**, **image builds**, **image-level SBOMs**, **provenance, signing, verification**, and **deployment**.
- A published pipeline artifact is a file copy; **it is not yet bound to an OCI subject digest**.

**Do not cite this skeleton as proof of SLSA compliance or complete supply-chain security.**

## 42. GitHub Actions and Azure: separating build from release

A workflow can segregate privileges:

~~~text
Pull Request Workflow
  -> compile/test
  -> dependency/SBOM check
  -> no production signing/push credentials

Protected Main/Release Workflow
  -> isolated trusted build
  -> final image to ACR
  -> provenance/SBOM attestation and signature
  -> verify gate
  -> controlled deployment
~~~

### OIDC with GitHub Actions

Workload federation requires a **trust relationship** between Microsoft Entra ID and GitHub workflow OIDC claims. When granting Azure permissions, constrain repository, environment, and ref per supported model.

**GitHub OIDC used for Azure tokens does not automatically create a Cosign keyless signing certificate.** Azure resource login and Sigstore signer identity are related but separate flows; configure each according to documentation.

### Never grant privileges to arbitrary pull requests

A PR with external contributions could edit build scripts to read tokens or secrets. Enforce runner/credential isolation, event restrictions, and branch/environment protections; do not rely solely on a branch-name condition inside YAML if an untrusted PR can modify the workflow file itself.

## 43. Docker Buildx: generating images and attestation metadata

In supported **Docker Buildx/BuildKit** versions, SBOM and provenance attestations can be emitted during the build.

~~~bash
# Illustrative command that PUSHES an image; run only with a lab registry and proper permissions.
# Replace registry/repo/tag with real lab values.
docker buildx build \
  --platform linux/amd64 \
  --tag "registry.example/checkout-api:lab-release-001" \
  --sbom=true \
  --provenance=mode=min \
  --metadata-file build-metadata.json \
  --push \
  .
~~~

### Explanation

- **--sbom=true:** instructs BuildKit to attach an SBOM attestation when supported.
- **--provenance=mode=min:** requests minimal BuildKit provenance metadata; does not automatically achieve a SLSA level.
- **--metadata-file:** writes build metadata to look up the output digest by version.
- **--push:** pushes the image to the registry; may incur cost and require push permissions.
- **--platform:** restricted here to `amd64` to avoid multi-platform complexity.

### Mandatory checks

1. The registry supports storing attestations and manifest indexes as emitted by the builder.
2. The digest in build metadata matches the image stored in the registry.
3. The BuildKit-generated SBOM adequately covers final image contents.
4. Generated provenance is protected/signed, and verifiers trust the builder/identity.
5. The build process leaks no secrets via build args, build logs, or provenance fields.
6. CI never publishes images from untrusted PRs under a production identity.

**`--provenance` alone is not a trusted release signature.** Build attestations must be stored, verified, and enforced by policy.

## 44. Dockerfiles and base image provenance

A sample Dockerfile:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/checkout-api.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This is a minimal example, **not a production-ready Dockerfile**; base image tags can shift, user IDs must match filesystem permissions, and JAR paths vary by project.

### Better supply-chain hygiene

- Choose base images from approved registries and vendors.
- **Pin base images by digest** in release builds when policy requires it.
- Verify base image provenance/signatures when available.
- Regularly refresh JRE/OS patches rather than pinning one aging digest forever.
- Generate the final-image SBOM after all layers are assembled.
- Avoid installing extra tools from unvetted sources via package managers during builds.

### A key trade-off

Pinning digests protects builds from tag drift, yet can freeze a base image containing a CVE patched in a newer tag. Maintain a **dependency update cadence** and policy reviews; immutability does not replace security patching.

## 45. Preventing dependency confusion and package substitution

A build may pull dependencies from:

- Maven Central or an approved proxy repository.
- Azure Artifacts feeds or internal repositories.
- Public package sources / third-party registries.
- Local build caches.

### Risks

If the same package name exists in both public and private repositories, misconfigured resolution can pull a malicious public package. Typosquatting, compromised publishers, and cache poisoning pose additional risks.

### Countermeasures

1. Configure explicit repository ordering, namespace ownership, and routing.
2. Use governed internal proxies/mirrors rather than adding arbitrary repositories in every `pom.xml`.
3. Pin dependency/plugin versions; avoid SNAPSHOTs and dynamic ranges on releases unless authorized.
4. Enable checksum/signature verification where supported by tools and repositories.
5. Scope package feed credentials tightly.
6. Inspect the SBOM and dependency tree after resolution.
7. Maintain mechanisms to quarantine/disable malicious packages.

**SBOMs reveal packages that entered an artifact**, but cannot stop a malicious package from executing during the build unless resolution policies block it beforehand.

## 46. Build secrets: keep them out of `ARG` and provenance

The following Dockerfile is a security risk:

~~~dockerfile
# ANTI-PATTERN: never use for secrets.
ARG PRIVATE_REPO_PASSWORD
RUN echo "$PRIVATE_REPO_PASSWORD" > /tmp/repo-password
~~~

Build args, commands, logs, image history, and provenance metadata can all leak secret values. Use **build secret mounts**, short-lived credentials, and supported build-environment secret mechanisms.

### CI secret handling

- Never echo access tokens.
- Keep `.env` files, private keys, and vault exports out of the Docker build context.
- Maintain a `.dockerignore` and audit build contexts.
- Avoid exporting signing key material into workspaces when KMS signing supports remote cryptographic operations.
- Enable log masking, but never rely on masking alone.
- Separate PR builds from release secrets.

**More detailed provenance modes are not always safer** if pipelines embed sensitive build inputs into metadata. Define secret boundaries before raising verbosity.

## 47. Are reproducible builds and provenance the same?

A **reproducible build** means identical bytes can be recreated given defined inputs and conditions within the reproducibility method. **Provenance** documents how an artifact was built; a build that is not byte-for-byte reproducible can still yield useful provenance.

### Sources of non-reproducibility

- Random timestamps inside JARs or container layers.
- Unlocked dependency versions.
- Mutable base image tags.
- Changing build plugin or toolchain versions.
- Differing OS, locale, or timezone settings.
- Dynamically fetched files/secrets lacking content digests.
- Tainted build caches or shared state.

### Value of reproducibility

If an independent builder using identical inputs produces the exact same digest, that provides additional proof the output was not unexpectedly altered. Still, **two builders could both pull the same malicious dependency**, so reproducibility alone does not prove source safety.

## 48. Separating build, sign, verify, and deploy

Clear separation of responsibilities:

~~~text
BUILD
  Inputs: source + dependencies + pinned base
  Output: image digest + build SBOM
     |
     v
PUBLISH
  Push immutable image digest to ACR
     |
     v
ATTEST + SIGN
  Image SBOM + provenance, trusted release identity
     |
     v
VERIFY
  Signature, issuer, source, builder, subject, policy
     |
     v
DEPLOY
  AKS/Container Apps/App Service pin approved digest
     |
     v
OBSERVE
  Running digests, CVE advisories, runtime issues
~~~

### Why not use one shared identity?

If a build job can edit policies, delete registry evidence, sign any image, and deploy to prod without approvals, compromising a build runner compromises the entire chain. Separating permissions, environments, and control planes provides defense in depth.

## 49. Pre-deploy verification: verifying the right signature

In the **Cosign keyless** ecosystem, verifiers must check the approved identity/issuer and image digest. Illustrative form:

~~~bash
# Command skeleton only; never use placeholders in production.
cosign verify \
  --certificate-identity "<APPROVED_RELEASE_WORKFLOW_IDENTITY>" \
  --certificate-oidc-issuer "<APPROVED_OIDC_ISSUER>" \
  "registry.example/checkout-api@sha256:<REAL_DIGEST>"
~~~

### Notes

- Verify flags and certificate identity format against your Cosign version.
- Other signing/verification modes use different trust roots or public keys.
- Certificate identity and issuer must match **exact values from the trusted workflow**—never use overly broad wildcards.
- Always verify the **image reference by digest**, not just tag.
- This verification command alone does not check full **provenance predicates or SBOM policies**.

### Attestations must also be verified

To enforce a policy like "source must be protected `main` and builder must be workflow X," the verifier must inspect the **signature-verified provenance attestation** and check source/builder attributes against schema—never trust an arbitrary JSON snippet on sight.

## 50. Policy-as-code for AKS

AKS can use **Kubernetes admission controls**, Azure Policy integrations, or supported engines such as Gatekeeper/Kyverno to enforce image policies. Exact support for verifying signed images and attestations depends on the engine, version, and configuration.

~~~text
GitOps/CI submits Deployment
        |
        v
Kubernetes API admission
        |
        +-- Registry allowlist
        +-- Digest pin requirement
        +-- Signature/attestation verification (if supported)
        +-- Source/builder/predicate policy
        |
        +---- PASS ---> Accepted PodSpec
        |
        +---- FAIL ---> Rejected with audit event
~~~

### Practical policies

1. Accept images only from **approved ACR repositories**.
2. Require **@sha256 digests**, disallowing mutable tags.
3. Require release images to carry a signature from a **trusted pipeline**.
4. Require provenance subjects to match the digest and approved source repo/ref.
5. Require valid SBOM attestations with policy-compliant metadata.
6. Define reviewed exception rules for sandboxes and emergency break-glass rather than applying identical rules across every namespace untested.

### Avoid causing outages with unprepared verifiers

- Registry/attestation lookups can hit network timeouts.
- Fail-open vs. fail-closed is an operational and security decision.
- OIDC verification / trust roots require updates.
- Clusters run system workloads not signed by your app pipeline.
- Roll out policies in **audit mode** before enforcing whenever the engine supports it.

**Never claim Azure Policy verifies Cosign signatures for every image by default**; actual capabilities must be installed and configured.

## 51. Using image digests on Azure Container Apps and App Service

Beyond AKS, Azure Container Apps and App Service for Containers can run registry images per each service's configuration capabilities.

### General principles

- Grant least-privilege **pull permissions** to runtime identities.
- Use immutable image digest references wherever supported by the platform.
- Verify artifacts before updating deployment resources.
- Record the **release → digest → SBOM → provenance** mapping.
- Test regional/registry connectivity and auth.
- Where the platform lacks built-in attestation admission checks, enforce policy gates in CI/CD deployment automation and monitor for post-deploy drift.

**Never claim App Service or Container Apps automatically validates Cosign signers on pull because an image is signed.** Verification must be integrated into the release workflow per platform capabilities.

## 52. Pitfalls with image tags and live rollouts

Suppose the pipeline verified:

~~~text
checkout-api:stable -> digest A
~~~

Before deployment, someone pushes `stable` pointing to digest B. If the Deployment references tag **stable**, the cluster may run something other than the verified artifact.

### Preventing TOCTOU

1. Resolve the tag to **digest A** right after publishing.
2. Verify signature, provenance, and SBOM for **digest A**.
3. Deploy **@sha256:A**, never reusing the mutable tag.
4. Inspect live Pod image IDs/digests during rollout.
5. Alert if workloads drift to another digest.

**Time-of-check-to-time-of-use (TOCTOU)** occurs when an artifact is verified in one state but consumed after a mutable reference changes.

## 53. Release record: what evidence should be saved?

Sample release record:

| Field | Illustrative value |
|---|---|
| Service | `checkout-api` |
| Environment | `production` |
| Application version | `1.8.0` |
| Source repo | `org/checkout-api` |
| Source commit | Full Git SHA |
| CI system/run | Azure DevOps run ID |
| Builder identity | Trusted pipeline identifier |
| Maven/Gradle toolchain | Approved pinned versions |
| Base image | Immutable digest reference |
| Final image | `ACR repository@sha256:digest` |
| SBOM | CycloneDX document digest/referrer |
| Provenance | SLSA/in-toto statement reference |
| Signer | Verified issuer/key/workflow identity |
| Scanner results | Tool/database version, timestamp, exception IDs |
| Approval | Reviewer/environment gate |
| Deployment | AKS namespace/revision/rollout ID |
| Rollback | Previously approved image digest |

**Never store secrets, service principal passwords, or signing private keys in a release record.**

## 54. Artifact provenance for non-container JARs

Not every Azure Java app runs in a container. A **Spring Boot JAR** deployed to App Service via a package-based flow is still a controlled artifact:

~~~text
Git commit
   |
   v
Maven build -> checkout-api.jar
                 |
                 +--> SHA-256 of exact JAR bytes
                 +--> Build-resolved SBOM
                 +--> Signed provenance statement
                 |
                 v
         Azure Artifacts / approved artifact store
                 |
                 v
         App Service deployment
~~~

### Differences from containers

- Compute the digest over **JAR/package bytes** rather than an OCI manifest digest.
- Bind the SBOM to the JAR/package fingerprint and bundled dependencies.
- Artifact stores/CI release flows must support storing signatures/attestations/verification evidence or maintain a dedicated ledger.
- App Service host runtimes add system dependencies outside the JAR; assessments must account for the host runtime.

**A JAR checksum alone does not prove the JAR came from the right commit**; provenance and a trusted signer are still needed.

## 55. SBOMs with third-party SaaS and vendor libraries

Organizations often rely on commercial SDKs/JARs or binaries distributed only via vendor registries. These remain part of the supply chain.

### Workflow

1. Request SBOMs, provenance, license info, and advisory feeds from vendors where appropriate.
2. Verify signatures/checksums and distribution channels.
3. Record opaque components in the inventory and risk register if full inspection is impossible.
4. If a vendor SBOM mismatches the shipped package, escalate to the owner and verify before production.
5. Never assume a vendor binary is clean simply because it came from a major supplier.

**Missing evidence must be logged as missing**—never fill SBOMs with assumed packages as if they were verified.

## 56. Governing multiple environments: dev, staging, and production

An organization may structure:

~~~text
DEV
  ACR repository checkout-dev
  unsigned or test-signed images, restricted namespace
          |
          v
STAGING
  Trusted release digest verified
  SBOM, provenance and integration tests
          |
          v
PRODUCTION
  Same digest or approved promotion artifact
  Verified signature/attestation and environment gate
~~~

### Key principles

- **Never rebuild images during promotion** when the goal is shipping the exact bytes tested in staging.
- If images must be copied to another registry, verify **digests and evidence are preserved** via OCI tooling.
- Environments can have distinct configs and identities while keeping the same release artifact digest.
- Each environment has distinct pull/deploy permissions and approval boundaries.
- PR builds use separate test signing identities or remain unsigned for release; prod trusts only the release signer.

### Promotion does not guarantee ongoing safety

An image that passed staging can be hit by a new critical CVE later. Policies must check scan timestamps, trust, exceptions, and advisory freshness rather than relying blindly on a "tested" sticker.

## 57. SBOM diffs between two releases

Comparing **SBOM A** and **SBOM B** highlights:

- Newly added packages.
- Removed packages.
- Package version changes.
- Base image or OS component shifts.
- Lost component identifiers or relationships.
- License metadata changes.

~~~text
Release 1.8.0                      Release 1.8.1
  azure-identity X                    azure-identity Y     UPDATED
  spring-web A                        spring-web A        UNCHANGED
  JSON library B                      JSON library C      UPDATED
  old-logging-helper                  (removed)           REMOVED
                                     new-metrics-lib      ADDED
~~~

### Do not diff purely by text lines

SBOMs can vary in JSON field ordering, timestamps, and `bom-ref` IDs even when components are identical. Use diff tools that understand component identities, `purl`, and dependencies; for byte-level verification, inspect hashes and digests.

### When is a diff a warning sign?

A release meant to tweak HTML that unexpectedly introduces 50 new native packages or bumps an HTTP client major version may signal dependency or base-image drift. Investigate rather than automatically assuming an attack.

## 58. CVE advisories emerging after release

A common scenario:

~~~text
Day 0: Release 1.8.0 scan has no known critical issues
Day 14: New critical advisory published for package X
Day 15: Rescan stored SBOM shows affected versions
Day 16: Rebuild fixed release, verify provenance, deploy
~~~

### Why retain SBOMs?

You do not need to rebuild or pull old sources to learn which past releases included a library. You can query stored inventories of running and historical artifacts against new advisories immediately.

### Still does not replace runtime scanners

Build-time SBOMs can miss packages downloaded at runtime or binaries installed by container startup scripts. Pair runtime visibility, image scanning, and build policies to close that gap.

## 59. Azure Defender for Cloud and registry scanning

**Microsoft Defender for Cloud** provides security/vulnerability assessments for container registries, images, and workloads depending on **plan, configuration, scope, and supported features**.

### Use each layer in its proper role

- Container image scanning identifies components with CVEs.
- Runtime/workload security adds behavioral signals.
- Azure Policy provides guardrails for configurations and registries.
- Release pipelines must still manage artifact digests, provenance, signers, and policy gates.

**Never claim enabling Defender automatically provides SLSA provenance, Cosign signatures, or admission verification.** Those are separate layers whose actual integration must be verified.

### Triage by finding type

| Finding | Remediation direction |
|---|---|
| CVE in Java JAR | Dependency graph/BOM upgrade and testing |
| CVE in OS package | Base image refresh, rebuild, rescan |
| Image from unapproved registry | Policy/admission and source validation |
| Image digest differs from release record | Registry/deployment drift investigation |
| Invalid signature | Block rollout, investigate trust/signer |
| Unfamiliar provenance source | Quarantine artifact, inspect CI identity/workflow |
| Incomplete SBOM component metadata | Improve generator/coverage; do not drop policies |

## 60. Builder compromise: when trust must be revoked

Suppose a CI runner is compromised mid-build:

~~~text
Reviewed source commit -> compromised builder
                              |
                              v
                        malicious image
                              |
                              v
                      signed by release identity
~~~

Here the signature may be valid, yet **builder integrity** was violated. Provenance records the builder name, but cannot prevent a compromised builder from lying.

### Incident actions

1. Suspend the affected builder, pipeline, and release identity.
2. Scope all impacted run IDs, source commits, and **output digests**.
3. Locate all production/staging workloads running those digests.
4. Halt deployments from the compromised trust root.
5. Rotate/revoke signing credentials and trust per key/identity type and policy.
6. Rebuild artifacts on a clean trusted builder—never just re-sign old images.
7. Audit dependency caches, runner images, secrets, and external actions/tasks.
8. Build a forensic timeline and report per incident response policy.

**Do not wipe logs or bundles upon discovering a compromise**; preserve forensic evidence per policy while securing exposed secrets.

## 61. Signing key rotation and trust root rollover

When signing keys or identity certificates rotate:

~~~text
Verifier trusts signing key/identity A
       |
       v
Prepare new signer B; distribute trust policy
       |
       v
Test signed artifact with B in staging
       |
       v
Production begins accepting B under approval
       |
       v
Stop signing new releases with A
       |
       v
Retire A trust per time-bound policy
~~~

### Key considerations

- Historical artifacts signed with A must remain verifiable/auditable per retention policy.
- If A was **compromised**, never continue trusting A signatures for convenience.
- Keyless trust roots and issuer configs also require updates and audits.
- Never change issuer/trust policies and deployment tooling simultaneously without testing.
- Maintain rollback and quarantine procedures for incidents.

## 62. Policy exceptions and break-glass

Not every vulnerability can be fixed immediately. A package may have an advisory with no vendor patch yet, or an emergency fix image may be needed to end an outage.

### A valid exception requires

1. **Specific artifact digest**, never exempting an entire registry.
2. Specific CVE/advisory or policy rule.
3. Authorized approver and business justification.
4. Start and expiration timestamps.
5. Compensating controls: network isolation, feature flag off, WAF, RBAC.
6. Evidence and a permanent remediation plan.
7. Heightened monitoring during the exception window.

**Never create an "allow unsigned images forever" exception** because one Cosign check timed out over the network. Fix trust roots, check attestation availability, and use timebound audited break-glass procedures instead.

## 63. Lab A: generate a Maven SBOM from a Java lab app

**Objective:** generate an SBOM and inspect the dependency graph for a small Java app without deploying to Azure.

### Preparation

- Authorized Maven lab repository/project.
- Approved JDK, Maven, and CycloneDX Maven plugin versions.
- Trusted mirror/repository environment requiring no production secrets.
- For multi-module projects, run from the root Maven reactor.

### Steps

1. Create or select a lab Spring Boot app with two direct dependencies, e.g., **azure-identity** and **azure-storage-blob**.
2. Inspect `pom.xml` and approved BOM versions.
3. Add the CycloneDX Maven plugin per Section 11, replacing the plugin version placeholder.
4. Run **mvn -B -ntp verify** in the lab environment.
5. Confirm **target/bom.json** (or the plugin's actual output path) exists.
6. Validate against your chosen CycloneDX schema version using an approved validator.
7. Inspect components: name, version, purl, and type.
8. Locate **azure-core** in the SBOM and Maven dependency tree—it is typically a transitive component.
9. Compare direct vs. transitive counts and note gaps if the plugin misses any module.
10. Do not commit SBOM files exposing internal environment details if forbidden by policy; store as a lab CI artifact.

### Example component inspection (requires `jq`)

~~~bash
jq -r '.components[]? | [.name, .version, .purl] | @tsv' \
  target/bom.json
~~~

### Acceptance criteria

| Check | PASS when |
|---|---|
| Generator | Plugin version pinned with metadata present |
| Format | Valid CycloneDX JSON per validator |
| Scope | Reactor/profiles match lab project |
| Components | Direct and transitive runtime components listed |
| Identifiers | Names, versions, and purls present where detectable |
| Privacy | No credentials or secrets in output |
| Evidence | Build run and artifact digest/hash recorded |

## 64. Lab B: compare Maven SBOM vs. final container image

**Objective:** prove a container image holds more than Java dependencies alone.

### Preparation

- Authorized Docker/Buildx or image tooling.
- Lab registry/image—never use production push permissions.
- Syft pinned and installed from a trusted source.
- Valid image digest after build/push.

### Execution

1. Generate a build-resolved SBOM with Maven per Lab A.
2. Build a lab Docker image from the JAR using an approved base image.
3. Push to a lab ACR or use a local image per authorized workflow.
4. Record the **final immutable digest**, not just the tag.
5. Run **Syft** to generate CycloneDX JSON for the image digest.
6. Validate schemas of both SBOMs.
7. Cross-check whether Maven libraries appear in the image.
8. List newly appearing OS/base-image packages.
9. Inspect JRE and any agents/scripts installed in the final image.
10. Document **coverage limitations** clearly rather than assuming every difference represents tampering.

### Outputs

~~~text
sbom-java.cdx.json
sbom-image.cdx.json
image-digest.txt
comparison-report.md
~~~

The names above are **suggested lab outputs**, not a requirement to write additional files in this STEP 4 worker task.

## 65. Lab C: detect an SBOM mismatched against an artifact digest

**Objective:** understand evidence integrity checks without needing production signing keys.

### Hypothetical scenario

~~~text
SBOM A:
  subject = checkout-api@sha256:DIGEST_A

Deployed image:
  checkout-api@sha256:DIGEST_B
~~~

### Resolution

1. Check whether digest A/B are OCI indexes or platform-specific manifests.
2. Verify the release record and tag→digest mapping.
3. Inspect the attestation's actual **subject**, not just the filename.
4. Because artifacts differ, **reject SBOM A as evidence for B**.
5. Locate the true SBOM/provenance for `DIGEST_B` or rebuild via a trusted process.
6. Ensure verifier policies block rollout when evidence is missing.

### Takeaway

A schema-valid SBOM is **irrelevant** to the running artifact if the subject mismatches. Even a valid signature on SBOM A does not make it valid for image B.

## 66. Lab D: simulate policy-as-code with evidence

**Objective:** reason through release rules without deploying a production admission controller.

### Hypothetical policy

~~~yaml
policy:
  allowedRegistry: myregistry.azurecr.io
  requireDigest: true
  requireTrustedSigner: true
  requireProvenance: true
  allowedSourceRepository: org/checkout-api
  allowedReleaseBranch: main
  requireSbomSubjectMatch: true
  maxUnapprovedCriticalVulnerabilities: 0
~~~

**This YAML is conceptual only—not valid configuration for Kyverno, Gatekeeper, or Azure Policy.**

### Evaluate cases

| Case | Expected outcome |
|---|---|
| Image from allowlisted ACR, digest-pinned, full signature/provenance/SBOM | Eligible to pass after CVE/license checks |
| Image tagged `stable`, not digest-pinned | Block |
| Signed image, untrusted signer | Block |
| SBOM subject A, deployed digest B | Block |
| Provenance source from untrusted fork | Block |
| Unapproved Critical CVE | Block per hypothetical policy |
| Registry/signature lookup timeout | Handle per approved fail-closed/break-glass strategy |
| Cluster system image not built by app pipeline | Separate reviewed policy scope/exception |

### Acceptance criteria

Learners must explain **why** each case passes or fails, the gap between policy intent and verification implementation, and how to avoid accidentally blocking cluster system workloads.

## 67. Lab E: verify provenance and signatures in a lab registry

**Objective:** practice distinguishing signers, provenance, and artifact subjects on evidence published by a test pipeline.

### Prerequisites

- An image built and pushed by a trusted **lab** pipeline.
- Test signatures/attestations emitted by configured tooling.
- Approved Cosign/OCI tooling versions.
- Read-only registry identity; no signing private key is needed to verify.

### Procedure

1. Identify the exact **image@sha256:digest**.
2. Inspect the image manifest and confirm platform/index.
3. Locate the corresponding SBOM artifact/referrer or evidence store.
4. Inspect SBOM subject, metadata, and components.
5. Run Cosign verify against the lab's **trusted identity/issuer**.
6. Inspect the provenance predicate via the signature-verified verifier.
7. Verify **source repository, commit, builder, workflow, and subject digest**.
8. Compare against the release record.
9. Test verifying another unsigned image or one signed by an untrusted signer.
10. Document observed behavior and why policy fails.

**Never mint production signatures or escalate registry permissions** just to finish the lab. If the registry or tool lacks expected referrer support, document the limitation rather than faking a PASS.

## 68. Case study: Java checkout on Azure

An enterprise runs a commerce system:

- Git-hosted source, Java 21, and multi-module Maven.
- Azure DevOps release pipelines using workload identity federation.
- Spring Boot fat JAR packaged onto a JRE base image.
- ACR stores images and OCI artifact metadata.
- AKS runs `checkout-api`; Azure Container Apps runs `notification-worker`.
- Microsoft Defender for Cloud surfaces container image findings.
- Mandate: production must run **verified image digests** with SBOMs and provenance from approved builders.
- Evidence must remain queryable for CVE/incident investigations six months later.

### Incident

A critical advisory drops for a transitive dependency. Defender flags image digest B, yet the team believes the release pipeline already upgraded the dependency and pushed tag **stable**. An engineer discovers AKS Pods are still running digest B, while the pipeline's latest saved SBOM references digest C.

### Tasks

1. Explain why the `stable` tag cannot serve as a release identity.
2. Identify the actual digests running on AKS and `notification-worker`.
3. Locate the SBOM/provenance for **digest B**—never substitute digest C's docs.
4. Analyze the vulnerable dependency in both the Maven graph and final image.
5. Distinguish whether the CVE lives in a Java JAR or base OS package.
6. Inspect the builder/workflow/source commit that produced digest B.
7. Audit signer identity, trust root, and attestation integrity.
8. Inspect ACR tag mutations, IAM, and release history.
9. Design a clean patch/rebuild on a trusted builder.
10. Propose how to keep the exact image digest identical from staging → prod.
11. Design an AKS admission policy blocking mutable tags.
12. Design pipeline verification for Container Apps if lacking an equivalent admission gate.
13. Define remediation SLAs by exploitability, not CVSS alone.
14. Plan rollback if the patch breaks business logic.
15. Specify which logs/evidence must be retained for postmortem.

### Reference analysis

~~~text
Production AKS:
  digest B -- vulnerable dependency confirmed by SBOM B

Recent pipeline:
  digest C -- fixed dependency, SBOM C, provenance C

Mutable tag stable:
  currently points to C, but running Pods still have B
~~~

**Action:** do not alter SBOM B; stage verified digest C (or build clean digest D if C lacked policy gates), test in staging, deploy the exact digest, confirm Pod image IDs/digests, and rescan. If rolling back, revert only to a verified digest that still satisfies security policy or invoke an approved emergency exception.

## 69. Case study: artifact altered inside the pipeline

A third-party build-step provider is compromised. A production workflow runs that step and outputs a new image; the SBOM still lists normal dependencies, and the release signature is valid because the pipeline holds signing privileges.

### What failed?

- SBOMs do not detect every malicious behavior.
- Signatures only prove an identity signed an artifact.
- The builder/script trust boundary was breached.
- Provenance confirms which workflow ran, but cannot prevent a workflow from executing malicious code.

### Recovery steps

1. Block the compromised third-party action/plugin.
2. Rotate tokens and credentials commensurate with compromise scope.
3. Identify all digests emitted by potentially affected CI runs.
4. Quarantine or roll back workloads per incident policy.
5. Rebuild from a clean isolated runner using pinned, verified steps.
6. Inspect binary diffs, provenance, and rescan the new image.
7. Sign using a re-vetted release identity.
8. Tighten enforcement so PRs cannot alter signing workflows without protected approvals.

**Hardening the build process and builder integrity is the core fix**, not merely adding another SBOM scanner.

## 70. Runbook: investigating an untrusted artifact

An incident may start with a **signature verification failed** alert, an SBOM mismatch, or an unrecognized image digest in a cluster.

### Phase 1 — Scope the incident

1. Record workload name, namespace, environment, UTC timestamp, and alert source.
2. Fetch **running image digests** directly from the cluster/runtime, not just tags declared in Git.
3. Cross-check digests against the release ledger, pipeline runs, and registry metadata.
4. Identify all suspect digests and affected workloads/regions.
5. Preserve logs, SBOMs, provenance, signatures, and CI artifacts per incident policy.

### Phase 2 — Verify evidence

6. Inspect the actual image manifest/index and repository.
7. Fetch the exact SBOM matching that subject digest.
8. Verify attestation signature, issuer, signer/workflow identity, and trust root.
9. Verify provenance source repo, commit, builder ID, run ID, and materials.
10. Cross-check dependencies/BOM, scanner reports, and active advisories.

### Phase 3 — Decide response

11. If merely **missing evidence**, inspect publishing/registry/network first—never fabricate evidence.
12. If **untrusted signer/source**, halt promotion, quarantine the release, and notify security.
13. If **compromised builder/key**, revoke the trust path, rotate credentials, and identify all affected digests.
14. If **critical CVE**, assess exploitability, patch/mitigate, and rebuild a clean artifact.
15. If **tag drift**, redeploy an immutable verified digest per runbook.

### Phase 4 — Verify and close

16. Rebuild, scan, generate SBOM/provenance, and sign from a trusted pipeline.
17. Verify in staging under the exact same policy as production.
18. Deploy the approved digest and confirm runtime actually runs it.
19. Monitor application errors, performance, resource consumption, and security alerts.
20. Write the postmortem: root cause, detection gaps, control bypasses, action owners, and deadlines.

### Safe evidence template

~~~text
Incident ID:        supply-chain-incident-001
Detected at (UTC):  <TIME>
Service:            checkout-api
Namespace/env:      prod/checkout
Running digest:     sha256:<ACTUAL_DIGEST>
Expected digest:    sha256:<APPROVED_DIGEST>
Source commit:      <FULL_SHA_FROM_VERIFIED_PROVENANCE>
Trusted builder:    <BUILDER_ID>
Signature:          verified / failed / missing
SBOM subject:       matches / mismatch / missing
Open findings:      <ADVISORY_IDS>
Impact:             <KNOWN_FACTS>
Hypothesis:         <UNVERIFIED_HYPOTHESES>
Owner:              <TEAM>
Remediation:        <APPROVED_PLAN>
~~~

Never put private keys, credentials, raw CI tokens, or PII into incident reports.

## 71. Monitoring and metrics for supply-chain controls

Generating an SBOM should not be just a green checkbox in CI. Operational metrics:

| Metric | Meaning |
|---|---|
| **% of release artifacts with valid SBOM** | Inventory coverage |
| **% of prod digests with verified provenance** | Origin assurance coverage |
| **% of releases with trusted signatures** | Signing coverage |
| **% of workloads using digest pinning** | Control over mutable tags |
| **% of image components identified** | Coverage indicator (requires measurement definition) |
| **Policy failures by root cause** | Registry/signature/source/SBOM/CVE |
| **Time from advisory to affected digest identification** | Incident triage speed |
| **Time from patch to verified deployment** | Remediation lead time |
| **Active production exceptions** | Risk backlog |
| **Expired/compromised signing credentials** | Trust management health |
| **Artifacts missing retention evidence** | Audit readiness |
| **Gate false-positive rate** | Policy signal quality |

### Do not turn coverage into a gameable metric

An auto-generated SBOM listing only one component still yields 100% "SBOM present" while providing zero real visibility. Measure **schema validity, runtime/component coverage, subject match, generator integrity, and verification**.

## 72. Costs and limitations of supply-chain controls

Potential cost drivers:

- CI runners and build/test/scanning minutes.
- Storage for pipeline artifacts, caches, SBOMs, and provenance.
- Azure Container Registry storage, transfer/replication, and retention.
- Vulnerability-scanning services / Defender plans.
- Azure Key Vault signing operations and key/HSM tiers when used.
- OCI artifact referrers/metadata storage per registry.
- Azure Monitor / Log Analytics ingestion for verification/admission events.
- Cluster admission controller compute and latency.
- Engineering time triaging false positives and upgrading dependencies.

### Costs go beyond the Azure bill

Overly weak controls invite severe incidents; overly rigid or poorly rolled-out controls block production releases and raise MTTR. Tailor policies by risk tier, test in staging, and adopt **audit → enforce** transitions where engines support them.

### Responsible optimization

1. Generate SBOMs on release builds and when image digests publish, avoiding expensive scans on trivial no-op actions.
2. Cache dependencies from approved sources while checking integrity and expiration.
3. Store evidence with clear retention policies indexed by digest.
4. Query affected digests from stored SBOM inventories first before rescanning every image.
5. Balance vulnerability rescan cadence against advisory feed updates.
6. Measure gate latency; cache verification carefully within trust/time bounds.
7. Never weaken security gates just to shave seconds off builds without risk evaluation.

**Never hardcode CI/ACR/Key Vault/Defender unit prices**, as regions, plans, request volumes, and pricing change. Consult the Azure Pricing Calculator and your organization's Cost Management.

## 73. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
|---|---|---|
| "`mvn dependency:tree` is a complete image SBOM" | Misses base image/JRE/OS and standard format/metadata | Combine build SBOM with final image SBOM |
| "Having an SBOM JSON file means it is trustworthy" | File can be altered or belong to another artifact | Verify subject digest, signer, and source |
| "CycloneDX is always better than SPDX" | Depends on use case, version, and tooling | Pick standard per consumer and policy |
| "An SBOM guarantees zero CVEs" | An SBOM is an inventory | Scan against advisories, triage, and patch |
| "Scanner reports 0 Critical means no malware" | Scanners do not prove benign code behavior | Enforce trusted source/build, tests, and runtime security |
| "Scanners detect 100% of packages" | Shaded, native, or dynamic artifacts can be missed | Review coverage and use multi-source SBOMs |
| "Tag `1.8.0` is immutable" | Tags can be repointed | Pin OCI manifest digests |
| "SHA-256 proves who built the image" | Hashes identify content only | Use signed provenance and identity |
| "A valid signature means clean code" | Signers or builders can be compromised | Enforce source/builder policies, scanning, and audits |
| "A signed commit signs the JAR/image" | Git commits differ from build outputs | Require artifact digests and provenance |
| "Having SLSA JSON achieves SLSA Level X" | Levels depend on builder controls and evidence | Assess against spec and real assurance |
| "`provenance mode=min` auto-signs releases" | Build metadata differs from signatures | Sign and verify attestations under trust policy |
| "Signing SBOM A covers image B" | Subject mismatch | Bind SBOMs to exact digests |
| "Cosign verify needs no issuer check" | Risks trusting unauthorized signers | Allowlist exact identity and issuer |
| "Private ACR means images are trusted" | Private registries can still receive malicious pushes | Enforce least privilege and policy verification |
| "Defender scan generates SLSA provenance" | Scanners differ from build provenance | Add trusted build attestations |
| "App Service verifies Cosign on every image automatically" | Not enabled by default | Enforce pre-deploy verification gates per platform support |
| "Share one signing secret across all PRs" | Untrusted PRs could sign releases | Separate PR and release permissions |
| "Non-exportable KMS keys always work with Cosign" | Provider/algorithm support varies | Verify integration beforehand |
| "Old SBOMs aren't needed once old images are deleted" | Audits and CVE forensics need historical evidence | Retain release evidence by policy |
| "A Critical CVE always means exploitable" | Advisory matches differ from exploitability | Evaluate context, reachability, and forensics |
| "Rolling back tag `stable` restores the old version" | Mutable tag may have shifted | Roll back to a verified digest |
| "One SBOM scan lasts forever" | New CVEs emerge post-release | Rescan stored SBOMs as advisories update |
| "Build once is automatically reproducible" | Timestamps, caches, and toolchains cause drift | Test reproducibility and pin inputs |
| "Self-generated attestation is independent proof" | A builder can emit false statements if compromised | Trust builder identity and harden pipelines |

## 74. Production checklist before accepting an artifact

| Category | Acceptance criteria |
|---|---|
| **Ownership** | Clear owners for source, builder, scanners, signing, and runtime |
| **Source control** | Protected branches/releases, reviews, and workflow permissions |
| **Toolchain** | Pinned versions for JDK, Maven/Gradle, plugins, Buildx, and scanners |
| **Dependency sources** | Approved mirrors/registries with dependency-confusion protections |
| **Dependency locking** | Verifiable direct and transitive versions |
| **Base image** | Approved vendor/source, digest pinning, and patch cadence |
| **Build isolation** | Trusted release runners separated from untrusted PRs |
| **Secrets** | No leaks in source, build args, logs, provenance, or attestations |
| **Build SBOM** | Generated from resolved graph and schema-validated |
| **Image SBOM** | Covers final OCI image, JRE, and OS packages within scanner limits |
| **Artifact identity** | Exact final digest with clear index/platform semantics |
| **Provenance** | Source commit, builder ID, run ID, materials, and subject |
| **Signature** | Approved trust root, signer identity, and issuer |
| **Attestation** | SBOM/provenance predicates valid and subject-matched |
| **ACR** | Registry/repo permissions, networking, retention, and referrers tested |
| **CVEs** | Scanner policy, advisory freshness, and exceptions with owner/expiry |
| **Licenses** | Metadata sufficient to review obligations and unresolved items |
| **CI/CD** | Build, sign, verify, and deploy responsibilities separated |
| **Deployment** | Digest pinning on AKS/Container Apps/App Service where supported |
| **Admission/policy** | Verifies trusted source/signature/attestation per active engine |
| **Canary** | Staged rollout, SLO measurement, and rollback digest ready |
| **Evidence storage** | SBOMs, provenance, and signatures preserved for audits/incidents |
| **Runtime inventory** | Live running digests tracked and mapped to releases |
| **Monitoring** | Alerts for verification failures, unexpected images, and CVE/policy violations |
| **Incident response** | Runbooks for builder/key compromise and malicious packages |
| **Cost** | CI, scanning, ACR, Key Vault, and logging budgeted |
| **Drift** | Detects tag or workload digest divergence from desired state |

### Final acceptance rule

**Release only digests generated, inventoried, signed, and verified by a trusted workflow** with policy-compliant evidence. When data is missing, log the exact missing evidence and enforce exception/deny rules—never force a PASS merely to make dashboards green.

## 75. Self-check questions

1. Which links make up the software supply chain from Git to AKS?
2. Why can't `pom.xml` describe every component inside the final container image?
3. What is an SBOM and how does it differ from a vulnerability scan?
4. Which fields and component identifiers should an SBOM include?
5. Do CycloneDX and SPDX always convert metadata losslessly?
6. How does a PURL differ from a SHA-256 digest?
7. How do direct and transitive dependencies affect CVE triage?
8. How does a source SBOM differ from a build-resolved SBOM?
9. Why does a final image SBOM also include OS/JRE packages?
10. How can shaded JARs cause scanners to miss dependencies?
11. Why can't an SBOM prove 100% of packages were detected?
12. Why must an SBOM be bound to an artifact digest?
13. Can a signed SBOM with a mismatched subject be used for another image?
14. Does an SPDX license expression imply legal compliance?
15. How do the CycloneDX Maven plugin and a Maven BOM differ?
16. When generating an aggregate BOM, why run from the root reactor?
17. Why doesn't Gradle `testRuntimeClasspath` necessarily represent the production JAR?
18. How do Syft image scans and Maven plugins differ in strengths?
19. How does an image tag differ from an OCI manifest digest?
20. How do multi-platform image indexes affect SBOM coverage?
21. What role does ACR play for artifacts and evidence?
22. Does pushing an image to a private ACR prove the image is trusted?
23. What information should artifact provenance contain?
24. How does provenance differ from a signed Git commit?
25. How does a SLSA predicate differ from a SLSA assurance level?
26. How does an in-toto attestation link a subject and a predicate?
27. Does image signing differ from signing an SBOM/provenance attestation?
28. Why must verifiers check both signing identity and issuer?
29. Which CI/OIDC conditions does keyless signing require?
30. Which least-privilege permissions should a Key Vault signing key grant?
31. Does a transparency log prove code is completely safe?
32. How do OCI referrers and registry cleanup interact with evidence retention?
33. Can a hand-written SLSA JSON file be considered compliant provenance?
34. Why must release CI be separated from untrusted PRs?
35. Which risks does Azure DevOps workload identity federation mitigate?
36. Is GitHub OIDC for Azure tokens automatically a Sigstore signing identity?
37. Do Docker Buildx `--sbom`/`--provenance` flags automatically create trusted signatures?
38. Why should secrets never enter Docker `ARG`s or provenance?
39. Does a reproducible build automatically prove source is malware-free?
40. Why verify a digest and deploy that exact digest to prevent TOCTOU?
41. What should an admission controller verify?
42. Does Azure Policy verify Cosign signatures by default?
43. Why do App Service and Container Apps need separate verification gates depending on capabilities?
44. Which evidence does a non-container JAR release require?
45. How do SBOMs and SBOM diffs assist triage of new CVEs?
46. Why distinguish Java package CVEs from base OS package CVEs?
47. When a signer or builder is compromised, are signatures still sufficient proof?
48. Why does key rotation require updating verifier trust policies?
49. Which constraints must a valid policy exception specify?
50. When a Pod runs digest B while the SBOM cites digest C, how should you respond?
51. Why does a moved `stable` tag not prove Pods are running the new version?
52. Should ACR releases retain evidence after deleting old images?
53. Which metrics measure provenance verification effectiveness?
54. Which Azure costs arise from supply-chain governance?
55. What are the three most critical decisions to avoid deploying an untrusted artifact?

## References

- Microsoft Learn — *Azure Container Registry overview*: https://learn.microsoft.com/azure/container-registry/container-registry-intro
- Microsoft Learn — *Azure Container Registry authentication*: https://learn.microsoft.com/azure/container-registry/container-registry-authentication
- Microsoft Learn — *Azure Container Registry repository management*: https://learn.microsoft.com/azure/container-registry/container-registry-repositories
- Microsoft Learn — *Workload identity federation for Azure DevOps*: https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure?view=azure-devops
- Microsoft Learn — *Azure DevOps pipelines overview*: https://learn.microsoft.com/azure/devops/pipelines/get-started/what-is-azure-pipelines?view=azure-devops
- Microsoft Learn — *Managed identities for Azure resources*: https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview
- Microsoft Learn — *Microsoft Defender for Cloud container security*: https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction
- Microsoft Learn — *AKS security baseline and policies*: https://learn.microsoft.com/azure/aks/security-best-practices
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Azure Artifacts*: https://learn.microsoft.com/azure/devops/artifacts/start-using-azure-artifacts?view=azure-devops
- OWASP — *Software Component Verification Standard*: https://owasp.org/www-project-software-component-verification-standard/
- CISA — *Software Bill of Materials*: https://www.cisa.gov/sbom
- CycloneDX — *Specification*: https://cyclonedx.org/specification/overview/
- CycloneDX — *Maven plugin*: https://github.com/CycloneDX/cyclonedx-maven-plugin
- CycloneDX — *Gradle plugin*: https://github.com/CycloneDX/cyclonedx-gradle-plugin
- SPDX — *Specification*: https://spdx.dev/specifications/
- Package URL — *PURL specification*: https://github.com/package-url/purl-spec
- Anchore — *Syft documentation*: https://github.com/anchore/syft
- Anchore — *Grype vulnerability scanner*: https://github.com/anchore/grype
- SLSA — *Specification and provenance*: https://slsa.dev/spec/
- In-toto — *Attestation framework*: https://in-toto.io/
- Sigstore — *Cosign overview*: https://docs.sigstore.dev/cosign/overview/
- Sigstore — *Signing and verifying*: https://docs.sigstore.dev/cosign/signing/overview/
- ORAS — *OCI artifact client documentation*: https://oras.land/docs/
- Open Container Initiative — *Image and Distribution specifications*: https://opencontainers.org/
- Docker — *Build attestations*: https://docs.docker.com/build/metadata/attestations/
- Docker — *Buildx build options*: https://docs.docker.com/reference/cli/docker/buildx/build/
- GitHub Docs — *OIDC with Azure*: https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure
- Kubernetes — *Admission controllers*: https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/
- Kyverno — *Verify Images policies*: https://kyverno.io/docs/writing-policies/verify-images/
- NIST — *Secure Software Development Framework*: https://csrc.nist.gov/Projects/ssdf
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
