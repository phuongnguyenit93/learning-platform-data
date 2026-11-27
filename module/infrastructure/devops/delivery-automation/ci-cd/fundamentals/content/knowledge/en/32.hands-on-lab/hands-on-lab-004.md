# Storing an Artifact and Handing Off the Exact Same Artifact to the Next Environment

In a reliable CI/CD process, a build produces an artifact with a clear identity; subsequent environments receive and deploy that exact artifact. Do not rebuild separately for staging and then rebuild again for production, because two builds can produce different contents even from the same commit, same version, or same filename.

This lab practices a small release flow for a Java service using Gradle. You will build a JAR once, create a release bundle containing the JAR, metadata, and checksums, store the bundle by SHA-256, deploy the same bundle to staging and then production, verify the digest at every stage, and intentionally corrupt a copy to verify tamper detection.

The lab uses local directories to simulate an artifact store and two environments. After completing it, you will map the same flow to GitHub Actions, GitLab CI, and Jenkins. In real deployments, the simulated artifact store and environment directories are replaced by a package/container registry, object storage, or your organization's deployment system.

## 1. Expected Outcomes

After this lab, you will be able to:

- Explain why you build once and promote the same artifact across environments.
- Distinguish between an artifact, cache, workspace, and release metadata.
- Create a JAR containing the version and commit SHA in its manifest.
- Package an artifact together with metadata and a SHA-256 checksum.
- Store artifacts by content digest to prevent accidentally overwriting versions.
- Deploy the exact same bundle to staging and production.
- Verify checksums before and after handoff.
- Detect modified or missing artifacts.
- Design a pipeline that passes artifacts across independent jobs/runners.
- Record evidence to trace source → build → artifact → deployment.

**Completion condition:** the JAR digest in the artifact store, staging, and production must match; the application must run from the deployed JAR; production may only be promoted after staging validation passes and an approval decision is recorded.

## 2. Scenario and Lab Architecture

You are releasing a simple service named orders-service. Version 1.0.0 is built from a specific commit. The pipeline must create a single release bundle and move that bundle through the steps:

~~~mermaid
flowchart TD
    A[Git commit] --> B[Gradle build + test]
    B --> C[orders-service JAR]
    C --> D[Release bundle]
    D --> E[SHA-256 + metadata]
    E --> F[Digest-addressed artifact store]
    F --> G[Deploy staging]
    G --> H[Verify digest + smoke test]
    H --> I{Approval}
    I -- Approved --> J[Deploy production]
    I -- Rejected --> K[Stop promotion]
    J --> L[Verify digest + runtime]
    L --> M[Release record]
~~~

Directory structure upon completion:

~~~text
orders-service/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/java/com/example/orders/Main.java
│   └── test/java/com/example/orders/MainTest.java
├── scripts/
│   ├── package-release.sh
│   └── deploy-local.sh
├── artifact-store/
│   └── orders-service/
│       └── 1.0.0/
│           └── sha256-<digest>/
│               ├── orders-service-1.0.0.jar
│               ├── release-metadata.json
│               ├── artifact-digest.txt
│               └── SHA256SUMS
└── environments/
    ├── staging/
    │   ├── current-digest
    │   └── releases/sha256-<digest>/
    └── production/
        ├── current-digest
        └── releases/sha256-<digest>/
~~~

Artifacts are stored in directories named after the JAR's content digest. The `current-digest` file acts as the current deployment pointer for the simulated environment; it updates when a new release is promoted. Digest-addressed release directories are treated as write-once in this lab. A local filesystem does not enforce immutability on its own; real systems require registry/object storage policies, restricted write permissions, and conditional object creation to prevent overwrites.

## 3. Preparing the Environment

Requirements:

- JDK 21.
- Gradle 8.10.2 or a compatible Gradle Wrapper.
- Git.
- Bash on Linux or WSL, with GNU coreutils for the `sha256sum` command. On macOS, install GNU coreutils and ensure `sha256sum` is on `PATH`.
- Access to the Gradle Plugin Portal/Maven repository on the first build to download the wrapper and JUnit.

Verify:

~~~bash
java -version
gradle --version
git --version
sha256sum --version
~~~

Create the project:

~~~bash
mkdir orders-service
cd orders-service

mkdir -p src/main/java/com/example/orders
mkdir -p src/test/java/com/example/orders
mkdir -p scripts

gradle wrapper --gradle-version 8.10.2
~~~

If you already have a Java service using Gradle, you can use that project instead of the skeleton below; just adjust the JAR path and filenames in the following steps.

## 4. Creating a Minimal Java Application

Create `src/main/java/com/example/orders/Main.java`:

~~~java
package com.example.orders;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "orders-service ready";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Create `src/test/java/com/example/orders/MainTest.java`:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MainTest {
    @Test
    void returnsReadyMessage() {
        assertEquals("orders-service ready", Main.message());
    }
}
~~~

This small test gives the lab a real quality gate. When tests fail, the pipeline must halt before creating and publishing a release bundle.

## 5. Declaring the Gradle Build

Create `settings.gradle`:

~~~groovy
rootProject.name = 'orders-service'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = providers.gradleProperty('releaseVersion').getOrElse('1.0.0')

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'com.example.orders.Main'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.test {
    useJUnitPlatform()
}

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': application.mainClass.get(),
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Build-Commit': System.getenv('GIT_COMMIT') ?: 'local'
        )
    }
}
~~~

The manifest helps identify which version and commit produced the JAR. This is useful traceability metadata, though it does not replace an artifact digest: the same version/commit can still produce a different binary if the toolchain, dependencies, or build inputs change.

If this is a new project, create an initial commit before packaging so the script has a specific source revision:

~~~bash
git init
git add build.gradle settings.gradle gradlew gradlew.bat gradle src
git commit -m "Create orders service starter"
~~~

If Git does not yet have a user identity configured, set `user.name` and `user.email` to your account before committing. For an existing repository, ensure `HEAD` points to the commit you want to release.

Run a test and build check:

~~~bash
./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
java -jar build/libs/orders-service-1.0.0.jar
~~~

Expected output:

~~~text
orders-service ready
~~~

If tests or build fail, stop here and fix the errors. Do not create a release bundle from the output of a build that has not passed the quality gate.

## 6. Build Once and Create the Release Bundle

Create `scripts/package-release.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
SERVICE="orders-service"
JAR_NAME="$SERVICE-$VERSION.jar"
GIT_COMMIT="$(git rev-parse HEAD)"
export GIT_COMMIT

./gradlew --no-daemon clean test jar -PreleaseVersion="$VERSION" >&2

JAR_PATH="build/libs/$JAR_NAME"
test -f "$JAR_PATH"

JAR_DIGEST="$(sha256sum "$JAR_PATH" | awk '{print $1}')"
STORE_PARENT="$PWD/artifact-store/$SERVICE/$VERSION"
ARTIFACT_DIR="$STORE_PARENT/sha256-$JAR_DIGEST"

mkdir -p "$STORE_PARENT"
TEMP_DIR="$(mktemp -d "$STORE_PARENT/.tmp.XXXXXX")"

cp "$JAR_PATH" "$TEMP_DIR/$JAR_NAME"

cat > "$TEMP_DIR/release-metadata.json" <<EOF
{
  "service": "$SERVICE",
  "version": "$VERSION",
  "sourceCommit": "$GIT_COMMIT",
  "artifactFile": "$JAR_NAME",
  "artifactSha256": "$JAR_DIGEST",
  "builtAtUtc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

printf '%s\n' "$JAR_DIGEST" > "$TEMP_DIR/artifact-digest.txt"

(
    cd "$TEMP_DIR"
    sha256sum "$JAR_NAME" release-metadata.json artifact-digest.txt > SHA256SUMS
)

if [ -d "$ARTIFACT_DIR" ]; then
    (
        cd "$ARTIFACT_DIR"
        sha256sum -c SHA256SUMS
    )
    rm -r "$TEMP_DIR"
else
    mv "$TEMP_DIR" "$ARTIFACT_DIR"
fi

printf '%s\n' "$ARTIFACT_DIR"
~~~

Grant execute permissions to the script:

~~~bash
chmod +x scripts/package-release.sh
~~~

Run the release build:

~~~bash
ARTIFACT_DIR="$(./scripts/package-release.sh 1.0.0)"
printf 'Artifact bundle: %s\n' "$ARTIFACT_DIR"
~~~

Continue the staging/production steps in the same Bash session to preserve the `ARTIFACT_DIR` variable. If you open a new terminal, re-assign `ARTIFACT_DIR` using the bundle path printed by the script.

The script performs the following actions:

1. Retrieves the current commit SHA from Git.
2. Runs `clean test jar` once.
3. Locates the output JAR and computes its SHA-256.
4. Generates metadata containing service, version, commit, filename, digest, and build timestamp.
5. Generates `SHA256SUMS` for the JAR, metadata, and digest file.
6. Stores the bundle in the artifact store by version and digest.
7. If a bundle with the same digest already exists, verifies the existing bundle instead of overwriting it.
8. Returns the bundle path so the deploy step uses that exact artifact.

In this lab, the artifact store is a local directory and assumes only one publisher runs at a time. This illustrative script does not implement distributed locking or safe create-if-absent operations under concurrent pipelines. In real systems, use a package registry/OCI registry or object storage with immutable versions, conditional create, retention, and restricted write permissions.

## 7. Inspecting Artifact Contents and Provenance

List the bundle contents:

~~~bash
find "$ARTIFACT_DIR" -maxdepth 1 -type f -print
cat "$ARTIFACT_DIR/release-metadata.json"
cat "$ARTIFACT_DIR/artifact-digest.txt"
~~~

Verify the checksums:

~~~bash
(
    cd "$ARTIFACT_DIR"
    sha256sum -c SHA256SUMS
)
~~~

Expected output:

~~~text
orders-service-1.0.0.jar: OK
release-metadata.json: OK
artifact-digest.txt: OK
~~~

Inspect the manifest inside the JAR:

~~~bash
unzip -p "$ARTIFACT_DIR/orders-service-1.0.0.jar" META-INF/MANIFEST.MF
~~~

You should see `Implementation-Version` as `1.0.0` and `Build-Commit` matching the commit recorded in the metadata.

**Security note:** `SHA256SUMS` detects corruption or accidental modification when the checksum file remains intact. If an attacker has permissions to replace both the JAR and `SHA256SUMS`, checksums alone do not prove origin. Production requires an artifact store with controlled write permissions, digests recorded in release records, and policy-verified signatures/provenance, such as Sigstore/cosign or an organization's artifact signing system.

## 8. Writing the Local Environment Deployment Script

Create `scripts/deploy-local.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="$1"
ARTIFACT_DIR="$2"

case "$ENVIRONMENT" in
    staging|production)
        ;;
    *)
        echo "Environment must be staging or production" >&2
        exit 2
        ;;
esac

test -d "$ARTIFACT_DIR"
test -f "$ARTIFACT_DIR/SHA256SUMS"
test -f "$ARTIFACT_DIR/artifact-digest.txt"

(
    cd "$ARTIFACT_DIR"
    sha256sum -c SHA256SUMS
)

EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
JAR_PATH="$(find "$ARTIFACT_DIR" -maxdepth 1 -type f -name 'orders-service-*.jar' -print -quit)"
test -n "$JAR_PATH"
JAR_NAME="$(basename "$JAR_PATH")"

ACTUAL_DIGEST="$(sha256sum "$ARTIFACT_DIR/$JAR_NAME" | awk '{print $1}')"
test "$ACTUAL_DIGEST" = "$EXPECTED_DIGEST"

TARGET_PARENT="$PWD/environments/$ENVIRONMENT/releases"
TARGET_DIR="$TARGET_PARENT/sha256-$EXPECTED_DIGEST"

mkdir -p "$TARGET_PARENT"

if [ -d "$TARGET_DIR" ]; then
    (
        cd "$TARGET_DIR"
        sha256sum -c SHA256SUMS
    )
else
    mkdir "$TARGET_DIR"
    cp -a "$ARTIFACT_DIR/." "$TARGET_DIR/"
fi

(
    cd "$TARGET_DIR"
    sha256sum -c SHA256SUMS
)

DEPLOYED_DIGEST="$(sha256sum "$TARGET_DIR/$JAR_NAME" | awk '{print $1}')"
test "$DEPLOYED_DIGEST" = "$EXPECTED_DIGEST"

OUTPUT="$(java -jar "$TARGET_DIR/$JAR_NAME")"
test "$OUTPUT" = "orders-service ready"

mkdir -p "$PWD/environments/$ENVIRONMENT"
printf '%s\n' "$DEPLOYED_DIGEST" > "$PWD/environments/$ENVIRONMENT/current-digest"

printf 'Environment: %s\n' "$ENVIRONMENT"
printf 'Artifact: %s\n' "$JAR_NAME"
printf 'SHA-256: %s\n' "$DEPLOYED_DIGEST"
printf 'Smoke test: %s\n' "$OUTPUT"
~~~

Grant execute permissions:

~~~bash
chmod +x scripts/deploy-local.sh
~~~

The script only accepts `staging` or `production`. Before copying, it verifies the bundle; after copying, it re-verifies the checksums and JAR digest. It runs the smoke test directly from the JAR in the release directory first; only when the smoke test passes does it update `current-digest`.

In this example, the `environments` directory simulates the environment filesystem. Real production replaces the file copy step with a deployment adapter such as SSH/rsync, Kubernetes, a VM deployment agent, or a release platform; the digest verification logic must still be kept.

## 9. Handing Off the Artifact to Staging

Deploy the stored bundle:

~~~bash
./scripts/deploy-local.sh staging "$ARTIFACT_DIR"
~~~

Verify staging points to the expected digest:

~~~bash
EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
STAGING_DIGEST="$(cat environments/staging/current-digest)"

test "$STAGING_DIGEST" = "$EXPECTED_DIGEST"
(
    cd "environments/staging/releases/sha256-$EXPECTED_DIGEST"
    sha256sum -c SHA256SUMS
)
~~~

Test the application from the exact handed-off file:

~~~bash
java -jar "environments/staging/releases/sha256-$EXPECTED_DIGEST/orders-service-1.0.0.jar"
~~~

The expected output is `orders-service ready`. Record the staging digest, deployment time, smoke-test result, and artifact reference. If the checksum or smoke test fails, do not promote to production.

## 10. Approving and Promoting the Exact Bundle to Production

Only after staging validation passes should you proceed to the production step. The lab simulates approval via manual confirmation:

~~~bash
read -r -p "Staging passed. Type YES to approve production: " APPROVAL
test "$APPROVAL" = "YES"
~~~

Deploy the exact same bundle:

~~~bash
./scripts/deploy-local.sh production "$ARTIFACT_DIR"
~~~

Verify both environments are running the same digest:

~~~bash
EXPECTED_DIGEST="$(cat "$ARTIFACT_DIR/artifact-digest.txt")"
STAGING_DIGEST="$(cat environments/staging/current-digest)"
PRODUCTION_DIGEST="$(cat environments/production/current-digest)"

test "$STAGING_DIGEST" = "$EXPECTED_DIGEST"
test "$PRODUCTION_DIGEST" = "$EXPECTED_DIGEST"
test "$STAGING_DIGEST" = "$PRODUCTION_DIGEST"

printf 'Staging:    %s\n' "$STAGING_DIGEST"
printf 'Production: %s\n' "$PRODUCTION_DIGEST"
~~~

The output must show the exact same SHA-256 across all three locations: artifact store, staging, and production.

Do not re-run Gradle before deploying to production. If you rebuild, even with the same version and commit, the output can still differ due to toolchain, dependencies, timestamps, or configuration. If you want to release a new fix, create a new version/release candidate, build, and verify from the beginning.

## 11. Testing Detection of a Modified Artifact

To prove that checksums are genuinely enforced, make a separate copy and modify one byte in the JAR. Never modify the original artifact in the artifact store.

~~~bash
TAMPERED_DIR="$(mktemp -d)"
cp -a "$ARTIFACT_DIR/." "$TAMPERED_DIR/"
printf 'corruption' >> "$TAMPERED_DIR/orders-service-1.0.0.jar"

if (
    cd "$TAMPERED_DIR"
    sha256sum -c SHA256SUMS
); then
    echo "ERROR: tampered artifact was not detected"
    exit 1
else
    echo "PASS: checksum detected artifact modification"
fi
~~~

The expected output is the JAR checksum reporting `FAILED` and the script confirming `PASS: checksum detected artifact modification`.

Next, attempt to deploy the tampered copy:

~~~bash
if ./scripts/deploy-local.sh staging "$TAMPERED_DIR"; then
    echo "ERROR: corrupted artifact was deployed"
    exit 1
else
    echo "PASS: deployment rejected corrupted artifact"
fi
~~~

Deployment must abort before updating `current-digest`. If the script still deploys, re-check the verification order and stop conditions.

## 12. Failure Scenarios and Handling

| Scenario | Symptom | Action |
|---|---|---|
| Build/test fails | Gradle returns non-zero | Do not create or publish bundle |
| JAR does not exist | No file matching expected version | Check Gradle output and version |
| Bundle with same digest already exists | Artifact path already present | Verify checksum and reuse |
| Same version but different digest | Artifact with different contents exists under that version | Stop and investigate; do not overwrite |
| Checksum fails before deploy | Missing or modified file | Disqualify bundle from promotion, inspect source, and re-download from trusted source |
| Copy to staging interrupted | Target directory missing files | Do not mark deploy successful; clean up partial copy per runbook |
| Staging smoke test fails | Application fails to respond | Halt promotion; investigate or release new candidate |
| Production approval rejected | No promotion decision | Keep artifact in tested state; do not deploy |
| Production digest differs from staging | Wrong artifact handoff | Halt release, verify deployment, and rollback per procedure |
| Deploy command times out | Unclear whether environment received artifact | Query deployment state and reconcile before retrying |

If the target directory exists but is missing files or fails checksum validation, the script halts. In real systems, upload to a staging location, verify completely, and then atomically promote/activate so users never see an incomplete release copy.

## 13. Integrating into GitHub Actions

Once the local lab works, you can move the artifact handoff flow into a workflow. The build job creates and uploads the bundle once; the staging and production jobs download the exact same artifact from that workflow run.

Example workflow `.github/workflows/release.yml`:

~~~yaml
name: Build and promote artifact

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test once
        run: |
          GIT_COMMIT="$GITHUB_SHA" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0

      - name: Create release bundle
        run: |
          mkdir -p dist/release
          cp build/libs/orders-service-1.0.0.jar dist/release/
          cd dist/release
          DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
          printf '%s\n' "$DIGEST" > artifact-digest.txt
          printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$GITHUB_SHA" "$DIGEST" > release-metadata.json
          sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS

      - name: Upload immutable workflow artifact
        uses: actions/upload-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/
          if-no-files-found: error
          retention-days: 14

  deploy_staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/

      - name: Verify artifact
        run: |
          cd dist/release
          sha256sum -c SHA256SUMS

      - name: Deploy staging
        run: ./scripts/deploy.sh staging dist/release

      - name: Verify staging
        run: ./scripts/verify-environment.sh staging dist/release

  deploy_production:
    needs: deploy_staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: orders-release-bundle
          path: dist/release/

      - name: Verify artifact again
        run: |
          cd dist/release
          sha256sum -c SHA256SUMS

      - name: Deploy production
        run: ./scripts/deploy.sh production dist/release

      - name: Verify production
        run: ./scripts/verify-environment.sh production dist/release
~~~

This workflow is a skeleton. You must configure environment protection for production in repository settings to require reviewers per policy. The deploy/verify scripts must deploy to real environments and verify the digest at runtime. In the production job, re-download the artifact with the same name from the same workflow run; do not check out source and rebuild.

Actions in the example use version tags for readability. Under strict supply-chain policies, pin actions to a reviewed full commit SHA. Workflow artifacts have retention limits; if you need to promote across multiple days or across separate workflows, publish the bundle to an immutable package/OCI registry or object storage, then pass the artifact digest/reference instead of relying on temporary workflow artifacts.

## 14. Mapping to GitLab CI and Jenkins

Other platforms offer equivalent handoff mechanisms in intent, though storage semantics and scope differ.

| Platform | In-Pipeline Handoff Mechanism | For Long-Term Storage |
|---|---|---|
| GitHub Actions | Upload/download workflow artifact | Package/container registry or release storage |
| GitLab CI | Job artifacts combined with needs/dependencies | Package/container registry or generic package registry |
| Jenkins | stash/unstash within the same Pipeline; archiveArtifacts | Artifact manager, Nexus, Artifactory, or OCI registry |

### 14.1. GitLab CI

The build job can publish the JAR as a job artifact; deploy jobs declare `needs` to download the artifact from that exact job:

~~~yaml
stages:
  - build
  - staging
  - production

build_release:
  stage: build
  image: gradle:8.10-jdk21
  script:
    - |
      GIT_COMMIT="$CI_COMMIT_SHA" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
      mkdir -p dist/release
      cp build/libs/orders-service-1.0.0.jar dist/release/
      cd dist/release
      DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
      printf '%s\n' "$DIGEST" > artifact-digest.txt
      printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$CI_COMMIT_SHA" "$DIGEST" > release-metadata.json
      sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS
      cd "$CI_PROJECT_DIR"
  artifacts:
    name: orders-release-bundle
    paths:
      - dist/release/
    expire_in: 14 days

deploy_staging:
  stage: staging
  needs:
    - job: build_release
      artifacts: true
  environment:
    name: staging
  script:
    - cd dist/release
    - sha256sum -c SHA256SUMS
    - cd ../..
    - ./scripts/deploy.sh staging dist/release

deploy_production:
  stage: production
  needs:
    - job: build_release
      artifacts: true
    - job: deploy_staging
      artifacts: false
  environment:
    name: production
  when: manual
  script:
    - cd dist/release
    - sha256sum -c SHA256SUMS
    - cd ../..
    - ./scripts/deploy.sh production dist/release
~~~

This example illustrates the job artifacts flow. Configure rules and protected environments/approvals according to your GitLab instance/tier. Artifact expiration must exceed the expected promotion window; if releases must be retained long term, publish to a registry with a retention policy.

### 14.2. Jenkins

Within a single Jenkins Pipeline, `stash`/`unstash` can transfer bundles across agents or stages. When artifacts must persist across multiple builds or pipelines, use an artifact repository.

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build once') {
            steps {
                checkout scm
                sh '''
                    GIT_COMMIT="$(git rev-parse HEAD)" ./gradlew --no-daemon clean test jar -PreleaseVersion=1.0.0
                    mkdir -p dist/release
                    cp build/libs/orders-service-1.0.0.jar dist/release/
                    cd dist/release
                    DIGEST="$(sha256sum orders-service-1.0.0.jar | awk '{print $1}')"
                    printf '%s\n' "$DIGEST" > artifact-digest.txt
                    printf '{"service":"orders-service","version":"1.0.0","commit":"%s","artifactSha256":"%s"}\n' "$(git -C ../.. rev-parse HEAD)" "$DIGEST" > release-metadata.json
                    sha256sum orders-service-1.0.0.jar artifact-digest.txt release-metadata.json > SHA256SUMS
                '''
                stash name: 'orders-release-bundle',
                      includes: 'dist/release/**'
            }
        }

        stage('Deploy staging') {
            steps {
                unstash 'orders-release-bundle'
                sh 'sha256sum -c dist/release/SHA256SUMS'
                sh './scripts/deploy.sh staging dist/release'
            }
        }

        stage('Approve production') {
            steps {
                input message: 'Staging passed. Approve production promotion?'
            }
        }

        stage('Deploy production') {
            steps {
                unstash 'orders-release-bundle'
                sh 'sha256sum -c dist/release/SHA256SUMS'
                sh './scripts/deploy.sh production dist/release'
            }
        }
    }
}
~~~

`stash` suits handoffs within the same Pipeline and generally does not replace an artifact repository with long-term retention/provenance. If Jenkins runs multiple controllers or separate pipelines, use a registry/artifact manager and reference by digest. Production approval requires RBAC and an approver policy; an `input` step alone does not define who is authorized to approve.

## 15. Distinguishing Artifact, Cache, and Workspace

| Component | Purpose | Use as Deploy Source? |
|---|---|---|
| Workspace | Temporary files for a job/runner | Not by default; may be wiped or modified |
| Cache | Speed up execution by reusing regenerable data | No |
| Job/workflow artifact | Hand off files between jobs or keep output within retention | Usable in short flows if integrity/retention fit |
| Package/OCI registry | Store versioned/digest-addressed artifacts with access policies | Yes, typically suited for promotion |
| Release record | Link source, artifact, approval, and deployment | Traceability evidence; does not necessarily store binaries |

Never use caches to pass JARs meant for deployment. Caches can expire, be evicted, restore under a mismatched key, or be written by another workflow. Released artifacts require identity, integrity verification, write permissions, and dedicated retention.

## 16. Release Records and Traceability

Every promotion should create or update a release record containing:

- Service and version.
- Source repository, commit SHA, and branch/ref.
- Pipeline run/build ID.
- Artifact name, coordinates, and SHA-256 digest.
- Metadata/provenance/signature reference.
- Environment and deployment ID.
- Staging/production timestamps.
- Approval identity and decision.
- Checksum, smoke test, and post-deploy verification results.
- Rollback reference if the release had to be reverted.

Example record:

~~~json
{
  "service": "orders-service",
  "version": "1.0.0",
  "commit": "a1b2c3d4",
  "artifactDigest": "sha256:abc123...",
  "buildRun": "ci-1842",
  "deployments": {
    "staging": {
      "status": "verified",
      "digest": "sha256:abc123..."
    },
    "production": {
      "status": "verified",
      "digest": "sha256:abc123..."
    }
  }
}
~~~

A record is valid only when the digest in deployment evidence is retrieved from the running environment or the artifact confirmed by the target system—not merely copied from self-reported build job metadata.

## 17. Extended Exercises

After completing the basic flow, perform the following exercises:

1. Build version 1.0.1 from a new commit and compare its digest with 1.0.0.
2. Re-run the package script for the same version and same contents; verify that the bundle with the same digest is reused.
3. Modify source code while keeping the same version; verify that the digest differs and explain why the old artifact must not be overwritten.
4. Delete a file in the staging copy and run checksum verification; verify that deploy/verification stops.
5. Create a new bundle, then intentionally pass the 1.0.0 bundle into the production promotion for release 1.0.1; design an expected version/commit/digest check to reject it.
6. Add an SBOM and provenance reference to release metadata.
7. Add artifact signing and verify the signature before deploying.
8. Replace the local artifact store with a package registry or object storage; pass only the digest/reference between pipelines.
9. Configure production approval and record the approver in the release record.
10. Rehearse a rollback by switching `current-digest` back to the previous release digest after verifying the old artifact still exists and is compatible.

## 18. Acceptance Criteria and Evidence to Save

| Criterion | Evidence |
|---|---|
| Build/test runs once per release candidate | Pipeline logs / build run ID |
| Bundle contains JAR, metadata, and SHA256SUMS | File listing in artifact store |
| Artifact stored by digest | Content-addressed path |
| Valid checksum before deploy | Output of `sha256sum -c` |
| Staging runs exact artifact | Runtime output and staging `current-digest` |
| Production runs exact tested artifact | Production `current-digest` matches staging |
| Modified artifact is rejected | Tamper test log showing checksum failure |
| Production has approval | Approval/deployment record |
| Traceable back to source | Commit SHA in metadata and release record |

Completion checklist:

- [ ] Gradle tests and build pass.
- [ ] JAR contains version and commit in its manifest.
- [ ] Release bundle contains JAR, metadata, artifact digest, and SHA256SUMS.
- [ ] Artifact store does not overwrite previously released content.
- [ ] Checksum is verified before deployment.
- [ ] Staging deploys from the artifact store without rebuilding.
- [ ] Staging smoke test passes.
- [ ] Production is approved before promotion.
- [ ] Production deploys from the exact same artifact bundle/digest.
- [ ] Staging and production digests match.
- [ ] Tamper test proves corrupted artifacts are rejected.
- [ ] Release record links commit, digest, approval, and deployment.

## 19. Self-Check Questions

**1. Why not rebuild the artifact in production?**

Because a second build can produce different contents due to changing dependencies, toolchains, timestamps, or configuration. Promoting the exact tested artifact ensures production runs the exact verified binary.

**2. What does a SHA-256 checksum prove?**

It detects whether content differs from what the checksum describes. If both the artifact and checksum are replaced together, checksums alone cannot prove origin; signatures, provenance, and write access controls are required.

**3. Why not use a cache for artifact handoff?**

Caches can expire, be evicted, restore under the wrong key, or originate from untrusted sources. Released artifacts require clear version/digest identity, retention, and release records.

**4. Why must staging and production have the same digest?**

To prove both environments are running the exact same tested contents. If digests differ, stop promotion and verify the actual artifact.

**5. When artifact upload succeeds but staging deployment fails, do you need to rebuild?**

Not necessarily. First investigate the deployment, verify the bundle is intact, and proceed from the stored artifact if it remains valid. Only create a new artifact when source code or build inputs need to change.

The lab is complete when an artifact can travel from build to staging and production without being rebuilt, every stage verifies the exact same digest, production requires prior approval, and full traceability evidence exists. This establishes the foundation for expanding into registry promotion, artifact signing, SBOMs, provenance, and release automation in real-world environments.
