# Artifact Management, Image Signing, and Release Traceability

A pipeline can build successfully, pass all tests, and deploy an application to production, yet still leave critical questions unanswered: which commit built the running binary, was the image altered after scanning, who signed the image, is the signature valid, and can we restore the exact artifact from the previous release?

**Artifact management, image signing, and release traceability** answer those questions. Artifacts must be stored under strict controls and remain unchanged after build. Images must be identified by digest, signed by a trusted identity, and verified before deployment. Release metadata must link source commit, build execution, test results, SBOM, provenance, signature, artifact digest, and deployment records into an auditable chain.

This lesson belongs to the **CI/CD on AWS** chapter of the **CLOUD_PROVIDERS_AWS** module. It combines Amazon S3, Amazon ECR, AWS CodeBuild, AWS CodePipeline, AWS Signer, AWS KMS, AWS CloudTrail, and ECS/EKS/Lambda deployment mechanisms to manage artifacts securely with traceability and recovery.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish between source artifacts, build artifacts, container images, deployment packages, SBOMs, and provenance attestations.
2. Design artifact repositories using S3, ECR, and CodeArtifact with encryption, versioning, retention, and least privilege.
3. Distinguish image tags from immutable image digests and deploy by digest.
4. Create a release manifest connecting source commit, build ID, artifact digest, and deployment version.
5. Generate an SBOM in SPDX or CycloneDX format and bind it to the exact artifact.
6. Explain digital signatures, signing identities, trust stores, signature verification, and key lifecycles.
7. Use AWS Signer with Notation or a compatible image-signing solution such as Cosign/AWS KMS.
8. Verify image signatures prior to deployment and at the Kubernetes admission boundary.
9. Distinguish encryption at rest with KMS from signing to prove integrity/provenance.
10. Promote the exact same artifact across dev, staging, and production without rebuilding.
11. Manage ECR replication, S3 Object Lock, lifecycle policies, and rollback retention.
12. Audit releases using CodePipeline, CodeBuild, CloudTrail, CloudWatch, and deployment records.

## 2. Artifacts in the CI/CD Workflow

An **Artifact** is an output produced or consumed during the build/release process. Each artifact type has its own purpose and storage pattern.

| Artifact type | Example | Suitable storage |
|---|---|---|
| Source snapshot | Source ZIP, Git commit tree | Git provider, CodePipeline source artifact |
| Java package | JAR/WAR | S3, CodeArtifact package repository, or managed artifact repository |
| Container image | OCI/Docker image | Amazon ECR |
| IaC package | CloudFormation template, CDK synthesized template, SAM package | S3 artifact store |
| Test evidence | JUnit XML, coverage report, scan report | CodeBuild reports, S3 |
| SBOM | SPDX JSON, CycloneDX JSON | S3 or OCI artifact/referrer in registry |
| Provenance | in-toto/SLSA attestation, build metadata | S3 or OCI artifact/referrer |
| Signature | Notation signature, Cosign signature | Registry/referrer or signature service per format |
| Release manifest | JSON recording digest, commit, build ID, and environment | S3, release metadata store, or Git release record |

Pipeline artifacts and deployed artifacts are not necessarily the same file. CodePipeline may pass a ZIP between actions while ECS runs an ECR image and Lambda runs a ZIP deployment package. Link these artifacts together using digests/checksums and a release manifest.

### 2.1. Build Once, Promote Many Times

A key principle is **build once, promote the same artifact across environments**:

1. Build from a specific source commit.
2. Run tests, scan, and generate SBOM/provenance.
3. Publish an immutable artifact/image.
4. Sign the artifact or image.
5. Verify signatures and policies before deploying to test.
6. Promote that exact digest to staging and production.
7. Change only environment configuration, secret references, and IAM roles.

If you rebuild in each environment, the JAR/image can differ due to dependency resolution, build time, toolchain, or base image changes. Staging results would no longer prove the exact production artifact.

~~~mermaid
flowchart TD
    SRC["Source commit"] --> BUILD["Isolated build"]
    BUILD --> TEST["Tests + security scans"]
    TEST --> SBOM["SBOM + provenance"]
    SBOM --> IMAGE["Immutable artifact / image digest"]
    IMAGE --> SIGN["Sign digest"]
    SIGN --> VERIFY["Verify signature + policy"]
    VERIFY --> DEV["Deploy dev"]
    DEV --> STAGE["Promote same digest to staging"]
    STAGE --> APPROVE["Release approval"]
    APPROVE --> PROD["Promote same digest to production"]
    PROD --> TRACE["Deployment record + audit trail"]
~~~

### 2.2. Artifacts Must Have Owners and Lifecycles

Every artifact repository needs an owner, retention period, access policy, encryption policy, and deletion process. Do not keep all build artifacts forever; also do not delete artifacts still referenced by production or rollback plans.

## 3. Version Identifiers: Version, Tag, Digest, and Checksum

A human-readable version label is not necessarily an immutable content identifier.

| Identifier | Example | Characteristics |
|---|---|---|
| Semantic version | `2.4.1` | Human-readable, expresses release compatibility by convention |
| Git commit SHA | `4f31c8...` | Identifies the source revision |
| Build ID | `codebuild:orders-api:1842` | Identifies a single build execution |
| Image tag | `orders-api:2.4.1` | Lookup label; may be mutable if the registry allows |
| Image digest | `sha256:...` | Hash of the image manifest; identifies exact content |
| File checksum | SHA-256 of JAR/ZIP | Checks whether a file has changed |

### 3.1. A Tag Is Not a Digest

Example:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
~~~

This is an image tag. If tags are mutable, a later push can point that tag to a different image. URI using a digest:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:0123456789abcdef...
~~~

A digest identifies the manifest bytes and is the identifier to use for deployments, signature verification, and release records. If the image manifest changes, the digest changes too.

### 3.2. Tag Strategy

A repository can use:

- Version tag: `2.4.1`.
- Commit tag: `sha-4f31c8a`.
- Build tag: `build-1842`.
- Environment label: `production` for lookup convenience only, never as the deployment identity.

Do not rely on `latest` as the sole version. Tags like `production` or `stable` may be updated for lookup convenience, while deployment manifests must pin the exact digest.

### 3.3. Semantic Versions and Commit Identity

Semantic versions typically follow `MAJOR.MINOR.PATCH`:

- `MAJOR`: changes that may break compatibility.
- `MINOR`: backward-compatible new functionality.
- `PATCH`: backward-compatible bug fixes.

Semantic versioning is a release convention; by itself it does not prove source or artifact origin. Bind the version to a commit SHA, build ID, and digest for complete identity.

### 3.4. Verifying Checksums for JAR/ZIP

Generate a checksum after building:

~~~bash
sha256sum target/orders-api.jar > target/orders-api.jar.sha256
cat target/orders-api.jar.sha256
~~~

Verify when downloading the artifact:

~~~bash
sha256sum --check orders-api.jar.sha256
~~~

Checksums detect when file contents diverge from a recorded hash. If an attacker can alter both the artifact and the checksum simultaneously, a checksum does not prove trusted origin. To prove provenance, you need a digital signature or attestation verified against an independent trust policy.

## 4. Storing Artifacts on Amazon S3

Amazon S3 commonly stores CodePipeline artifacts, Lambda deployment packages, IaC templates, test reports, SBOMs, provenance, and release manifests.

### 4.1. Designing an Artifact Bucket

A production artifact bucket should:

- Enable Block Public Access at the account/bucket level.
- Enable versioning to support recovery and auditing.
- Use default SSE-KMS encryption when clear key ownership/auditing is required.
- Use a bucket policy restricting access to required CodePipeline/CodeBuild/deploy roles and accounts.
- Enable appropriate logging/auditing.
- Use lifecycle policies to manage noncurrent versions and temporary artifacts.
- Enable Object Lock when WORM/compliance retention is required and designed.
- Separate release artifacts from build scratch/intermediate files.

### 4.2. SSE-S3 vs. SSE-KMS

| Mechanism | Meaning | When to choose |
|---|---|---|
| SSE-S3 | S3 manages encryption keys | Basic encryption-at-rest needs |
| SSE-KMS | Encryption via AWS KMS key | Need key policies, auditing, cross-account control, or customer-managed keys |
| DSSE-KMS | Dual-layer server-side encryption with KMS as supported | Specialized data protection/compliance requirements |

Encryption at rest protects stored contents under key access controls. It **does not prove who built the artifact**, does not replace signatures, and does not prevent overwrites by principals with write permissions.

### 4.3. S3 Versioning and Object Keys

Structure keys clearly:

~~~text
releases/orders-api/2.4.1/orders-api.jar
releases/orders-api/2.4.1/orders-api.jar.sha256
releases/orders-api/2.4.1/sbom.cdx.json
releases/orders-api/2.4.1/provenance.intoto.jsonl
releases/orders-api/2.4.1/release-manifest.json
~~~

Never reuse the same key to overwrite an already-published release artifact. S3 versioning preserves multiple object versions, yet consumers still retrieve the latest version unless they pin `VersionId`. Release manifests should record the object key, `VersionId` where appropriate, and SHA-256.

### 4.4. S3 Object Lock

S3 Object Lock provides WORM retention with governance or compliance modes plus legal holds. The bucket must have versioning enabled. Governance mode lets principals with special permissions bypass retention; compliance mode is stricter and prevents deleting or overwriting versions before retention expires.

Use Object Lock for release evidence/audit archives when immutable retention is required. Do not enable long-term retention indiscriminately on all build outputs; it increases storage costs and blocks cleanup during the lock period.

### 4.5. Cross-Account and Cross-Region Artifact Access

When pipelines span multiple accounts/Regions, verify all of these together:

- S3 bucket policy for the target principal.
- KMS key policy/grants for encrypt/decrypt.
- IAM permissions of the pipeline/action role.
- Artifact store in the matching Region for actions.
- Data transfer and replication costs.
- `VersionId`/checksum after copying.

S3 replication does not replace integrity/provenance verification. After copying, verify checksums and signatures in the destination account/Region.

## 5. Amazon ECR: Managing Container Images

Amazon Elastic Container Registry (ECR) stores OCI/Docker images and related image artifacts. ECR supports private repositories, repository policies, image tag mutability, lifecycle policies, scanning, and replication.

### 5.1. Repository Strategy

Repositories can be organized by service:

~~~text
orders-api
payments-api
inventory-worker
notification-service
~~~

Or separated by environment/account when access boundaries differ. Avoid creating numerous repositories per commit; use tags/digests to manage versions.

### 5.2. Enabling Tag Immutability

Tag immutability prevents an existing tag from being overwritten by another image. This is a useful guardrail for release tags such as versions or commit SHAs.

Example creating a repository with immutable tags:

~~~bash
aws ecr create-repository \
  --repository-name orders-api \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --region ap-southeast-1
~~~

This example uses ECR's AES256 encryption option; if a customer-managed KMS key is needed, choose KMS encryption configuration and grant matching key permissions. For existing repositories, use `update-repository` or IaC. Scan-on-push is just one scanning setting; verify ECR scanning mode and Amazon Inspector coverage per requirements.

Tag immutability does not replace digest pinning and does not stop an image from being deleted by an IAM principal or lifecycle policy. When using image signing, check the behavior of the active signing mode/OCI reference format. ECR currently supports managed signing and manual signing; older registry/signing integrations had limitations around tag immutability. Production deployments should always use digests.

Compatibility note: older AWS documentation for OCI 1.0-based signature flows noted restrictions with tag immutability. ECR now supports OCI 1.1 reference types and managed signing. When choosing manual signing or specific Notation/plugin versions, test tag immutability together with the signing flow on a test repository before rolling out to production.

### 5.3. Logging In and Pushing Images

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com

docker build -t orders-api:2.4.1 .
docker tag orders-api:2.4.1 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
docker push 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
~~~

Log into the registry hostname, not the repository URI. In CodeBuild, the role needs ECR authorization token and upload actions on the repository; never store Docker passwords in the buildspec.

### 5.4. Retrieving the Digest After Push

~~~bash
aws ecr describe-images \
  --repository-name orders-api \
  --image-ids imageTag=2.4.1 \
  --region ap-southeast-1 \
  --query 'imageDetails[0].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt}' \
  --output json
~~~

Save the returned `imageDigest` in the release manifest and deployment inputs. For multi-architecture manifest lists, the digest of the manifest list is the referenced image identifier; account for platform-specific child manifests when inspecting runtime behavior.

### 5.5. Tag Immutability and Digests Together

Tag immutability prevents overwriting a tag; digest pinning ensures consumers reference exact content. Use both:

- Immutable release tags for operator lookup.
- Digests in task definitions/Kubernetes manifests for deployment.
- Signatures/attestations attached to the digest.
- Release manifests linking the digest to source/build/test evidence.

Tag immutability does not prevent deletion by authorized principals or lifecycle policies. IAM/repository policies and retention controls remain essential.

### 5.6. ECR Lifecycle Policies

Lifecycle policies expire untagged images or older images by tag prefix/age/count. Protect:

- Release tags currently running in production.
- Digests referenced by rollback plans.
- Images with signatures/SBOMs/provenance needed for audits.
- Base images consumed by downstream builds.

Before applying a lifecycle policy, run a preview and verify rule priorities and tag statuses. A misconfigured policy can delete images needed for production recovery.

### 5.7. ECR Replication

ECR replication copies images across repositories, accounts, or Regions per configuration. Use replication to distribute images to deployment accounts/Regions without rebuilding.

After replication:

1. Verify destination repository and digest.
2. Verify tag mapping and image manifest.
3. Verify signatures/OCI referrers exist at the destination.
4. If signature artifacts were not copied as expected by the registry/client, copy/reattach/re-sign following a provenance-preserving procedure.
5. Verify trust policies and run verification at the destination before deploying.

Do not assume image replication automatically replicates all external SBOM/provenance objects and trust configurations.

### 5.8. Signature Artifacts and Quotas/Lifecycles

Signatures stored in an ECR repository also count toward the repository's image/artifact quota. When a subject image is deleted by a lifecycle policy, ECR may automatically clean up associated reference artifacts within 24 hours per ECR behavior. Therefore:

- Factor signature artifacts into repository quotas.
- Do not delete subject images while signatures are still needed for verification/rollback.
- Align lifecycle rules with subject images and rollback retention.
- If storing SBOM/provenance outside ECR, apply independent retention to those evidence objects.

## 6. AWS CodeArtifact for Package Dependencies

CodeArtifact is a package repository service supporting formats such as Maven, npm, PyPI, NuGet, and Swift per service documentation. For Java applications, CodeArtifact can proxy public Maven repositories and store internal libraries.

### 6.1. Separating Dependency Packages from Release Images

CodeArtifact stores build package inputs such as internal Java SDKs; ECR stores deployable container images. S3 can store JARs, SBOMs, reports, and release metadata. Each store has its own IAM access and retention policies.

### 6.2. Maven Settings and Authentication

CodeArtifact provides Maven repository endpoints and authorization tokens. Build roles need permission to read package repositories and fetch tokens. Tokens expire; use CLI/credential helpers or auto-refresh mechanisms in the build environment instead of hard-coding tokens in `settings.xml`.

### 6.3. Dependency Pinning

- Pin dependency versions in `pom.xml`/Gradle build scripts.
- Control repositories and upstream sources.
- Do not use dynamic versions/`SNAPSHOT` in production releases without clear controls.
- Scan dependencies and store SBOMs.
- Separate package publish permissions from dependency read permissions.

CodeArtifact helps control package sources, yet does not by itself prove a dependency is safe. SCA, signatures/provenance where available, license reviews, and vulnerability policies are still required.

## 7. Software Bill of Materials (SBOM)

An **SBOM** is a structured inventory of components in a piece of software: libraries, modules, package versions, and related metadata. SBOMs help determine whether an application uses dependencies affected by a CVE or license issue.

### 7.1. Common Formats

| Format | Characteristics | Use case |
|---|---|---|
| SPDX | ISO/IEC standard for software package/component/license metadata | License compliance, inventory, and supply chain |
| CycloneDX | SBOM standard focused on software/hardware components and vulnerability data | Dependency inventory, security analysis |

Choose one format as the canonical release output, or produce both if consumers require them. Record format versions and tool versions so parsers process them accurately.

### 7.2. Generating an SBOM for Java

Example Maven CycloneDX plugin:

~~~xml
<plugin>
  <groupId>org.cyclonedx</groupId>
  <artifactId>cyclonedx-maven-plugin</artifactId>
  <version>2.9.1</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals>
        <goal>makeAggregateBom</goal>
      </goals>
    </execution>
  </executions>
</plugin>
~~~

The plugin version is illustrative; pick a vetted version and pin it in the build. Generate the BOM:

~~~bash
mvn -B clean verify
mvn -B cyclonedx:makeAggregateBom
~~~

The output file is typically generated in `target`, such as `bom.json` or `bom.xml` depending on plugin configuration. Verify actual outputs and ensure the BOM describes the packaged release artifact rather than unpackaged source dependencies alone.

### 7.3. Generating an SBOM for Container Images

Use Syft or an approved SBOM tool to scan the image by digest:

~~~bash
syft 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST \
  -o cyclonedx-json=orders-api.cdx.json
~~~

The digest is a placeholder. Bind the SBOM to the exact image digest, not just a tag. If an image is rebuilt/rebased, generate a new SBOM because OS packages and layers may have changed.

### 7.4. An SBOM Is Not a Security Scan

An SBOM describes components; it does not assert those components are vulnerability-free. Use SBOMs as input to vulnerability scanners, license analysis, and incident response. An SBOM can be schema-valid while missing components if the scanner cannot inspect certain layers or runtime dependencies.

### 7.5. Binding the SBOM to the Artifact

Record:

- Subject digest of the image/package.
- SBOM format/version.
- Generating tool and tool version.
- Source commit/build ID.
- Timestamp.
- SBOM file digest.

Store SBOMs in S3 with the release manifest or publish them as OCI artifacts/referrers alongside the image if supported by the registry/client. Consumers must verify the subject digest to avoid reading an SBOM from another image tag.

## 8. Build Provenance and Attestations

**Provenance** records how an artifact was produced: source repository/revision, builder identity, build invocation, materials/dependencies, and output digest. An attestation is a structured, signed or integrity-protected statement that consumers verify.

### 8.1. SBOM vs. Provenance

| | SBOM | Provenance |
|---|---|---|
| Question | Which components does the artifact contain? | Where and by what process was the artifact built? |
| Data | Packages/components/versions/licenses | Source, builder, invocation, materials, output digest |
| Users | Security, licensing, incident response | Release engineering, platform security, compliance |
| Link | Subject artifact digest | Subject artifact digest |

The two documents complement each other. An SBOM does not prove a build pipeline is trustworthy; provenance does not replace vulnerability/license analysis.

### 8.2. What Should Provenance Record?

- Source repository URL and immutable commit SHA.
- Build system/project/pipeline identity.
- Build execution ID and invocation parameters with secrets scrubbed.
- Builder image/toolchain versions.
- Dependency/material references and checksums.
- Output artifact digest.
- Timestamp and build environment metadata.
- Test/scan evidence references.

Never place secrets, access tokens, private environment variables, or customer data inside attestations.

### 8.3. SLSA and in-toto

SLSA (Supply-chain Levels for Software Artifacts) provides a framework for evaluating supply-chain assurance levels. in-toto provides a metadata/attestation model for build steps and materials. Provenance can be generated in SLSA/in-toto formats and signed by a trusted signing identity.

Do not claim a SLSA level solely because JSON provenance exists. Assurance depends on builder isolation, source controls, build service identity, tamper resistance, reproducibility, and verification policies required by that level.

### 8.4. Release Manifest

The release manifest links the artifact to build evidence:

~~~json
{
  "schemaVersion": "1.0",
  "service": "orders-api",
  "releaseVersion": "2.4.1",
  "source": {
    "repository": "https://github.com/example-org/orders-api",
    "commit": "4f31c8a0123456789abcdef0123456789abcdef01"
  },
  "build": {
    "provider": "AWS CodeBuild",
    "project": "orders-api-release",
    "buildId": "orders-api-release:1842"
  },
  "artifact": {
    "type": "oci-image",
    "uri": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api",
    "digest": "sha256:REPLACE_WITH_REAL_DIGEST"
  },
  "evidence": {
    "sbom": "s3://orders-release-evidence/releases/2.4.1/sbom.cdx.json",
    "provenance": "s3://orders-release-evidence/releases/2.4.1/provenance.intoto.jsonl"
  }
}
~~~

Values are placeholders. In real releases, the digest must be the actual digest; object keys must point to uploaded evidence, and evidence checksums should be recorded in the manifest/attestation. A manifest is not inherently trustworthy unless signed or integrity-protected.

## 9. Digital Signatures for Container Images

Image signatures let consumers verify that an image was signed by an organization-trusted identity and that the signed content has not been altered. Signatures typically attach to an image digest rather than a mutable tag.

### 9.1. What Does a Signature Prove?

When verification succeeds, consumers verify:

- The signature is valid per algorithm and trust chain.
- The signature covers the exact requested digest.
- The signer certificate/profile is accepted by the trust policy.
- The signature satisfies configured policies for signer, repository, and timestamp.

A signature **does not by itself prove** that source code is secure, tests passed, SBOMs are complete, or the build environment was uncompromised. Those require provenance, test evidence, scanners, and build controls.

### 9.2. Why Sign a Digest Instead of a Tag?

Tags can be reassigned to point to another image. Digests are content-addressable identifiers of manifests. Signing a mutable tag allows consumers to pull different content than what the signer reviewed. Pipelines must resolve the tag to a digest, sign the digest, and deploy that exact digest.

### 9.3. Signing and Encryption Are Two Different Mechanisms

| Mechanism | Purpose | Example |
|---|---|---|
| Encryption | Protect contents from actors lacking the key | ECR/S3 encryption, SSE-KMS |
| Hash/checksum | Detect contents differing from a known digest | SHA-256 |
| Digital signature | Verify integrity and signing identity | AWS Signer + Notation |
| Provenance attestation | Describe source/builder/materials/output | in-toto/SLSA |
| SBOM | List components | SPDX/CycloneDX |

A KMS key used to encrypt artifacts is not automatically a signing key. If using an asymmetric KMS key with Cosign, configure the signing workflow, key usage, and verification accordingly.

## 10. AWS Signer and Notation

AWS Signer is a managed code-signing service. For container images, AWS Signer integrates with **Notation** via the AWS Signer plugin for Notation. Notation is a tool for signing and verifying OCI artifacts using a trust store/trust policy model.

### 10.1. Components in the Signing Flow

| Component | Role |
|---|---|
| AWS Signer signing profile | Configures the profile used for signing |
| AWS Signer plugin for Notation | Connects Notation CLI to AWS Signer |
| Notation CLI | Signs and verifies OCI images/signatures |
| ECR repository | Stores images and signature artifacts/referrers per registry support |
| Trust store | Stores certificate chains/trust anchors trusted by verifiers |
| Trust policy | Specifies accepted signers/identities and verification rules |
| CI signing role | Least-privilege permission to invoke the signing profile |
| Deployment verifier | Checks signatures before allowing images to run |

### 10.2. Signing Profiles and Signer Identity

Create signing profiles following organizational processes and select the platform matching Notation/OCI image signing. A signing profile defines the signing identity/certificate and validity period per AWS Signer settings. Permission to use the profile must be restricted to approved pipeline signing roles.

Do not allow every developer or every CodeBuild project to sign production images. Separate build/test roles from signing roles so only artifacts passing required gates are signed.

### 10.2.1. ECR Managed Signing

Amazon ECR now supports **managed signing**, recommended by AWS for most use cases. When a signing configuration is set on a private registry, ECR automatically generates signatures using AWS Signer upon image push. A signing configuration references one or more signing profiles and can filter repositories by name/pattern.

Key characteristics to remember:

- Configured at the private registry level; no need to install the Notation plugin in every build job solely to sign.
- Multiple signing rules can restrict which repositories are signed by which profiles.
- The principal pushing the image needs ECR upload permissions and `signer:SignPayload` on the matching signing profile.
- ECR managed signing uses the identity of the principal performing the image push as the signing identity for the operation.
- The signing profile must be in the same Region as the ECR registry; managed signing supports cross-account signing with matching configuration/trust.
- Managed signing signs images on push; the pipeline must still scan/verify and block deployment if quality gates fail.

Example signing configuration:

~~~json
{
  "rules": [
    {
      "signingProfileArn": "arn:aws:signer:ap-southeast-1:444455556666:/signing-profiles/orders-image-profile",
      "repositoryFilters": [
        {
          "filter": "orders-*",
          "filterType": "WILDCARD_MATCH"
        }
      ]
    }
  ]
}
~~~

Apply the configuration:

~~~bash
aws ecr put-signing-configuration \
  --region ap-southeast-1 \
  --signing-configuration file://signing-config.json

aws ecr get-signing-configuration --region ap-southeast-1
~~~

Profile names, accounts, and filters are examples. Before applying, review rule scope and permissions; a signing configuration can affect every repository matching the filter in the registry.

Managed signing does not mean an image passed vulnerability scans or approvals. If policy requires signing only after scans pass, use manual signing after quality gates or design an additional pipeline gate; never allow deployment solely because ECR created a signature.

### 10.2.2. ECR Manual Signing

Manual signing uses the Notation CLI and AWS Signer plugin to sign images already in ECR. Choose this approach when you need explicit control over when signing occurs, such as after scans, SBOMs, and approvals pass. Manual signing requires client tools, registry authentication, signer permissions, and ECR permissions.

### 10.3. Installing Notation and the AWS Signer Plugin

Install Notation CLI and the AWS Signer Notation plugin following official release instructions. Pin CLI/plugin versions in the build image or tool container; never download unverified binaries/plugins on every build. Verify the plugin is installed and at the expected version before signing.

Example checks:

~~~bash
notation version
notation plugin ls
~~~

Plugin names and installation methods depend on the AWS-supported release. Use exact packages/checksums/release artifacts from AWS Signer documentation; do not assume the plugin is preinstalled on every CodeBuild image.

### 10.4. Signing Images with Notation

Illustrative commands after configuring the plugin and signing profile:

~~~bash
aws ecr get-login-password --region "$AWS_REGION" |
  notation login --username AWS --password-stdin "$ECR_REGISTRY"

notation sign "$IMAGE_URI" \
  --plugin com.amazonaws.signer.notation.plugin \
  --id "$SIGNING_PROFILE_ARN"
~~~

`IMAGE_URI` must point to an image digest already pushed to the registry; `SIGNING_PROFILE_ARN` is the approved profile; `ECR_REGISTRY` is the registry hostname. Notation needs registry credentials to push signatures and read images during verification. You can use the ECR Docker credential helper instead of `notation login` if properly configured. Never sign a mutable tag and then rebuild or retag different content.

### 10.5. Storing Signatures in the Registry

Notation creates signature artifacts linked to the subject image via the OCI artifact/referrer model. The registry must support storing and returning signature artifacts. Amazon ECR supports OCI 1.1 reference artifacts/referrers; ECR replication supports copying referrers alongside images when workflows and configurations are compatible.

After replication, still verify signatures/referrers in the destination repository and run verification in the target account/Region. When using registries or copy tools other than ECR replication, confirm signatures were transferred; if missing, re-publish/copy signatures per procedure rather than skipping verification.

### 10.6. Trust Store and Trust Policy

Verifiers need trust anchors/certificate chains and a policy specifying which signers are accepted. Trust policies can scope registry/repository paths and signer identities. Never use a single permissive trust policy accepting any signer across all production repositories.

Trust configuration is part of deployment security policy; version-control and review changes to trust roots/policies as code.

### 10.7. Verifying Images

Example:

~~~bash
notation verify "$IMAGE_URI"
~~~

`IMAGE_URI` should be a digest reference. `verify` uses the trust store/trust policy configured in the Notation environment. If verification fails, the pipeline must stop deployment and record the error reason; never bypass signature checks with an arbitrary flag in production.

### 10.8. AWS Signer and CodeBuild IAM

The CodeBuild signing role needs only the AWS Signer permissions matching the plugin/API workflow plus ECR image/referrer access. Scope ECR read/write permissions to the target repository. Check plugin documentation for exact actions; never grant `signer:*` or `ecr:*` account-wide if signing only one repository.

## 11. Cosign and AWS KMS as an Alternative

Cosign is a tool in the Sigstore ecosystem supporting container image and attestation signing. Cosign can use AWS KMS asymmetric keys as a signing backend.

### 11.1. When to Choose Cosign

Cosign fits when an organization already enforces Sigstore-based policies/tooling, needs Cosign-format image and attestation signing/verification, or integrates with Cosign-capable admission controllers. AWS Signer + Notation fits when using AWS managed signing profiles and the Notation OCI workflow.

Do not mix two signature formats without defining verifiers and trust policies for each. Consumers must know which signature type to verify.

### 11.2. Signing with AWS KMS

Cosign supports KMS URIs for AWS KMS asymmetric keys. Illustrative syntax:

~~~bash
cosign sign \
  --key "awskms://arn:aws:kms:ap-southeast-1:444455556666:key/REPLACE_WITH_KEY_ID" \
  "$IMAGE_URI"
~~~

Replace the ARN with an asymmetric KMS key configured for signing key usage; `IMAGE_URI` must pin a digest. Verify using the public key or KMS-aware verification config per your Cosign version. Check current Cosign/AWS KMS documentation for URI syntax and supported algorithms.

### 11.3. KMS Key Policies and Separation of Duties

- Signing roles are permitted to sign using the exact key ARN.
- Verification systems have permission to read required public keys/metadata.
- Key administrators are not the same as release approvers.
- Key deletion/disablement actions require controls and auditing.
- Key rotation/replacement requires trust policies to accept older signatures during the retention window if historical verification is needed.

Do not casually reuse an S3 encryption key as a signing key. Separating key purposes reduces blast radius and clarifies policies.

## 12. Where Should Signatures Be Verified?

Signatures only help when verification runs before an artifact is trusted.

### 12.1. Verifying in the Pipeline

Pipelines can verify after signing and before deploying:

1. Resolve the release image digest.
2. Locate the signature/referrer for that digest.
3. Verify the certificate chain/trust policy.
4. Verify signer identity and repository scope.
5. Verify SBOM/provenance attestations if required by policy.
6. Allow the deployment action to run only if all required checks pass.

### 12.2. Verifying at the Deployment Boundary

| Runtime | Typical enforcement approach |
|---|---|
| ECS | CodePipeline/CodeDeploy pre-deploy verification action or deployment wrapper verifying digest/signature before updating task definitions |
| EKS | Admission controller/policy engine verifying image signatures before Pods are created |
| Lambda container image | Verify image/signature in the release pipeline before updating the function; Lambda execution does not replace release verification |
| EC2/container host | Deployment agent/orchestrator verifies before pulling/running images per platform policy |

Do not assume ECS or Lambda automatically rejects unsigned images merely because images reside in ECR. Design appropriate enforcement points.

### 12.3. EKS Admission Policy

On EKS, an admission controller such as Kyverno can verify image signatures/attestations depending on version and plugin support. Admission policies should:

- Require images to be referenced by digest or enforce digest resolution.
- Restrict allowed registries/repositories.
- Accept only approved signer identities/trust roots.
- Enforce attestation/SBOM policies where appropriate.
- Block unsigned/untrusted images in production namespaces.
- Run audit mode or test namespaces before switching to enforce mode.

Example policies depend on Kyverno version and signature format; never apply generic manifests without cluster testing.

### 12.4. Fail Closed or Fail Open?

For production workloads requiring supply-chain assurance, verification failures must fail closed: reject the image. During migrations, audit-only mode can run briefly with clear owners, expirations, and scope. Never leave permanent exceptions that hollow out signing policies.

## 13. Lambda Code Signing for Deployment Packages

For Lambda ZIP deployment packages, AWS offers **Lambda Code Signing** integrated with AWS Signer. This is a code-package signing flow distinct from Notation image signing for OCI container images.

### 13.1. Code Signing Configuration

A Lambda code signing configuration specifies trusted signing profiles and the policy for invalid packages:

- **Warn:** logs validation failures while allowing deployment to proceed per configuration.
- **Enforce:** rejects deployment packages failing validation.

Production should use `Enforce` once the signing workflow is deployed and tested. If using `Warn` during migration, set a deadline to switch to `Enforce`.

### 13.2. Comparing the Three Flows

| Artifact | Signing approach | Verification boundary |
|---|---|---|
| Container image in ECR | AWS Signer + Notation or Cosign/KMS | Pipeline, EKS admission, or deployment wrapper |
| Lambda ZIP package | AWS Signer Lambda code signing | Lambda code signing configuration |
| JAR/WAR stored in S3 | JAR signing/checksum/provenance per toolchain | Pipeline/deployment agent/application packaging |

Never rely on a Lambda code signing configuration to assume ECR container images are signed. Pick the signing format and enforcement mechanism matching the artifact type.

## 14. End-to-End Pipeline: Build, Evidence, Sign, and Publish

A pipeline can be divided into these stages:

| Stage | Action | Output |
|---|---|---|
| Source | Checkout immutable commit | Source revision |
| Build | Compile/package/container build | JAR/image |
| Test | Unit/integration/contract tests | Test reports |
| Scan | SCA/SAST/container/IaC/secret scans | Scan reports |
| SBOM | Generate SPDX/CycloneDX | SBOM tied to digest |
| Provenance | Record builder/source/materials | Provenance attestation |
| Publish | Push image/publish package/upload S3 artifact | Immutable artifact digest |
| Sign | Sign exact digest | Signature/referrer |
| Verify | Verify signature, provenance, and policy | Verification evidence |
| Promote | Deploy same digest across environments | Deployment record |

### 14.1. Signing Order

Sign after the artifact is finalized and mandatory gates have passed:

1. Build the final image.
2. Push the image so the registry assigns the digest.
3. Scan the image by digest.
4. Generate SBOM and provenance for that digest.
5. Sign the digest and/or sign the attestation.
6. Verify the signature and evidence.
7. Publish the release manifest linking the digest and evidence.
8. Deploy.

If the image changes after signing, the new digest differs and the old signature no longer validates the new image. Rebuilds/rebases require fresh evidence and signatures.

### 14.2. Never Let Build Jobs Auto-Sign Arbitrary Outputs

Isolate the signing stage as a conditional action/job:

- Accept artifacts only from an identified build execution.
- Verify test/scan statuses.
- Sign only allowed repositories/digests.
- Use a dedicated signing role.
- Record profile/key ARN and signing request ID.
- Never allow fork pull requests to use the production signing role.

### 14.3. Illustrative Buildspec Generating Evidence

~~~yaml
version: 0.2

phases:
  build:
    commands:
      - mvn -B clean verify
      - mvn -B cyclonedx:makeAggregateBom
      - sha256sum target/orders-api.jar > target/orders-api.jar.sha256
  post_build:
    commands:
      - mkdir -p release-evidence
      - cp target/orders-api.jar release-evidence/
      - cp target/orders-api.jar.sha256 release-evidence/
      - cp target/bom.json release-evidence/sbom.cdx.json
      - printf '%s\n' "$CODEBUILD_RESOLVED_SOURCE_VERSION" > release-evidence/source-commit.txt

artifacts:
  files:
    - release-evidence/**/*
~~~

This buildspec is a fragment; the SBOM path must match the plugin's actual output. This buildspec does not push images, sign artifacts, or generate SLSA-compliant provenance yet. Those steps require corresponding actions/tools once the digest is established.

## 15. Release Manifests and Deployment Records

The release manifest is central metadata linking artifacts with evidence and deployments. It should be created once per release candidate, with environment-specific deployment records appended separately without altering artifact identity.

### 15.1. Recommended Fields

| Category | Fields |
|---|---|
| Release | service, version, release ID, timestamp |
| Source | repository, commit SHA, branch/tag |
| Build | CodeBuild project/build ID, builder image/toolchain |
| Artifact | type, repository URI, digest, checksum, size |
| Evidence | SBOM URI/digest, provenance URI/digest, scan report |
| Signature | signer profile/key identity, signature reference, verification result |
| Deployment | account, Region, cluster/service/function, image digest, deployment ID |
| Approval | change ticket, approver, approval timestamp |

### 15.2. One Artifact, Many Deployment Records

Do not mutate the digest in the release manifest for each environment. Create separate deployment records referencing the release ID/digest:

~~~json
{
  "releaseId": "orders-api-2.4.1-1842",
  "environment": "staging",
  "account": "444455556666",
  "region": "ap-southeast-1",
  "artifactDigest": "sha256:REPLACE_WITH_REAL_DIGEST",
  "deploymentTarget": "ecs/orders-staging",
  "deploymentId": "d-EXAMPLE",
  "status": "SUCCEEDED",
  "deployedAt": "2026-11-20T04:00:00Z"
}
~~~

Values are examples. Deployment records should be append-only or protected by versioning/retention; never overwrite a staging record to turn it into production. One release can have many records across multiple accounts/Regions.

### 15.3. Never Store Secrets in Manifests

A manifest may record secret ARNs/references or parameter paths if allowed, but never `SecretString`, passwords, or tokens. Avoid recording customer data, private environment variables, or build commands containing secrets.

### 15.4. Where to Store Manifests?

- S3 release evidence bucket with SSE-KMS/versioning/retention.
- Git release tags/release metadata if the manifest contains no sensitive information.
- Artifact repository or OCI referrer attached to the image.
- Deployment system metadata/CloudWatch Logs indexed by release ID.

Multiple copies may be kept for auditing, provided there is a canonical source and checksum so manifests cannot conflict.

## 16. Promoting Across Accounts and Regions

Promotion moves the exact same verified artifact from a lower environment to a higher environment. Promotion is not rebuilding.

### 16.1. Promotion Flow

~~~mermaid
flowchart TD
    BUILD["Build once in CI account"] --> PUSH["Publish image digest"]
    PUSH --> SB["SBOM + provenance + signature"]
    SB --> VERIFY["Verify evidence"]
    VERIFY --> DEV["Dev account"]
    DEV --> STAGE["Staging account"]
    STAGE --> APPROVE["Production approval"]
    APPROVE --> COPY["Replicate/copy exact image digest"]
    COPY --> VERIFY2["Verify digest + signature at destination"]
    VERIFY2 --> PROD["Production account"]
    PROD --> RECORD["Append deployment record"]
~~~

### 16.2. ECR Replication and Destination Verification

ECR replication copies images to destination repositories. Destination deployments require:

- Digest identical to the source release.
- Repository policy allowing the deployment role to pull.
- Accessible and verifiable signatures/referrers.
- Trust store/policy accepting the signer identity.
- Scan policies meeting destination security requirements.
- KMS/encryption and replication settings aligned with the target account/Region.

If signature referrers are missing at the destination, do not skip verification; replicate/copy signatures per the registry format and tooling in use.

### 16.3. Cross-Account KMS and IAM

The pipeline account can sign using an AWS Signer profile or KMS key. Target accounts need sufficient permissions to read images/evidence and verify trust chains. When using KMS public-key verification, distribute public keys/certificates and trust metadata through controlled channels; verifiers do not need signing permissions.

### 16.4. Approval-Gated Promotion

Production approvals should display:

- Release version, commit SHA, and build ID.
- Image digest and registry URI.
- Signature verification result and signer identity.
- Links to SBOM/provenance/scan reports.
- Staging deployment ID and test results.
- Change ticket, target account/Region, and rollback plan.

Never approve based solely on an image tag or a green pipeline indicator.

## 17. Artifact Retention, Rollback, and Disaster Recovery

Artifact retention is part of recovery strategy. If a production rollback needs an older image that a lifecycle policy already deleted, the team cannot restore the exact version.

### 17.1. Defining Retention by Data Type

| Artifact | Retention decision |
|---|---|
| Temporary build workspace | Short, clean up after build |
| Failed build logs/reports | Per debugging/audit policy |
| Release JAR/image | At least the rollback window and compliance period |
| SBOM/provenance/signatures | Keep at least as long as release evidence |
| IaC templates/change set evidence | Per change management/audit policy |
| Deployment records | Per compliance/incident investigation needs |
| Signing certificates/trust metadata | Retain long enough to verify historical signatures |

### 17.2. Retaining Active Artifacts

Before ECR lifecycle rules expire an image:

- Check digests referenced by ECS task definitions or EKS manifests.
- Check Lambda container image versions if applicable.
- Check rollback windows and release history.
- Verify signatures/SBOMs/provenance remain accessible.
- Check cross-account/Region copies.

### 17.3. S3 Lifecycle and Noncurrent Versions

Lifecycle rules can transition objects to cheaper storage classes or expire temporary artifacts and noncurrent versions. Ensure retention never deletes evidence needed for audits or release packages needed for restores. S3 Object Lock retention/legal holds can block lifecycle expiration until unlocked or expired.

### 17.4. ECR Backup/Copy Strategy

ECR replication does not substitute for backup policies across every failure mode. Consider:

- Cross-account/Region replication.
- Repository policies and lifecycle rules.
- Image digest inventories.
- Signature/referrer retention.
- Rebuild reproducibility and base image availability.
- Runbooks for recovering from a deleted repository/account or lost access.

When copying images through another registry, verify digests and signatures at the destination. Do not assume registry migrations always preserve every OCI referrer.

### 17.5. Rolling Back to the Exact Artifact

Rollback records must point to a previously deployed and verified release digest. Never rely on `production` or `stable` tags if those tags can move. Before rolling back:

1. Identify the prior release version and digest.
2. Verify the image still exists in the registry and its signature still verifies.
3. Confirm runtime config and IAM roles remain compatible.
4. Check database schema and event compatibility.
5. Deploy the old digest per rollback runbook.
6. Record a new deployment record with action type `ROLLBACK`.

## 18. Managing Signing Keys, Certificates, and Trust Policies

A signing identity is only trustworthy when its lifecycle is managed. Define who can create profiles/keys, who can sign, who can modify trust roots, and who can verify.

### 18.1. Separation of Duties

| Role | Responsibility | Should not hold by default |
|---|---|---|
| Build role | Build/test/scan/publish image | Sign production releases or alter trust policies |
| Signing role | Sign approved digests | Alter source code or build outputs |
| Release approver | Approve promotion | Administer signing keys |
| Deployment role | Deploy verified digests | Sign images or edit trust stores |
| Trust administrator | Manage trust roots/policies | Self-approve releases |
| Auditor | Read evidence/logs | Modify artifacts/signatures |

Separating duties prevents a single compromised pipeline from altering an artifact, signing it itself, and deploying without independent checks.

### 18.2. AWS Signer Profile Lifecycle

Manage signing profiles as production security assets:

- Profile name/ARN and signing platform are versioned in IaC/change records.
- Only the signing role can invoke signing operations on the profile.
- Monitor profile status, certificate validity, and expiration.
- Rotate profiles/certificates according to a rotation plan.
- Retain older trust chains during the window required to verify historical releases.
- Revoke trust per incident response when compromise is detected.

### 18.3. Certificate Expiration and Historical Verification

A signature may be created while a certificate is valid and verified months later. Trust policies must specify how timestamps, certificate expiration, and revocation are handled per signing format/tool. Retain signing metadata, certificates, and verification evidence for historical audits.

Do not immediately delete an old trust anchor upon issuing a new certificate if older releases still require verification/rollback. Conversely, if a key is compromised, revoke trust immediately per incident policy and re-evaluate artifacts signed during the exposure window.

### 18.4. KMS Key Rotation

KMS automatic rotation supports specific key types/configurations; it does not apply identically to asymmetric signing keys. For asymmetric signing, perform key/profile rotation by creating a new key, distributing the new public key/certificate, updating trust policies, and preserving verification capability for older signatures. Do not assume enabling automatic rotation on encryption keys handles signing keys.

### 18.5. Incident Response When a Signing Identity Is Compromised

1. Halt pipelines/jobs using the signer identity.
2. Disable/revoke the profile/key or signing permissions per runbook.
3. Identify the exposure time window, repositories, and signed digests.
4. Inspect CloudTrail/Signer audit records and pipeline logs.
5. Remove the signer from trust policies if necessary.
6. Rebuild and re-sign required releases with a new identity.
7. Re-verify/redeploy artifacts; consider redeploying all at-risk workloads.
8. Preserve incident evidence and strengthen trust policies/controls.

## 19. Traceability and Audit Trails

Traceability must work in both directions:

- Forward from a source commit to every built artifact and running environment.
- Backward from a production digest to source, build, tests, signer, and approvals.

### 19.1. Traceability Chain

~~~mermaid
flowchart LR
    COMMIT["Git commit"] --> BUILD["CodeBuild execution"]
    BUILD --> TEST["Test / scan evidence"]
    BUILD --> DIGEST["Artifact digest"]
    DIGEST --> SBOM["SBOM"]
    DIGEST --> PROV["Provenance"]
    DIGEST --> SIG["Signature"]
    SBOM --> MANIFEST["Release manifest"]
    PROV --> MANIFEST
    SIG --> MANIFEST
    MANIFEST --> DEPLOY["Deployment record"]
    DEPLOY --> RUNTIME["ECS / EKS / Lambda runtime"]
~~~

### 19.2. Using CloudTrail

CloudTrail can audit relevant API actions:

- CodePipeline create/update/start execution.
- CodeBuild start build/project modifications.
- ECR image push/delete and repository policy changes per event coverage.
- AWS Signer profile/signing API actions.
- KMS key policy/administration events.
- IAM role/policy/trust changes.
- ECS/EKS/Lambda/CloudFormation deployments.
- S3 artifact object operations per management/data event configuration.

Do not assume every S3 object read/write or every ECR data-plane action is logged unless the appropriate event types are enabled. Check CloudTrail event selectors, data events, organization trails, retention, and access controls.

### 19.3. CloudWatch Logs and Metrics

CodeBuild logs record build phases, commands, and errors; pipeline execution history records action statuses; deployment services record deployment events. Use correlation IDs:

- Pipeline execution ID.
- CodeBuild build ID.
- Source commit SHA.
- Image digest.
- Signing profile/key identity.
- Deployment ID.
- ECS task definition revision/EKS rollout revision/Lambda version.

Never write secret values, access tokens, private signing material, or customer payloads into logs.

### 19.4. Deployment Inventory

You should be able to query:

- Which digest is each service/environment currently running?
- Which commit built that digest?
- Where are its SBOM/provenance/signature?
- Which actor/role signed it?
- Which trust policy version verified the signature?
- Which accounts/Regions received the release?
- What are the deployment ID and rollback target?

Aggregate this from release manifests, deployment records, ECR image metadata, ECS task definitions, Kubernetes manifests, and Lambda versions. Never rely on mutable tags or image names displayed in dashboards.

### 19.5. Evidence Retention

Retain evidence per policy:

- Release manifest and digest.
- SBOM/provenance/signature references.
- Test/security scan reports.
- Approval/change tickets.
- Pipeline/build/deployment IDs.
- Verification results and trust policy version.
- CloudTrail/CloudWatch references.

Evidence must remain sufficient for investigation even after source branches are deleted or build projects change.

## 20. Securing Artifact Repositories and Signing Workflows

### 20.1. Access Control

- Developers have read access to needed release artifacts; write access is restricted to build/publish roles.
- Signing roles sign only artifacts from trusted pipelines.
- Deployment roles only pull/verify artifacts, never overwrite them.
- Repository administrators are separated from release approvers.
- S3 bucket/ECR repository policies are scoped by account, role, and repository.
- Cross-account permissions are opened only to approved pipeline/deployment accounts.

### 20.2. Protecting the Build Environment

Artifact signatures cannot save a pipeline if the build environment is compromised before signing. You must:

- Isolate untrusted pull request builds from production secrets and signing roles.
- Pin CodeBuild images and toolchains.
- Restrict network egress whenever possible.
- Review buildspec changes as privileged code.
- Never run shell scripts from untrusted dependencies with signer permissions.
- Scan build images and rotate build environments during incidents.
- Use short-lived credentials and IAM roles.

### 20.3. Preventing Artifact Overwrites and Deletions

Tag immutability, S3 versioning, bucket policies, and Object Lock reinforce one another:

| Control | Mitigates risk of |
|---|---|
| ECR immutable tags | Release tags being overwritten |
| Digest pinning | Deployments pulling wrong content via mutable tags |
| S3 versioning | Object loss from overwrites/deletions |
| S3 Object Lock | Object version deletion/modification within retention windows |
| IAM/bucket/repository policies | Unauthorized principals altering/deleting artifacts |
| CloudTrail | Auditing who performed each action |

No single control replaces all the others.

### 20.4. Encryption and Access to Signing Material

Private signing keys must never be exported or committed to source. AWS Signer manages signing operations within the service model; with KMS, key material stays inside KMS. Verifiers need public keys/certificates/trust metadata, never private signing keys.

### 20.5. Image Scanning and Signing Policies

An image should be signed only after passing required quality gates. However, vulnerability databases evolve over time; an image signed yesterday may have newly disclosed CVEs today. Periodically rescan running images and apply remediation policies. A signature proves identity/integrity at signing time—it does not guarantee an image remains vulnerability-free forever.

## 21. Testing Verification and Policies

Verification policies must be tested for both valid and invalid cases.

### 21.1. Minimum Test Cases

| Test | Expected result |
|---|---|
| Image digest has signature from approved signer | Verification passes |
| Unsigned image | Rejected at production gate |
| Signature from untrusted signer | Rejected |
| Signature subject digest differs from deployed image | Rejected |
| Image altered after signing | Digest mismatch/verification fails |
| Signature artifact deleted | Rejected or policy reports missing signature |
| SBOM subject digest mismatches image | Rejected if policy requires SBOM |
| Provenance from unapproved builder | Rejected |
| Image copied to another account without signature | Rejected, requires evidence recovery |
| Certificate/trust anchor expired or revoked | Handled per trust policy, never silently bypassed |

### 21.2. Testing Negative Paths

Do not test only valid images. Push unsigned images or forged signatures into a test repository to prove the deployment gate genuinely blocks them. If using an EKS admission policy, confirm the Pod is rejected before the container starts. For ECS/Lambda, test the pipeline pre-deploy verification action.

### 21.3. Testing Trust Policy Changes

Changes to a trust store/policy can stop older releases from verifying. Test:

- Adding a new signer while keeping the old signer during a migration window.
- Revoking the old signer.
- Changing repository scope.
- Verifying artifacts in destination Regions/accounts.
- Rolling back to an older digest after key rotation.

### 21.4. No Uncontrolled Signature Bypasses

Any emergency bypass needs:

- An incident/change ticket.
- An independent approver.
- Specific repository/digest/environment scope.
- An expiration time.
- Audit logging.
- A remediation/re-signing plan.

Never introduce an environment variable like `SKIP_SIGNATURE_VERIFY=true` on a production pipeline without guardrails and approvals.

## 22. Hands-On: Publish, Sign, Verify, and Trace an ECR Image

This lab demonstrates the workflow from a built image to release evidence. You need an AWS test account, an ECR repository, a CodeBuild/CLI identity with appropriate permissions, the Notation CLI, and the AWS Signer plugin. Never use a production signing profile in labs.

### 22.1. Create a Test Repository

~~~bash
aws ecr create-repository \
  --repository-name orders-api-lab \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --region ap-southeast-1
~~~

If the repository already exists, inspect its configuration instead of recreating it. In a lab, default ECR encryption is fine; in production, select encryption/KMS per policy.

### 22.2. Build and Push the Image

~~~bash
REGISTRY="444455556666.dkr.ecr.ap-southeast-1.amazonaws.com"
REPOSITORY="$REGISTRY/orders-api-lab"
TAG="lab-$(git rev-parse --short HEAD)"

aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin "$REGISTRY"

docker build -t "orders-api-lab:$TAG" .
docker tag "orders-api-lab:$TAG" "$REPOSITORY:$TAG"
docker push "$REPOSITORY:$TAG"
~~~

The account ID is a placeholder. The repository has tag immutability enabled; if `TAG` already exists, the push will be rejected. Use a unique tag derived from commit/build ID.

### 22.3. Resolve the Digest

~~~bash
IMAGE_DIGEST="$(aws ecr describe-images \
  --repository-name orders-api-lab \
  --image-ids imageTag="$TAG" \
  --region ap-southeast-1 \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

IMAGE_URI="$REPOSITORY@$IMAGE_DIGEST"
printf '%s\n' "$IMAGE_URI"
~~~

Confirm `IMAGE_DIGEST` is non-empty and starts with `sha256:`. From this point onward, use `IMAGE_URI` for scanning, SBOM generation, signing, verification, and deployment.

### 22.4. Scan and Generate the SBOM

Wait for ECR scanning to finish and check findings against your severity policy. Generate the SBOM from the exact digest:

~~~bash
syft "$IMAGE_URI" -o cyclonedx-json=orders-api-lab.cdx.json
sha256sum orders-api-lab.cdx.json > orders-api-lab.cdx.json.sha256
~~~

Store the SBOM/checksum in the release evidence bucket or publish an OCI artifact/referrer. Record the subject digest in metadata.

### 22.5. Sign and Verify

Once the signing profile, Notation plugin, trust store, and trust policy are configured, log Notation into ECR and sign the exact digest:

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  notation login --username AWS --password-stdin "$REGISTRY"

notation sign "$IMAGE_URI" \
  --plugin com.amazonaws.signer.notation.plugin \
  --id "$SIGNING_PROFILE_ARN"

notation verify "$IMAGE_URI"
~~~

The example uses manual signing. `REGISTRY` is the registry hostname; the signing profile and plugin Region must match the ECR registry's Region. You can use the ECR Docker credential helper instead of `notation login`. Do not deploy if signing or verification fails. Record the signing profile identity and verification result in the release manifest.

### 22.6. Create the Release Manifest

~~~bash
cat > release-manifest.json <<EOF
{
  "service": "orders-api",
  "releaseVersion": "$TAG",
  "sourceCommit": "$(git rev-parse HEAD)",
  "imageUri": "$IMAGE_URI",
  "sbom": "orders-api-lab.cdx.json",
  "signatureVerified": true,
  "signingProfile": "$SIGNING_PROFILE_ARN"
}
EOF
~~~

This is a lab script; in production, serialize JSON with a proper tool/library to avoid escaping bugs, validate fields, and sign/protect the manifest. Never place secret values in the file. Store the manifest with SBOM/provenance and deployment records.

### 22.7. Deploy the Same Digest

In the ECS task definition or EKS manifest, set the image URI to `IMAGE_URI`. Do not resolve the tag again in production. After deployment, inspect the running task definition/Pod spec to confirm runtime uses the exact digest.

## 23. Troubleshooting Artifacts and Signatures

| Symptom | Possible cause | How to investigate |
|---|---|---|
| ECR push denied | Build role lacks upload actions or repository policy blocks it | Caller identity, repository ARN, ECR permissions |
| Tag already exists | Repository enables `IMMUTABLE` and tag was reused | Generate unique tags per commit/build ID |
| Digest differs between staging/prod | Rebuild, mutable tag, or wrong image copied | Release manifest, source/destination digests |
| Signature not found | Signing incomplete, referrer not copied, or registry client lacks support | ECR referrers, `notation inspect`/`list`, replication behavior |
| Notation plugin fails to load | Plugin not installed, version/OS mismatch | `notation plugin list`, plugin release/checksum |
| AWS Signer `AccessDenied` | Signing role lacks action/profile access or wrong trust config | CloudTrail, role policy, profile ARN/Region |
| `notation verify` fails | Trust store/policy mismatch, cert expired/revoked, wrong subject digest | Verification error, trust policy, signature metadata |
| `cosign verify` fails | Wrong KMS key ARN/public key/trust configuration | Cosign version, key URI, certificate/identity claims |
| SBOM subject mismatch | SBOM generated from another tag or image was rebuilt | SBOM metadata, image digest, build ID |
| Provenance rejected | Builder/source identity outside allowlist or invalid attestation schema | Attestation subject, predicate, trust policy |
| ECS deploys unsigned image | Pipeline verification action skipped or deploy ran outside pipeline | ECS task definition, IAM permissions, release logs |
| EKS admission rejects Pod | Policy does not trust signer/repository or signature missing | Admission events, policy report, trust store |
| Rollback image cannot be pulled | ECR lifecycle deleted digest or cross-account policy changed | ECR `describe-images`, lifecycle, repository policy |
| S3 artifact checksum mismatch | Object altered/wrongly copied or manifest points to wrong version | S3 `VersionId`, checksum, CloudTrail data events |
| Signature expired/fails historical verify | Trust root/certificate deleted or policy changed | Historical trust chain, timestamp, revocation policy |

### 23.1. Investigating Digest Mismatches

1. Read the digest in the release manifest.
2. Check ECR `describe-images` by tag and digest.
3. Check source/destination replication.
4. Read the running task definition/Pod spec.
5. Check pipeline artifact mappings and parallel executions.
6. Never edit the manifest to match the wrong image; identify the correct artifact and redeploy using the exact digest.

### 23.2. Investigating Signature Verification Failures

Check in order:

1. Does the image digest match the signed digest?
2. Is the signature/referrer present in the current repository/Region?
3. Does the Notation plugin or Cosign version support the signature format?
4. Does the trust store contain the needed certificate chain/public key?
5. Does the trust policy accept the signer identity and repository scope?
6. Do certificate validity, timestamp, and revocation status satisfy the policy?
7. Do IAM/network permissions allow the verifier to read metadata/signatures?

Never resolve verification failures by disabling verification. Fix the trust configuration or republish evidence properly.

### 23.3. Deleted Artifacts

If an image needed for rollback is no longer in ECR:

- Identify the digest from the release manifest/deployment record.
- Check replica repositories or backups/copies.
- If a copy exists, verify its digest/signature before using it.
- If no copy exists, evaluate a reproducible rebuild from pinned source and dependencies; a rebuilt artifact will have a new digest and must be re-scanned and re-signed.
- Update retention policies and rehearse restores.

Never claim a rebuilt artifact is byte-identical unless reproducible builds have been verified.

## 24. Costs and Retention Optimization

Artifact management can generate long-term storage and data transfer costs. Balance retention, rollback windows, audit requirements, and cost.

| Component | Cost drivers | Optimization |
|---|---|---|
| S3 artifact store | Storage, requests, replication, KMS API usage | Lifecycle rules, tiering, cleanup temporary artifacts |
| S3 Object Lock | Retained object versions cannot be deleted early | Apply only to evidence requiring WORM |
| ECR | Image layers, replication, scan features, transfer | Deduplicate layers, lifecycle rules, retain releases |
| CodeArtifact | Package storage, requests, upstream data transfer | Caching and retention for obsolete package versions |
| AWS Signer/KMS | Signing operations, KMS requests/key usage per pricing | Sign needed release artifacts, right-size key/profile usage |
| CodeBuild | Build minutes for SBOM/scan/sign stages | Cache dependencies, avoid duplicate stage runs |
| CloudWatch/CloudTrail | Logs, data events, metrics, retention | Select event coverage and retention based on risk |
| Cross-Region | Image/evidence replication and transfer | Replicate only to genuinely needed Regions |

### 24.1. Retention Aligned with Release Policy

Define:

- How many recent releases must stay online?
- How long is the rollback window?
- Which evidence must be kept for compliance?
- Which artifacts can transition storage classes?
- When can failed/temporary build artifacts be deleted?
- Who approves deleting deployed releases?

### 24.2. Never Delete Referenced Images

Lifecycle policies must account for older ECS task definitions, EKS manifests/rollout history, Lambda versions, blue/green deployment windows, and release rollback targets. You can maintain allowlists/tag prefixes for releases to retain, while keeping the digest as the deployment identity.

### 24.3. Cost of Signing and Scanning

You do not need to sign every intermediate build image if it is never deployed. You can scan at multiple stages while signing only release candidates that pass gates. If policy requires signing every build, separate signing profiles for non-production and production to preserve trust boundaries.

## 25. Scenario Exercises

### Scenario A — Production Tag Overwritten

A new build pushes the `production` tag to ECR. The ECS service still uses a tag-based image URI, so task replacement pulls a different image from what was tested in staging.

**Question:** How should the release mechanism change?

**Hint:** Enable tag immutability on release repositories, store the digest in the manifest, and deploy by digest. Use the `production` tag only as a lookup label, not as the deployment identity.

### Scenario B — Valid Signature Yet Image Has a Critical CVE

An image was signed by AWS Signer and verifies cleanly, yet ECR scanning detects a critical vulnerability after a CVE database update.

**Question:** Can the image still be trusted solely because its signature is valid?

**Hint:** A signature proves only identity/integrity per trust policy. Rescanning, vulnerability policies, and remediation are still required. A signature does not prove an image stays safe forever.

### Scenario C — SBOM Belongs to Another Image

The release manifest points to image digest B, yet the SBOM was generated from an image tag before a rebuild (digest A).

**Question:** How do you detect and prevent this?

**Hint:** Generate the SBOM after the final digest is pushed or bind the exact subject digest; verify the SBOM subject in a pipeline gate. Never use mutable tags as the link.

### Scenario D — Signing an Image Before Scanning

The pipeline signs an image immediately after `docker push`. Later, the vulnerability scan fails, yet the deploy stage still runs due to misconfigured stage dependencies.

**Question:** How should the pipeline be structured?

**Hint:** Scans and required quality gates must pass before signing/approval; deployment accepts artifacts only from a successful verification stage. Separate the signing role from the build role and never invoke it from untrusted PR jobs.

### Scenario E — Image Replicated Without Signature

An image digest was replicated to the production account, yet `notation verify` reports no signature found.

**Question:** Can verification be skipped because the digest matches the source?

**Hint:** No. Check OCI referrers/signature replication and repository support. Copy/reattach the signature per procedure, then verify at the destination; matching digests do not replace signer proof.

### Scenario F — AWS Signer Certificate Rotated

A team issues a new signing profile/certificate and immediately deletes the old trust anchor. An incident requires rolling back to an image signed with the old certificate.

**Question:** How should trust rotation be managed?

**Hint:** Retain the old trust chain throughout the retention/rollback window and test historical verification. Revoke immediately on compromise per incident policy, while planned rotations require controlled overlap.

### Scenario G — Both Checksum and Artifact Replaced

An actor with S3 write permissions replaces both the JAR and the `.sha256` file simultaneously. Checksum verification still passes.

**Question:** What additional controls are needed?

**Hint:** A checksum does not authenticate origin if an attacker can modify both files. Use signatures/provenance with an independent trust root, S3 bucket policies/Object Lock, separate write/sign roles, and CloudTrail auditing.

### Scenario H — Production Redeploys a Mutated Tag

Staging and production use the same `2.4.1` tag, yet the registry tag was updated accidentally between the two deployments.

**Question:** Why does "same tag" not prove "same artifact"?

**Hint:** Tags can be mutable. Release manifests need digests; promotion uses the tested digest. Enable immutable tags and verify digests at every destination.

### Scenario I — Build Role Self-Signs Artifacts Without Approval

A CodeBuild project running pull requests has permissions for the production Signer profile. An attacker modifies the buildspec to sign their own image.

**Question:** How should permissions be separated?

**Hint:** PR build roles have no signer permissions; the signing stage accepts artifacts only from protected pipelines after tests/scans/approvals. Scope profiles/repositories and audit signing operations.

### Scenario J — S3 Object Lock Blocks Cleanup

A lifecycle policy attempts to delete release evidence, yet objects are under compliance retention.

**Question:** How should this be handled?

**Hint:** Compliance retention cannot be bypassed early. Design retention before enabling Object Lock, separate temporary artifacts from WORM evidence, and monitor storage costs and expirations.

### Scenario K — Rollback Image Missing from ECR

A lifecycle policy deletes older images after 14 days, yet a production incident occurs on day 30 requiring rollback.

**Question:** How should retention change?

**Hint:** Retain images for at least the rollback window and compliance period, replicate to a backup repository, protect running/referenced digests, and rehearse restores.

### Scenario L — EKS Admission Policy Checks Only Tags

An admission policy allows any image tag starting with `production-`, yet tags can be overwritten.

**Question:** How do you increase assurance?

**Hint:** Require digest pinning, verify signatures/referrers, and enforce signer identity/repository scope. A tag prefix is not a trust identity.

### Scenario M — Provenance Exists from an Untrusted Builder

An attestation records the right source commit and digest, yet was produced by a build host that developers can modify freely.

**Question:** Is provenance alone enough to approve?

**Hint:** Evaluate builder identity/isolation, access controls, immutable build images, source protections, and attestation signing. Syntactically valid metadata does not prove the builder was secure.

### Scenario N — KMS Encryption Key Mistaken for a Signing Key

A team enables SSE-KMS on ECR/S3 and assumes artifacts are signed.

**Question:** What is missing?

**Hint:** Encryption at rest protects storage; a separate signing workflow, digest-bound signatures, and verifier trust policies are needed. Only a properly configured asymmetric KMS signing flow performs signing.

### Scenario O — Signature Verification Passes in Staging but Fails in Production

The production account lacks the new trust anchor and the destination ECR repository does not contain the signature referrer.

**Question:** What must be added to the promotion checklist?

**Hint:** Distribute trust roots/policies to the destination, verify referrers after replication, check IAM/networking, and run verification inside the target account/Region prior to deployment.

## 26. Production Checklist

- [ ] Every release has a source commit SHA, build ID, semantic version, and artifact digest.
- [ ] Build once and promote the exact same artifact across environments.
- [ ] JAR/ZIP files have checksums; checksums are never treated as a substitute for digital signatures.
- [ ] S3 artifact buckets block public access and configure versioning, encryption, bucket policies, and lifecycles.
- [ ] S3 Object Lock is enabled only after retention/compliance requirements are designed.
- [ ] ECR release repositories enable immutable tags appropriately.
- [ ] ECS/EKS/Lambda container deployments pin image digests, never using `latest`/mutable tags as identity.
- [ ] ECR scanning/Inspector findings are handled per severity policy.
- [ ] ECR lifecycles do not delete running images or images within the rollback window.
- [ ] ECR replication is verified for digests and signatures/referrers at the destination.
- [ ] CodeArtifact package versions/upstream sources are controlled.
- [ ] SPDX/CycloneDX SBOMs are generated from the final artifact/image and bound to the subject digest.
- [ ] Provenance records source, builder, invocation, materials, and output digest.
- [ ] SBOM/provenance artifacts have checksums, retention, and access policies.
- [ ] AWS Signer/Notation or Cosign signing profiles/keys are managed via IaC/change control.
- [ ] Signing roles are separated from build, approval, and deployment roles.
- [ ] Signing runs only after required tests/scans and against published digests.
- [ ] Signatures bind to the exact digest and verify against a trust policy.
- [ ] Trust stores/policies restrict signer identity and repository scope.
- [ ] EKS admission policies verify signatures before Pods run when required by architecture.
- [ ] ECS/Lambda have pipeline verification gates before deployment.
- [ ] Lambda ZIP code signing uses a Lambda Code Signing Configuration with enforced policy.
- [ ] KMS encryption keys and signing keys have distinct purposes and permissions.
- [ ] Certificate/key rotation preserves historical verification throughout the rollback window.
- [ ] An incident response plan exists for signer/key compromise.
- [ ] Release manifests link digests, SBOMs, provenance, signatures, and deployment records.
- [ ] Deployment records are appended per environment/account/Region.
- [ ] CloudTrail audit coverage matches S3/ECR/Signer/KMS/IAM operations.
- [ ] Logs/manifests contain no secrets, tokens, or customer data.
- [ ] Artifact retention covers rollback, auditing, and compliance windows.
- [ ] Negative tests cover unsigned images, untrusted signers, wrong digests, missing referrers, and revoked trust.
- [ ] Artifact restores, cross-account promotion, signature verification, and rollbacks have been rehearsed.

## 27. Takeaways

**An artifact is what gets built and deployed; a digest identifies content; a signature verifies signer identity and integrity; an SBOM describes components; provenance explains how the artifact was built; and a release manifest links all that evidence to deployment.**

On AWS, use S3 for pipeline/release evidence, ECR for container images, CodeArtifact for packages, KMS for encryption/key operations, and AWS Signer with Notation or Cosign/KMS for image signing per your trust model. Enable ECR tag immutability, deploy by digest, generate SBOM/provenance from the exact final artifact, and verify signatures before releasing. For Lambda ZIPs, use Lambda Code Signing Configurations; for EKS, consider admission verification; for ECS/Lambda containers, place verification gates in the deployment pipeline.

Keep the same artifact digest across dev/staging/prod, store release manifests and deployment records, manage trust/key lifecycles, and retain artifacts long enough for rollbacks and audits. Encryption does not replace signing, checksums do not replace provenance, signatures do not prove code is vulnerability-free, and code rollbacks do not automatically restore data. A trustworthy supply chain requires build isolation, least privilege, immutable artifacts, signed evidence, verification enforcement, and end-to-end audit trails.

### Official AWS and Standards Documentation for Reference

- [Amazon ECR User Guide](https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html) — repositories, images, and registries.
- [ECR image tag mutability](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html) — immutable/mutable tags.
- [ECR lifecycle policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html) — retention and image expiration.
- [ECR replication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/replication.html) — cross-account/Region replication.
- [ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) — scan configuration and findings.
- [AWS Signer User Guide](https://docs.aws.amazon.com/signer/latest/developerguide/Welcome.html) — signing profiles and code signing.
- [AWS Signer container image signing](https://docs.aws.amazon.com/signer/latest/developerguide/image-signing-steps.html) — signing profiles, Notation plugin, sign, and verify.
- [Amazon ECR image signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing.html) — managed signing and manual signing.
- [Amazon ECR managed signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/managed-signing.html) — automatic signing on image push and repository filters.
- [Amazon ECR manual signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing-manual.html) — client-side signing with Notation.
- [AWS Signer image-signing prerequisites](https://docs.aws.amazon.com/signer/latest/developerguide/image-signing-prerequisites.html) — installing Notation/plugin, registry authentication, and IAM permissions.
- [Notation documentation](https://notaryproject.dev/docs/) — signing, verification, trust stores, and policies.
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — WORM retention and legal holds.
- [Amazon S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) — object versions and recovery.
- [AWS KMS key types](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html) — symmetric/asymmetric keys and key usage.
- [AWS CodeArtifact User Guide](https://docs.aws.amazon.com/codeartifact/latest/ug/welcome.html) — package repositories.
- [AWS Lambda code signing](https://docs.aws.amazon.com/lambda/latest/dg/governance-code-signing.html) — signing profiles and enforcement when deploying ZIP packages.
- [Amazon EKS image verification](https://docs.aws.amazon.com/eks/latest/userguide/security.html) — workload security context; admission policies are deployed per cluster toolchain.
- [SPDX specification](https://spdx.github.io/spdx-spec/) — SBOM format.
- [CycloneDX specification](https://cyclonedx.org/specification/overview/) — SBOM format.
- [SLSA specification](https://slsa.dev/spec/v1.0/) — supply-chain levels and provenance.
- [in-toto attestation framework](https://github.com/in-toto/attestation) — attestation model.
- [Sigstore Cosign](https://docs.sigstore.dev/cosign/overview/) — container image signing and verification.
- [AWS CloudTrail User Guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — API auditing and event history.
