# Rebuilding Artifacts per Environment and Treating Them as the Same Tested Build

A team can build an application successfully in development, run the build command again with staging configuration, and build a third time for production. The output files may carry the same name and version, such as `order-service:2.8.0`, leading everyone to assume it is the same tested build. Yet if each build uses different source state, dependencies, toolchains, build arguments, or generated files, the actual contents can differ.

This is a dangerous thinking pitfall in CI/CD: **equating a version label with artifact identity**. A version string helps humans recognize a release, but it does not prove two files share identical bytes or contents. An artifact tested in staging is not automatically the artifact running in production if the pipeline rebuilt it in between.

The safer mindset is **Build Once, Promote Many**: build an artifact with an immutable identity, test and verify that exact artifact, and then promote that very artifact across environments. Environment-specific differences such as endpoints, feature policies, resource limits, and secrets are supplied through controlled runtime or deployment configuration. Every promotion must preserve the link between source revision, artifact digest, test evidence, approval, and target environment.

## 1. Why Does Rebuilding per Environment Create Risk?

Suppose a pipeline has three steps:

1. Build `order-service` for development and run unit tests.
2. Rebuild `order-service` with staging configuration and run integration tests.
3. Rebuild `order-service` with production configuration and deploy.

Even when all three use the version label `2.8.0`, they do not necessarily produce the same artifact. Differences can stem from:

- Source revision changing between builds.
- Dependencies re-resolving to different versions.
- Compilers, JDKs, package managers, or base images changing.
- Build profiles removing or adding modules.
- Environment variables altering compiled code or packaged resources.
- Generated sources, frontend bundles, or migration files created from different data.
- Timestamps, file ordering, or metadata embedded into the package.
- Build caches containing stale or invalid outputs.
- Build scripts fetching data from the network at runtime.

As a result, test evidence only proves that one specific artifact worked. It does not prove that a different artifact sharing the same name will behave identically.

## 2. A Version Label Is Not Artifact Identity

Version labels are usually human-readable metadata: `2.8.0`, `release-2026.11`, or `build-1842`. Two builds can carry the same label while having different contents. Conversely, the same content can be assigned different aliases or tags.

| Concept | Purpose | Does It Prove Identical Content? |
|---|---|---|
| Version string | Identifies a version by convention | No |
| Git commit SHA | Identifies source repository revision | Does not prove all build inputs were identical |
| Artifact filename | File name in repository | No |
| Registry tag | Label pointing to an image/package | No; tags can be moved if the registry permits |
| Digest/checksum | Content identifier by hash | Confirms bytes/content per hash algorithm and hashed scope |
| Signature | Verifies signer's signature over content/statement | Does not itself prove artifact safety or testing |
| Provenance | Describes source and artifact creation process | Aids traceability; requires verifying source and policy |

For OCI images, a digest such as `sha256:...` identifies the manifest or index content for the referenced object. For JAR, ZIP, or package files, the SHA-256 of the file itself can be used. Understand what object the digest is computed over; the digest of a multi-architecture image index differs from the digest of an image manifest for a specific platform.

Do not conclude two artifacts are identical simply because they share the same version, tag, or commit SHA. Compare the digest of the exact deployed artifact.

## 3. What Is Build Once, Promote Many?

Build Once, Promote Many means a release candidate is built into an artifact, and that same artifact moves across environments. The pipeline does not create a new binary for staging or production merely to swap endpoints or environment configuration.

Conceptual flow:

~~~mermaid
flowchart TD
    A[Source commit] --> B[Build immutable artifact]
    B --> C[Calculate digest and publish]
    C --> D[Run tests against artifact]
    D --> E[Promote same digest to staging]
    E --> F[Verify and approve]
    F --> G[Promote same digest to production]
    G --> H[Verify runtime digest and health]
~~~

The artifact is produced once in the release candidate pipeline. Environments reference the same digest; deployment configurations may differ by environment but are managed and reviewed separately. Thus, staging test evidence binds to the exact contents that will run in production.

Build once does not mean running only one build command across the entire software lifecycle. Developers can build locally, and CI can build for different commits or targets. The rule applies to **a release candidate**: the artifact chosen for release must be the artifact that was verified and promoted intact.

## 4. Distinguishing Artifact, Release, and Deployment Configuration

A release system typically has several components:

- **Source:** selected code and revision.
- **Build input:** toolchain, dependency lock, build script, base image, and permitted parameters.
- **Artifact:** binary, package, container image, frontend bundle, or deployable file.
- **Release metadata:** version, commit SHA, digest, provenance, SBOM, and test evidence.
- **Deployment configuration:** replica count, resource limits, routes, endpoints, feature policies, and per-environment settings.
- **Secret:** credentials or keys supplied from a secret manager when runtime/deploy needs them.
- **Deployment record:** environment, timestamp, actor, actual digest, and verification result.

Do not bake every environmental difference into the artifact. For instance, production database URLs, passwords, staging endpoints, and replica counts should not be compiled into separate binaries when they can be safely configured at deployment time.

Conversely, not everything is runtime configuration. Certain values must be compiled or bundled into the artifact, such as target architecture, static frontend assets, or code generation. If they alter the content, treat each variant as a distinct artifact with its own digest and test evidence.

## 5. Example: The Same Container Image Across Three Environments

Suppose the pipeline builds an image once and publishes:

~~~text
registry.example.com/platform/order-service@sha256:7a91...c42e
~~~

Deployments across environments reference the same digest:

| Environment | Image reference | Varying configuration |
|---|---|---|
| Development | Same digest | Dev endpoint, 1 replica, appropriate debug logging |
| Staging | Same digest | Staging endpoint, test data, 2 replicas |
| Production | Same digest | Production endpoint, load-based replicas, production secrets |

Different configuration values do not modify the image. If staging and production genuinely need different binaries, the team must classify them as two distinct target artifacts with separate identities rather than calling them the same artifact.

A tag like `order-service:2.8.0` can be used for display, but deployments should pin by digest. Even if a tag is overwritten, the digest still identifies the exact tested content.

## 6. Example with a JAR Package

For a Java application, the pipeline can build one JAR:

~~~bash
./gradlew clean test bootJar
sha256sum build/libs/order-service.jar
~~~

The JAR is published to an artifact repository alongside its checksum, version, and provenance. Environments download the exact package by digest or immutable coordinates, then supply configuration via environment variables, mounted configs, or a secret manager.

Do not re-run Gradle with a production profile to create another JAR while keeping the same version as staging. If a profile alters code, resources, or packaged dependencies, it produces a different artifact and requires separate testing.

If the application needs build profiles to select different modules or targets, make that profile explicitly part of the artifact identity. Do not use a shared version label to mask content variants.

## 7. How Should Environment-Specific Configuration Be Managed?

Environment configuration typically includes:

- Endpoints of dependent services.
- Database, schema, or queue names.
- Replica counts, CPU/memory limits, and autoscaling.
- Log levels and sampling.
- Feature flags or rollout percentages.
- Timeouts, retry limits, and circuit breaker policies.
- Ingress, domains, routes, and network policies.
- Secret references or workload identities.

These values can be managed in deployment manifests, Helm values, Kustomize overlays, config services, or secret managers. They require review, versioning, and change-access control.

Kubernetes Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: registry.example.com/platform/order-service@sha256:7a91c42e
          env:
            - name: APP_ENV
              value: staging
            - name: PAYMENT_API_URL
              valueFrom:
                configMapKeyRef:
                  name: order-service-config
                  key: payment-api-url
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: order-service-db
                  key: password
~~~

Digests and resource names in this example are placeholders. The manifest simply illustrates keeping the image reference fixed while injecting configuration and secrets from separate sources. In production, secrets must be managed via platform-appropriate mechanisms, least-privilege read permissions, and rotation; never store plaintext passwords in a repository.

## 8. Do Not Let Environment Configuration Silently Alter the Binary

Some build systems allow profiles or environment variables to change packaged source or resources. For example:

- A staging profile excludes or includes modules.
- A build flag disables a security check in development.
- A frontend build bakes an API URL into the bundle.
- A script copies a different config file into the package before archiving.
- A build fetches feature definitions or schemas from an external endpoint.

If those values change the artifact contents, the pipeline has produced different artifacts. That is not necessarily wrong, but they must be recognized and controlled as separate targets.

For static frontend bundles, an API URL might be embedded into JavaScript files at build time. There are two choices:

1. Build a separate bundle per environment and test each bundle; each bundle is then a separate artifact.
2. Build an environment-agnostic bundle that loads runtime config safely at application startup; the exact same bundle can then be promoted.

Do not claim "build once" if build arguments or generated configs actually alter the binary.

## 9. Dependency Drift Across Builds

Even when the source SHA is unchanged, dependencies can shift if builds do not lock versions. Declaring version ranges, `latest` tags, or mutable packages can resolve to newer contents in a subsequent build.

To reduce drift:

- Use lockfiles or dependency constraints appropriate to the ecosystem.
- Pin base images by digest when immutability is required.
- Manage plugin, compiler, and toolchain versions.
- Use controlled repository mirrors with retention.
- Never fetch arbitrary scripts from unpinned URLs during builds.
- Record resolved dependencies/materials in provenance.
- Key caches on critical inputs and never treat a cache as a source of truth.

Caches speed up builds, but a cache does not prove correctness. If a cache key omits compiler versions or build arguments, stale output can be reused in an incompatible context. When in doubt, have a way to run a clean build and compare results.

## 10. Reproducible Builds Differ from Build Once

The two concepts are related, not identical:

- **Build Once, Promote Many:** do not rebuild the same release candidate's artifact when moving across environments.
- **Reproducible Build:** identical source and controlled build inputs yield identical output according to defined criteria.

Build once does not automatically guarantee reproducibility. A build might embed timestamps, file ordering, or unpinned dependencies yet still promote the exact same digest across environments.

Reproducible builds also do not replace promotion. If a team rebuilds production from the same source and happens to get the same checksum, that still has to be proven rather than assumed.

Reproducibility helps verify build processes, investigate supply chains, and reconstruct artifacts. Immutable promotion guarantees that downstream environments receive the exact artifact that was tested.

## 11. Test the Exact Artifact That Will Be Deployed

A common mistake is testing source/build output in a workspace and then creating a new package in another job. If the later package differs from the tested output, evidence is no longer bound to the released artifact.

The pipeline should:

1. Build the artifact and compute its digest.
2. Publish the artifact to an immutable repository.
3. Download the artifact by digest in test jobs when tests run against the packaged artifact.
4. Run integration, smoke, and security checks against that exact package/image.
5. Record test evidence alongside the artifact digest.
6. Promote that exact digest to the next environment.

Unit tests can run inside the build job before packaging completes. However, checks for packaging, container runtime, migration bundles, startup, smoke tests, and deployment should verify the final artifact whenever possible.

If tests only run on the source tree without checking the packaged artifact, missing files, wrong resources, or Docker layers missing required contents can slip through.

## 12. Artifact Repositories Must Support Immutability

An artifact repository/registry stores packages and distributes them to environments. It must be designed so published artifacts cannot be silently replaced.

Useful controls:

- Immutable versions or disallowing overwrites of release coordinates.
- Digests/checksums stored and verified on download.
- Publish permissions separated from read/promote permissions.
- Retention keeping artifacts available for rollback/audit windows.
- Audit logs for publishes, deletions, tags, and permission changes.
- Replication/mirroring with integrity checks.
- Quarantine or revocation when an artifact is found to be compromised or defective.

If a registry allows mutable tags, the pipeline must deploy by digest and enforce policies restricting who may move release tags. A tag is a convenient human alias; a digest is the content-identifying reference.

Do not delete older artifacts immediately after a successful deploy. Rollbacks, forensic investigations, or environment rebuilds may require that exact artifact.

## 13. Promotion Is a Trust-State Change, Not a New Build

Promotion moves an artifact that has passed a set of checks to a higher-trust environment or stage. Each promotion step should record:

- Artifact digest and version label.
- Source commit and repository.
- Build provenance and signer identity.
- Test and scan evidence.
- Source and target environments.
- Policy gates and approvals.
- Actor or automation identity.
- Timestamp and outcome.

Promotion does not alter artifact content. If you need to modify a binary, swap a package, repackage an image, or inject environment-specific files, that creates a new artifact requiring a new digest and new evidence.

One release record can reference the same digest while linking multiple deployment records for dev, staging, and production. Each deployment record maintains its own configuration, approvals, and verification results.

## 14. Example Pipeline: Build Once, Then Promote

Conceptual workflow example:

~~~mermaid
flowchart TD
    A[Commit merged] --> B[Build and test source]
    B --> C[Package artifact]
    C --> D[Calculate digest]
    D --> E[Publish immutable artifact]
    E --> F[Test packaged artifact]
    F --> G[Promote digest to development]
    G --> H[Promote same digest to staging]
    H --> I[Approval and policy checks]
    I --> J[Promote same digest to production]
    J --> K[Verify runtime digest and health]
~~~

Each environment can have its own deployment configuration, yet the artifact reference stays constant. If the digest changes, the pipeline must treat it as a different artifact and re-run the appropriate gates.

## 15. GitHub Actions Example: Build/Publish Once, Deploy by Digest

The illustrative workflow below separates the build job from deployment jobs. The build job builds the image, pushes it once, and saves the digest as a small artifact; downstream jobs retrieve that reference:

~~~yaml
name: Build and promote

on:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build and push
        run: |
          docker build -t "ghcr.io/example/order-service:$GITHUB_SHA" .
          docker push "ghcr.io/example/order-service:$GITHUB_SHA"
          DIGEST="$(crane digest "ghcr.io/example/order-service:$GITHUB_SHA")"
          printf '%s\n' "ghcr.io/example/order-service@$DIGEST" > image-ref.txt
      - name: Upload image reference
        uses: actions/upload-artifact@v4
        with:
          name: image-reference
          path: image-ref.txt

  verify-image:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Verify packaged image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./verify-image.sh "$IMAGE_REF"

  deploy-staging:
    needs: verify-image
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Deploy tested image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./deploy.sh --environment staging --image "$IMAGE_REF"

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Deploy the same image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./deploy.sh --environment production --image "$IMAGE_REF"
~~~

This is an illustrative example that must be adapted to your registry, deployment tooling, and repository permission policies. Runners must authenticate to the registry with an appropriate identity; never hardcode credentials. In production, pin GitHub Actions by commit SHA if required by policy. The production job requires appropriate approval and protection rules.

The key point is that the staging and production jobs use the exact same image reference file produced by the build job. Do not invoke build inside individual deploy jobs. If a deploy script rebuilds or mutates the image, the promotion principle is broken.

## 16. GitLab CI Example: Passing Artifact Digest Across Stages

A GitLab pipeline can save the digest as a `dotenv` artifact for downstream jobs to reuse:

~~~yaml
stages:
  - build
  - verify
  - staging
  - production

build-image:
  stage: build
  script:
    - docker build -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA" .
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA"
    - DIGEST="$(crane digest "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA")"
    - echo "IMAGE_REF=$CI_REGISTRY_IMAGE@$DIGEST" > image.env
  artifacts:
    reports:
      dotenv: image.env

verify-image:
  stage: verify
  needs:
    - job: build-image
      artifacts: true
  script:
    - ./verify-image.sh "$IMAGE_REF"

deploy-staging:
  stage: staging
  needs:
    - job: verify-image
      artifacts: false
    - job: build-image
      artifacts: true
  script:
    - ./deploy.sh staging "$IMAGE_REF"

deploy-production:
  stage: production
  needs:
    - job: deploy-staging
      artifacts: false
    - job: build-image
      artifacts: true
  when: manual
  script:
    - ./deploy.sh production "$IMAGE_REF"
~~~

This example assumes Docker CLI, `crane`, and deploy scripts are installed, registry authentication is configured, and `dotenv` artifacts are passed properly according to your GitLab version. Check the exact semantics of `needs`/`artifacts`, protected environments, and manual approvals in your actual setup.

Do not rebuild the image in `deploy-staging` or `deploy-production`. These jobs only consume the reference created in the build stage and verified upstream.

## 17. Artifacts for Multiple Platforms or Architectures

There is not always a single binary that runs on every platform. An application may require:

- Linux x86_64 and Linux ARM64.
- Windows and Linux packages.
- Multi-architecture container images.
- Debug/release builds or FIPS-compliant variants.
- Frontend bundles for different runtime targets.

Each variant can be a distinct artifact with its own digest. Build Once, Promote Many still applies to each target artifact: build the required variant, test that exact variant, and promote the corresponding digest. For OCI multi-platform images, you can publish an image index pointing to platform manifests; know which manifest the runtime resolves and verify the exact digest/index.

Do not try to force one artifact across every target when runtimes genuinely need different binaries. What must be avoided is rebuilding the same target per environment and treating the differing outputs as one build.

## 18. Do Configuration Changes After Build Require Retesting?

An artifact may be immutable, yet deployment configuration still changes. Therefore, "same artifact" does not mean "every deployment is completely identical."

Distinguish between:

- **Artifact validation:** does the package/image have the right contents, run properly, and pass corresponding tests?
- **Configuration validation:** is the environment configuration valid, complete, and compatible with the artifact?
- **Deployment validation:** did the target system deploy the exact digest and desired state?
- **Runtime verification:** does the service operate properly under live configuration and traffic?

If a config change only adjusts replica count or an already-verified endpoint, corresponding validation may suffice. If config enables a new code path or changes authorization, timeouts, or database behavior, additional risk-based testing is needed. If config alters the artifact's contents, it is no longer independent runtime config.

Version deployment configuration and record the config digest/commit alongside the deployment record. When reproducing a release, you must know both the artifact and the configuration that was applied.

## 19. Secrets Must Be Supplied at Deploy/Runtime

Secrets must never be baked into artifacts. If a password or private key is packaged inside an image or JAR, every environment using that artifact receives the secret, making rotation or revocation difficult.

Best practices:

- Retrieve secrets from a secret manager or workload identity at deploy/runtime.
- Scope permissions by service and environment.
- Use short-lived credentials when the platform supports them.
- Never store secrets in build arguments, image layers, or artifact metadata.
- Never print secrets in logs, test reports, or release notes.
- Maintain a rotation process and post-rotation verification.

Build jobs generally do not need permission to read production secrets. Only the production deploy job receives the minimal identity and permissions needed after approval. Separating build permissions from deploy permissions limits impact if a dependency or untrusted pull request is compromised.

## 20. Which Artifact Do Provenance and SBOM Bind To?

Provenance describes which source and build process produced an artifact. An SBOM lists components and dependencies inside the artifact. Test reports and scan reports must also bind to the exact artifact.

A release evidence set should reference:

- Artifact digest.
- Source repository and commit SHA.
- Builder/workflow identity.
- Build parameters and key materials.
- Toolchain, base image, and dependency versions.
- Provenance/attestation and signature.
- SBOM digest or reference.
- Test/scan results and execution timestamps.
- Policy decisions and approvals.

If you rebuild for production, provenance and SBOM may differ even with the same source commit. If a scan report was generated for digest A while digest B is deployed, report A does not prove B was scanned.

Verify signatures, signer identity, and provenance against a trust policy. A validly signed artifact can still contain vulnerabilities; a signature proves signing origin for a key/identity, while policies and security scans evaluate other properties.

## 21. What Should Promotion Gates Verify?

Before promoting to a higher-risk environment, the pipeline can verify:

- Current digest matches the digest that was built and tested.
- Artifact exists in a trusted registry and is not quarantined or revoked.
- Signatures and provenance are valid per policy.
- Test evidence belongs to that exact digest.
- SBOM/scan evidence meets freshness and severity policies.
- Deployment configuration has been reviewed and validated.
- Approval is bound to the exact release identity.
- Environment readiness and change windows are appropriate.
- Migration/API compatibility and rollback plans are ready.

Gates must fail closed when mandatory evidence is missing, unretrievable, or mismatched. Never treat "scanner did not respond" as "no vulnerabilities."

## 22. Staging Differs from Production, Yet the Artifact Must Be the Same

Staging can differ from production in scale, data, networking, dependencies, and permissions. You cannot assume a staging smoke test proves production will definitely work.

To increase confidence:

- Use the exact same artifact digest.
- Keep configuration and topology close to production where needed.
- Use synthetic or properly protected data.
- Test contracts against realistic dependencies and versions.
- Check resource and scaling behavior with appropriate tests.
- Validate production configuration before deploying.
- Use canary/progressive rollouts and post-deploy verification in production.

Environment differences should be documented and managed. If production runs a different database engine or extension than staging, test compatibility in a representative environment or collect separate evidence. Building once does not eliminate the need for environment verification.

## 23. Rollback Must Use Stored Artifacts, Not Rebuild Old Versions

When rolling back, fetch the previous release's artifact digest from the release/deployment record. Do not rebuild an old source branch and assume the result matches the prior package.

Rollback must consider:

- Is the older artifact still in the registry and its digest verifiable?
- Was the previous configuration saved and versioned?
- Is the database migration backward-compatible?
- Can older consumers process newer events/messages?
- Are rotated secrets or certificates compatible with the older version?
- Do feature flags need to be disabled or adjusted?
- Will rolling back create side effects or data loss?

Artifact rollback and configuration rollback are two separate operations. You may need to deploy an older digest with compatible newer configuration, or restore both old config and old artifact together. Maintain runbooks and tests for those combinations.

Not every release can be rolled back safely. When schemas or data have changed irreversibly, rolling forward or executing a recovery plan may be required instead of simply swapping image digests.

## 24. Promotion Across Multiple Environments and Approvals

Each environment can enforce its own gates:

| Stage | Evidence / Conditions | Action |
|---|---|---|
| Build | Source revision, build log, digest, provenance | Publish immutable artifact |
| Test | Unit/integration/contract/security checks on the exact artifact | Mark candidate eligible |
| Development | Deploy digest, smoke test, config validation | Verify baseline behavior |
| Staging | Integration/E2E, migration rehearsal, load/compatibility checks | Prepare release |
| Production | Approval, policy, environment readiness | Promote the same digest |
| Post-deploy | Runtime digest, health, error/latency, and business checks | Continue, pause, or rollback |

Approvals should reference the release ID and digest. If the artifact changes, prior approval must not automatically apply to the new contents. If only configuration changes, policy should define whether re-approval is needed based on risk.

## 25. GitOps and Desired State Must Also Pin Digests

In GitOps, the configuration repository describes the environment's desired state. If manifests only reference a mutable tag like `latest`, the controller may pull different contents during reconciliation without any new config commit.

Update manifests with digests or immutable tags per policy. Pull requests modifying desired state should link the release record, artifact digest, and approval. The GitOps controller then reconciles the exact reviewed reference.

If automation is used to bump image references, the bot must verify artifact evidence before opening or merging the change. Never treat the mere existence of a tag as proof the artifact passed tests.

## 26. Valid Exceptions and How to Handle Them

There are cases requiring different builds per environment or target. The key is not mistakenly calling them the same artifact:

- **Frontend builds embedding API endpoints:** produce separate bundles per environment and test each bundle, or move endpoints to runtime configuration to share one bundle.
- **Platform-specific binaries:** build separately for each OS/architecture; each variant gets its own digest and evidence.
- **FIPS/compliance builds:** build a distinct variant with a controlled toolchain/base image and separate policy.
- **Customer-specific packages:** if packages differ in content per tenant, manage them as artifact variants with corresponding testing and provenance.
- **Schema-driven code generation:** the input schema is a build material; changing the schema produces a new artifact.

A valid exception must have a documented rationale, explicit target identity, clear build inputs, and test evidence. Never use "production needs to be different" as a blanket excuse to rebuild everything.

## 27. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Separate dev/staging/prod builds with the same version | Unknown which binary was actually tested | Build one candidate, promote by digest |
| Deploying via mutable tags | Tags can shift to point at a different image | Pin by digest |
| Rebuilding inside deploy jobs | Artifact is no longer the tested output | Deploy the exact artifact reference from the build job |
| Using commit SHA as proof of identical bytes | Dependencies/tools/configs may differ | Record digest and provenance |
| Baking secrets into images/JARs | Secrets leak across environments and resist rotation | Use secret managers/workload identity |
| Baking env endpoints into code without managing variants | Produces different artifacts assumed to be identical | Use runtime config or explicit variant identity |
| Testing source without testing the final package | Misses packaging, layer, or resource defects | Test the exact published artifact |
| Promoting without scans/provenance | Cannot prove artifact meets policy | Gate on digest and evidence |
| Rebuilding to roll back | Can produce different bytes than the prior release | Retrieve the stored artifact digest |
| Deleting old artifacts | Unable to roll back or reproduce | Retain per rollback/audit window |
| Treating staging as identical to production | Overlooks topology/config/data differences | Test differences and use progressive rollouts |
| Not storing deployment config versions | Cannot reproduce releases | Version configs and write deployment records |

## 28. Pre-Promotion Artifact Checklist

- [ ] Release candidate has an unambiguous source commit SHA.
- [ ] Key build inputs, toolchain, and dependencies are controlled.
- [ ] Artifact is published to a trusted repository.
- [ ] Artifact has a digest and cannot be overwritten.
- [ ] Test evidence references the exact digest.
- [ ] Signatures, provenance, and SBOM are verified per policy.
- [ ] Every environment references the same digest for the same target artifact.
- [ ] Deployment configuration is versioned and validated separately.
- [ ] Secrets are supplied via a secure runtime/deploy mechanism.
- [ ] Approvals bind to the exact release identity and digest.
- [ ] Post-deploy runtime is verified against the actual digest.
- [ ] Artifact/config rollback and data compatibility plans exist.
- [ ] Artifacts and evidence are retained per retention policy.
- [ ] Any build variant exceptions carry separate target identities and test evidence.

## 29. Conclusion

Rebuilding an artifact separately for each environment and treating the outputs as the same tested build is a fallacy because version labels and commit SHAs do not prove identical package contents. Build inputs, dependencies, toolchains, build profiles, and generated files can all alter artifacts between runs.

For a release candidate, build the artifact, compute its digest, publish it immutably, test the exact final artifact, and promote that same digest across environments. Manage environment configuration and secrets separately with proper versioning, permissions, and validation. Provenance, SBOMs, signatures, test evidence, approvals, and deployment records must all link back to the same artifact identity.

Build Once, Promote Many eliminates uncontrolled drift between staging and production, strengthens traceability, and makes rollbacks far more reliable. When platform targets or special requirements genuinely demand separate variants, treat each variant as its own artifact and test the exact contents being deployed.
