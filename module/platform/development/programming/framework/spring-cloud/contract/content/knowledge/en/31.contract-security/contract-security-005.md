# Protecting Read and Write Access to the Artifact Repository

## 1. Why is the artifact repository part of contract security?

In **Spring Cloud Contract (SCC)**, producers and consumers agree on HTTP or messaging interactions via **Groovy/YAML DSL**. The producer uses **Contract Verifier** to generate and run tests verifying the implementation, builds a **stub artifact**, and publishes it to a Maven-compatible repository (such as Nexus or Artifactory). The consumer uses **Stub Runner** to fetch the right stub, start an HTTP stub or simulate messages, and test its HTTP client or message handler. CI helps catch incompatible API changes.

However, that chain of evidence is trustworthy only when **the stub package downloaded by the consumer is genuinely the one verified and published with authority by the producer**.

Example:

```text
Producer:
  com.acme.billing:payment-service:1.4.2
  └─ payment-service-1.4.2-stubs.jar

Consumer:
  checkout-service
  └─ Stub Runner REMOTE
     └─ com.acme.billing:payment-service:1.4.2:stubs

Repository:
  https://repo.example.org/repository/maven-releases/
```

If a consumer user also holds **write access** to `maven-releases`, they could accidentally or intentionally replace an already-published stub version. Consumer CI might then test against a **forged-origin mock contract**, leading to false passes or wrongly blocked releases. Conversely, if producer CI lacks the proper minimal write permissions, stub publishing breaks.

**Topic of this lesson:** designing and operating **artifact repository read/write access controls** to protect the confidentiality, integrity, provenance, and availability of contracts. This is an infrastructure governance requirement **complementary** to SCC's testing features, not SCC itself managing Nexus/Artifactory accounts or ACLs.

### 1.1. What will you learn?

1. Distinguish **stub readers** from **stub publishers** and their least-privilege permissions.
2. Identify boundaries between the repository, build tool, Stub Runner, and consumer HTTP tests.
3. Configure read/write via Maven `settings.xml`, Gradle `maven-publish`, and Stub Runner `REMOTE` with secrets outside source code.
4. Distinguish repository permission `401/403/404` from `404` returned by an HTTP stub.
5. Protect release artifacts against overwrites, dependency confusion, untrusted sources, and wrong caches/mirrors.
6. Design CI gates, token rotation, audit trails, and incident revocation procedures.
7. Handle snapshots, development environments, external partners, and multiple teams consuming stubs.
8. Practice building a role matrix and testing both happy paths and **policy-denied** paths.

> **Foundational principle:** Consumers need **read access to the exact stub package**, not deploy/delete privileges; producer release CI needs **scoped write access**, not full-repository admin rights.

## 2. Trust model: who is allowed to do what?

A minimal system has four actors:

- **Producer developer:** writes contracts, edits implementations, runs producer verification locally; does not automatically hold release publish rights.
- **Producer CI release identity:** builds artifacts from approved commits/contracts, runs tests, and **publishes** to the designated repository.
- **Consumer CI test identity:** **reads** published artifacts and runs Stub Runner with chosen versions; needs no upload/delete rights.
- **Repository administrator:** creates repositories, policies, identities/roles, audits, retention, and incident response; admin accounts should never be default build credentials.

```mermaid
flowchart LR
    DEV["Producer developer"] -->|PR + contract review| CI["Producer CI"]
    CI -->|Verify + package| JAR["Versioned -stubs.jar"]
    JAR -->|WRITE via publish identity| REPO["Artifact repository"]
    CON["Consumer CI"] -->|READ via test identity| REPO
    REPO -->|Stub JAR| RUN["SCC Stub Runner"]
    RUN -->|WireMock/message stubs| TEST["Consumer tests"]
    ADMIN["Repository admin"] -. "ACL, retention, audit" .-> REPO
```

The **WRITE** and **READ** arrows represent two separate permissions. A CI runner may run both builds and tests, yet **credentials must be provisioned per job/stage and purpose**; never hand write tokens to every job just to "save configuration".

### 2.1. Sample permission matrix

| Actor | Read release stubs | Write release stubs | Read snapshot stubs | Write snapshot stubs | Delete/overwrite releases | Administer ACLs |
|---|---|---|---|---|---|---|
| Consumer CI | **Yes** | No | When needed | No | No | No |
| Producer PR CI (untrusted code) | As needed | **No** | As needed | Usually no | No | No |
| Producer release CI | Yes | **Assigned namespace only** | Yes | Per policy | **No** | No |
| Producer development publisher | Yes | No | Yes | Possible in dev namespace | No | No |
| Artifact admin | Per task | Per task | Per task | Per task | Exception process only | **Yes** |

This is a **recommended policy**, not default Nexus/Artifactory role names. Specific permissions can be expressed as repository/path/namespace ACLs, token scopes, project roles, or workload identities depending on the product.

**Even if consumers can only read artifacts, they can still be misled by an artifact replaced** by another publisher. Therefore, you must protect both the write path and source identity, not only lock down consumer permissions.

## 3. Assets that need protection

| Asset | Example | Risk if control is lost |
|---|---|---|
| Contract DSL | `contracts/payments/payment-captured.yml` | API expectations altered without authorization |
| Producer verification report | Generated tests for P2 | Unverified artifact marked as verified |
| Stub JAR | `payment-service-1.4.2-stubs.jar` | Mappings altered, fake responses added, or sensitive data embedded |
| Artifact metadata/POM | `payment-service-1.4.2.pom` | Consumer resolves wrong version or pulls unexpected dependencies |
| Repository URL/mirror | `maven-releases`, `maven-snapshots` | Stub comes from an unapproved repository |
| Read/write credentials | Username/token/OIDC identity | Leakage, overwrites, unauthorized artifact access |
| Consumer test configuration | Stub Runner `ids`/`repositoryRoot` | CI downloads wrong classifier/version or hits production URL |
| Audit/build provenance | Commit, test report, checksum, publisher identity | Unable to trace which stub was used during an incident |

### 3.1. Contracts are not places for real secrets

An SCC stub artifact can contain **request headers, bodies, paths, and sample responses**. Thus, contracts containing literal tokens, cookies, passwords, emails, or real personal data risk being packaged into `-stubs.jar` and spreading to consumer machines or artifact repositories.

Example of **what not to do**:

```yaml
request:
  method: GET
  url: /api/payments/PAY-42
  headers:
    Authorization: "Bearer REAL_ACCESS_TOKEN_VALUE"
response:
  status: 200
```

Use **fake values with no real access rights**, appropriate matchers, or synthetic fixtures. If a contract needs to prove an `Authorization` header exists, describe its structure/matcher in the DSL rather than embedding a production token.

### 3.2. A Stub JAR is a published artifact, not a harmless JSON file

A `-stubs.jar` package is normally used to run mappings; however, JAR/POM/metadata formats interact with build systems and dependency resolution. Downloading from the wrong repository, an uncontrolled mirror, or using a POM that pulls untrusted dependencies still creates **supply chain risks**.

Do not treat "it's just a test stub" as a reason to disable source checks, authentication, or least-privilege principles.

## 4. Separating three repository zones: development, release, and external

A Maven repository layout might separate:

```text
https://repo.example.org/repository/maven-snapshots/
  com/acme/billing/payment-service/1.5.0-SNAPSHOT/...

https://repo.example.org/repository/maven-releases/
  com/acme/billing/payment-service/1.4.2/...

https://repo.example.org/repository/maven-proxy/
  approved external dependencies...
```

**`maven-proxy` is only an illustrative name**, not an SCC-defined repository type. Nexus/Artifactory implement hosted, proxy, and virtual/group repositories in their own ways.

### 4.1. Release repository

- Only approved CI identities have permission to **publish** into the producer namespace.
- Release artifacts should be **immutable**: forbid overwriting/redeploying the same GAV/version/classifier.
- Consumers may **read** published artifacts they are authorized to use.
- Maintain proper audit logs, retention, and backups.
- Disallow anonymous writes; allow anonymous reads only if data is approved for public disclosure by policy.

### 4.2. Snapshot/development repository

- Supports non-final builds, such as `1.5.0-SNAPSHOT`.
- May allow developer/separate CI publishing inside a dev namespace.
- Shorter retention with cleanup rules for old builds.
- Consumer CI using snapshots must record the resolved artifact/timestamp/checksum; do not treat it as reproducible release evidence.
- **Do not** use a snapshot publisher token as a release publisher token.

### 4.3. External repositories

If consumer tests download from a partner repository or public repository, evaluate trust policy:

- Approved host/domain and TLS certificate.
- Artifact/group namespace matches the legitimate publisher.
- Appropriate version locking/pinning and integrity/provenance mechanisms.
- Never add an unknown repository when the resolver reports 404.
- Avoid sending internal repository credentials to external endpoints due to URL/mirror changes.

## 5. Authentication, authorization, integrity, and audit: four distinct layers

**Authentication (AuthN)** answers **"Who is accessing?"** For example, a CI job using an issued token.

**Authorization (AuthZ)** answers **"What is this identity allowed to do, on which repository/path?"** For example, consumer CI having a read-only scope.

**Integrity/provenance** answers **"Does this package have the exact verified content and publishing origin?"** For example, checksums, signatures, and build metadata linking to the source commit.

**Auditability** answers **"Who downloaded, wrote, overwrote, or deleted which artifact, and when?"** Repository audit logs and CI release records.

Do not equate them:

- A valid token **does not** mean it is allowed to publish to any groupId.
- Successful HTTPS **does not** mean the content is a producer-approved artifact.
- A checksum stored next to an artifact **does not** prove authorship if an attacker can replace both JAR and checksum.
- Producer verification PASS for commit A **does not** prove a JAR came from commit B.
- A green Consumer Stub Runner test **does not** verify credentials were granted least-privilege permissions.

### 5.1. Zero trust does not mean everything is "public"

Consumer tests may need stubs from multiple different producers. Instead of one admin token used for everything:

- Grant read permissions by **team, repository, namespace, and environment**.
- Grant write permissions by **producer namespace and release workflow**.
- Restrict manage/delete/overwrite privileges as tightly as possible.
- Use separate identities across PRs, main branches, release tags, and production deploys.
- Revoke permissions when a service or pipeline is decommissioned.

This is **least privilege** practice, especially important when artifacts can influence release decisions.

## 6. Practical threat model for the stub repository

| Scenario | Possible consequence | Defensive layer |
|---|---|---|
| Consumer token has write permission | Consumer CI can replace producer stubs | Read-only role, denied-write tests |
| Producer token appears in PR build | Untrusted pull request can exfiltrate credential | Secret isolation, protected workflows |
| Release artifact can be overwritten | "Version 1.4.2" points to two different contents | Repository immutability |
| Stub JAR contains real token | Secret spreads across artifacts and caches | Synthetic data, secret scanning |
| Download over cleartext HTTP | Credentials/content easily exposed or altered | HTTPS + certificate validation |
| Resolver falls back to public repo | Dependency confusion/namespace collision | Repository allowlists, mirror/content filters |
| No build provenance recorded | Unknown which commit/test produced stub | Build metadata, checksums/signatures |
| Developer uses admin token | Overly broad rights, hard to revoke per job | Scoped tokens/workload identities |
| Read credential leaks into logs | Outsiders download unauthorized artifacts | Masking, no secret logging, rotation |
| 401/403 "fixed" by making repo anonymous | Loss of access control | Fix role/credential in the right place |
| Stale cache keeps tests green | Consumer tests use unverified build for new release | Version pinning, cache policy, log resolved artifact |
| Token expires mid-publish | Artifact/POM partially published depending on repo | Controlled retries, verify publication state |
| Plugin/build dependency swapped from odd mirror | Producer build compromised | Pin trusted plugins/repositories, verification |

### 6.1. Negative permission test examples

Besides "producer publishes successfully" and "consumer downloads successfully", test:

- Token `consumer-read` **cannot upload/delete** artifacts.
- Token `producer-payment-publish` **cannot publish** to `inventory-service`'s namespace.
- PR CI lacks release credentials when code comes from an untrusted branch.
- The release repository **rejects redeploying** an already-existing version.
- A revoked account can no longer download/publish, with an audit event recorded.

**Never perform delete/overwrite tests against a real release repository** without a dedicated test environment and test permissions. Use a sandbox repository with dummy artifacts and equivalent policies to verify denied cases.

## 7. How does Stub Runner fetch artifacts?

SCC Stub Runner supports three common modes:

| Mode | Where are stubs fetched from? | Required security controls |
|---|---|---|
| `CLASSPATH` | Stub JAR on test classpath | Dependency provenance, lock/verification, build-tool repo controls |
| `LOCAL` | Local Maven repository, usually `~/.m2` | Who can write to local cache, avoid stale artifacts |
| `REMOTE` | Maven-compatible repository, e.g., Nexus/Artifactory | TLS, credentials, **read-only role**, pin version, and audit |

**No mode means "no security needed".** `CLASSPATH` can load JARs from dependency repositories; `LOCAL` still risks cache tampering; `REMOTE` depends on ACLs and network boundaries.

### 7.1. Distinguish artifact coordinates from the producer URL

```text
Stub ID:
  com.acme.billing:payment-service:1.4.2:stubs

Repository root:
  https://repo.example.org/repository/maven-releases/

Stub HTTP server while test runs:
  http://localhost:<dynamic-port>

Producer API in real environment:
  https://payment-api.example.internal/
```

`repositoryRoot` is **the source for downloading the JAR**, not the producer's HTTP base URL. During tests, the consumer must call **Stub Runner's HTTP URL/port**, avoiding accidental calls to the real producer when stubs fail to download.

### 7.2. Use immutable versions instead of `+` for release gates

```text
# Pinned for traceability:
com.acme.billing:payment-service:1.4.2:stubs

# Track compatibility against latest build:
com.acme.billing:payment-service:+:stubs
```

Stub Runner's `+` instructs the resolver to pick the latest version permitted by the source. It is useful for **breaking-change discovery jobs** but can change between runs. Release CI should pin an exact version or record the resolved version, artifact checksum, and provenance.

### 7.3. Do not "fall back" to a weakly secured repository

If `REMOTE` fails to download an artifact due to bad credentials, **do not** add a public Maven repo or switch to `LOCAL` to use an arbitrary cache and claim the consumer is compatible. Fix the root cause: token, repository policy, namespace, version, classifier, or network.

## 8. Configuring consumer Stub Runner to read with least privilege

Example `application-contract-test.yml` for **consumer CI**:

```yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: "https://repo.example.org/repository/maven-releases/"
        ids:
          - "com.acme.billing:payment-service:1.4.2:stubs"
        username: "${STUB_REPO_READ_USER}"
        password: "${STUB_REPO_READ_TOKEN}"
        fail-on-no-stubs: true
```

Explanation:

- `STUB_REPO_READ_USER` and `STUB_REPO_READ_TOKEN` are merely **environment variable names**, injected by the CI secret manager at test runtime.
- The corresponding account/token holds **read-only permission** for the required artifacts; never use a release publisher token.
- Stub Runner accepts `repository-root`, `ids`, `username`, and `password`; these property names are documented in SCC.
- `fail-on-no-stubs: true` prevents silently skipping when a required package is missing. It **is not** a complete repository ACL check.
- The YAML file contains **secret references**, not actual secret values.

**Operational note:** How the Spring test context is initialized, active profiles, or `@AutoConfigureStubRunner` annotations can override properties. After configuring, check that logs do not expose tokens, the exact artifact was downloaded, and the HTTP client calls the stub server.

### 8.1. Do not provide empty default secrets in release CI

A configuration like:

```yaml
username: "${STUB_REPO_READ_USER:}"
password: "${STUB_REPO_READ_TOKEN:}"
```

can cause the build to send empty strings if CI failed to inject secrets, leading to hard-to-diagnose errors or accidental anonymous access if the repository permits it. In pipelines requiring authentication:

- Do not supply empty defaults for required secrets.
- Check for the presence of environment variables **without printing their values**.
- Fail before running consumer tests if tokens are not injected.
- Keep enough logging to distinguish **missing credential** from **artifact not found**.

### 8.2. Annotations are alternative configuration, not password storage

```java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme.billing:payment-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/maven-releases/"
)
class CheckoutContractTest {
    // Read credentials from Spring test configuration/CI secrets.
}
```

**Never hardcode usernames/tokens into Java source or test annotations.** How annotations and Spring properties combine depends on version and precedence; when using both, verify the actual resolved configuration.

### 8.3. Consumer code must still be tested

A successful repository security test only proves **the stub can be downloaded**. Consumer contract testing must still invoke the **real PaymentHttpClient or CheckoutService** against the stub URL and assert agreed status/body/error semantics. Stub Runner read permission and behavioral compatibility are **two separate pieces of evidence**.


## 9. Maven producer: publishing stubs with a dedicated write identity

On the producer side, the SCC Maven plugin can generate tests, convert DSL into stubs, and attach `-stubs.jar` to the module's artifacts. After generated producer verification tests actually execute, Maven `deploy` publishes the attached artifacts per configuration.

**Distinguish POM from credentials:**

- `pom.xml` declares **repository IDs, URLs, and publishing configuration**.
- `settings.xml` belongs to the **build environment** or a CI-provisioned file, holding the corresponding **authentication**.
- The repository server decides **whether this identity is allowed to write to a specific path/namespace**.

### 9.1. Declaring the publishing target in the producer POM

`pom.xml` excerpt:

```xml
<project>
    <!-- Existing project, parent, and plugin declarations -->
    <groupId>com.acme.billing</groupId>
    <artifactId>payment-service</artifactId>
    <version>1.4.2</version>

    <distributionManagement>
        <repository>
            <id>internal-releases</id>
            <url>
                https://repo.example.org/repository/maven-releases/
            </url>
        </repository>
        <snapshotRepository>
            <id>internal-snapshots</id>
            <url>
                https://repo.example.org/repository/maven-snapshots/
            </url>
        </snapshotRepository>
    </distributionManagement>
</project>
```

This is an **explanatory excerpt**; do not paste it wholesale as a standalone POM if your project already has a different `project` and `distributionManagement` structure. The `repository.id`/`snapshotRepository.id` pair must **match the server id** in settings used during Maven `deploy`.

If `payment-service` releases version `1.4.2`, Maven normally selects `internal-releases`. If the version is `1.5.0-SNAPSHOT`, it uses `internal-snapshots` per plugin/repository policy. Do not provision a snapshot write token to a release job unnecessarily.

### 9.2. Maven `settings.xml` in CI

CI provides a settings file in a **secure workspace** or temporary home directory with environment placeholders:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.REPO_RELEASE_WRITE_USER}</username>
            <password>${env.REPO_RELEASE_WRITE_TOKEN}</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>${env.REPO_SNAPSHOT_WRITE_USER}</username>
            <password>${env.REPO_SNAPSHOT_WRITE_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven supports environment variable interpolation in `settings.xml`. These are **runtime references**, containing no real tokens. Secret values must be supplied by CI with separate scopes.

Key points to note:

- `<id>internal-releases</id>` **is not a username**; it is the key linking to the repository ID in the POM.
- Never commit a `settings.xml` containing real tokens into the repository.
- If CI writes a settings file containing rendered secrets, restrict read permissions and securely delete it after the job.
- Never print `settings.xml`, `effective-settings`, or environment variables containing secrets to logs.
- Use `-s` to point to the settings file when needed, but **never pass tokens directly on the CLI**.

Example build commands **after CI provides settings and credentials**:

```bash
./mvnw -s ci-settings.xml clean verify
./mvnw -s ci-settings.xml deploy
```

`ci-settings.xml` is an **illustrative name for a CI-provisioned file inside the job environment**, not a file to create in this lesson folder. In real projects, ensure **deploy** has a producer verification gate and is not bypassed by `skipTests` flags or custom plugin executions.

### 9.3. Maven server credentials do not control granted permissions

Even if Maven can authenticate as `internal-releases`, **repository ACLs** must still constrain that identity: publish only under `com/acme/billing/payment-service/**` or the permitted namespace/hosted repository, with no permission to delete arbitrary artifacts.

**Never grant Nexus/Artifactory admin privileges to fix a `403 Forbidden` error.** Inspect role scopes, repository/path rules, permitted upload methods, and release immutability policies.

### 9.4. Note on Maven password encryption

Maven 3 offers a **password encryption** feature for `server` entries, yet official documentation warns that Maven 3's mechanism provides **obfuscation-grade** protection and does not replace a secret manager or file permissions.

Therefore:

- Prefer CI secret stores/vaults and short-lived credentials where supported.
- Never treat `{...}` "encrypted" values in `settings.xml` as safe to commit to Git.
- Never share a single master password or `settings-security.xml` across all developers/jobs.
- Protect settings files and everywhere secrets can land: caches, logs, artifacts, and shell history.

## 10. Gradle producer: separating Maven publication from authentication

With Gradle, SCC creates the `verifierStubsJar` task to package mappings/DSL, while the `maven-publish` plugin publishes **artifacts declared in the publication**. These two steps must be connected in the build configuration.

Producer Groovy DSL `build.gradle` example, **excerpt**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract' version 'REPLACE_WITH_SCC_VERSION'
    id 'maven-publish'
}

group = 'com.acme.billing'
version = '1.4.2'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            // Stub artifact generated by Spring Cloud Contract.
            artifact(tasks.named('verifierStubsJar'))
        }
    }

    repositories {
        maven {
            name = 'internalReleases'
            url = uri(
                'https://repo.example.org/repository/maven-releases/'
            )

            // Gradle reads values from Gradle properties or
            // corresponding managed credential sources.
            credentials(PasswordCredentials)
        }
    }
}
```

With repository name `internalReleases`, Gradle looks for credential property names:

```text
internalReleasesUsername
internalReleasesPassword
```

Those properties **should not be stored with real values in a committed `gradle.properties`**. They can be supplied via CI secrets mapped into Gradle project properties, or using a credential provider suited to your infrastructure.

Example mapping **without writing values into source**:

```text
CI secret: REPO_RELEASE_WRITE_USER
    → Gradle property internalReleasesUsername

CI secret: REPO_RELEASE_WRITE_TOKEN
    → Gradle property internalReleasesPassword
```

This is a **conceptual mapping**, not environment variables automatically understood by Gradle without configuration. When using Gradle's project property environment convention, the corresponding names are `ORG_GRADLE_PROJECT_internalReleasesUsername` and `ORG_GRADLE_PROJECT_internalReleasesPassword`, depending on version/invocation.

### 10.1. If you want to read environment variables explicitly

An alternative inside `publishing.repositories.maven`:

```groovy
credentials {
    username = providers.environmentVariable(
        'REPO_RELEASE_WRITE_USER').orNull
    password = providers.environmentVariable(
        'REPO_RELEASE_WRITE_TOKEN').orNull
}
```

**Choose one consistent credential management mechanism**, rather than mixing multiple sources whose precedence is hard to audit. In release CI, fail when credentials are absent instead of falling back to anonymous publishing, plaintext HTTP, or an uncontrolled repository.

### 10.2. Enforce producer verification before publication

Example:

```groovy
tasks.named('publish') {
    dependsOn(tasks.named('contractTest'))
}

tasks.named('publishToMavenLocal') {
    dependsOn(tasks.named('contractTest'))
}
```

`contractTest` is the SCC Gradle plugin's producer test task; generated tests must actually execute. `verifierStubsJar` only builds the JAR and **does not mean verification has PASSED**.

Inspect the **task graph of your actual plugin version and release workflow**, as a job may invoke a specific publication task rather than the aggregate `publish`. To prevent bypassing the gate, apply dependencies/policies to **every publish task granted write privileges**, or provision write tokens only to a stage after mandatory checks.

### 10.3. Difference between `publish` and `publishToMavenLocal`

- `publish`: publishes Maven publications to configured repositories.
- `publishToMavenLocal`: installs publications into the user/build agent's local Maven repo.
- `verifierStubsJar`: only builds the stub JAR; **does not publish automatically**.
- `mavenLocal()` in dependency repositories: **reads** local Maven artifacts; **not a write command**.

**Never use a successful local publish to prove a remote repository has proper ACLs**; they are different targets with different permission paths.

## 11. Permissions by pipeline: PR, main, release, and consumer CI

A repository may have multiple workflows, yet **not every workflow needs a write token**.

| Pipeline | Responsibility | Granted credentials |
|---|---|---|
| Producer pull request | Generate contracts, tests, test build | Read-only dependencies/stubs if needed; **no release write** |
| Producer main snapshot | Verification + publish snapshot if policy permits | Write only to snapshot repo/namespace |
| Producer release tag | Verify, package, attest/sign, publish | Write to approved release repo/namespace |
| Consumer pull request | Download fixed stubs, run Stub Runner/tests | Read-only |
| Consumer release | Regression/compatibility matrix against stubs | Read-only |
| Repository maintenance | Retention, audit, key rotation | Admin identity only in maintenance workflows |

### 11.1. Untrusted PR code must not see write tokens

Build scripts and tests are executable code in CI. If an unreviewed pull request has access to write credentials:

- A modification to a Gradle/Maven build script can exfiltrate credentials.
- An uncontrolled dependency/plugin can read the runner environment.
- A modified job can publish artifacts before producer verification finishes.

**Never inject release write secrets into jobs running untrusted code**, including PRs from forks or internal branches lacking corresponding protection rules. Use protected environments, approval gates, and appropriate branch/tag conditions.

### 11.2. Separating build and publish stages

A secure pipeline can follow this flow:

```mermaid
flowchart TD
    PR["PR/code change"] --> VERIFY["Producer verification: no write token"]
    VERIFY --> QA{"Generated tests PASS and artifact valid?"}
    QA -- "No" --> FAIL["Build fails, no publish credential issued"]
    QA -- "Yes" --> APPROVE["Protected release approval/tag"]
    APPROVE --> PUB["Publish stage: narrowly scoped write identity"]
    PUB --> REPO["Immutable Maven release repository"]
    REPO --> CON["Consumer CI: read-only identity"]
    CON --> TEST["Stub Runner + consumer tests"]
```

Some CI platforms can issue **short-lived federated credentials** via OIDC/workload identity. Use them only when the repository or token broker natively supports them with identity/claim mapping policies; SCC does not provide this mechanism itself.

### 11.3. Do not confuse artifact publish rights with application deploy rights

An account permitted to run `mvn deploy` to a Maven repository **must not necessarily** have permission to deploy containers/apps to staging or production. Both workflows should have separate identities and approvals. Conversely, an application deployment account should not automatically hold permission to modify stub artifacts.

This prevents an incident on a consumer test runner from compromising the source of contract artifacts used in releases.

## 12. Artifact immutability: published packages must not mutate

Suppose consumer C1 is tested against:

```text
com.acme.billing:payment-service:1.4.2:stubs
SHA-256: <digest_of_approved_jar>
```

If the producer team republishes `1.4.2-stubs.jar` with different contents without bumping the version:

- One CI runner keeps the old cache while another downloads the new build.
- The same consumer commit can **PASS on machine A and FAIL on machine B**.
- A report saying "tested against 1.4.2" is insufficient to reproduce.
- Attestations/test reports signed for the old artifact no longer match the current file.

**Release repositories should block redeploying/overwriting identical coordinates** `groupId:artifactId:version:classifier`. That is a repository policy, not an `@AutoConfigureStubRunner` setting.

### 12.1. Snapshots differ from releases

`1.5.0-SNAPSHOT` is generally intended for active development and can publish multiple builds with timestamped snapshots depending on the Maven repository. Do not use mutable snapshots as long-term release evidence unless you record the resolved version/build metadata/checksum.

When testing a release candidate:

- Create an explicit release candidate version (e.g., `1.5.0-rc.1` per organization convention).
- Pin the artifact in consumer CI.
- Tie the artifact to its source commit and test report.
- Promote the release only after mandatory CI gates pass.

### 12.2. Verifying integrity differs from checking authorization

**Checksums** detect contents differing from a known digest; if an attacker has permission to replace both the JAR and the checksum in the same repository, checksums alone do not prove provenance.

**Digital signatures/attestations** raise verification assurance when signing keys, issuers, and policies are governed independently. A consumer/test pipeline must **actively verify** signatures/provenance against trust policies; simply having a `.asc` file next to the JAR does not make every tool verify signatures automatically.

**Repository access control** remains essential even with signatures, because it limits who can modify metadata/artifacts or disrupt distribution.

## 13. Dependency confusion, repository mirrors, and approved sources

A supply chain risk arises when a project requests `com.acme.billing:payment-service:1.4.2:stubs` while the resolver is allowed to search both public and internal repositories without clear source routing.

The goal is ensuring **internal namespaces resolve exclusively from approved internal repositories**, preventing a rogue artifact with matching coordinates elsewhere from taking precedence.

### 13.1. Controlling resolution paths

- Define repository allowlists in Maven settings, Gradle settings, or CI policies.
- Use organizational mirror/virtual/group repositories with explicit routing.
- In Gradle, use `content`/`exclusiveContent` filters where appropriate to bind internal groups.
- Pin plugin/dependency versions and protect plugin repositories too.
- Do not enable `mavenLocal()` unconditionally in release CI if the local repo could hold unverified artifacts.
- Log resolved artifact location, version, and checksum for auditing.

### 13.2. Example Gradle content filter

```groovy
repositories {
    maven {
        url = uri(
            'https://repo.example.org/repository/maven-internal/'
        )
        content {
            includeGroupByRegex('com\\.acme\\..*')
        }
    }
    mavenCentral {
        content {
            excludeGroupByRegex('com\\.acme\\..*')
        }
    }
}
```

This example illustrates **group filtering**, yet does not automatically block other paths if the project also declares repositories in settings, plugin management, or subprojects. Inspect the actual resolution configuration.

### 13.3. Never switch to plain HTTP URLs to fix TLS errors

If Gradle/Maven reports certificate or handshake errors, check the CA trust store, enterprise-approved TLS proxies, hostnames, certificate validity, or repository configuration. **Never use `allowInsecureProtocol=true` or disable SSL checks** on repositories holding critical artifacts/credentials just to make a build green.

## 14. Preventing secrets from leaking into artifacts, caches, and logs

A write token can leak outside POMs/build scripts via many places:

- Shell command-line arguments and process listings.
- Gradle `--info`/`--debug` or Maven `-X` if plugins/loggers fail to mask sensitive fields.
- CI environment dumps, `printenv`, `env`, `set`, stack traces.
- Gradle configuration cache, build cache, or CI workspace artifacts.
- Container layers when using `ARG`/`ENV` or `RUN echo ...` during image builds.
- `settings.xml` files saved as build artifacts, PR attachments, or test reports.
- Test fixtures/contract YAML containing real tokens.
- Browsers/dev tools/network traces accidentally capturing Authorization headers.

### 14.1. Secret handling principles

1. Fetch secrets from an approved secret manager/CI secret store.
2. Supply them **only to the exact job** after branch/protection conditions are met.
3. Prefer short-lived tokens, workload identities, and narrow scopes where supported.
4. Never print secret values, even when debugging 401 errors.
5. Never write them into outputs, Docker layers, or generated stub JARs.
6. Delete/revoke secrets according to job lifecycle; do not persist them on shared runners.
7. Rotate and revoke immediately if exposure is suspected.

### 14.2. Placeholders and real values

An illustrative contract may use:

```yaml
request:
  method: GET
  url: /api/payments/PAY-42
  headers:
    Authorization: "Bearer TEST_TOKEN_NOT_VALID_OUTSIDE_TEST"
response:
  status: 200
```

This is a **fake fixture granting no real privileges**. If you need to test token presence/format without pinning a value, use SCC's `request.matchers` or appropriate matcher DSL for your version. Never test by reusing a real production token.

### 14.3. Scanning before publishing

A CI policy can scan:

- Contract sources, generated mappings, and test resources.
- Stub JAR contents before publishing.
- Build logs/artifacts for absence of sensitive tokens/passwords/cookies.
- Maven POM/Gradle published metadata for absence of embedded credentials in URLs.

Secret scanning is imperfect; human review and synthetic data principles remain necessary.

## 15. Auditing, rotation, and revocation

**Granted access should never live indefinitely.** Periodic security reviews should check:

- The list of **service identities** with read/write access on each repository/namespace.
- Which identities have been unused for a long time and which services were retired.
- Whether any human accounts are shared with CI.
- Whether any write permissions exceed team boundaries.
- Whether delete/overwrite release permissions exist.
- Whether credentials have clear expiration/rotation policies and owners.
- Whether logs capture package/version/classifier, action, identity, timestamp, outcome, and source address per policy.

### 15.1. When a publish token is suspected leaked

A high-level response procedure:

1. **Revoke/disable the token** or affected workload identity.
2. Halt publishing from the affected job/identity and protect unverified artifacts.
3. Inspect audit logs for recent write/delete/overwrite operations.
4. Cross-check published artifacts against build provenance/checksums/signatures stored in an independent trusted source.
5. If any suspicious artifact is found, quarantine or mark it revoked per policy; notify consumers that downloaded it.
6. Issue a new least-privilege credential for the fixed pipeline.
7. Re-run producer verification and consumer matrix against verified artifacts.
8. Record the incident report, blast radius, and preventive measures.

**Never just change the password and assume artifacts already in the repository are safe.** If the token had write access, verify the integrity of versions written during the potentially compromised window.

### 15.2. When a read token is leaked

The primary risk is **unauthorized viewing/downloading of artifacts**. Revoke the token, inspect download logs, assess the sensitivity of exposed stubs, and notify per data policy. Never assume "test-only" stubs contain nothing worth protecting.

### 15.3. Rotation must not break every consumer CI

When rotating:

- Prepare the new credential and secret store mapping.
- Verify read-only access in a sandbox/test job.
- Update authorized workflows.
- Revoke the old credential after a managed transition window.
- Confirm jobs no longer use the old token and audits show no anomalous access.

Never create one shared token for every producer and consumer just to make rotation "easier". Separating identities by role limits the blast radius.


## 16. Distinguishing repository errors from HTTP contract errors

In consumer testing, there are **two completely separate HTTP paths**:

1. **Repository HTTP:** Stub Runner uses HTTP(S) to download `payment-service-1.4.2-stubs.jar` from the artifact repository.
2. **Stub API HTTP:** The consumer application's PaymentHttpClient calls the WireMock stub on `localhost:<port>` and receives `200`, `404`, `409`, etc. per contract.

```mermaid
flowchart TD
    C["Consumer test"] --> SR["Stub Runner"]
    SR -->|"HTTPS: resolve artifact"| REPO["Maven repository"]
    REPO -->|"JAR mappings"| SR
    SR --> W["WireMock HTTP server"]
    C --> PC["Real PaymentHttpClient"]
    PC -->|"HTTP: /api/payments/PAY-42"| W
    W -->|"200/404/409 per mapping"| PC
```

If the repository refuses to download the JAR, **the client does not yet have any stub to call**. Do not rush to edit `response.status: 404` in a YAML contract.

### 16.1. Error table read along the right path

| Symptom | Where is it? | First investigation |
|---|---|---|
| Repository **401 Unauthorized** | Artifact download | Missing/invalid credentials, expired token |
| Repository **403 Forbidden** | Artifact download/publish | Authenticated identity lacks path/action permission |
| Repository **404 Not Found** | Artifact download | Wrong GAV/classifier/version; some repos also **hide existence** from unauthorized users |
| Repository **409 Conflict** | Artifact publish | Duplicate version, immutable repo, or metadata conflict depending on product |
| Repository **429 Too Many Requests** | Download/publish | Rate limit, too many CI jobs, repository policy |
| TLS/certificate error | Repository connection | Trust store, CA, hostname, proxy |
| Stub Runner **no stubs found** | Loading JAR/mappings | Missing artifact, wrong layout, or no contracts |
| WireMock **404** after stub started | Client → stub | Unmatched request mapping **or** contract business 404 |
| Consumer **401/403** from WireMock | Client → stub | Auth contract behavior or test mapping, not Maven permissions |
| Maven/Gradle plugin resolution fail | Build-tool repository | Build plugin dependencies, separate from Stub Runner JAR resolution |

**Do not assume a repository 404 always means the artifact does not exist.** Some repository managers return 404 instead of 403 to avoid disclosing artifact existence; check policies and audit logs with the appropriate role.

### 16.2. Secret-safe debugging workflow

**Step A — Identify the failing path:** producer publish, consumer download, or consumer calling WireMock stub?

**Step B — Identify coordinates and repository:** groupId, artifactId, version, classifier, and host/repository URL *without credentials*.

**Step C — Identify identity (without printing tokens):** which read/write role was given to the job? Correct namespace and validity?

**Step D — Verify artifact metadata:** file/POM/classifier present, release immutability status, upload/download logs.

**Step E — Only after stubs download and load cleanly**, inspect WireMock mappings, HTTP port, and consumer behavior.

### 16.3. Do not use admin rights to "diagnose faster"

If a read-only token gets 403, testing with an admin token only confirms a higher-privileged account can read — **it does not explain which role policy is wrong** and risks exposing admin rights to the runner. Inspect repository ACLs/audits through a dedicated admin channel or use a **sandbox test identity** created for diagnostics.

## 17. CI protects both testing and artifact publication

A consumer test is trustworthy only when the pipeline connects this chain of evidence:

1. Contracts were reviewed against real consumer needs.
2. Producer verification **generated and ran real tests**, producing test reports.
3. The stub artifact was packaged with version/classifier and contains no real secrets.
4. The repository accepts publishes **only from authorized identities**.
5. Release artifacts cannot be overwritten after publication.
6. Consumers can **only read** specific artifacts and Stub Runner loads the right mappings.
7. Consumer tests invoke real client code and assert required behaviors.
8. Audit/provenance records suffice to reproduce and investigate regressions.

### 17.1. Overall pipeline model

```mermaid
sequenceDiagram
    participant P as Producer CI - no write secret
    participant V as Verification gate
    participant PUB as Protected publish job
    participant R as Artifact repository
    participant C as Consumer CI - read-only

    P->>V: Generate + execute contract tests
    V-->>P: PASS/FAIL + report
    P->>V: Scan stub JAR + provenance
    V-->>PUB: Approved artifact + release metadata
    PUB->>R: Publish exact version with scoped credential
    R-->>PUB: Accepted + artifact identity
    C->>R: Read pinned group:artifact:version:stubs
    R-->>C: Stub JAR
    C->>C: Stub Runner + consumer code tests
```

**This is a reference CI architecture**, not an SCC-generated workflow. Separating build and publish stages must ensure **the published artifact is the exact artifact that was tested**; if the publish job rebuilds from a different source commit, test→release traceability is broken.

### 17.2. Publication gates

| Gate | Passing condition |
|---|---|
| Branch/commit protection | Only approved release tags/commits can trigger publish |
| Producer contract tests | Not skipped; expected number of tests actually ran |
| Stub packaging | Correct mappings/contracts/classifier present |
| Secret scan | No real credentials/sensitive data inside artifact |
| Artifact identity | GAV/version/classifier match release metadata |
| Repository authorization | Write identity restricted to allowed namespace/repo |
| Immutability | Cannot overwrite existing release coordinates |
| Consumer read | Read identity loads exact stub, holds no write rights |
| Consumer compatibility | HTTP/message client tests execute through Stub Runner |
| Auditability | Traceable from commit and test report to distributed artifact |

Not every gate needs to be a separate service, yet **skipping a gate must be an explicit, reasoned decision**, not silent pipeline omission.

### 17.3. "Publish successful" does not prove consumers can read

Producer CI may upload an artifact cleanly while consumer CI still hits 401/403 due to missing read rights, blocked routes, or different namespace ACLs. After publishing, perform a **read-side smoke test** using a **consumer-like identity** in an appropriate environment.

Conversely, a consumer reading a JAR does not prove producer verification passed if the publisher lacked a release gate. Keep both layers of evidence separate.

## 18. When to use public, internal, or partner-dedicated repositories?

Not all stubs have the same sensitivity.

| Contract/stub type | Typically suitable policy |
|---|---|
| Public API, payloads entirely synthetic | Can be published publicly after security review and license policy check |
| Internal API between microservices | Hosted repository with read access only for granted identities |
| API with sensitive business schemas | Restricted per team/project; inspect mappings for disclosed details |
| Partner API | Dedicated repository/namespace, scoped/expiring read tokens, rotation schedule |
| Contracts with highly sensitive data | **Remove sensitive data first**; ACLs do not replace redaction |

**Never use a private repository as an excuse to embed real tokens** or copy production payloads into contracts. Data inside `-stubs.jar` can still be cached, downloaded, and copied into test reports and logs across many machines.

### 18.1. Partners may only read, never publish producer artifacts

If an external partner needs to test a client against stubs:

- Provide the approved artifact version via an appropriate repository/download channel.
- Issue read credentials scoped to the artifact/repo as needed.
- Never grant write/delete rights even if the partner only "wants to re-upload a file when a test fails".
- When a partner proposes a new contract, use a PR/review/contract-proposal flow; the producer verifies and publishes its own stub.

Protecting the publisher identity preserves clear accountability for **who commits to which API behavior**.

## 19. Verifying permissions through "positive" and "negative" tests

A sound security setup not only tests that permitted actions succeed, but also verifies that **unauthorized actions are rejected**.

### 19.1. Sandbox test scenarios

Create a test repository **containing no production artifacts**, with similar identities and ACLs:

```text
Sandbox repo:
  maven-sandbox-releases

Identity A: payment-publisher
  allow: read/write namespace com.acme.billing
  deny: delete/overwrite release, write com.acme.catalog

Identity B: checkout-consumer
  allow: read com.acme.billing
  deny: write/delete

Identity C: unauthenticated
  allow: none (if private repo)
```

Scenarios to run using organization-approved tools/clients:

| Step | Actor | Action | Expected result |
|---|---|---|---|
| 1 | Payment publisher | Upload stub `1.4.2` in granted namespace | **ALLOW** |
| 2 | Checkout consumer | Download the same package | **ALLOW** |
| 3 | Checkout consumer | Attempt to publish a **dummy sandbox package** | **DENY** |
| 4 | Payment publisher | Upload to inventory namespace | **DENY** |
| 5 | Payment publisher | Redeploy the same release version | **DENY** |
| 6 | Anonymous client | Read private package | **DENY** |
| 7 | Revoked identity | Read/push artifact after revocation | **DENY** |

**Never instruct or execute deleting/overwriting production artifacts to test ACLs.** Negative tests must run in an authorized sandbox using purely dummy data.

### 19.2. Limitations of permission tests

- A single negative DENY test does not replace a full repository security audit.
- ACLs can behave differently across virtual/group repositories versus hosted repositories.
- Tokens may remain valid briefly during post-revocation propagation delays.
- Group-level read permissions may change when adding a Maven mirror.
- Tests must log **identity class/action/path/result**, never secrets.

## 20. Hands-on exercise: access control for payment and inventory stubs

### 20.1. Context

An organization has two producers and one consumer:

| Service | Stub coordinates | Role |
|---|---|---|
| `payment-service` | `com.acme.billing:payment-service:2.3.1:stubs` | Payment producer |
| `inventory-service` | `com.acme.catalog:inventory-service:4.0.0:stubs` | Inventory producer |
| `checkout-service` | Needs to read both artifacts | Consumer using Stub Runner |

Repositories:

```text
https://repo.example.org/repository/maven-releases/
https://repo.example.org/repository/maven-snapshots/
```

Three required identities:

```text
payment-release-publisher
inventory-release-publisher
checkout-consumer-reader
```

### 20.2. Tasks

1. Build a read/write/delete/overwrite/admin role matrix for the three identities and two namespaces.
2. Explain why `checkout-consumer-reader` does not need a write token.
3. Design a producer CI release stage that supplies `payment-release-publisher` only after generated producer tests PASS.
4. Write `distributionManagement` in `payment-service/pom.xml` and `settings.xml` using **environment references** without real tokens.
5. Write `publishing.repositories.maven` for a Gradle producer with CI-provisioned publisher credentials.
6. Write `application-contract-test.yml` so Stub Runner reads **both stub artifacts** via `REMOTE`.
7. Explain how to guarantee checkout's real HTTP client calls the WireMock ports rather than the production producer.
8. Design sandbox negative tests: consumer write denied, payment publisher writing to inventory namespace denied, release redeploy denied.
9. Explain the difference between a repository `403` and a WireMock `404`.
10. If a publisher token leaks, outline steps for revocation, auditing, verifying artifact integrity, and restoring CI.
11. If the same stub version shows two different checksums on two runners, explain the risk and remediation policy.
12. Show how CI records commit, test report, GAV/classifier, checksum, publisher identity, and consumer test results.
13. Propose permission limits for an external partner who only needs to read one artifact.
14. Explain how to block untrusted PR CI from accessing release tokens.
15. Explain why an artifact checksum downloaded from the same repository is insufficient to prove publisher identity if an attacker can replace both JAR and checksum there.

### 20.3. Suggested consumer YAML

```yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: "https://repo.example.org/repository/maven-releases/"
        ids:
          - "com.acme.billing:payment-service:2.3.1:stubs"
          - "com.acme.catalog:inventory-service:4.0.0:stubs"
        username: "${STUB_REPO_READ_USER}"
        password: "${STUB_REPO_READ_TOKEN}"
        fail-on-no-stubs: true
```

This is a **sample configuration** when a single read identity is permitted to download from both namespaces. If your organization forbids one identity from reading both, design repository access and CI test jobs accordingly; do not put two username/password pairs into one Stub Runner config and expect per-artifact selection.

### 20.4. Suggested token policy rules

```text
ALLOW payment-release-publisher:
  upload com/acme/billing/** to releases
DENY payment-release-publisher:
  upload com/acme/catalog/**, delete/overwrite releases

ALLOW inventory-release-publisher:
  upload com/acme/catalog/** to releases
DENY inventory-release-publisher:
  upload com/acme/billing/**, delete/overwrite releases

ALLOW checkout-consumer-reader:
  read approved billing/catalog stubs
DENY checkout-consumer-reader:
  upload/delete/overwrite any artifact

DENY untrusted pull request:
  access release write credential
```

**This is policy pseudocode**, not ACL syntax you can paste verbatim into Nexus or Artifactory. Implementers must map it to their repository product's specific permissions, especially where artifact paths/classifiers cannot be separated by group-level roles alone.

### 20.5. Self-assessment criteria

A solution succeeds when:

- Read and write identities are clearly separated with least privilege.
- The publish path accepts packages only after the producer verification gate.
- Consumer uses `REMOTE`, pinned versions, and no insecure fallbacks.
- Secrets never appear in source, logs, artifacts, or CI caches.
- Sandbox DENY tests prove consumers have no write access.
- Artifacts cannot overwrite existing release coordinates.
- Tests ensure only verified stubs get published.
- CI maintains audit/provenance and a revoke/rotate plan.
- The learner clearly distinguishes **repository access control** from **HTTP API contract behavior**.

## 21. Checklist before merging, publishing, or granting permissions

- [ ] Contracts use synthetic data; contain no real tokens/cookies/passwords.
- [ ] Producer verification tests actually execute, not skipped or silently `0 tests`.
- [ ] Stub JAR and POM have correct version/classifier and valid mapping/DSL layout.
- [ ] Every release artifact originates from a verified commit/build.
- [ ] Repository URL is allowlisted and uses HTTPS with certificate validation.
- [ ] Release and snapshot repositories have separate permissions and rules.
- [ ] No anonymous **write**; anonymous read only when data is approved public.
- [ ] Consumer CI uses a read-only identity with no release write secrets.
- [ ] Producer release publisher writes only to its granted namespace/repository.
- [ ] PR CI cannot access release tokens.
- [ ] Tokens come from CI secrets/vaults, never hardcoded in POM/Gradle/YAML.
- [ ] Settings files, Gradle caches, and logs do not leak credentials.
- [ ] Repository admin rights are never granted to build jobs just to fix 401/403 errors.
- [ ] Repository blocks redeploying/overwriting immutable release coordinates.
- [ ] CI checks checksums/signatures/provenance proportional to risk.
- [ ] Internal group namespaces cannot resolve from untrusted public repositories.
- [ ] Consumer Stub Runner `ids` pin versions, `repositoryRoot` is right, and `failOnNoStubs` is not carelessly disabled.
- [ ] Real consumer HTTP client calls WireMock stub URLs, not the real producer.
- [ ] READ/WRITE/DENY permissions are verified in a sandbox.
- [ ] Audit logs record actions and identities per policy without secrets.
- [ ] Owner/token expiry/rotation plans, revocation workflows, and incident response exist.
- [ ] Historical release artifacts are never deleted outside approved retention policies.
- [ ] External partners only hold read rights to approved shared artifacts.
- [ ] Repository auth errors are classified separately from HTTP contract errors.
- [ ] Test reports and provenance suffice to reproduce a consumer compatibility run.

## 22. Key takeaways and references

**Protecting read and write access to the artifact repository** means protecting **the trust chain from the producer's contracts to the stubs the consumer actually runs**.

- SCC generates producer tests, mappings, and stubs, yet **does not automatically configure ACLs** for Nexus/Artifactory.
- **Producer publishers** need narrow write privileges granted only after CI verification passes.
- **Consumer Stub Runner** needs minimal read privileges to fetch exact `groupId:artifactId:version:stubs`.
- Maven `distributionManagement`/`settings.xml` and Gradle `maven-publish`/credentials handle **repository authentication**, without replacing repository authorization policies.
- **Release immutability, TLS, provenance, secret management, auditing, and rotation** reduce the risk of stub tampering or credential leaks.
- A passing consumer test is only as valid as the stub artifact actually loaded; you need its version, checksum, and the generated producer tests that verified it.
- **Repository errors `401/403/404` differ from WireMock stub HTTP statuses** during business contract testing.

### Official documentation

- [Spring Cloud Contract — Stub Runner Core: CLASSPATH, LOCAL, REMOTE and JAR downloading](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html).
- [Spring Cloud Contract — Stub Runner Common Properties: username, password, repositoryRoot, IDs](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html).
- [Spring Cloud Contract — Configuration Properties: fail-on-no-stubs and options](https://docs.spring.io/spring-cloud-contract/reference/configprops.html).
- [Spring Cloud Contract — Maven Project and producer verifier](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html).
- [Spring Cloud Contract — Gradle Project and verifierStubsJar](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html).
- [Apache Maven — Settings Reference: servers and interpolation](https://maven.apache.org/settings.html).
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html).
- [Apache Maven — Password Encryption: warnings about Maven 3 encryption](https://maven.apache.org/guides/mini/guide-encryption.html).
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html).
- [Gradle — Supported Repository Protocols: credentials and authentication](https://docs.gradle.org/current/userguide/supported_repository_protocols.html).
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html).

**Final note:** Namespace/path permissions, artifact immutability, workload identities, logging, and retention are **policies of your repository/CI platform**, not features Spring Cloud Contract turns on automatically when you add `@AutoConfigureStubRunner`. Configure and verify those policies independently alongside your contract tests.
