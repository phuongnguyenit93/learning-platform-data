# Verifying Connectivity with a Simple Reactive Query

When initializing a Spring Data R2DBC application, you should verify that the application can open a connection to the database and execute an SQL statement. A direct, easy-to-understand check is running a `SELECT 1` query through `DatabaseClient`. Because this query does not depend on business tables, it validates the connection path and SQL execution capability before investigating entities or repositories.

In a reactive application, query results are represented by `Mono` or `Flux`. Creating a publisher does not mean the query has executed; the query runs when the publisher is subscribed to. Spring WebFlux consumes the publisher when handling HTTP requests, while tests can use `StepVerifier` to subscribe and assert the result.

## 1. Goal and Scope of the Check

A simple connectivity check usually answers three questions:

1. Can the application locate the R2DBC driver and create a `ConnectionFactory`?
2. Can the driver open a connection to the database using the configured URL and credentials?
3. Can the connection execute a simple SQL statement and return the result to the application?

A `SELECT 1` query is ideal for initialization because it requires no tables, entities, or seed data:

```sql
SELECT 1 AS probe_value;
```

If the query returns `1`, the application has succeeded in establishing a connection, sending a statement, and reading a result. This probe does not prove that all business tables exist, that the database user has permissions on every table, that entity mappings are correct, that transactions behave properly, or that the system handles production load. Those aspects must be tested separately.

## 2. Preparing Dependencies and the Database Driver

The application needs Spring Data R2DBC and the driver matching your database management system. The example below uses PostgreSQL and Spring Boot with Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Dependency versions are normally managed by Spring Boot dependency management or the corresponding project plugin. You do not need to specify versions for individual dependencies when using Spring Boot dependency management.

Role of each dependency:

- `spring-boot-starter-data-r2dbc` provides Spring Data R2DBC infrastructure, including `DatabaseClient` and reactive repository configuration support.
- `r2dbc-postgresql` provides the driver implementing the R2DBC SPI for PostgreSQL.
- `spring-boot-starter-webflux` lets you build endpoints returning `Mono` or `Flux`.
- `reactor-test` provides `StepVerifier` for testing publishers.

If using H2, MariaDB, Microsoft SQL Server, or another database, replace the PostgreSQL driver with the corresponding R2DBC driver. A JDBC driver cannot replace an R2DBC driver simply by changing the URL.

## 3. Connection Configuration in application.yml

Spring Boot can auto-configure a `ConnectionFactory` when a driver dependency and valid R2DBC configuration are present on the classpath.

PostgreSQL example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: ${DB_USERNAME:app_user}
    password: ${DB_PASSWORD}
```

Property meanings:

| Property | Meaning |
| --- | --- |
| `spring.r2dbc.url` | R2DBC URL identifying the driver, host, port, and database |
| `spring.r2dbc.username` | Database username |
| `spring.r2dbc.password` | Database password |

The URL has the form `r2dbc:postgresql://host:port/database`. In this example, the application connects to PostgreSQL on the local machine, port `5432`, database `customer_db`.

`DB_USERNAME` and `DB_PASSWORD` are environment variables. Set appropriate values in the application runtime environment or local development configuration. Do not commit real passwords to Git. In deployment environments, use a secret manager or your platform's secure configuration mechanism.

Some common configuration errors:

- Using a JDBC URL such as `jdbc:postgresql://...` instead of an R2DBC URL.
- Missing the corresponding R2DBC driver on the runtime classpath.
- Wrong hostname, port, database name, or credentials.
- Database not running or refusing connections from the application host.
- Referencing a non-existent environment variable, resulting in empty or unexpected configuration values.

## 4. Creating a Probe Component with DatabaseClient

`DatabaseClient` is Spring's abstraction for executing SQL reactively. It receives the Spring-configured `ConnectionFactory` and handles execution details at the R2DBC SPI layer.

Create a small service:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DatabaseConnectionProbe {

    private final DatabaseClient databaseClient;

    public DatabaseConnectionProbe(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> ping() {
        return databaseClient.sql("SELECT 1 AS probe_value")
                .map((row, metadata) ->
                        row.get("probe_value", Integer.class)
                )
                .one();
    }
}
```

The `ping()` method returns `Mono<Integer>` because the query is expected to return a single value:

1. `databaseClient.sql(...)` specifies the SQL statement to execute.
2. `map((row, metadata) -> ...)` reads the `probe_value` column from the result row and converts it to `Integer`.
3. `one()` expects at most one row and returns a `Mono`.

With `SELECT 1`, the database normally returns a single row containing the integer `1`. If there is no row, the publisher completes empty; if connection or SQL execution fails, the publisher emits an error signal.

Using the alias `probe_value` makes column retrieval clear. You can also use a column index such as `row.get(0, Integer.class)`, but reading by column name makes the code easier to understand as SQL queries grow.

## 5. Exposing a Reactive Probe Endpoint

To test manually after the application starts, you can expose an internal endpoint returning the query result. The controller returns a publisher directly to Spring WebFlux:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/diagnostics")
public class DatabaseProbeController {

    private static final Logger log =
            LoggerFactory.getLogger(DatabaseProbeController.class);

    private final DatabaseConnectionProbe probe;

    public DatabaseProbeController(DatabaseConnectionProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/database")
    public Mono<ResponseEntity<DatabaseProbeResponse>> checkDatabase() {
        return probe.ping()
                .map(value -> ResponseEntity.ok(
                        new DatabaseProbeResponse("UP", value)
                ))
                .onErrorResume(error -> {
                    log.warn("Reactive database connection check failed", error);
                    return Mono.just(
                            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                                    .body(new DatabaseProbeResponse("DOWN", null))
                    );
                });
    }
}

record DatabaseProbeResponse(String status, Integer value) {}
```

When the query succeeds, the endpoint returns HTTP 200 with a body like:

```json
{
  "status": "UP",
  "value": 1
}
```

When the query fails, the endpoint returns HTTP 503 and status `DOWN`. Error details are logged server-side for investigation; the response does not expose raw exception messages externally.

In the example above, the record is placed in the same file as the controller for brevity. In a real project, move the response record to its own file according to your project's package and source layout conventions.

Diagnostic endpoints can reveal infrastructure state. Only expose them on internal networks or protect them with appropriate authentication and authorization. If your goal is operational health checking, consider integrating Spring Boot Actuator and configuring health endpoints for your deployment environment.

## 6. Running the Application and Calling the Probe Query

Start PostgreSQL first, ensure the configured database and user exist, and then run the Spring Boot application:

```bash
./gradlew bootRun
```

Once the application is listening for HTTP traffic, call the endpoint:

```bash
curl -i http://localhost:8080/diagnostics/database
```

If connection and SQL execution succeed, the expected response is HTTP 200:

```text
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP","value":1}
```

If the database is unreachable or authentication fails, the endpoint returns HTTP 503:

```text
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"DOWN","value":null}
```

The HTTP status code and body let callers distinguish success from failure. On failure, inspect the application logs to find the root cause; do not diagnose solely from the `"DOWN"` string.

## 7. Testing the Query with StepVerifier

You do not have to hit an HTTP endpoint to verify connectivity. You can write an integration test confirming the publisher emits the expected value:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class DatabaseConnectionProbeTest {

    @Autowired
    private DatabaseConnectionProbe probe;

    @Test
    void shouldExecuteSimpleReactiveQuery() {
        StepVerifier.create(probe.ping())
                .expectNext(1)
                .verifyComplete();
    }
}
```

`StepVerifier.create(probe.ping())` subscribes to the publisher. `expectNext(1)` asserts that the emitted value is `1`, and `verifyComplete()` asserts that the publisher completes normally.

This is an integration test because Spring must build the context and connect to the configured database. When running in CI, provide an accessible test database, such as a PostgreSQL service or test container. If the database is unavailable, the test may fail before reaching the assertion step.

Do not use a mocked `DatabaseClient` as proof that the real driver and database can connect. Mocks are suited for unit-testing coordination logic; to verify URL, authentication, driver, SQL, and mapping, run integration tests against a real or compatible test database.

## 8. Understanding When the Query Actually Executes

A key characteristic of reactive programming is that a publisher typically describes work that only runs upon subscription.

Example:

```java
Mono<Integer> result = probe.ping();
// The publisher has been created, but no subscriber is consuming it yet.
```

The snippet above is not enough to conclude the connection has been tested. The publisher must be subscribed to. In a WebFlux endpoint, the framework subscribes to the publisher when processing the request and writes the result to the HTTP response. In an integration test, `StepVerifier` subscribes to the publisher.

In reactive processing flows, return the publisher so the caller controls when consumption happens:

```java
public Mono<Integer> ping() {
    return databaseClient.sql("SELECT 1")
            .map((row, metadata) -> row.get(0, Integer.class))
            .one();
}
```

Avoid calling `block()` inside reactive controllers or services:

```java
Integer value = probe.ping().block();
```

`block()` waits for the result and blocks the current thread. That forfeits non-blocking benefits and can cause thread starvation in a WebFlux request path. Also avoid manually calling `subscribe()` inside a service just to fire off a query and discard the publisher; callers cannot easily coordinate completion or handle errors that way.

If there is a controlled imperative boundary, waiting for a result may have a specific justification, but that is not how standard reactive endpoints are implemented.

## 9. Verifying an Additional Query Against a Business Table

`SELECT 1` confirms connectivity and basic SQL execution. Once that probe succeeds, separately verify access permissions and mapping for a table the application actually uses.

Repository example:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findById(Long id);
}
```

You can invoke `findById` from a service or test:

```java
StepVerifier.create(customerRepository.findById(100L))
        .expectNextMatches(customer -> customer.getId().equals(100L))
        .verifyComplete();
```

This test example assumes the table contains a row with ID `100`. If test data does not guarantee that row exists, seed the data before the test or assert a query matching your existing fixture.

If `SELECT 1` succeeds while the repository query fails, overall connectivity is likely working. In that case, check the table name, column names, schema, access privileges, generated SQL, data types, and entity mapping.

## 10. Diagnosing Errors by Cause Category

When the probe fails, categorize the error by the stage where the application could not proceed:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Driver not found or cannot create `ConnectionFactory` | Missing dependency, wrong URL scheme, or driver does not support the URL | Runtime classpath, driver, and `r2dbc:` prefix |
| Connection refused or timeout | Database not running, wrong host/port, or network blocking connection | Database status, hostname, port, firewall, and network |
| Authentication failed | Wrong username/password or restricted account | Secrets, environment variables, privileges, and auth policy |
| Database does not exist | Wrong database name in URL or database not created yet | Database name and environment configuration |
| SQL syntax or unsupported feature error | SQL incompatible with dialect or driver | SQL statement and database/driver documentation |
| Cannot read result type | Column type and requested Java type are incompatible | Metadata, Java type, and driver type conversion support |
| Publisher completes empty | Query returns no rows or mapping logic behaves unexpectedly | SQL, data, and appropriate `one()`/`first()` operator |
| Pool connection acquisition timeout | Pool exhausted or connections not released | Connection lifecycle, subscriptions, and pool configuration |

### Distinguishing Connection Errors from Query Errors

If `ConnectionFactory` cannot open a connection, focus on the driver, URL, authentication, network, and database server.

If a connection succeeds but SQL fails, check syntax errors, execution privileges, data types, or SQL features supported by the database.

If SQL executes successfully but mapping fails, check column names, Java types, and the logic inside the `map` callback.

Categorizing by layer prevents you from changing entity mappings when the real cause is a wrong password, or changing network settings when the cause is invalid SQL.

## 11. Practical Considerations for Using Probes in Real Applications

- **Do not run the probe too frequently.** Health checks may be polled periodically. Choose a reasonable interval to avoid creating unnecessary load on the database.
- **Keep the probe query small and stable.** `SELECT 1` does not scan large tables and does not depend on business data.
- **Set appropriate timeouts.** If you need to bound health check duration, configure timeouts at the publisher layer or health check infrastructure according to application policy. Overly aggressive timeouts can trigger false alarms under database load.
- **Do not expose sensitive information over HTTP.** Responses should only indicate overall status; keep technical details in internal logs.
- **Protect the endpoint.** Diagnostic endpoints should reside on an administrative network or require authentication and authorization.
- **Do not treat one successful ping as a long-term guarantee.** Connections can drop immediately after the probe; the application still needs error handling on every business query.
- **Monitor the pool if pooling is used.** A single ping may succeed while the pool is still near exhaustion under high load. Track active connections, pending acquires, and acquisition timeouts.

If using Spring Boot Actuator, the health endpoint and health contributors provide integration with monitoring systems. Configure access permissions and detail exposure based on the environment.

## 12. Quick Verification Workflow for Project Setup

You can follow this sequence after adding Spring Data R2DBC to a project:

1. Add the R2DBC starter and the right driver for your database.
2. Configure `spring.r2dbc.url`, username, and password using values for the runtime environment.
3. Start the database and verify host, port, and database are reachable.
4. Create `DatabaseConnectionProbe` with a `SELECT 1` query.
5. Return the `Mono` from a WebFlux endpoint or consume the publisher in an integration test with `StepVerifier`.
6. Confirm the result is `1` and the publisher completes normally.
7. Follow up by testing a query on a business table to verify schema, permissions, and entity mapping.
8. When errors occur, read the root cause and determine whether it belongs to configuration, network, driver, database, SQL, or mapping.

## Key Takeaways

A simple reactive query such as `SELECT 1` is a fast way to confirm a Spring Data R2DBC application can connect to the database and execute SQL. Use `DatabaseClient` to build the query and return `Mono<Integer>`; let WebFlux or `StepVerifier` subscribe to the publisher and receive the result. When the query succeeds, the value `1` confirms the basic connection path works. Afterward, still verify business tables, access rights, mappings, and behavior under load to fully validate the application.
