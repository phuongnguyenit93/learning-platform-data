# Vulnerability scanning for operating systems and software dependencies

Virtual machines, containers, and cloud applications rely on many software components: the operating system, kernel, system libraries, runtimes, application packages, and direct or transitive dependencies. A vulnerable component can give an attacker a path to gain privileges, read data, execute code, or disrupt the workload. Compute workload security therefore requires continuously inspecting what is installed and running.

**Vulnerability scanning** is the process of inventorying components, matching versions and configurations against published vulnerability data, and assessing risk for remediation. OS scanning focuses on the kernel and OS packages; dependency scanning focuses on libraries, modules, and packages used by the application. The two complement each other and must apply both to images before deployment and to running workloads.

In **CLOUD_CORE_SERVICES_COMPUTE**, scan results guide operations teams on when to update base images, patch VMs, upgrade libraries, rebuild container images, or isolate workloads. An effective workflow combines CVE data, inventories/SBOMs, exploitability, exposure, service criticality, and remediation deadlines.

## 1. Software vulnerabilities and risk sources

A vulnerability is a weakness in software or configuration that can be exploited to affect system confidentiality, integrity, or availability. Vulnerabilities can reside in:

- **Operating system:** kernel, system libraries, network services, package managers, and administrative utilities.
- **Runtimes:** Java runtime, .NET runtime, Node.js, Python interpreter, or other execution environments.
- **Direct dependencies:** packages explicitly declared and called by the application.
- **Transitive dependencies:** packages pulled in indirectly by another dependency.
- **Supporting components:** web servers, reverse proxies, monitoring agents, SSH servers, database clients, or backup tools.
- **Images and artifacts:** packages sitting in container image layers or machine images, even if unused in the primary execution path.

A single workload can contain hundreds or thousands of packages. Inspecting only application source code while ignoring the OS, runtime, and packaged layers leaves many risks undetected.

### 1.1. Vulnerability scanning vs. configuration checks

Related security activities answer different questions:

| Activity | Primary question | Example |
| --- | --- | --- |
| Vulnerability scanning | Which components have versions affected by known vulnerabilities? | OpenSSL package falls within an affected version range |
| Configuration/compliance scanning | Is the system configured according to baseline? | SSH allows root login or firewall is overly permissive |
| Malware scanning | Is malware or evidence of malicious execution present? | File contains a trojan or cryptominer |
| Secret scanning | Were secrets committed into source code or artifacts? | API key appears in a repository |
| Penetration testing | Can weaknesses be exploited in the live context? | Attack chain spanning application flaws and IAM permissions |

A scanner flagging a package with a CVE does not prove the system has been compromised. Conversely, zero reported CVEs do not guarantee a workload is safe; a scanner may lack complete inventory, vulnerability feeds, or package recognition support.

## 2. CVE, CVSS, and vulnerability data

To match packages against vulnerabilities, scanners typically rely on vulnerability databases and vendor advisories.

### 2.1. What is a CVE?

**CVE (Common Vulnerabilities and Exposures)** is a public identifier for a documented vulnerability. A CVE helps security teams, vendors, and tools refer to the exact same issue.

CVE records may include:

- Description of affected components and conditions.
- Affected version ranges or fixed versions.
- Potential impacts such as code execution, privilege escalation, or denial of service.
- References to advisories, patches, and technical details.
- Severity scores when available.

Not every vulnerability receives a CVE immediately upon discovery. Some packages have ecosystem- or vendor-specific advisories. Scanners must therefore keep data feeds updated and support the operating systems and package managers in use.

### 2.2. CVSS expresses technical severity

**CVSS (Common Vulnerability Scoring System)** provides a standardized method for scoring vulnerability severity. CVSS scores typically range from 0.0 to 10.0 and group as follows:

| CVSS score | Severity rating |
| --- | --- |
| 0.0 | None |
| 0.1–3.9 | Low |
| 4.0–6.9 | Medium |
| 7.0–8.9 | High |
| 9.0–10.0 | Critical |

A CVSS Base Score describes technical characteristics of a vulnerability in a standardized context. It does not automatically reflect the specific workload running in your organization. A high-scoring vulnerability in an uninstalled or unreachable component may carry lower priority than a lower-scoring flaw actively exploited on a public-facing service.

When evaluating findings, inspect the CVSS vector and CVSS version used—not only the aggregate number.

### 2.3. Additional signals for prioritization

To decide what to fix first, combine:

- **CISA Known Exploited Vulnerabilities (KEV):** a catalog of vulnerabilities observed being exploited in the wild.
- **EPSS (Exploit Prediction Scoring System):** data-driven probability estimates of a CVE being exploited in the near term.
- **Vendor advisories:** guidance from OS, library, or product vendors regarding affected versions and patches.
- **Exploit intelligence:** information about public exploit code, exploitation prerequisites, and active campaigns.
- **Workload context:** Internet exposure, processed data sensitivity, process privileges, and service criticality.

KEV and EPSS supplement CVSS rather than replacing risk assessment. EPSS is a predictive probability, not certainty that a specific system will be attacked. KEV indicates exploitation has occurred somewhere, not that every instance holding the package is compromised.

## 3. Inventorying components before scanning

A scanner can only evaluate components it recognizes. Build reliable inventories for VMs, container images, and applications.

### 3.1. Operating system inventory

An OS inventory should capture:

- Distribution name and version, edition, or release.
- Running kernel and installed kernel packages.
- List of packages with exact versions and architectures.
- Package repositories or sources.
- Update status and timestamp of last check.
- Agents, background services, and software installed outside default packages.

On Linux, package managers typically provide installed package data. Examples:

~~~bash
# Debian/Ubuntu
dpkg-query -W

# RHEL/Fedora and RPM-based systems
rpm -qa

# OS and kernel information
cat /etc/os-release
uname -r
~~~

These commands produce an inventory; they do not by themselves determine whether packages are vulnerable or patched. Cross-reference with distribution advisories and scanner data feeds.

### 3.2. Application dependency inventory

Applications typically use manifest files and lockfiles to pin dependencies. Examples:

| Ecosystem | Common files |
| --- | --- |
| Node.js | package.json, package-lock.json, yarn.lock, pnpm-lock.yaml |
| Python | requirements.txt, poetry.lock, Pipfile.lock |
| Java/Maven | pom.xml, dependency tree, project lock/version management |
| Java/Gradle | build.gradle, build.gradle.kts, dependency locking |
| .NET | .csproj, packages.lock.json, NuGet assets |
| Go | go.mod, go.sum |
| Rust | Cargo.toml, Cargo.lock |

Lockfiles reveal exact resolved versions, including transitive dependencies. Reading only a manifest with version ranges may miss which exact packages landed in the built artifact.

### 3.3. SBOMs to support inventory

An **SBOM (Software Bill of Materials)** is an inventory of software components in an artifact or product. An SBOM can record package names, versions, origins, dependency relationships, licenses, and identifiers such as PURL or CPE.

An SBOM helps answer: "Which images contain package X at version Y?" when a new CVE breaks. It also aids inspecting transitive dependencies and comparing components across releases.

An SBOM is not a vulnerability report. Match the SBOM against the latest advisory/CVE data to identify affected components. An SBOM is only trustworthy when generated from the exact deployed artifact and stored alongside that artifact's ID or digest.

## 4. Scanning operating system vulnerabilities

OS scanning can run against live hosts, root filesystems, or machine images before release.

### 4.1. Scanning packages and kernels

Scanners usually compare package inventories against distribution advisories. They must accurately identify the distribution, release, repository, and package version. Many distributions backport security fixes into packages without bumping the upstream version number in ways a generic scanner expects.

For instance, a distribution package may retain most of the upstream version string while adding security patches in a vendor revision suffix. A scanner comparing only upstream numbers may emit false positives. Verify official distribution advisories and release metadata in such cases.

The kernel deserves special attention:

- A new kernel package may be installed while the machine has not rebooted, leaving the old kernel running.
- A package-inventory scanner may report the patch installed, while a runtime scanner still flags the active kernel as unpatched.
- Some kernel patches use live patching; verify patch application status and vendor support.
- Third-party kernel modules may be incompatible with newer kernels.

Check both installed packages and the actually running kernel/runtime.

### 4.2. Scanning running VMs

Two common approaches exist:

- **Authenticated/agent-based scanning:** the scanner uses an agent or appropriate credentials to read inventory from inside the guest OS. This generally identifies packages more accurately.
- **Agentless/cloud API scanning:** tooling inspects metadata, snapshots, or inventories via cloud APIs. Coverage and depth depend on permissions and provider capabilities.

External network scanning can identify exposed services, ports, and banners, yet rarely sees all packages installed inside a VM. Never rely solely on network scans to assess OS packages.

### 4.3. Scanning machine images before deployment

Scanning images before launching VMs stops vulnerabilities at the source. Pipelines can:

1. Build the image from a pinned base image.
2. Collect package inventory or generate an SBOM.
3. Scan OS packages, kernel packages, and installed software.
4. Match against updated advisories.
5. Block release per risk policy.
6. Store scan results alongside the image ID/digest.

An image scanned cleanly at build time can accumulate newly disclosed vulnerabilities later. Re-scan stored images and running VMs on a schedule and whenever major new CVEs emerge.

## 5. Scanning application dependency vulnerabilities

Dependency scanning is commonly called **SCA (Software Composition Analysis)**. SCA tools read manifests, lockfiles, SBOMs, or built artifacts to identify libraries and match them against advisories.

### 5.1. Direct and transitive dependencies

Suppose an application declares library A. Library A depends on B and C; B depends on D. A CVE in D can impact the application even though the team never declared D directly.

SCA needs to construct a dependency graph showing:

- Direct packages declared by the application.
- Transitive packages pulled in indirectly.
- Versions resolved in lockfiles.
- Dependency paths leading to affected packages.
- Recommended upgrade versions or patches.

When upgrading dependencies, verify API compatibility and behavioral changes. You cannot always upgrade one package independently if it is constrained by a framework or runtime.

### 5.2. Ecosystem-specific dependency checks

Examples of commands usable in pipelines or development environments:

~~~bash
# Node.js: check dependencies via package-lock
npm audit --omit=dev

# Python: check dependencies listed in requirements
pip-audit -r requirements.txt

# OSV-Scanner: scan project lockfile
osv-scanner scan --lockfile=package-lock.json
~~~

Commands and flags vary by tool version. For Node.js, `--omit=dev` fits only when targeting production dependencies; still scan dev dependencies if they execute in build pipelines or can affect development environments. For Python, scan the exact environment or lockfile representing the deployed artifact.

For Java, .NET, Go, and Rust, pick scanners supporting their lock/manifest formats. If an application bundles libraries into a fat JAR, assembly, or binary, verify whether the scanner inspects the final artifact or only reads manifests.

### 5.3. Unused dependencies

A package with a CVE is not necessarily exploitable through the application. However, do not dismiss it merely because developers believe the package is never called.

Impact evaluation should examine:

- Is the package included in the deployed artifact?
- Is the module loaded at startup or auto-registered?
- Does a call path exist to the vulnerable function?
- Can the package be invoked via plugins, reflection, dynamic loading, or configuration?
- Can the flaw be triggered before the application calls the package directly?

Some tools offer reachability analysis to estimate whether code can call a dependency. This aids prioritization but is not absolute proof of exploitability. Document rationale whenever accepting risk on an un-upgraded dependency.

## 6. Scanning container images and deployment artifacts

Container images can contain multiple layers combining OS packages and application dependencies. Scanning source code before building is insufficient to verify final contents accurately.

### 6.1. Scanning images after build

An effective workflow typically follows:

1. Build the container image from a Dockerfile and a pinned base image version.
2. Record the image digest.
3. Scan OS packages and application dependencies inside the image.
4. Generate an SBOM for the image.
5. Evaluate vulnerabilities against policy.
6. Sign or record provenance if required by workflow.
7. Push/promote only policy-compliant images to deployment registries.

Example using Trivy:

~~~bash
# Scan vulnerabilities in image
trivy image --scanners vuln my-service:1.4.2

# Export SBOM in CycloneDX format
trivy image --format cyclonedx --output sbom.cdx.json my-service:1.4.2
~~~

Replace example image names with your actual images. Scan by digest rather than mutable tags so results stay tied to exact artifact contents.

### 6.2. Multi-stage images and leftover packages

Multi-stage builds reduce unnecessary packages in final images. However, scanners must inspect the final deployed image. Scanning only a build stage can flag packages absent from production; scanning only source without scanning the final image misses packages installed later in the Dockerfile.

Base images also need monitoring. When a base image receives security updates, application images must be rebuilt to pick up fixed packages. Simply updating a base image tag in a Dockerfile without rebuilding leaves running images unchanged.

### 6.3. Registry and runtime scanning

Registry scanning re-scans stored images when CVE feeds update. This detects images that previously passed policy but now carry newly disclosed vulnerabilities.

Runtime scanning adds live context:

- Which images are currently running in clusters or VMs.
- Which Containers/Pods run outdated digests.
- Whether a workload is Internet-exposed or processes untrusted data.
- Which packages are reachable by running processes.
- Whether outdated images remain in registries or node caches.

Never scan only the `latest` image in a repository. Older versions may still be running or used during autoscaling, rollbacks, or recovery.

## 7. Evaluating and prioritizing findings

A scanner report can contain hundreds of findings. Remediating strictly by raw CVSS order can waste time on low-impact packages while leaving actively exploited flaws open on public services.

### 7.1. Prioritization factors

| Factor | Questions to answer |
| --- | --- |
| Severity | What are the CVSS score and technical impact? |
| Active exploitation | Is the CVE in KEV or is active exploitation observed? |
| Likelihood of exploitation | What are the EPSS score, public exploits, and required preconditions? |
| Exposure | Is the workload Internet-facing, exposing public ports, or ingesting untrusted data? |
| Reachability | Is the package on an active execution or reachable path? |
| Process privileges | Does the service run as root/admin or under restricted privileges? |
| Business impact | Does the workload handle critical data or support essential services? |
| Remediability | Is there a tested patch, workaround, or replacement version? |

### 7.2. Illustrative triage matrix

| Scenario | Priority action |
| --- | --- |
| Critical CVE under active exploitation on an Internet-facing VM | Emergency remediation, isolation, or immediate compensating controls if unpatchable |
| High CVE in a reachable dependency of an API handling sensitive data | Prioritize dependency upgrade and release a fix on a tight timeline |
| High CVE in a package absent from the final image | Verify inventory and scope; document exclusion from deployed artifacts |
| Medium CVE on an internal host with restricted privileges | Address per SLA and maintenance schedule based on context |
| Package belongs to an end-of-life OS | Plan OS upgrade or workload migration; do not simply silence alerts |

This matrix is illustrative, not a universal SLA. Define deadlines based on security policies, regulatory obligations, exposure, and operational capacity.

### 7.3. Checking vendor-backported versions

When a scanner flags an OS package with a CVE, verify:

1. Do the distribution and release match the advisory?
2. Does the package revision already include the backported patch?
3. Does the running kernel require a reboot to activate the patch?
4. Did the scanner accurately parse package epoch, release, and architecture?
5. Does the vendor advisory confirm `fixed` or `not affected` status?

Never close a finding merely because a version string looks recent. Record the advisory or vendor evidence explaining the decision.

## 8. Integrating scanning into CI/CD

Scanning should run at multiple points in the software lifecycle rather than once right before production.

### 8.1. Scan checkpoints

- **Pull request/commit:** inspect manifests, lockfiles, and newly added dependencies.
- **Build:** scan OS packages and dependencies inside the artifact.
- **Pre-publish:** enforce policies blocking releases above thresholds.
- **Registry:** re-scan stored images whenever CVE feeds change.
- **Runtime:** inventory and scan running VMs/containers.
- **Scheduled:** re-check machine images, long-lived VMs, and infrequently rebuilt workloads.
- **Emergency advisories:** query inventories/SBOMs to locate all affected artifacts and workloads.

### 8.2. Example pipeline

~~~yaml
stages:
  - source_scan
  - build
  - artifact_scan
  - publish

dependency-scan:
  stage: source_scan
  script:
    - run-sca --lockfiles
    - export-dependency-report

build-image:
  stage: build
  script:
    - docker build -t app:commit-sha .

scan-final-image:
  stage: artifact_scan
  script:
    - trivy image --scanners vuln --format json --output image-vuln.json app:commit-sha
    - trivy image --format cyclonedx --output sbom.cdx.json app:commit-sha
    - evaluate-vulnerability-policy image-vuln.json
  artifacts:
    paths:
      - image-vuln.json
      - sbom.cdx.json

publish-image:
  stage: publish
  script:
    - publish-image-by-digest
  rules:
    - if: '$VULNERABILITY_POLICY_PASSED == "true"'
~~~

Command names like `run-sca`, `evaluate-vulnerability-policy`, and `publish-image-by-digest` are placeholders for your organization's tools. Production pipelines must pass scan outputs securely between jobs and prevent the publish job from running if policy evaluation fails.

### 8.3. Setting sensible blocking thresholds

Avoid blocking every finding mechanically, which can stall pipelines—especially when dependencies carry unreviewed advisories or OS packages emit non-applicable alerts. Conversely, ignoring all alerts to keep builds green defeats scanning altogether.

Policies can combine:

- Minimum CVSS severity.
- Presence in KEV or active exploits.
- Whether the package resides in the final artifact.
- Whether the dependency is reachable.
- Whether the workload is exposed or handles critical data.
- Whether a verified patch or upgrade version exists.
- Whether exceptions have an owner and expiration date.

Start in warning mode to tune scanner quality and calibrate policies before enabling broad enforcement. Once release gates block builds, maintain a clear process for false positives and exceptions.

## 9. Remediating vulnerabilities

Once a finding is confirmed impactful, select remediation suited to the affected layer.

### 9.1. Patching the operating system

For VMs, update packages via the OS package manager or centralized patch management tools. Examples:

~~~bash
# Debian/Ubuntu: update package index and apply package updates
sudo apt-get update
sudo apt-get upgrade

# RHEL-family: review security advisories and apply patches per policy
sudo dnf updateinfo list --security
sudo dnf update --security
~~~

Run updates aligned with your distribution, repositories, and maintenance policies. Avoid uncontrolled major upgrades in production. Before patching, review changed packages, dependencies, reboot requirements, and rollback options.

For fleets managed with immutable images, the sustainable fix is updating the base image, building a new image, re-scanning, and replacing instances via rolling updates. Patching live instances directly can work in emergencies, but propagate the fix back into the pipeline so new instances do not spawn from vulnerable images.

### 9.2. Upgrading dependencies

When a dependency fix is available:

1. Identify affected packages and dependency paths.
2. Select the fixed version per official advisory.
3. Update the manifest and lockfile.
4. Run unit, integration, compatibility, and security tests.
5. Rebuild the artifact and scan the final artifact.
6. Roll out via canary/rolling strategy.
7. Monitor runtime errors and compatibility.

Avoid hand-editing a single package version in a lockfile when the package manager can re-resolve cleanly. Use ecosystem tooling to update dependencies consistently and verify transitive changes.

### 9.3. When no patch is available

If no patch exists yet, temporary mitigations may be needed:

- Disable or constrain the affected component if the application remains functional.
- Block endpoints or ports that can trigger the vulnerability.
- Restrict source access via security groups, firewalls, WAF, or network policies.
- Reduce process privileges and isolate the workload from critical data.
- Disable vulnerable plugins or features if recommended by the vendor.
- Increase monitoring, anomaly detection, and prepare isolation plans.

Mitigations do not replace long-term patches. Record an owner, review date, and conditions for retiring the exception.

### 9.4. Rebuilding images and replacing workloads

For VM and container images, updating packages on a build host does not fix previously launched instances or containers. You must:

1. Update the base image or dependencies.
2. Build a new artifact.
3. Re-scan OS and dependencies.
4. Record the ID/digest and SBOM.
5. Deploy a canary.
6. Replace instances/pods running old artifacts.
7. Verify runtime inventory shows no remaining vulnerable workloads.
8. Deprecate or retire old images per policy.

Do not delete old images immediately upon release if needed for rollback or forensics. However, prevent autoscaling or pipelines from inadvertently launching new instances from known critically vulnerable images.

## 10. Managing false positives and exceptions

Scanners can produce false positives due to missing metadata, vendor backports, unbundled dependencies, or version parsing quirks. Every exclusion decision must rest on evidence.

### 10.1. False positive verification workflow

1. Verify whether the package actually exists in the artifact or live machine.
2. Check full package name, ecosystem, architecture, and exact version.
3. Cross-reference vendor advisories and CVE sources.
4. Verify patch/backport status or affected preconditions.
5. Confirm whether the finding applies under active configurations and enabled features.
6. Record evidence, verifier, and review date.

Never apply a blanket ignore rule across all images or package versions just because one instance proved to be a false positive.

### 10.2. Risk-acceptance exceptions

When remediation cannot meet the deadline, an exception should document:

- Affected CVE/finding and package.
- Workload, image ID/digest, and environment.
- Reason patching is currently blocked.
- Residual risk and exploitability.
- Active compensating controls.
- Accountable owner.
- Approver.
- Expiration date and review schedule.

Exceptions must expire. Upon expiration, re-evaluate, renew with formal approval, or remediate. Never turn ignore rules into permanent vulnerability suppression.

## 11. Monitoring running workloads and detecting drift

CI/CD scans inspect artifacts before deployment. Once running, workloads can change via manual patches, ad-hoc package installs, or out-of-band IaC edits. This **configuration drift** can cause runtime state to diverge from scanned images.

To detect drift:

- Collect periodic inventories from VMs and nodes.
- Compare runtime packages against approved images/SBOMs.
- Monitor VMs lacking agents or failing to report inventory.
- Inventory actual running Pod/container image digests.
- Detect machines running end-of-life OS versions.
- Re-scan on schedule and upon major new CVE announcements.
- Flag machines with installed patches awaiting reboot.

In Kubernetes, inspect both running container images and node OSes. Scanning Pod images does not replace scanning worker node kernels and packages. Likewise, scanning nodes does not replace SCA for libraries inside applications.

## 12. Selecting scanning tools

No single scanner covers every layer. Combine tools by target layer:

| Layer to check | Tool category | Examples |
| --- | --- | --- |
| OS packages on VMs | Agent or authenticated scanner | Cloud/security platform vulnerability management tools |
| Root filesystems or machine images | Filesystem/image scanner | Trivy, Grype, and integrated image-builder scanners |
| Application dependencies | SCA | OSV-Scanner, Dependabot, Snyk, or CI platform scanners |
| Container images | Registry/image scanner | Trivy, Grype, or registry scanning |
| SBOMs | SBOM generator and analyzer | Syft, Trivy, and CycloneDX/SPDX tooling |
| Runtime inventory | Cloud security posture/workload protection | Agents, cloud APIs, or Kubernetes integrations |

When evaluating tools, assess:

- Support for your distributions, package managers, and languages.
- Ability to scan lockfiles, binaries, image layers, and root filesystems.
- Advisory feed quality and update cadence.
- Recognition of vendor backports and revision formats.
- Reachability analysis and ability to map findings to live workloads.
- Output support for SBOMs, JSON/SARIF, and pipeline integration.
- Agent deployment model, required permissions, and performance overhead.
- Support for exception management, auditing, and remediation tracking.

Pilot tools across a representative set of VMs and repositories before organization-wide rollout. Measure false-positive rates, coverage, and operational overhead.

## 13. Measuring vulnerability management effectiveness

Falling finding counts do not necessarily mean lower risk; scanners may have stopped running or inventories may be incomplete. Track coverage, remediation speed, and residual risk.

| Metric | Meaning |
| --- | --- |
| Asset coverage | Percentage of VMs, images, nodes, and repositories scanned |
| Scan freshness | Time since last scan and currency of CVE feeds |
| Critical/High findings | Finding counts by severity and by workload |
| KEV exposure | Number of workloads running actively exploited vulnerabilities |
| Mean time to remediate | Average duration from detection to remediation |
| SLA compliance | Percentage of findings resolved within deadline |
| Exception age | Age and count of active exceptions |
| Vulnerable workload count | Number of live instances/containers still running affected artifacts |
| EOL asset count | Number of workloads running end-of-life OSes/runtimes |

Group metrics by environment, owner, application, asset type, and exposure. One finding appearing across 100 instances of the same image should be fixed at the source image and rolled out—never manually closed 100 times without fixing the root artifact.

## 14. Example: handling a CVE in a Java service dependency

A Java service runs on VMs and containers. A scanner detects an HTTP library in the dependency tree affected by a CVE. The report shows the package is pulled in transitively by a framework; both production images and older registry images contain the affected version.

Team response:

1. Review the CVE, vendor advisory, and affected version range.
2. Inspect the dependency tree to identify the parent package pulling the library.
3. Verify whether the library ships in the production artifact and whether affected code paths are reachable.
4. Select the fixed framework or library version and update manifest and lockfile.
5. Run unit/integration tests, verify compatibility, and rebuild the JAR/container image.
6. Scan the final image, generate an SBOM, and confirm the finding is resolved.
7. Release a canary and monitor HTTP errors, latency, and application logs.
8. Roll out across the fleet and confirm no VMs/Pods remain on the old digest.
9. Mark old images deprecated, block new workloads from launching them, and retain per policy for controlled rollback.

If the framework cannot be upgraded immediately due to compatibility, restrict affected endpoints or features, increase monitoring, and document a time-bound exception. Once the patch is tested, close the exception and replace remaining workloads.

## 15. Common mistakes

- Scanning only source code without scanning OS packages and final images.
- Scanning only container images while ignoring worker node kernels and packages.
- Scanning only direct dependencies while ignoring transitive dependencies.
- Using CVSS alone as the sole prioritization criterion.
- Ignoring actively exploited CVEs or Internet-exposed workloads.
- Assuming a scanner finding automatically means the system is actively compromised.
- Closing false positives based solely on version numbers without checking vendor backports.
- Updating packages on build hosts without rebuilding and replacing running workloads.
- Failing to re-scan registries when new CVE data is published.
- Tracking scan results by mutable image tags instead of digests.
- Ignoring findings indefinitely without an owner or expiration date.
- Failing to track VMs/nodes that stop reporting inventory or reach end-of-life.
- Treating an SBOM as proof an artifact has no vulnerabilities.

## 16. Recommended operational workflow

1. **Inventory assets:** catalog VMs, machine images, container images, nodes, repositories, and owners.
2. **Collect component inventories:** OS packages, kernels, runtimes, lockfiles, and per-artifact SBOMs.
3. **Scan across layers:** source/dependencies, machine images, final container images, and running VMs/nodes.
4. **Update feeds:** rely on trusted advisories, CVEs, vendor bulletins, KEV, and exploit intelligence.
5. **Prioritize by context:** combine CVSS, exploitability, exposure, reachability, privileges, and business impact.
6. **Enforce CI/CD policies:** block releases on agreed thresholds with a defined exception process.
7. **Remediate:** patch OSes, upgrade dependencies, rebuild images, replace workloads, or apply temporary mitigations.
8. **Verify:** re-scan artifacts, verify runtime digests/packages, and confirm findings close.
9. **Monitor drift:** scan periodically and detect unmanaged machines or end-of-life OSes/runtimes.
10. **Report:** track coverage, scan freshness, SLAs, KEV exposure, remediation time, and exceptions.

## 17. Key principles to remember

1. OS scanning and dependency scanning are distinct layers; run both.
2. Accurate inventories and lockfiles/SBOMs enable scanners to identify components reliably.
3. CVEs identify vulnerabilities; CVSS scores severity; KEV, EPSS, and workload context guide prioritization.
4. Vendor advisories matter because packages can contain backported fixes even when upstream version numbers look unchanged.
5. Pre-deployment image scanning must be paired with registry re-scanning and live workload scanning.
6. Scan results must bind to artifact IDs/digests and scan timestamps.
7. Fix at the source image/dependency and roll out replacements to eliminate vulnerable versions.
8. False positives and exceptions require evidence, owners, compensating controls, and expiration dates.
9. SBOMs support inventory and traceability, not proof that an artifact is vulnerability-free.
10. Coverage, scan freshness, and remediation speed matter just as much as remaining finding counts.

Vulnerability scanning across operating systems and software dependencies gives engineering teams visibility into risk across the entire component stack of compute workloads. By combining accurate inventories, up-to-date vulnerability feeds, exploit-aware prioritization, and verified remediation, organizations shorten exposure windows and operate cloud VMs, containers, and applications more securely.
