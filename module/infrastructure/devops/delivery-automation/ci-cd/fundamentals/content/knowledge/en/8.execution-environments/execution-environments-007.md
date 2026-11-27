# Managing Resources, Timeouts, and Connection Limits

A CI/CD pipeline can be logically sound yet still slow, unstable, or disruptive to shared services if job resource consumption goes uncontrolled. Multiple concurrent jobs can exhaust runner CPU, memory, and disk space. A job waiting indefinitely on an external service can tie up a worker and stall the queue. A test suite opening too many connections to a database or API can exceed the dependency's limits.

Managing execution environments therefore goes beyond picking a machine to run the pipeline. You must explicitly design **resource budgets, timeouts, concurrency levels, and connection limits** for each job. These guardrails give pipelines predictable completion times, efficient infrastructure utilization, and protection against overloading external services.

## 1. What Resources Does an Execution Environment Consume?

Every job runs on a runner, virtual machine, container, or platform-provided execution environment. Throughout its lifecycle, a job consumes several classes of resources:

| Resource | Where it is used | Signs of shortage or overload |
|---|---|---|
| CPU | Compilation, compression, static analysis, running tests | Prolonged jobs, sustained high CPU, heavy process contention |
| RAM | Compilers, test runners, containers, in-memory caches | OOM kills, terminated processes, heavy garbage collection |
| Disk | Checkouts, dependency caches, build outputs, Docker layers, logs | Disk full, write errors, mid-build failures |
| I/O | Reading dependencies, archive extraction, artifact writes, database tests | Low CPU yet slow jobs, rising I/O wait queues |
| Network | Fetching dependencies, API calls, image pushes, test service traffic | Timeouts, increased retries, low throughput, connection errors |
| Process/thread | Parallel tests, compiler daemons, workers | Process limit exceeded, excessive context switching |
| Connections | Database pools, HTTP clients, registries, service endpoints | Connection refused, pool timeouts, HTTP 429 or 503 |
| Platform quotas | CI minutes, runner count, artifact storage, API rate limits | Queued jobs, rejected runs, or publish failures |

Not every job needs high CPU. A dependency-download job may be bottlenecked by networking or the registry; an integration test job may be bottlenecked by the database; an image-build job may heavily consume disk and I/O. Therefore, do not look only at total duration and assume you need a bigger machine.

Measure resource usage per job type and per stage. For instance, if a build spends most of its time downloading dependencies while CPU sits nearly idle, adding cores will not help. If a runner runs out of disk because old Docker images accumulate, adding CPU or RAM will not fix the root cause.

## 2. Defining a Resource Budget per Job

Each job type should have a resource budget aligned with its workload and expected concurrency. A budget can cover CPU, RAM, disk, maximum duration, process count, and open connections.

Rough baseline classification:

| Job type | Characteristics | Key resources to watch |
|---|---|---|
| Lint and static analysis | Heavy source file reads, multi-file analysis | CPU, RAM |
| Unit tests | May spawn multiple test worker processes | CPU, RAM, process/thread count |
| Integration tests | Starts databases, brokers, or backing services | RAM, disk, network, connections |
| Package build | Compiler, linker, packaging | CPU, RAM, disk, and I/O |
| Container image build | Layer creation, compression, cache storage | CPU, RAM, disk, and I/O |
| Artifact publishing | Uploading packages or container images | Network, connections, registry quotas |
| Deploy | Infrastructure API calls and rollout waits | Network, API rate limits, timeouts |
| End-to-end tests | Calls multiple services and creates test data | Network, connections, duration, and service capacity |

Budgets must leave headroom for the operating system, CI agent, and background processes. Never allocate 100% of visible RAM or CPU to job workloads. On shared runners, account for the aggregate demand of concurrent jobs, not just a single job in isolation.

### 2.1. Estimating Concurrency

Suppose a runner has 8 vCPUs and 16 GiB RAM. A build job consumes an average of 2 vCPUs and 4 GiB RAM. Considering only those two resources, the theoretical maximum concurrent jobs is:

~~~text
min(floor(8/2), floor(16/4)) = 4
~~~

However, 4 leaves zero headroom for system reserve, I/O, disk, processes, networking, or background daemons. Reserving 2 vCPUs and 4 GiB RAM brings practical concurrency in this example down to:

~~~text
min(floor((8-2)/2), floor((16-4)/4)) = 3
~~~

Even this remains an estimate. Validate against metrics under real load, as peak utilization and average utilization can diverge sharply.

Across heterogeneous workloads, concurrency is bounded by the scarcest resource:

~~~text
C <= min(C_CPU, C_RAM, C_disk, C_network, C_connections, C_quota)
~~~

Where `C` is allowable concurrency. If runners have spare CPU yet the database accepts only 20 additional connections, the database limit determines how many integration test jobs can run simultaneously.

### 2.2. Setting Resource Requests and Limits

Depending on the platform, resources are configured at the runner, container, executor, Kubernetes pod, or test-runner invocation level. Distinguish:

- **Request:** expected resource allocation needed for the scheduler to place the environment.
- **Limit:** hard ceiling a process is permitted to consume.
- **Concurrency limit:** maximum number of jobs or tasks executing simultaneously.
- **Quota:** aggregate resources or runtime minutes allowed over a time window.

A Docker Compose example for a test service can declare CPU and memory limits supported by the deployment target:

~~~yaml
services:
  integration-test:
    image: example/test-runner:1.0
    command: ./run-integration-tests.sh
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
~~~

This snippet illustrates resource limit concepts. How `deploy.resources` is enforced depends on Docker Compose version, deployment mode, and runtime; verify whether your target platform actually honors those limits. If limits exist only in a file while the executor ignores them, jobs can still consume more resources than intended.

Do not set limits so low that jobs suffer constant OOM kills or throttling. Nor should you assign excessive limits to every job, which lowers concurrency and raises costs. Tune requests and limits using observed metrics.

## 3. Controlling Concurrency and Queuing

CI/CD often receives bursts of triggers concurrently: multiple pull requests, rapid pushes, release builds, and scheduled checks. If every job runs at once, infrastructure and backing services can overload.

Distinguish the layers of concurrency:

- **Pipeline concurrency:** number of active pipelines in a repository or project.
- **Job concurrency:** number of jobs dispatched concurrently by the scheduler.
- **Step/process parallelism:** number of processes or test workers inside a single job.
- **Service concurrency:** number of requests, sessions, or connections hitting a backing service.

Raising concurrency at one layer multiplies load at downstream layers. For example, 5 concurrent pipelines, each running 4 integration test jobs, each opening a 10-connection pool, create up to 200 potential database connections.

Ways to keep concurrency under control:

1. Cap concurrent jobs per runner pool or task category.
2. Use queues to throttle jobs competing for scarce resources.
3. Cancel superseded runs when new commits arrive, where policy allows.
4. Cap test worker counts inside each job.
5. Separate runners for CPU-intensive builds, integration tests, and deployments.
6. Restrict publish or deploy job concurrency per environment.
7. Use semaphores or locks when multiple pipelines mutate a shared resource.

GitHub Actions example using a concurrency group to keep only the latest run per workflow and ref:

~~~yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: ./mvnw --batch-mode verify
~~~

This pattern fits CI verification runs that newer commits can safely supersede. Avoid `cancel-in-progress` for every job type. A deployment mutating an environment, running migrations, or publishing a release may need to complete or follow a safe cancellation procedure. Those tasks require dedicated concurrency groups, serialization, and inter-run state management.

## 4. Managing Timeouts by Layer

A timeout caps how long an operation or task may wait or run. Without timeouts, jobs can hold runners indefinitely when a service stops responding, a process hangs, or a request never terminates.

Do not rely on a single global timeout for the entire system. Define timeouts across layers:

| Timeout layer | Scope | Example |
|---|---|---|
| Queue timeout | Time waiting for the scheduler to assign a runner | Job waiting in queue for an available runner |
| Job timeout | Total job execution time | Build or test completes within budget |
| Step timeout | A single step within a job | Dependency download or deployment |
| Command timeout | A subprocess or command | Maven, Gradle, Docker build |
| Connection timeout | Establishing a connection | Opening a database or API connection |
| Read/response timeout | Waiting for response data | HTTP request or socket read |
| Test timeout | A single test or suite | Hung integration test |
| Deployment/rollout timeout | Waiting for resources to reach target state | Kubernetes rollout |

CI platforms define timeouts differently. Some provide job-level timeouts without per-step timeouts; others support stage- or task-level timeouts. Verify your platform's exact semantics, especially when the clock starts and how child processes are terminated.

### 4.1. Setting Evidence-Based Timeouts

Timeouts that are too tight cause false failures during brief slowdowns. Timeouts that are too loose tie up runners and mask hung processes.

Derive timeouts from historical execution distributions:

- Collect completion durations across many successful runs.
- Inspect the median and high percentiles such as p95 or p99.
- Account for normal variance from load, cache misses, and network jitter.
- Set timeouts comfortably above normal runtimes yet below thresholds that waste capacity or breach SLAs.
- Track timeout occurrences and adjust as workload sizes evolve.

For instance, if 95% of unit test runs finish within 4 minutes and 99% within 6 minutes, a 10-minute timeout provides reasonable buffer. If jobs routinely take 8 minutes and keep hitting the 10-minute cap, investigate load or optimize the job rather than blindly bumping the timeout.

### 4.2. Overall Job Timeout vs. Operation Timeouts

Job timeout is the outer ceiling. Inside the job, network operations and long-running commands need tighter bounds of their own. If a job timeout is 20 minutes while a single HTTP call is allowed to hang for 20 minutes, error handlers and log-collection steps get zero time to run.

Allocate the time budget structurally:

~~~text
T_job >= T_checkout + T_build + T_test + T_publish + T_cleanup + T_reserve
~~~

For network calls, bound connection establishment and response reads separately. For example: 3 seconds max to connect to an API, 15 seconds max to read the response, and a 5-minute timeout on the entire publish step. Actual values should reflect service latency and SLAs.

### 4.3. Timeout Example in GitHub Actions

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - name: Run unit tests
        run: ./mvnw --batch-mode test

      - name: Package application
        timeout-minutes: 8
        run: ./mvnw --batch-mode package -DskipTests
~~~

In GitHub Actions, `timeout-minutes` can be configured on both jobs and steps. Step timeouts must fit within the remaining job budget if subsequent steps need time to execute. Values above are illustrative; choose durations tailored to your project and runner tier.

## 5. Timeouts for Networking and Backing Services

CI jobs frequently call registries, package repositories, databases, APIs, Kubernetes APIs, or test services. Each operation has distinct wait characteristics.

Distinguish:

- **DNS timeout:** failing to resolve the service hostname.
- **Connect timeout:** failing to establish a TCP/TLS connection within the limit.
- **TLS handshake timeout:** failing to complete the security handshake.
- **Read timeout:** connected, yet no response data arrives on time.
- **Overall request deadline:** total wall-clock budget for the entire request, including any retries.

A call with a 3-second connect timeout and a 10-second read timeout can still take far longer than 13 seconds if the client retries multiple times. Always enforce an overall request deadline.

For inherently slower operations like pulling large images or deploying, base timeouts on payload size, bandwidth, and expected rollout duration. Avoid overly aggressive timeouts that abort valid uploads mid-flight, while never leaving connections open indefinitely.

When a timeout occurs, logs should record the timeout type, target endpoint or service (never secrets), elapsed wait time, attempt count, and error code. These details separate DNS issues from network partitions, overloaded services, or application bugs.

## 6. Managing Connection Limits

Every connection is a stateful resource. Databases, HTTP servers, registries, and brokers cap concurrent connections. Opening too many causes services to reject new connections, inflates memory consumption, and degrades performance for both pipelines and live applications.

### 6.1. Connection Pools

Instead of opening a fresh connection per operation, applications and test runners typically use a connection pool. The pool reuses established connections and caps the maximum open count.

Key parameters:

| Parameter | Meaning |
|---|---|
| Maximum pool size | Maximum connections allowed in one pool |
| Minimum idle | Minimum idle connections kept warm |
| Connection timeout | Max wait to borrow a connection from the pool |
| Idle timeout | How long an unused connection stays open |
| Max lifetime | Maximum lifespan of a connection |
| Validation | How the pool verifies a connection is still healthy |

If a job launches 8 test workers and each worker creates a pool of up to 10 connections, one job can open 80 connections. With 4 such jobs running concurrently, total potential demand hits 320 connections—easily exceeding database limits.

### 6.2. Calculating Total Connections from Pipelines

A simple budgeting formula:

~~~text
N_total = N_jobs * N_workers_per_job * N_pool_per_worker + N_other
~~~

Where `N_other` covers connections from applications, monitoring, migrations, operators, and other services.

Suppose a database has a 500-connection limit. The team reserves 100 connections for applications and operations and 50 as buffer, leaving 350 for CI. If each integration test job spawns 5 workers with a max pool of 5 connections each, every job can open 25 connections. The theoretical ceiling on concurrent integration test jobs is:

~~~text
floor(350/25) = 14
~~~

Do not run at the full theoretical 14 slots if real traffic fluctuates. Retain headroom for burst connections and administrative tasks.

If the connection pool is shared at the process level rather than per worker, calculate using the actual pool topology. Formulas give an initial budget; always measure real connection counts at the database or proxy.

### 6.3. HTTP Clients and Per-Host Limits

HTTP clients should also reuse connections via keep-alive and cap concurrent connections. A pipeline can fire many concurrent requests against a package registry or cloud provider API. Exceeding server-side limits triggers HTTP `429` (Too Many Requests), `503`, or dropped connections.

Configure:

- Global and per-host maximum connections.
- Maximum concurrent in-flight requests.
- Pool acquisition wait timeout.
- Connection idle timeout and keep-alive settings.
- Overall request deadline.
- Retry caps and honoring `Retry-After` headers when returned.

Never enlarge connection pools just to cut wait times without checking server load. Oversized pools increase contention and push backing services into overload faster.

## 7. Retries, Backoff, and Rate Limits

Retries help ride out transient faults like brief timeouts, connection resets, or HTTP `503`. However, retries are not a cure-all.

**Consider retrying when:**

- The failure is likely transient.
- The operation is safely repeatable or uses an idempotency key.
- Budget remains within the overall deadline.
- The service permits retries and does not instruct otherwise.

**Avoid blind retries when:**

- Authentication or authorization fails (`401`, `403`).
- The request payload is invalid (`400`, `422`).
- The operation has side effects with unknown completion state.
- The service enforces a rate limit and the retry window has not elapsed.
- The overall deadline has already expired.

Use exponential backoff to gradually space out retry attempts, plus random jitter so concurrent jobs do not retry in lockstep:

~~~text
delay_n = min(delay_max, delay_base * 2^n) + jitter
~~~

Always cap retry attempts. If 100 jobs fail together and all retry after exactly 1 second, the target service gets hammered repeatedly. Jitter spreads out the retry storm.

On HTTP `429`, honor `Retry-After` whenever present. Rate limits may apply per token, request, user, IP, repository, or project; check service documentation. Jobs should log retry counts and wait intervals for post-mortem analysis.

Never retry deployment or publish steps carelessly without knowing whether the prior call succeeded. Inspect target resource state, use idempotent requests, or query by artifact/release identifier before resending.

## 8. Backing Service Resources in Integration Tests

Integration tests commonly spin up databases, message brokers, caches, or service containers. These containers have their own resource limits and must be managed alongside the runner.

Key principles:

- Start only the services required by the test suite; avoid redundant instances.
- Use isolated data per test suite or worker to prevent collisions.
- Close connections, threads, file handles, and containers when tests finish.
- Set timeouts on health checks and service startup.
- Enforce CPU/RAM limits on service containers where supported by the runtime.
- Clean up temporary volumes and networks according to policy.
- Avoid running destructive migrations against shared databases.
- Use isolated databases or namespaces for parallel jobs.

If multiple jobs share one test database, cap concurrency or create a separate schema/database per run ID. A hung job must never hold locks or open transactions indefinitely. Test frameworks need timeouts on individual test cases and teardown hooks to release resources.

Backing services can also become the bottleneck. If a runner has 16 cores while the test database only sustains 4 concurrent jobs, raising test parallelism can actually slow down total runtime through lock contention and connection waits.

## 9. Disk, Caches, and Artifacts Need Limits Too

Disk space is frequently overlooked until runners run out of room. Multiple repository checkouts, dependency caches, Docker layers, test reports, and artifacts accumulate quickly.

Control:

- Workspace sizes and concurrent checkout counts.
- Cache capacity and eviction/expiration policies.
- Retained Docker images and dangling layers.
- Artifact sizes and retention policies.
- Verbose logs or duplicated test outputs.
- Temporary test data and scratch files deleted after jobs.

Caches reduce dependency download times, but caches are not release artifact stores. Never cache secrets, tokens, or sensitive data. Cache keys should capture dependency lockfiles and target platforms to avoid restoring incompatible versions.

Release artifacts need retention long enough to support deployments, rollbacks, and audits. Factor artifact storage volume and retention windows into platform quotas.

## 10. Observing and Diagnosing Overload

You cannot manage execution environments effectively by looking only at pass/fail outcomes. Track metrics across runners, jobs, and backing services:

| Metric | What to look for |
|---|---|
| Queue wait time | Whether jobs sit waiting for runners |
| Job duration | Unexpected spikes or drift in runtimes |
| CPU utilization | Saturation or CPU throttling |
| Memory peak / OOM | RAM hitting container or host limits |
| Disk usage | Rapid workspace or cache growth |
| Network throughput | Bottlenecks downloading dependencies or uploading artifacts |
| Connection pool wait | Jobs blocking for available connections |
| Active connections | Connection count approaching service limits |
| HTTP 429/5xx | Rate limiting or overloaded services |
| Timeout/retry rate | Rising transient errors or misconfigured timeouts |
| Cancellation rate | Frequent cancellations due to concurrency or timeouts |

When a job slows down, compare queue wait time against actual execution time. High queue wait points to insufficient runners or concurrency quotas; high execution time points to heavy job steps or slow backing services.

When multiple jobs time out against the same endpoint, investigate that endpoint and connection limits before raising timeouts everywhere. On OOM events, identify which process consumed RAM, peak usage, worker count, and container limits. On disk exhaustion, inspect caches, Docker layers, artifacts, and temporary files.

Logs should include run ID, job ID, endpoint/service name, elapsed duration, retry count, and error classification. Never include credentials or sensitive payloads in diagnostic logs.

## 11. Example Resource Budget for a Pipeline

Suppose a Java service pipeline includes `verify`, `integration test`, `package`, and `publish`. The team uses 8-vCPU, 16-GiB RAM runners and a test database capped at 200 connections.

An illustrative budget configuration:

| Job | Expected CPU | Expected RAM | Timeout | Max DB connections |
|---|---:|---:|---:|---:|
| Lint + unit test | 2 vCPU | 3 GiB | 10 minutes | 0 |
| Integration test | 2 vCPU | 4 GiB | 20 minutes | 20 |
| Package | 3 vCPU | 5 GiB | 12 minutes | 0 |
| Publish | 1 vCPU | 1 GiB | 8 minutes | 0 |

Suppose the team reserves 40 connections for other services and 20 as buffer. That leaves 140 database connections for integration tests. At up to 20 connections per job, the database limit allows at most 7 concurrent integration test jobs. However, runner capacity and quotas may impose a lower cap.

The team might limit each 8-vCPU/16-GiB runner to at most 2 concurrent integration test jobs and measure real execution times. To scale further, they can add runners or database capacity after verifying other bottlenecks.

A well-structured design will:

1. Run lint and unit tests early since they need minimal backing services.
2. Cap integration tests by connection count and database resources.
3. Run packaging only after mandatory tests pass.
4. Run publish with low concurrency and bounded retries.
5. Set distinct timeouts per job and for registry calls.
6. Retain logs, reports, and metrics to tune budgets over time.

Numbers in this example illustrate the methodology only. Measure real load, peak memory, active connections, and runtimes before finalizing production budgets.

## 12. Execution Environment Operations Checklist

Before putting a pipeline into service or raising concurrency, verify:

- [ ] CPU, RAM, disk, I/O, and network needs are profiled for each job type.
- [ ] Requests and limits align with actual observed utilization.
- [ ] Headroom is reserved for the runner OS and background processes.
- [ ] Concurrency stays within runner capacity, service limits, and quotas.
- [ ] Jobs enforce overall timeouts; critical network calls and tests have tighter timeouts.
- [ ] Timeouts are derived from historical data and leave budget for cleanup.
- [ ] Connection pools are bounded and summed across all concurrent jobs/workers.
- [ ] HTTP clients enforce connection caps, request deadlines, and keep-alive limits.
- [ ] Retries are bounded with backoff, jitter, and respect for `Retry-After`.
- [ ] Side-effecting steps are idempotent or verify state before retrying.
- [ ] Integration tests release connections, containers, locks, and temp data.
- [ ] Caches, logs, and artifacts enforce size limits and retention policies.
- [ ] Metrics cover queue wait, job duration, CPU, RAM, disk, connections, and timeouts.
- [ ] Safe mechanisms exist to pause or shed load when backing services overload.

Managing resources, timeouts, and connections is an integral part of pipeline design, not an afterthought. When budgets are tailored per job, concurrency matches real capacity, and every operation has clear deadlines, pipelines run more reliably, cost stays predictable, and shared systems remain protected.
