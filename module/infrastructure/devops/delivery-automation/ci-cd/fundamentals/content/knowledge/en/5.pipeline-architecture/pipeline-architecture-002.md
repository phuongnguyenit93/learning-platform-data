# Describing Job Dependencies with Directed Graphs

A CI/CD pipeline typically includes many jobs: compiling source code, checking formatting, running unit tests, packaging artifacts, running integration tests, performing security scans, and deploying. If a pipeline is described merely as a sequential list, independent jobs must wait on one another unnecessarily. Conversely, if all jobs run in parallel without declaring dependencies, the pipeline might run tests before artifacts are ready or deploy before quality gates finish.

Directed graphs clearly describe which jobs must complete before others. In pipelines, the standard model is a Directed Acyclic Graph (DAG). Each vertex represents a job; each edge represents a dependency and execution ordering relationship. From this graph, the system can determine which jobs are eligible to run, leverage parallelism, block dependent steps on failure, and help teams understand how a change flows from source code to the deployment environment.

## 1. What is a directed graph in a pipeline?

A directed graph consists of two components:

- **Vertex (or node):** represents an entity in the workflow, typically a job or task such as `compile`, `unit_test`, `package`, `integration_test`, or `deploy`.
- **Directed edge:** represents an ordering or dependency relationship between two vertices.

In pipeline design, a readable convention is that edge A → B means **B depends on A**: A must complete successfully before B is permitted to run. For example, `package` requires the output of `compile`, so there is an edge `compile` → `package`.

A DAG is a directed graph that contains no cycles. That means you cannot start at a vertex, follow directed edges, and return to the same starting vertex. Pipelines require this property because a job cannot wait on its own completion through a chain of dependencies.

Simple example:

~~~text
source
  |
  v
compile -----> package
  |
  v
unit_test
~~~

In this diagram, `compile` must run before `package` and `unit_test`. If `package` requires both `compile` and `unit_test`, we add the edge `unit_test` → `package`. The graph clearly describes the input conditions for `package`.

### DAGs vs. sequential job lists

A sequential list typically forces every step to run in a fixed order:

~~~text
compile -> lint -> unit_test -> package -> integration_test -> deploy
~~~

However, `lint` can be independent of `compile`, and both can run concurrently. A directed graph expresses this:

~~~text
             +----> compile ----> package ----> integration_test
source ------|
             +----> lint ------------------------------+
                                                        |
                                                        v
                                                   quality_gate
                                                        ^
                                                        |
             +----> unit_test --------------------------+
~~~

The graph does not dictate that all jobs must run in parallel. It only states the mandatory constraints. The scheduler can run independent vertices concurrently when sufficient runners and resources are available.

## 2. Modeling jobs and dependency relationships

Before writing pipeline YAML, you need to clearly identify the jobs, inputs, outputs, and execution conditions.

### Identifying vertices

A job should represent an independently understandable and verifiable goal. For example:

| Job | Objective | Primary Inputs | Outputs |
|---|---|---|---|
| compile | Compile source code | Source code, dependencies | Intermediate classes or binaries |
| lint | Check code conventions and quality | Source code, rule set | Analysis results |
| unit_test | Run unit tests | Source code or compiled classes | Test report |
| package | Create release package | Binaries, metadata, packaging config | JAR or container image |
| integration_test | Test component interactions | Artifact, test services | Test report |
| security_scan | Check security risks | Source or artifact | Scan report |
| quality_gate | Evaluate mandatory conditions | Results from preceding jobs | Pass or fail status |
| deploy | Deliver artifact to an environment | Verified artifact | Deployment record |

Do not split jobs too finely just to increase the node count. A job needs a sufficiently clear responsibility boundary, observable outputs, and a clear reason to exist in the pipeline. Conversely, if one job performs too many unrelated tasks, failures are hard to isolate and parallel optimization is limited.

### Identifying edges

For each job, ask:

1. What data or results does the job need before starting?
2. Which job produces that data or those results?
3. Must it wait for the upstream job to succeed, or does it only need an existing artifact?
4. If the upstream job fails or is skipped, is the current job still meaningful?

For example, `integration_test` needs `package` to produce the artifact, so there is an edge `package` → `integration_test`. `deploy` requires `quality_gate` to pass and needs the packaged artifact, so there are two edges: `package` → `deploy` and `quality_gate` → `deploy`.

Do not create an edge simply because two jobs appear next to each other in a YAML file. Edges must reflect real constraints. If there is no data or conditional dependency, two jobs can run independently.

### Distinguishing ordering dependencies from data dependencies

These two concepts are related but not identical:

- **Ordering dependency:** job B may only run after job A finishes.
- **Data dependency:** job B requires outputs produced by job A, such as a JAR file, test report, or image digest.

Declaring that job B depends on job A usually instructs the system to enforce ordering. However, many platforms do not automatically transfer files across runners. To use an output, you need artifacts, a shared workspace, or an appropriate storage mechanism.

For example, `compile` runs on runner 1 and `package` runs on runner 2. Even though `package` declares a dependency on `compile`, runner 1's build directory may not exist on runner 2. The pipeline must upload the artifact after `compile` and download it in `package`, or use a platform-supported data-sharing mechanism.

Cache is typically used to speed up builds and can be evicted or refreshed. An artifact is an intentional output of a run that must be stored and retrieved by identifier. Do not use cache as the sole record of a releasable output.

## 3. Reading a DAG through fan-out and fan-in

Two shapes commonly appear in pipelines: fan-out and fan-in.

### Fan-out: one job opens multiple branches

Fan-out occurs when one job finishes and multiple independent jobs can start:

~~~text
                 +----> lint
                 |
compile ---------+----> unit_test
                 |
                 +----> package_check
~~~

After `compile` finishes, `lint`, `unit_test`, and `package_check` can run in parallel if they have no other dependencies. This organization reduces feedback time and separates check results by objective.

Fan-out also appears when running a test matrix across multiple JDK versions, operating systems, or configurations. Each combination can be a separate job depending on a shared input.

### Fan-in: multiple branches converge into one job

Fan-in occurs when a job requires results from multiple preceding jobs:

~~~text
lint -----------+
                |
unit_test ------+----> quality_gate ----> deploy
                |
integration_test+
                |
security_scan --+
~~~

`quality_gate` can only pass when all mandatory checks have completed and satisfied policy. This is a convergence point for decision-making. A pipeline may have multiple quality gates at different stages, such as pre-merge, pre-staging, and pre-production.

### Combining fan-out and fan-in

Real-world pipelines often combine both patterns:

~~~text
                    +----> lint ---------------------+
                    |                                |
source -> compile --+----> unit_test ----------------+--> quality_gate
                    |                                |          |
                    +----> package -> integration_test+          v
                                 |                    |      deploy_staging
                                 +--> security_scan --+          |
                                                                v
                                                            smoke_test
                                                                |
                                                                v
                                                          deploy_production
~~~

This graph shows that independent checks can start early, while steps needing the artifact must wait for `package`. After results converge at `quality_gate`, the pipeline proceeds to deployment.

## 4. Conditions for a job to run

A job is generally eligible to run when all mandatory dependency jobs have finished with a platform-accepted status. Exact rules vary by CI/CD tool, so you need to distinguish the statuses:

| Upstream Job Status | Meaning | Typical Impact on Dependent Job |
|---|---|---|
| Success | Completed successfully | Can unlock downstream jobs |
| Failed | Encountered an error | Dependent job is typically blocked or skipped |
| Cancelled | Canceled before completion | Dependent job typically does not run |
| Skipped | Not executed due to conditions or dependencies | Can cause downstream jobs to be skipped if dependency is mandatory |
| Pending / Running | No final result yet | Dependent job continues waiting |
| Allowed failure / Warning | Failed but permitted by policy | May not block flow, depending on platform and configuration |

Do not assume every non-success status is acceptable. Define which jobs are mandatory, which are informational only, and who is authorized to grant exceptions.

### Mandatory jobs vs. optional jobs

Some steps may only run under specific conditions. For example, documentation checks only run when a PR modifies Markdown files; a docs publish job only runs on the main branch. When a conditional job is skipped, the pipeline must define whether dependent jobs should continue.

If a downstream job strictly requires the output of an optional job, explicitly design the behavior for when that job does not run. You can use optional dependencies if supported by the platform, or split the two flows into separate branches and converge at a job with appropriate conditions. Avoid creating mandatory dependencies on a job that may not exist in every run.

### Run conditions and dependencies are not interchangeable

A condition such as "run only on main" determines whether a job is activated in the current context. A dependency determines which jobs it must wait for. A job can have both simultaneously:

- Run only on the `main` branch.
- Start only after `quality_gate` succeeds.

Read both rules when investigating why a job was skipped or not scheduled.

## 5. Topological order and how systems schedule DAGs

A DAG does not define a single unique execution order. It permits multiple valid orderings, as long as every job runs after its dependencies.

**Topological order** is an arrangement of vertices such that for every directed edge A → B, A always appears before B. For example, if `compile` → `package` and `lint` is independent, both of the following orders are valid:

~~~text
compile, lint, package
lint, compile, package
~~~

In practice, the system does not necessarily execute jobs sequentially according to this list. It uses dependency relationships to identify the set of ready jobs, then schedules those jobs onto available runners.

### Kahn's algorithm at a conceptual level

A common way to find a topological order is to track the number of incomplete dependencies for each node:

1. Compute the number of incoming edges (indegree) for each node.
2. Put nodes with an indegree of 0 into a queue.
3. Dequeue a node and append it to the output order.
4. For each outgoing edge from that node, decrement the target node's indegree.
5. When a target node's indegree reaches 0, enqueue it.
6. Continue until the queue is empty.

If the number of dequeued nodes equals the total number of nodes, the graph has no cycles. If unprocessed nodes remain, there may be a cycle or a group of nodes stuck in dependency relationships.

### Cycles are design errors

Example:

~~~text
compile -> package -> integration_test -> compile
~~~

`compile` waits for `integration_test`, `integration_test` waits for `package`, and `package` waits for `compile`. No node in the cycle can start. The system may report a configuration error or fail to schedule the pipeline.

When encountering a cycle:

- Review each dependency and the reason for waiting.
- Check whether one job bundles multiple responsibilities that cause circular dependencies.
- Split work into separate preparation and independent verification steps.
- Pass required data via artifacts instead of creating reverse dependencies solely to share a workspace.
- Inspect dependencies dynamically generated from templates or matrices, as cycles may not be obvious in source files.

Do not arbitrarily delete an edge just to make the pipeline run. Before removing a dependency, verify whether the target job has the required data and conditions to run independently.

## 6. Critical path and pipeline duration

A DAG reveals which jobs determine the pipeline's completion time. The longest path by duration in a DAG is called the **critical path**. Ignoring runner limits, the minimum total duration of the pipeline is governed by this path.

Suppose a pipeline has the following durations:

| Job | Assumed Duration | Dependencies |
|---|---:|---|
| compile | 4 minutes | source |
| lint | 2 minutes | source |
| unit_test | 6 minutes | compile |
| package | 2 minutes | compile |
| integration_test | 8 minutes | package |
| security_scan | 5 minutes | package |
| quality_gate | 1 minute | lint, unit_test, integration_test, security_scan |
| deploy_staging | 3 minutes | package, quality_gate |

Each job's earliest completion time depends on the latest completion time among its dependencies. With the figures above:

- `compile` finishes at minute 4.
- `lint` finishes at minute 2.
- `unit_test` finishes at minute 10.
- `package` finishes at minute 6.
- `integration_test` finishes at minute 14.
- `security_scan` finishes at minute 11.
- `quality_gate` finishes only after all inputs are ready, at minute 15.
- `deploy_staging` finishes at minute 18.

The critical path in this example is `compile` → `package` → `integration_test` → `quality_gate` → `deploy_staging`, totaling 18 minutes. `lint` and `security_scan` can run in parallel with other branches, so they do not determine the finish time in this scenario.

Actual duration also depends on runner count, queue wait time, concurrency limits, shared resources, and cache. If only one runner is available, independent jobs may still have to queue. Therefore, DAG optimization must combine optimizing the dependency structure with execution capacity.

### Ways to shorten the critical path

- Move fast, independent checks earlier to detect errors sooner.
- Parallelize jobs that do not depend on each other.
- Optimize the longest job on the critical path, such as sharding integration tests into independently runnable groups.
- Reduce runner startup and dependency download times.
- Pass artifacts between jobs to avoid rebuilding identical inputs.
- Avoid adding dependencies just to preserve visual presentation order.
- Monitor runner queue times to distinguish DAG bottlenecks from insufficient execution capacity.

Running in parallel is not always faster. If jobs share a test database or a resource-constrained service, concurrent runs can cause contention, flaky tests, and longer total times. In such cases, isolate data, limit concurrency, or group jobs according to environment capacity.

## 7. Designing a DAG for a CI/CD pipeline

A practical design approach is to start from the final output and trace backward through the required preconditions.

### Step 1: Identify the final outcome

For example, the goal is to deploy a verified artifact to staging. To achieve that, the pipeline needs:

- An artifact built from a specific commit.
- Mandatory source code checks passing.
- Integration tests passing against the artifact.
- Security scans meeting policy.
- An aggregated quality gate approving release.

### Step 2: Separate jobs by responsibility

Create nodes for `compile`, `lint`, `unit_test`, `package`, `integration_test`, `security_scan`, `quality_gate`, and `deploy_staging`. Each node has a clear goal, inputs, and outputs.

### Step 3: Declare minimal dependencies

- `compile` depends on source checkout.
- `unit_test` depends on `compile` if compiled classes are needed.
- `package` depends on `compile`.
- `integration_test` and `security_scan` depend on `package`.
- `quality_gate` depends on `lint`, `unit_test`, `integration_test`, and `security_scan`.
- `deploy_staging` depends on `package` and `quality_gate`.

### Step 4: Identify outputs to pass

The package artifact must be uploaded once and downloaded in test or deployment jobs. Test reports and scan reports must be saved so `quality_gate` can evaluate them. Do not assume runners share a filesystem if the platform provisions a separate runner per job.

### Step 5: Define failure behavior

If `compile` fails, `unit_test` and `package` cannot run. If `lint` fails, `integration_test` might still be useful to gather further information, but `deploy` must be blocked by `quality_gate`. If `security_scan` is a mandatory gate, a failure or missing scan result must block release per policy.

### Step 6: Review conditions and release branches

PRs can run `compile`, `lint`, `unit_test`, and required scans. `deploy_staging` may run only after merging to `main`. `deploy_production` may require manual approval or dedicated release conditions. These conditions must be explicitly expressed in configuration.

## 8. DAG example in GitHub Actions

GitHub Actions supports declaring dependencies between jobs using the `needs` field. A job starts only after the jobs listed in `needs` have completed according to the platform's status rules.

The following example illustrates the flow: `build_package`, `lint`, and `unit_test` can run in parallel; the artifact from `build_package` undergoes integration testing and security scanning; results converge at `quality_gate`; then the artifact is deployed to staging, smoke-tested, and deployed to production.

~~~yaml
name: ci-cd

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build_package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon assemble
      - uses: actions/upload-artifact@v4
        with:
          name: application-package
          path: build/libs/*.jar

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon checkstyleMain

  unit_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle
      - run: ./gradlew --no-daemon test

  integration_test:
    needs: [build_package]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Run integration tests against package
        run: ./scripts/integration-test.sh package

  security_scan:
    needs: [build_package]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Scan package
        run: ./scripts/scan-package.sh package

  quality_gate:
    needs: [lint, unit_test, integration_test, security_scan]
    runs-on: ubuntu-latest
    steps:
      - name: All required checks passed
        run: echo "Quality gate passed"

  deploy_staging:
    needs: [build_package, quality_gate]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Deploy
        run: ./scripts/deploy.sh staging package

  smoke_test:
    needs: [deploy_staging]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify staging
        run: ./scripts/smoke-test.sh staging

  deploy_production:
    needs: [build_package, smoke_test]
    if: github.ref == 'refs/heads/main'
    environment: production
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: application-package
          path: package
      - name: Deploy
        run: ./scripts/deploy.sh production package
~~~

This is an architectural example; scripts, Gradle tasks, environments, and access permissions must be provided per project. Key points to note:

- `needs` creates dependency edges. For example, `quality_gate` waits for `lint`, `unit_test`, `integration_test`, and `security_scan`.
- `build_package`, `lint`, and `unit_test` can run in parallel because they declare no dependencies on one another.
- `build_package` creates and uploads the artifact. Integration tests, security scans, and deploy steps fetch that exact artifact by artifact name.
- `deploy_staging` has two prerequisites: `build_package` and `quality_gate`. It only runs on `main` according to the `if` condition in the example.
- `deploy_production` waits for `smoke_test` and `build_package`. Approval for the `production` environment must be configured in the repository's environment protection rules.
- If a mandatory dependency fails or is skipped, downstream jobs are usually skipped. Check `if` rules and job status behavior in the platform's documentation before applying.
- This minimal workflow does not yet include digest verification, provenance signing, or secret management. Those steps should be added according to release policy.

## 9. Representing DAGs across different CI platforms

CI/CD platforms have different syntax and scheduling rules, but the idea of nodes and dependencies is similar.

### GitHub Actions

- Each job is a node.
- `needs` declares the predecessor nodes that the job must wait for.
- Jobs without shared dependencies can run in parallel if runners and concurrency limits permit.
- Artifact actions are used to pass files between jobs.
- `if` conditions control whether a job runs in a specific context.
- Jobs depending on a failed or skipped job are typically skipped unless appropriate status conditions like `always` or `failure` are used. Use these conditions carefully so deployments do not accidentally run when a gate fails.

### GitLab CI/CD

GitLab supports `stages` and `needs`. When using only `stages`, jobs in a later stage usually wait for the previous stage to finish. When using `needs`, a job can start as soon as its specified dependencies complete, forming a finer-grained DAG flow.

Illustrative example:

~~~yaml
stages:
  - build
  - verify
  - deploy

build_app:
  stage: build
  script:
    - ./gradlew assemble
  artifacts:
    paths:
      - build/libs/

unit_test:
  stage: verify
  needs:
    - build_app
  script:
    - ./gradlew test

security_scan:
  stage: verify
  needs:
    - build_app
  script:
    - ./scripts/scan-package.sh build/libs/

deploy_staging:
  stage: deploy
  needs:
    - job: build_app
      artifacts: true
    - job: unit_test
      artifacts: false
    - job: security_scan
      artifacts: false
  script:
    - ./scripts/deploy.sh staging
~~~

In this example, `unit_test` and `security_scan` both depend on `build_app`, so they can run in parallel after the build finishes. `deploy_staging` waits for both results. Artifact and dependency configurations should be verified against how the project stores files and the GitLab version in use.

### Jenkins Pipeline

In Jenkins Declarative Pipeline, `stages` and `parallel` can describe certain forms of parallelism. For complex pipelines, scripted pipelines or other orchestration mechanisms can represent dependencies. Regardless of syntax, ensure parallel branches have clear input conditions and convergence steps run only after mandatory branches complete.

Do not copy configurations verbatim between platforms. Translate the semantics of the graph, then map them to the syntax and behavior of the target tool.

## 10. Test matrices and dynamic DAGs

Many pipelines must test the same application across multiple environment combinations—for example, JDK 17 and 21, Linux and Windows, or multiple database versions. A matrix generates multiple jobs from one shared definition.

~~~text
                 +--> test JDK 17 / Linux --+
build artifact --+--> test JDK 21 / Linux --+--> aggregate_test_results
                 +--> test JDK 21 / Windows-+
~~~

Matrix jobs are separate nodes in the execution graph. An aggregation job must wait for all mandatory combinations or apply a policy specifying which combinations are required.

When a matrix allows certain jobs to fail, distinguish acceptable failures from jobs skipped due to misconfiguration. Platforms may support `continue-on-error` or `allow_failure`, but applying them too broadly can mask compatibility bugs.

Some systems support generating child pipelines or dynamic DAGs based on repository contents. For example, changes in module A only generate test jobs for A and its dependent modules. This can save resources, but requires an accurate inter-module dependency model. If the change scope is misidentified, the pipeline might skip a required check. Periodic or pre-release comprehensive checks should compensate for selective testing strategies.

## 11. Common DAG design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Missing dependency edge | Job runs before inputs are ready | Declare real dependencies and explicitly pass artifacts |
| Adding unnecessary edges | Loss of parallelism, slower pipeline | Keep only dependencies that have a valid reason |
| Creating a cycle | Pipeline cannot be scheduled | Detect cycles and re-partition job responsibilities |
| Confusing dependency with file transfer | Downstream job cannot find artifact | Use supported artifacts or workspaces |
| Conditional job as mandatory dependency | Downstream job unexpectedly skipped | Design optional dependencies or appropriate conditions |
| Overly broad failure allowance | Quality gate stays green despite critical failures | Separate mandatory jobs from warning-only jobs |
| Running in parallel on shared resources | Data conflicts, flaky tests | Isolate environments or limit concurrency |
| Rebuilding across multiple pipeline branches | Inconsistent artifact outputs | Build once, share identified artifacts |
| Aggregation job not checking all inputs | Gate does not reflect all results | Declare complete dependencies and verify reports |
| Not recording per-node status | Hard to investigate bottlenecks and failures | Retain logs, durations, and statuses per job |

## 12. Observing and operating DAG pipelines

A graph that is easy to read on paper is not necessarily easy to operate. When the pipeline runs in practice, teams need visibility into the status and duration of every node.

Information to retain:

- Job name and run identifier.
- Related commit SHA or release ID.
- List of the job's dependencies.
- Queued, started, and finished timestamps.
- Runner or execution resource type.
- Status: success, failed, cancelled, skipped, or warning.
- Logs, test reports, scan reports, and related artifacts.
- Reason a job did not run or was blocked.

When a pipeline is slow, distinguish three time components:

1. **Queue time:** time a job spends waiting for a runner.
2. **Execution time:** time a job spends actually running.
3. **Dependency wait time:** time a job spends waiting for predecessor nodes.

If queue time is high, review runner capacity and concurrency limits. If execution time is high, optimize scripts, tests, caching, or tooling. If dependency wait time is high, review the critical path and unnecessary edges.

### Keeping a DAG maintainable

- Use goal-descriptive job names; avoid overly generic names like `task1` or `step2`.
- Group jobs by responsibility such as build, test, security, and deploy.
- Reuse templates or reusable workflows when multiple pipelines share the same structure.
- Keep dependency logic readable; avoid creating dependency chains solely to mimic presentation order.
- Document which nodes hold permissions to publish, deploy, or access secrets.
- Validate the DAG when modifying pipeline definitions, especially when adding conditional or matrix jobs.
- Store artifacts and reports with names, versions, or digests sufficient for traceability.

## 13. DAG design checklist

Before putting a DAG pipeline into use, review:

- [ ] Each node represents a job with a clear objective.
- [ ] Each edge represents an actual ordering or input dependency.
- [ ] The graph contains no cycles.
- [ ] Independent jobs can run in parallel when resources allow.
- [ ] Jobs needing artifacts have explicit upload/download or data-transfer mechanisms.
- [ ] Convergence jobs wait for all mandatory checks.
- [ ] Conditional jobs and optional dependencies have defined skip behavior.
- [ ] Failures in build, test, scan, or quality gates properly block release steps.
- [ ] Exceptions are scoped and recorded.
- [ ] Critical path and runner queue times are monitored.
- [ ] Artifacts are identified and consistently reused across steps.
- [ ] Logs, reports, and per-node statuses are sufficient for investigation.
- [ ] Secret and deployment permissions are granted only to necessary jobs.

## Conclusion

A DAG is a way of representing dependencies that keeps pipelines both properly ordered and able to exploit parallel execution. Clearly define nodes, edges, inputs, and outputs; keep the graph acyclic; distinguish execution dependencies from artifact transfer; and design convergence points for quality gates. Combined with per-job timing observability and identified artifact management, DAGs make pipelines easier to understand, optimize, and trust across the entire CI/CD flow.
