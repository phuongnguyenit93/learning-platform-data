# Controlling Runner Permissions and Network Access

A CI/CD runner or agent is where the pipeline executes source code, installs dependencies, runs tests, produces artifacts, and sometimes deploys software. Because the runner directly handles source code and credentials, its permissions and network reachability determine the blast radius if a job fails or runs untrusted code.

A runner can read repositories, access registries, call test services, download dependencies, connect to cloud APIs, or deploy to target environments. If every job shares one machine with broad permissions and open networking, a small change in a pull request can become an entry point to sensitive resources. Execution environments must therefore follow least privilege, trust-level isolation, need-based network restriction, and post-job resource revocation.

This lesson focuses on two tightly coupled controls: **what a runner is allowed to do** and **where a runner is allowed to connect**. It covers runner identity, per-job permissions, ingress/egress networking, runner isolation, secret management, self-hosted runners, incident response, and a practical implementation roadmap for CI/CD systems.

## 1. Runner Roles and Trust Boundaries

A runner is the environment executing one or more jobs. Depending on the platform, a runner may be a provider-managed virtual machine, a self-hosted server, a container, a Kubernetes pod, or an ephemeral environment created per job.

A job typically performs several tasks:

- Checking out source code from a repository.
- Downloading dependencies and toolchains.
- Running build or test scripts.
- Spinning up containers and backing services.
- Reading from or writing artifacts to a registry.
- Calling cloud or deployment platform APIs.
- Connecting to test, staging, or production environments.
- Reporting logs and status back to the CI/CD control plane.

Each operation may require OS privileges, repository access, application credentials, or network connectivity. Therefore, define clear trust boundaries between components:

| Component | Role | Risks to control |
|---|---|---|
| CI/CD control plane | Scheduling, dispatching jobs, storing state, managing configs | Orchestration privileges, tokens, and workflow configurations |
| Runner host | Supplies CPU, memory, filesystem, and networking to jobs | OS privileges, leftover processes, network access |
| Job process | Executes scripts, builds, and tests | Malicious code or unexpected commands |
| Job container / VM | Isolates processes and dependencies | Shared kernel, volumes, sockets, or credentials |
| Secret manager / identity provider | Issues authentication credentials | Token abuse, overly broad scope, and credential lifetime |
| Registry / artifact store | Stores dependencies and build outputs | Artifact overwriting, unauthorized access, cache poisoning |
| Deployment environment | Runs the application | Out-of-scope changes, data exposure, or service disruption |

Crucially, repositories, pull requests, pipeline definitions, and executed scripts can all influence runner behavior. A job running code from an untrusted branch must be treated as capable of executing arbitrary commands within whatever permissions the runner grants.

## 2. Assessing Trust Levels Before Assigning Runners

Not every job carries the same level of trust. Workloads can be grouped by code origin and required permissions:

| Job group | Code origin / trust level | Appropriate permissions |
|---|---|---|
| Fork PR checks | May contain untrusted code | Ephemeral runner, minimal read access, no sensitive secrets |
| Internal feature branch builds | Controlled within repository, still requires bounds | Isolated shared runner, read access to dependencies |
| Integration testing | Needs connectivity to test services | Runner in test network, dedicated test data and credentials |
| Release artifact builds | Commit passed integration gates | Scoped registry write permission and verified identity |
| Staging deployment | Verified inputs | Staging deploy permissions, network restricted to target endpoints |
| Production deployment | High blast radius | Dedicated runner or job, approval gates, short-lived credentials |

An internal pull request is not automatically risk-free. Privileged repository accounts can be compromised, dependencies can be poisoned, or workflows can be altered unintentionally. Runner permissions must rest on policy and technical boundaries rather than merely assuming commit authors are trustworthy.

Separate at least the following groups whenever risk warrants it:

- Runners processing untrusted code.
- Runners building and testing shared branches.
- Runners authorized to publish artifacts.
- Runners or jobs authorized to deploy to sensitive environments.

Separation can be implemented using runner pools, labels, machine groups, OS accounts, network segments, or ephemeral environments. Exact implementation depends on scale and platform, but permission boundaries must be auditable.

## 3. Enforcing Least Privilege on Runners

Least privilege means each runner and job receives only the permissions needed for its current task, strictly scoped in capability and duration.

### 3.1. Distinguishing Host Permissions from Job Permissions

Consider two distinct permission layers:

- **Runner host permissions:** OS administrative privileges, software installation, service management, filesystem access, and network configuration.
- **Job permissions:** reading source code, writing artifacts, calling APIs, accessing secrets, or deploying applications.

Routine jobs should never execute with host administrative privileges. If a job requires Docker, Kubernetes, or special system operations, evaluate it separately because certain privilege grants allow a job to take over the host.

Never grant administrative accounts merely to bypass build permission errors. Identify the exact directory, socket, or operation required and grant narrower permissions.

### 3.2. Separating Identities by Function

Do not use a single machine account authorized to read every repository, write to every registry, and deploy to every environment. Provision separate identities or credentials for:

- Repository checkout.
- Reading packages and dependencies.
- Publishing artifacts.
- Reading test-environment secrets.
- Deploying to staging.
- Deploying to production.

A unit test job typically needs only read access to source code and dependencies. A publish job needs write access scoped to the target repository or package namespace. A staging deploy job needs permission to deploy to staging, not production.

### 3.3. Short-Lived Tokens and Workload Identity

Where supported by the platform, use short-lived credentials or workload identity federation instead of long-lived static keys stored on runners.

For instance, a job can obtain a temporary token via OIDC or an equivalent identity federation mechanism. The target system verifies issuer, audience, subject, and trust conditions before granting access. Configurations must constrain tokens to specific repositories, branches, environments, or approved workflows.

Do not simply enable OIDC and attach broad roles. Trust policies must specify precisely which workload may assume the identity and what permissions it receives. Once the job finishes, short-lived credentials expire on schedule.

### 3.4. Restricting Write Permissions

Write permissions typically carry greater impact than read permissions. A job with write access to a repository, package registry, or deployment target can alter outputs others trust.

Ensure you:

- Grant write permissions only to jobs that genuinely publish or deploy.
- Scope target package namespaces and repositories tightly.
- Enforce environment protection rules requiring approvals.
- Never pass write tokens to test steps running untrusted code.
- Audit the identity that performed each write and its associated artifact.

## 4. Controlling Network Access

Runners need networking to talk to the control plane, fetch dependencies, call test services, and potentially deploy applications. However, unrestricted networking expands what job code can reach.

Distinguish two traffic directions:

- **Outbound (egress):** connections initiated outward by the runner or job, such as fetching dependencies, sending logs, or calling APIs.
- **Inbound (ingress):** connections initiated from external systems toward the runner, such as accessing a service inside the job or remote host administration.

Conceptual network flow diagram:

~~~mermaid
flowchart LR
    B["Runner"] -->|"Agent opens bidirectional outbound channel"| A["CI/CD control plane"]
    B -->|"Allowlisted HTTPS / API"| C["Dependency registry"]
    B -->|"Restricted connectivity"| D["Test services"]
    B -->|"Short-lived credentials"| E["Identity / secret service"]
    B -->|"Scoped publish"| F["Artifact registry"]
    B -->|"Environment-scoped deploy"| G["Staging / Production"]
    H["Internet or other internal networks"] -. "Blocked unless required" .-> B
~~~

On many platforms, the runner agent initiates an outbound connection to the control plane to poll for jobs and report status. Exact mechanics vary by vendor. Never open broad inbound ports just so a runner can communicate with the CI/CD platform; verify official platform networking requirements and open only the required destinations, protocols, and ports.

### 4.1. Inventory Required Network Destinations

Before configuring firewalls or network policies, list the exact destinations jobs genuinely require:

| Network destination | Purpose | Recommended policy |
|---|---|---|
| CI/CD control plane | Pick up jobs and report status | Allow only documented endpoints, protocols, and ports |
| Git repository | Check out source and fetch metadata | Allow only required hosts or endpoints |
| Package registry | Download dependencies | Restrict domains/namespaces and require TLS |
| Artifact registry | Publish or download artifacts | Per-repository permissions, dedicated auth |
| Secret / identity provider | Obtain authorized credentials | Restricted to valid jobs and identities |
| Test services | Integration or smoke testing | Allow only required test-network traffic |
| Cloud / deployment API | Provision or deploy resources | Scope endpoints, roles, and environments |
| Observability services | Ship logs, metrics, and status | Use internal or approved endpoints |

Validate this list using network logs and platform documentation. Never allow full Internet egress merely because required endpoints are unknown. When public dependencies are needed, use an internal proxy or mirror to govern sources and traffic.

### 4.2. Egress Filtering

Egress filtering constrains outbound connections from runners. It can be enforced by:

- Domain or FQDN.
- IP address or CIDR block.
- Port and protocol.
- Network segment or security group.
- Authenticating and logging proxy.
- DNS policy and approved resolvers.

IP-based filtering can be brittle with cloud services using dynamic IPs. Domain-based filtering requires understanding how firewalls or proxies inspect DNS, TLS, and HTTP redirects. Use mechanisms supported by your network platform, update allowlists under change control, and test when endpoints change.

Do not rely solely on a DNS allowlist if jobs can connect directly to raw IPs or query alternate resolvers. Policies must be enforced and observed at the network enforcement point.

### 4.3. Ingress Filtering

Runners generally do not need to accept arbitrary inbound connections from the Internet. If administrative access is needed for troubleshooting, use controlled management channels with individual identities, strong authentication, and audit logging.

Core principles:

- Never expose runner management ports to the public Internet.
- Restrict source networks allowed to reach internal services.
- Use bastions or organization-approved administrative access channels when needed.
- Prevent PR jobs from exposing test services on addresses reachable from unrelated networks.
- Close or tear down temporary endpoints immediately after the job completes.
- Avoid sharing ports or services across jobs of differing trust levels.

If a platform requires callbacks or special inbound connectivity, verify exact endpoints, sources, authentication, and port lifetimes. Never add a broad ingress rule to work around an uninvestigated connectivity failure.

### 4.4. Network Segmentation

Runners can be placed into distinct network segments:

- Build segment: reaches repositories and package registries.
- Integration segment: reaches required test services.
- Release segment: reaches artifact registries and release systems.
- Deployment segment: reaches target environment APIs or endpoints.

Not every organization needs four separate networks. However, runners with production privileges must have tightly bounded network paths and never share a segment with jobs running untrusted code.

### 4.5. Protecting Metadata Endpoints and Management Networks

Cloud-hosted jobs run close to VM metadata or workload identity endpoints. If arbitrary job code can query these endpoints, it may retrieve host-level identities or credentials. Restrict metadata endpoint access per platform guidance, enable only required token or workload identity mechanisms, and prevent untrusted jobs from assuming the host's identity.

Similarly, never allow runners unrestricted access to management planes, cluster control planes, internal configuration stores, or unrelated hosts simply because they share a private network. When a job needs an internal API, define the exact endpoint, identity, and allowed action in a dedicated rule. This limits impact if a dependency or build script probes unrelated internal services.

## 5. Isolating Runners and Jobs

Network restrictions are insufficient if jobs can read files or credentials left behind by earlier runs. Isolate processes, filesystems, containers, OS accounts, and runner lifecycles.

### 5.1. Ephemeral vs. Persistent Runners

| Model | Characteristics | Best suited for |
|---|---|---|
| Ephemeral runner | Provisioned for a single job or run, then destroyed | Untrusted code, sensitive jobs, minimizing leftover state |
| Persistent runner | Reused across multiple jobs over time | Steady workloads, specialized hardware, large local caches |
| Autoscaled runner | Scaled up/down based on queue and demand | Variable loads balancing cost and wait time |
| Containerized job | Job runs inside a container on a host or cluster | Consistent environments and process-level isolation |
| VM-per-job | Each job receives a dedicated VM | Stronger isolation boundary or dedicated kernel needs |

Ephemeral runners reduce the risk of credentials, files, and processes from one job affecting the next. However, teardown must include volumes, disks, local caches, network attachments, and issued credentials. Terminating only the agent process does not guarantee leftover data is gone.

Persistent runners save startup time and preserve local caches, but demand strict cleanup, patching, state verification, and permission isolation.

### 5.2. Containers Do Not Fully Replace VM Boundaries

Containers package runtimes and dependencies while isolating filesystems, processes, and network namespaces as configured. However, containers typically share the host kernel. Granting elevated privileges, mounting the Docker socket, or mounting sensitive host directories can severely weaken isolation.

VMs carry separate kernels and provide stronger boundaries, though they still require proper networking, permissions, images, and credential scoping. Choose based on code trust level, performance targets, and infrastructure model.

### 5.3. Caution with Docker Sockets and Privileged Containers

Granting a job access to the host Docker daemon can let the job spawn privileged containers, mount the host filesystem, or control host resources. Likewise, `privileged` containers drastically reduce isolation.

When container image builds are needed, pick a build mechanism aligned with your platform's security model. If host Docker daemon access is unavoidable, isolate the runner, restrict eligible job sources, constrain socket access, and tighten machine lifecycle. Never grant this access to pipelines processing untrusted PRs.

### 5.4. Post-Job Cleanup

After each job or run, handle:

- Workspaces and temporary files.
- Temporary credentials and tokens.
- Temporary containers, images, and networks.
- Background processes or test services.
- Volumes and test data.
- Caches that might hold sensitive data.
- Logs or temporary artifacts per retention policy.

With ephemeral runners, destroy the entire VM or pod after the job. With persistent runners, verify cleanup succeeded and quarantine or drain the host if cleanup fails.

## 6. Managing Secrets and Identities in Execution Environments

Runners are typically where secrets enter a job, so provisioning, usage, and revocation must be tightly governed.

### 6.1. Never Store Static Secrets on Runners

Avoid baking tokens, private keys, passwords, or secret config files into runner images, shared workspaces, or host-wide environment variables. Fetch secrets from a secret manager on demand and grant them only to authorized jobs.

A secure pattern works as follows:

1. The job authenticates using a platform-issued identity token.
2. The identity provider verifies repository, ref, environment, and workflow.
3. The secret manager issues narrowly scoped credentials.
4. The job uses the credentials for a short window.
5. Credentials expire or are revoked afterward.
6. Logs and audit records capture the identity used, never the secret value.

### 6.2. Environment-Scoped Secrets

Separate secrets across development, test, staging, and production. Test jobs do not need production secrets. Staging deploy jobs do not need production registry write access unless explicitly required.

Every secret needs an owner, rotation policy, expiration, and revocation playbook upon suspected exposure. Log masking is a secondary safety net; it never replaces blocking untrusted jobs from accessing secrets in the first place.

### 6.3. Preventing Leftover Credentials

On persistent runners, pay special attention to credentials cached in:

- Git credential helpers.
- Cloud CLI config files.
- System-wide environment variables.
- Docker config files.
- Package manager configs.
- SSH agents or private key files.
- Build caches and workspace directories.

Use a dedicated runner OS account, isolated per-job `HOME` directories where appropriate, and cleanup after every run. If credential removal cannot be verified, rebuild the runner or remove it from the pool before accepting the next job.

## 7. Accessing Dependencies, Artifacts, and Internal Services

Runner networks typically reach several systems. Each connection must have an explicit purpose, identity, and permission scope.

### 7.1. Dependency Registries

When fetching dependencies from the Internet, jobs risk pulling substituted packages, untrusted sources, or unexpected versions. You should:

- Use lockfiles or explicit version declarations.
- Prefer managed internal registries or caching proxies where appropriate.
- Verify checksums or signatures when supported by the ecosystem.
- Restrict allowed package sources.
- Record resolved dependencies and toolchains in build metadata.
- Never grant publish rights to jobs that only read packages.

### 7.2. Artifact Registries

Artifact publishing jobs need write access scoped to the target repository or namespace. Deployment jobs need only read access to approved artifacts. Separating these permissions prevents a test job from overwriting release artifacts.

Use immutable artifacts or digests to identify exact contents. Human-readable tags aid discovery but can be mutated unless locked by the registry. During deployment, verify that the downloaded artifact digest matches the verified build digest.

### 7.3. Test Services and Data

Integration runners may need databases, message brokers, stub APIs, or test services. Place these in dedicated network segments with separate credentials. Give each job an isolated namespace or dataset to prevent collisions.

Never use real production data simply for testing convenience. If production-like data is required, create sanitized copies governed by data policies and restrict which users and jobs may access them.

## 8. Reference Architecture for Runner Pools

The diagram below illustrates segregating runners by trust level and network destination:

~~~mermaid
flowchart TB
    CP["CI/CD control plane"]
    DP["Git / dependency proxy"]
    subgraph U["Untrusted code zone"]
      U1["Ephemeral runner for PRs/forks"]
    end
    subgraph B["Build and test zone"]
      B1["Build runner"]
      B2["Integration runner"]
      T["Test services / mock data"]
    end
    subgraph R["Release zone"]
      R1["Release runner"]
      AR["Artifact registry"]
    end
    subgraph D["Deployment zone"]
      D1["Deploy runner"]
      S["Staging"]
      P["Production"]
    end
    U1 -->|"Agent opens bidirectional outbound channel"| CP
    B1 -->|"Agent opens bidirectional outbound channel"| CP
    B2 -->|"Agent opens bidirectional outbound channel"| CP
    R1 -->|"Agent opens bidirectional outbound channel"| CP
    D1 -->|"Agent opens bidirectional outbound channel"| CP
    U1 -->|"Read-only"| DP
    B1 --> DP
    B2 --> DP
    B1 --> AR
    B2 --> T
    B2 --> AR
    R1 --> AR
    D1 --> AR
    D1 --> S
    D1 --> P
~~~

Real deployments may merge or split zones based on scale. Regardless, runners executing untrusted code must never have paths to production secrets or management networks. Release and deployment runners require dedicated identities, audit trails, and access strictly limited to approved artifacts and target environments.

## 9. Conceptual Policy Example for Permissions and Networking

The following example illustrates how to model policies conceptually. It is not literal syntax for any specific CI/CD, firewall, or cloud platform:

~~~yaml
runner_pools:
  untrusted_pr:
    lifecycle: ephemeral
    job_identity: read_only
    secrets:
      production: denied
      test: denied
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - git_read_endpoint
        - dependency_proxy

  integration:
    lifecycle: ephemeral
    job_identity: integration_test
    secrets:
      test_environment: scoped
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - git_read_endpoint
        - dependency_proxy
        - test_services

  release:
    lifecycle: isolated
    job_identity: release_publisher
    secrets:
      registry_write: short_lived
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - artifact_registry
        - identity_provider

  deployment:
    lifecycle: isolated
    job_identity: staging_deployer
    secrets:
      staging_deploy: short_lived
      production_deploy: approval_required
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - artifact_registry
        - approved_deployment_api
~~~

When implementing, translate this policy into concrete runner scopes, IAM roles, firewall rules, security groups, network policies, and secret manager rules. Never rely solely on pool names; verify that actual jobs cannot access credentials or network routes beyond their granted scope.

## 10. Operating Self-Hosted Runners

Self-hosted runners give control over hardware, private networking, and environment configuration. In return, the organization owns host lifecycle, patching, monitoring, and incident response.

An operational lifecycle should include:

- **Controlled registration:** allow only approved hosts to register into runner pools.
- **Standardized images:** use versioned OS and toolchain images updated on a schedule.
- **Security patching:** patch the OS, CI agent, runtimes, container engine, and build tools.
- **Privilege bounds:** run the runner service under a dedicated account, not a daily admin account.
- **Pool segmentation:** separate runners by trust level, environment, and network requirements.
- **Monitoring:** watch for anomalous jobs, network traffic, CPU, memory, disk, and lingering processes.
- **Cleanup:** wipe workspaces, credentials, and temporary resources.
- **Revocation:** drain and decommission compromised, misconfigured, or unmanaged runners.
- **Periodic audits:** verify runner labels, permissions, network rules, and software versions remain accurate.

A runner that has executed untrusted code must be treated as potentially modified afterward. If persistent runners are used in that tier, rebuild or verify host integrity before assigning trusted jobs.

## 11. Monitoring and Recording Audit Evidence

Permission and network controls require evidence for investigations. Record:

| Evidence category | Fields to capture |
|---|---|
| Runner identity | Runner ID, pool, image/version, host or pod identity |
| Job | Pipeline run ID, job ID, repository, ref, and commit SHA |
| Permissions | Role, scope, and lifetime of issued credentials |
| Secrets | Secret reference or audit event, never the secret value |
| Network | Destination, protocol, port, timestamp, and allow/deny outcome |
| Resources | CPU, memory, disk, queue wait time, and execution duration |
| Isolation | Lifecycle, container/VM identity, and cleanup outcome |
| Artifacts | Name, digest, registry, and source commit |
| Deployment actions | Target environment, acting identity, and result |

Never log secret values, private keys, or sensitive payloads purely for debugging. Protect network logs under data governance policies and restrict access to authorized personnel.

Useful alerts include:

- A runner attempts to reach an endpoint outside its allowlist.
- A PR job requests out-of-policy permissions or secrets.
- A persistent runner accepts jobs from a mismatched trust level.
- Credentials persist after job completion.
- An unpatched runner or outdated agent version checks in.
- Cleanup fails or unexpected processes remain on a runner.
- A deployment uses a mismatched artifact digest.
- A job generates anomalous outbound network traffic.

## 12. Troubleshooting Permission and Network Failures

When a job cannot connect or access a resource, investigate systematically to avoid over-permissive fixes.

### Job Cannot Check Out the Repository

Check trigger event, ref, repository read permissions, checkout token, DNS, proxy, and Git endpoint. Distinguish authentication errors from network connectivity failures before altering firewalls.

### Job Cannot Download Dependencies

Check registry URL, lockfile, proxy, DNS, TLS certificates, package-read credentials, and egress rules. If using an internal mirror, confirm sync status and target namespace.

### Job Cannot Reach Test Services

Check network segment, routing, security groups, network policies, DNS, and service ports. Confirm the service passed readiness checks and the runner targets the right test environment.

### Deploy Job Cannot Reach Target Environment

Check IAM role, token, audience, credential TTL, API endpoint, and firewall rules. Verify the job is authorized for that environment and the artifact digest matches the approved release.

### Job Has Overly Broad Permissions

Inspect host identity, job role, workflow token, secret scopes, runner groups, and network routes. Revoke potentially exposed credentials, tighten scopes, and rebuild the runner if cleanliness cannot be confirmed.

### Runner Retains Data After Job Completion

Inspect workspaces, volumes, caches, containers, background processes, config files, and credential helpers. If cleanup is unreliable, drain the runner and rebuild the environment before dispatching new jobs.

Never fix connectivity errors by opening outbound traffic to all destinations or granting admin privileges to the job. Pinpoint the exact required endpoint and operation, then add a narrowly scoped rule and document why.

## 13. Sample Scenario: PR Verification and Release Deployment

Suppose a team uses self-hosted runners to build a web service, run integration tests, and deploy to staging and production.

1. A pull request from a fork enters the queue. It runs on an ephemeral runner in the untrusted code zone with only source read access and dependency proxy access. The runner receives no production secrets and has no route to management networks.
2. Fast checks pass. When integration tests are required, the pipeline launches an isolated runner or job in the test network, injects short-lived test credentials, and permits connectivity solely to the required test database and stub services.
3. After review and merge, the main branch pipeline builds the artifact. The build job holds write access strictly to the candidate artifact area.
4. The artifact is stored with its commit SHA and digest. The release job validates metadata, runs required checks, and publishes to a protected registry.
5. The staging deploy job receives a short-lived identity authorized for staging deployment. The runner reaches only the artifact registry and staging APIs.
6. Once staging smoke tests and release gates pass, the production job awaits policy-mandated approval. Upon approval, it receives short-lived production credentials and routes only to production deployment APIs.
7. After deployment, the pipeline verifies the running version and archives digests, logs, and outcomes. Ephemeral runners and temporary credentials are revoked or destroyed.

This structure establishes crisp boundaries: untrusted code only tests, integration jobs reach only test networks, publish jobs write only artifacts, and deploy jobs act only on authorized environments.

## 14. Practice Roadmap

You can practice on a sample repository with these steps:

1. **Inventory runners:** list runner hosts, pools, labels, operating systems, service accounts, lifecycles, and active jobs.
2. **Map permissions:** record repositories, registries, secrets, cloud roles, and environments reachable by each job group.
3. **Map networking:** catalog required outbound and inbound endpoints, protocols, ports, purposes, and owners.
4. **Separate trust levels:** create distinct runner pools or jobs for untrusted PRs, internal builds, integration tests, releases, and deployments.
5. **Restrict egress:** apply an allowlist or proxy to one runner group and verify checkouts, dependencies, and tests still work.
6. **Remove unnecessary ingress:** close unused ports and retain only authenticated, logged management channels.
7. **Replace static secrets:** migrate to a secret manager or short-lived workload identity where supported.
8. **Test cleanup:** run jobs that create temp files, containers, and temporary credentials; confirm they are deleted or the runner is destroyed afterward.
9. **Simulate unauthorized access:** in a safe environment, run a test job attempting to reach an unapproved endpoint; verify it is blocked and logged.
10. **Review and document:** compare permissions, network access, and evidence before and after, documenting approved exceptions and owners.

### Completion Criteria

Learners can consider the exercise complete when they can demonstrate:

- Explaining the distinct roles of the control plane, runner host, and job process.
- Grouping runners by source code trust level and job sensitivity.
- Distinguishing host permissions from job permissions.
- Provisioning identities and credentials under least privilege.
- Cataloging required network endpoints for each job category.
- Designing appropriate egress filtering, ingress filtering, and network segmentation.
- Explaining container isolation limits and when VMs or ephemeral runners are required.
- Protecting secrets, registries, and deployment environments per trust tier.
- Capturing audit evidence for permissions, network connections, and cleanup.
- Troubleshooting connectivity errors without over-expanding permissions or network access.

## Conclusion

Runners are where source code actually executes, making runner permissions and network reachability a core pillar of CI/CD architecture. Every runner needs an explicit identity, least-privilege permissions, sound isolation boundaries, and network paths restricted strictly to required services. Untrusted code must run with a minimal blast radius; publish and deployment jobs require dedicated identities, credentials, and network paths.

A reliable design combines runner pool segmentation, short-lived credentials, egress/ingress filtering, network segmentation, cleanup, monitoring, and traceability. When these controls work together, pipelines access precisely the resources needed to build, test, and release while containing the impact of any failed or abused job.
