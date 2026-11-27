# Runtime Lifecycle Tracking and Dependency Upgrade Planning

A serverless function running smoothly today can become a liability within a few months if its Java runtime reaches end-of-support, its framework stops receiving patches, a library develops a vulnerability, or its container base image grows outdated. Upgrades are therefore an integral part of operations and system governance, not merely routine maintenance for developers.

With Java serverless, track multiple distinct lifecycle layers:

- The runtime and operating system managed by the cloud provider.
- The Java/JDK version and vendor distribution.
- Frameworks, direct libraries, and transitive dependencies.
- Build tools, compiler plugins, and packaging tools.
- Container base images, runtime agents, and native libraries.
- Function configurations, deployment artifacts, and integration contracts.

An application may run Java 21 and still be insecure if Spring Boot, a logging library, or the base image contains a vulnerability. Conversely, updating a single dependency can alter serialization behavior, connection pooling, or startup characteristics, directly affecting functions running at scale.

This lesson covers how to build an inventory, track end-of-support dates, triage vulnerabilities, build an upgrade plan, test compatibility, and roll out incrementally to keep Java serverless workloads secure and auditable.

## 1. What Is the Runtime and Dependency Lifecycle?

A software lifecycle describes the stages from release, active maintenance, patching, and limited support through end-of-support or removal.

Common milestones:

| Milestone | Meaning | Governance Action |
|---|---|---|
| General availability | Version is officially released | Evaluate, test, and add to the allowed catalog |
| Active support | Receives bug fixes and updates per vendor policy | Monitor releases and security advisories |
| Maintenance support | Scope of fixes may be limited | Plan version transition |
| End of standard support | Standard support period ends | Set upgrade deadlines and exception rules |
| End of life / end of support | No further standard patches or support | Upgrade or apply approved mitigations |
| Runtime deprecation | Provider begins phasing out runtime support in the service | Migrate to a supported runtime |
| Runtime retirement | Runtime can no longer be deployed or operated per service policy | Complete migration ahead of the deadline |

Milestone names and sequencing differ across providers. A vendor may apply `deprecated`, `blocked for new deployments`, and `blocked for updates` at different dates. Do not assume that blocking new function creation automatically stops running functions immediately; read the specific provider policy.

### 1.1. Four Lifecycles to Track Separately

| Layer | Examples | Lifecycle Source |
|---|---|---|
| Cloud runtime | AWS Lambda managed Java runtime, Azure Functions runtime, Google Cloud Functions runtime | Cloud provider |
| Java platform | OpenJDK builds, Oracle JDK, Amazon Corretto, Microsoft Build of OpenJDK, Eclipse Temurin | JDK vendor/distribution |
| Application dependencies | Spring Boot, Jackson, Netty, Log4j, AWS SDK | Project/vendor maintainers |
| Build/deployment stack | Maven, Gradle, plugins, container base images, buildpacks | Tool/image maintainers |

Never collapse these milestones into a single `Java version` field. A function can run a provider-supported Java runtime while its dependencies are end-of-support, or have supported dependencies on a provider runtime nearing retirement.

## 2. Cloud-Managed Runtimes vs. Self-Packaged Runtimes

There are two common deployment models.

**Managed runtime:** the function selects a Java runtime provided by the cloud provider. The provider manages most of the runtime environment, patches the OS/runtime per service policy, and publishes deprecation/retirement schedules.

**Custom runtime or container image:** the engineering team packages the runtime, JDK/JRE, system libraries, and application into an artifact or image. The team owns tracking and updating more components, including the base image, OS packages, JDK, and native libraries.

| Aspect | Managed Runtime | Custom Runtime / Container |
|---|---|---|
| Underlying runtime updates | Managed by provider per policy | Managed by app team / build pipeline |
| Version control | Selected from provider-supported list | Proactively chosen version |
| OS patching responsibility | Typically provider-owned | Owned by image maintainer |
| SBOM | May require combining provider info with app artifact | Can be generated for the entire image/artifact |
| Risk | Impacted by retirement schedules or runtime updates | Forgetting to rebuild images or keeping stale packages |
| Testing | Verify behavior before/after runtime updates | Test runtime, image, and application together |

Managed runtimes reduce operational overhead but do not remove responsibility for governing application dependencies. Containers offer environment control while increasing update responsibility and artifact provenance requirements.

### 2.1. Automatic Runtime Updates

Some platforms apply runtime security updates automatically; others provide controls for update timing or runtime management settings. Clarify:

- When does the provider update runtimes?
- Can runtime versions be pinned or updates deferred?
- Can runtime updates change patch levels without altering function configuration?
- Is advance notice provided before runtime deprecation/retirement?
- Is a redeploy required to pick up patches?
- Can an existing function keep running even when new deployments are blocked?
- How do you inspect the actual runtime version in a live environment?

Never assume a managed runtime receives every patch instantaneously. Read the service's runtime management documentation and inspect live version details.

## 3. Building a Runtime and Dependency Inventory

You cannot govern lifecycles without knowing which versions the organization runs. The first step is inventorying every function and related artifact.

Fields to record:

| Field | Example |
|---|---|
| Service/function | `orders-worker` |
| Owner/team | `commerce-platform` |
| Environment | `production` |
| Provider/region | AWS / `ap-southeast-1` |
| Deployment type | Managed runtime / container |
| Runtime | Java 21 |
| JDK vendor | Amazon Corretto |
| Framework | Spring Boot 3.x |
| Build tool | Maven |
| Artifact version | `orders-worker 2.8.4` |
| Base image | Image name + immutable digest |
| Direct dependencies | AWS SDK, Jackson, Micrometer |
| Deployment date | Current release date |
| Support deadline | Target migration completion date |
| Criticality | Tier 1 / Tier 2 / Tier 3 |
| Data classification | Public / Internal / Confidential / Restricted |
| Exception owner | Approver of any active exception |

Do not inventory production functions only. Account for staging, preview, scheduled jobs, DLQ replay workers, migration utilities, and rarely invoked functions. An idle function can still hold code or secrets and present risk.

### 3.1. Automating the Inventory

Combine multiple sources:

- Cloud resource inventory / configuration APIs.
- Infrastructure-as-Code state.
- Deployment manifests.
- Build artifact metadata.
- Container registry metadata.
- Pipeline-generated SBOMs.
- Cloud asset inventories and organization policies.

Reconcile sources to catch manually created functions or deployed artifacts without source owners. Record the last-updated timestamp and data source so operators know whether the inventory is fresh.

### 3.2. Classifying Criticality

Not every function needs the exact same upgrade deadline. Prioritize based on:

- Does it process payments, identity, or sensitive data?
- Does it expose a public HTTP endpoint?
- Does it hold broad IAM permissions or access multiple systems?
- Does it sit on a critical transaction path?
- Does it process replayable events?
- Does it carry special compliance or audit mandates?
- Is it reachable from the Internet or untrusted messages?

Public functions, high-privilege workloads, and sensitive-data handlers require higher risk priority.

## 4. Tracking Java Releases and JDK Vendors

Java publishes feature releases alongside security/critical patch updates on vendor-specific schedules. LTS releases carry longer support under vendor policies, yet LTS does not guarantee every JDK distribution shares the same end-of-support date or support terms.

When choosing a Java version, evaluate:

- Current Java feature release.
- Vendor distribution and support policy.
- Vendor end-of-support date.
- Security update cadence.
- Supported CPU architectures.
- Compatibility with cloud runtimes.
- Compatibility with frameworks and libraries.
- Build tool and test agent support.
- Parity across local, CI, and production environments.

Do not record only `Java 21` in the inventory. Record the distribution/vendor and patch/build level whenever data sources expose them.

### 4.1. LTS Is Not the Only Reason to Upgrade

Adopting a newer Java LTS brings longer support, performance gains, and new capabilities. Yet switching versions can also alter:

- Bytecode targets and compiler behavior.
- Reflection, module access, and encapsulation.
- TLS/security defaults.
- Garbage collector and memory behavior.
- JIT compilation and startup profiles.
- Serialization or library compatibility.
- Native agents, JNI, and GraalVM compatibility.

Plan upgrades around support deadlines, security risk, compatibility, and engineering value. Do not upgrade solely for a newer version number, and do not wait until the brink of EOL to start.

## 5. Tracking Frameworks and Transitive Dependencies

Direct dependencies are libraries declared in the project. Transitive dependencies are libraries pulled in indirectly through other dependencies.

Example:

~~~text
orders-worker
  -> spring-boot-starter-web
       -> spring-web
       -> spring-context
       -> spring-core
       -> jackson-databind
       -> logging implementation
  -> cloud provider SDK
       -> HTTP client
       -> authentication library
       -> JSON library
~~~

A transitive dependency can carry a CVE even when developers never declared it directly. Reviewing `pom.xml` or `build.gradle` alone is therefore insufficient; analyze the artifact's resolved dependency graph.

Components to inventory:

- Frameworks and framework starters.
- JSON/XML parsers.
- HTTP clients and TLS providers.
- Logging facades and implementations.
- Database drivers and connection pools.
- Cloud SDKs and authentication libraries.
- Serialization, compression, and archive libraries.
- Metrics/tracing agents.
- Native libraries and JNI bindings.
- Test/build plugins that execute in CI.

### 5.1. Dependency Management and Version Alignment

With Maven, use dependency management / BOMs to coordinate versions consistently. With Gradle, use platforms, version catalogs, and dependency locking appropriately.

Goals:

- Prevent modules from unintentionally pulling mismatched versions.
- Minimize version conflicts.
- Keep the dependency graph reproducible.
- Upgrade frameworks and SDKs smoothly in compatible sets.
- Document justifications whenever overriding a version for a security patch.

Never force a transitive dependency onto a newer version solely because a scanner suggests it if the framework is incompatible. Check release notes and run tests before overriding.

## 6. Build Tools, Plugins, and Container Base Images Have Lifecycles Too

Upgrading the Java runtime while leaving an outdated Maven/Gradle wrapper can break builds or lack support for newer compilers. Compiler, test, shade, packaging, and native-image plugins must also be governed.

For containers:

- Record image names and digests.
- Track the distro, package manager, and base image support status.
- Rebuild from patched base images.
- Inspect OS packages and native libraries.
- Never use floating tags like `latest` as production artifact identifiers.
- Scan images post-build and pre-deploy.
- Retain artifact provenance and build metadata.

If a base image is updated upstream without rebuilding the function, production continues running the stale image. Tracking only the tag in a `Dockerfile` is insufficient; inventory the deployed digest.

## 7. SBOM: Knowing Exactly What an Artifact Contains

A Software Bill of Materials (SBOM) lists the software components inside an artifact. An SBOM identifies which packages, versions, and dependency relationships are shipped.

Two common formats:

- **CycloneDX:** widely used for component inventories, dependency relationships, and security use cases.
- **SPDX:** standard format for representing component details, licenses, and provenance.

An SBOM may contain:

- Component names and versions.
- Package URLs (PURLs) or identifiers.
- Suppliers/vendors.
- Licenses.
- Dependency relationships.
- Hashes/checksums.
- Metadata about the SBOM-generating tool.
- Artifact/build references.

Condensed illustrative example:

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "components": [
    {
      "type": "library",
      "name": "jackson-databind",
      "version": "2.x.y",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.x.y"
    }
  ]
}
~~~

This is illustrative data, not a real project SBOM. Exact versions must come from the built artifact.

### 7.1. SBOMs for Java Functions

For Maven/Gradle, generate SBOMs from the release artifact's dependency graph. For container images, generate or enrich with OS package and runtime layer inventories. An SBOM from source dependencies may not accurately mirror a production image if shading, relocation, packaging, or image layering alters the artifact.

Link the SBOM to:

- Artifact checksum.
- Git commit.
- Build pipeline/run ID.
- Image digest.
- Function version/revision.
- Deployment environment.

Store SBOMs alongside release evidence so when a new CVE emerges, you can query which functions contain the affected package.

## 8. Vulnerability Scanning and CVE Management

Software Composition Analysis (SCA) tools compare packages/versions against vulnerability databases and advisories. Findings typically report CVEs, severity, affected ranges, fixed versions, and dependency paths.

Common feeds:

- GitHub Security Advisories.
- NVD.
- OSV.
- Framework/library vendor advisories.
- Cloud provider security bulletins.
- Container registry / image scanning.
- CI or artifact registry SCA tools.

Each feed varies in update latency and coverage. Zero findings from a scan do not prove a package is completely vulnerability-free.

### 8.1. CVSS Is Not the Entire Prioritization Decision

CVSS describes technical severity, not full risk within your specific deployment environment.

When prioritizing CVEs, consider:

- Is the affected version actually present in the deployed artifact?
- Is the vulnerable code path exercised?
- Does the function have public exposure?
- Can an attacker control the input?
- What IAM permissions or sensitive data does the function access?
- Is there a public exploit or evidence of active exploitation?
- Is an official patch available?
- Is a safe workaround available?
- Are there statutory or contractual remediation deadlines?

A critical CVE in an unloaded package carries a different practical risk than a high CVE in a parser handling public input. However, never use "unreachable code path" as an exemption excuse without reliable analysis.

### 8.2. Triage Decisions

| Assessment Outcome | Action |
|---|---|
| Affected and easily exploitable | Prioritize emergency patching or reduce exposure immediately |
| Affected, compatible patch exists | Prepare hotfix/upgrade and deploy promptly |
| Affected, no patch available yet | Mitigate, monitor advisories, and set a review deadline |
| Not affected by version/config | Record evidence and exclusion rationale |
| False positive | Document scanner rule, package path, and evidence |
| Unclear impact scope | Investigate further; do not mark resolved prematurely |

Never close a CVE ticket merely because a scanner stopped alerting after a package rename or rule suppression. Retain artifact/version evidence and rationale.

## 9. Vulnerability Remediation SLA Policies

Organizations should define remediation SLAs by risk tier. Exact timelines are approved by governance/security policy; no universal schedule fits every company.

Illustrative policy framework:

| Priority Tier | Example Conditions | Handling Direction |
|---|---|---|
| Emergency | Active exploitation, public exposure, severe impact | Immediate triage, reduce exposure, and hotfix |
| Critical | Severe CVE, component present in production | Prioritize patch within short policy-defined window |
| High | Exploitable within service context | Schedule into priority sprint and track deadline |
| Medium | More limited exploitability or impact | Schedule within regular maintenance cycle |
| Low | Low risk, no clear attack path | Monitor and update on routine schedule |

SLAs should distinguish time to acknowledge, triage, mitigate, and deliver a permanent fix. When no patch exists yet, reducing exposure serves as temporary mitigation rather than completed remediation.

## 10. Tracking Runtime Deprecation and EOL

Each runtime/provider needs a lifecycle record tracking:

- Runtime name and version.
- Provider service and region.
- Support start date.
- Deprecation date.
- New-deployment cutoff date.
- Existing-function update cutoff date.
- Retirement date.
- Recommended replacement.
- Link to official announcement.
- Migration owner.
- Internal status and deadline.

Provider dates can shift. Periodically check official announcements and update the inventory; never copy EOL dates from an old blog post.

### 10.1. Pre-EOL Alert Checkpoints

Internal checkpoints can be structured as:

- **T-180 days:** inventory impacted functions, pick target runtime, and estimate effort.
- **T-120 days:** check framework/library compatibility, create migration branch and test plan.
- **T-90 days:** deploy to dev/staging, resolve incompatibilities.
- **T-60 days:** canary or partial production rollout.
- **T-30 days:** complete bulk migration, track exceptions.
- **Before deadline:** verify zero production functions remain on the retiring runtime.

This is a sample schedule for organizations to adapt. Runtimes can be deprecated on shorter timelines or follow different rules; always treat provider notices as authoritative.

Do not wait until deployments are blocked before starting migration. Actual lead time depends on function count, frameworks, integrations, and approval workflows.

## 11. Planning Upgrades by Dependency Graph

Do not bump every library simultaneously without understanding compatibility relationships. Start with the dependency graph and group changes logically.

Typical ordering example:

1. Select a supported target Java runtime/JDK.
2. Upgrade build tools and compiler/test plugins to build on the target JDK.
3. Upgrade the framework/BOM to a version supporting the target Java release.
4. Upgrade cloud SDKs and integration libraries.
5. Upgrade remaining direct and transitive dependencies.
6. Rebuild container base images or custom runtimes.
7. Run unit, integration, contract, and load tests.
8. Regenerate SBOMs and rescan artifacts.
9. Deploy canary and observe.
10. Complete rollout and verify inventory.

Actual order may vary. A framework might require a newer JDK first, or the provider runtime might need switching before upgrading the framework. Record dependency constraints and release notes as justification.

### 11.1. Splitting Upgrades to Limit Blast Radius

An upgrade cycle may bundle multiple independent changes:

- Java major version.
- Framework major version.
- Logging implementation.
- HTTP client.
- Database driver.
- Cloud SDK.
- Base image.

If everything changes in one release, pinpointing the cause of a regression becomes difficult. For large systems, split upgrades into controlled batches. For urgent CVEs, ship a minimal hotfix updating only the affected component.

## 12. Java Serverless Compatibility Checklist

Before upgrading Java or a framework, inspect:

**Build and bytecode**

- Compiler source/release target.
- Maven/Gradle wrapper.
- Compiler, Surefire/Failsafe, and packaging plugins.
- Annotation processors and code generation.
- Shading/relocation.
- Dependency convergence and duplicate classes.

**Runtime**

- Provider support for Java version and CPU architecture.
- JVM flags and memory limits.
- TLS/cipher defaults.
- Reflection and module access.
- Classpath/module path.
- Timezone, locale, and trust store.
- JNI/native libraries.

**Frameworks and integrations**

- Dependency injection and startup hooks.
- HTTP serialization/deserialization.
- Validation and exception mapping.
- Database drivers and connection pools.
- Cloud SDK authentication/credential chains.
- Metrics, logging, and tracing agents.
- Function handler signatures and event models.

**Serverless behavior**

- Cold start/init duration.
- Timeouts and memory.
- Concurrency and thread lifecycles.
- Connection reuse across invocations.
- Environment variables/configuration.
- Temporary storage and file system.
- Shutdown hooks and graceful termination.
- Retries, idempotency, and partial batch responses.

An upgrade can compile cleanly yet still change runtime behavior. Test on the exact target runtime/container and realistic triggers.

## 13. Testing Java Major Upgrades

When moving from one Java LTS to the next, check higher-risk areas:

- Deprecated or removed APIs.
- Reflection into internal JDK APIs.
- Strong encapsulation and module access.
- Garbage collector and heap sizing.
- TLS defaults and certificate handling.
- Charset/locale/timezone behavior.
- Serialization compatibility.
- Threading and executor behavior.
- JIT warm-up, startup, and memory footprint.
- Agent/profiler/APM compatibility.

Run the test suite on the target JDK in CI before changing production runtimes. When possible, build a production-equivalent artifact and run integration tests on the target provider runtime or container image.

### 13.1. Build JDK vs. Runtime JRE

The build JDK and runtime image can differ. This is valid when controlled for:

- Bytecode target.
- Vendor compatibility.
- Native library architecture.
- Required modules.
- Runtime classpath.
- Security providers / trust stores.
- Build provenance.

Do not assume code built on a newer JDK runs on an older runtime, or vice versa. Verify bytecode target levels and APIs actually invoked.

## 14. Upgrading Frameworks and Libraries

Major framework upgrades often introduce breaking changes in configuration, auto-configuration, dependency baselines, and APIs. Read the framework's migration guide and release notes before changing versions.

For Spring Boot or similar frameworks, check:

- Supported Java baseline.
- Managed dependency BOMs and versions.
- Deprecated configuration properties.
- HTTP server / embedded container versions.
- Jackson/JSON behavior.
- Validation namespaces/APIs.
- Security filter chains and defaults.
- Observability instrumentation.
- Startup / lazy initialization.
- Native image / AOT compatibility if used.

Never override a framework-managed dependency without checking the compatibility matrix. An individual security patch may require a framework patch release rather than bumping one transitive library in isolation.

## 15. Upgrading Container Base Images

For container-packaged functions, image lifecycle is part of runtime lifecycle.

Process:

1. Identify the currently deployed base image and digest.
2. Inspect distro, packages, and JDK build.
3. Read image vendor advisories.
4. Choose an updated, supported base image.
5. Rebuild the application image from source and lockfiles.
6. Scan the image and SBOM.
7. Test startup, handler, native libraries, and security settings.
8. Push an immutable image and record the digest.
9. Deploy revision/canary.
10. Retain scan evidence and the running image digest.

Illustrative Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/orders-worker.jar /app/app.jar

USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The image tag in this example illustrates base image selection only. In production, pin images by digest with a controlled digest-update process; tags can shift to new contents over time.

Do not run the application as root unless necessary. Keeping images lean shrinks attack surface and pull times, but never strip packages required for TLS, timezones, or native runtime behavior.

## 16. Automating Checks in CI/CD

Pipelines can enforce dependency and runtime checks at multiple stages:

**Pull request**

- Compile with target JDK.
- Unit and integration tests.
- Dependency graph diff.
- SCA scan.
- License policy.
- Secret scanning.
- Build reproducibility checks.

**Build/release**

- Generate SBOM.
- Scan artifact and container image.
- Check base image support.
- Sign artifact/image if policy requires.
- Generate provenance/attestation.
- Record commit, toolchain, and dependency lock state.

**Deploy**

- Verify allowed runtime.
- Check security gates.
- Verify target environment and region.
- Canary/smoke tests.
- Monitor errors, latency, cold starts, and memory.
- Record deployment revision and artifact digest.

**Periodic**

- Rescan SBOMs against fresh vulnerability feeds.
- Check runtime EOL dates.
- Check end-of-support dependencies.
- Detect stale image digests.
- Find unowned functions or functions deployed outside standard pipelines.

An SCA scan at build time reflects vulnerability data only at that moment. A new CVE may be published after the artifact ships; rescan deployed SBOMs rather than scanning source only at build time.

## 17. Example Dependency Inspection with Maven

These commands illustrate inspecting the dependency tree and resolved versions:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw -DskipTests=false verify
~~~

`dependency:tree` reveals transitive dependencies and the paths pulling packages into the project. `effective-pom` shows resolved versions and configurations after applying parent POMs and BOMs. These commands do not detect CVEs by themselves; pair them with SCA tools and advisory databases.

With Gradle, you can use:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind
./gradlew test
~~~

Dependency locking and version catalogs keep resolved versions under control. Commit lockfiles per project conventions so builds remain reproducible.

## 18. Post-Upgrade Testing

A runtime/dependency upgrade test suite should cover:

| Test Group | What to Verify |
|---|---|
| Unit | Business logic and edge cases remain unchanged |
| Integration | Databases, HTTP clients, serialization, and SDKs |
| Contract | Event schemas, API request/response formats, and compatibility |
| Security | TLS, authentication, IAM, deserialization, and scanners |
| Startup | Cold starts, init duration, and readiness |
| Load | Throughput, p95/p99 latency, memory, and GC |
| Resilience | Retries, timeouts, idempotency, redelivery, and DLQs |
| Regression | Business outcomes compared with the previous version |
| Deployment | Artifacts, image digests, environment config, and rollback |
| Observability | Logs, metrics, traces, and alerts keep working |

For queue consumers, send test messages and verify acks, retries, partial batch failures, visibility/ack deadlines, and duplicate handling. For HTTP functions, verify response statuses, headers, authentication, and timeouts.

Do not check merely that the function returns `200`. Inspect side effects and business state to catch silent regressions.

## 19. Canaries and Phased Rollouts

A runtime upgrade can affect every invocation of a function upon deployment. Canaries catch defects on a slice of traffic before full rollout.

A general strategy:

~~~mermaid
flowchart TD
    A["Build new artifact + SBOM"] --> B["Security and compatibility gates"]
    B --> C["Deploy dev/staging"]
    C --> D["Integration and load tests"]
    D --> E["Canary partial traffic"]
    E --> F{"SLOs and correctness met?"}
    F -->|Yes| G["Gradually shift traffic"]
    G --> H["Rollout complete"]
    F -->|No| I["Halt rollout / rollback"]
    I --> J["Investigate and prepare fix"]
~~~

Use platform-native mechanisms:

- AWS Lambda versions + aliases with weighted routing.
- Cloud Run revisions and traffic splitting.
- Azure Functions deployment slots or rollout features matching the hosting plan.
- Container platform deployment strategies such as rolling or blue/green.

Feature names and limits vary by service and plan. Choose a platform-supported mechanism and test real rollback behavior.

### 19.1. Canary Criteria

Monitor at minimum:

- Invocation success/error rates.
- Timeouts and throttling.
- p50/p95/p99 durations.
- Cold start / init durations.
- Memory/CPU and GC activity.
- Downstream latency.
- Queue age / backlog.
- Retries and DLQ counts.
- Business outcomes and duplicate side effects.

Compare the candidate against a baseline under the same traffic profile. If a canary receives only simple request types, it may miss bugs triggered by rare payloads or integrations.

### 19.2. Bounded Rollbacks

Rolling back code does not always revert database migrations or external side effects. Before rollout, verify:

- Is the database schema backward-compatible?
- Are event schemas backward/forward-compatible?
- Did persisted data formats change?
- Were IAM policies or secret versions modified?
- Do provider SDKs produce irreversible side effects?
- Is the previous artifact still available for redeployment?

Use expand-contract for database schemas: add compatible columns/fields, deploy code supporting both old and new schemas, shift traffic, and remove old structures only once no consumers rely on them.

## 20. Governing Dependency Exceptions

Sometimes an immediate upgrade is impossible because a dependency lacks a compatible patch or the provider does not yet support the target runtime. Exceptions must have expiration dates and owners.

An exception record should include:

- Affected component and version.
- CVE or reason preventing immediate upgrade.
- Affected functions, artifacts, and environments.
- Exposure and business impact.
- Active mitigations.
- Technical owner.
- Risk approver.
- Start date and expiration date.
- Closure criteria.
- Links to tickets and evidence.

Never allow permanent exceptions or vague notes like `"will upgrade later."` Every renewal must re-evaluate exploitability, exposure, and mitigations.

## 21. Allowed Runtime and Dependency Policies

Organizations can maintain an internal catalog listing:

- Allowed Java versions for production.
- Approved JDK vendors/distributions.
- Supported cloud managed runtimes.
- Framework baselines.
- Dependencies with permitted licenses.
- Scanned and supported base images.
- Build tool and plugin versions.
- Mandatory security configurations.
- Exception request workflow.

Policies should distinguish:

- **Allowed:** permitted in production.
- **Preferred:** recommended version for new projects.
- **Deprecated:** still operational, but discouraged for new deployments.
- **Blocked:** prohibited from production deployment.
- **Exception:** permitted only with formal approval and expiration.

Do not block versions only in CI. Inventory production to catch older resources deployed before the policy took effect.

## 22. Audit Evidence and Traceability

During audits or security incidents, operations teams must prove which artifact is running, which source built it, and which dependencies it contains.

Retain evidence:

- Source commit and pull request.
- Build pipeline identity and timestamp.
- Build tool / JDK version.
- Dependency lockfiles.
- SBOM.
- SCA scan reports and CVE dispositions.
- Artifact checksum / image digest.
- Signatures/provenance if applicable.
- Approval and exception records.
- Deployment revision/version.
- Runtime configuration and provider runtime identifier.
- Canary results and rollback history.

Never store secrets or sensitive production data inside audit evidence. Use metadata, checksums, and references to systems with proper access controls.

### 22.1. Tracing from a CVE to Running Functions

When a new advisory drops:

1. Extract the package name/PURL and affected version range.
2. Query the SBOM registry to find artifacts containing that package.
3. Map artifacts to running functions/revisions.
4. Identify environment, region, owner, and exposure.
5. Assess exploitability and impact.
6. Create remediation tasks per SLA.
7. Track deployment of patched versions.
8. Verify production runtimes no longer run affected artifacts.
9. Record evidence and close the finding.

Maintain links between artifacts, image digests, and deployment revisions. Knowing only the source repository risks missing functions still running older artifacts.

## 23. Example Upgrade Plan for a Java Function

Suppose `orders-worker` currently runs:

- A managed Java runtime approaching deprecation.
- An older Spring Boot baseline.
- A Cloud SDK pulling in a flagged transitive dependency.
- An SQS message handler writing to a database.

Plan:

**Phase 1 — Discover**

- Inventory function, runtime, framework, JDK vendor, and artifact version.
- Generate/inspect the production artifact's SBOM.
- Identify affected dependencies and provider-supported target runtimes.
- Assign owner and deadline.

**Phase 2 — Plan**

- Select compatible target Java and framework versions.
- Upgrade Maven/Gradle wrapper and compiler plugins.
- Remediate flagged dependencies via BOM or patch releases.
- Confirm schema/event compatibility.
- Prepare the test matrix and rollback plan.

**Phase 3 — Build and verify**

- Build on the target JDK.
- Run unit/integration/contract tests.
- Verify SQS event model, partial batch failures, and idempotency.
- Measure cold starts, memory, duration, and throughput.
- Generate a fresh SBOM and scan the artifact/image.

**Phase 4 — Deploy**

- Deploy to staging and run smoke/load tests.
- Deploy canary to a fraction of traffic.
- Monitor error rates, queue age, DLQs, and business state.
- Ramp traffic in defined steps.

**Phase 5 — Close**

- Verify all production revisions run supported runtimes/dependencies.
- Archive build, scan, approval, and deployment evidence.
- Update the inventory.
- Close exceptions and CVE tickets.
- Clean up old runtimes/artifacts per retention policy.

## 24. Periodic Governance Cadence

Reference schedule:

| Cadence | Activity |
|---|---|
| Every build | Dependency/SCA scan, unit tests, and SBOM |
| Every release | Compatibility, image scan, provenance, and deployment evidence |
| Daily | Ingest security advisories and detect new CVEs |
| Weekly | Review critical/high findings and upcoming runtime deadlines |
| Monthly | Reconcile runtime inventory, dependency support, and owners |
| Quarterly | Review Java LTS roadmap, framework baselines, and exceptions |
| Ahead of EOL | Migration, canary, rollback tests, and production fleet verification |

Adjust cadence to risk levels and compliance requirements. Critical vulnerabilities or runtime retirements may require immediate action rather than waiting for the next scheduled review.

## 25. Common Governance Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only the Java major version | Misses framework and transitive CVEs | Inventory the full dependency graph |
| Scanning only at build time | New CVEs go undetected in running artifacts | Rescan deployed SBOMs periodically |
| Ignoring provider runtime deadlines | Blocked deployments or rushed migrations | Maintain a lifecycle calendar and owners |
| Using floating container tags | Exact production image is unknown | Pin digests and store provenance |
| Upgrading multiple major dependencies at once | Hard to isolate regressions | Split upgrades into batches |
| Not testing on the target runtime | Bugs surface only after deploy | Run integration tests on matching provider/container |
| Suppressing CVEs without justification | Risk is hidden | Enforce exceptions with evidence and expiry |
| Rolling back code with incompatible schemas | Older code breaks against new schemas | Use expand-contract migrations |
| Not retaining SBOMs/artifact digests | Hard to identify affected fleet | Link evidence to deployment revisions |
| Governing production only | Old staging/utility functions retain vulnerabilities | Inventory every environment |

## 26. Process for Tracking Lifecycles and Planning Dependency Upgrades

1. **Inventory.** List functions, runtimes, JDK vendors, frameworks, dependencies, build tools, and image digests.
2. **Assign owners.** Every component and function needs an accountable team.
3. **Track support dates.** Monitor releases, deprecations, EOLs, and retirements from official sources.
4. **Generate SBOMs.** Bind SBOMs to artifact checksums and deployment revisions.
5. **Scan continuously.** Scan dependencies and images in CI, registries, and periodically post-deploy.
6. **Triage risk.** Combine severity, exploitability, exposure, data sensitivity, and business criticality.
7. **Plan upgrades.** Choose compatible target versions, batch changes, and set deadlines.
8. **Test.** Run build, integration, contract, security, load, and serverless behavior tests.
9. **Canary.** Deploy to partial traffic and compare against baseline.
10. **Roll back safely.** Verify code, schemas, events, and external side effects before rolling back.
11. **Verify the fleet.** Confirm all production functions run supported runtimes and artifacts.
12. **Retain evidence.** Store SBOMs, scans, approvals, artifact digests, and deployment records.
13. **Review exceptions.** Renew or close exceptions based on current risk.

## 27. Self-Check Questions

- How do provider runtimes, Java JDKs, and application dependencies differ in their lifecycles?
- How do managed runtimes and custom containers divide patching responsibilities?
- Why must the inventory record JDK vendors and artifact digests?
- How can a transitive dependency introduce a CVE into a function?
- How do SBOMs help query a production fleet when a new CVE appears?
- How does CVSS differ from exposure-aware risk assessment?
- Why is it necessary to rescan SBOMs after artifacts have been deployed?
- How does runtime deprecation differ from retirement?
- Which steps are needed before upgrading a Java major version?
- Why must you verify framework BOMs and dependency convergence?
- How should container base images be pinned and rebuilt?
- Which metrics and business outcomes should a canary monitor?
- Why can rolling back code fail after a database schema migration?
- What owner, mitigations, and expiration details does a dependency exception need?
- Which audit evidence traces a CVE back to a running function and revision?
