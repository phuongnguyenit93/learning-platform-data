# Distinguishing Platform-Hosted Runners from Self-Hosted Runners

Every CI/CD pipeline needs an environment to execute build, test, scan, and deploy commands. That environment can be provided out of the box by the CI platform, or provisioned and operated by the organization itself. This choice directly affects job queue times, build stability, internal network reachability, cost, security, and operational effort.

A platform-provided execution machine is commonly called a **hosted runner** or **managed runner**. The platform provider is responsible for provisioning and maintaining the job execution infrastructure as a service. A **self-hosted runner** is an execution machine or environment managed by the organization and registered with the CI platform to receive jobs. It can be a virtual machine, physical server, cloud instance, container host, or an on-demand pod.

Neither runner type is universally better. Hosted runners fit teams that need to start quickly, use standard environments, and minimize machine administration. Self-hosted runners fit workloads requiring specialized hardware, private networks, custom setups, or deep control over the environment. Many organizations combine both so each job runs where its requirements and trust level are best matched.

## 1. What Is a Runner and Where Does It Fit in the Pipeline?

A runner is an execution environment that picks up a job from the CI system, prepares the workspace, executes the declared commands, and reports results back to the platform. A job typically passes through these steps:

1. The platform receives a Git event or a pipeline run request.
2. The scheduler locates a runner matching the operating system, CPU architecture, labels, and access permissions.
3. The runner accepts the job, checks out source code, and prepares tools.
4. Build, test, scan, or deploy steps execute.
5. Logs, status, and artifacts are uploaded or stored according to configuration.
6. The runner finishes the job, cleans up the workspace, or is decommissioned based on its operating model.

The general flow can be visualized as follows:

~~~text
Git event / Manual trigger
          |
          v
   CI scheduler
          |
          v
 Select matching runner
      /       \
     /         \
 Hosted      Self-hosted
 runner        runner
     \         /
      \       /
          v
   Checkout source
          |
          v
     Run job steps
          |
          v
  Logs / reports / artifacts
          |
          v
   CI result and status
~~~

The runner is where execution happens, while the pipeline definition describes what to do and under what conditions. A single pipeline can use different runners across jobs: checking code on a hosted runner, testing hardware on a self-hosted runner, and deploying to the target environment using a separately authorized runner.

### Distinguishing Runner Host, Container, and Target Environment

These three concepts are frequently confused:

- **Runner host:** the machine or environment where the agent/runner actually runs. It provides the kernel, CPU, RAM, filesystem, and network connectivity.
- **Job container:** the container created to run the job's commands. A container can package runtimes and dependencies, yet it still uses the host's kernel and resources.
- **Target environment:** the environment where the application will be deployed, such as staging or production. The runner may reside in a different network and reach the target via API, VPN, or an authorized deployment mechanism.

Using a container for a job does not automatically turn a self-hosted runner into a fully isolated environment. If the container has access to the Docker socket, mounts host directories, runs in privileged mode, or receives broad credentials, code running inside can still affect the host and other resources. Trust boundaries must be designed around actual permissions, not just technology labels.

## 2. Hosted Runners vs. Self-Hosted Runners

### Hosted Runners

A hosted runner is an execution resource supplied by the CI platform or infrastructure provider. When a job needs to run, the platform provisions an environment matching the selected runner type. Organizations typically select from a list of supported operating systems, architectures, or machine sizes.

Common examples:

- GitHub-hosted runners in GitHub Actions.
- Platform-provided shared runners (e.g., GitLab.com hosted runners) or instance runners configured by organization administrators.
- Cloud CI services providing managed build agents.
- Managed build workers from other CI platforms.

The provider is generally responsible for provisioning machines, maintaining base images, applying partial OS updates, and tearing down environments after jobs under a service model. Exact responsibility boundaries depend on the platform, runner type, service tier, and configuration.

### Self-Hosted Runners

Self-hosted runners are installed, registered, and operated by the organization. They can run on:

- Virtual machines in the cloud or an on-premises datacenter.
- Physical machines with specialized CPUs, GPUs, RAM, or attached devices.
- Machines inside an internal network needing access to private systems.
- Container hosts or Kubernetes clusters.
- Ephemeral machines automatically provisioned per job or per group of jobs.

The organization is responsible for machine lifecycle, OS, patching, runner agent, toolchains, networking, storage capacity, monitoring, and cleanup. The CI platform may still handle queuing and job dispatch, but it does not inherently maintain self-hosted infrastructure.

### Comparison Table

| Criterion | Hosted runner | Self-hosted runner |
|---|---|---|
| Machine provisioning | Provided by the platform as a service | Created and registered by the organization |
| OS maintenance | Primarily handled by the provider within service scope | Responsibility of the organization |
| Hardware customization | Choose from offered machine configurations | Tailored to needs and budget |
| Build tooling | Use pre-built images/tools or install during the job | Can be pre-installed with deeper control |
| Internal network | Often restricted; requires a supported connectivity solution | Can reside in a VPC/VNet or internal network |
| Scalability | Platform typically scales automatically within quota | Requires fixed capacity or autoscaling |
| Cost | Typically billed per minute, machine type, or quota | Compute, storage, network, operations, and admin time |
| Job isolation | Based on the platform's model and guarantees | Depends on the organization's architecture |
| Environment customization | Bounded by supported images and services | More flexible, with higher maintenance overhead |
| Operational effort | Lower | Higher |
| Best suited for | Standard jobs, code with appropriate trust level | Jobs needing custom resources, networking, or setup |

## 3. Advantages and Limitations of Hosted Runners

### Strengths

**Fast onboarding.** Teams can create workflows and run jobs without provisioning machines, installing agents, or designing runner scaling systems.

**Reduced maintenance overhead.** The provider handles much of the infrastructure layer such as machine provisioning and base image maintenance. Teams spend more time focusing on pipelines, tests, and product quality.

**Easy scaling under load.** When many PRs are opened simultaneously, the platform typically allocates multiple runners within service quotas and limits. Teams do not need to predict exact always-on capacity.

**Standardized environments.** Common images typically include Git, shells, runtimes, and developer tools out of the box. This is convenient for projects using Java, Node.js, Python, .NET, or mainstream toolchains.

**Better fit for lower-trust jobs.** With proper platform isolation settings, hosted runners can be a strong choice for running code from PRs or external contributor branches without bringing untrusted code onto internal hosts holding sensitive data.

### Limitations

**Mutable environments.** Aliases like `ubuntu-latest` track newer images according to the provider's schedule. Pre-installed toolchains, compiler versions, or system libraries can change over time. When high reproducibility is required, select explicit image versions where supported, pin tool versions in the pipeline, and record build metadata.

**Resource caps.** CPU, RAM, disk space, maximum job duration, and concurrency depend on runner tier and service plan. Large builds may hit out-of-memory errors or timeouts.

**Limited private network access.** Hosted runners generally sit outside the organization's internal network. Reaching private databases, registries, or internal systems requires secure connectivity supported by the platform. Never expose public endpoints solely for runner convenience.

**Limited hardware customization.** Requirements like specific GPUs, USB peripherals, uncommon CPU architectures, or internal operating systems may not be available in hosted catalogs.

**Quotas and queue wait times.** Minute quotas, concurrency caps, or platform queuing can slow execution during load spikes. Platforms may also enforce different policies across private repositories, public repositories, and subscription tiers.

## 4. Advantages and Responsibilities of Self-Hosted Runners

### Strengths

**Deep customization.** Organizations can choose CPUs, RAM, disks, GPUs, operating systems, devices, and exact toolchain versions as needed.

**Private network access.** Runners can be placed inside a VPC/VNet, private subnet, or datacenter to reach internal dependency repositories, test databases, registries, or internal services. Connectivity must follow least-privilege principles.

**Toolchain control.** Teams can build golden images, pre-install internal tools, or use software licensed strictly within the organization. This helps specialized jobs run more consistently when images are properly versioned and updated.

**Optimized for steady load or heavy jobs.** Teams can maintain appropriately sized hosts, local caches, or hardware acceleration. For large, consistent workloads, this model can be cost-effective even after factoring in operational overhead.

**Support for specialized requirements.** Examples include building iOS apps on macOS, testing physical hardware, compiling firmware, processing large datasets, or validating on dedicated hardware.

### Associated Responsibilities

The organization must manage the runner lifecycle and treat runners as code-executing infrastructure assets. Responsibilities include:

- Provisioning, registering, upgrading, and decommissioning runners.
- Patching operating systems, agents, runtimes, and tooling.
- Monitoring CPU, RAM, disk, network, queue depth, and agent health.
- Cleaning workspaces, temporary credentials, and job artifacts after completion.
- Managing access scopes across repositories, groups, projects, and environments.
- Restricting network egress and access to internal systems.
- Handling failed runners, disconnects, hung jobs, or suspected compromises.
- Planning capacity, autoscaling, and cost.
- Maintaining golden images, vulnerability scanning, and patch cycles.

A self-hosted runner is not automatically more secure just because it lives inside the organization's network. If a job executes untrusted code on a host with broad credentials or network access, the runner becomes a pivot path to internal resources. The higher the privilege, the stricter the trust boundaries and isolation mechanisms must be.

## 5. Security: A Runner Executes Arbitrary Code

Pipelines can execute commands introduced into a repository by contributors. Therefore, a runner must be evaluated by code origin, job permissions, and machine reachability.

### Common Threats

- A PR from a fork modifies a build script to read environment variables or exfiltrate data.
- A compromised job writes credentials into the workspace, cache, or logs.
- A subsequent job on the same machine reads leftover files from the previous job.
- Runner registration tokens or cloud credentials are leaked.
- A runner with broad internal network access creates a path to databases or management planes.
- A job with access to the Docker socket or running a privileged container compromises the host.
- Untrusted users dispatch jobs onto an internal runner with deployment privileges.
- An unpatched runner or misconfigured agent is exploited.

### Never Share Privileged Runners with Untrusted Code

A critical rule is never allowing untrusted PR jobs to share machines or credentials with production deployment jobs. Segment runners by trust level:

| Job group | Suitable runner | Recommended permissions |
|---|---|---|
| Public PR or fork checks | Hosted runner or single-use isolated runner | Read source code and run tests |
| Internal source builds | Hosted or dedicated self-hosted pool | Fetch dependencies and upload required artifacts |
| Artifact publishing | Dedicated release runner | Write access to specific registries/repositories |
| Staging deployment | Runner authorized to reach staging | Staging credentials and scoped deployment rights |
| Production deployment | Protected runner and environment | Minimal production privileges, approvals, and audit |

Do not expose production secrets to workflows processing forked or untrusted code. Restricting secrets in the CI UI alone is insufficient if the job can read credentials from host files, metadata services, system variables, or shared sockets.

### Prefer Ephemeral Runners for Untrusted Workloads

An ephemeral (single-use) runner is provisioned to handle a single job or bounded scope and then destroyed. This reduces the risk of state or malware persisting from one job to the next.

A typical lifecycle:

~~~text
Provision runner
      |
      v
Register with CI
      |
      v
Receive one job
      |
      v
Execute in isolated workspace
      |
      v
Upload required outputs
      |
      v
Remove runner and temporary storage
~~~

Ephemeral does not automatically mean complete isolation. If multiple jobs share the same underlying host, network, or volume, risks remain. Both the underlying infrastructure and resource reclamation must be tightly controlled.

### Scoping Runners and Credentials

- Allow only necessary repositories or projects to use a runner.
- Use runner groups or equivalent controls to restrict access scope.
- Place privileged runners in dedicated groups and require protected workflows.
- Use short-lived tokens or scoped temporary credentials whenever supported by the platform.
- Never store production credentials in base images or shared directories.
- Separate permissions for reading source, publishing artifacts, and deploying.
- Log who registered, modified, or used a runner.
- Immediately revoke runners or credentials upon signs of compromise.

## 6. Lifecycle Management and Environment Consistency

Hosted runners reduce machine administration, but tool versions still need control. Self-hosted runners add OS, agent, and image management.

### Standardizing the Toolchain

A build environment should explicitly declare:

- Operating system or base image version.
- JDK, Node.js, Python, .NET SDK, or compiler versions.
- Build tool versions such as Gradle or Maven.
- Dependencies and lock files.
- Required environment variables.
- Auxiliary tools and their versions.

For Java, you can use the Gradle Wrapper or Maven Wrapper and declare a Java toolchain. This keeps the pipeline from depending on an arbitrary Gradle or Maven version pre-installed on the runner.

### Using Versioned Images

For self-hosted runners, teams can build standard images containing required tooling. Images should be built from reviewed source definitions, vulnerability-scanned, tagged by version or digest, and updated on a schedule.

Do not let a self-hosted machine run for years with manually installed tools and no documentation. If that host needs replacement, reproducing the environment becomes difficult. Image-as-code or automated provisioning makes runner recovery straightforward.

### Cleaning Workspaces and Caches

A workspace may contain source code, temporary files, logs, credentials, or artifacts. After a job finishes, define clearly what is retained and what must be purged.

- Delete temporary files and credentials.
- Never store secrets inside caches.
- Partition caches by repository, branch, or trust level.
- Prevent untrusted jobs from writing to caches consumed by trusted release jobs.
- Control cache read and write permissions.
- Periodically prune storage and inspect stale caches.

Caching is a performance optimization, not a store for release artifacts. Artifacts must be stored with versions/digests and dedicated retention policies.

### Updates and Patching

Self-hosted runners require a patching cadence for the OS, agent, and tools. Updates should be tested before promoting a new image into the main pool. Teams can maintain a canary runner group to validate new versions before broad rollout.

Hosted runners also undergo image and toolchain updates from the provider. Track provider release notes, avoid relying on unpinned default versions, and pin explicit images when strict control is needed.

## 7. Scaling and Capacity Management

### Hosted Runners: Scaling as a Service

The platform typically allocates runners based on queued jobs, though constrained by concurrency, quotas, or machine sizes. Teams should monitor queue wait times, runtimes, and concurrent jobs to pick the right tier or configuration.

If pipelines repeatedly wait for runners, you can:

- Eliminate redundant jobs.
- Split long jobs into independent parallel stages where beneficial.
- Optimize caching and dependency downloads.
- Select a runner size suited to the workload.
- Adjust schedules or concurrency within platform policies.

### Self-Hosted Runners: Pools and Autoscaling

A runner pool is a group of machines with similar configurations and permissions designated for a class of jobs—for example, `linux-general`, `windows-build`, `macos-signing`, and `deploy-staging`.

Teams can start with a small baseline of static machines and autoscale based on queue depth or pending jobs. An autoscaler can provision VMs or pods during spikes and reclaim them when demand drops.

Common patterns include:

- **Static machines:** simple and suited for steady loads, but wasteful during idle periods.
- **Ephemeral VMs:** provisioned on demand and deleted after each job. Suited for workloads needing VM-level isolation.
- **Containers or Kubernetes pods:** fast environment startup and easy cluster scaling; requires safeguarding the host and container permissions.
- **Runner scale sets:** automated runner orchestration driven by platform APIs or dedicated controllers.

GitHub Actions Runner Controller (ARC) is one option for running and scaling self-hosted runners on Kubernetes. GitLab Runner also supports multiple executors, including Shell, Docker, and Kubernetes. When picking an executor, understand the boundaries across job, container, pod, VM, and host.

### Measuring Capacity by Workload

Do not just count the number of runners. Evaluate:

- Queued job count and wait time.
- Execution duration by job type.
- CPU, RAM, disk I/O, and network utilization.
- Safe concurrent job count per host.
- Percentage of unavailable or disconnected runners.
- Autoscaling frequency and provisioning latency.
- Job failure rate due to resource exhaustion.
- Cost per successful pipeline.

A powerful runner can handle several lightweight jobs concurrently, whereas heavy builds or exclusive-device tests may require single-tenant runs. Capacity planning must reflect actual workload profiles.

## 8. Configuring Runners in Pipelines

### GitHub Actions Example: Hosted Runner

A workflow selects a GitHub-provided runner via the `runs-on` field:

~~~yaml
name: build-on-hosted-runner

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon check
~~~

Here, `ubuntu-24.04` selects a more specific Ubuntu image than the `ubuntu-latest` alias. Action and toolchain versions still need to follow project policy. When strict reproducibility is needed, pin actions by commit SHA and control dependencies.

### GitHub Actions Example: Self-Hosted Runner

Self-hosted runners are targeted via labels:

~~~yaml
name: build-on-self-hosted-runner

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: [self-hosted, linux, x64, ci-general]
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew --no-daemon check
~~~

The labels in `runs-on` must match the labels registered on the runner. This example requires a runner labeled `self-hosted`, `linux`, `x64`, and `ci-general`. If no runner satisfies all labels or all matching runners are busy, the job queues.

Do not attach overly broad labels to runners with elevated privileges. A label like `production-deploy` should belong only to runners and repositories authorized to deploy to production.

### GitLab CI/CD Example

GitLab Runners are selected using `tags`. A runner must have all tags requested by the job:

~~~yaml
stages:
  - verify

verify:
  stage: verify
  tags:
    - linux-docker
    - ci-general
  script:
    - ./gradlew --no-daemon check
~~~

GitLab can use shared/instance runners or organization-managed runners registered at the project, group, or instance level. Which runner a job can claim depends on project enablement, tags, protected status, and access settings.

The executor determines how the job runs. The Shell executor runs directly on the runner host with broader environment sharing. The Docker executor runs jobs inside containers but still depends on the Docker host and mount/network configuration. The Kubernetes executor spawns pods for jobs and requires controlling service accounts, namespaces, network policies, and cluster permissions.

### Jenkins Agent

In Jenkins, an agent is the machine that executes jobs orchestrated by the controller. An agent can be a static host, VM, container, or Kubernetes pod. Labels select the appropriate agent, such as `linux-build`, `windows-signing`, or `macos-test`.

Avoid running builds on the controller itself. Separating the controller from agents limits load, privileges, and blast radius. On long-lived shared agents, clean workspaces and credentials after each job; for untrusted or high-privilege jobs, ephemeral agents are generally safer.

## 9. Choosing Runners by Code Trust Level

Job origin matters more than how simple a job looks. A test command can execute a script modified by a PR; a build job can run a Gradle plugin or npm package containing arbitrary code.

A simple decision matrix:

| Job origin | Hosted runner | Self-hosted runner |
|---|---|---|
| PR from public fork | Usually preferred if no secrets are exposed | Use only if ephemeral, isolated, and without internal access |
| PR from internal contributor | Suitable for routine checks | Can use a dedicated pool with restricted permissions |
| Build on protected main branch | Suitable or use internal pool | Can use standardized runners for higher performance |
| Release build | Viable if artifact and credential policies are met | Can use dedicated release runners |
| Staging deployment | Viable if secure connectivity to staging exists | Often preferred when staging sits in a private network |
| Production deployment | Only if platform and permission model meet policy | Can use dedicated, protected runners with approvals |
| Job needing GPU/special hardware | Only if provider offers the exact hardware | Usually requires self-hosted |
| Job needing internally licensed software | May be constrained by licensing/networking | Fits organization-managed hosts and licenses |

This is directional guidance. Final choices depend on your threat model, data policies, connectivity, budget, and provider guarantees.

### Separating Runners by Trust Zone

An organization can design multiple trust zones:

- **Untrusted zone:** jobs from forks or unreviewed code; no internal secrets and no private network access.
- **Build zone:** jobs on protected branches; permitted to fetch dependencies and produce artifacts.
- **Release zone:** jobs publishing artifacts; accepts only verified inputs and holds limited registry write access.
- **Deployment zone:** deployment jobs; reaches only the target environment using dedicated credentials.
- **Production zone:** sensitive deployment steps requiring protected runners, approvals, and audit trails.

These zones may use hosted runners, self-hosted runners, or both. Crucially, a job must not be able to escalate privileges merely by modifying YAML inside a PR.

## 10. Hybrid Model: Combining Hosted and Self-Hosted

A hybrid model uses hosted runners for standard tasks and self-hosted runners for jobs with specialized requirements.

Example:

~~~text
Pull Request
     |
     v
Hosted runner
  - lint
  - unit test
  - static analysis
     |
     v
Protected main branch
     |
     v
Hosted build runner
  - compile
  - package
  - create artifact
     |
     v
Artifact registry
     |
     v
Self-hosted staging runner
  - deploy staging
  - smoke test
     |
     v
Approval / release gate
     |
     v
Protected production runner
  - deploy production
  - verify runtime
~~~

Benefits of the hybrid model:

- Reduces the number of internal machines to maintain.
- Keeps untrusted jobs out of private networks.
- Routes jobs needing special hardware or privileges to appropriate runners.
- Separates routine verification jobs from deployment jobs.
- Scales hosted runners elastically while reserving self-hosted runners for specialized workloads.

Artifacts must be transferred through an identified repository with proper access controls. Never rely on a shared machine workspace to pass outputs between hosted and self-hosted runners. Artifacts should be bound to a commit, version, or digest so downstream jobs can verify their inputs.

## 11. Cost: Looking at the Full Lifecycle

Hosted runners usually have transparent pricing: runtime minutes, machine tiers, concurrency, or plan quotas. Self-hosted runners may not incur platform per-minute fees, yet still carry infrastructure and operational costs.

### Hosted Cost Components

- Runner minutes or usage duration.
- Price multipliers by CPU, RAM, or operating system.
- Storage fees for artifacts, caches, and logs where applicable.
- Overage or concurrency upgrade fees per plan.
- Opportunity cost of queue delays if tier upgrades are needed.

### Self-Hosted Cost Components

- VMs, physical servers, GPUs, disks, and networking.
- Cluster or Kubernetes management costs if used.
- Engineering time for operations, patching, and incident response.
- Monitoring, logging, backups, and security tooling.
- Buffer capacity for peak demand.
- Idle machine costs during off-peak periods.
- Effort to build and maintain autoscalers and golden images.

Never compare solely on per-minute pricing. Self-hosted runners can be cheaper under heavy, steady workloads, but operational overhead, idle capacity, and incidents can push total cost higher. Hosted runners can save significant effort for sporadic workloads despite higher direct per-minute rates.

### Estimation Formula

A directional formula can help frame comparisons:

~~~text
Total hosted cost
  = total runner minutes by tier
  + related storage and service fees

Total self-hosted cost
  = compute and network infrastructure
  + peak buffer capacity
  + storage and observability
  + operational engineering cost
  + incident and maintenance overhead
~~~

Measure cost per successful pipeline or per release rather than cost per job. A cheap runner that fails frequently or triggers retries can increase overall spend.

## 12. Troubleshooting Runners

When a job fails to start or fails mid-run, classify the issue before editing the pipeline.

| Symptom | Possible cause | What to check |
|---|---|---|
| Job stays queued for a long time | No matching runner, quota exhausted, or runners busy | Check labels/tags, concurrency, quotas, and agent status |
| Job cannot find a tool | Tool missing from image or PATH | Check runner image, toolchain version, and setup steps |
| Build fails only on self-hosted | Stale host state or configuration drift | Check workspace, caches, environment variables, and OS version |
| Job cannot reach a service | Network policy, DNS, firewall, or credentials | Check network path, endpoint, permissions, and secrets |
| Long job runs out of disk space | Accumulated workspaces, caches, or artifacts | Check disk capacity, retention, and cleanup jobs |
| Next job sees previous job's data | Shared workspace or uncleaned volume | Isolate runners, purge state, or switch to ephemeral |
| Runner disconnects | Agent, network, or host failure | Inspect agent logs, host health, and provisioning system |
| Job denied permission | Runner group, protected branch, or permission settings | Review registration scope and protection policies |
| PR job can read secrets | Unsafe trigger or runner permission configuration | Audit trust zones, trigger events, and credential injection |

If a runner shows signs of compromise, stop dispatching jobs to it, revoke associated credentials, isolate the machine, and inspect logs. For ephemeral runners, decommission the host after collecting necessary forensic evidence. Never return a compromised runner to the pool merely by restarting the agent without identifying the root cause.

## 13. Runner Selection and Operations Checklist

### Before Choosing a Runner Type

- [ ] Identified required OS, architecture, and compute resources.
- [ ] Determined whether the job needs internal network access.
- [ ] Evaluated code origin and job trust level.
- [ ] Identified required secrets and permissions.
- [ ] Checked hosted runner quotas, concurrency, and timeout limits.
- [ ] Factored in operational overhead if considering self-hosted.
- [ ] Reviewed specialized hardware or licensed software requirements.

### When Operating Self-Hosted Runners

- [ ] Runners are registered at the appropriate repository/group/project scope.
- [ ] Runner labels accurately reflect OS, architecture, and purpose.
- [ ] OS, agent, and toolchains follow a regular patching schedule.
- [ ] Jobs execute under a least-privilege OS account.
- [ ] Network egress and internal access are restricted.
- [ ] Workspaces, caches, and credentials are cleaned or isolated between jobs.
- [ ] Runners have monitoring for health, disk, CPU, RAM, and queue depth.
- [ ] Procedures exist to revoke runners and credentials during incidents.
- [ ] Untrusted jobs do not share privileged runners.
- [ ] Autoscaling or capacity plans cover peak demand.

### When Using Hosted Runners

- [ ] Appropriate runner image or version selected.
- [ ] Critical toolchains are version-pinned.
- [ ] Pipelines do not implicitly depend on unmanaged pre-installed tools.
- [ ] Pipelines do not assume private network access from hosted runners.
- [ ] Secrets are provisioned only to authorized jobs at appropriate trust levels.
- [ ] Quotas, queue times, and costs are monitored.
- [ ] Artifacts are stored separately with identifiers for traceability.

## Conclusion

Hosted runners help teams get started quickly, reduce administration overhead, and scale elastically as a service. Self-hosted runners provide control over hardware, toolchains, and networking, at the cost of ongoing maintenance, security, and capacity management responsibilities. Choose runners based on each job's requirements, source trust level, and required permissions. When both flexibility and control are needed, a hybrid model combining hosted runners with dedicated self-hosted pools often serves better than a single choice across the entire pipeline.
