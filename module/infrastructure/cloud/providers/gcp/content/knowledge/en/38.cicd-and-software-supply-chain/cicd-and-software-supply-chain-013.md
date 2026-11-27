# Binary Authorization and Attestations in the Release Chain

A successfully built container image is not automatically eligible to run in production. Organizations may require that images be built by a trusted pipeline, pass tests, receive QA approval, or satisfy a security process prior to release. Relying solely on tag names like `latest` or manual checks makes it hard for deployment platforms to independently verify whether the requested image truly passed those steps.

**Binary Authorization** is a deploy-time enforcement control on Google Cloud. It evaluates images against policies and can block images that do not meet requirements. A common pattern uses **attestations**: digitally signed claims bound to an image digest confirming that a process or authorized party approved that image.

In the **CLOUD_PROVIDERS_GCP** module, Binary Authorization connects CI/CD workflows with container runtimes such as Google Kubernetes Engine (GKE) and Cloud Run. It enables development teams to automate releases, security teams to manage signers and attestors, and operations teams to govern which images are allowed into production environments.

After this lesson, you will be able to:

- Distinguish between image digest, signer, attestor, attestation, Artifact Analysis note, and policy.
- Describe the build, attestation signing, verification, and deployment workflow.
- Create an attestor and associate a public key with it.
- Create an attestation for an image digest using Cloud KMS.
- Configure a policy requiring attestations and test policies using dry-run mode.
- Organize IAM permissions following a separation-of-duties model.
- Apply Binary Authorization to GKE, Cloud Run, and integrate with Cloud Build.
- Investigate rejected deployments and handle breakglass according to procedure.

## 1. What Problem Does Binary Authorization Solve?

A container delivery chain typically passes through several stages:

1. Developers push source code to a repository.
2. CI checks code, runs unit tests, scans dependencies, and builds the container image.
3. The image is pushed to Artifact Registry.
4. QA or security pipelines inspect the image and build results.
5. CD deploys the image to dev, staging, canary, and then production.

If someone can build an image locally, swap a tag, and deploy straight to production, earlier checks could be bypassed. Binary Authorization creates an enforcement gate at the deployment platform: an image is admitted only when the project's policy allows it.

Binary Authorization does not decide on its own whether an image is secure. The organization defines the criteria to satisfy, who has authority to certify them, and which processes are trusted. Binary Authorization verifies the evidence required by policy before allowing an image to deploy.

For example, a production policy may require simultaneously:

- The image was built by Cloud Build or a trusted CI pipeline.
- The image passed integration tests.
- The image was approved by QA or the security team.

An image missing any required attestation will be blocked when the policy is in enforce mode.

## 2. Core Concepts

| Concept | Role | How to Understand It |
|---|---|---|
| Container image | Controlled object | Image stored in Artifact Registry or a compatible registry |
| Digest | Immutable identifier of image content | String formatted as `sha256:...` pinpointing the exact image manifest |
| Signer | Entity creating signatures and claims | Human, CI pipeline, or QA system authorized to sign |
| Attestation | Digitally signed claim | Confirms an image digest completed a process |
| Artifact Analysis note | Metadata describing the attestor | Note resource linked to an attestor |
| Attestor | Verification authority | Holds the note and public key so Binary Authorization verifies signatures |
| Artifact Analysis occurrence | Attestation record | Record created when an attestation is attached to a note |
| Policy | Deployment rules | Defines which images are permitted or denied |
| Deployer | Platform or project requesting deployment | E.g., GKE cluster or Cloud Run service |

Signer and attestor are two distinct roles. The signer uses a private key to sign claims. The attestor holds the corresponding public key to verify signatures at deploy time. Private keys do not need to—and must not—be distributed to the deployment platform.

An Artifact Analysis note identifies the attestor's metadata. When an attestation is created, the system creates an occurrence linked to that note. Binary Authorization looks up attestations and uses the attestor's public key to validate signatures.

### What Does an Attestation Certify?

An attestation is an explicit claim. Examples:

- Image digest X was built by pipeline release-prod.
- Image digest X passed integration test suite 2026.11.
- Image digest X was approved by QA for production deployment.

Binary Authorization verifies the signature and attestor per policy. It does not re-run tests, scan source code, or inspect the semantic truth of the claim itself. An attestation's trustworthiness depends on the trustworthiness of the signer and the process authorizing that signer.

## 3. Why Must You Use Image Digests?

Tags like `latest`, `stable`, or `release-2026-11` can be reassigned to different images. Signing a tag and deploying that tag after it moved could result in running a different image than the one approved.

A digest is the content identifier of an image manifest. After building and pushing an image, retrieve the actual digest from Artifact Registry, then create an attestation for the image in the form:

~~~text
asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api@sha256:IMAGE_DIGEST
~~~

Binary Authorization uses the digest to look up attestations at deploy time. Therefore, deployment manifests should specify digests rather than mutable tags.

One attestation can apply to the same image digest stored in multiple locations or registries. Although the image path appears in the signed payload, the digest determines the verified image content. This helps when a verified image is mirrored to another registry without altering its content.

Never attest an image merely because a repository name or tag looks right. Obtain the digest from build/push output, verify it belongs to the right pipeline artifact, and sign that digest.

## 4. Architecture and Verification Flow

A basic architecture can operate within a single project. When security duties must be separated, use separate projects for the deployment environment, attestors, and attestations.

~~~mermaid
flowchart TD
    A["Source repository"] --> B["Cloud Build: build, test, scan"]
    B --> C["Artifact Registry: image + digest"]
    C --> D["Signer / release pipeline"]
    D --> E["Sign attestation with private key"]
    E --> F["Artifact Analysis: occurrence"]
    G["Attestor: note + public key"] --> H["Binary Authorization policy"]
    F --> H
    H --> I["GKE or Cloud Run requests deploy"]
    I --> J{"Policy and signature valid?"}
    J -->|Pass| K["Allow deployment"]
    J -->|Fail| L["Deny and write audit log"]
~~~

Sequential flow:

1. CI builds the image and pushes it to the registry.
2. CI retrieves the digest of the newly created image.
3. Verification checks execute on that artifact.
4. The signer creates an attestation for the digest using a securely managed private key.
5. The attestation is stored as an occurrence attached to an Artifact Analysis note.
6. At deploy time, Binary Authorization reads the project's policy and required attestations.
7. The attestor verifies signatures using its registered public key.
8. If the image satisfies the policy, the platform allows deployment; otherwise, the request is denied and the reason is logged.

Binary Authorization supports GKE, Cloud Run, Cloud Service Mesh, and Google Distributed Cloud. Specific enforcement mechanisms and rule types vary by platform.

## 5. Creating an Attestor and Managing Signing Keys

### 5.1. Enabling Required APIs

In your test project, enable Binary Authorization, Artifact Analysis, and deployment platform APIs. If using Artifact Registry and Cloud KMS, enable those APIs as well.

~~~bash
gcloud services enable \
  binaryauthorization.googleapis.com \
  containeranalysis.googleapis.com \
  artifactregistry.googleapis.com \
  cloudkms.googleapis.com \
  --project=PROJECT_ID
~~~

For GKE, also enable `container.googleapis.com`. For Cloud Build, enable `cloudbuild.googleapis.com`. The operator needs permission to enable services, typically via `serviceusage.services.enable`.

### 5.2. Creating an Artifact Analysis Note

A note describes attestor metadata. Example creating a note named `release-approval-note` in the attestor project:

~~~json
{
  "name": "projects/ATTESTOR_PROJECT_ID/notes/release-approval-note",
  "attestation": {
    "hint": {
      "human_readable_name": "Release approval attestor"
    }
  }
}
~~~

Save the payload above into `note_payload.json`, then call the Artifact Analysis API:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-binary @note_payload.json \
  "https://containeranalysis.googleapis.com/v1/projects/ATTESTOR_PROJECT_ID/notes/?noteId=release-approval-note"
~~~

Binary Authorization uses the Artifact Analysis global endpoint. Do not configure notes in regional storage or call regional endpoints for this attestation flow.

### 5.3. Creating the Attestor

Create the attestor in the project containing the note:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors create release-approval \
  --attestation-authority-note=release-approval-note \
  --attestation-authority-note-project=ATTESTOR_PROJECT_ID
~~~

The attestor now references the note, but cannot verify signatures until a public key is added.

### 5.4. Using Cloud KMS to Hold the Private Key

In production, use Cloud KMS to hold private keys and perform signing operations. Private keys never need to be downloaded onto build machines. Create a key ring and an asymmetric signing key:

~~~bash
gcloud kms keyrings create binauthz-keyring \
  --location=global \
  --project=KMS_PROJECT_ID

gcloud kms keys create release-signing-key \
  --location=global \
  --keyring=binauthz-keyring \
  --purpose=asymmetric-signing \
  --default-algorithm=ec-sign-p256-sha256 \
  --protection-level=software \
  --project=KMS_PROJECT_ID
~~~

This example uses ECDSA P-256 with SHA-256. Organizations can choose protection levels and key management mechanisms matching their security policies.

Add the corresponding public key to the attestor:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors public-keys add \
  --attestor=release-approval \
  --keyversion-project=KMS_PROJECT_ID \
  --keyversion-location=global \
  --keyversion-keyring=binauthz-keyring \
  --keyversion-key=release-signing-key \
  --keyversion=1
~~~

The command returns the public key ID. You can retrieve the ID later with:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors describe release-approval \
  --format="value(userOwnedGrafeasNote.publicKeys[0].id)"
~~~

The public key ID identifies the key inside the attestor. When creating an attestation with `sign-and-create`, Binary Authorization uses the Cloud KMS key version and attestor metadata to sign, store, and verify the signature.

Restrict `cloudkms.cryptoKeyVersions.useToSign` permission to the pipeline identity authorized to sign. Do not grant key-signing rights to all developers or every build job. The security team should manage attestor public keys, while signers receive only scoped permission to use the key version per duty.

## 6. Creating an Attestation for an Image Digest

Suppose Cloud Build built the checkout API image and pushed it to Artifact Registry. The build result provides the digest:

~~~bash
IMAGE_PATH=asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api
IMAGE_DIGEST=sha256:REPLACE_WITH_REAL_DIGEST
IMAGE_TO_ATTEST=$IMAGE_PATH@$IMAGE_DIGEST
~~~

Never use placeholder digest strings in production commands. Obtain the real digest from push output or Artifact Registry.

Use the Cloud KMS key version to sign and create the attestation:

~~~bash
gcloud container binauthz attestations sign-and-create \
  --project=ATTESTATION_PROJECT_ID \
  --artifact-url="$IMAGE_TO_ATTEST" \
  --attestor=release-approval \
  --attestor-project=ATTESTOR_PROJECT_ID \
  --keyversion-project=KMS_PROJECT_ID \
  --keyversion-location=global \
  --keyversion-keyring=binauthz-keyring \
  --keyversion-key=release-signing-key \
  --keyversion=1 \
  --validate
~~~

The `--validate` flag checks that the newly created attestation can be verified by the configured attestor. In a multi-project setup, the identity creating the attestation needs:

- `roles/containeranalysis.notes.attacher` on the attestor's Artifact Analysis note.
- `roles/containeranalysis.occurrences.editor` on the project storing attestations.
- Appropriate signing permission on the Cloud KMS key version.

You can list attestations:

~~~bash
gcloud --project=ATTESTATION_PROJECT_ID \
  container binauthz attestations list \
  --attestor=release-approval \
  --attestor-project=ATTESTOR_PROJECT_ID
~~~

Attestations bind to a digest. If an image is rebuilt—even without source code changes—its digest can change and requires a new attestation. Never reuse an old attestation for an artifact with a different digest.

## 7. Configuring a Policy Requiring Attestations

Each Google Cloud project has exactly one Binary Authorization policy. The policy must be configured in the project where the deployment platform runs. In a single-project setup, policy, attestors, and attestations can reside in that same project. In a multi-project setup, the policy remains in the deployer project and references attestors in the security project.

A policy has two key settings:

- `evaluationMode`: condition the image must satisfy, such as allow all, deny all, or require attestation.
- `enforcementMode`: action when an image fails the condition, such as blocking deployment or audit-logging only.

Example policy requiring an attestation from attestor `release-approval`:

~~~yaml
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/ATTESTOR_PROJECT_ID/attestors/release-approval
name: projects/DEPLOYER_PROJECT_ID/policy
~~~

`globalPolicyEvaluationMode: ENABLE` lets Google-managed system images be evaluated via the global policy evaluation mechanism. This prevents blocking system images needed by the platform.

Export the current policy, edit the YAML file, and re-import it:

~~~bash
gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy export > policy.yaml

# Edit policy.yaml, review rules and image exemptions.

gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy import policy.yaml
~~~

Policies can take a few minutes to take effect. Never overwrite a production policy with a minimal file without reviewing existing specific rules, image exemptions, and settings. Export, review diffs, archive the previous policy, and import via change management procedures.

If a policy lists multiple attestors, the image must hold valid attestations from all listed attestors. Multiple signers can represent different verification gates, such as `built-by-ci`, `security-scanned`, and `qa-approved`.

A policy has one default rule and may support specific rules depending on the platform. GKE supports rules per cluster, Kubernetes namespace, and Kubernetes service account. Cloud Run supports only the default rule, with no per-service specific rules. Check which rule types your target platform supports before designing policies.

## 8. Dry-Run Before Enforcing

Do not enable blocking policies in production before observing their impact. Dry-run evaluates the policy while still allowing non-compliant deployments to run. Violations are recorded in Cloud Logging or Cloud Audit Logs so operations teams can spot false positives and unattested images.

In the policy YAML, set `enforcementMode` to:

~~~yaml
enforcementMode: DRYRUN_AUDIT_LOG_ONLY
~~~

Once the policy is verified to behave properly, switch to:

~~~yaml
enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
~~~

Roll out policies in steps:

1. Export the current policy and save a backup copy.
2. Add attestors and attestation-requiring rules in dry-run mode.
3. Deploy representative workloads in dev/staging and inspect logs.
4. Check system images, sidecars, init containers, and service-managed images.
5. Confirm pipelines generate attestations for the exact digests.
6. Switch the policy to enforce once legitimate unattested images are addressed.

Dry-run does not prove the entire security pipeline is sound. It only shows whether deployment requests satisfy the policy. Audit signers, IAM permissions, digest sources, and claim semantics before trusting attestations.

## 9. Integrating with Cloud Build

Cloud Build can generate attestations for images it builds and pushes. Within the same project, the default attestor is named `built-by-cloud-build`. You can configure a policy requiring this attestation so only images built by Cloud Build are eligible.

Illustrative build configuration:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/runtime/checkout-api:$SHORT_SHA
      - .

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/runtime/checkout-api:$SHORT_SHA
~~~

Cloud Build must identify the output image via the `images` field. If a build uses an explicit `docker push` step instead of the `images` field, Cloud Build does not generate a Binary Authorization attestation via this flow.

For builds running in a private pool, Cloud Build does not generate Binary Authorization attestations by default. Add `requestedVerifyOption: VERIFIED`:

~~~yaml
options:
  requestedVerifyOption: VERIFIED
~~~

This option enables and verifies generation of attestations and provenance metadata. The build succeeds only if the requested attestation and provenance are generated.

After the build, the pipeline must fetch the digest of the pushed image, record it in outputs or release metadata, and use that digest during deployment. Never construct digests from tags or infer them from image names.

### Separating Build Pipelines and Deploy Pipelines

Cloud Build creates attestations after the build pipeline completes successfully. Therefore, separate the build pipeline from the deploy pipeline:

- Build pipeline: checks out source, builds, tests, scans, pushes image, and generates provenance/attestation.
- Release pipeline: takes the verified image digest, verifies required attestations, generates deployment manifests, and requests platform deployment.

Policies referencing the `built-by-cloud-build` attestor can be exported/imported via CLI. Example rule:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/BUILD_PROJECT_ID/attestors/built-by-cloud-build
name: projects/DEPLOYER_PROJECT_ID/policy
~~~

In multi-project setups, the deployer project's Binary Authorization service agent must be granted permission to verify the attestor from the build project. Do not assume a policy in the deployer project automatically has permission to read attestors or Artifact Analysis notes in another project.

## 10. Separation of Duties Across Multiple Projects

In large organizations, divide administrative privileges across three projects:

| Project | Responsibility | Managed By |
|---|---|---|
| Deployer project | GKE/Cloud Run and Binary Authorization policy | Platform / DevOps |
| Attestor project | Attestors, notes, and public keys | Security Operations |
| Attestation project | Artifact Analysis occurrences storing attestations | CI/CD signers or release approvers |

This separation prevents developers from creating attestors, swapping public keys, or self-approving production images. Security teams manage trusted identities, while release pipelines only have permissions to create attestations according to assigned workflows.

Common IAM roles:

| Action | Project | Role |
|---|---|---|
| Create attestors and manage notes | Attestor | `roles/containeranalysis.notesEditor`, `roles/binaryauthorization.attestorsAdmin` |
| Configure policy | Deployer | `roles/binaryauthorization.policyEditor` |
| Read attestors for policy evaluation | Attestor | `roles/binaryauthorization.attestorsViewer` |
| Enable Binary Authorization and manage clusters | Deployer | `roles/serviceusage.serviceUsageAdmin`, `roles/container.clusterAdmin` |
| Create attestation | Attestor note | `roles/containeranalysis.notes.attacher` |
| Write occurrences | Attestation | `roles/containeranalysis.occurrences.editor` |

Beyond user roles, grant permissions to the deployer project's Binary Authorization service agent to verify attestors in the attestor project. The service account has the form:

~~~text
service-DEPLOYER_PROJECT_NUMBER@gcp-sa-binaryauthorization.iam.gserviceaccount.com
~~~

On the attestor resource, grant `roles/binaryauthorization.attestorsVerifier` to this service agent. The Artifact Analysis note requires `roles/containeranalysis.notes.occurrences.viewer` for the relevant service agents. Follow Google Cloud's multi-project setup guide to configure all IAM bindings across notes, attestors, and occurrences.

Do not grant `roles/binaryauthorization.admin` or Owner to pipelines just to create attestations. Grant exact permissions on notes, occurrences, and key versions. In particular, Cloud KMS signing permissions should belong solely to approved signers.

## 11. Enabling Enforcement on Deployment Platforms

### 11.1. Google Kubernetes Engine

When creating a GKE cluster, enable Binary Authorization evaluation:

~~~bash
gcloud container clusters create app-prod-cluster \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE
~~~

The cluster uses the deployer project's policy. When a Pod is created or updated, Binary Authorization checks the image against that policy. If the policy requires an attestation and none is valid, the admission request is rejected.

When deploying, use a digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      containers:
        - name: checkout-api
          image: asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
~~~

When rejected, inspect Kubernetes events and Binary Authorization audit logs to see which rule blocked the image and which attestor lacks an attestation.

### 11.2. Cloud Run

Cloud Run supports policies for services and jobs. Enable the default policy via CLI:

~~~bash
gcloud run services update checkout-api \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binary-authorization=default
~~~

For a Cloud Run job:

~~~bash
gcloud run jobs update nightly-reconcile \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binary-authorization=default
~~~

For services, Cloud Run evaluates the policy whenever creating a new revision. If the image violates policy, deployment fails and the new revision is not deployed. Existing revisions are not re-evaluated simply because the policy changed.

For jobs, updating job configuration can succeed even if the image violates policy; job execution will fail when policy disallows the image. Policy changes also do not apply retroactively to already-running executions.

Use Organization Policies to mandate Binary Authorization for Cloud Run. If enabled only per service without an organization-level policy, anyone with deploy permissions could disable Binary Authorization in service settings.

Cloud Run provides a breakglass mechanism to bypass policy during emergencies. Breakglass generates an audit log entry. Use it only during incidents, recording the approver, reason, image digest, expiration, and remediation plan. Once resolved, remove the bypass and deploy a policy-compliant image.

For Cloud Run functions, certain platform-managed source repositories must be exempted per Google Cloud guidance, such as `cloud-run-source-deploy` or `gcf-artifacts` depending on the deployment API. Do not add broad allowlists for entire registries when only function build/deploy repositories need exemption.

### 11.3. Continuous Validation

Binary Authorization also provides Continuous Validation (CV) to periodically verify whether images attached to running Pods continue satisfying policies. CV is a continuous monitoring mechanism distinct from deploy-time enforcement. CV logs findings when running workloads fall out of compliance; it does not replace admission-time enforcement gates.

Current documentation marks check-based platform policies for CV as Preview. Verify release stage and feature limitations before relying on it for mandatory production compliance controls.

## 12. Investigation and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Deployment rejected with No attestations found | Attestation not created or stored in another project | Check digest, attestor, occurrence project, and attestation list |
| Attestation exists but signature invalid | Public key ID mismatch, wrong key version, or payload digest mismatch | Inspect attestor public key and run attestation creation with validate |
| Image has attestation yet still blocked | Policy requires multiple attestors or manifest uses a different digest | Compare `requireAttestationsBy` and image digest in manifest |
| Cloud Build succeeds yet lacks attestation | Private pool missing `requestedVerifyOption: VERIFIED`, or pushed via separate step | Check build config, `images` field, and build results |
| Dry-run policy still lets image deploy | Enforcement mode is audit-only | Check `enforcementMode` in policy YAML |
| Deployer cannot verify attestor | Missing IAM on attestor or Artifact Analysis note | Check deployer project service agent and IAM bindings |
| Cloud Run job update succeeds but execution fails | Jobs evaluate policy only at execution time | Check execution logs and image digest |
| Approved image tag blocked at deploy | Tag repointed to another digest or manifest uses tag | Deploy using image digest and create attestation for that digest |

Investigate in order:

1. Retrieve the actual image digest the platform is attempting to deploy.
2. Confirm that digest exists in Artifact Registry and matches expected build outputs.
3. Check which project and attestor hold the attestation.
4. Verify the public key ID and key version match the attestor.
5. Inspect the deployer project's policy and identify which rule applies.
6. Check enforcement mode and image exemptions.
7. Verify IAM for the deployer service agent, signer, and policy administrators.
8. Inspect Binary Authorization logs, Cloud Audit Logs, GKE events, or Cloud Run deployment events.

Export the current policy with:

~~~bash
gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy export
~~~

And list attestors:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors list
~~~

Never fix errors by switching production policy to allow-all or adding wildcard exemptions. Diagnose missing attestations, digest mismatches, or IAM gaps first.

## 13. Real-World Scenario: Bringing Checkout API to Production

An organization deploys `checkout-api` across dev, staging, and production. The security team requires every production image to be built by CI and approved by QA.

Release flow:

1. Developer merges code into the release branch.
2. Cloud Build builds the image, runs unit tests, integration tests, and scans.
3. Image is pushed to Artifact Registry; pipeline records the actual digest.
4. Cloud Build creates a build attestation or signer creates attestation `ci-build-approved`.
5. QA tests the image by digest in staging.
6. QA signer creates attestation `qa-approved` for the exact same digest.
7. Release pipeline renders production manifests using that digest.
8. Binary Authorization policy requires both `ci-build-approved` and `qa-approved`.
9. GKE or Cloud Run validates attestations before admitting the deployment.
10. When deployment succeeds, pipeline records digest, source commit, build ID, attestors, and release timestamp.

The policy can require both attestors:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/SECURITY_PROJECT_ID/attestors/ci-build-approved
    - projects/SECURITY_PROJECT_ID/attestors/qa-approved
name: projects/PROD_PROJECT_ID/policy
~~~

If QA has not signed its attestation, the image is rejected even though the build succeeded. This turns QA sign-off from a manual step into an automatically enforceable gate at deploy time.

If an incident requires rolling back, the pipeline must redeploy the digest of an older image that already holds valid attestations. Do not simply move a `stable` tag back to an earlier tag because tags are mutable and do not prove which artifact was approved.

## 14. Operational Best Practices

- Use digests rather than tags for attestations and production deployments.
- Separate build, sign, attestor administration, and deploy permissions so no individual or service account can self-approve every step.
- Use Cloud KMS to hold private keys; restrict signing permissions and audit key version usage.
- Create attestations only after pipelines verify the exact image digest and complete required checks.
- Have each attestor represent a clearly accountable process or team.
- Run policies in dry-run mode before enabling block-and-audit-log.
- Retain build, test, scan, source commit, and signer identity evidence for investigations.
- Protect Artifact Analysis notes, occurrences, attestors, and policies with least-privilege IAM.
- Keep image exemptions narrow and justified; avoid overly broad wildcards.
- Monitor Binary Authorization audit logs and breakglass usage.
- Re-verify policies, signers, and attestations whenever changing CI/CD, key versions, registries, or deploy platforms.
- Pair Binary Authorization with vulnerability scanning, SBOMs, and build provenance. Attestations only verify signer claims; they do not prove an image is vulnerability-free.

## 15. Pre-Production Enforcement Checklist

- [ ] Image is pushed to registry and digest is obtained from actual build output.
- [ ] Attestor has a valid Artifact Analysis note and public key.
- [ ] Private keys are stored in Cloud KMS or an equivalent secure mechanism.
- [ ] Only approved signers hold permissions to create attestations.
- [ ] Attestations are created for the exact digest and pass validation.
- [ ] Policy resides in the deployer project and references the right attestors.
- [ ] Deployer IAM service agent has permissions to verify attestors/notes.
- [ ] Attestation project and occurrence permissions are properly configured.
- [ ] GKE cluster or Cloud Run service/job has Binary Authorization enabled.
- [ ] Policy has run in dry-run mode and false positives have been resolved.
- [ ] Production manifests reference digests rather than tags.
- [ ] Image exemptions have been reviewed.
- [ ] Breakglass, audit, and rollback procedures using approved digests are in place.
- [ ] Dashboards/log alerts exist to detect rejected deployments and policy changes.

## 16. Self-Check

1. Why must attestations bind to image digests rather than only tags?
2. How do the roles of signer and attestor differ?
3. How do Artifact Analysis notes and occurrences participate in the attestation process?
4. Which two parts of a policy do `REQUIRE_ATTESTATION` and `ENFORCED_BLOCK_AND_AUDIT_LOG` address?
5. Why use dry-run before enforcing?
6. In the three-project model, what responsibilities do the deployer, attestor, and attestation projects hold?
7. Why do Cloud Build private pools require `requestedVerifyOption: VERIFIED`?
8. At what point does a Cloud Run job check Binary Authorization?
9. Does an attestation prove an image contains no security vulnerabilities?

**Suggested Answers**

1. Tags can be reassigned to different images; digests uniquely identify specific image content and never change when tags move.
2. Signers use private keys to sign claims; attestors hold public keys and verify signatures at deploy time.
3. Notes describe attestor metadata; occurrences store signed attestations linked to the note.
4. `REQUIRE_ATTESTATION` defines the condition requiring valid signatures from attestors; `ENFORCED_BLOCK_AND_AUDIT_LOG` enforces blocking non-compliant images and writing audit logs.
5. Dry-run lets teams observe violations and false positives without blocking workloads, reducing policy rollout risk.
6. The deployer project holds policies and runtime platforms; the attestor project holds notes, attestors, and public keys; the attestation project stores occurrences.
7. Cloud Build does not generate Binary Authorization attestations by default for private pool builds; `requestedVerifyOption: VERIFIED` enables and verifies attestation/provenance generation.
8. Cloud Run jobs evaluate policies at job execution time; updating the job can succeed even if the image fails policy.
9. No. An attestation is only a claim signed by a signer. Evaluating vulnerabilities requires separate scanning and policy controls.

## References

- [Google Cloud: Binary Authorization overview](https://docs.cloud.google.com/binary-authorization/docs/overview)
- [Google Cloud: Binary Authorization concepts and policy model](https://docs.cloud.google.com/binary-authorization/docs/key-concepts)
- [Google Cloud: Get started using the Google Cloud CLI for GKE](https://docs.cloud.google.com/binary-authorization/docs/getting-started-cli)
- [Google Cloud: Create attestations](https://docs.cloud.google.com/binary-authorization/docs/making-attestations)
- [Google Cloud: Create attestors using the gcloud CLI](https://docs.cloud.google.com/binary-authorization/docs/creating-attestors-cli)
- [Google Cloud: Configure a multi-project setup](https://docs.cloud.google.com/binary-authorization/docs/multi-project-setup-cli)
- [Google Cloud: Separation of duties and IAM roles](https://docs.cloud.google.com/binary-authorization/docs/reference/organizational-and-iam-roles)
- [Google Cloud: Secure image deployments with Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/secure-deployments-to-run-gke)
- [Google Cloud: Binary Authorization for Cloud Run](https://docs.cloud.google.com/binary-authorization/docs/run/overview)
- [Google Cloud: Use Binary Authorization on Cloud Run](https://docs.cloud.google.com/run/docs/securing/binary-authorization)
