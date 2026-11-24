# Building Once and Promoting the Exact Verified Artifact Across Environments

A reliable CI/CD pipeline creates **one tested build**, stores it as an immutable artifact, and promotes that exact artifact across Development, Staging, and Production. Every environment receives the exact same JAR/WAR or the exact same OCI image digest; only runtime configuration, secrets, endpoints, resources, and deployment permissions change per environment.

That is the principle of **Build once, promote many**.

For example, CI builds a Spring Boot service from Git commit `a83f1c2` into:

~~~text
Artifact: orders-api-1.8.0.jar
SHA-256:  <actual digest computed by CI>
Source:   a83f1c2
Build:    run-4821
~~~

Once tests and security checks pass, the artifact enters a repository. Development, Staging, and Production all download this exact artifact, verify its checksum/signature, and deploy it. The pipeline **never re-runs Gradle or Maven to produce a different JAR per environment**.

For containers, the idea is the same: build the image once, push it to a registry, record its digest, and deploy the exact same reference `registry/team/orders-api@sha256:...` across each environment.

## 1. Why Build Once?

An error-prone process builds separately for each environment:

~~~text
Source commit
   |
   +--> Build for Development --> orders-api.jar (A)
   |
   +--> Build for Staging -----> orders-api.jar (B)
   |
   +--> Build for Production --> orders-api.jar (C)
~~~

Even from the same branch or version string, three separate builds can pick up different dependencies, plugins, JDKs, generated timestamps, or environment variables. Consequently, A, B, and C do not necessarily contain identical bytes. If Staging tested A yet Production runs C, you have not actually deployed the tested binary.

The build-once workflow:

~~~text
                Git commit
                    |
                    v
             Build + test once
                    |
                    v
             Package artifact
                    |
                    v
        Verify + checksum + signature
                    |
                    v
        Immutable artifact repository
                    |
          +---------+----------+
          |         |          |
          v         v          v
       Dev deploy  Stage     Production
          |         |          |
          +---------+----------+
          Same artifact bytes / image digest
~~~

Benefits:

- **Consistency:** the binary tested in Staging is the exact binary promoted to Production.
- **Traceability:** you know which commit, workflow run, and toolchain built the artifact.
- **Accurate rollback:** redeploy a known version or digest.
- **Change control:** only configuration and environment state differ.
- **Less drift:** building per environment cannot accidentally create diverging artifacts.
- **Clear auditing:** each promotion tracks approver, timestamp, environment, and digest.

### What Is an Artifact?

An artifact is **the packaged output of a build**, such as:

- An executable Spring Boot JAR or WAR.
- An OCI container image.
- A distribution archive/ZIP containing the application and required files.
- Associated metadata such as checksums, signatures, SBOMs, and provenance.

Source code, Gradle caches, Maven local repositories, and container build caches are **not** release artifacts delivered to deployment environments. A release record can reference multiple files, yet must clearly designate which file is the deployable artifact.

## 2. Distinguishing Build, Verify, Publish, Promote, and Deploy

| Stage | Activity | Output / Exit Criteria |
| --- | --- | --- |
| Build | Check out exact commit, resolve dependencies, compile, package | Fresh JAR/WAR or OCI image |
| Verify | Unit/integration tests, dependency checks, checksums, signatures, scans | QA results and verification evidence |
| Publish | Push verified artifact to a repository or registry | Retrievable version or digest |
| Promote | Authorize the exact same artifact for the next environment | Promotion status and approval |
| Deploy | Install/run the artifact in the target environment | Running instances/containers matching exact digest |
| Validate | Smoke tests, health checks, contract/monitoring checks | Post-deployment verification results |

**Publish and deploy are not the same action.** Publishing stores an artifact in a repository for retrieval; deploying rolls an artifact out into a running environment. Maven's `deploy` phase publishes artifacts to a remote repository—it does not deploy an application to Production by default.

**Promoting is not rebuilding either.** With a repository manager, promotion may move a staging repository to release status, change visibility, or attach metadata. With an OCI image, it may add a new tag pointing to the exact same image digest. In both cases, artifact bytes remain unchanged.

## 3. What Stays Identical vs. What Varies by Environment?

| Element | Identical Across Environments? | Examples |
| --- | --- | --- |
| JAR/WAR bytes | Yes | `orders-api-1.8.0.jar` |
| OCI image digest | Yes | `sha256:...` |
| Maven GAV / release version | Yes | `com.example:orders-api:1.8.0` |
| Git commit / build provenance | Yes | `a83f1c2` / run 4821 |
| Spring profile | May differ | `development`, `staging`, `production` |
| Database URL | May differ | Each environment's DB |
| Credentials / API tokens | May differ | Environment-scoped secret store |
| Feature flags | May differ | Gradual feature rollouts |
| CPU / RAM / replica count | May differ | Resource limits and autoscaling |
| Deployment approval | May differ | Production requires reviewers |

### Externalize Runtime Configuration Outside the Binary

Spring Boot reads configuration from environment variables, external config files, Config Server, Kubernetes ConfigMaps/Secrets, or secret managers.

Example running the exact same JAR with different profiles:

~~~bash
java -jar orders-api-1.8.0.jar --spring.profiles.active=staging
~~~

~~~bash
java -jar orders-api-1.8.0.jar --spring.profiles.active=production
~~~

Both commands use **the exact same JAR file**; the Spring Environment activates different profiles. For containers, you can pass:

~~~bash
docker run -e SPRING_PROFILES_ACTIVE=staging registry.example.test/team/orders-api@sha256:...
~~~

`registry.example.test` and the digest are illustrative placeholders; substitute your real registry and reference.

Never bake database passwords, API keys, tokens, or private certificates into a JAR or image. Inject them at runtime from an audited, access-controlled secret store.

### Never Use Build Profiles to Produce Environment-Specific Binaries

Distinguish clearly:

- **Spring runtime profiles:** select configuration when the application starts.
- **Maven build profiles / Gradle project properties:** can alter dependencies, resource filtering, compiler options, or artifact contents at build time.

If `-Pproduction` makes Maven/Gradle package a different JAR than `-Pstaging`, the pipeline has produced distinct artifacts. Use runtime configuration for endpoints, credentials, and feature flags; keep release build inputs uniform.

Values that genuinely must be resolved at build time (such as compile targets, native binaries, or static frontend bundles) require explicit policies. If artifacts depend on platform/architecture, build one explicit artifact per target and promote each matching artifact rather than silently rebuilding per environment.

## 4. Versions, Checksums, and Build Identity

A release should have **one stable identifier** along with evidence of its origin.

~~~text
Product:             Orders API
Artifact:            orders-api-1.8.0.jar
Coordinates:         com.example:orders-api:1.8.0
Git commit:          <full commit in CI>
Build run:           4821
JDK:                 <actual version>
Gradle:              <Wrapper version>
SHA-256:             <digest computed from file>
Signature:           <signature/key identity if applicable>
SBOM:                <file/reference if applicable>
Built at:            <UTC timestamp>
~~~

Values in angle brackets must be populated from the real build system, never fabricated.

### Versions Must Be Immutable

Use a unique release version, such as `1.8.0`. Release repositories should be configured **to forbid overwriting existing coordinates** with new bytes. Never rebuild and republish a different artifact under the same `com.example:orders-api:1.8.0`.

Avoid `SNAPSHOT`s, dynamic dependency versions, and `latest` tags for promotable releases. If release candidates take multiple attempts, assign distinct build IDs or release-candidate versions, and promote only one verified candidate.

### SHA-256 Verification on Download

After building:

~~~bash
sha256sum orders-api-1.8.0.jar > SHA256SUMS
~~~

After downloading the artifact in another environment:

~~~bash
sha256sum --check SHA256SUMS
~~~

When the checksum matches, the downloaded file contains identical bytes to the hashed file. However, if an attacker can replace both the JAR and checksum in an untrusted store, both files could still match. For critical releases, retrieve manifests/checksums from a protected source, verify signatures or provenance, and enforce repository write controls.

### Signatures and Provenance

- **Checksum:** verifies bytes match an expected digest.
- **Digital signature:** verifies data was signed by a trusted key/identity.
- **Build provenance/attestation:** records source, builder/workflow, and build creation details.
- **SBOM:** inventories software components inside the artifact/image.

No single layer fully replaces the others. A valid signature does not mean the artifact lacks CVEs; having an SBOM does not prove the source commit was built properly. Apply layered policies and retain verification outcomes.

## 5. Making the Initial Build Controlled and Traceable

Build-once ensures environments share the same artifact. It **differs from reproducible builds**:

- **Build once, promote many:** never rebuild the artifact while moving across environments.
- **Reproducible build:** an independent party/machine can rebuild from identical source, environment, and instructions to obtain identical bytes.

Reproducibility is stronger proof of process repeatability. Even before achieving bit-for-bit reproducibility, a pipeline can still promote the exact built artifact safely when storage and integrity checks are enforced properly.

### Pinning Build Inputs with Gradle

- Commit the Gradle Wrapper and pin its version.
- Declare the Java toolchain explicitly.
- Pin plugin versions.
- Use dependency locking on relevant configurations.
- Use dependency verification metadata when checking checksums/signatures.
- Restrict dynamic/changing dependencies in releases.
- Never let builds depend on uncontrolled environment inputs.

Example enabling dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Generate/update lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit lockfiles to version control after review. Locking pins resolved versions, yet does not guarantee identical artifact bytes across every repository; pair it with dependency verification.

Refer to [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) and [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

### Pinning Build Inputs with Maven

- Commit the Maven Wrapper if the project uses one.
- Pin plugin/dependency versions and manage parent/BOM explicitly.
- Avoid version ranges and changing snapshots in releases.
- Use dependency convergence and enforcer rules where appropriate.
- Set reproducible archive timestamps and use plugin versions supporting reproducible builds.
- Record actual JDK, Maven, and OS/platform in the build record.

Maven provides `project.build.outputTimestamp` to support reproducible builds:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

This is a fixed illustrative timestamp; real projects pick values per release policy. Setting the timestamp alone is insufficient: plugins and other build inputs must also support reproducibility.

See [Maven Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html).

### Testing the Exact Releasable Artifact

Run checks before publishing:

1. Compilation and unit tests.
2. Integration tests against required dependencies.
3. Packaging the executable JAR/WAR or image.
4. Smoke-testing the packaged artifact itself, not only class files in the test task.
5. Dependency, security, and license scans per policy.
6. Checksums, signatures, and provenance.
7. Storing the artifact with metadata in an immutable store.

Post-package tests catch issues unit tests miss, such as missing resources, broken manifests, or unpackaged runtime dependencies.

## 6. Gradle Hands-On: Publishing an Executable Spring Boot JAR Once

Example using Java 17 and the Spring Boot Gradle plugin. The goal is creating `orders-api-1.8.0.jar`, testing it, and publishing that exact file to a Maven-compatible repository.

### 6.1. Configuring `build.gradle`

~~~groovy
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'maven-publish'
}

group = 'com.example'
version = providers.gradleProperty('releaseVersion').getOrElse('0.0.0-dev')

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName.set('orders-api-' + project.version + '.jar')
}

publishing {
    publications {
        app(MavenPublication) {
            groupId = project.group.toString()
            artifactId = 'orders-api'
            version = project.version.toString()
            artifact(tasks.named('bootJar'))
        }
    }

    repositories {
        maven {
            name = 'releaseRepo'
            url = uri(providers.gradleProperty('releaseRepoUrl').getOrElse(
                layout.buildDirectory.dir('staging-repo').get().asFile.toURI().toString()
            ))
            credentials(PasswordCredentials)
        }
    }
}
~~~

Key details:

- `releaseVersion` comes from the release tag/CI, never from an environment name.
- `bootJar` produces the executable archive; the publish task publishes that exact task output as the publication artifact.
- Maven publication coordinates are `com.example:orders-api:1.8.0` when version is `1.8.0`.
- `releaseRepo` is the target repository. Gradle resolves credentials by repository name from `releaseRepoUsername` and `releaseRepoPassword` properties.
- In CI, pass credentials via environment properties such as `ORG_GRADLE_PROJECT_releaseRepoUsername` and `ORG_GRADLE_PROJECT_releaseRepoPassword`. Never commit passwords into `gradle.properties`.
- The repository URL falls back to a local staging folder for convenient testing; real release jobs must pass the managed repository URL.

This example publishes the executable Boot JAR as **a deployable distribution file**. It does not declare `from components.java` like a standard library; consumers must not treat this publication as an API library with a full dependency graph for compile classpaths.

### 6.2. Build, Test, and Publish Strictly Once

From the project root:

~~~bash
./gradlew clean test bootJar -PreleaseVersion=1.8.0
~~~

Verify the file:

~~~text
build/libs/orders-api-1.8.0.jar
~~~

Compute checksum:

~~~bash
cd build/libs
sha256sum orders-api-1.8.0.jar > SHA256SUMS
~~~

After build and tests pass, publish:

~~~bash
cd ../..
./gradlew publish -PreleaseVersion=1.8.0 -PreleaseRepoUrl=https://repo.example.test/releases
~~~

In CI, credentials are supplied via the environment properties noted above. `repo.example.test` is an example hostname, not a real repository.

Gradle Maven Publish generates publish tasks matching declared publications and repositories. `publish` publishes declared publications to declared repositories. To avoid accidentally building a different artifact, the release pipeline should use the exact commit, version, and QA-verified build output rather than running separate builds per environment.

Documentation: [Gradle Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html).

### 6.3. Promotion and Deployment

The repository may hold:

~~~text
com/example/orders-api/1.8.0/
    orders-api-1.8.0.jar
    orders-api-1.8.0.pom
    checksums/signatures (if configured)
~~~

Development downloads `com.example:orders-api:1.8.0`, verifies its checksum, and deploys. Once verified, Staging and Production pull **the exact same release coordinates and bytes** from the repository.

If your repository manager provides a staging/promote workflow, promote the repository/metadata using that product's native mechanism. Never rebuild and overwrite version `1.8.0`.

## 7. Maven Equivalent: Deploying an Artifact Once

In Maven, the `deploy` phase of the default lifecycle publishes final artifacts to a remote repository. `mvn clean deploy` runs preceding phases in order: `validate`, `compile`, `test`, `package`, `verify`, `install`, then `deploy`. It does not deploy the app to Production servers. [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).

### 7.1. Declaring the Target Repository in the POM

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.test/maven/releases</url>
    </repository>
</distributionManagement>
~~~

This belongs inside `pom.xml`. Matching credentials are placed in Maven `settings.xml` under the same server ID:

~~~xml
<settings>
    <servers>
        <server>
            <id>internal-releases</id>
            <username>USERNAME_FROM_SECRET_STORE</username>
            <password>PASSWORD_FROM_SECRET_STORE</password>
        </server>
    </servers>
</settings>
~~~

This structure is illustrative; never commit real credentials to source control. CI generates/supplies secure settings from a secret manager or native credentials mechanism.

### 7.2. Build and Publish Once

~~~bash
mvn clean verify deploy
~~~

Once finished, the artifact resides in the remote Maven repository under the declared GAV. Downstream deployment jobs download that exact release version from the repository; **never re-run `mvn package` or `mvn deploy` per environment**.

The Maven Deploy Plugin also offers `deploy:deploy-file` to upload a file built elsewhere. When using this goal, pass the exact file, GAV, and repository; never rebuild a fresh artifact just to change deployment targets. See [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html).

### 7.3. Maven Configuration Must Not Alter the Artifact per Environment

Do not create `dev`, `staging`, and `prod` Maven profiles that swap dependencies, filter resources differently, or bake credentials into the JAR if your goal is promoting one binary. Use Spring runtime profiles or external configuration for per-environment differences.

## 8. Container Images: Promoting by Digest Instead of Tags Alone

When packaging applications as OCI images, image tags are human-friendly:

~~~text
registry.example.test/team/orders-api:1.8.0
~~~

However, tags can be reassigned to a different image if registry policies allow it. **A digest is a content-addressed identifier** for the image contents. Docker supports pulling images by digest to pin an exact image version. [Docker pull by digest](https://docs.docker.com/reference/cli/docker/image/pull/).

After building and pushing an image once:

~~~bash
docker push registry.example.test/team/orders-api:1.8.0
~~~

The registry/CLI returns the digest of the pushed image. Record that real value in the release record, e.g.:

~~~text
registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

Deploy the exact same reference across environments:

~~~bash
docker pull registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

In Kubernetes, a Deployment's `image` field can also reference the digest directly, for example:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-api
          image: registry.example.test/team/orders-api@sha256:<actual-digest>
~~~

`<actual-digest>` is a placeholder that must be replaced with the real digest. Never commit a fabricated digest into production manifests.

### When Using Spring Boot Cloud Native Buildpacks

You can build OCI images directly from executable archives via `bootBuildImage` or Maven `spring-boot:build-image`. Point the image name at your registry and enable publishing per policy when pushing. Once pushed, capture the digest from output/registry and use that digest across every environment.

Never re-run Buildpacks with different tags/environments per stage when the requirement is running one identical image. If you wish to attach tags like `staging` or `production`, those tags must point to **the exact same digest**.

### Tags Are Not Digests

~~~text
orders-api:1.8.0       -> readable name, can be retagged
orders-api@sha256:...  -> reference to exact content
~~~

Use tags to locate artifacts and display releases; use digests for exact verification and deployment. After every push, record the digest returned by the registry—do not compute a digest by hashing a tar export that does not equal the registry manifest digest.

## 9. GitHub Actions: Build Once, Three Environments Use the Same Artifact

The following example illustrates a workflow for release tag `v1.8.0`:

- The `build` job runs tests and builds the JAR **once**.
- Uploads one workflow artifact named after the Git commit.
- Development, Staging, and Production sequentially download that exact workflow artifact.
- Each job verifies SHA-256 before invoking the deploy script.
- GitHub Environments can enforce required reviewers for Staging/Production.

Action versions in this example are major tags published in GitHub documentation at writing time: checkout v7, setup-java v6, upload-artifact v7, and download-artifact v8. For strict supply-chain control, pin each action to a reviewed full commit SHA instead of major tags alone.

### 9.1. Workflow File

Create `.github/workflows/release.yml`:

~~~yaml
name: Build once and promote

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.meta.outputs.version }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - id: meta
        shell: bash
        run: |
          RELEASE_VERSION="$(printf '%s' "$GITHUB_REF_NAME" | sed 's/^v//')"
          echo "version=$RELEASE_VERSION" >> "$GITHUB_OUTPUT"

      - name: Build and test once
        run: |
          ./gradlew --no-daemon clean test bootJar \
            -PreleaseVersion="${{ steps.meta.outputs.version }}"

      - name: Create checksum manifest
        env:
          RELEASE_VERSION: ${{ steps.meta.outputs.version }}
        run: |
          cd build/libs
          sha256sum "orders-api-$RELEASE_VERSION.jar" > SHA256SUMS

      - name: Upload immutable release artifact
        uses: actions/upload-artifact@v7
        with:
          name: orders-api-${{ github.sha }}
          path: |
            build/libs/orders-api-*.jar
            build/libs/SHA256SUMS
          if-no-files-found: error
          retention-days: 30

  deploy-development:
    needs: build
    runs-on: ubuntu-latest
    environment: development

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment development \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"

  deploy-staging:
    needs: deploy-development
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment staging \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: orders-api-${{ github.sha }}
          path: release

      - name: Verify downloaded artifact
        working-directory: release
        run: sha256sum --check SHA256SUMS

      - name: Deploy the same JAR
        env:
          RELEASE_VERSION: ${{ needs.build.outputs.version }}
        run: |
          ./ci/deploy.sh \
            --environment production \
            --artifact "release/orders-api-$RELEASE_VERSION.jar"
~~~

### 9.2. What This Workflow Guarantees

- Only the `build` job runs Gradle to produce the JAR.
- Deploy jobs download the artifact named after the exact same `github.sha` and workflow run.
- Each environment recomputes SHA-256 and checks it against the manifest uploaded alongside the artifact.
- Jobs run sequentially via `needs`.
- `environment` isolates configuration and deployment permissions per environment.
- The deploy script receives the downloaded JAR; it must never invoke Gradle or Maven again to rebuild the artifact.

`./ci/deploy.sh` is **a project-specific integration script** that must be implemented to copy/deploy the exact passed file and read runtime config from the environment. This sample workflow cannot deploy to a real system until that script and connection details are configured.

### 9.3. Setting Up Approval for Production

In GitHub repository settings, create Environments:

- `development`
- `staging`
- `production`

Configure Required reviewers for Production and appropriate protection rules. GitHub supports required reviewers, wait timers, and protection rules for environment deployment jobs. [GitHub deployment environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

When `deploy-production` needs to run, protection rules require an authorized reviewer to approve before the job proceeds. Approval only authorizes deployment; checksums and provenance must still be verified.

### 9.4. Artifact Retention and Long-Term Repositories

GitHub workflow artifacts are useful for passing files across jobs within one workflow run. `upload-artifact` v4 and newer produce immutable artifacts; this example uses v7. `download-artifact` v8 fails on digest mismatches by default. [actions/upload-artifact releases](https://github.com/actions/upload-artifact/releases) and [actions/download-artifact releases](https://github.com/actions/download-artifact/releases).

In the example, retention is 30 days. Workflow artifacts are not necessarily long-term release repositories. For releases requiring rollback months or years later, publish the JAR to a Maven-compatible repository or the image to an OCI registry with proper retention and immutability policies. Promotion should pull by GAV or digest from durable storage.

### 9.5. Build Provenance with GitHub Artifact Attestations

GitHub Actions can generate artifact attestations recording **where and how an artifact was built**. For binaries, workflows can request `id-token: write` and `attestations: write` permissions and invoke `actions/attest` after building. Consumers/CI can verify attestations via the GitHub CLI against repository and identity policies. [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

Attestation provides provenance evidence; it does not replace checksums, signatures, or vulnerability scans. Grant minimal permissions and verify the exact source repository and workflow identity expected by your release policy.

## 10. Runtime Configuration and Environment State

The exact same binary can behave differently due to runtime configuration and external state. That is normal when explicitly managed.

### Environment-Specific Spring Boot Configuration

Shared configuration example:

~~~properties
spring.application.name=orders-api
server.port=8080
~~~

Environment-specific values can be injected at startup:

~~~bash
SPRING_PROFILES_ACTIVE=production \
ORDERS_DATABASE_URL='jdbc:postgresql://db-prod.example.test/orders' \
java -jar orders-api-1.8.0.jar
~~~

The URL above is only an example; usernames and passwords should come from a secret store. In Kubernetes, configurations can originate from ConfigMaps/Secrets mounted or injected as environment variables.

Never bake production passwords or database URLs into the JAR during the build stage. Runtime configuration needs auditing, access control, and secret rotation independent of the release binary.

### Database Migrations Must Stay Compatible Across Promotion

Build-once does not automatically resolve database schema differences across environments. Migrations require a compatible rollout strategy:

1. Add new columns/tables without breaking the currently running app version.
2. Deploy the new app version and verify it.
3. Shift traffic or feature flags per plan.
4. Drop or alter old structures only after all consumers have transitioned and rollback no longer depends on the legacy schema.

With rolling deployments, keep in mind that two application versions may run concurrently during transitions. A non-backward-compatible migration can break rollback of an older binary even when the artifact bytes were preserved unchanged.

### Feature Flags

Features can be toggled per environment or user segment without building a new JAR. Feature flags must be managed, versioned, and audited separately. Never use feature flags to hide different artifacts running in Production.

## 11. Promotion, Rollback, and Post-Deployment Checks

### Conditional Promotion

An environment should promote only when:

- Artifact checksum/digest has been verified.
- Signatures/attestations satisfy trust policy if required for releases.
- Pre-release tests and scans passed.
- Deployment in the current environment is healthy.
- Smoke tests, API/contract checks, and operational criteria pass.
- Authorized reviewers have approved if the environment requires approval.

If Staging fails, the pipeline halts there. Never build a fresh artifact just to "patch Production"; fix the source, cut a new release candidate/version, and restart from the build stage.

### Rollback

Keep a log of deployed releases:

~~~text
Production current:
  orders-api@sha256:aaa...

Previous known-good:
  orders-api@sha256:bbb...

Git commit:
  a83f1c2...

Deployment record:
  environment=production
  release=1.8.0
  deployedAt=<UTC time>
~~~

This is an illustrative template. On rollback, point deployment back to the recorded, verified digest/GAV paired with matching runtime configuration. Do not rebuild old source trying to recreate an earlier binary if the old artifact still lives in the repository.

Rollbacks must also account for database migrations, queue/event compatibility, and external API changes. An older binary can fail against new data states unless migrations were designed to be backward-compatible.

### Post-Deployment Checks

After each environment:

- Health and readiness endpoints.
- HTTP smoke tests and contract checks.
- Error rates, latency, saturation, and log exceptions.
- Connectivity to DB, queues, and external services.
- Whether the version/digest reported by instances matches the release record.
- Rollout progress and actual running replica count.
- Observations across a soak window before promoting further.

**Build success only proves an artifact was created. Deploy success only proves the rollout action finished.** You must check that the live application runs the exact expected version/digest and meets operational criteria.

## 12. Common Mistakes That Break Build-Once

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Production JAR differs from Staging | Each environment runs its own Gradle/Maven build | Build once, store artifact, and download the exact release |
| Same version yet different checksums | Overwrote release coordinates or rebuilt with differing inputs | Enforce immutable releases; cut a new version on changes |
| Dependencies shift on rebuild | Dynamic versions or changing snapshots | Pin/lock dependency versions and verification metadata |
| Same image tag yet different image | Tag was retagged or re-pushed | Store and deploy by OCI digest |
| Staging passes yet Production fails on config | Missing or differing secret/URL/profile | Version external configs; validate config prior to promotion |
| Build profile produces a different JAR | Resource filtering or dependencies vary by env | Move configuration to runtime |
| Deploy job re-runs tests/build/package | Pipeline mixes verification with build stage | Deploy job only downloads, verifies, and deploys the artifact |
| Checksum passes yet file is malicious | Both checksum and artifact source compromised | Verify signatures/provenance and manifest origin |
| Artifact gone when rollback is needed | Repository retention too short or release deleted | Use durable release storage with proper retention policy |
| Promotion changes image digest | Built/pushed a fresh image per stage | Promote tags/metadata while keeping the exact digest |
| Rolling back old binary breaks DB | Migration broke backward compatibility | Use expand/contract migrations and rollback plans |
| Production deploys without approval | Environment protection rules unconfigured | Set up reviewers/approvals and branch protection |
| CI artifact download fails checksum | Corrupted artifact or transfer mismatch | Fail job, investigate run/artifact; never ignore digest mismatch |

### Signs a Pipeline Is Silently Rebuilding

- The deploy stage runs `./gradlew bootJar`, `./gradlew build`, or `mvn package`.
- Image builds execute inside every environment job.
- Versions change to `1.8.0-staging` and `1.8.0-prod` despite unchanged source.
- JAR checksums are never recorded or checked upon download.
- Deploy scripts directly mutate JAR contents, edit manifests, or repack images.
- Runtime records only tags without recording image digests/GAVs and source commits.

If a deployment step genuinely must transform an artifact (e.g., signing, adding metadata, compressing, or generating config files), model it as an explicit **artifact transformation/build step** with its own inputs, outputs, and checksum. Never silently mutate an approved binary and claim the output is the same artifact.

## 13. Minimum Release Record

Every publish or promotion should store a traceable record:

~~~text
Application:             orders-api
Release version:         1.8.0
Source repository:       <repository>
Source commit:           <full commit SHA>
Build workflow/run:      <run ID and URL>
Build toolchain:         <JDK, Gradle/Maven, plugin versions>
Dependency lock state:   <lockfile/verification metadata revision>
Artifact coordinate:     com.example:orders-api:1.8.0
Artifact SHA-256:        <actual digest>
OCI image digest:        <actual digest, if containerized>
Signature/attestation:   <verified identity/reference>
SBOM:                    <reference>
Tests/scans:             <report references and results>
Promotion history:       dev -> staging -> production
Approvals:               <reviewer and timestamp>
Deployment result:       <health checks and runtime digest>
~~~

The release record bridges source, artifact, and deployment. During an incident, operations can immediately tell which binary runs in each environment, which commit built it, and who approved promotion.

## 14. Checklist Before Promoting to the Next Environment

### Before Publishing

- [ ] Built from a specific commit or tag.
- [ ] Gradle/Maven, JDK, plugin, and dependency inputs are pinned.
- [ ] Unit, integration, and package tests pass.
- [ ] Security, license, and dependency scans pass per policy.
- [ ] Artifact is packaged once with explicit naming and versioning.
- [ ] SHA-256 is computed or OCI digest is recorded.
- [ ] Signatures/provenance are generated and verified if required by policy.
- [ ] Published to a repository/registry enforcing immutable releases.
- [ ] Release manifest, SBOM, and build reports are stored.

### Before Every Promotion

- [ ] Exact approved GAV or image digest is downloaded.
- [ ] Checksum, signature, and attestation are verified.
- [ ] Release version and source commit are confirmed.
- [ ] Environment configuration and secrets come from controlled runtime sources.
- [ ] Approvals are complete when required by the environment.
- [ ] Deploy script consumes the exact artifact without rebuilding.
- [ ] Deployment record and artifact digest are logged.
- [ ] Smoke, health, and contract checks pass.
- [ ] Promote onward only after the current environment meets criteria.

### During Rollback

- [ ] Select the previous known-good artifact or digest.
- [ ] Re-verify integrity and signature.
- [ ] Verify schema and data compatibility.
- [ ] Apply matching runtime configuration.
- [ ] Record rollback actor, timestamp, and digest.

## 15. Self-Check Questions

**Question 1.** What does "Build once, promote many" mean?

**Answer:** Build and test a single artifact, publish it once, and deploy those exact bytes/digest across multiple environments.

**Question 2.** Why can building the same source commit separately in Staging and Production still yield different artifacts?

**Answer:** Dependency resolution, JDK/plugin versions, timestamps, environment-dependent resource filtering, or differing toolchains can alter the bytes.

**Question 3.** Is build-once synonymous with reproducible builds?

**Answer:** No. Build-once avoids rebuilding during promotion; reproducible builds let independent builds recreate bit-for-bit identical artifacts from the same source and build inputs.

**Question 4.** Can you switch Spring profiles between Staging and Production while keeping the exact same JAR?

**Answer:** Yes. Spring profiles are runtime configuration, provided configuration is never baked into environment-specific binaries.

**Question 5.** Does Maven's `deploy` phase deploy the app to Production servers?

**Answer:** No. Maven `deploy` publishes the artifact to a remote repository. Application deployment is handled by a separate CD/orchestrator step.

**Question 6.** Why shouldn't you overwrite `com.example:orders-api:1.8.0`?

**Answer:** The same coordinates must always reference the exact same release artifact. Overwriting breaks checksums, caching, auditing, and rollback reliability.

**Question 7.** Is an image tag `1.8.0` enough to prove Production runs the exact tested image?

**Answer:** No if tags can be reassigned. Record and deploy by immutable image digest.

**Question 8.** Does a passing checksum prove the publisher is authentic?

**Answer:** No. Expected checksums must come from a trusted source; signatures/attestations and identity trust add proof of origin.

**Question 9.** After Staging passes, should you run Gradle again to build the Production JAR?

**Answer:** No. Production must download/promote the exact artifact tested in Staging; if source changes are needed, cut a new release and start over.

**Question 10.** What can cause rolling back an older binary to fail even when the JAR is completely intact?

**Answer:** Non-backward-compatible database schemas or data changes, new runtime configs, changed external API/queue contracts, or rotated secrets unsupported by the older app.

## 16. Official Documentation

- Gradle — [Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publish a publication to a Maven-compatible repository.
- Gradle — [Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): lock resolved dependency versions.
- Gradle — [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): verify checksums and PGP signatures of dependencies.
- Maven — [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): `package`, `verify`, `install`, and `deploy` phases.
- Maven — [Deploy Plugin Usage](https://maven.apache.org/plugins/maven-deploy-plugin-4.x/usage.html): deploy artifacts to a remote repository.
- Maven — [Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): create reproducible and comparable artifacts.
- Docker — [Pull an Image by Digest](https://docs.docker.com/reference/cli/docker/image/pull/): pin an image to a specific digest.
- GitHub — [Manage Deployment Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): required reviewers and environment protection.
- GitHub — [Store and Share Workflow Artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data): transfer artifacts across workflow jobs.
- GitHub — [Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): record build provenance.

**Key takeaway:** Build once from a specific source commit; test and verify the artifact; publish to an immutable store; promote the exact GAV/checksum or OCI digest; change only runtime configuration across environments. Every deployment must log artifact identity, approvals, and health check outcomes for accurate traceability and rollback.