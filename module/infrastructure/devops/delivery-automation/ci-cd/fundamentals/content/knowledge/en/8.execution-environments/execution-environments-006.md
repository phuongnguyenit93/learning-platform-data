# Provisioning Backing Services for Integration Tests

Integration tests verify that multiple components work properly when interacting with one another. An application can pass all unit tests and still fail when connecting to a database, cache, message broker, object storage, or an external service API. Therefore, the test environment must provide backing services with controlled versions, configurations, data, and lifecycles.

In CI/CD, provisioning backing services goes beyond simply starting a container. The pipeline must ensure the service is ready to accept requests, the application connects to the right address, test data does not collide, failures are logged thoroughly for diagnosis, and resources are cleaned up after each run. This forms part of **DEVOPS_CI_CD_FUNDAMENTALS**: designing reproducible execution environments so automated builds and tests provide trustworthy evidence before release.

## 1. What Are Backing Services in Integration Testing?

A backing service (supporting service or dependency) is an external system the component under test communicates with to complete a business flow. Depending on the application, these may include:

| Service category | Examples | What to verify |
| --- | --- | --- |
| Relational databases | PostgreSQL, MySQL, SQL Server | Connections, SQL, transactions, constraints, migrations, and data types |
| NoSQL databases | MongoDB, Cassandra | Protocols, schemas/documents, indexes, and queries |
| Caches and key-value stores | Redis | Reads/writes, TTL, serialization, eviction, and behavior when cache disconnects |
| Message brokers | RabbitMQ, Kafka | Publish/consume, routing, acknowledgements, retries, and message ordering |
| Object storage | S3-compatible storage, MinIO | Uploads/downloads, access permissions, metadata, and error handling |
| Search engines | Elasticsearch, OpenSearch | Mappings, indexing, queries, and eventual consistency |
| External APIs | Payment, shipping, identity services | HTTP contracts, timeouts, auth, retries, and error responses |
| Supporting utilities | SMTP server, fake OAuth/OIDC provider | Email delivery, callbacks, tokens, and authentication flows |

Not every integration test needs to spin up the entire ecosystem. Choose the exact services needed for the behavior under test. For example, repository tests need a real production-compatible database; payment API timeout tests can use an HTTP stub capable of simulating latency and errors. Publish/consume tests should use a real broker or compatible environment to validate critical protocols and semantics.

Clearly distinguish three testing layers:

- **Unit test:** isolates a small unit, typically replacing dependencies with mocks or fakes.
- **Integration test:** verifies interactions across components, usually requiring one or more real or compatible services.
- **End-to-end test:** verifies end-to-end flows across multiple layers, often requiring a more production-like environment and taking longer to run.

A mock can help force an API to return a specific error, yet it does not prove compatibility with a real database engine, broker, or protocol. Choose service fidelity based on the risk being verified.

## 2. Inventory Dependencies Before Building the Environment

Before writing the pipeline, map out the services your tests require. For each dependency, document:

- Service name and required version.
- Protocol, port, hostname, or network alias.
- Authentication method and required permissions.
- Mandatory configuration such as database name, topic, bucket, or virtual host.
- Readiness condition: when the service can genuinely handle business operations.
- Initial data seeding, migration, and data reset procedures.
- Resource limits and startup duration.
- Log collection, status reporting, and cleanup procedures.

For example, an ordering application might require PostgreSQL to store orders, Redis to cache inventory, RabbitMQ to emit events, and an HTTP stub to simulate a shipping service. Identify which tests need all four services and which need only a subset. Grouping tests avoids spinning up a heavy broker for a simple database-only check.

A concise dependency table serves as a contract between test authors and pipeline maintainers:

| Component under test | Required service | Input configuration | Readiness condition |
| --- | --- | --- | --- |
| Order repository | PostgreSQL | URL, user, password, database | Connection succeeds and migrations finish |
| Inventory cache | Redis | Host, port, namespace | Ping succeeds, set/get operations work |
| Event publisher | RabbitMQ | Host, port, user, virtual host, exchange | Broker is ready and exchange is declared |
| Shipping adapter | HTTP stub | Base URL, mock API key | Health endpoint returns ready status |

Keep non-sensitive configuration in version-controlled test config files. Passwords, tokens, and private certificates must be injected via a secret store or the CI platform's secrets mechanism.

## 3. Choosing How to Provision Backing Services

There are several ways to provision services for integration tests. No single option fits every team; weigh production fidelity, startup latency, isolation, Docker requirements, and operational cost.

### 3.1. CI-Managed Service Containers

Some CI platforms let you declare auxiliary containers directly inside the pipeline definition. The CI engine or runner starts the containers, wires them to the job, and cleans them up with the job lifecycle.

Advantages:

- Services are declared right next to the pipeline, making them easy to inspect and review.
- Services can be scoped to an individual job.
- Easy to provision fresh databases, caches, or brokers per run.
- Reduces the need to maintain a shared test server.

Limitations:

- Hostname resolution and port mapping depend on the platform, executor, and job type.
- Not every platform supports the same service options or health check flags.
- Complex multi-container setups, volumes, networks, or bootstrap sequences can be awkward to express directly.

### 3.2. Docker Compose

Docker Compose excels when the environment needs multiple interconnected containers: application, database, broker, cache, stub APIs, and observability tools. A single Compose file describes images, networks, ports, volumes, environment variables, health checks, and dependencies.

Its advantage is that teams can share the exact same setup locally and in CI. The limitation is that the runner needs Docker Engine or a compatible runtime, and the pipeline must orchestrate service waits, log collection, and resource teardown.

Minimal Compose example:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: orders_test
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user -d orders_test"]
      interval: 5s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
~~~

This is an illustrative setup. In real environments, pin image versions per team policy; when strict traceability is needed, pin digests instead of mutable tags. Never reuse illustrative passwords in shared or production environments.

Compose can express dependency ordering and health conditions:

~~~yaml
services:
  api:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
~~~

`depends_on` with `service_healthy` waits for dependency health checks to pass before starting the dependent service in Compose versions supporting this syntax. However, a health check only reflects its declared probe; it does not guarantee every business workflow is ready. Applications and tests should still implement bounded connection retries.

### 3.3. Testcontainers

Testcontainers is a library that lets test code start and stop dependency containers tied to the test lifecycle. This works well for Java projects using JUnit: tests can declare PostgreSQL, Redis, Kafka, or other containers directly inside test code.

Advantages:

- Test environment requirements live close to the tests that need them.
- Containers can be scoped per test class or test suite.
- Easy to run identical tests locally and in CI wherever a compatible Docker API is available.
- Uses service versions much closer to production than in-memory databases.

Limitations:

- The runner must provide a Docker daemon/socket or compatible runtime.
- Container startup adds time to test runs.
- Image versions and Docker environment compatibility must be managed.
- Parallel test execution requires resource and data isolation controls.

JUnit 5 example with PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import java.sql.DriverManager;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class OrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void databaseStartsAndAcceptsConnections() throws Exception {
        try (var connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword())) {
            assertTrue(connection.isValid(2));
        }
    }
}
~~~

This example illustrates container lifecycle and a basic connectivity check; in real projects, configure your DataSource from the JDBC URL, username, and password supplied by Testcontainers, run migrations, and verify repositories or business logic. Testcontainers dependencies must match your project's JUnit and Java versions. Never hardcode host ports, because Testcontainers maps containers to random ports.

### 3.4. Dedicated Managed Shared Environments

A team may use a database or broker running in a shared test environment. This can reduce startup time, but increases risk:

- Another team's tests can mutate shared data or configuration.
- One run can interfere with another run's results.
- The environment can drift outside pipeline control, hurting reproducibility.
- Secrets and access permissions require tighter governance.

If a shared environment is unavoidable, create a separate database/schema/topic/bucket or namespace per pipeline, use least-privilege accounts, enforce reset rules, and audit usage. Never let automated tests write to live staging or production user data.

## 4. Service Started Does Not Mean Service Ready

This is a frequent cause of flaky integration tests. A container may show as running while the process inside is still initializing:

- A database is replaying WAL logs, running migrations, or creating users.
- A broker is electing a leader, creating topics, or recovering logs.
- Redis has bound its port but is still loading persistence data or config.
- An HTTP service has bound its port but has not connected to its own dependencies.

Distinguish these readiness levels:

1. **Process started:** the process has launched.
2. **Container running:** the runtime reports the container is up.
3. **Port reachable:** a TCP connection to the port succeeds.
4. **Service ready:** the protocol or health endpoint reports it can accept requests.
5. **Application ready:** the business operations tests rely on succeed, such as querying a database or publishing/consuming a message.

Waiting only for container startup or an open TCP port is usually insufficient.

### 4.1. Use Meaningful Health Checks

Health checks should verify conditions closely matching how the application uses the service:

| Service | Weak check | Better check |
| --- | --- | --- |
| PostgreSQL | TCP port 5432 open | `pg_isready` with target database/user |
| Redis | TCP port 6379 open | `redis-cli ping` returns `PONG` |
| RabbitMQ | AMQP port open | Broker reports ready and app can connect |
| HTTP stub | Process running | Health endpoint returns expected HTTP status |
| Kafka | Broker port open | Metadata request succeeds and target topics exist |

Health checks must never destroy data or consume business messages. Keep them fast, repeatable, and bounded by timeouts.

### 4.2. Bounded Retries and Backoff

Even after a health check passes, applications can encounter brief transient connection failures. Use bounded retries with gradual delay and an overall timeout:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

attempt=1
max_attempts=20

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"; do
  if (( attempt >= max_attempts )); then
    echo "Database not ready after $max_attempts attempts" >&2
    exit 1
  fi

  delay=$((attempt < 5 ? attempt : 5))
  echo "Database not ready; retrying in ${delay}s (attempt $attempt)"
  sleep "$delay"
  attempt=$((attempt + 1))
done

echo "Database is ready"
~~~

This script uses Bash and `pg_isready` inside the execution environment. In practice, match total timeout to the service's normal startup window. If the timeout expires, fail the pipeline with logs; never retry infinitely, as that ties up runners and masks configuration bugs.

If a service starts slowly, inspect logs to distinguish slow startup from genuine failures such as misconfiguration, OOM errors, port conflicts, or incompatible images.

## 5. Configuring Networking and Connection Addresses Properly

Containers can be running while tests still fail to connect because hostnames and ports differ by topology:

- Tests running directly on the runner host usually connect via host address and published/mapped ports.
- Tests running inside a job container typically connect via service alias or container name on a shared network.
- One container cannot reach another container using `localhost` by default. `localhost` always refers to the current process's machine/network namespace.
- Container-internal ports and host-published ports can differ.

For example, Compose defines services `postgres` and `api` on the same default network. From inside the `api` container, the hostname is `postgres` and the port is the internal port `5432`. From a process running directly on the host, tests may use `localhost` and the published host port, such as `5432`.

Therefore, inject connection parameters from the pipeline or test framework rather than hardcoding `localhost`:

~~~text
DB_HOST=<hostname or service alias>
DB_PORT=<port reachable from the test process>
DB_NAME=orders_test
DB_USER=test_user
DB_PASSWORD=<test credential>
~~~

With Testcontainers, read the host and mapped port from the container API; never assume a fixed host port. With GitHub Actions service containers, when the job runs directly on the runner host, service ports normally must be published/mapped to be reached via `localhost`; when the job runs inside a container, the service label acts as the hostname on the Actions-created network. With GitLab CI, services are typically reached via hostname alias on the job network depending on the executor and runner configuration.

When connections fail, verify in order: is the container running, did health checks pass, does the hostname resolve, which ports are published, are tests running on host or container, are firewalls/network policies blocking traffic, and are credentials correct. Never solve networking failures by opening all ports externally.

## 6. Managing Service Versions and Configurations

Test results are trustworthy only when you know exactly which service versions ran. Pin database, broker, cache, and stub API image versions per project policy. Avoid mutable tags like `latest` in critical pipelines so the same commit does not run against different images on different days.

Keep these synchronized:

- Image versions and digests when immutability is required.
- Service extensions, plugins, or feature flags.
- Database settings, collation, timezone, and character encoding.
- Broker configuration such as topics, partitions, retention, and acknowledgements.
- Cache configuration such as eviction policies and TTLs.
- Schema versions or API contracts for mock/stub services.

Test services need not mirror production identically, yet every difference must be intentional. For instance, running real PostgreSQL at the same major version as production gives far stronger evidence than H2 if the app relies on PostgreSQL-specific SQL syntax, types, or behaviors.

Commit test configuration to the repository so reviewers see changes. Keep non-sensitive config separate from secrets. Test credentials should be narrowly scoped, short-lived where possible, and never reused in production.

## 7. Creating and Isolating Test Data

Even a healthy service produces flaky results if input data shifts across runs. Every integration test needs clarity on what data is created, what is read, and how cleanup occurs.

### 7.1. Choosing the Right Isolation Scope

Common strategies include:

- **Dedicated database per job:** easy to reset completely; suits engines with fast database creation.
- **Dedicated schema per job or suite:** reduces instance creation overhead, but requires careful migration and search-path handling.
- **Dedicated namespace:** uses prefixes for Redis keys, topics, buckets, or objects.
- **Transaction rollback:** works when tests run inside a single transaction; insufficient for async tasks, multiple connections, or out-of-transaction commits.
- **Uniquely identified fixtures:** tags created data with run ID/UUID and deletes by namespace after testing.

Match the strategy to the service's semantics. Not every system supports fast rollbacks or resets. For message brokers, avoid sharing topics and consumer groups across parallel jobs that might consume each other's messages.

### 7.2. Using Deterministic Data and Avoiding Order Dependencies

Tests should create the data they need and never rely on leftover state from prior runs. Fixtures should stay small enough to understand while covering valid, invalid, boundary, and error cases.

Example:

1. Create a customer with a test-specific ID.
2. Create an order linked to that customer.
3. Invoke the API or repository under test.
4. Assert persisted data and emitted events.
5. Delete data by ID or tear down the test environment.

Avoid hardcoding collision-prone IDs like `1` or `100` in shared databases. Use UUIDs, prefixes containing pipeline/job IDs, or isolated databases. Never use real personal data; fixtures should use synthetic, non-sensitive data.

### 7.3. Handling Parallel Test Execution

When CI runs multiple jobs or tests concurrently, guard against collisions:

- Give each job an isolated database/schema/namespace.
- Let the runtime dynamically allocate host ports where possible.
- Give topics, queues, buckets, and object keys unique names.
- Never share a single mutable test account across concurrent jobs.
- Use locks only when a resource truly cannot be isolated.
- Cap concurrency if services hit connection, CPU, or RAM limits.

A test that passes in isolation yet fails intermittently in parallel runs usually indicates shared state, colliding resource names, or test-order dependencies.

## 8. Running Migrations and Bootstrapping in Sequence

Databases should be prepared in a clear sequence:

1. Start the database and wait for readiness.
2. Create the database/schema and accounts with appropriate privileges.
3. Run migrations using the exact tool and version the application uses.
4. Load required fixtures or reference data.
5. Start the application or test suite.
6. Verify behavior and collect logs.

Do not let every test craft schemas in ad-hoc ways. Run the exact migration code the application uses in deployment so migrations themselves are validated. Hand-written test schemas can miss migration bugs before production.

For brokers, bootstrapping may require declaring exchanges, queues, topics, or permissions before tests run. For object storage, create buckets and policies. For stub APIs, load expectations or scenarios. Make bootstrap steps idempotent whenever possible so re-running neither duplicates state nor breaks the environment.

Never run destructive migrations against shared services. When testing upgrade migrations, spin up a temporary database from old-version fixtures or a controlled snapshot and run the upgrade inside that isolated scope.

## 9. Examples of Provisioning Services in CI

### 9.1. GitHub Actions with PostgreSQL Service Container

The following example shows a job running directly on the runner host, using a PostgreSQL service and waiting for database readiness before executing tests:

~~~yaml
name: Integration tests

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: orders_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U test_user -d orders_test"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 20
    env:
      DB_HOST: localhost
      DB_PORT: 5432
      DB_NAME: orders_test
      DB_USER: test_user
      DB_PASSWORD: test_password
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run integration tests
        run: ./gradlew integrationTest
~~~

This example illustrates running on the runner host with a published port. Health check options tell GitHub Actions to wait for the service to become healthy before starting the job; tests should still handle connection timeouts gracefully. For jobs running inside a container, connections typically use the service label as hostname and the internal port; adjust according to your job's network topology. The password shown is strictly for ephemeral testing, never shared services.

### 9.2. GitLab CI/CD with Services

GitLab CI lets you declare service containers within a job. The service alias resolves as the hostname from the job environment according to runner configuration:

~~~yaml
integration-test:
  image: gradle:8-jdk21
  stage: test
  services:
    - name: postgres:16
      alias: postgres
  variables:
    POSTGRES_DB: orders_test
    POSTGRES_USER: test_user
    POSTGRES_PASSWORD: test_password
    DB_HOST: postgres
    DB_PORT: "5432"
    DB_NAME: orders_test
    DB_USER: test_user
    DB_PASSWORD: test_password
  script:
    - ./gradlew integrationTest
~~~

Passing variables into services and health check support depend on the GitLab Runner version, executor, and image. Verify that the runner can reach the service, the service receives initialization variables, and the job waits for readiness before tests begin. If the runner lacks native health checks, add a bounded wait step in the script.

### 9.3. Docker Compose in a Pipeline

When multiple dependencies are required, a pipeline can launch Compose, run tests, collect logs on failure, and always clean up resources:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose logs --no-color > compose-test.log || true
  docker compose down --volumes --remove-orphans
}
trap cleanup EXIT

docker compose up --detach --wait
./gradlew integrationTest
~~~

`trap ... EXIT` guarantees cleanup runs whether the script exits normally or fails. Saving logs before `down` preserves forensic evidence. In real pipelines, upload `compose-test.log` as an artifact even on job failure using the CI platform's always-run upload mechanism.

`down --volumes` deletes the Compose project's volumes. Use it only when data belongs strictly to the job's ephemeral environment. Never run that cleanup against a shared project or volume relied on by another team.

## 10. Collecting Logs, Diagnostics, and Cleanup

When an integration test fails, test runner logs may report only `connection refused` or `timeout`. To pinpoint root causes, capture evidence from the backing services as well:

- Container/service state and health check status.
- Startup logs from databases, brokers, caches, or stubs.
- Network and port-mapping details.
- Migration and bootstrap output.
- Test start times, wait durations, and retry counts.
- Commit SHA, job ID, image tag/digest, and tool versions.

Pipelines should collect service logs upon test failure before stopping or destroying services. Avoid printing credentials, tokens, personal data, or sensitive payloads in logs. Use sanitized logs, request IDs, and metadata for troubleshooting.

Cleanup is part of environment design:

- Stop containers and networks created by the job.
- Remove temporary volumes, databases, schemas, topics, buckets, or namespaces.
- Revoke temporary credentials if supported by the system.
- Release ports, processes, and temp files.
- Retain diagnostic artifacts for the required retention window.

If cleanup fails, log and alert so leaked resources do not exhaust runners or break subsequent runs. Use unique per-pipeline project/namespace names so resources can always be traced back to the run that created them.

## 11. Common Failures and Remediation

| Symptom | Possible cause | Investigation or fix |
| --- | --- | --- |
| `Connection refused` at test start | Service port not open yet or test uses wrong host | Wait for readiness; inspect network and port mappings |
| Port open but queries fail | Process bound port, yet service not ready or DB missing | Use protocol-level health checks, inspect logs and bootstrap |
| Tests pass locally but fail in CI | Differing images, versions, shells, networks, or env vars | Pin dependencies, make config explicit, and match topology |
| Intermittent test failures | Shared data, startup races, concurrency, or tight timeouts | Isolate namespaces, use bounded retries, and check ordering |
| Migrations fail in CI | Different DB version/collation, non-idempotent script, or missing perms | Match DB engine/version and run migrations with proper role |
| Job cannot resolve service hostname | Tests on wrong network or incorrect alias | Check whether tests run on host or container; fix hostname |
| Container OOM or killed | Too many services or excessive concurrency | Reduce services, limit concurrency, allocate adequate RAM |
| Next run affected by previous run | Incomplete cleanup or shared volume/database | Use isolated project names and reset temporary resources |
| Root cause unclear after job ends | Service logs deleted before collection | Upload logs and status prior to cleanup |

Do not raise timeouts indefinitely as a blanket fix. If a service normally takes 10 seconds to become ready and the job waits only 2 seconds, increasing the timeout makes sense. If logs show the service crashed from missing configuration, waiting longer only slows the pipeline and obscures the bug.

## 12. Practices Worth Maintaining

- Use real or compatible dependencies where tests verify protocols, SQL, transactions, or broker semantics.
- Use intentional mocks/stubs for hard-to-reproduce conditions such as timeouts, network errors, rate limits, or third-party responses.
- Pin service image versions and configs; record versions in test logs/artifacts.
- Wait for protocol-level readiness with bounded retries and overall timeouts.
- Isolate data and resources per job/test suite; support safe parallel execution.
- Use the application's real migration and bootstrap mechanisms.
- Inject credentials via a secret store, minimize permissions, and use synthetic data.
- Collect logs before cleanup and always tear down temporary resources.
- Track startup times, test durations, flaky rates, and failure causes.
- Keep local and CI setups aligned to minimize environment drift.

## 13. Backing Service Provisioning Checklist

**Before running tests**

- [ ] Identified all dependencies for each integration test group.
- [ ] Pinned service image versions and configs in code.
- [ ] Passed correct hostnames, ports, networks, and credentials to test processes.
- [ ] Configured health checks reflecting true readiness.
- [ ] Enforced bounded retries and timeouts.
- [ ] Bootstrapped migrations, topics, buckets, exchanges, or fixtures in sequence.
- [ ] Isolated data and namespaces across parallel jobs.

**After running tests**

- [ ] Stored test results and service versions for traceability.
- [ ] Collected service logs on failure.
- [ ] Cleaned up temporary containers, volumes, and data.
- [ ] Verified secrets do not appear in logs or artifacts.
- [ ] Monitored startup durations and flaky test failures.

## Conclusion

Provisioning backing services is an essential part of integration test environments. A reliable pipeline supplies the right dependencies, waits for protocol-level readiness, configures networking and credentials accurately, generates deterministic data, isolates concurrent runs, and cleans up afterward. Service containers, Docker Compose, Testcontainers, or shared environments can all work well when their lifecycles and risks are properly controlled.

When services and test data are declared as code, explicitly versioned, and backed by traceable logs, integration test results become far more reproducible between developer laptops and CI. That lets pipelines catch integration bugs early, reduce test flakiness, and deliver stronger release evidence before promoting artifacts to the next environment.
