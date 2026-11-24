# Distinguishing Between a Running Container and a Ready Service

## Container Running Does Not Mean the Service Is Ready

In integration testing, Testcontainers or Docker Compose commonly starts a database, message broker, cache, or HTTP service for a Spring application to connect to. A container entering the running state only indicates that the container's main process has started from Docker's perspective. It does not prove that the service inside has finished initializing and can handle requests.

For example, PostgreSQL may have a running process while still recovering data or initializing the database. Redis may have started its process without finishing data loading. An HTTP application may have bound a port before finishing connection pool creation, running migrations, or loading business configuration.

If a test starts sending requests the moment the container is running, the outcome can depend on machine speed, CI load, or image startup time. Tests may fail intermittently with connection refused, timeouts, or database-not-ready errors.

Distinguish the following status levels:

| Observation level | What it proves | What it does not yet prove |
| --- | --- | --- |
| Container created | Docker created the container | Process has started |
| Container running | Main process is running | Service has opened its port or finished initializing |
| Port listening | A TCP listener exists on the checked port | Protocol and application can handle requests |
| Health check succeeded | Configured probe reports the service healthy by its criteria | Every API or business flow needed by the test works |
| Readiness probe succeeded | Service declares itself ready to accept the traffic type checked by the probe | External dependencies excluded from the probe are also ready |
| Business check succeeded | One specific behavior of the service works | All other execution paths work |

The test's goal is to wait for the exact readiness level it requires. A test that only verifies TCP connectivity can use a port check. A test querying a database must wait until the database accepts connections and has the required schema. A test calling another service's API should wait for a health endpoint or a probe demonstrating that the service can actually process requests.

## Readiness Is a Service Condition, Not a Docker State

Readiness is a criterion defined by the system. A probe should reflect the minimum condition required for the service to accept the types of requests the test will send.

For a database, checks may include:

- TCP port is open.
- Database accepts connections and authentication.
- The database/schema required by the application exists.
- Required migrations and initialization data are complete.

For an HTTP service, checks may include:

- HTTP port is listening.
- Health endpoint returns a success status.
- Readiness health group reports a ready state.
- A minimal business endpoint can handle requests with required dependencies.

Not every test needs a deep business probe. Overly deep probes can create circular dependencies: service A waits for service B, and service B waits for service A, so neither ever reports ready. Choose a short, stable probe that checks strictly required dependencies.

### Distinguishing Liveness and Readiness

These two concepts commonly appear in health endpoints:

- **Liveness** answers whether the process is still alive and able to continue running. If liveness fails repeatedly, the platform may restart the container.
- **Readiness** answers whether the service can accept traffic yet. If readiness fails, the platform can temporarily stop routing traffic to the service without restarting it.

A service can pass liveness while failing readiness during initialization or when losing connection to a required dependency. Therefore, if the goal is waiting for an API to become ready for requests, a readiness probe is usually more appropriate than a liveness probe.

In Spring Boot Actuator, health groups such as readiness can be exposed via the corresponding endpoint when enabled and configured. Paths, access permissions, and response bodies depend on application configuration. Tests must use the actual enabled endpoint; do not assume every application exposes a readiness path out of the box.

## Testcontainers: Waiting with WaitStrategy

Testcontainers provides wait strategies to wait for readiness conditions after a container starts. You can configure a wait strategy on `GenericContainer` via `waitingFor(...)`.

### Waiting for a Listening Port

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forListeningPort())
        .withStartupTimeout(Duration.ofSeconds(60));
~~~

`Wait.forListeningPort()` waits for the exposed port to have a TCP listener. It is useful when the test only needs to know the process has opened the port and can accept connections at the TCP layer.

An open port does not prove an HTTP endpoint returns valid responses. An application may open its connector before finishing handler initialization, migrations, or dependency setup. If the test needs to call an HTTP API, consider an HTTP wait strategy.

### Waiting for an HTTP Endpoint

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
                Wait.forHttp("/actuator/health/readiness")
                        .forPort(8080)
                        .forStatusCode(200)
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

`Wait.forHttp(...)` sends an HTTP probe to the container and waits for a response matching the condition. In this example, the container is considered ready only when the readiness endpoint returns HTTP 200.

For this to work, the image must run an application with that endpoint, the endpoint must be exposed, and the probe must be reachable. If Actuator is protected by authentication or bound to a different interface, configure the probe accordingly or provide a dedicated health endpoint for the test environment.

A plain HTTP 200 may also not be enough. If an endpoint always returns 200 even when the health status is DOWN, configure the probe or strategy to check the response body in accordance with the application's health contract. Do not rely solely on the HTTP status code if the body carries the state you need to verify.

### Waiting for an Initialization Log Message

Some images emit a stable log line when the service becomes ready:

~~~java
GenericContainer<?> database = new GenericContainer<>(
        DockerImageName.parse("example/database:1.0"))
        .withExposedPorts(5432)
        .waitingFor(
                Wait.forLogMessage(".*ready for connections.*\\n", 1)
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

`Wait.forLogMessage(...)` waits for a log pattern to appear the specified number of times. This can be a good option when an image lacks a health endpoint but emits reliable initialization logs.

Logs are only signals emitted by the application. A "Started" line may appear before business dependencies are ready, and log formats can also change across image versions. Use logs as a readiness signal only when that line genuinely marks the condition the test needs and remains stable across supported versions.

### Using a Built-in Docker Healthcheck

If an image declares a Docker `HEALTHCHECK`, Testcontainers can wait for its health status via:

~~~java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.0"))
        .waitingFor(Wait.forHealthcheck())
        .withStartupTimeout(Duration.ofSeconds(90));
~~~

`Wait.forHealthcheck()` relies on the healthcheck defined in the image or container configuration. If the image has no `HEALTHCHECK`, this strategy has no probe to evaluate.

The healthcheck must test the right readiness condition. A command that only checks whether a process exists or a port is open may report healthy too early. Inspect the image's `HEALTHCHECK` definition before trusting it to represent request-serving capability.

### Waiting for a Command to Succeed

If an image includes an internal check command, Testcontainers can wait for the command to succeed:

~~~java
GenericContainer<?> database = new GenericContainer<>(
        DockerImageName.parse("example/database:1.0"))
        .waitingFor(
                Wait.forSuccessfulCommand("database-cli", "ping")
                        .withStartupTimeout(Duration.ofSeconds(90))
        );
~~~

The command runs inside the container. It is useful when a service has its own CLI or health utility and does not need to expose a public endpoint. The command must exit with a success code when readiness is reached; avoid commands that only check the process if the test needs real database connections.

## Startup Check and Wait Strategy Answer Two Different Questions

Testcontainers separates checking whether a container has started under Docker's lifecycle from waiting for the service to be ready under a `WaitStrategy`.

- A startup check determines whether the container enters the running state according to the startup strategy.
- A `WaitStrategy` determines whether the service condition required by the test has been met, such as an open port, an HTTP health 200, or a ready log message.

A container can pass the startup check while not yet passing the readiness wait. This is normal: Docker has started the process, while the application inside is still initializing.

When configuring Testcontainers, do not treat `start()` returning as an ambiguous signal. `start()` completes after both startup and wait strategy conditions are satisfied. If the container does not reach readiness within the startup timeout, Testcontainers fails rather than letting the test continue sending requests to an unready service.

## Example Spring Integration Test with an HTTP Service Container

A test can start a service container and wait for its readiness endpoint before using the host and mapped port:

~~~java
static final GenericContainer<?> catalogService =
        new GenericContainer<>(DockerImageName.parse("example/catalog:1.0"))
                .withExposedPorts(8080)
                .waitingFor(
                        Wait.forHttp("/actuator/health/readiness")
                                .forPort(8080)
                                .forStatusCode(200)
                )
                .withStartupTimeout(Duration.ofSeconds(90));

@BeforeAll
static void startCatalogService() {
    catalogService.start();
}

@AfterAll
static void stopCatalogService() {
    catalogService.stop();
}

@Test
void callsCatalogAfterItIsReady() {
    String baseUrl = "http://" + catalogService.getHost()
            + ":" + catalogService.getMappedPort(8080);

    // Use baseUrl to create an HTTP client and perform the request under test.
}
~~~

This example shows a manual lifecycle; in a JUnit 5 project, you can use the Testcontainers extension with `@Testcontainers` and `@Container` to manage start/stop. Either way, the container must finish its readiness wait before the test issues business requests.

If the service is a dependency of a Spring Boot application under test, ensure the container is started and ready before the `ApplicationContext` builds clients or makes its first connection. You can supply URLs/credentials via `DynamicPropertySource` or use `ServiceConnection` in supported Spring Boot versions. Property passing does not replace the readiness wait: it only provides connection details.

## Databases: Open Port, Accepting Connections, and Ready Schema

Databases clearly illustrate the difference between readiness levels. Suppose a test uses PostgreSQL:

1. Container running: the PostgreSQL process is running.
2. Port 5432 listening: a TCP connection can be opened.
3. Database accepting connections: PostgreSQL is ready to accept login commands.
4. Schema ready: migrations have created the tables and constraints the application needs.
5. Fixtures ready: seed data relied upon by the test has been loaded.

Tests querying repositories need at least levels 3 and 4; tests requiring seed data also need level 5. Waiting only for an open port may not be enough.

With a PostgreSQL image, a Docker healthcheck can commonly use `pg_isready` to verify the server accepts connections:

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 30
      start_period: 5s
~~~

`pg_isready` checks whether the PostgreSQL server accepts connections. It does not prove that application migrations have run or required tables exist. Migrations are typically a separate initialization step; tests must wait for that step to finish before querying repositories.

A clean way to organize this is to run migrations as an awaitable setup step before starting tests. If migrations run inside the Spring `ApplicationContext`, wait for context startup to complete before executing test methods. If migrations run in a separate container/job, wait for that job to exit successfully.

## Docker Compose: `depends_on` and `service_healthy`

In Docker Compose, the short `depends_on` syntax primarily defines service startup order. It does not inherently prove that the dependency is ready to accept requests.

If a dependent service requires a healthcheck before another service starts, use the long `depends_on` syntax with the `service_healthy` condition:

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 30

  application:
    image: example/application:1.0
    depends_on:
      database:
        condition: service_healthy
~~~

Compose waits for the database healthcheck to pass before creating the `application` service according to this dependency relationship. The healthcheck still must reflect real readiness; if it only checks the process, Compose only waits for the process.

Compose also supports the `service_completed_successfully` condition for job-style dependencies that run to completion, such as a migration container. This fits when the application should start only after schema preparation finishes.

When running tests with Compose, distinguish:

- Compose has created or started the service.
- The service's healthcheck has succeeded.
- The migration job has exited successfully.
- The application has finished initializing and is ready to receive traffic.

These signals can occur at different times. Tests should only start once their own required conditions are met.

## Choosing the Right Probe for the Dependency

| Dependency or target | Usually suitable probe | Limitation to keep in mind |
| --- | --- | --- |
| Simple TCP service | Listening port | Only verifies TCP connectivity |
| HTTP service | HTTP endpoint | Requires a meaningful, reachable readiness endpoint |
| Spring Boot service | Actuator readiness health group | Endpoint must be enabled/exposed and dependency health configured properly |
| Database | CLI healthcheck or real query | Server accepting connections does not prove schema/migrations are ready |
| Message broker | Healthcheck or broker command/protocol probe | An open port does not prove the broker accepts publish/consume |
| Cache | Protocol ping/auth probe | Ping does not necessarily confirm keyspace or fixture data |
| Service without a health endpoint | Reliable startup log or internal command | Log/command may not reflect business readiness |
| Migration job | Wait for process/job to complete successfully | Job exit 0 does not prove another test's seed data is ready |

A probe should be fast, have a timeout, produce deterministic results, and have minimal side effects. Avoid probes that write business data or create new resources on every call.

## Timeouts and Readiness Failures Must Be Handled Explicitly

Every readiness wait should have a finite startup timeout. If a service does not become ready, the test must fail with enough information to diagnose the root cause instead of hanging indefinitely.

When a timeout occurs, check:

- Is the container actually running or has it exited?
- Does the probed port match the port inside the container?
- Are the HTTP path, protocol, status code, and authentication accurate?
- Is the healthcheck declared in the image or Compose file?
- Is the service waiting on another dependency, migration, or seed data?
- Do container logs reveal a configuration error, missing environment variable, or initialization failure?

Do not mechanically increase timeouts to mask configuration errors. If a service genuinely needs more startup time in CI, adjust the timeout with justification, while ensuring the probe still checks a real readiness condition.

## Why `Thread.sleep` Is Not a Readiness Check

A test can easily end up written like this:

~~~java
container.start();
Thread.sleep(5_000);
callService();
~~~

This snippet assumes the service is always ready within five seconds. On a fast machine, the test wastes time; on slow CI, five seconds may still be insufficient. Sleeping does not check whether the service is actually ready.

`WaitStrategy` works in the opposite direction: it repeatedly checks a meaningful condition until the condition passes or times out. The test proceeds as soon as readiness is reached, instead of waiting out a fixed duration.

If writing custom polling, use a bounded deadline and interval, handle transient exceptions such as connection refused, and throw the final failure with its cause when time expires. Never write an infinite loop or swallow all exceptions while continuing to wait.

## Common Mistakes

### Checking Only `container.isRunning()`

`isRunning` only indicates the container is running according to Docker. It does not prove the database, broker, or HTTP server is ready to handle requests. Use a probe tailored to the service.

### Waiting Only for an Open Port

A port can open before the application finishes initialization. For HTTP services, wait for a readiness endpoint; for databases, verify the server accepts connections and the required schema is ready.

### Using a Liveness Endpoint as Readiness

A passing liveness check may only prove the process is alive. If the service is still initializing or a required dependency is not connected yet, readiness may not be satisfied.

### Using an Overly Shallow Healthcheck

A healthcheck that only checks a process or port can report healthy too early. Determine the exact condition the healthcheck verifies and whether that condition is sufficient for the test.

### Forgetting Migrations and Seed Data

A database accepting connections does not mean tables or test data exist yet. Wait for the migration/seed step to finish separately.

### Setting Timeouts Too Short or Infinite

Timeouts that are too short cause failures on slow CI environments; infinite timeouts hang the pipeline. Choose finite limits based on actual startup times and keep probes meaningful.

### Using `Thread.sleep` Instead of Readiness Polling

Sleeping depends on environment speed and proves no required condition. Use `WaitStrategy`, a Docker healthcheck, or deadline-based polling.

### Thinking Short `depends_on` Waits for a Healthy Service

Short `depends_on` is not a health gate. Use a healthcheck and the `service_healthy` condition when Compose needs to wait for a dependency to become ready.

## Workflow for Setting Up Reliable Test Infrastructure

1. Identify what state the test's first action requires from the dependency: open port, protocol acceptance, ready API, migrated schema, or ready seed data.
2. Choose a probe that accurately reflects that state: listening port, HTTP, healthcheck, log, or command.
3. Declare the probe with a finite startup timeout in Testcontainers or Docker Compose.
4. Ensure containers and dependencies are started before the Spring `ApplicationContext` or test clients use them.
5. Wait for migrations and fixture initialization separately if the database healthcheck does not cover them.
6. On timeout, collect container state, logs, and probe results to find the root cause.
7. Execute business requests or queries only after the required readiness condition has passed.
8. Stop and clean up containers according to the test lifecycle so runs do not leave unintended resources behind.

Container running is a lifecycle signal; service ready is an operational condition that must be verified. When tests define readiness using a probe suited to the dependency in use, the test suite avoids random startup failures and clearly separates running infrastructure from a service genuinely capable of serving requests.
