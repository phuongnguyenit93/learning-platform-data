# Least Privilege for Builder, Runner, Runtime Container, and Registry

A Spring Boot Native Image pipeline has multiple components working together to build and run an application: the build environment, CI runner, image registry, deployment system, and the container serving requests. If all of them share a single administrative account, a bug in a build step or a compromised container can pivot to source code, the registry, clusters, and other infrastructure.

**Least privilege** requires each component to hold only the permissions needed for its task, within the exact scope of resources and duration required. The builder needs to read source and dependencies to produce an executable; the release job needs to push images to the designated repository; the runtime node needs to pull images; the running application only needs to access databases, brokers, or business APIs per granted permissions.

This lesson designs permission boundaries across the entire native container lifecycle: builder and compiler, CI runner, BuildKit/Docker daemon, dependency-fetch credentials, registry push/pull, deployment identity, runtime container, and Kubernetes ServiceAccount. Examples focus on Spring Boot Native Image, Docker, Kubernetes, and GitHub Actions; the principles apply to other CI/CD systems and registries.

## 1. Why must permissions be separated by stage?

Native Image typically needs a build job with substantial CPU/RAM resources and permission to read dependencies. That does not mean the running application process needs similar permissions.

For example, a service may need:

- Build job to read the source repository, download Maven dependencies, and produce an executable.
- CI runner to run the native-image compiler, tests, and package the OCI image.
- Publisher to push the image to a specific repository.
- Kubernetes node or kubelet to pull the image to start the Pod.
- Runtime container to call PostgreSQL and a message broker.
- Deployment controller to update workloads in the assigned namespace.

If one credential with read/write/delete access across all repositories and clusters is shared, independent tasks collapse into one large trust domain. An injected build script could steal publish credentials; an exploited runtime container could steal CI tokens if tokens were mounted into the container.

The goal is to partition permissions, identities, lifetimes, and network scope to limit blast radius when one component is compromised.

## 2. Trust boundaries in the pipeline

The diagram below shows the identities that should be separated:

~~~mermaid
flowchart TD
    A["Source repository<br/>read-only checkout"] --> B["Ephemeral CI runner"]
    B --> C["Native Image builder<br/>source + dependency read"]
    C --> D["Test artifact"]
    D --> E["Release publisher<br/>repository push only"]
    E --> F["Container registry"]
    F --> G["Node / kubelet<br/>image pull only"]
    G --> H["Runtime container<br/>non-root"]
    H --> I["Database / broker / API<br/>scoped application access"]
    B --> J["Deployment job<br/>namespace-scoped deploy"]
    J --> K["Kubernetes API"]
~~~

The arrows represent access paths, not a single account passed down the entire pipeline. Artifacts pass between steps; builder credentials do not need to travel alongside the artifact to the publisher or runtime.

A useful rule of thumb: **artifacts can flow forward through the pipeline; credentials are granted only at the exact step that needs them**.

## 3. Least-privilege permission matrix

| Component | Permissions needed | Permissions normally not needed |
|---|---|---|
| Source checkout | Read allowed repository and submodules | Push source, repository admin |
| Native builder | Read source, dependency registry; write build output | Production database, cluster-admin, registry delete |
| CI runner | Execute job and access job artifacts | Shared host/daemon administrative rights |
| Test job | Read image/artifacts and call test dependencies | Push release image, deploy to production |
| Image publisher | Push to authorized repository | Delete repository, organization admin |
| Registry pull identity | Pull workload image | Push, delete, or modify repository permissions |
| Deployment job | Update workload in assigned namespace/environment | Cluster-admin, read all Secrets |
| Runtime container | Call required business dependencies | Docker socket, registry push, Kubernetes API if unused |
| Runtime ServiceAccount | Minimal API permissions if app actually calls Kubernetes API | Broad default permissions or cross-namespace access |
| Registry administrator | Manage repositories and policies per admin duties | Using this credential in build/test/runtime |

Not every pipeline runs every role as a separate process. One runner may execute multiple jobs, yet credentials and permissions for each job should still be separated. If builder and publisher run in the same workflow, grant publish permissions only to the release job after tests pass.

## 4. Native builder permissions

The builder includes GraalVM Native Image, JDK, compiler, linker, Spring AOT processing, and build tools such as Maven/Gradle. Its job is to turn source and dependencies into a native executable.

The builder normally needs only:

- Read access to the source code of the repository being built.
- Read access to Maven/Gradle dependencies from allowed artifact registries.
- Read access to required base images or builder images.
- Write access for generated sources, caches, and binaries within the workspace.
- CPU/RAM and process resources required for compilation.

The builder does not need permission to read production databases, access the Kubernetes API, modify registry permissions, or administer cloud accounts. If the build has a step that fetches schemas/configs from another system, grant read access strictly to that resource and consider bringing needed data into source/artifacts.

Native Image compilation itself does not require the application to run as root. If a buildpack, Docker daemon, or specific toolchain requires system privileges, identify the exact component requiring them and its permission scope; do not grant privileged mode to the entire builder container by default.

## 5. Builder images, Buildpacks, and daemon permissions

Cloud Native Buildpacks separate the builder image from the run image. The builder contains buildpacks and artifact creation tools; the run image contains the platform needed to run the application. The runtime container does not need a compiler simply because the builder used one.

With Docker-based builds, the runner may invoke the Docker daemon to build images. Pay special attention to daemon access: the Docker daemon typically runs with root privileges, and anyone able to control the daemon can request host filesystem mounts or create privileged containers. Thus, access to the Docker socket can be equivalent to very high privilege on the runner host.

Do not mount `/var/run/docker.sock` into application containers or untrusted test containers. If a build job needs a daemon:

- Use a dedicated runner or ephemeral runner for jobs with daemon access.
- Do not run untrusted source against a daemon with privileged host access.
- Consider Docker Rootless or rootless BuildKit if compatible with the workflow.
- Do not share an administrative daemon across jobs from repositories/tenants of different trust levels.
- Clean up the runner/workspace and credentials after the job.

Docker Rootless runs both the daemon and containers under an unprivileged user inside a user namespace, reducing impact if the daemon or a container is compromised. Rootless has specific kernel/subuid/subgid requirements and compatibility limits; verify before switching.

## 6. CI runner permissions

The CI runner is the workflow execution environment, not the application's identity. The runner should be granted minimal permissions to check out code, run compilers, store artifacts, and call only the services needed by the job.

For self-hosted runners:

- Prefer ephemeral runners provisioned for a single job or group of jobs at the same trust level.
- Do not share workspaces between jobs with sources/credentials of differing trust levels.
- Do not run pull requests from forks on runners holding secrets or sensitive Docker daemons.
- Restrict network access from runners to production networks.
- Do not retain cloud credentials, registry tokens, or kubeconfigs after a job completes.
- Restrict who can manage runners and install extensions/actions.
- Keep the OS, Docker/BuildKit, and runner agent patched.

A runner executing native compilation may require substantial RAM/CPU, yet resource quotas are not security permissions. Configure resource limits separately and decouple system access permissions from allocated compute resources.

## 7. Using short-lived credentials instead of long-lived secrets

Credentials should be short-lived, narrowly scoped, and issued right before the operation that needs them. When the platform supports workload identity or OIDC federation, CI can exchange a short-lived identity token for registry/cloud credentials rather than storing long-lived access keys in a secret store.

For example, in GitHub Actions, a job requesting an OIDC token needs:

~~~yaml
permissions:
  id-token: write
  contents: read
~~~

`id-token: write` allows the job to request a JWT from the GitHub OIDC provider; it **does not automatically grant write access to cloud resources**. The cloud provider still must configure trust relationships and IAM roles/policies specifying which repository, branch, tag, environment, audience, and subject may exchange the token.

Restrict trust policies to specific repositories and release refs/environments. Do not allow every branch or every workflow in an organization to assume the same production role.

If a registry/cloud does not support OIDC, use dedicated automation tokens with scoped permissions, expiration, and rotation. Never use personal account passwords as long-lived pipeline credentials.

## 8. Scoping GitHub Actions permissions per job

Do not grant `write-all` at the workflow level if only one job needs to publish. Set default permissions to none, then open exact scopes per job:

~~~yaml
name: native-image-ci

on:
  pull_request:
  push:
    tags:
      - "v*"

permissions: {}

jobs:
  verify:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Build and test native executable
        run: ./mvnw -Pnative verify

  publish:
    if: github.event_name == 'push'
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Build and publish image
        run: ./ci/publish-native-image.sh
~~~

This illustrative example separates verify and publish. The publish script must log into the registry using a job-scoped token and push only to allowed packages/repositories. With GitHub Container Registry, `packages: write` is typically the workflow permission needed to publish packages; package permissions and linked repository settings must also permit it.

In production, pin third-party actions to verified full commit SHAs rather than mutable tags. If a job generates provenance/attestations or uses OIDC to sign/release, add the exact permissions such as `attestations: write` or `id-token: write` only on the job that needs them. Do not grant them to the verify job simply because the publish job requires them.

## 9. Separating test jobs from release jobs

Pull requests from forks or unreviewed sources must be treated as untrusted. A build script can execute arbitrary code via Maven/Gradle plugins, annotation processors, tests, or build scripts.

Pipeline design:

- **Verify job:** read-only checkout, build/test, no registry push token, no production credentials.
- **Package job:** packages the image after source review; permissions scoped solely to target registry.
- **Publish job:** runs on protected branches/tags or approved environments, holding image push permissions.
- **Deploy job:** uses a separate identity authorized to update the target namespace/environment.
- **Runtime:** inherits no tokens from any CI job.

Do not pass secrets into jobs executing code from untrusted pull requests. In GitHub Actions, avoid using `pull_request_target` to check out and execute pull request code with a write-privileged token; this event has a different permission context and requires careful design.

## 10. Maven and Gradle secrets during native builds

The native builder may need credentials to read private Maven repositories, plugin repositories, or Git repositories. These credentials should only have read access to required artifacts.

With Docker BuildKit, use secret mounts instead of Dockerfile `ARG` or `ENV`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM ghcr.io/graalvm/native-image-community:25 AS native-build

WORKDIR /workspace
COPY . .

RUN --mount=type=secret,id=maven_settings,target=/run/secrets/settings.xml \
    ./mvnw -s /run/secrets/settings.xml -Pnative package
~~~

Pass the credential file only for that build step:

~~~bash
docker buildx build \
  --secret id=maven_settings,src=./settings-ci.xml \
  -t orders-service:native .
~~~

Secret mounts are exposed to the build command's execution environment when needed and are not baked into image layers the way `ARG`/`ENV` can be. Do not `COPY` settings files containing passwords into the build context or print tokens to logs. Use `.dockerignore` to exclude credential files, `.env`, private keys, and kubeconfigs from the context.

With Gradle, use a credential provider or secret mount for repository credentials; do not commit passwords into `gradle.properties` or build scripts. If build caches are shared across tenants/jobs, check cache read permissions and cache contents before sharing.

## 11. Distinguishing build secrets from runtime secrets

These two categories of secrets have different purposes and lifecycles:

| Secret | Who uses it | Permissions required | When it exists |
|---|---|---|---|
| Maven repository token | Builder | Read artifacts/private plugins | During dependency download step |
| Git SSH key | Builder | Read designated repository | During source fetch step |
| Registry push token | Publisher | Push to specific image repository | During publish step |
| Registry pull credential | Kubelet/node or credential provider | Pull image | When node starts the container |
| Database password | Runtime application | Target database/schema/role | While application needs connections |
| Cloud workload credential | Application or deploy job | Designated APIs and resources | Short-lived token scoped to workload/job |
| Kubernetes API token | Application actually calling API or deploy job | Appropriate Role/ClusterRole | During Kubernetes operations |

Do not use database passwords as build arguments. Do not use registry push tokens as image pull credentials. Do not copy a deploy job's `kubeconfig` into an image. Do not allow a runtime container to read an entire secret store just because one bean needs one credential.

## 12. Registry permissions: pull, push, and admin

A registry should have distinct identities per operation:

- **Pull identity:** read-only access to images of repositories/workloads that need to run.
- **Push identity:** write access restricted to the released service's repository.
- **Delete/admin identity:** manages tags, retention, repositories, and permissions; granted only to authorized administrators or admin automation.

For example, a build job pulling base and dependency images may need only read permission on those repositories. The publish job is granted write access to `orders-service`. Application nodes only need to pull `orders-service`; they never need to push or delete images.

If using Docker Hub, choose tokens with the lowest repository permission sufficient for the task. A token pulling private base images can use Repo Read-only; publish automation needs write access within a managed scope. Organization access tokens can restrict repositories and operations per supported configuration.

Never use a single full-privilege personal token across all workflows. Push credentials must support expiration/rotation and independent revocation.

## 13. Protecting images and tags in the registry

The registry stores release artifacts; write access to the registry therefore directly impacts production.

Recommended controls:

- Separate repositories by service or trust boundary.
- Enable tag immutability if supported by the registry.
- Prevent routine jobs from deleting images/tags.
- Allow only verified publishers to create release tags.
- Deploy by immutable digest rather than relying solely on mutable tags like `latest`.
- Enable image scanning and store SBOMs.
- Enable audit logging for logins, pulls, pushes, deletes, and permission changes.
- Restrict retention/deletion policies to avoid accidentally removing running images.
- Verify signatures/provenance before deployment if your organization enforces admission policies.

Tags help humans identify versions; digests pinpoint exact image contents. Deploying by digest ensures the cluster runs the exact tested artifact.

## 14. Runtime container permissions and the non-root principle

A native executable does not need to run as root just because it was built by GraalVM. Choose a non-zero UID/GID, grant read permission on the binary and config, and allow writes only to required directories.

Dockerfile example:

~~~dockerfile
FROM debian:bookworm-slim

WORKDIR /app
COPY --chown=10001:10001 application /app/application

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/application"]
~~~

At runtime, the application needs only to:

- Read the executable, resources, CA certificates, and mounted configuration.
- Write to temporary directories or authorized volumes.
- Bind the application port.
- Connect to dependencies permitted by network policy.
- Read only the required runtime secrets.

If a service merely listens on port 8080, it generally does not need the Linux `NET_BIND_SERVICE` capability. Prefer ports above 1024 so all capabilities can be dropped.

## 15. Docker runtime security options

Example running a container with common restrictions:

~~~bash
docker run --rm \
  --user 10001:10001 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --memory=512m \
  --cpus=1 \
  --pids-limit=128 \
  --publish 8080:8080 \
  orders-service@sha256:REPLACE_WITH_VERIFIED_DIGEST
~~~

Meaning of the flags:

- `--user`: runs the process under an unprivileged UID/GID.
- `--read-only`: prevents writes to the root filesystem.
- `--tmpfs`: provides a bounded temporary area for runtime files.
- `--cap-drop=ALL`: drops Linux capabilities not needed by the application.
- `no-new-privileges`: prevents processes from gaining privileges via setuid/setgid.
- `--memory`, `--cpus`, `--pids-limit`: bounds resources and process/thread count.

Docker applies the daemon's default seccomp profile; if using a custom profile, test it against the native runtime and actual JNI libraries. Do not enable `--privileged`, host PID/network namespaces, or broad host path mounts without an explicit requirement. Specifically, never mount the Docker socket into a runtime container.

Resource limits must be measured against actual workloads. Native Image may need memory for the heap, thread stacks, direct buffers, and native libraries; setting memory limits too low can trigger OOM kills.

## 16. Kubernetes SecurityContext under the Restricted standard

Kubernetes lets you configure user, group, capabilities, seccomp, and filesystem permissions at the Pod/container level.

Example ServiceAccount and Deployment:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-runtime
  namespace: production
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-native
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-native
  template:
    metadata:
      labels:
        app: orders-native
    spec:
      serviceAccountName: orders-runtime
      automountServiceAccountToken: false
      imagePullSecrets:
        - name: orders-registry-pull
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: orders
          image: registry.example.com/orders/orders-service@sha256:REPLACE_WITH_VERIFIED_DIGEST
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
            sizeLimit: 64Mi
~~~

This is a starting baseline, not a manifest to apply verbatim to every application. If the application needs to write files, mount a specific volume with proper permissions. If a supplementary group is needed to access a volume, add only the required group.

Fields like `runAsNonRoot`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, and `seccompProfile: RuntimeDefault` align with the core requirements of the Kubernetes Restricted Pod Security Standard on Linux. Namespaces can apply Pod Security Admission to enforce this policy.

## 17. Application ServiceAccounts and imagePullSecrets are separate concerns

A Kubernetes ServiceAccount provides an identity for processes inside a Pod when calling the Kubernetes API. `imagePullSecrets` are used by the kubelet to authenticate with a registry when pulling images. These two credentials serve two distinct purposes.

If a Spring Boot service does not call the Kubernetes API, set:

~~~yaml
automountServiceAccountToken: false
~~~

The Pod then does not automatically mount an API token into the container filesystem. This does not prevent the kubelet from using `imagePullSecrets` to pull the image.

If the application genuinely needs to call the Kubernetes API:

1. Create a dedicated ServiceAccount for the service.
2. Create a Role permitting only the required verbs/resources in the namespace.
3. Bind that Role to the ServiceAccount via a RoleBinding.
4. Use short-lived token projection/TokenRequest whenever possible.
5. Do not grant broad ClusterRoleBindings when operating within a single namespace.
6. Do not reuse the deployment controller's ServiceAccount for the runtime application.

Do not rely on default permissions of the `default` ServiceAccount. Declare identities explicitly for review and auditing.

## 18. Node runtime image pull credentials

The container process does not need registry passwords to pull its own image. In Kubernetes, the kubelet/container runtime performs the pull before starting the container.

Options include:

- `imagePullSecrets` in the same namespace as the Pod.
- Kubelet credential provider plugins.
- Node identity or workload federation depending on platform capabilities.
- Private registry endpoints with policies scoped to specific node pools/workloads.

Pull secrets need only read permission for the images to be run. Do not place pull credentials into Spring Boot environment variables. Do not mount `.dockerconfigjson` into application containers.

When using platform credential providers or workload identity, verify the Kubernetes version, node configuration, and supported token-exchange mechanisms. Do not assume a Pod's ServiceAccount token is always used by the kubelet to pull images across every cluster.

## 19. Cloud permissions for runtime workloads

A Spring Boot service may call object storage, queues, KMS, or a secret manager. Grant workload permissions scoped to specific resources and operations.

Examples:

| Need | Permission to grant |
|---|---|
| Read config files from object storage | Read on exact bucket/prefix |
| Write reports | Write on exact bucket/prefix |
| Send messages | Publish to exact topic/queue |
| Receive messages | Consume from exact queue/subscription |
| Decrypt data | KMS decrypt on exact key |
| Read secrets | Get exact secret name/version |
| Call internal API | Identity with matching audience/scope |

Use Kubernetes Workload Identity, cloud workload federation, or short-lived credentials if supported by the platform. Avoid storing long-lived cloud access keys in Docker images, ConfigMaps, or manifests. If secret mounts are needed, mount only into the container and path that requires them.

Separate the runtime identity from the deploy identity. An application does not need permission to create Pods, edit Deployments, or read Secrets across a namespace just because CI needs to deploy it.

## 20. Network policies and connectivity permissions

Network access is also part of least privilege. Runtime containers should connect only to required dependencies such as databases, brokers, DNS, and internal APIs.

A solid policy defines:

- Ingress from required ingress controllers/services.
- Egress to required database and broker ports.
- DNS egress to the cluster resolver.
- HTTPS egress to required APIs/identity providers.
- No arbitrary access to metadata endpoints, node management ports, or other sensitive services.

Kubernetes NetworkPolicy requires a CNI that supports enforcement. Creating NetworkPolicy resources without cluster enforcement provides no actual network boundary. Verify using tests for both allowed and denied connections.

Do not use host networking to work around ordinary connectivity issues. Configure Services, DNS, and policies properly instead of opening the node's entire network namespace.

## 21. Native Image does not replace container security layers

Native Image removes the need for a JRE when running the executable, yet the process still runs under a Linux user and can access permitted filesystems, networks, syscalls, and shared libraries.

Points to remember:

- JNI/native libraries run inside the same process and can execute native operations with the process's privileges.
- Replaceable or unverified shared libraries can open code-execution paths.
- The dynamic loader and libc must be patched just like other runtime packages.
- Resources/configs packaged into the image can still leak sensitive data if built improperly.
- A native binary without a shell does not mean it cannot be exploited.
- Reflection/AOT metadata is runtime compatibility configuration, not OS access control.
- JFR, heap dumps, and diagnostic endpoints can expose data if exposed with improper permissions.

Keep container defense layers intact: user namespaces, seccomp, capabilities, read-only filesystems, network policies, secret isolation, and image provenance.

## 22. Filesystem and temporary file controls

Native executables may require temporary files, certificates, timezone data, external classpath resources, or diagnostic directories. Running with a read-only root filesystem forces the application to write only to explicitly granted areas.

Recommendations:

- Use `/tmp` backed by tmpfs or an emptyDir with a size limit.
- Mount upload/cache directories at exact paths with quotas.
- Set owner/group to match the process UID/GID.
- Mount secrets read-only with minimal read permissions.
- Never mount host root, home directories, or the Docker socket.
- Never copy `application.yml` containing passwords into the image.
- Never write heap dumps or diagnostic files into shared volumes without access/retention controls.

If the application needs persistent file storage, use a volume/storage service designed for that data. Do not use the container's writable layer for long-term storage.

## 23. SBOMs, scanning, and artifact verification

Least privilege limits the impact of compromised credentials; supply-chain verification helps ensure images come from trusted sources and toolchains.

For each released image, retain:

- Image digest and source commit.
- GraalVM/JDK, Spring Boot, and Native Build Tools versions.
- Builder image and run image digests.
- Build arguments and target OS/architecture.
- SBOMs for application dependencies and OS packages.
- Vulnerability scan results.
- Provenance/attestations and signatures if supported by the pipeline.

Scan the final image, including shared libraries and CA packages—not just Maven dependencies. A native image has no JRE, yet it still relies on libc, zlib, JNI libraries, and OS packages requiring patches.

Deploy by scanned and signed digest. Admission policies can require signatures/provenance from an authorized release identity. Signing credentials must live in the publisher/signing job, never inside the runtime container.

## 24. Auditing, rotation, and revoking permissions

Least privilege must be maintained after the pipeline is up and running. Every credential should have an owner, purpose, scope, expiration, and revocation procedure.

Periodically audit:

- Which credentials have gone unused for an extended period?
- Which tokens hold write/delete rights when the job only needs read?
- Which repositories allow pushes from unprotected branches?
- Which Pods still mount a ServiceAccount token without calling the Kubernetes API?
- Which workloads run as root, privileged, or with extra capabilities?
- Which containers mount host paths or the Docker socket?
- Which roles hold broader namespace/resource permissions than needed?
- Which images lack SBOMs, scans, or provenance?
- Which long-lived runners retain old workspaces/caches/secrets?

When a credential compromise is suspected: revoke the token, stop affected jobs/runners, inspect registry/cloud/cluster audit logs, identify altered digests, rebuild images from trusted sources, and redeploy verified digests. Never merely delete the secret from a workflow and consider the incident closed.

## 25. Incident scenarios and blast-radius containment

| Incident | With combined permissions | With separated permissions |
|---|---|---|
| Malicious pull request runs build script | Could steal registry push tokens or cloud keys | Verify job has no secrets/publish permissions |
| Builder compromised | Could access production and clusters | Reads only source/dependencies, writes workspace |
| Registry pull token leaked | Could push/delete images | Token can only pull assigned repository |
| Runtime container exploited | Could access Docker socket or host filesystem | Non-root, read-only, no capabilities, no host mounts |
| Deployment job compromised | Could administer entire cluster | Role updates only the assigned namespace/environment |
| App needs to call cloud APIs | Could use account-wide static keys | Workload identity scoped to specific resources with short-lived tokens |
| Image tag overwritten | Nodes could pull a different artifact under the same tag | Tag immutability and deploy by digest |

The goal is not assuming every incident can be prevented. The goal is ensuring that when one component is compromised, the attacker does not automatically inherit the permissions of all remaining components.

## 26. Hands-on lab: separating build, push, and runtime pull permissions

Suppose a service named `orders-service` is built with GraalVM Native Image, stored in a private registry, and run on Kubernetes.

### Step 1 — Define the three identities

- Builder: reads repository and Maven dependencies, creates the native executable.
- Publisher: pushes the image to `registry.example.com/orders/orders-service`.
- Runtime: kubelet pulls the image; the process runs as UID 10001 and needs no registry credentials.

Do not share the same token across all three.

### Step 2 — Configure build secrets

Use a BuildKit secret mount to supply Maven settings strictly during the build step. Do not copy the file into the image and do not pass passwords via Dockerfile `ARG`/`ENV`.

### Step 3 — Configure registry permissions

- Builder can pull builder/base images.
- Publisher can push to the exact repository.
- Runtime pull credential has read-only access to the image.
- Neither automated identity is granted delete/admin rights.

### Step 4 — Harden runtime

Run the container as non-root with a read-only root filesystem, drop all capabilities, and mount a bounded `/tmp`. Do not mount the Docker socket or host paths.

### Step 5 — Harden Kubernetes identity

Create a dedicated ServiceAccount. If the service does not call the Kubernetes API, disable token automounting. Declare `imagePullSecrets` separately for the kubelet using only a pull-permitted secret.

### Step 6 — Negative testing

Run the following checks in a test environment:

- Builder cannot access the production database.
- Verify job cannot push release images.
- Pull identity cannot push or delete images.
- Runtime process cannot read a ServiceAccount token when automount is disabled.
- Runtime container cannot write to the root filesystem.
- Runtime container holds no unneeded capabilities.
- Runtime identity cannot read another service's secrets.
- Deployment identity cannot modify resources outside its assigned namespace.

A meaningful security test must confirm both allowed permissions and denied actions.

## 27. Pre-release checklist

- [ ] Builder reads only required source/dependencies and writes to an isolated workspace.
- [ ] Runners are isolated, preferably ephemeral, and do not share daemons with untrusted jobs.
- [ ] Docker socket is not exposed to application/test containers.
- [ ] Pull requests receive no secrets, registry push tokens, or production credentials.
- [ ] Build secrets use secret mounts/secret stores, never Dockerfile ARG/ENV.
- [ ] CI credentials are short-lived via OIDC/federation where supported by the platform.
- [ ] Publisher pushes only to the assigned repository; no delete/admin rights.
- [ ] Runtime pull identity has read-only access to the image being deployed.
- [ ] Image is pinned by digest, scanned, and has SBOM/provenance archived.
- [ ] Container runs as non-root, non-privileged, and disallows privilege escalation.
- [ ] Root filesystem is read-only; writable directories are mounted separately with quotas.
- [ ] All Linux capabilities are dropped unless the service requires a specific capability.
- [ ] An appropriate seccomp profile is enabled.
- [ ] Dedicated Kubernetes ServiceAccount and minimal RBAC.
- [ ] ServiceAccount token automount disabled if the app does not call the Kubernetes API.
- [ ] Registry pull secret separated from application credentials.
- [ ] Cloud workload identity holds only required resource/operation permissions.
- [ ] NetworkPolicy is enforced by the CNI and opens only required flows.
- [ ] Credentials have owners, expirations, rotation, and revocation procedures.
- [ ] Denied actions have been verified via testing.

## 28. Takeaways

Least privilege for Native Image containers must be applied at every stage: builder, CI runner, publisher, registry, deployment, and runtime. The builder needs read access to source/dependencies; the publisher needs push access to the assigned repository; the kubelet needs pull access; the application only needs access to its business dependencies.

Separate credentials, use OIDC/short-lived tokens, BuildKit secret mounts, distinct registry read/write identities, isolated runners, and immutable image digests. At runtime, enforce non-root, read-only filesystems, dropped capabilities, seccomp, network policies, and minimal ServiceAccount/RBAC. If the application does not call the Kubernetes API, do not mount a ServiceAccount token.

Native Image does not create a sandbox on its own. JNI, shared libraries, and the executable still carry the privileges of the process/container. **A secure pipeline must protect both the artifact and the identities authorized to build, publish, deploy, and run that artifact.**

### References

- Docker Engine — Security: https://docs.docker.com/engine/security/
- Docker Engine — Rootless mode: https://docs.docker.com/engine/security/rootless/
- Docker Build — Build secrets: https://docs.docker.com/build/building/secrets/
- Docker Build — SecretsUsedInArgOrEnv check: https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/
- Docker Hub — Access token permissions: https://docs.docker.com/security/access-tokens/reference/
- GitHub Actions — OpenID Connect: https://docs.github.com/en/actions/reference/security/oidc
- GitHub Actions — Workflow permissions: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Kubernetes — Configure a Security Context: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Kubernetes — Service Accounts: https://kubernetes.io/docs/concepts/security/service-accounts/
- Kubernetes — Application Security Checklist: https://kubernetes.io/docs/concepts/security/application-security-checklist/

Exact permissions, token exchange details, registry scopes, and Pod Security Admission behavior depend on your CI, registry, Kubernetes, and cloud provider versions. Always verify the active policies enforced in the deployment environment, not just the committed YAML.
