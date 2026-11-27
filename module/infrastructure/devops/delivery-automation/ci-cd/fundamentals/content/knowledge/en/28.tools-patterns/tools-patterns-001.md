# Placing GitHub Actions, GitLab CI, and Jenkins into the Same Conceptual Model

GitHub Actions, GitLab CI, and Jenkins all help automate the process from source code changes to building, testing, publishing artifacts, and deploying. However, each tool uses different terminology, pipeline structures, execution mechanisms, and governance models. If you only learn YAML syntax or Jenkinsfile in isolation, it is easy to mistake a similarly named feature for having identical semantics, or find it difficult to migrate a pipeline from one platform to another.

A more durable way to learn is to place all three into a single model: **source event → orchestrator → pipeline definition → job graph → execution worker → artifacts and evidence → promotion/deployment**. Once you understand what each component is responsible for, you can then map it to GitHub Actions, GitLab CI, and Jenkins.

All three can execute the same CI/CD flow, but there is no perfect one-to-one mapping. GitHub Actions organizes workflows, jobs, and steps; GitLab CI organizes pipelines, stages, and jobs; Jenkins uses controllers, agents, pipelines, stages, and steps. Differences in schedulers, runner lifetimes, permissions, caches, artifacts, approvals, and plugins can directly affect correctness, security, and operational cost.

## 1. A Common Model for Every CI/CD Platform

A pipeline can be broken down into seven layers:

1. **Source and event:** what change triggers the process, such as a push, pull request/merge request, tag, schedule, or manual action.
2. **Control plane/orchestrator:** the system that receives the event, reads the pipeline definition, creates a run, and manages state.
3. **Pipeline graph:** the jobs/tasks, execution conditions, dependencies, parallelism, and ordering.
4. **Execution worker:** the runner or agent that executes commands on a provisioned machine, container, or environment.
5. **Inputs and credentials:** source checkout, dependencies, variables, secrets, identity, and access permissions.
6. **Outputs and side effects:** logs, test reports, artifacts, caches, package publishing, deployments, and notifications.
7. **Evidence and governance:** check statuses, approvals, audit trails, provenance, monitoring, and release records.

~~~mermaid
flowchart TD
    A[Git event or manual trigger] --> B[Control plane / Orchestrator]
    B --> C[Read pipeline definition and revision]
    C --> D[Schedule pipeline graph]
    D --> E[Runner / Agent executes jobs]
    E --> F[Build, test, and quality checks]
    F --> G[Artifacts, reports, and cache]
    G --> H[Publish / Promote / Deploy]
    H --> I[Post-deployment verification]
    I --> J[Evidence, audit, and release record]
~~~

This model helps you ask the right questions when designing a pipeline:

- Where does the event come from, and which actors can trigger it?
- From which commit/ref is the pipeline definition loaded?
- Which tasks can run in parallel?
- Is the worker isolated and granted least-privilege permissions?
- Which outputs are artifacts to retain, and which outputs are just cache?
- To which jobs are secrets granted, and under which identity?
- Who can approve production?
- How do you know the artifact being deployed is the exact artifact that was tested?

## 2. Terminology Across the Three Platforms

| Common Concept | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Pipeline definition | Workflow YAML | Pipeline YAML | Jenkinsfile |
| Trigger event | Event and workflow trigger | Pipeline source, workflow/rules, and trigger | SCM webhook, polling, timer, or trigger plugin |
| Run instance | Workflow run | Pipeline | Job or Pipeline build/run |
| Primary scheduling unit | Job | Job | Pipeline stage/branch and steps executed on an agent |
| Logical grouping | Workflow/job/step | Pipeline/stage/job/script | Pipeline/stage/step |
| Worker | Runner | GitLab Runner | Agent/node |
| Orchestration | GitHub Actions service | GitLab instance | Jenkins controller |
| Reuse | Reusable workflow, composite action, action | include, component, extends, child pipeline | Shared Library, plugin, and function |
| Artifact | Workflow artifact, package/container registry | Job artifact, package/container registry | Archived artifact or artifact manager/plugin |
| Cache | Actions cache | GitLab cache | Typically via plugin, workspace, or external remote cache |
| Approval/deploy gate | Environment protection, reviewers, and workflow logic | Manual job, protected environment, and deployment approvals depending on configuration | input step, RBAC, and plugin |
| Secret/identity | Secrets, GITHUB_TOKEN, OIDC | CI/CD variables, job token, ID token/OIDC | Credentials store, binding plugin, and identity integration |

This table is a conceptual map, not a claim that the features are completely equivalent. For example, a GitHub Actions step can invoke a packaged action or run a shell command; a GitLab CI job typically contains a multi-command script; a Jenkins step is a command within the Pipeline DSL. When migrating, compare semantics rather than just swapping field names.

## 3. Source Events and Triggers

A pipeline starts when an event occurs or someone requests a run. The event determines the pipeline context: commit, branch/ref, actor, change type, and the permissions that can be granted.

### 3.1. GitHub Actions

Workflows reside in the `.github/workflows` directory. The `on` block declares events such as `push`, `pull_request`, `workflow_dispatch`, or `schedule`.

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Verify
        run: ./gradlew check
~~~

Pay close attention to event and actor context. A workflow running on a pull request may have different permissions than one running after merge. For pull requests from forks, secrets and token permissions are typically restricted by platform policy. Never assume every event has the same permissions or the same source revision.

### 3.2. GitLab CI

GitLab uses the pipeline source and conditions such as workflow rules, job rules, branch/tag, merge request events, schedules, web, or trigger tokens. Jobs can be excluded from a pipeline using rules.

~~~yaml
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
    - when: never

verify:
  stage: test
  image: gradle:8.10-jdk21
  script:
    - ./gradlew --no-daemon check
~~~

Understand the difference between workflow rules, which decide whether a pipeline is created, and job rules, which decide which jobs appear in the pipeline. A rules configuration with missing cases can prevent a pipeline from running, or create both a branch pipeline and a merge request pipeline for the same change.

### 3.3. Jenkins

Jenkins can receive webhooks from SCM, poll repositories, run on a timer, or use plugin-provided triggers. Pipeline as Code declares triggers in the Jenkinsfile or in the job/multibranch project configuration.

~~~groovy
pipeline {
    agent any

    triggers {
        pollSCM('H/5 * * * *')
    }

    stages {
        stage('Verify') {
            steps {
                sh './gradlew --no-daemon check'
            }
        }
    }
}
~~~

This example uses polling to illustrate a trigger; webhooks generally reduce latency and polling load when SCM and Jenkins are properly configured. Multibranch Pipeline can discover branches and pull requests via SCM integration/plugins. Actual trigger behavior depends on plugins and controller configuration.

### 3.4. Common Questions When Designing Triggers

- Does the pipeline run for push, PR/MR, tag, schedule, or manual action?
- Does it run two pipelines for the same change?
- Can pipelines from forks access secrets or sensitive caches?
- Which pipelines have permissions to publish and deploy?
- Are there conditions to skip documentation or unrelated changes?
- Are release tags protected and is their creation source verified?

## 4. Pipeline Definition and Version Control

All three platforms support managing pipeline definitions as code, but how they are stored and applied differs.

- GitHub Actions: each workflow is a YAML file in `.github/workflows`; it can call reusable workflows or actions.
- GitLab CI: a pipeline typically starts from `.gitlab-ci.yml` and can include other files, components, or child pipelines.
- Jenkins: the Jenkinsfile usually lives in the repository; Shared Libraries provide shared logic. Some job and plugin configurations still live on the controller and need to be managed separately.

Pipeline as Code brings diffs, reviews, history, and rollback capability. However, not all CI/CD behavior lives inside the pipeline file. Repository settings, branch protection, runner groups, Jenkins plugins, credential bindings, service connections, environment approvals, and organization permissions may reside outside the source repository.

Therefore, to reproduce a pipeline, you must version-control the pipeline file and also manage the control plane configurations that affect permissions and execution behavior.

### 4.1. Review Pipelines Like Application Code

Sensitive changes require appropriate review:

- Adding write/admin permissions or deployment permissions.
- Changing runner/agent pools or network boundaries.
- Changing actions, includes, plugins, or Shared Libraries.
- Changing secret references or credential bindings.
- Removing required checks, approvals, or protected environments.
- Changing triggers in ways that grant higher privileges to code from untrusted branches/forks.
- Changing registries, artifact retention, or deployment targets.

## 5. Pipeline Graph: Jobs, Stages, Steps, and Dependencies

A pipeline is typically a directed acyclic graph (DAG) or a sequence of conditional stages. Independent jobs can run in parallel; dependent jobs start only when their dependency conditions are satisfied.

### 5.1. GitHub Actions: workflow → jobs → steps

- A workflow is the definition file and the unit that gets triggered.
- A job is the scheduler unit assigned to a runner.
- Jobs can generally run in parallel if no dependencies are declared.
- `needs` creates dependencies between jobs.
- Steps within the same job run sequentially on the same job runner/workspace.
- A step can run a shell command or use an action.

~~~yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew assemble

  test:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./gradlew test

  package:
    needs: [build, test]
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/package.sh
~~~

Each job has its own runner/workspace according to the platform's execution model. If you need to pass files between jobs, use artifacts or a registry instead of assuming a shared workspace.

### 5.2. GitLab CI: pipeline → stages → jobs

- A pipeline contains jobs.
- Stages group jobs into logical phases.
- Jobs in the same stage can run in parallel depending on runner capacity and dependencies.
- By default, stages execute in the order declared.
- `needs` can create a DAG so a job starts as soon as its direct dependencies finish without waiting for the entire previous stage.
- `script` contains the commands executed within the job.

~~~yaml
stages:
  - build
  - test
  - package

build:
  stage: build
  script:
    - ./gradlew assemble

unit_test:
  stage: test
  script:
    - ./gradlew test

package:
  stage: package
  needs:
    - build
    - unit_test
  script:
    - ./scripts/package.sh
~~~

A GitLab job can declare `artifacts` to pass files to downstream jobs and `cache` to reuse data. These two concepts have different semantics; do not use cache as a substitute for artifacts that must be transferred reliably between steps.

### 5.3. Jenkins: Pipeline → stages → steps

Jenkins Declarative Pipeline has `pipeline`, `agent`, `stages`, `stage`, and `steps`. A stage can contain sequential steps, `parallel`, or `matrix` depending on the structure. `agent` determines where steps run.

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew assemble'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew test'
            }
        }

        stage('Package') {
            steps {
                sh './scripts/package.sh'
            }
        }
    }
}
~~~

Jenkins does not have an identical job/step structure to GitHub Actions. A Jenkins Pipeline can be thought of as a single multi-stage/multi-step run; the Jenkins controller manages the run and agents execute the work. Freestyle jobs, Pipeline jobs, Multibranch Pipelines, and plugins can alter the specific model.

### 5.4. Imperfect One-to-One Mapping

| Goal | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| Run a group of commands | Step with run | Job script | Pipeline step inside a stage |
| Run independent tasks in parallel | Jobs without `needs` dependencies | Jobs in a stage or DAG with `needs` | Parallel branches/stages |
| Wait for other tasks | `needs` | Stage order or `needs` | Stage order, parallel/join, or Pipeline logic |
| Skip condition | `if` | `rules`, legacy `only`/`except` | `when`, expression, or scripted logic |
| Version/OS matrix | `strategy.matrix` | `parallel:matrix` | `matrix` directive or appropriate plugin/logic |
| Modularize flow | Reusable workflow/action | `include`/component/child pipeline | Shared Library, downstream job |

When migrating, translate the dependency graph and conditions first, then translate the syntax. If you only convert each stage into a job while ignoring dependencies or artifact handoffs, the new pipeline may run out of order or lose files.

## 6. Workers: Runners, GitLab Runner, and Jenkins Agents

The control plane decides what work to run; the worker executes the commands. Separating these two roles helps clarify isolation, capacity, and permissions.

### 6.1. GitHub Actions Runner

GitHub-hosted runners are provided by the platform and assigned to a job. Self-hosted runners are managed by the organization and can be persistent or provisioned ephemerally. Self-hosted runners can access internal networks and sensitive resources, so you must restrict which repositories/workflows can use them, control registration, and clean up workspaces.

### 6.2. GitLab Runner

GitLab Runner picks up jobs from GitLab and executes them using an executor such as Shell, Docker, Kubernetes, or other supported executors. Runners can be registered at the instance, group, or project scope depending on configuration. Tags help jobs select an appropriate runner, but tags do not inherently create a security boundary; you must control who is allowed to run jobs on that runner.

### 6.3. Jenkins Agent

The Jenkins controller schedules and orchestrates; agents/nodes run build steps. Agents can be static machines, containers, or pods dynamically provisioned via plugins/cloud integrations. Heavy build workloads should not run on the controller. You need to manage node labels, executor counts, workspace cleanup, plugins, and the permissions agents have when connecting to the controller.

### 6.4. What to Compare

| Attribute | GitHub Actions runner | GitLab Runner | Jenkins agent |
|---|---|---|---|
| Orchestration | Actions service | GitLab instance | Jenkins controller |
| Managed workers | GitHub-hosted runners | Depends on GitLab service/runner deployment | Not a single default hosted model; depends on infrastructure |
| Self-managed workers | Self-hosted runner | Self-managed runner | Agent/node |
| Worker selection | `runs-on` and labels | `tags`, runner scope, and executor | Agent label, node selection |
| Isolation | Depends on hosted/self-hosted and job setup | Depends on executor and runner config | Depends on agent, container/VM, and plugins |
| Workspace hygiene | Depends on runner type | Depends on executor/config | Requires managing workspace cleanup |

Do not treat different runner names as the core difference. Evaluate where code runs, what the worker can access, whether other jobs can read the workspace/cache, and who can register or select a worker.

## 7. Artifacts, Cache, and Data Passed Between Jobs

A pipeline typically produces several kinds of data. You must distinguish between them:

- **Artifact:** an output that must be retained or passed downstream, such as a JAR, container image, package, test report, or SBOM.
- **Cache:** reproducible data used to reduce execution time, such as downloaded dependencies or build caches.
- **Workspace:** the working directory of a job/agent; not shared between workers by default.
- **Release record:** metadata linking source, artifact digest, approvals, environment, and deployment.

### 7.1. GitHub Actions

Artifacts can be uploaded/downloaded between jobs or stored for inspection according to retention settings. The cache action uses keys and restore keys; cache should not be used as the sole storage location for release artifacts.

### 7.2. GitLab CI

Job artifacts store output files and can be downloaded by downstream jobs according to `dependencies`/`needs`/artifact rules. Cache is for reuse across runs and has its own policy. Artifact expiration/retention must be configured to match release and audit requirements.

### 7.3. Jenkins

Jenkins can archive artifacts from a build or use plugins/artifact repositories such as Nexus, Artifactory, or a registry. The workspace is not a durable artifact store. When promoting the same artifact across environments, publish it to an immutable repository and record the digest/version.

### 7.4. General Rules

- Build once, promote the same artifact across environments.
- Use digests or checksums to identify content.
- Do not rebuild in each environment if the goal is to test and release the exact same binary.
- Store test reports, SBOMs, provenance, and required metadata.
- A cache miss must not break pipeline correctness; release artifacts must not depend on cache persistence.
- Restrict push/pull/delete permissions and retention based on criticality.

## 8. Secrets and Workload Identity

The three platforms store secrets differently, but the core principle is the same: secrets must only be granted to jobs that need them, for the required duration, with least privilege.

### 8.1. GitHub Actions

You can use repository, environment, or organization secrets and `GITHUB_TOKEN` with restricted permissions. OIDC allows a workflow to obtain a token with claims and exchange it with a cloud identity provider for short-lived credentials, provided the trust policy is configured properly.

Explicitly declare `permissions` for workflows/jobs. Do not grant `contents`/`packages`/`deploy` write permissions to every job if only a publish job needs them. Protect the production environment with appropriate reviewers and branch policies.

### 8.2. GitLab CI

GitLab supports CI/CD variables with attributes such as masked, protected, environment scope, and file variables depending on configuration. `CI_JOB_TOKEN` has its own scope and lifetime; ID tokens can be used for workload identity federation with external services.

Masked variables only obscure values in logs according to platform rules; they do not stop malicious code from reading and exfiltrating the secret. Jobs running untrusted code must not be granted production secrets.

### 8.3. Jenkins

Jenkins typically stores credentials in the Credentials Store and exposes them to a Pipeline via credentials binding or appropriate plugins. Read access to credentials depends on folder/item scope, credential domain, and authorization strategy. You must control who can modify a Jenkinsfile/job and who can run jobs with credentials.

Credential masking is not a boundary against malicious code. A script can read environment variables or transmit credentials over the network. Do not echo secrets, do not write them into workspaces/artifacts, and restrict which agents are allowed to receive credentials.

### 8.4. Table of Common Principles

| Control | Question |
|---|---|
| Least privilege | Does the job only have the permissions needed for its task? |
| Secret scope | Is the secret scoped to the repository/project, environment, or folder? |
| Workload identity | Can OIDC/federation be used instead of long-lived credentials? |
| Untrusted code | Can PRs from forks or unprotected branches read secrets? |
| Log/artifact | Could secrets leak into console logs, test reports, cache, or artifacts? |
| Rotation | Do credentials have an owner, expiry, and a rotation/revocation process? |

## 9. Environments, Approvals, and Promotion

An environment represents where an application is deployed, such as development, staging, or production. Environments can be associated with secrets, URLs, approvals, protection rules, and deployment history.

- GitHub Actions has environments, deployment history, and protection rules such as required reviewers or branch restrictions depending on configuration.
- GitLab CI has environment/deployment records, protected environments, and manual jobs/approval controls depending on edition, tier, and configuration.
- Jenkins can use the `input` step, credentials/RBAC, and plugins to create approval gates; exact semantics depend on how Jenkins is structured.

Approvals should be bound to a specific release candidate: artifact digest, commit, environment, and scope. Do not simply approve a generic button that allows the pipeline to deploy any arbitrary artifact afterward.

### 9.1. Promotion vs. Rebuilding

A reliable process typically:

1. Builds the artifact from an identified commit.
2. Tests and scans the artifact.
3. Publishes an immutable artifact to a registry.
4. Deploys the same digest to staging.
5. Runs post-deployment verification.
6. Collects production approval.
7. Deploys the exact verified digest to production.
8. Records the deployment record and verification results.

If you rebuild for production, the output may differ from the artifact that was tested. If a rebuild is strictly required, create a new release candidate and re-run the relevant gates.

## 10. Reusing Pipeline Logic

Reuse helps standardize pipelines and reduce copy/paste, though each platform has its own abstractions.

### 10.1. GitHub Actions

- Actions encapsulate a step or group of operations.
- Composite actions bundle multiple steps.
- Reusable workflows invoke another workflow as a unit with an input/output and secrets contract.
- Workflow templates help bootstrap standardized pipelines.

Pin actions by version or commit SHA according to policy; inspect the source and permissions of actions. Reusable workflows reduce duplication but also create supply chain dependencies that must be managed.

### 10.2. GitLab CI

- `include` loads configuration from another file, project, or component.
- `extends` and YAML anchors help reuse job templates.
- CI/CD components provide packaged configurations with an explicit interface.
- Child pipelines and multi-project pipelines split flows by component or repository.

Understand the merge/override semantics of `include`, `extends`, and variables. Shared templates can alter behavior across many projects; versioning and review are essential.

### 10.3. Jenkins

- Shared Libraries provide shared functions, steps, and pipeline conventions.
- Plugins extend SCM, credentials, agents, reporting, and deployment integrations.
- Folder/job templates or Job DSL can standardize configurations.

Shared Libraries and plugins can execute code on the controller/agent with broad privileges. Manage versioning, reviews, trusted/untrusted libraries, and plugin updates.

## 11. Observability, Status, and Audit Trail

Each platform provides its own logs and statuses, but a release needs a unified chain of evidence:

- The actor/event that triggered the pipeline.
- Repository, commit SHA, branch/ref, and pipeline definition revision.
- Run ID, job ID, and runner/agent identity.
- Test results, scan results, and quality gates.
- Artifact coordinates, version, digest, and provenance.
- Approval, approver, environment, and timestamp.
- Deployment ID, runtime digest, and post-deploy results.
- Retries, cancellations, rollbacks, and related incidents.

Pipeline logs explain the commands inside a job; platform audit logs record administrative changes; cloud/registry audit logs show which principal made API calls on target resources. Do not rely on a single console log to prove the entire release chain.

## 12. The Same CI/CD Flow Across Three Tools

Suppose a Java service has the flow:

1. Push or pull request.
2. Build and unit test.
3. Publish artifact when merged to `main`.
4. Deploy staging.
5. Smoke test.
6. Approval and deploy production.

### 12.1. GitHub Actions

~~~yaml
name: Orders CI/CD

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./gradlew --no-daemon clean check build
      - name: Upload release artifact for main
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/upload-artifact@v4
        with:
          name: orders-jar
          path: app/build/libs/*.jar

  publish:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: orders-jar
          path: dist/
      - name: Publish
        run: ./scripts/publish.sh dist/

  deploy_staging:
    needs: publish
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh staging

  deploy_production:
    needs: deploy_staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh production
~~~

This is an illustrative skeleton. A real workflow must upload/promote artifacts between jobs rather than assuming a shared workspace; the publish job must pin actions per policy, verify digests, and use an appropriate identity. The production environment should have protection rules and required approvals.

### 12.2. GitLab CI

~~~yaml
stages:
  - verify
  - publish
  - staging
  - production

verify:
  stage: verify
  image: gradle:8.10-jdk21
  script:
    - ./gradlew --no-daemon clean check build
  artifacts:
    paths:
      - app/build/libs/*.jar
    expire_in: 7 days

publish:
  stage: publish
  image: gradle:8.10-jdk21
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  needs:
    - job: verify
      artifacts: true
  script:
    - ./scripts/publish.sh app/build/libs/

deploy_staging:
  stage: staging
  environment:
    name: staging
  script:
    - ./scripts/deploy.sh staging

deploy_production:
  stage: production
  environment:
    name: production
  when: manual
  script:
    - ./scripts/deploy.sh production
~~~

This skeleton requires adjusting `rules` and `needs` to ensure different pipeline sources have proper dependencies; release artifacts must be published to an immutable registry and deployed by digest. A manual job is only a pause point; job execution permissions and protected environments must be configured separately.

### 12.3. Jenkins Declarative Pipeline

~~~groovy
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Verify') {
            steps {
                checkout scm
                sh './gradlew --no-daemon clean check build'
                stash name: 'orders-jar', includes: 'app/build/libs/*.jar'
            }
        }

        stage('Publish') {
            when {
                branch 'main'
            }
            steps {
                unstash 'orders-jar'
                sh './scripts/publish.sh app/build/libs/'
            }
        }

        stage('Deploy Staging') {
            when {
                branch 'main'
            }
            steps {
                sh './scripts/deploy.sh staging'
            }
        }

        stage('Deploy Production') {
            when {
                branch 'main'
            }
            steps {
                input message: 'Approve production deployment?'
                sh './scripts/deploy.sh production'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'build/reports/**', allowEmptyArchive: true
        }
    }
}
~~~

This skeleton assumes Multibranch Pipeline and Declarative Pipeline are configured appropriately. Production approval requires clear RBAC, designated approvers, and policies; the `input` step alone does not replace full governance. In a production system, separate credential scopes, pin the toolchain, publish immutable artifacts, and deploy the exact digest.

### 12.4. Similarities and Differences

| Step | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| PR/MR trigger | `pull_request` | Merge request pipeline/rules | SCM integration or multibranch plugin |
| Build/test | Job and steps | Job in a stage | Stage and steps |
| Dependency | `needs` | `stage`/`needs` | Stage order or Pipeline logic |
| Publish condition | `if` on event/ref | `rules` | `when`/branch condition |
| Artifact handoff | upload/download artifact or registry | Job artifacts or registry | archive/artifact repository |
| Staging | Environment and deployment job | Environment job | stage/job and plugin/script |
| Production approval | Environment protection | manual/protected environment | `input`/RBAC/plugin |
| Worker | Runner | Runner | Agent |

## 13. Pipeline Security: More Than Protecting YAML Files

A pipeline can read source code, secrets, and artifacts, and access production. The attack surface includes:

- Pipeline definitions and reusable components.
- Actions, includes, plugins, and Shared Libraries.
- Runner/agent images, workspaces, and networks.
- Secret stores, tokens, OIDC trust policies, and credential bindings.
- Artifact registries, caches, and package repositories.
- Environment approvals and deployment permissions.
- Webhooks, trigger tokens, and service accounts.

### 13.1. Separate Jobs by Privilege Level

Build/test jobs for pull requests typically only need read access to source and dependencies. Publish jobs need package write permissions. Staging/production deploy jobs need environment-specific identities and permissions. Do not grant full permissions to every job simply to make configuration easier.

### 13.2. Protect Workers

- Use ephemeral runners/agents for untrusted workloads where appropriate.
- Clean up workspaces and credentials after each job.
- Do not allow PRs from forks to run on workers with access to production networks.
- Restrict runner tags/labels and worker registration permissions.
- Keep images, runtimes, plugins, and actions up to date.
- Separate the controller/control plane from worker execution.

### 13.3. Pipeline Supply Chain

Pin actions, plugins, Shared Libraries, and components to reviewed versions/revisions. Verify artifacts using digests/provenance. Monitor changes to pipelines and permissions. A safe workflow file can still invoke an unsafe action/plugin; you must govern the entire pipeline dependency chain.

## 14. Operational Differences to Understand Before Choosing a Tool

| Topic | GitHub Actions | GitLab CI | Jenkins |
|---|---|---|---|
| SCM integration | Tightly integrated with GitHub repositories/events | Tightly integrated with GitLab projects/MRs | Connects to SCM via plugins/integrations |
| Control plane management | GitHub service | GitLab SaaS or self-managed | Organization operates the Jenkins controller |
| Execution scaling | Hosted/self-hosted runners | GitLab Runner and executors | Agent/node, cloud/plugin |
| Customizability | Actions, reusable workflows, and runners | YAML, components, runners, and pipeline features | Very broad via plugins and Shared Libraries |
| Maintenance | Lower with hosted; self-hosted requires management | Runners and instance depending on model | Controller, plugins, agents, and backups |
| Portability | Workflows/actions tied to GitHub ecosystem | Pipeline syntax tied to GitLab | Jenkinsfile/Shared Libraries tied to Jenkins/plugins |
| Operational cost | Depends on plan, minutes, and runners | Depends on tier, runners, and infrastructure | Infrastructure, operations, plugins, and staffing |

No single tool is best for every organization. GitHub Actions is often advantageous when source and governance live on GitHub; GitLab CI fits teams using GitLab as an integrated platform for source, issues, and pipelines; Jenkins is useful in environments requiring diverse system integrations, plugins, or complex legacy pipelines, though the organization must manage the controller, plugins, and agents.

The decision should be based on repository platform, self-hosting requirements, network boundaries, compliance, runner capacity, team skills, existing integrations, and total cost of ownership.

## 15. Migrating Pipelines Between Platforms

When migrating, do not start by translating YAML line-by-line. Extract the desired behavior into a platform-independent model:

1. List triggers and pipeline creation conditions.
2. Draw the job/dependency DAG and identify parallelism.
3. Document runner/agent requirements, OS, toolchain, and network access.
4. List inputs, secrets, identities, and permissions per job.
5. Define artifact/cache/workspace handoffs.
6. Document approvals, environments, and deployment scopes.
7. Define retry, timeout, cancellation, and concurrency semantics.
8. Document reports, audit events, and release evidence.
9. Re-implement on the target platform using appropriate abstractions.
10. Run in parallel or compare outputs during the transition period.

### 15.1. Common Migration Mistakes

- Converting a GitHub job into a GitLab stage while altering dependencies between jobs.
- Assuming workspaces are shared between jobs.
- Using GitLab cache instead of artifacts that must be transferred accurately.
- Long-lived Jenkins agents retaining files/secrets from previous builds.
- Converting an approval into a manual job where anyone has permission to trigger it.
- New triggers running two pipelines for the same commit.
- Job reruns causing duplicate publish or deploy side effects.
- Moving secrets to variables without preserving protected/environment scopes.
- Replacing plugins or actions without checking semantics and permissions.

## 16. Choosing the Right Abstractions

Several principles help keep pipelines maintainable:

- Use a job for a unit of work with clear inputs, outputs, and permissions.
- Use stages to express logical phases; do not create stages just for cosmetic naming.
- Use DAG dependencies to represent real relationships; avoid implicit ordering dependencies.
- Separate build/test from publish/deploy.
- Extract shared logic out of pipeline files into versioned abstractions.
- Place policies and permissions close to the jobs that require them.
- Use an artifact registry for outputs that need promotion; use cache for reproducible data.
- Use environments/protected resources for approvals and deployment history.
- Use ephemeral workers or workspace cleanup for untrusted code.
- Record release records to link commits, digests, approvals, and deployments.

## 17. Checklist for Reading and Reviewing a Pipeline

### Triggers and Source

- [ ] Know which events create a pipeline and which events are ignored.
- [ ] Know which source revision/ref is actually checked out.
- [ ] PRs/MRs from forks have appropriate permissions and secrets.
- [ ] No unintended duplicate pipelines are created.

### Graph and Execution

- [ ] Jobs, stages, steps, and dependencies are clearly understood.
- [ ] Independent tasks run in parallel properly.
- [ ] Artifacts are passed through durable mechanisms, not implicit workspaces.
- [ ] Runners/agents have appropriate capacity, isolation, and cleanup.

### Artifacts, Cache, and Security

- [ ] Artifacts have versions/digests and are promoted consistently.
- [ ] Cache does not replace release artifacts.
- [ ] Secrets are granted only to jobs that need them.
- [ ] Tokens/identities have least-privilege permissions and appropriate lifetimes.
- [ ] Actions/plugins/includes/Shared Libraries have controlled sources and versions.

### Environments and Governance

- [ ] Staging and production are clearly separated.
- [ ] Approvals are bound to the right artifact and environment.
- [ ] Production deployment permissions are restricted.
- [ ] Audit trails, release records, and post-deploy verification are in place.
- [ ] Retries, cancellations, and rollbacks do not cause unintended side effects.

## 18. Model Conclusion

GitHub Actions, GitLab CI, and Jenkins differ in naming, configuration, and operations, but all solve the same problem: receiving events, orchestrating a work graph, provisioning workers, managing inputs/credentials, producing outputs, and controlling releases.

Understand that the control plane is responsible for orchestration; the runner/agent is responsible for execution; the pipeline graph represents dependencies; artifacts are outputs to identify and promote; cache is only an optimization; secrets/identities determine permissions; environments/approvals control releases; and audit logs and observability provide evidence. Once you master this model, you can read pipelines across all three tools, spot semantic differences, design traceable pipelines, and switch platforms without losing critical controls.
