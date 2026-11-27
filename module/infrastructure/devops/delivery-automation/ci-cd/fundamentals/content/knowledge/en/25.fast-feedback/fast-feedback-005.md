# Selecting OS and Version Matrices Based on Support Needs

A project may run across multiple operating systems, runtime versions, and hardware architectures. Testing every combination on every push often slows down pipelines, consumes runners, and produces sprawling results that are hard to triage. Conversely, testing only on a single latest Linux machine can miss bugs that surface exclusively on Windows, macOS, an older Linux distribution, or a runtime version customers still rely on.

A sound CI matrix starts from the product's support policy. The team needs to know which operating systems and versions it has committed to supporting, which combinations carry high risk, which checks must run before merge, and which checks can run on a schedule or before release. That turns the matrix into an enforcement mechanism for the support policy and a way to allocate testing budget, rather than a huge Cartesian product created simply because it is possible.

This lesson explains how to build a well-grounded OS and version matrix, distinguish runner environments from product target environments, shorten feedback times while protecting support commitments, and maintain the matrix as CI platforms or OS lifecycles evolve.

## 1. What Does a CI Matrix Represent?

A CI matrix is the set of test configurations a pipeline runs for the same revision. Each configuration is a combination of values across dimensions such as:

- Operating system or runner image.
- Runtime version, such as JDK, Node.js, Python, or .NET.
- CPU architecture, such as x64 or ARM64.
- Compiler or build tool version.
- Dependency or database version requiring compatibility testing.
- Build configuration type, such as debug/release or feature profiles.

For example, a Java library may need testing on Linux, Windows, and macOS while supporting JDK 17 and 21. A simple matrix has three OSes multiplied by two JDK versions, yielding six configurations.

| Operating System | JDK | Question Verified |
|---|---:|---|
| Linux | 17 | Does the minimum runtime version build and pass tests? |
| Linux | 21 | Is the newer runtime version compatible? |
| Windows | 17 | Are file path, process, and shell behaviors correct? |
| Windows | 21 | Does the newer Windows/runtime combination have unique bugs? |
| macOS | 17 | Are there OS- or toolchain-specific failures? |
| macOS | 21 | Does the newer runtime version work on macOS? |

A matrix can run many jobs in parallel, but increasing job count increases runner queue time, quota consumption, and the number of results to inspect. Therefore, do not pick combinations merely based on how many versions can be listed.

## 2. Start from the Product's Support Policy

The first source of truth is the support policy, not the list of runners available on the CI platform.

The policy should answer:

- Which operating systems does the product support?
- What are the minimum and latest supported versions?
- Are multiple Linux distributions supported, or only one distribution family?
- Are both x64 and ARM64 supported?
- Which runtime is the minimum, recommended, and experimental tier?
- Which versions are only supported during a transition period?
- Which versions are end-of-life and no longer covered by commitments?
- Are any combinations excluded because dependencies or vendors do not support them?

Classify them clearly:

| Support Status | Meaning | Testing Expectation |
|---|---|---|
| Supported | Official support commitment | Must have appropriate automated tests |
| Best effort | May work, but no full commitment | Representative or scheduled checks |
| Preview/experimental | Under evaluation, subject to change | Separate pipeline; do not block every PR unless required |
| Deprecated | Announced end-of-support | Continue testing during the transition period |
| Unsupported | No longer committed | Exclude from release gates |

If product documentation claims support for Windows and Linux while the pipeline only tests Ubuntu, the matrix fails to reflect the commitment. Conversely, if the product only supports Linux, running full test suites on macOS and Windows on every PR may add zero value.

The support policy should have an owner, review cadence, and criteria for retiring versions. Update the CI matrix whenever the policy changes.

## 3. Distinguishing Runner OS from Target OS

The runner OS is the operating system where the CI job executes. The target OS is the operating system or environment where the product is designed to run. They can be the same, but do not have to be.

Examples:

- CI runs on Ubuntu to cross-compile a Windows binary.
- A job runs on macOS to sign a package for Apple platforms.
- A container build runs on Linux yet produces an image running a different Linux distro.
- CI runs on Windows to build a .NET application targeting Windows.
- A pipeline runs on an ARM64 runner to test an ARM64 binary.

Building on Ubuntu does not prove the application works on Windows. If Windows behavior must be verified, tests must run on a Windows runner or an equivalent supported Windows environment.

Conversely, if you are only testing pure OS-independent Java logic, some tests can run on a representative runner; checks touching filesystems, shells, processes, paths, line endings, native libraries, and packaging are what need to span each OS.

Clearly state each job's objective: testing buildability on the runner, testing runtime behavior on the target, or verifying a package built for a specific target.

## 4. Choosing OS Granularity

"Linux support" can span many distinct environments: Ubuntu, Debian, Fedora, RHEL-compatible, Alpine, or minimal images. They differ in libc, package managers, library paths, shells, and package versions.

Define the commitment level:

- Supporting a specific distro and version.
- Supporting a distro family, such as Debian-based.
- Supporting any distro meeting runtime requirements.
- Supporting only container images published by the project.
- Supporting a customer-selected list of target images.

If the product only runs inside a container image supplied by the team, the matrix can focus on that image and published architectures. If you distribute native packages for multiple distros, test each ABI platform or compatibility group that carries distinct risk.

Alpine uses `musl` libc while most mainstream Linux distributions use `glibc`. A native binary built on Ubuntu may fail on Alpine unless built or packaged appropriately. Simply writing "Linux" in the matrix hides this crucial distinction.

## 5. Selecting Versions by Lifecycle and Commitment

You do not need to test every version that has ever existed. Select versions based on support lifecycle and compatibility.

A common policy:

- **Minimum supported:** the oldest version the product still commits to.
- **Current stable/LTS:** the primary recommended version.
- **Latest supported:** the newest version within the supported scope.
- **Next version:** an upcoming release tested early to catch breaking changes.
- **Deprecated version:** tested only during a transition period while commitments remain.

For example, a Java library might support JDK 17 and 21. JDK 17 represents the minimum tier, and JDK 21 represents the newer LTS. A newer feature release, such as JDK 26 under evaluation by the project, can run in a scheduled preview job rather than blocking every PR.

Never use `"latest"` without a concrete definition. `"Latest"` drifts over time and hurts pipeline reproducibility. Use explicit versions or a clearly governed preview channel.

## 6. Selecting Combinations by Risk Instead of Multiplying Every Dimension

Suppose a project has 3 operating systems, 3 JDK versions, 2 CPU architectures, and 2 database versions. A full Cartesian matrix has \(3 \times 3 \times 2 \times 2 = 36\) jobs. Even if each job takes 8 minutes and runs up to 6 runners in parallel, time and cost are substantial; if runner quota is tight, queues can stretch out.

Not every combination makes sense. Perhaps the database is only tested on Linux; macOS only needs one JDK; ARM64 only targets Linux; and Windows only supports JDK 17 and 21. In that case, the matrix should describe valid combinations rather than generating every permutation only for jobs to fail on unsupported setups.

A selection approach:

1. List the combinations the product actually supports.
2. Identify the minimal combinations required to gate merges.
3. Flag combinations with a history of bugs or platform differences.
4. Choose representative combinations for nightly runs.
5. Choose the full supported set for releases or pre-releases.
6. Remove combinations with no testing value and document why.

A good matrix has a rationale for every row—not the largest number of jobs.

## 7. Tiering Checks: Pull Request, Nightly, and Release

One way to balance fast feedback with coverage is to use tiered matrices.

| Tier | Goal | Suggested Matrix | When It Runs |
|---|---|---|---|
| Pull request | Catch common errors fast | Representative OS + minimum and current runtime | Every PR |
| Merge/main | Broader checks after integration | Supported OSes and primary versions | Every merge |
| Nightly | Cover rare combinations, previews, and secondary architectures | Broad or pairwise matrix | Scheduled |
| Release candidate | Validate all release commitments | Full supported matrix | Before release |
| Scheduled compatibility | Catch drift from runners, dependencies, and upstream | Next versions or updated images | Scheduled |

Do not make every PR wait for 36 combinations if only a handful provide fast-feedback value. Still, every committed combination must have a verification path before release.

If a combination only runs nightly and keeps failing, the team must decide whether to fix it, narrow support, or promote it to a more frequent tier. Never leave a job red for so long that everyone ignores the alerts.

## 8. Choosing Representative Combinations for Pull Requests

The PR matrix should stay small while maximizing the probability of catching bugs.

For example:

- Linux + minimum JDK to catch accidental use of APIs newer than the minimum target.
- Linux + latest supported JDK to test the current runtime.
- Windows + current JDK to catch path, process, and shell bugs.
- macOS + current JDK if macOS is covered by support commitments.
- One secondary architecture if the project ships native binaries or platform-specific dependencies.

You might pick 3–5 configurations instead of all 12 or 24 combinations. The exact number depends on test duration, bug history, and platform divergence.

The PR matrix should not consist solely of the newest version. If the product still supports older runtimes, bugs from accidentally calling newer APIs may only show up on the minimum version. Testing the minimum supported version is an essential safeguard.

## 9. When Is a Full Matrix Needed?

A full matrix is valuable for validating release commitments, testing cross-dimension interactions, or investigating bugs that only reproduce on a specific combination.

Run a full matrix:

- Before cutting an official release.
- When changing build tools, compilers, or runtimes.
- When modifying code tied to OS-specific behavior.
- When updating dependencies that ship native libraries.
- When changing packaging, installers, or signing.
- When adding or removing OSes or versions in the support policy.
- When a bug has been reported on an uncommon combination.
- On a schedule if the product needs to detect drift from runner images or upstream updates.

A full matrix does not necessarily mean re-running every heavy integration test on every combination. You can separate compile/package/smoke checks from deep tests, as long as the release policy specifies what evidence is required for each target.

## 10. Using Pairwise Testing When Dimensions Grow

When a matrix has many dimensions, pairwise testing can shrink combinations by ensuring every pair of values across dimensions appears at least once.

For instance, instead of running every OS × JDK × database × architecture combination, the team selects a smaller set covering all interacting pairs.

Pairwise testing helps when:

- There are many configuration dimensions.
- Most bugs are expected from two-way interactions.
- Running the full matrix is too expensive.
- A full matrix still runs in another tier such as release or nightly.

Pairwise does not replace mandatory combinations. If the product commits to Windows + JDK 17 + x64, that combination must be tested directly even if the pairwise generator skips it. Combinations with bug histories or native dependencies should also be pinned into the matrix.

For three-way or higher interaction bugs, pairwise can miss defects. Use risk-based selection or t-wise testing for high-risk areas.

## 11. Separating Build, Test, and Packaging Matrices

Not every step needs to run on every combination.

A pipeline can split into:

- **Build/compile matrix:** verifies code compiles on supported runtimes and toolchains.
- **Unit test matrix:** runs independent logic across representative OSes/runtimes.
- **Integration matrix:** runs on combinations where dependencies or behaviors diverge.
- **Packaging matrix:** builds packages for each target OS/architecture.
- **Release verification:** tests the actual packages on their corresponding targets.

For example, Java bytecode can be built once using a specified JDK and then tested across multiple OSes and JREs. However, if the build script invokes native tools or OS-specific shell scripts, the build itself must also run on the corresponding runners.

Splitting jobs avoids redundant rebuilds and clarifies whether a failure happened in compilation, testing, or packaging. Still, if an artifact built on Linux is transferred to Windows, verify that the artifact is genuinely portable and free of Linux-specific paths or file metadata.

## 12. GitHub Actions Example with an Explicit Matrix

The example below selects representative combinations instead of multiplying every OS by every JDK:

```yaml
name: Supported platform checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        include:
          - os: ubuntu-24.04
            java: '17'
            tier: pr
          - os: ubuntu-24.04
            java: '21'
            tier: pr
          - os: windows-2025
            java: '21'
            tier: pr
          - os: macos-15
            java: '21'
            tier: pr

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}

      - name: Run tests on Unix-like runner
        if: runner.os != 'Windows'
        run: ./gradlew test

      - name: Run tests on Windows
        if: runner.os == 'Windows'
        run: .\gradlew.bat test
```

In this example, `runs-on` and `java-version` reference each matrix row's values directly. Pin actions according to organizational policy; version tags are used here for readability, while production environments may require full commit SHA pinning.

Key points to note:

- `include` explicitly declares the exact chosen combinations.
- `max-parallel` caps concurrent jobs to manage quota.
- `fail-fast: false` lets remaining combinations finish and provide fuller diagnostics when one platform fails.
- `runner.os` selects the appropriate command for Windows vs. Unix-like runners.
- The JDK version is passed per matrix row.
- Tests execute on each selected runner OS.

For repositories needing very fast workflow feedback, use a smaller PR matrix and a dedicated nightly workflow for remaining combinations.

## 13. Using exclude and include Intentionally

In GitHub Actions, a matrix can be generated from lists and then adjusted via `exclude` and `include`.

Example:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04, windows-2025, macos-15]
    java: ['17', '21']
    exclude:
      - os: macos-15
        java: '17'
    include:
      - os: ubuntu-24.04
        java: '26'
        tier: preview
```

`exclude` removes unsupported or meaningless combinations. `include` adds a specific configuration, such as a preview JDK running only on Linux.

Never use `exclude` to hide failing tests or avoid a broken combination without an explicit support decision. Every exclusion should have a rationale, owner, and review date. If a combination is unsupported, product policy and documentation must reflect that.

When using `include` to attach extra attributes, understand how the platform merges properties into existing combinations. If you want exact control over every configuration, listing objects under `include` is often clearer and less error-prone.

## 14. Choosing Appropriate fail-fast Behavior

`fail-fast` controls what happens when one configuration in a matrix fails.

**Enabling `fail-fast`** cancels remaining matrix jobs on error. This saves runner capacity and works well when every configuration runs the same fast check where a single failure already blocks the PR.

**Disabling `fail-fast`** lets remaining configurations finish, which is useful when you need to know whether a bug affects only Windows, macOS, or a specific runtime.

A common strategy:

| Tier | fail-fast | Reason |
|---|---|---|
| PR smoke matrix | Can enable | Early feedback and lower cost |
| Small PR platform matrix | Usually disable if diagnostics are needed | Gather results across OSes |
| Nightly full matrix | Disable | Full combination report needed |
| Release matrix | Disable or per policy | Evidence required for every target |
| Exploratory preview | Disable | Observe multiple versions without stopping early |

Do not confuse matrix `fail-fast` with a test case halting a test suite inside a single runner. Those two mechanisms operate at different scopes.

## 15. Controlling Job Count and Feedback Time

Pipeline time is not just single-job runtime. It also includes queuing, runner limits, setup time, and result aggregation.

Ways to reduce time:

- Run independent combinations in parallel within quota limits.
- Keep the PR matrix small and run broad matrices nightly/at release.
- Cache dependencies by OS, architecture, and toolchain.
- Avoid reinstalling dependencies in unnecessary steps.
- Separate fast smoke tests from heavy integration tests.
- Match runner sizing to workload and startup time.
- Run high-signal checks early.
- Fail early at the PR tier on guaranteed merge-blockers if full-matrix diagnostics are not needed.

Do not raise `max-parallel` beyond runner capacity or organizational quota. If a job runs for 5 minutes but waits 20 minutes in a queue, launching more parallel jobs can slow down every other pipeline too.

Monitor both queue time and execution time. Those two metrics require different remedies.

## 16. Caches Must Be Segregated by Compatible Environment

Dependency or build output caches must never be blindly shared across different OSes, architectures, or toolchain versions.

Cache keys should reflect every factor that can make cached contents incompatible:

- Runner OS or distro.
- Architecture.
- JDK/runtime version.
- Build tool version.
- Lockfile or dependency manifest hash.
- Compiler flags and build profile if they affect outputs.

Example logical cache key:

```text
gradle-OS-ARCH-JDK-VERSION-LOCKHASH
```

Sharing a cache between Windows and Linux can break due to paths, permissions, or file formats. For native compilation, architecture and ABI are especially critical.

Caches are performance optimizations, not the source of truth for artifacts. If a cache is wiped, the build must remain reproducible from source and locked dependencies. Release artifacts must live in a dedicated repository.

## 17. Runner Images and Reproducibility

Runner labels like `ubuntu-24.04` or `windows-2025` usually point to platform-managed images. Image contents can update over time: pre-installed compilers, SDKs, system packages, or tools may change.

This can cause the exact same commit to produce different results at two different times.

To stay in control:

- Use specific runner labels instead of `latest` aliases when the platform offers them.
- Pin toolchain versions inside workflows.
- Record runner image/version metadata when the platform exposes it.
- Use container images pinned by digest for jobs that can run in containers.
- Schedule and monitor runner image updates.
- Run scheduled compatibility tests to detect upstream drift.
- Store build metadata to investigate discrepancies.

Not every runner image can be fully pinned. With hosted runners, providers still roll out image updates under their maintenance policies. Document this limitation and rely on toolchain pinning to minimize variance.

## 18. Testing OS-Specific Differences

Bugs that appear on only one OS typically stem from environmental differences rather than business logic.

| Difference | Risk | Recommended Check |
|---|---|---|
| File path separators | Wrong slash/backslash usage | Test paths via standard language APIs |
| Case sensitivity | Filenames differing only by case | Test on case-sensitive filesystems |
| Line endings | Scripts or fixtures altered by CRLF/LF | Verify checkout and script execution |
| File permissions | Scripts missing executable bits | Test packaging and permissions |
| Processes/signals | Different process shutdown behavior | Test start/stop and cleanup |
| Shells | Bash, PowerShell, and cmd have different syntax | Declare shells explicitly |
| Native libraries | Different ABIs or libc | Test on target image/architecture |
| Symlinks | Varying permissions and behavior | Test install/unpack steps |
| Encoding/locale | Different default locales | Test Unicode and formatting |
| Certificate stores | Different trust stores | Test TLS on the target OS |

Never concatenate file paths manually when standard library path APIs exist. Never assume every runner provides Bash or the same shell version. Workflows should specify shells explicitly and verify tool prerequisites.

## 19. Linux Matrix: Distros, libc, and Container Base Images

For products running on Linux, decide whether support is defined by specific distros or by ABI/runtime.

Things to check:

- `glibc` vs. `musl`.
- Minimum `libc` version.
- OpenSSL and native libraries.
- Package manager and package names.
- Default container user/group.
- Certificate authority bundle.
- Shell and core utilities.
- CPU architecture.
- Kernel features if the application relies on them.

If the production image is Alpine, testing only on Ubuntu is insufficient. If the application runs in a distroless image, test the actual image or an equivalent environment to verify startup, health checks, and certificates.

You do not have to include every distro on every PR. You can pick a representative distro for PRs, the release image at release time, and additional distros nightly. Still, every published target image must have a direct verification step.

## 20. Windows and macOS Require Dedicated Checks

Windows and macOS have build and test requirements distinct from Linux.

**Windows:**

- Drive letters and path length limits.
- File locking rules and deleting open files.
- PowerShell, cmd, and Git Bash differences.
- File permissions and executable behavior.
- Native DLLs, signing, and installers.
- Process termination and service management.
- Line endings and case-insensitive filesystems.

**macOS:**

- SDK and Xcode versions for native builds.
- Intel and Apple Silicon architectures if both remain supported.
- Code signing, notarization, and entitlements.
- Keychain/certificate handling.
- Filesystem and permission behavior.
- Differences between runner image and target macOS version.

If a product is not released for a given OS, there is no need to emulate all checks for that platform. If it is released for that OS, test the actual package on the target and verify signing/installer steps.

## 21. Testing CPU Architectures When Native Dependencies Exist

A matrix may need an architecture dimension whenever binaries or dependencies include native code.

Examples:

- Linux x64 and ARM64.
- macOS Apple Silicon.
- Windows x64 or ARM64.
- Multi-architecture container images.

Not every Java dependency is pure Java. JNI bindings, compression libraries, native database drivers, and build tools can all be architecture-dependent.

Distinguish:

- Runner architecture: where the job executes.
- Build target architecture: the architecture of the produced binary.
- Runtime architecture: the architecture where the binary executes.

Cross-compilation can produce binaries for a target different from the runner, but it does not fully replace runtime testing on the target architecture. When real hardware runners are unavailable, emulators or containers can help, provided limitations are documented and high-risk releases are still verified on target hardware/runners.

## 22. Choosing Runtime and Toolchain Versions Independently

A common mistake is using a single version dimension for all tools. Application runtime, compiler, build tool, and test runtime can have separate lifecycles.

Java example:

- Compiler toolchain may be JDK 21.
- Bytecode target may be Java 17.
- Unit tests may run on JDK 17 and 21.
- Gradle Wrapper has its own version.
- Gradle plugins have their own JDK constraints.

If a product supports Java 17, building only on JDK 21 without setting a target release can accidentally emit incompatible bytecode or reference APIs missing in Java 17.

Clarify each component:

| Component | Question |
|---|---|
| Compiler JDK | Which JDK compiles the code? |
| Target bytecode/API | Which Java level must the product remain compatible with? |
| Test runtime | Which JDKs must tests run on? |
| Build tool | Which Gradle/Maven versions are supported? |
| Plugins | Are plugins compatible with the JDK and build tool? |
| Runtime image | Which JRE/JDK or base image does production run on? |

For other languages, the same principle applies across compilers, SDKs, package managers, runtimes, and target frameworks.

## 23. Testing New Versions Before Adding Them to the Support Matrix

New OS or runtime versions can alter APIs, compiler warnings, TLS defaults, certificate stores, package managers, or system behavior.

Do not add a new version to official support commitments merely because a runner became available. First:

1. Create a preview or scheduled compatibility job.
2. Build and run unit tests.
3. Run integration tests with critical dependencies.
4. Verify packaging and installers.
5. Verify native libraries and security providers.
6. Run smoke tests on the target.
7. Monitor failures and performance.
8. Decide on preview, supported, or unsupported status.

Similarly, when an older version approaches end-of-support, check which dependencies and users still rely on it. Announce deprecation before removing it from the matrix and product.

## 24. Handling Unsupported Combinations and Infrastructure Failures

A combination can fail to run either because the configuration is unsupported or due to a temporary runner/infrastructure outage. Distinguish these two cases.

| Outcome | Example | Action |
|---|---|---|
| Product incompatibility | New runtime breaks a dependency | Fix code or update support policy |
| Unsupported combination | OS/version outside commitments | Exclude with rationale; do not treat as a product failure |
| Runner outage | Hosted runner fails to allocate | Retry or wait on infrastructure |
| Download failure | SDK mirror or package registry outage | Bounded retry, check upstream source |
| Test failure | Assertion fails on one OS | Investigate product/platform behavior |
| Flaky test | Passes and fails intermittently on same config | Record, stabilize test, never hide long-term |

Do not set `continue-on-error` for an entire platform just because tests are red. If a temporary bypass is needed to unblock pipelines, attach an owner, issue, expiration date, and clear reporting. A supported combination that is permanently ignored defeats the purpose of the matrix.

## 25. Caches, Artifacts, and Results Across Combinations

Each matrix job should name its outputs uniquely so it never overwrites another job's artifacts.

Artifact names can include OS, runtime version, architecture, build profile, and run ID or commit SHA.

Examples:

```text
test-report-linux-jdk17-x64
test-report-windows-jdk21-x64
test-report-macos-jdk21-arm64
```

When aggregating results, the pipeline should know which job produced each report and which combination it corresponds to. Never reuse the same artifact name across all matrix jobs if the platform overwrites or merges contents.

For release artifacts, publish only the exact outputs selected by release policy. Never accidentally publish experimental binaries from a preview matrix. Metadata should record the corresponding toolchain and target.

## 26. Planning Matrix Updates and Retirements

OSes and runtimes have finite lifecycles. Runner labels get deprecated, images are retired, and JDKs or SDKs reach end-of-life.

Maintain a review schedule:

- Check runner deprecation schedules.
- Track OS and runtime lifecycles.
- Review build tool and plugin versions.
- Assess users still running older versions.
- Update support policies and product documentation.
- Introduce new versions in preview before promoting them.
- Remove old versions after the deprecation notice window.
- Clean up obsolete cache keys, secrets, and runner configs.

Every matrix change should have a reason and an owner. Never leave an obsolete version lingering in workflows for years simply because nobody remembers why it was added.

## 27. Measuring Matrix Effectiveness

Metrics that show whether a matrix is well-balanced:

- Queue time and execution time per combination.
- Failure rate by OS/runtime/architecture.
- Number of bugs caught on only a single platform.
- Flaky test rate.
- Share of supported combinations tested in PR, nightly, and release pipelines.
- Runner cost by pipeline tier.
- Time from upstream release of a new version to project verification.
- Number of skipped combinations and age of exceptions.
- Share of releases with complete verification evidence for supported targets.

If a combination consistently takes significant time without catching defects, revisit its test scope or execution strategy. Do not automatically drop a committed combination; re-evaluate risk and product policy first.

## 28. Support Matrix Design Checklist

- [ ] Supported OSes, distros, runtimes, and architectures are documented.
- [ ] Every version has a status: supported, preview, deprecated, or unsupported.
- [ ] Minimum and latest supported versions are explicitly defined.
- [ ] Runner OS and target OS are clearly distinguished.
- [ ] Unsupported combinations are excluded with documented rationale.
- [ ] PR matrix covers representative OS/runtime pairs plus the minimum version.
- [ ] Nightly or release pipelines cover additional required combinations.
- [ ] Full matrix runs before release when required by policy.
- [ ] Pairwise testing does not replace mandatory combinations.
- [ ] Platform-specific behavior is tested on appropriate runners.
- [ ] Native dependencies are tested by architecture and ABI.
- [ ] Compiler target, runtime, and build tool versions are specified separately.
- [ ] Cache keys are partitioned by OS, architecture, and toolchain.
- [ ] Artifacts/reports are named with each matrix combination.
- [ ] `fail-fast` and `max-parallel` suit each pipeline tier.
- [ ] Runner images and toolchains are pinned or recorded.
- [ ] A schedule exists for deprecation reviews and version updates.
- [ ] `continue-on-error` exceptions have an owner and expiration date.
- [ ] Release evidence proves all supported targets were verified.

## Conclusion

An OS and version matrix should reflect the product's actual support policy. Start from committed target OSes, runtimes, architectures, and versions; then pick mandatory combinations for pull requests, broaden coverage nightly, and validate completely before release. A runner OS is merely the job's execution environment and does not by itself prove the product works on a target.

When build, test, and packaging are separated cleanly—using full matrices for required gates, pairwise coverage for high-dimensional spaces, and properly partitioned caches and artifacts—teams shorten feedback loops while retaining evidence for every supported platform. Review the matrix alongside OS/runtime lifecycles, and give every row a clear rationale, owner, and verification goal.
