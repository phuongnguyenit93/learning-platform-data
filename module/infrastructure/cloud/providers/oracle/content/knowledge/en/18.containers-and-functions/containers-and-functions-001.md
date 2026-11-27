# Container Registry and Managing Repositories in OCIR

## 1. Objectives and Context

In the **Containers and Functions** chapter of the **CLOUD_PROVIDERS_ORACLE** module, Container Registry is where application packages are stored before being deployed to a runtime environment. An OCI deployment workflow must identify which tenancy an image belongs to, which region and compartment the repository resides in, who is permitted to publish, who is permitted to download, and which versions are retained for recovery.

After this lesson, learners will be able to:

- Distinguish between registry, repository, image, tag, digest, and tenancy namespace.
- Design repositories that align with team and environment permission boundaries.
- Create a private repository, log in, push, and pull images using the Docker CLI.
- Separate repository administration permissions, publishing permissions, and image consumption permissions.
- Plan vulnerability scanning, retention, monitoring, and storage capacity control.

This lesson focuses on managing images in OCIR. OKE, Compute, Container Instances, and OCI Functions are referenced as image consumers; configuring those runtime environments requires separate deployment workflows.

## 2. Where Does OCIR Fit in the Deployment Workflow?

**Oracle Cloud Infrastructure Registry**, commonly abbreviated as **OCIR** or referred to as **Container Registry**, is an Oracle-managed registry. The service supports storing and distributing container images via the registry protocol and Docker CLI. OCIR also supports Open Container Initiative standard artifacts such as multi-architecture manifest lists and Helm charts. See [Overview of Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm).

~~~mermaid
flowchart LR
    SRC["Source code and Dockerfile"] --> BUILD["Developer workstation or CI builds image"]
    BUILD -->|Push using publishing identity| REG["OCIR: private repository"]
    REG --> SEC["Scan and evaluate release criteria"]
    SEC --> RELEASE["Record approved image digest"]
    REG -->|Pull approved image| RUN["Application runtime environment"]
    RELEASE --> RUN
~~~

The diagram illustrates a **recommended workflow**: the release criteria evaluation step is implemented by the organization via CI/CD. The presence of an image in OCIR does not by itself indicate that the image has been tested or approved for production.

The registry stores artifacts; application runtime resources provide CPU, memory, and database connectivity. Therefore, changes to a repository or pull permissions can directly affect the next startup, scaling event, or deployment of an application.

## 3. Concepts to Distinguish

| Concept | Meaning | Example in This Lesson |
| --- | --- | --- |
| Registry | Service that receives and distributes images | OCIR in a given region |
| Repository | Resource that groups related images | `learning/orders-api` |
| Image | Package containing the application and components required to run it | Build of the orders application |
| Image tag | Version name used when referencing an image | `1.0.0`, `git-a1b2c3d` |
| Image digest | Hash-based content identifier | `sha256:...` |
| Tenancy namespace | Namespace of the tenancy that owns the repository | Retrieved from tenancy details |
| Compartment | Scope for organizing resources and applying IAM | `AppDev` |
| Repository OCID | Repository resource identifier via OCI API | `ocid1.containerrepo...` |

An image consists of the packaged components used to create a container. One image can be used to launch multiple containers; the lifecycle of running containers and the lifecycle of images in the registry are two separate concerns to manage. See [Docker's container concept](https://docs.docker.com/learn/content/what-is-a-container/).

### 3.1. Image Tags and Resource Tags

`1.0.0` in `orders-api:1.0.0` is an **image tag**, used to select an image version.

Labels such as `Owner=platform` or `Environment=dev` attached to OCI resources are **resource tags**, used to describe and organize resources. The two types of tags serve different purposes. Editing a resource tag does not publish a new application version. Repository configuration and resource tag operations are described in [Editing a Repository](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/edit-repository.htm).

### 3.2. Tags Are Convenient, Digests Pin Content

Suppose today `orders-api:1.0.0` points to image A. If the workflow allows overwriting tags, tomorrow the same reference may point to image B. A version name looks fixed, yet it is not sufficient proof that the content has not changed.

A digest lets you reference specific content:

~~~text
<registry-domain>/<tenancy-namespace>/<repository>@sha256:<digest>
~~~

The recommended convention is to use tags for human recognition of releases while recording the digest in deployment records. When you need to redeploy or roll back, retrieve the approved digest. Docker supports pulling by digest; see [docker image pull](https://docs.docker.com/reference/cli/docker/image/pull/).

A digest does not prevent an image from being deleted and does not prove that an image is secure. Digests must be combined with access permissions, retention policies, and security checks.

## 4. Image Addresses, Regions, and Compartments

For a standard repository without top-level capability enabled, an image reference has the form:

~~~text
<registry-domain>/<tenancy-namespace>/<repository-name>:<image-tag>
~~~

Illustrative example:

~~~text
ocir.us-ashburn-1.oci.oraclecloud.com/demo_namespace/learning/orders-api:1.0.0
~~~

`demo_namespace` is a placeholder in this lesson; when practicing, you must replace it with a real namespace.

| Component | What to Verify |
| --- | --- |
| `ocir.us-ashburn-1.oci.oraclecloud.com` | Registry endpoint of the selected region |
| `demo_namespace` | Namespace of the tenancy that owns the repository |
| `learning/orders-api` | Repository name in the lab model |
| `1.0.0` | Image tag to push or pull |

Oracle documentation describes the endpoint format `ocir.<region-identifier>.oci.oraclecloud.com`; the formats `<region-key>.ocir.io` and `<region-identifier>.ocir.io` are also supported in the OC1 realm. Check the appropriate endpoint for your actual region and realm in [Preparing for Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryprerequisites.htm).

**Compartment does not appear as a separate component in the image address.** A repository still belongs to a compartment for applying permissions. Do not insert a compartment OCID into the Docker path.

Repository names must be unique across compartments in the registry of the same tenancy and region. Therefore, if you want to separate dev and prod into two repositories, use two distinct names, such as `dev/orders-api` and `prod/orders-api`. See [Creating a Resource in Container Registry](https://docs.oracle.com/en-us/iaas/Content/Marketplace/container-registry.htm).

The namespace used in the address is the tenancy's Object Storage namespace, not a compartment name or tenancy OCID. You can view it in the tenancy details in the Console; how the namespace is used is also explained in [Pulling Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypullingimagesusingthedockercli.htm).

## 5. Designing Repositories

### 5.1. Choosing Boundaries by Permissions and Lifecycle

One design approach for the orders service development team:

| Proposed Repository | Purpose | Entity Permitted to Push | Retention Direction |
| --- | --- | --- | --- |
| `dev/orders-api` | Builds for development | Orders team CI | Short, phasing out discarded builds |
| `staging/orders-api` | Builds undergoing integration testing | Authorized pipeline | Retained long enough to reproduce tests |
| `prod/orders-api` | Approved release builds | Release pipeline | Retained for running builds and rollback builds |

This is a design choice, not a mandatory OCIR structure. If a single repository contains both `dev` and `prod` tags, you must evaluate whether having the same repository permission boundary cover all those images meets organizational requirements.

For example, the development team needs to publish builds daily, while the operations team wants to receive only approved builds. Separating repositories makes the publishing permissions and retention policies of each side explicit.

### 5.2. Slashes and Top-Level Capability

OCIR supports two models that must be distinguished:

- **Top-level capability disabled:** `team/orders` and `team/payments` are two independent repositories. The `team/` prefix is merely part of the name.
- **Top-level capability enabled on repository `team`:** `team/orders:v1` and `team/payments:v1` can be image paths belonging to the same `team` repository. The sub-paths do not have independent repository permissions.

Therefore, a `/` in a path is not sufficient to determine IAM boundaries. You must check the actual repository configuration. See [Container Registry Concepts](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryconcepts.htm).

This lab uses a **standard repository, private, with top-level capability disabled**, named `learning/orders-api`.

### 5.3. Standard and Pull-Through Cache

A standard repository receives images pushed by clients. A pull-through cache repository fetches and caches requested images from a supported upstream OCIR in another region within the same realm; clients do not push images into a cache repository.

Repository type and top-level capability are chosen at creation time and cannot be changed afterward. Finalize the model before wiring up pipelines. For this lab, creating the repository beforehand in the target compartment avoids relying on the automatic repository creation mechanism in the root compartment on the first push. See [Creating a Repository](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrycreatingarepository.htm).

## 6. IAM: Who Can View, Pull, Push, and Administer?

### 6.1. Understanding the `repos` Resource Type

OCIR access permissions use the `repos` resource type:

| Verb | Primary Meaning Within This Lesson's Scope |
| --- | --- |
| `inspect` | List resource information |
| `read` | Read and pull images |
| `use` | For `repos`, adds no additional permissions compared to `read` |
| `manage` | Includes create, update, delete, and administration permissions |

A common mistake is granting `use repos` and expecting to be able to push. Pushing requires `REPOSITORY_READ` and `REPOSITORY_UPDATE`; use the actual permissions rather than inferring from the verb name. See [Details for Container Registry](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/registrypolicyreference.htm).

### 6.2. Example Separating Three Roles

Assume the `AppDev` compartment and the following groups already exist in the `Default` identity domain. Replace domain, group, and compartment names to match your environment:

~~~text
Allow group 'Default'/'RegistryAdmins' to manage repos in compartment AppDev

Allow group 'Default'/'RegistryReaders' to read repos in compartment AppDev

Allow group 'Default'/'RegistryPublishers' to manage repos in compartment AppDev where all { target.repo.name = 'learning/orders-api', any { request.permission = 'REPOSITORY_READ', request.permission = 'REPOSITORY_UPDATE' } }
~~~

The admin group creates repositories beforehand. The reader group can pull within the compartment. The publisher group can read and update images in the designated repository, without being granted additional permissions to create, delete, or change visibility through this policy.

This is an example of narrowing permissions following [Policies to Control Repository Access](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registrypolicyrepoaccess.htm). You must also consider other policies currently granted to users: a narrow policy does not revoke permissions already granted by a broader policy.

### 6.3. Authentication and Authorization

`docker login` verifies the identity and credentials for the registry. Push and pull must also satisfy IAM policies for the corresponding repository.

For example, an account that logs in successfully but belongs only to `RegistryReaders` will not be able to push. The fix is to grant the appropriate publishing permissions for the target repository after confirming the requirement.

An auth token represents a user; the token itself is not a policy scoped to a single repository. To reduce the blast radius if credentials are exposed, minimize the permissions of the identity that owns the token and manage credentials appropriately for CI/CD.

## 7. Lab: Creating a Private Repository and Pushing an Image

### 7.1. Preparation

The commands below are **examples for learners to execute in Bash**, such as WSL or a Linux machine with Docker. They require:

- A tenancy subscribed to the intended region.
- A working Docker CLI and Docker daemon.
- OCI CLI configured with authentication and appropriate permissions.
- A lab compartment and IAM policies prepared by an administrator.
- Connectivity to OCIR; building the example also requires pulling the base image from Docker Hub.

OCI CLI login and Docker registry login are two separate authentication configurations.

Declare lab variables:

~~~bash
export OCI_REGION='us-ashburn-1'
export REGISTRY='ocir.us-ashburn-1.oci.oraclecloud.com'
export TENANCY_NAMESPACE='REPLACE_WITH_REAL_NAMESPACE'
export COMPARTMENT_OCID='REPLACE_WITH_REAL_COMPARTMENT_OCID'
export REPOSITORY='learning/orders-api'
export IMAGE_TAG='1.0.0'
export IMAGE_PATH="$REGISTRY/$TENANCY_NAMESPACE/$REPOSITORY"
export IMAGE_REF="$IMAGE_PATH":"$IMAGE_TAG"
~~~

Replace the `REPLACE_WITH_...` values before running. If you choose a different region, update both `OCI_REGION` and `REGISTRY` accordingly.

### 7.2. Creating the Repository in the Target Compartment

In the Console, navigate to **Container Registry**, select the target region, select the lab compartment, and create a repository with:

| Property | Lab Value |
| --- | --- |
| Repository type | Standard |
| Repository name | `learning/orders-api` |
| Access/visibility | Private |
| Top-level capability | Disabled |
| Compartment | Prepared lab compartment |

You can use the OCI CLI to create a private container repository:

~~~bash
oci artifacts container repository create \
  --region "$OCI_REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --display-name "$REPOSITORY" \
  --is-public false
~~~

**Choose one creation method**, Console or CLI, to avoid duplicate creation. If you use the CLI, verify in the Console that the type and top-level capability match the lesson's model. The CLI syntax is described in [container repository create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/create.html).

List to verify the resource is in the right place:

~~~bash
oci artifacts container repository list \
  --region "$OCI_REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --display-name "$REPOSITORY" \
  --all
~~~

Save the repository OCID from the output for management purposes. `--all` fetches all pages of results; `--display-name` filters by exact name. See [container repository list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/list.html).

### 7.3. Creating an Auth Token and Logging In

In your OCI user profile, open **Auth Tokens**, generate a token, and store it using a suitable secret management system. When Docker prompts for a password, enter the **auth token**, not your Console password.

Username format:

~~~text
<tenancy-namespace>/<username>

Or with the corresponding federated identity configuration:
<tenancy-namespace>/<domain-name>/<username>
~~~

You must obtain the actual domain from your account configuration; do not assume every tenancy uses `oracleidentitycloudservice`.

Interactive login:

~~~bash
export OCIR_USERNAME='REPLACE_WITH_FULL_OCIR_USERNAME'
docker login "$REGISTRY" --username "$OCIR_USERNAME"
~~~

Token creation and login format are covered in [Pushing Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm).

For CI with the secret provided in the `OCIR_AUTH_TOKEN` environment variable, use stdin:

~~~bash
printf '%s' "$OCIR_AUTH_TOKEN" \
  | docker login "$REGISTRY" \
      --username "$OCIR_USERNAME" \
      --password-stdin
~~~

Do not enable shell tracing when handling secrets. Use a credential helper or appropriate credential storage mechanism for the runner. `--password-stdin` avoids passing the token directly as an argument; see [docker login](https://docs.docker.com/reference/cli/docker/login/).

### 7.4. Building a Small Image

In your lab directory, create a Dockerfile:

~~~dockerfile
FROM nginx:stable-alpine
RUN printf '%s\n' 'Orders API - OCIR learning image' > /usr/share/nginx/html/index.html
EXPOSE 80
~~~

This image only serves to test the artifact path. It returns static content so the downloaded build is easy to identify.

~~~bash
docker build -t orders-api-local:1.0.0 .
docker tag orders-api-local:1.0.0 "$IMAGE_REF"
docker image ls "$IMAGE_PATH"
docker push "$IMAGE_REF"
~~~

`docker tag` adds a reference to the built image; this step does not send data to the registry yet. `docker push` transfers the artifact to the destination. After pushing, keep the digest from the output and open the Console to inspect the image.

The `nginx:stable-alpine` base image is used in the lab to make getting started easy. Production release workflows require explicit decisions on base image versions and approved digests to ensure reproducible builds.

### 7.5. Verifying by Pulling by Digest

Obtain the **image manifest digest in the registry** from the push output or image details. Do not use the local Docker image ID as a substitute for this digest.

~~~bash
export IMAGE_DIGEST='sha256:REPLACE_WITH_REAL_MANIFEST_DIGEST'
export PINNED_IMAGE="$IMAGE_PATH@$IMAGE_DIGEST"

docker pull "$PINNED_IMAGE"
docker image inspect "$PINNED_IMAGE" --format '{{json .RepoDigests}}'
~~~

In the Console, you can view image details, push timestamp, pusher, size, and versions. Use this data to cross-check against the build; see [Getting an Image's Details](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryviewingimagedetails.htm).

To further verify the content of the pulled image:

~~~bash
docker run --rm --name ocir-orders-lab \
  -p 127.0.0.1:8080:80 "$PINNED_IMAGE"
~~~

In another terminal:

~~~bash
curl http://127.0.0.1:8080
~~~

The expected output is `Orders API - OCIR learning image`. Stop the container with Ctrl+C; `--rm` cleans up the container when it exits.

### 7.6. Expected Outcomes

The lab is complete when all of the following are confirmed:

1. The private repository exists in the selected region and compartment.
2. The publishing identity can push images; the read-only identity can pull but cannot push.
3. The Console displays the matching image tag, digest, and push details.
4. Pulling by digest succeeds and the container returns the identifying content.
5. Deployment records capture the repository, tag, digest, and associated build ID or commit.

Test permissions using a separate identity, such as a test profile or dedicated test runner, to avoid accidentally using cached admin credentials on the machine.

## 8. Using Private Repositories from OCI Infrastructure

### 8.1. Checking Two Independent Paths

An application runtime resource simultaneously requires:

- **Network path:** DNS resolution and HTTPS connectivity to the registry endpoint.
- **Access path:** supported credentials or authentication mechanism along with image read permissions.

Successful network connectivity does not guarantee a successful pull. Likewise, an identity with read permissions still cannot download an image if the network path is blocked.

OCIR supports access from resources in a VCN in the same region via a **Service Gateway**, allowing resources in private subnets to access the service without public IPs. The design also requires appropriate route and network rules. See [Overview of Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm).

In the lab, Docker build downloads the base image from Docker Hub. A private access path to OCIR does not automatically provide connectivity to that external registry; outbound network routing for builds must be planned separately.

### 8.2. Preparing for OKE, Compute, and Functions

Before an environment consumes an image, hand off the following details:

| Detail | Example to Record |
| --- | --- |
| Artifact reference | Image path with approved digest |
| Usage permissions | Which identity needs read access to which repository |
| Architecture | Whether the image targets AMD64, ARM64, or multi-architecture |
| Networking | Required endpoint and appropriate egress path |
| Recovery | Previous version's digest and how long it remains retained |

How credentials are delivered to each runtime must follow that runtime's documentation. Do not use a `docker login` result on your laptop to conclude that worker nodes or the Functions service already have pull permissions.

## 9. Securing the Image Supply Chain

### 9.1. Vulnerability Scanning

You can add an image scanner to a repository; OCIR integrates with **OCI Vulnerability Scanning**. The scanning service must be granted the necessary read permissions. See [Scanning Images for Vulnerabilities](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryscanningimagesforvulnerabilities.htm).

Recommended release workflow:

1. CI pushes the image into a repository for review.
2. Wait for scan results for the exact digest.
3. Apply the agreed risk acceptance criteria.
4. Record the approved digest in the release record.
5. Re-monitor as vulnerability information changes.

For example, a team may require remediating all Critical vulnerabilities with available patches before release. This is an organizational criterion that must be enforced in the pipeline; enabling the scanner alone does not create a deployment gate.

### 9.2. Image Signing

OCIR supports signing images using keys from **OCI Vault**; see [Signing Images for Security](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrysigningimages_topic.htm).

When designing the workflow, clearly assign which people or pipelines may use the signing key, which digests get signed, and where signatures are verified. Existing signatures must be verified by the consumer to serve as an effective control.

Vulnerability scanning evaluates content for known risks; signing verifies the publishing source and integrity under the chosen trust mechanism. Both must be clearly defined before using images for systems handling critical data.

### 9.3. Credentials and Visibility

By default, the lab design uses a private repository. Switch to public only after the owner confirms the artifact is permitted for public distribution.

Separate publishing identities from pull-only identities; store credentials in the pipeline's secret store with clear ownership and a rotation process. When token exposure is suspected, revoke the relevant credentials and audit actions within that identity's scope.

Do not embed database credentials, private keys, or tokens into Dockerfiles or image layers. Applications should receive secrets at runtime through the platform's secret management mechanism.

## 10. Lifecycle, Retention, and Storage Management

### 10.1. Three Distinct Cleanup Operations

| Operation | Affected Target | What to Watch Out For |
| --- | --- | --- |
| Delete local image | Copy on the Docker host | Does not clean up images in OCIR |
| Unversion image | Removes a version identifier on the registry | Does not mean deleting the image content |
| Delete image in OCIR | Artifact on the registry | May affect subsequent pulls |

Oracle refers to removing a version identifier as **unversioning**. After this operation, evaluate whether the image still needs to be retained by digest or is eligible for cleanup; see [Unversioning an Image](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryuntaggingimages.htm).

### 10.2. Per-Region Retention Policies

OCIR has a separate global image retention policy per region; by default, it retains all images. You can apply a custom policy to a repository to override the global policy. A repository can belong to only one custom policy at a time.

Criteria include time since last pulled, time since unversioned, and exempted version identifiers. Policies are processed asynchronously, with a waiting period after creation or update. Details are in [Retaining and Deleting Images Using Retention Policies](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrymanagingimageretention.htm).

Recommended design:

| Image Group | Handling Approach |
| --- | --- |
| Unused experimental builds | Choose a short retention window after assessing needs |
| Currently running builds | Ensure they fall within the retained scope |
| Approved rollback builds | Retain according to the system's recovery objectives |
| Untagged images still deployed by digest | Verify references before cleanup |

A stable production release running for a long time may be pulled infrequently. Therefore, "not recently pulled" criteria must be cross-checked against the list of digests actively in use.

### 10.3. Storage Usage Does Not Drop Immediately After Deletion

Oracle notes that deleting images and reclaiming storage space can take up to 48 hours; see [Deleting an Image](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrydeletingimages.htm).

Operationally, monitor storage trends rather than waiting until quotas are nearly exhausted to clean up. Combine removing unnecessary components from images, controlling the number of retained builds, and avoiding republishing artifacts that serve no clear purpose.

Costs must be evaluated based on storage capacity, number of retained builds, and traffic of the actual architecture. When budgeting, consult the pricing schedule and tenancy terms at the time of deployment; this lesson does not assume a fixed price.

## 11. Changing Compartments and Preparing for Recovery

You can move a repository to another compartment. After moving, access permissions must align with the target compartment; see [Moving a Repository Between Compartments](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrymovingrepos.htm).

For example, a repository is moved from a sandbox compartment to a compartment managed by the platform team. Before the change, verify that the CI identity can still push and runtime identities can still pull after the move. After the change, re-verify both flows.

**Moving a compartment** and **preparing images in another region** are two different tasks. For disaster recovery requirements in a standby region, establish a process to transfer or pre-stage artifacts there, prepare permissions, and test pull capability when the primary region is unavailable.

A recovery checklist should record:

- Repository and endpoint in the standby region.
- Approved digest along with how to verify the artifact at the destination.
- Credentials or authentication mechanism for the standby environment.
- Image retention policy and periodic verification steps.

The practical goal is to prove that the application can be relaunched from accessible artifacts under the defined recovery conditions.

## 12. Monitoring and Troubleshooting

### 12.1. Data to Record

For each release, record the timestamp, pipeline identity, commit or build ID, repository path, image tag, manifest digest, and verification results used for approval.

For each repository, record the owner, compartment, visibility, admin group, and retention policy. This information helps respond quickly when a build needs to be revoked or when diagnosing lost pull access.

### 12.2. Diagnosing by Failure Step

| Symptom | First Area to Check | Evidence to Collect |
| --- | --- | --- |
| `docker login` reports unauthorized | Full username, domain, auth token | Registry host and username format; do not record token |
| Login succeeds but push is denied | Publishing permissions and target repository | Identity, compartment, granted permissions |
| Repository not found | Region, namespace, exact name | List output in the expected region and compartment |
| `manifest unknown` | Whether tag or digest exists | Full reference and whether image still exists in registry |
| DNS failure or timeout | Network path to endpoint | DNS resolution, HTTPS connectivity, routes, and egress |
| Runtime pull fails while laptop pull works | Runtime credentials and networking | Configuration at the actual place pulling the image |
| No manifest for machine architecture | Image architecture and host architecture | Image platform or manifest list |
| Storage not reduced after deletion | Asynchronous deletion job | Deletion timestamp and subsequent storage metrics |

These are triage directions, not conclusions drawn from a single error string alone. Troubleshooting should proceed in order: **endpoint → network → identity → permissions → image reference**.

When sending logs for support, retain the commands with secrets redacted, timestamps, and full error messages; remove tokens, credentials, and secret contents.

## 13. Completing the Lab and Application Principles

After completing the lab, stop any test containers and log out of the registry if the lab environment no longer needs credentials:

~~~bash
docker logout "$REGISTRY"
~~~

`docker logout` does not delete images or repositories on OCI. Cleaning up lab artifacts should be done in the specific repository after confirming they are no longer in use. Do not apply a broad region-level deletion policy just to clean up a single lab exercise.

When applying this in real projects, every repository should have a clear owner, permission boundary, and purpose. Release records must preserve digests; retention policies must protect running builds and rollback builds. Reliable deployments depend simultaneously on artifacts remaining present, identities having permissions, and functioning network paths.
