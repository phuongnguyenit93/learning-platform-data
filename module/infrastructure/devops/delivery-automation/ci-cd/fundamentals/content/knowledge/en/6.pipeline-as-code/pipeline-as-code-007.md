# Version Pinning for Reusable Components and Execution Tools

Pipeline as code enables CI/CD processes to be stored in a repository, reviewed like source code, and executed automatically. However, a Git-managed pipeline file can still produce different results across two runs if it references external components that can change: actions, reusable workflows, templates, shared libraries, container images, runner images, compilers, or dependencies.

**Version pinning** means explicitly declaring the version or immutable identifier of the components a pipeline uses. The goal is for any run to pinpoint the exact pipeline code, reusable components, and toolchain involved in producing the result. When a reference is updated, that update becomes a reviewable, controlled change.

In the CI/CD module, this principle supports consistency across builds, tests, artifacts, and releases, while reducing supply-chain risk when an external dependency or action is replaced. Version pinning does not eliminate the need for updates; it creates an explicit checkpoint where the team proactively evaluates and upgrades dependencies.

## 1. What needs to be version-pinned

Pipelines typically depend on multiple layers of components. An inventory should cover:

| Component | Examples | Identifier to consider |
|---|---|---|
| CI action or plugin | Git checkout action, cache action, scanner action | Full commit SHA or verified immutable release |
| Reusable workflow/template | Shared workflow, CI template, pipeline component | Commit SHA or immutable release version |
| Shared library | Jenkins Shared Library, internal script library | Immutable release tag or commit SHA |
| Container image | Image containing build tools, scanners, or deploy clients | Image digest, optionally paired with a human-readable tag |
| Runner/executor image | Job runner or build agent machine image | Digest or managed image version |
| Compiler and runtime | JDK, Node.js, Python, .NET SDK | Specific version, including patch version when needed |
| Build tool | Gradle, Maven, npm, pnpm, Docker BuildKit | Wrapper or explicit version plus checksum if supported |
| Application dependencies | Direct and transitive libraries | Lockfile, checksums, and update rules |
| Check rule sets | Linters, formatters, policy bundles, scanner databases | Versioned or recorded snapshot |

Not every component uses the same identifier type. For source code, a commit SHA identifies an exact revision. For container images, a digest identifies image contents. For runtimes, pin the runtime release version and account for how the runner delivers OS patches. For dependencies, lockfiles and checksums verify the exact packages downloaded.

## 2. Tags, versions, and immutable identifiers

Common reference types carry different levels of stability:

- `latest`, `main`, `stable`, or branch names are moving references. Contents can change without modifying the pipeline.
- Tags such as `v3` or `1.8.0` are readable and convenient for upgrades, but their immutability depends on the publisher's policy. Some systems allow moving tags.
- A full commit SHA identifies an exact repository revision. When pinning source code, use the full SHA required by the platform rather than an abbreviated SHA.
- A digest such as `sha256:...` identifies the contents of a container image or content-addressed object.
- Package or download checksums verify that retrieved content matches the value published or recorded in a trusted manifest.

For example, `tool-image:2.4` tells readers the intended version, yet if the tag is overwritten the same reference can return a different image. A reference like `tool-image@sha256:...` pins exact contents. You can include both the tag and the digest for readability alongside guaranteed identification.

Pinning to a commit SHA or digest identifies the input, but does not by itself prove the input is safe. Before pinning, verify the source repository, publisher, commit contents, signatures, or provenance when available. A malicious version pinned accurately is still a malicious version.

## 3. Pinning actions and reusable workflows in GitHub Actions

In GitHub Actions, an action can be referenced by tag or commit SHA. For pipelines requiring strict control, pin by full-length commit SHA and annotate the corresponding release tag so reviewers can read the version in use.

The example below uses placeholder values to illustrate structure; replace them with verified SHAs from the official repositories:

```yaml
name: verify

on:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA> # vX.Y.Z

      - name: Set up Java
        uses: actions/setup-java@<FULL_40_CHARACTER_COMMIT_SHA> # vX.Y.Z
        with:
          distribution: temurin
          java-version: '21.0.x'

      - name: Run tests
        run: ./gradlew test
```

This snippet illustrates action pinning only. Java version `21.0.x` still allows receiving patch updates within the 21 line; if builds require absolute immutability, select an exact patch version and control the image/runner providing the JDK. Pinning an action does not automatically pin the runtime that the action installs.

Reusable workflows are also dependencies. When calling a workflow from another repository, use an immutable ref per organizational policy, preferring a full commit SHA when exact content pinning is required:

```yaml
jobs:
  verify:
    uses: owner/ci-workflows/.github/workflows/java-verify.yml@<FULL_COMMIT_SHA>
    with:
      java-version: '21'
```

When a shared workflow changes, consuming repositories should not inherit that change unintentionally. The team publishes a new version or commit, reviews impact, and updates the ref in consuming repositories. If the workflow uses `workflow_call` inputs or secrets, verify the input contract, token permissions, and secret access when upgrading.

## 4. Pinning templates, components, and shared libraries on other platforms

Other CI/CD platforms have different syntax, yet the principle is identical: reference an identified revision and review ref changes upon upgrades.

**GitLab CI/CD** can include files from another project. Conceptual example:

```yaml
include:
  - project: platform/ci-templates
    ref: '<FULL_COMMIT_SHA>'
    file: '/templates/java-build.yml'

stages:
  - verify
  - package
```

`ref` can be a branch, tag, or commit depending on the include mechanism. A branch like `main` is a moving reference; tags may be protected by policy, though system mutability rules still matter. For critical templates, pinning a commit SHA ensures the pipeline consumes verified contents. GitLab CI/CD components should also use released versions governed by catalog immutability rules.

**Jenkins Shared Libraries** can be loaded with a specific version. Illustrative example:

```groovy
@Library('company-ci-library@v2.3.1') _

pipeline {
    agent any
    stages {
        stage('Verify') {
            steps {
                runStandardVerification()
            }
        }
    }
}
```

Here `v2.3.1` is only as immutable as repository policies preventing tag moves or overwrites. For environments requiring strict traceability, SCM configuration can reference a commit SHA. Check how Jenkins configures default versions, version overrides, and library caching to avoid unintentionally loading the default branch.

The examples above are conceptual patterns; exact syntax and pinning capabilities depend on the platform version, plugins, and administrative configuration in use.

## 5. Pinning container images and runners/executors

CI jobs often run inside a container image containing a shell, SDK, scanner, or deployment tools. If the image is referenced by a mutable tag, a later run may receive a different toolset even though the pipeline file has not changed.

Example:

```yaml
jobs:
  build:
    container:
      image: registry.example.com/ci/java-toolchain:21@sha256:<IMAGE_DIGEST>
    steps:
      - run: ./gradlew clean test
```

The `21` tag helps readers recognize intent; the digest pins the exact image contents. Digests should come from a trusted registry and be updated deliberately. When an image needs security patches, publish a new digest, evaluate the changes, and update the pipeline via review.

Runners are also part of the execution environment. Hosted runners may have their image, kernel, pre-installed tools, and packages updated by the vendor without workflow changes. Labels like `ubuntu-latest` can shift to a new Ubuntu release on the provider's schedule. When higher stability is required, consider self-hosted runners with pinned images, container jobs pinned by digest, or controlled runner groups. Even on hosted runners, log the actual image/runner version to aid investigations.

Not every host machine attribute can be pinned via `runs-on` alone. If the platform offers runner image versions or immutable image references, use them; otherwise, treat hosted images as mutable inputs and test periodically against vendor updates.

## 6. Pinning compilers, runtimes, build tools, and dependencies

Pinning actions while letting compilers or dependencies float can still alter builds. A stable workflow must manage the toolchain as well:

- Use the Gradle Wrapper or Maven Wrapper so the repository dictates the build tool version. For the Gradle Wrapper, check the distribution URL and distribution checksum configuration where supported.
- Declare the Java toolchain and exact JDK version matching compatibility policies; record vendor and patch version when needed.
- Use lockfiles for dependencies and plugins where the ecosystem supports them; avoid version ranges or floating dependencies in release pipelines.
- Pin base images, compiler images, and packaging tools; verify checksums or signatures of downloaded files.
- Record build environment variables affecting outputs, locale, timezone, and architecture parameters when significant.

Example Gradle configuration illustrating a Java toolchain:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This snippet pins the toolchain major version required by the build; it does not necessarily pin the patch release or vendor. For tighter control, the runner/container image must provide the specific JDK and the pipeline should log the actual version via `java -version`.

Dependency lockfiles also need review. A lockfile pins resolved versions for an installation, yet does not replace checksum verification, source checks, and security policies. For package managers supporting integrity hashes, preserve and verify those hashes. Never disable TLS or checksum verification to work around dependency download errors.

## 7. Combining pinning with supply-chain security

Version pinning identifies components, while supply-chain controls evaluate whether those components are trustworthy. Combine pinning with these practices:

1. Pull actions, templates, libraries, and images only from organization-approved sources.
2. Verify commits, signed tags, image signatures, or provenance when provided by publishers.
3. Restrict CI token permissions and expose secrets only to jobs that genuinely require them.
4. Use read-only access for dependencies and registries in consuming jobs; separate publish privileges from routine build privileges where appropriate.
5. Scan dependencies and images per policy; bind scan results to the inspected digest or revision.
6. Record sources, versions, and content identifiers in logs or build provenance.
7. Monitor security advisories and compromise reports affecting pinned dependencies.

A fixed SHA stops a ref from drifting to another commit, yet does not prevent a pinned commit from containing malicious code or vulnerabilities. If an action is discovered to be compromised, the team must proactively move the ref to a safe release, audit historical usage, and assess artifacts built during the exposure window.

## 8. Controlled version updates

Pinning everything and never updating makes pipelines stable in the short term while accumulating vulnerabilities and technical debt. Therefore, pinning must be paired with an upgrade workflow:

1. **Inventory:** maintain a list of actions, workflows, templates, shared libraries, images, runners, and toolchains in use.
2. **Monitor:** track release announcements, security advisories, and support lifecycles for each component.
3. **Propose updates:** bots or owners open pull requests updating refs, digests, or versions.
4. **Review changes:** inspect release notes, diffs, breaking changes, new permission requests, and behavioral changes.
5. **Run verification pipelines:** test on the updated revision, run security checks, and compare artifacts or outputs as needed.
6. **Promote gradually:** roll out updates to sandbox repositories or a small group of pilot projects before broad adoption.
7. **Preserve rollback capability:** retain the prior ref and document how to revert to the stable version if issues appear.

For critical vulnerabilities, upgrade timelines should follow security SLAs rather than waiting for routine cycles. Even emergency patches still require verifying sources, testing compatibility, and recording who approved the change.

## 9. Reproducibility and the limits of version pinning

Version pinning reduces input variance but does not guarantee two runs produce byte-for-byte identical outputs. Outputs can also depend on timestamps, file ordering, random seeds, network state, external data, operating system, kernel, locale, caches, or remote services.

Distinguish three goals:

- **Version pinning:** fixing the version or identifier of dependent components.
- **Reproducible builds:** given controlled inputs, producing identical outputs as defined by the project.
- **Traceability:** identifying the exact inputs, tools, runs, and artifacts that produced a result.

These three goals reinforce one another. A pipeline with strong pinning and traceability may still not be reproducible if builds depend on timestamps or external services. When reproducible builds are required, add controls for non-deterministic inputs, isolated environments, timestamps, archive ordering, and output checksum verification.

Hosted runners, SaaS services, registries, and advisory databases can change in ways that cannot be pinned entirely from a pipeline file. Clarify which parts are fixed, which are vendor-managed, and how actual runtime versions are recorded. Never claim a pipeline is completely immutable if critical inputs are still updated automatically by external services.

## 10. Pipeline review checklist

Before merging a pipeline change or releasing a shared template, verify:

- [ ] Moving branches or tags are not used for critical components where immutable identifiers are needed.
- [ ] Actions and reusable workflows are pinned to verified refs, with version comments for reviewer readability.
- [ ] Templates, components, and shared libraries have explicit release versions and overwrite-protection policies.
- [ ] Container images are referenced by digest when content control is required.
- [ ] Runner images and runtimes/toolchains are controlled or their actual versions are recorded.
- [ ] Build tool wrappers, lockfiles, and checksums are reviewed alongside source code.
- [ ] Dependency sources, signatures/provenance, and access permissions are verified per policy.
- [ ] The update process includes release notes, testing, approvals, and a rollback plan.
- [ ] No secrets or broad-scoped tokens are exposed to shared workflows.
- [ ] Mechanisms exist to inventory and detect end-of-life components or security advisories.

Version pinning turns pipeline dependencies into visible, reviewable inputs. Combining immutable identifiers, source verification, toolchain management, and disciplined update cadences lets teams understand why a pipeline produced a result, reproduce incidents more easily, and upgrade components without losing traceability.
