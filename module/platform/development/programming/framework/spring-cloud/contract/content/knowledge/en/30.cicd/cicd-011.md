# Preventing untrusted changes in DSLs executed as arbitrary code

## Learning objectives

**Spring Cloud Contract** supports contract testing between **producer** and **consumer**: HTTP or messaging interactions are described with **Groovy/YAML DSL**, the plugin generates producer tests, packages stubs for consumers using **Stub Runner**, and feeds verification into **CI/CD** to catch incompatible API changes.

However, **Groovy DSL is executable Groovy code**, not merely a data file. If a pull request (PR), an external contract repository, or an untrusted artifact is allowed to supply a Groovy contract to the plugin, test generation becomes an **arbitrary code-execution entrypoint for the contributor**. The danger is acute when CI simultaneously holds tokens, artifact repository write access, deploy rights, or internal network access.

This lesson belongs to the **CI/CD** chapter, focusing on **preventing untrusted changes in DSLs executed as arbitrary code**. After this lesson, you will:

- Explain why **reading/compiling/executing Groovy DSL** differs from parsing declarative YAML.
- Define trust boundaries across fork PRs, internal branches, common contract repositories, contract JARs, verification pipelines, and release pipelines.
- Understand what a PR author might target: secrets, credentials, internal networks, workspaces, artifacts, or build outcomes.
- Place static checks and reviews **before** executing unapproved DSL.
- Design jobs running untrusted code with **isolated runners, zero secrets, least privilege, and restricted egress**.
- Avoid CI misconfigurations such as running PR code under `pull_request_target`, privileged self-hosted runners, or interpolating PR titles directly into shells.
- Protect Git/JAR contract sources using versions/digests, repository permissions, review rules, and provenance.
- Keep **producer contract verification**, **stub publication**, and **consumer Stub Runner tests** in separate privilege tiers.
- Establish an incident response plan when suspicious DSL or unverified artifact provenance is detected.

> **Security principle:** never treat a `*.groovy` file as safe data merely because it lives under `contracts` or "looks like DSL". A pipeline may execute it only once proper trust boundaries and isolation are established.

## 1. The problem: contracts express business requirements yet can be code

Suppose **Inventory Service** is a producer offering:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Response agreed with **Checkout Service**:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Normal Groovy contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 has 8 items in stock'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

In a valid case, Spring Cloud Contract Verifier uses the file to generate a **generated producer test**, test Inventory's controller/implementation, and produce stub mappings for Checkout to use with Stub Runner.

Yet Groovy is a **general-purpose programming language**. Inside a Groovy script, imports, variables, method calls, and statements are not mere HTTP data descriptors. The benign example below is still **executable code**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

def sourceLabel = 'consumer-proposal'
println "Contract source: $sourceLabel"

// Contract.make { ... } lines remain just part of a Groovy script.
~~~

This illustrates **executability**, not a recommended production contract pattern: how the plugin loads scripts and permits top-level statements can vary by version. What matters is that a plugin may need to **evaluate a script**, rather than merely parsing JSON keys.

Anyone able to modify a Groovy file can attempt to add **non-contract operations**: reading files, reading environment variables, spawning processes, opening network connections, or altering build outputs. You do not need an attack payload to recognize the risk: **an executable input boundary is the primary hazard**.

## 2. Why is CI/CD a sensitive target?

Build jobs often hold privileges that a PR author lacks directly:

| CI resource | Example | Risk when untrusted DSL executes |
|---|---|---|
| **Secrets** | Artifact tokens, deploy credentials, cloud keys | Can be accessed or exfiltrated via logs/traffic |
| **Workspace** | Sources, fixtures, generated tests, build outputs | Can be altered/deleted or falsify test evidence |
| **Network** | Internal Maven repositories, test DBs, metadata endpoints | Can be accessed outside intended purpose |
| **Artifact publisher** | Nexus/Artifactory, Maven Central, internal registries | Can publish unverified artifacts |
| **Git credentials** | Tokens used to push tags/branches | Can modify repositories/branches unexpectedly |
| **Build cache** | Gradle caches, Maven local, CI artifacts | Can be poisoned to affect other jobs |
| **Runner host** | Self-hosted runners, Docker daemon sockets | Can break out beyond the container/job |
| **Reports/status** | Test counts, logs, generated stubs | Can be forged or mask failures |

**Groovy code does not need to sit in `src/main` to be dangerous.** If a plugin evaluates contract scripts during test or stub generation, the "build/test" step is already a potential code-execution point for that file's contents.

Specifically, running `./mvnw verify` or `./gradlew contractTest` **is not a purely safe read-only check**: Maven/Gradle scripts, plugins, test code, and Groovy contracts are all executable components. A command "just to validate contracts" can still run arbitrary code.

## 3. Trust boundary model

Classify inputs and environments by **control**, rather than solely by file extension.

~~~mermaid
flowchart TD
    A["Untrusted PR / fork"] --> B["Static diff / metadata checks"]
    B --> C["Code owners + security review"]
    C --> D{"Eligible to execute?"}
    D -->|Not yet| E["Do not run Groovy DSL in privileged job"]
    D -->|Yes, yet needs trial| F["Ephemeral runner, zero secrets"]
    F --> G["Producer contract verification"]
    G --> H{"Tests PASS and provenance OK?"}
    H -->|No| I["Do not publish"]
    H -->|Yes| J["Create candidate artifact with digest"]
    J --> K["Consumer Stub Runner compatibility tests"]
    K --> L{"Release gates PASS?"}
    L -->|Yes| M["Protected promotion job"]
    L -->|No| I
~~~

Key concepts:

- **Untrusted input:** fork PRs, unreviewed commits, contract JARs uploaded by external sources, unpinned Git refs, dependencies of unclear origin.
- **Trusted review:** changes reviewed by responsible owners covering both contract semantics and executable code.
- **Isolated execution:** an environment permitting execution for testing without granting secrets or sensitive access.
- **Trusted promotion:** the stage moving **the exact verified artifact** to the release channel, with dedicated approvals and credentials.
- **Provenance:** the ability to trace which commit/artifact digest contracts came from and which bytes tests ran against.

No "internal branch" label automatically guarantees every change is trustworthy. A team member's account can be compromised, a dependency can change, and a contract JAR can be overwritten mid-CI.

## 4. Contract source map: where must controls apply?

Spring Cloud Contract can accept contracts from multiple sources. Each source is a build entrypoint.

| Contract source | Example | Boundary to guard |
|---|---|---|
| **Files in producer repo** | `src/contractTest/resources/contracts/*.groovy` | PR diffs, CODEOWNERS, branch protection |
| **External checkout folder** | `../common-contracts/inventory` | External repo commit, CI permissions, path tampering |
| **Maven contract artifact** | `com.example.contracts:shared-contracts:1.4.0` | Repository, publisher, coordinates, digest, contents |
| **Git SCM contract store** | `git://https://git.example.invalid/contracts.git` | Git ref/commit, repo permissions, layout, history |
| **Fixtures/body templates** | JSON/XML/body files, request matcher config | Templating, sensitive data, and file paths |
| **Build scripts and plugins** | `pom.xml`, `build.gradle`, plugin code | Pipeline itself runs these executable files |
| **Stub artifact for consumers** | `inventory-producer:2.3.0:stubs` | Candidate/verified distinction, mapping source, version |

Therefore, guarding only `src/contractTest/resources/contracts` is **insufficient** if the producer also fetches external contract JARs or Git SCMs. Control the **entire path from DSL source to execution site**.

### What to verify when using contract JARs

A JAR resolving successfully proves only that the artifact is downloadable. It does **not** prove scripts inside the JAR are safe.

Verify:

1. Group/artifact/version/classifier and source repository.
2. Immutable version/digest, never overwritten post-review.
3. Actual DSL/fixture contents inside the JAR.
4. Which users/CI jobs hold permission to publish that artifact.
5. Only approved paths are consumed by the generator.
6. Producer tests executed against the **exact reviewed build**.

Even an internal repository can hold untrusted artifacts if publish permissions are overly broad.

## 5. Does YAML DSL eliminate all risk?

**No**, though the distinction matters.

| Characteristic | Groovy DSL | YAML DSL |
|---|---|---|
| Format nature | Programming language script | Declarative data |
| Direct arbitrary code execution risk from file | **Higher**, when plugin evaluates scripts | **Lower** when parsed with a strict schema-validated safe loader |
| Can describe HTTP/message contracts | Yes | Yes |
| Can serve as source for generated tests/stubs | Yes | Yes |
| Can contain harmful content for consumers | Yes | Yes: paths, bodies, templates, invalid values |
| Replaces dependency/plugin review | No | No |
| Means the whole pipeline is a safe sandbox | No | No |

**YAML does not mean "impossible to cause security flaws".** If a loader enables arbitrary-type deserialization, untrusted custom tags, custom transformers, script/template engines, or unpatched plugins, YAML data can still trigger dangerous behavior.

Still, an engineering policy can **prefer declarative YAML** for externally proposed contracts whenever DSL features suffice. Disallowing Groovy on untrusted paths shrinks the direct code-execution surface.

### Appropriate controls for YAML

- Parser uses **safe load**, forbidding arbitrary object/class instantiation from untrusted tags.
- Validate against the **contract DSL schema and field allowlist**, rejecting arbitrary keys.
- Limit file sizes, nesting/aliases, and parser resources to prevent DoS.
- Allow fixture/body paths strictly within approved roots.
- Never render templates via overly privileged evaluators.
- Never let a PR's YAML file alter **CI workflows** or plugin configurations outside review scope.
- Even for YAML-only contracts, generators and test runners should still run **without secrets**.

If the team permits Groovy DSL because matchers need complex logic, treat it explicitly as **code review + execution isolation**, never calling it "just config parsing".

## 6. Classifying DSL changes by risk level

Every contract change requires business review; for **Groovy**, security review must inspect beyond request/response fields.

| Change type | Example | Review action |
|---|---|---|
| Change expected status/body | `200` to `201`, add `quantity` | Evaluate compatibility |
| Add matchers | `byType()`, `byRegex(...)` | Check for overly loose/tight bounds |
| Add headers/path/query | `Idempotency-Key`, new endpoint | Evaluate API semantics |
| Add `import` unneeded by Contract DSL | Libraries outside contract API | **Security review**, require justification |
| Add top-level statements or arbitrary closures | Logic not serving request/response | **Block for review**; never run on privileged CI |
| Use file/process/network/env APIs | Unrelated to contract behavior | Treat as a **critical risk signal** |
| Edit `pom.xml`/`build.gradle`/wrapper | Change plugins/repositories/scripts | Review as **executable build code** |
| Edit workflow permissions/runners | Add write permissions or self-hosted runner | Security and branch-protection review |
| Pull contracts from an external repo | Change URL/version/branch | Verify provenance and publish permissions |

Static pattern checks can spot flags like unusual imports or references to `System`, yet **cannot guarantee safety across arbitrary Groovy code**. Code can be expressed in countless obfuscated forms. Therefore **never substitute regex blacklists for execution boundaries and review**.

## 7. Principle: never execute unreviewed input in privileged jobs

An unsafe pipeline commonly mixes:

~~~text
Pull request from untrusted contributor
    ↓
Checkout PR head
    ↓
Run ./gradlew contractTest (eval Groovy DSL)
    ↓
Artifact deploy credentials present
    ↓
Publish stubs / push tags
~~~

The trust boundary was already crossed at DSL execution **because credentials were present**, not only at the publish step.

Better design:

~~~text
Untrusted PR
    ↓
Static review / checks with read-only permissions
    ↓
Optional isolated test execution (no secrets)
    ↓
Human/code-owner approval + verified source revision
    ↓
Producer verification on protected source
    ↓
Candidate artifact with digest
    ↓
Consumer compatibility tests
    ↓
Protected promotion job (credentials only here)
~~~

**Zero secrets in test-execution jobs** means injecting none via environment variables, files, Docker mounts, agent credentials, credential helpers, or network metadata services. Unsetting one env var while leaving `~/.m2/settings.xml` mounted with a repository password does not make the job secret-free.

### Least-privilege controls

- Repository tokens need only `contents: read` for source-reading jobs.
- Never grant `packages: write`/`contents: write`/OIDC publish to PR jobs.
- Never supply deploy keys, cloud credentials, or Artifactory publish tokens to test jobs.
- Never mount the Docker socket or host directories holding secrets into untrusted runners.
- Never share persistent self-hosted runners across projects with broad privileges without isolation.
- Each PR execution uses an isolated or reliably reset workspace/cache.
- Never feed PR outputs/logs/artifacts into automatic execution inside a privileged job.

The goal is that if a PR holds untrusted code, it **has no valuable assets to steal or tamper with**, and zero authority to alter releases.

## 8. CODEOWNERS, branch protection, and review sources

In GitHub, an illustrative `CODEOWNERS` might be:

~~~text
# Illustrative paths specific to a repository.
/inventory-producer/src/contractTest/resources/contracts/ @inventory-owners @security-reviewers
/inventory-producer/build.gradle @build-owners @security-reviewers
/.github/workflows/ @platform-security
/.github/CODEOWNERS @platform-security
~~~

Account/team handles are placeholders. `CODEOWNERS` by itself **does not enforce reviews** unless branch protection/rulesets require code-owner approval.

A sound policy includes:

1. Protected branches forbidding arbitrary direct pushes.
2. Required producer-owner reviews on Groovy DSL / contract JAR paths.
3. Security/platform reviews for workflow, Gradle/Maven plugin, wrapper, and repository config edits.
4. Mandatory status checks that authors cannot bypass.
5. Re-review whenever PRs are updated post-approval, per platform rules.
6. Restricting permission to edit `CODEOWNERS`/rulesets to appropriate admins.
7. Confirming reviewers inspected **executable code**, not merely status/body fields.

**Consumer approval of API behavior does not equal security approval of arbitrary Groovy code.** Those two reviews serve distinct purposes.


## 9. GitHub Actions: checking PRs without executing Groovy DSL

Example workflow performing **static checks only** on a PR, without running Gradle, Maven, Groovy, the Spring Cloud Contract plugin, or test code from the PR branch:

~~~yaml
name: Contract proposal static checks

on:
  pull_request:

permissions:
  contents: read

jobs:
  contract-diff:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout for static review
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Check changed files without executing them
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        shell: bash
        run: |
          git diff --check "$BASE_SHA" "$HEAD_SHA"
          git diff --name-status "$BASE_SHA" "$HEAD_SHA" -- \
            inventory-producer/src/contractTest/resources/contracts/
          echo "DSL files were NOT executed in this job"
~~~

This is a **directional example**; adjust paths per repository, and pin `actions/checkout@v4` to a **full commit SHA** in strict supply-chain CI environments. This workflow does two simple things:

- Lists modified files in the contracts directory.
- Detects whitespace errors in the diff.

It is **not** a Groovy security scanner, does not validate contract correctness, and does not replace code-owner reviews.

### Why keep secrets out of PR jobs?

Even a static-check job should have **zero secrets**. Later, someone might add a `./gradlew contractTest` step to the workflow: if the workflow already holds credentials by default, the security boundary breaks quietly.

For GitHub Actions:

- `pull_request` events usually restrict fork PR permissions, yet you must **confirm organizational and repository policies** rather than relying blindly on defaults.
- `permissions: contents: read` restricts `GITHUB_TOKEN` scopes explicitly, yet does not affect external secrets configured outside the token.
- `persist-credentials: false` avoids storing checkout credentials in Git config where later steps could reuse them.
- `fetch-depth: 0` fetches full history for base/head diffs; weigh fetch cost on large repositories.
- Running only `git diff` does not execute DSL; running `./gradlew`, shell scripts, `make`, or Maven goals from a PR **executes code**.

### What if you want to run the generator on PRs for early feedback?

You can, provided you treat it as **untrusted code execution**. Use an ephemeral, isolated runner with zero secrets, zero publish rights, and restricted egress. Static checks above provide **insufficient protection** if the runner is later granted permission to invoke Gradle/Maven.

Never tie contract quality to secret access: a business-valid PR can still embed unrelated Groovy statements.

## 10. Special warning: `pull_request_target`

In GitHub Actions, `pull_request_target` runs in the context of the **base repository** and can be configured with stronger permissions/secrets than `pull_request`. Danger strikes when a workflow uses this privileged context yet checks out the **untrusted PR head commit** and runs Gradle/Maven/Groovy from it.

Broken pattern:

~~~text
on: pull_request_target
    ↓
Checkout untrusted PR head
    ↓
Run producer contract generator / tests
    ↓
Job has base repo credentials or write privileges
    ↓
Untrusted Groovy/build code executes in privileged context
~~~

**Never implement the pattern above.**

`pull_request_target` has legitimate uses like labeling or metadata handling, yet should never execute untrusted PR **source code/DSL** with base-repo credentials.

### Variants carrying the same risk

- Using a privileged `workflow_run` that downloads artifacts from an untrusted PR and executes files inside.
- Calling a reusable workflow with default secrets open to any caller without checking ref/provenance.
- Interpolating contributor-controlled PR/branch names directly into shell script templates.
- Running `git checkout` to a PR-supplied SHA inside a publish job.
- Running a "lint" tool added by the PR itself, when it is an executable script.
- Reusing containers/runners with leftover tokens from an earlier job.

**Untrusted inputs stay untrusted even when passed via artifacts or messages from another workflow.** Verify data types, origins, digests, and permissions before a privileged job consumes them.

## 11. Preventing command injection from CI metadata

Even without evaluating Groovy DSL, PR metadata such as titles, branch names, or comments are **externally controlled data**. Interpolating a workflow expression directly into a shell command turns data into shell syntax.

Example to avoid on principle:

~~~yaml
# Do not do this:
# run: echo "${{ github.event.pull_request.title }}"
~~~

Safer way to print a title:

~~~yaml
- name: Print PR title as data
  env:
    CHANGE_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$CHANGE_TITLE"
~~~

This passes the string into an **environment variable** and prints it as quoted data, rather than interpolating user-controlled content directly into shell source code. Still, any string used as a **file path, ref, regex, command argument, or URL** must be validated contextually.

**Never run `eval`, `bash -c`, or dynamic templating over contributor-supplied text** just for convenience building commands. This rule covers all CI metadata, not just Groovy DSL.

## 12. Post-review producer verification job

Another example for a **protected branch**, assuming branch protection and code-owner approvals are already enforced:

~~~yaml
name: Verified producer contracts

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  verify-producer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Verify approved producer contracts
        shell: bash
        run: |
          ./gradlew :inventory-producer:contractTest \
            --no-daemon --no-build-cache
~~~

**Critical boundary:** this job runs only sources from a protected, reviewed branch, never an arbitrary PR head. It holds no publish secrets and should not perform automated releases.

The example assumes the producer uses a **modern Spring Cloud Contract Gradle plugin**, `contractTest` exists, the wrapper/Gradle plugins are configured, and dependencies resolve cleanly. For Maven, substitute `./mvnw -B -ntp clean verify` in a producer configured with the verifier plugin.

**Never conclude "100% safe" just because a commit is on `main`.** Review policies can slip, maintainer accounts can be compromised, or dependencies/plugins can be malicious. Keep ephemeral runners, least privilege, and supply-chain controls active.

### An operational trade-off: breaking `main`

Waiting until post-merge to run full contract verification can surface bugs late. Teams needing pre-merge feedback can run producer tests **on PRs** inside isolated runners with **zero secrets and zero publish rights**, under strict network/access controls. Post-approval, still re-verify on the protected source as a release gate.

What is forbidden is letting "we want early feedback" become an excuse to give publish credentials to untrusted execution.

## 13. Execution isolation: runners, filesystems, and networks

A container is **not automatically a complete security sandbox**. Processes inside a container can still have network access, mount workspaces holding secrets, share the host kernel, or run in privileged mode.

A test environment for untrusted PR Groovy should enforce:

| Control | Purpose |
|---|---|
| **Ephemeral VM/runner** | Destroys state after one run; prevents cross-job contamination |
| **Zero secrets** | No tokens, keys, Maven settings credentials, agent sockets, or sensitive CI env |
| **Non-root / unprivileged** | Reduces reach over filesystems, kernel, and container host |
| **No Docker socket mount** | Never grant control over the host Docker daemon |
| **Egress allowlist or no network** | Blocks access to internal services and unauthorized data sinks |
| **Isolated writable workspace** | Lets builds write outputs without polluting shared directories |
| **CPU/memory/time quotas** | Caps runaway execution or resource exhaustion |
| **Read-only mounts where possible** | Limits source/system tampering; isolate output volumes |
| **Isolated dependencies/caches** | Prevents PRs from poisoning caches used by trusted jobs |
| **Controlled log + artifact retention** | Preserves evidence without storing secrets |

### Practical tension between networking and build dependencies

`./gradlew` or `./mvnw` may need to download dependencies. Blocking all network traffic at startup with an empty cache will fail builds from missing dependencies rather than contract errors.

A workable design:

1. **Prefetch approved dependencies** in a trusted step into a cache or read-only repository mirror.
2. Run untrusted builds in isolated runners reading solely from allowlisted dependency sources, with no route to sensitive internal services.
3. Scope caches/outputs per PR.
4. Forbid PR jobs from writing into dependency caches trusted by protected jobs.

Implement these at the actual runner/network-policy layer. Adding `--offline` without pre-populating dependencies in the cache is **not** a reliable solution.

### Warning on self-hosted runners

With shared self-hosted runners:

- Credential files may linger on the host.
- Workspaces and caches may be reused across repositories/PRs.
- Runners may sit inside VPCs with access to databases, metadata endpoints, Kubernetes APIs, or internal registries.
- If runners permit privileged containers or Docker daemon access, container isolation may fail to hold intended boundaries.

Public or untrusted PRs **should never run automatically on privileged self-hosted runners**. If self-hosted runners are required, use single-use ephemeral runners whose isolation is reviewed by the security team.

## 14. Forbid secrets during test generation and contract testing

A design mistake is bundling many privilege levels in one job:

~~~text
Build:
  resolve contracts
  generate tests
  run producer implementation
  package stubs
  publish artifact
  push tags
  deploy staging
~~~

If the job holds credentials from the start, **any code executed in early steps** can reach them. Groovy DSL is just one of several entrypoints.

Recommended separation:

1. **Validate proposal:** static checks, zero secrets.
2. **Execute tests:** isolated runner, read-only sources, zero publish tokens.
3. **Package candidate:** build artifact with digest/provenance, still lacking official publish rights.
4. **Compatibility check:** Stub Runner consumer tests against the exact candidate.
5. **Approve release:** protected environment and approval.
6. **Promote artifact:** credentialed job, **without re-evaluating untrusted Groovy**; prefer promoting the exact verified artifact.

For artifact services requiring **read-only** auth, use a repository mirror or narrowly scoped read-only token restricted to the proper environment step. Even then, **read credentials are still secrets** and must not be exposed to untrusted Groovy execution. Prefetching or caching approved dependency sources is safer.

## 15. Supply chain: plugins, contract JARs, and dependencies are also code/data inputs

Guarding PR Groovy scripts is just one layer. A Java build also executes:

- Gradle build scripts, init scripts, wrappers, and plugin code.
- Maven plugins, extensions, and lifecycle hooks.
- JUnit test classes, static initializers, and build-time processors.
- Groovy contract scripts fetched from Maven/SCM.
- Custom matchers/transformers/helpers and test fixtures.
- GitHub Actions/CI tasks and container entrypoints.

### Pinning versions and sources

Never rely on `latest` or version wildcards for sensitive dependencies when reproducibility matters. You should:

- Pin compatible versions of Spring Boot, the Spring Cloud Contract plugin, and dependency BOMs.
- Verify provenance, checksums, or signatures per organizational policy.
- Use trusted repositories and restrict publish permissions.
- Forbid overwriting release artifacts under the same version.
- Pin contract JAR versions and digests rather than relying solely on an artifact name.
- With Git SCM, record the exact commit SHA; a `META-INF/.../version` folder does not by itself pin a Git revision.
- Pin CI actions/container images by immutable digest/SHA when required by environment policy.
- Isolate caches and never promote an artifact merely because its filename matches tested output.

### Why isn't "internal repo" enough?

If an internal publish account is compromised, a Groovy contract JAR can be replaced right inside the registry trusted by the producer. Subsequent producer builds fetch the artifact and execute its DSL even without a new PR in the producer repository.

**Trust boundaries must guard where contract artifacts are published too**, not only where the plugin runs.

## 16. Contract DSL, stub mappings, and artifact promotion are distinct

In a Spring Cloud Contract pipeline:

~~~text
Groovy/YAML contract source
    |
    v
Producer generated tests (may execute code)
    |
    v
Producer verification PASS
    |
    v
Generated mappings/message definitions
    |
    v
Producer stubs artifact
    |
    v
Consumer Stub Runner
    |
    v
Consumer compatibility test
~~~

**Building a stub JAR does not prove the producer satisfies it.** Generators can emit mappings from DSL even when the producer lacks the endpoint.

**A passing Stub Runner test likewise does not replace producer tests.** The consumer talks to a stub, not the real producer.

### When an artifact comes from an untrusted step

A plausible-looking `*-stubs.jar` remains an **untrusted artifact** if it came from a job that executed unreviewed DSL. Privileged jobs must never:

- Unzip/execute custom code or load plugins/classes from the artifact without source controls.
- Use unverified mappings/fixtures to establish "official" behavior.
- Push that artifact to the release repository without verifying digests and provenance.
- Label it verified merely because consumer stub tests passed.

A candidate artifact is eligible for promotion only when **created from verified sources/conditions** with policy-compliant producer test and consumer gate evidence.

## 17. Do not overlook indirect workflow modifications

A contributor does not need to touch `*.groovy` if permitted to alter how the generator runs. These changes also need security review:

| File or setting | Impact |
|---|---|
| `pom.xml` / `build.gradle` | Adds plugins, repositories, scripts, or disables tests |
| `settings.gradle` / Gradle init scripts | Redirects plugin/dependency sources or configuration logic |
| `gradlew` / Maven wrapper config | Alters the build execution binary |
| `.github/workflows/*.yml` | Alters triggers, permissions, secrets, or runners |
| Contract repository URL | Redirects Groovy sources from a trusted artifact to elsewhere |
| `contractsPath`, include/ignore filters | Can pull different DSL or skip tests |
| `failOnNoContracts`, `failOnInProgress` | Affects gates when valid contracts are absent |
| `skipTests` or disabling `contractTest` | Can build stubs without verifying the producer |
| Stub publication destination | Can publish artifacts to unauthorized locations |
| Docker runner/volume config | Can expose secrets/sockets into untrusted code scope |

CODEOWNERS and rulesets should cover both **contract sources and build/CI configurations**. Requiring reviews solely inside `contracts/` lets a PR alter pipeline behavior elsewhere.


## 18. Verification tiers: static, isolated, and trusted

Not every check carries identical privileges or risks.

| Check tier | Work performed | Executes Groovy DSL? | Conditions |
|---|---|---|---|
| **Static file review** | Inspects diffs, extensions, paths, whitespace, sizes | **No** | PR from any source; read-only access |
| **Static policy scan** | Looks for unexpected imports/commands | **No**, if scanner reads text only | Use reviewed scanner; never PR-supplied scripts |
| **YAML schema validation** | Parses via safe loader, validates fields/types | Normally runs no Groovy | Block custom object deserialization / template execution |
| **Groovy syntax/generator check** | Compiles/evaluates DSL | **Potentially yes** | Isolated untrusted runner or reviewed sources |
| **Producer `contractTest`** | Runs generated tests on implementation | **Yes** | Controlled runner with zero publish secrets |
| **Consumer Stub Runner test** | Exercises stub mappings / message definitions | Can run test/plugin code | Verified source artifacts only; minimal-privilege runner |
| **Artifact publish/promotion** | Publishes verified stubs | **Must not** re-execute untrusted inputs | Protected job, approvals, provenance/digests |

Distinguishing "syntax analysis" from "execution" is crucial. A tool checking syntax by **loading/evaluating a Groovy script** is no longer a static scanner, even if its CLI subcommand is named `validate` or `lint`.

### A simple policy for untrusted PRs

1. Collect the diff as plain data.
2. Check file structure, paths, extensions, and size limits.
3. Flag changes containing imports, top-level statements, or build/CI config edits.
4. Route to code owners and security reviewers.
5. If execution is needed for pre-review feedback: use an **ephemeral isolated environment with zero secrets**, egress allowlists, and zero publish rights.
6. After approval/merge to a protected ref, re-run producer verification.
7. Publish only from verified artifacts tied to that exact source revision.

Searching for strings like `System.getenv` or `new File` catches some anomalies, yet never proves the rest of a script is harmless. Rely on **positive policies and isolation**, not character blacklists.

## 19. Fail closed: protecting the integrity of the contract test gate

The risk is not limited to exfiltration; a PR can make tests **stop running** while keeping CI green.

Example:

~~~text
Before:
  24 generated producer tests executed, 24 passed

After change:
  0 generated producer tests executed
  Gradle/Maven build reports SUCCESS
~~~

If publishing checks only exit codes, CI can publish stubs unverified by the producer.

### Signals to capture

- Contract source/artifact version and SHA.
- Count of discovered DSL files per producer/consumer.
- Count of generated and executed producer tests.
- Names and reasons for any skipped/ignored/`inProgress` tests.
- PASS/FAIL test reports, with expected/actual on failure.
- Plugin version and test mode.
- Whether `verifierStubsJar` or `*-stubs.jar` holds expected mappings/fixtures.
- Artifact hash/provenance and publish destination.

### `failOnNoContracts`

Spring Cloud Contract provides options such as `failOnNoContracts` and `failOnInProgress` in compatible plugin versions. Illustrative Gradle configuration snippet:

~~~groovy
contracts {
    failOnNoContracts = true
    failOnInProgress = true
}
~~~

**Verify compatibility and exact semantics for your version.** Even with these options enabled, CI should still check executed test counts, because a wrong base class or `-x contractTest` filter can defeat the gate.

### Never use skip flags to "wave through" a release

Ways tests get disabled:

~~~bash
# Never use these for a verified release gate:
./mvnw verify -DskipTests
./mvnw verify -Dmaven.test.skip=true
./gradlew build -x contractTest
~~~

Even if stub generation or artifact packaging still produces a file, it **does not prove the producer implementation satisfied the DSL**.

### Never tamper with reports instead of fixing code

Disabling `generateContractTests` or `contractTest`, deleting test reports, or reusing a stale task cache can fake success. For security gates, never rely solely on artifact presence and a generic "BUILD SUCCESS" log; verify evidence from the **exact test run on the exact revision**.

## 20. Protecting artifact promotion and consumer pipelines

A secure workflow for reviewed contract sources:

~~~mermaid
sequenceDiagram
    participant Repo as Protected source
    participant P as Isolated producer CI
    participant Art as Candidate artifacts
    participant C as Consumer CI
    participant Gate as Approval / release policy
    participant Pub as Trusted publisher
    Repo->>P: Checkout reviewed SHA
    P->>P: Generate + execute producer contract tests
    alt Producer tests PASS
        P->>Art: Upload candidate stubs with digest
        Art->>C: Provide exact artifact version
        C->>C: Stub Runner consumer tests
        alt Consumer PASS
            C-->>Gate: Verified test evidence + digest
            Gate->>Pub: Approve promotion
            Pub->>Art: Promote exact artifact, no DSL re-evaluation
        else Consumer FAIL
            C-->>Gate: Block release
        end
    else Producer tests FAIL
        P-->>Gate: Block release
    end
~~~

### Why check digests?

Artifact names can match while bytes change when:

- A `SNAPSHOT` version is overwritten.
- CI artifacts from an untrusted workflow are downloaded by mistake.
- A repository mirror/cache serves a stale build.
- A release job rebuilds from a branch that moved to another commit.
- A plugin builds stubs from different contract sources than the producer test run.

Pinning both version **and** digest verifies the **exact artifact bytes** produced by producer verification and consumed by consumer tests.

### Is consumer Stub Runner an untrusted-code execution risk?

Stub Runner differs from the Groovy contract generator, yet consumer tests still execute **Java test code, Spring runtime, and artifact mappings/fixtures**. Mappings can invoke templating or extensions if configured; an artifact from an untrusted source must not run in an environment holding secrets or broad internal network access.

For consumer pipelines:

- Fetch artifacts solely from authorized repositories with exact versions/digests.
- Avoid `latest`/dynamic versions in release gates.
- Never accept an arbitrary `repositoryRoot` supplied by a PR.
- Isolate runners from deployment secrets.
- Never treat passing consumer tests as producer verification passes.
- Inspect both request matchers and response/error bodies, not status codes alone.

## 21. Scenario 1: contract PR contains unrelated Groovy code

### Context

An external contributor submits a PR claiming to "update JSON response". Actual diff contains:

- Changes `quantity` from `8` to `9`.
- Adds an import/helper unrelated to contracts.
- Adds top-level statements interacting with the environment.
- Modifies the workflow to run `./gradlew contractTest` in a privileged context.

### Why is it suspicious?

Changing the JSON may be reasonable. Yet extra imports/top-level statements and workflow permission edits are **unnecessary to express the response**. This signals an attempt to turn the contract file into a code-execution entrypoint with CI privileges.

### Proper response

1. **Do not run the PR on a privileged runner** "just to see if it passes".
2. Inspect the full diff across Groovy files, build scripts, and workflows.
3. Require the author to justify or remove non-contract code.
4. Security/code-owner review; reject or strip dangerous edits.
5. Keep proposal validation in static check mode; if dynamic checks are needed, use a secret-free ephemeral sandbox.
6. Post-approval, run producer tests on the controlled source revision.
7. Never publish any stub built from this PR ahead of the producer gate.

**Why not rely on a single regex?** Import names and code idioms vary; keyword scanning aids triage without proving the remaining script is harmless.

## 22. Scenario 2: external contract JAR gets overwritten

### Context

Producer configures downloading:

~~~text
com.example.contracts:shared-contracts:1.4.0
~~~

The organization uses an internal artifact repository. A publisher with overwrite rights replaces version `1.4.0`, and pipelines later pull a contract JAR with different bytes than were reviewed.

### Risks

- Groovy DSL inside the artifact may differ from the approved PR.
- Generated producer tests may check altered behavior.
- Build environments may evaluate new Groovy code without producer code review.
- Stubs may be generated from different sources than reviewers expected.
- Builds hitting different caches can produce inconsistent outcomes.

### Remediation

- Disable overwriting release versions in the artifact registry.
- Separate contract-definition publish rights from producer CI read rights.
- Record the digest of reviewed contract JARs.
- Use dedicated candidate versions for PRs; never reuse release coordinates.
- Verify the artifact digest immediately before generator/producer tests run.
- Audit repository ACLs, publisher identities, and provenance.
- If compromise is suspected, **halt Groovy execution from that source** until verified.

**Never treat HTTPS and the word "internal" as sufficient.** HTTPS protects transport; it does not prove contents were reviewed or publisher accounts remain uncompromised.

## 23. Scenario 3: pipeline edited to bypass tests

### Context

In a PR modifying DSL, a contributor also edits Gradle task dependencies so `verifierStubsJar` publishes without `contractTest` running, or adds `-x contractTest` to the CI command.

### Dangerous outcome

~~~text
Contract: new endpoint expected 201
Producer implementation: still returns 404

Generated stub: can return 201 according to DSL
Producer generated test: not executed
Consumer Stub Runner test: PASS
Release artifact published: YES
~~~

Neither artifact existence nor green consumer tests **prove the real producer** implements the API.

### How to block it

- Cover `build.gradle`/`pom.xml` and workflow files with CODEOWNERS.
- Have CI inspect producer test reports and executed generated test counts.
- Make publish jobs depend on the producer verification gate, not merely packaging.
- Prevent release jobs from executing arbitrary scripts from PR artifacts.
- Grant publish access only after approvals and passing gates.
- Record source SHAs/digests for both contracts and stubs.
- Enforce policies blocking `skipTests` or disabled test tasks.

This is why **protecting the verification process itself** matters just as much as protecting secrets.

## 24. When malicious DSL execution is suspected

An incident may surface through anomalous build logs, outputs diverging from contracts, unexpected outbound network traffic, or signs of exposed credentials.

### Incident response steps

1. **Halt running jobs using the suspect contract source**; block publishing and promotion.
2. **Isolate or terminate ephemeral runners** per incident procedure; never reuse workspaces/caches of unknown integrity.
3. **Preserve forensic evidence securely**: commit SHAs, artifact digests, pipeline IDs, secret-redacted logs, action lists, and timestamps.
4. Identify **every resource accessible to that job**: tokens, secret mounts, repositories, registries, cloud credentials, and networks.
5. **Revoke/rotate potentially exposed credentials** per organizational security procedure; do not wait for absolute proof of exfiltration when risk is significant.
6. Quarantine artifacts/caches produced by the job; never reuse or promote them.
7. Audit PR history, contract JAR versions, CI configs, and publisher ACLs to find the entry vector.
8. Provision fresh runners and verified artifact sources, then re-run producer/consumer gates.
9. Document root cause and strengthen controls: permissions, CODEOWNERS, isolation, provenance, and logging.
10. Resume releases only after responsible teams confirm boundaries are restored.

Never post raw secrets or sensitive details publicly in issues/PRs while describing the incident. Use restricted incident-response channels with redacted logs.

## 25. Exercise 1: assessing the trustworthiness of a contract PR

### Prompt

A fork PR adds:

~~~text
inventory-producer/src/contractTest/resources/contracts/reservation.groovy
~~~

Alongside `Contract.make { ... }`, the file contains imports/helpers unrelated to the DSL. The PR also edits GitHub Actions to run Gradle on `pull_request_target` with `contents: write`.

**Question 1:** Should you run `./gradlew contractTest` immediately to see if it passes?

**Answer:** Never run it in a privileged job. Review the diff first, strip/explain unrelated code, and inspect workflow changes. If dynamic feedback is required, use an isolated ephemeral runner with zero secrets and zero publish permissions.

**Question 2:** If a code owner approves the contract body, is that enough?

**Answer:** No. You must review executable Groovy code and workflow permission changes; business approval does not replace security review.

**Question 3:** Would converting all Groovy to YAML solve everything?

**Answer:** It reduces the direct code-execution surface if paired with a safe YAML parser and strict schema, yet you must still protect build scripts, dependencies, templating, fixtures, runners, and artifact promotion.

**Question 4:** Is testing in a runner with zero secrets safe if it still sits inside an internal VPC?

**Answer:** Not necessarily. The runner may reach sensitive internal services, metadata endpoints, or caches over the network. Enforce egress policies, network segmentation, and proper isolation.

## 26. Exercise 2: spotting where CI turns false green

### Scenario

Both producer and consumer are Spring Boot projects. The consumer requests adding `POST /api/inventory/reservations`.

~~~text
Producer code:
  POST /reservations not implemented

Producer pipeline:
  generateClientStubs PASS
  verifierStubsJar PASS
  contractTest SKIPPED

Consumer pipeline:
  Stub Runner serves 201 from generated mapping
  Checkout test PASS

Release:
  candidate stub was promoted to verified repository
~~~

**Question 1:** Which step failed from a quality standpoint?

**Answer:** Producer contract verification was skipped, yet the artifact was published as verified. Stub Runner only proved the consumer handles the mapping, not that the producer implementation complies.

**Question 2:** Which quality gates are needed?

**Answer:** Require generated producer tests to actually execute and PASS against the implementation, valid test counts, matching artifact revision, passing consumer compatibility if required by policy, and protected approval prior to promotion.

**Question 3:** If contracts come from a common contract JAR, what extra controls apply?

**Answer:** Repository/publisher ACLs, immutable versions, source SHAs/digests, exact `contractsPath`, and ensuring Groovy inside the JAR is reviewed code.

**Question 4:** What if a PR needs to test DSL before the producer implements it?

**Answer:** Use a proposal/candidate test lane clearly labeled **not yet supported**; never use the release gate or verified repository for trial results.

## 27. Checklist for securing CI/CD with Groovy contract DSL

### Input and review controls

- [ ] Identified all DSL sources: producer repo, external folders, contract JARs, Git SCM.
- [ ] Groovy DSL treated as **executable code**, not merely a configuration file.
- [ ] Contract YAML uses a safe parser/schema with arbitrary deserialization/templating disabled.
- [ ] PRs from untrusted sources never auto-run Groovy in privileged jobs.
- [ ] CODEOWNERS/rulesets require code-owner and security reviews for sensitive edits.
- [ ] Build scripts, wrappers, dependencies, CI workflows, and runner configs are also reviewed.
- [ ] Diffs add no file/process/network/environment calls unrelated to contracts.
- [ ] Never rely solely on grep/regex blacklists to declare a script safe.

### Permissions and isolation

- [ ] PR jobs hold minimal permissions, zero secrets/publish tokens.
- [ ] Never check out and execute untrusted PR heads inside privileged `pull_request_target`.
- [ ] Never let `workflow_run` execute untrusted artifacts in a high-privilege job.
- [ ] Never interpolate untrusted PR metadata directly into shell commands.
- [ ] Dynamic PR testing, if needed, uses ephemeral, secret-free runners with restricted networking.
- [ ] Runners avoid privileged/root modes unless required and never mount the Docker socket.
- [ ] Workspaces, dependencies, and build caches are isolated so PRs cannot poison protected jobs.
- [ ] Network egress and internal service access are restricted.
- [ ] CPU/memory/time limits and log retention are configured appropriately.

### Producer verification and artifacts

- [ ] Resolvers fetch the exact contract repository, source revision, version, and digest.
- [ ] `contractsPath`/include filters do not drop required DSL files.
- [ ] Generated producer tests **are generated, executed, and PASSED**, never skipped or 0.
- [ ] Build gates never equate `verifierStubsJar` creation with producer verification.
- [ ] Never pass `-x contractTest`/`skipTests` on verified releases.
- [ ] Candidate artifacts pin version/commit/digest without overwriting releases.
- [ ] Stub Runner consumer tests use the exact producer candidate artifact.
- [ ] Consumer tests never substitute for producer verification.
- [ ] Artifact promotion runs only after required gates and approvals.
- [ ] Publish credentials exist solely in the protected promotion job, never in DSL-execution jobs.

### Operations and response

- [ ] Procedures exist to quarantine artifacts/caches or runners upon suspected compromise.
- [ ] Ability to revoke/rotate affected credentials quickly.
- [ ] CI preserves source SHAs, test reports, artifact provenance, and digests.
- [ ] Breaking API/message changes still undergo review as part of quality gates.
- [ ] Neither internal repositories nor HTTPS alone are treated as complete proof of trust.
- [ ] Clear ownership exists for protecting workflows, repository ACLs, and release policies.

## 28. Takeaways and references

**Groovy contract DSL can be executable code.** An untrusted PR or contract JAR can therefore do more than change an expected HTTP response; it can compromise test generation or builds if evaluated in a privileged environment.

**Three boundaries that must never be collapsed into one:**

1. **Untrusted proposal:** inspect diffs, review, and run static checks; dynamic tests only under isolation.
2. **Producer verification:** run code from approved sources—or in isolated runners without publish secrets—to prove the implementation satisfies contracts.
3. **Trusted publication:** promote the exact verified artifact/version with provenance and approvals; never re-evaluate untrusted DSL in credentialed jobs.

Choosing declarative YAML over Groovy where suitable shrinks the direct execution surface, yet never removes the need to secure dependencies, runners, sources, scripts, artifact pipelines, and consumer Stub Runner environments.

### References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): Groovy/YAML DSL, generated producer tests, stubs, and Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): DSL formats and matchers.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): lifecycle for generating and running contract tests.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, `verifierStubsJar`, and publication.
- [GitHub Docs — Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): least privilege, untrusted inputs, runners, and third-party actions.
- [GitHub Docs — Events that trigger workflows](https://docs.github.com/en/actions/reference/events-that-trigger-workflows): context differences between `pull_request` and `pull_request_target`.
- [GitHub Docs — About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners): requiring reviews when sensitive files change.
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html): privilege boundaries, secrets, runner isolation, and supply-chain controls.
- [SLSA — Supply-chain Levels for Software Artifacts](https://slsa.dev/): provenance, build integrity, and artifact verification.

**Practical conclusion:** if you cannot explain **who controls the DSL being executed, which privileges that job holds, and which exact test run produced the published artifact**, you lack sufficient basis to call the pipeline safe or trustworthy. Securing sources, execution, and publication together enables Spring Cloud Contract to catch incompatible changes without introducing supply-chain risk.
