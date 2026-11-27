# Verifying Environment-Specific Configuration and Troubleshooting Initial Connection Errors

## 1. Why Must Connection Configuration Be Verified per Environment?

A Spring Data R2DBC application typically runs across multiple environments: a developer's local machine, Docker Compose, test environments, staging, and production. Each environment may use a different hostname, port, database, account, password, or TLS requirement. If configuration is hard-coded in source code, the application can easily connect to the wrong database or work on one machine while failing on another.

The goal of configuration management is to keep data access logic stable while connection details are supplied per deployment environment. When the application starts up or executes its first query, you need a way to verify:

- The application is using the right Spring profile and configuration source.
- The R2DBC URL points to the right host, port, and database.
- The corresponding R2DBC driver is on the classpath.
- The database is running and reachable from where the application executes.
- Username, password, access permissions, and TLS requirements match.
- Connection pool and timeouts are configured within reasonable bounds.
- Connection errors are logged with enough detail for diagnosis without exposing secrets.

This lesson focuses on verifying and troubleshooting initial connection errors in Spring Data R2DBC. Examples use PostgreSQL; when using another database engine, substitute the corresponding driver, URL scheme, and connection options.

## 2. Configuration Layers of Spring Data R2DBC

In a Spring Boot application, R2DBC connections are usually created automatically from configuration and drivers on the classpath. Core properties include:

| Property | Meaning |
|---|---|
| spring.r2dbc.url | URL specifying driver, host, port, and database |
| spring.r2dbc.username | Connection account |
| spring.r2dbc.password | Connection password |
| spring.r2dbc.properties | Additional driver-specific properties |
| spring.r2dbc.pool.* | Connection pool configuration when a compatible pool library is present |

Minimal configuration example for PostgreSQL:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

General URL format:

~~~text
r2dbc:<driver>://<host>:<port>/<database>
~~~

In the example:

- **r2dbc** is the R2DBC protocol scheme.
- **postgresql** identifies the PostgreSQL driver.
- **localhost** is the hostname as seen from the Spring Boot process.
- **5432** is the PostgreSQL port.
- **app** is the database name.

An R2DBC URL is not a JDBC URL. For example, a PostgreSQL JDBC URL normally starts with **jdbc:postgresql:**, whereas an R2DBC URL starts with **r2dbc:postgresql:**. Passing a JDBC URL by mistake into R2DBC configuration can prevent the driver from recognizing the URL.

Prefer configuring username and password as separate properties instead of embedding them directly in the URL. This separates endpoints from credentials and reduces the risk of leaking passwords when logging URLs or sharing configurations.

## 3. Managing Configuration with Spring Profiles

### 3.1. Profiles Help Separate Environment Configuration

Spring profiles allow activating a configuration set tailored to the active runtime environment. Separate configuration files can be organized such as:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-docker.yml
├── application-test.yml
└── application-prod.yml
~~~

**application.yml** holds shared configuration and environment-independent properties:

~~~yaml
spring:
  application:
    name: customer-service
  r2dbc:
    username: ${DB_USER:app}
    password: ${DB_PASSWORD}
~~~

**application-local.yml** is for the application running directly on a developer machine:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/app
~~~

**application-docker.yml** is for the application running inside the same Docker Compose network as a database service named db:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db:5432/app
~~~

When running on a personal machine, activate the local profile:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
~~~

When running the application in Docker Compose, you can set the environment variable:

~~~yaml
environment:
  SPRING_PROFILES_ACTIVE: docker
~~~

The profile name must match the configuration file suffix. For example, the docker profile causes Spring Boot to additionally load application-docker.yml.

### 3.2. Distinguishing Hostname by Application Runtime Location

The hostname is resolved from the perspective of the process opening the connection:

| Where Spring Boot runs | Commonly used hostname | Example URL |
|---|---|---|
| Directly on dev machine, database publishes port to host | localhost | r2dbc:postgresql://localhost:5432/app |
| In a container sharing a Compose network with service db | db | r2dbc:postgresql://db:5432/app |
| In Kubernetes | Database Service DNS | Depends on namespace and Service |
| On another server | Reachable DNS or IP | Per environment endpoint |

**localhost always means the current machine or network namespace.** Inside an application container, localhost points to the application container itself, not to the PostgreSQL container. In a Compose network, the service name is the appropriate hostname for containers to communicate.

If the application runs on the host but PostgreSQL does not publish its port, localhost still cannot reach the database just because the container is running. Check port mappings or use an explicitly designed network path.

### 3.3. Preventing Production from Accidentally Using Local Configuration

Do not make the local profile the default across all deployment environments. Specify the profile explicitly where the application runs and confirm that value in startup logs. Production configuration should be supplied by the deployment platform or a secret manager, with least-privilege access.

Avoid committing production passwords to application-prod.yml or compose files. Configuration files can hold placeholders while real values are supplied via secrets or environment variables at runtime.

## 4. Externalized Configuration and Environment Variables

Spring Boot supports externalized configuration: the same artifact can receive configuration from files, environment variables, Java system properties, or command-line arguments. As a result, you do not need to rebuild the application just to change a database endpoint.

Example application.yml using environment variables:

~~~yaml
spring:
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/app}
    username: ${DB_USER:app}
    password: ${DB_PASSWORD}
~~~

Meaning of the expressions:

- **${R2DBC_URL:...}** uses R2DBC_URL if provided; otherwise it uses the default local URL.
- **${DB_USER:app}** uses DB_USER or falls back to app.
- **${DB_PASSWORD}** requires DB_PASSWORD to be provided; if missing, placeholder resolution fails when configuration loads.

You can use environment variable names under Spring Boot's relaxed binding rules:

| Property | Environment variable |
|---|---|
| spring.r2dbc.url | SPRING_R2DBC_URL |
| spring.r2dbc.username | SPRING_R2DBC_USERNAME |
| spring.r2dbc.password | SPRING_R2DBC_PASSWORD |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |

Example running a JAR with environment variables on Linux or macOS:

~~~bash
SPRING_PROFILES_ACTIVE=local \
SPRING_R2DBC_URL=r2dbc:postgresql://localhost:5432/app \
SPRING_R2DBC_USERNAME=app \
SPRING_R2DBC_PASSWORD=local-password \
java -jar app.jar
~~~

On PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SPRING_R2DBC_URL = "r2dbc:postgresql://localhost:5432/app"
$env:SPRING_R2DBC_USERNAME = "app"
$env:SPRING_R2DBC_PASSWORD = "local-password"
java -jar app.jar
~~~

Values from environment variables, system properties, or command-line arguments can override values in configuration files according to Spring Boot's precedence order. Therefore, when the URL in application.yml looks right but the application still connects to the wrong host, check environment variables, IDE run arguments, container settings, and the active profile. Do not look at a single YAML file and assume it holds the final value.

### 4.1. Docker Compose's .env File Does Not Configure a Host Java Process Automatically

Docker Compose reads the **.env** file to interpolate values in compose.yaml. Having this file does not mean a Java process launched directly from an IDE automatically picks up those variables.

For example, Compose might use:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=local-dev-password
~~~

And pass variables into the container:

~~~yaml
services:
  app:
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://db:5432/${DB_NAME:-app}
      SPRING_R2DBC_USERNAME: ${DB_USER:-app}
      SPRING_R2DBC_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD}
~~~

If running the application from IntelliJ IDEA, Eclipse, or a terminal on the host, configure environment variables separately in the Run Configuration or shell. This is a common reason an application in a container connects while the same application run from an IDE reports a missing password or wrong URL.

### 4.2. Checking Loaded Configuration

You can confirm active profiles via Spring Boot's startup logs. When needed, use Actuator or internal diagnostics to inspect resolved properties, but protect endpoints and never expose passwords externally.

Do not print all environment variables, application properties, or connection URLs containing credentials to logs. When logging configuration for diagnostics, log only non-sensitive fields such as profile, driver, hostname, port, and database name; mask username if policy requires, and never log passwords.

## 5. Verifying Dependencies and the R2DBC Driver

Having the right URL alone is not enough. The corresponding driver must be on the runtime classpath. For PostgreSQL, Gradle dependencies typically look like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Spring Boot dependency management should manage compatible versions across Spring Data, Spring Framework, Reactor, and the driver. Avoid mixing arbitrary standalone versions without checking the compatibility matrix.

If using MySQL, replace it with a suitable MySQL R2DBC driver and the corresponding URL scheme. You cannot use the PostgreSQL driver to connect to MySQL merely by changing the hostname.

Some signs of a missing or wrong driver:

- An error indicating no driver was found matching the URL.
- ConnectionFactory is not created or no ConnectionFactory bean exists.
- The application reports a missing ConnectionFactory when creating repositories or DatabaseClient.
- The URL uses the JDBC scheme while the application requires R2DBC.

Inspect runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows using the Gradle Wrapper:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Look for your database's R2DBC driver in the output. If the dependency is only in test runtime or excluded from runtimeClasspath, the packaged application may fail to connect even if tests pass inside the IDE.

## 6. Layer-by-Layer Connection Verification Process

When a connection fails, verify from the outer layer inward. Each step validates a specific hypothesis and narrows the scope of the failure.

~~~text
Application configuration
       |
       v
Right profile and resolved properties?
       |
       v
Right R2DBC driver and URL scheme?
       |
       v
Hostname resolvable?
       |
       v
Port reachable?
       |
       v
Database running and accepting connections?
       |
       v
Database / username / password valid?
       |
       v
TLS, permissions, and driver options suitable?
       |
       v
ConnectionFactory / pool working?
       |
       v
SELECT 1 query succeeds
~~~

### 6.1. Checking Which Configuration the Application Uses

Confirm:

- Does the active profile match the environment?
- Which file or environment variable supplies the R2DBC URL?
- Are IDE run parameters overriding the URL?
- Does the app container receive the SPRING_R2DBC_* variables?
- Do database name, user, and port match the provisioned database?

In particular, match the hostname against where the application runs. localhost and a Compose service name cannot be swapped arbitrarily.

### 6.2. Checking DNS and Network

If using a hostname like **db**, check whether the application is on the same network and can resolve that name. You can open a shell inside the app container to verify:

~~~bash
docker compose exec app sh
~~~

Depending on what tools are installed in the image, you can use **getent hosts db**, **nslookup db**, or **ping db**. Not every production image includes these utilities. A failed ping alone also does not prove the database is unreachable, because ICMP may be blocked.

If the application runs on the host, check the published port. In PowerShell:

~~~powershell
Test-NetConnection localhost -Port 5432
~~~

On Linux you can use:

~~~bash
nc -vz localhost 5432
~~~

A port check only confirms TCP connectivity can open; it does not confirm the database, account, or permissions are correct.

### 6.3. Checking the Database with an Independent Client

With PostgreSQL running in Compose, test connecting directly inside the container:

~~~bash
docker compose exec db pg_isready -U app -d app
docker compose exec db psql -U app -d app -c "SELECT 1;"
~~~

If psql inside the container cannot connect either, inspect the database status and logs before investigating Spring. If psql works inside the container while the app on the host cannot connect, focus on port mapping, firewall, and hostname. If psql from the host succeeds while Spring fails, focus on URL, driver, credentials, TLS, and runtime configuration.

When testing with psql from the host, use the exact hostname and port the application expects to use:

~~~bash
psql "host=localhost port=5432 dbname=app user=app" -c "SELECT 1;"
~~~

This command may prompt for a password depending on configuration. Do not pass the password directly on the command line, as it can show up in process lists or shell history.

### 6.4. Checking with DatabaseClient

Once network and authentication layers are confirmed, you can run a simple query through Spring Data R2DBC itself to verify the application's actual connection path.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DatabaseConnectionProbe {

    private final DatabaseClient databaseClient;

    public DatabaseConnectionProbe(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> checkConnection() {
        return databaseClient.sql("SELECT 1 AS value")
                .map((row, metadata) -> row.get("value", Integer.class))
                .one();
    }
}
~~~

The method returns **Mono<Integer>**. The query only executes when the publisher is subscribed to. You can use it in an integration test to verify the application connects using its actual loaded configuration.

~~~java
@SpringBootTest
class DatabaseConnectionTest {

    @Autowired
    DatabaseConnectionProbe probe;

    @Test
    void shouldConnectToDatabase() {
        StepVerifier.create(probe.checkConnection())
                .expectNext(1)
                .verifyComplete();
    }
}
~~~

The test requires a real database or Testcontainers and proper test configuration. Do not turn a check query into a detached self-subscribed task inside a business service. For operational checks, prefer the framework's built-in health indicator or a controlled readiness mechanism.

## 7. Common Initial Connection Errors

| Symptom / message | Common causes | How to check and fix |
|---|---|---|
| Driver not found or cannot create ConnectionFactory | Missing R2DBC driver, wrong URL scheme, or dependency missing at runtime | Check runtimeClasspath, URL must use R2DBC scheme and right database driver |
| Connection refused | Database not running, wrong port, port not published, or process bound to another address | Check container, healthcheck, port mapping, and test TCP connectivity |
| UnknownHostException or unresolvable host | Wrong hostname, app and database not on same network, or DNS not ready | Use service name within the same Compose network; check DNS and networking |
| Connection timed out | Firewall, network route, wrong endpoint, database unresponsive, or pool waiting too long | Check network, security groups, database load, and connection acquire time |
| password authentication failed | Wrong user/password or volume initialized with old credentials | Confirm runtime credentials; update database password if preserving data |
| database does not exist | Wrong database name or database not yet created | Check database name and bootstrap process |
| SSL / TLS handshake failed | Client and server disagree on TLS mode, certificate, or trust chain | Check driver SSL options, CA, and environment certificates |
| too many connections | Total connections from app and other clients exceed database limit | Check pool max-size, instance count, and server connection limit |
| Connection validation failed | Pooled connection is stale or server closed the connection | Check max-idle-time, max-life-time, validation, and timeouts |
| App starts up but first query fails | Connections are opened lazily or no query forced opening a connection yet | Run a readiness check or integration test that executes an actual query |

Exact error messages vary by driver and version. Read both the root cause exception and the nested exception chain rather than looking only at the top log line from Spring.

## 8. Handling Specific Error Groups

### 8.1. Connection refused

This error usually happens when the TCP client cannot open a connection to the configured address and port. Typical causes:

- PostgreSQL container is not running or still initializing.
- Application uses the wrong host port.
- Database is only exposed inside the Compose network while the app runs on the host.
- App runs inside a container while using localhost.
- Database is not bound to or listening on the required interface.

Check step by step:

~~~bash
docker compose ps
docker compose logs --tail=100 db
docker compose port db 5432
~~~

If the app runs in the Compose network, use the service hostname and internal port. If the app runs on the host, use the published port. For startup ordering, healthchecks and depends_on condition: service_healthy help avoid connecting too early, though the application still needs to handle database restarts after startup.

### 8.2. UnknownHostException

Hostname resolution failures are typically signs of a wrong DNS name or network environment mismatch.

For example, the URL **r2dbc:postgresql://db:5432/app** only makes sense when the app process can resolve the db service name inside the Compose network. If running from an IDE on the host, the OS usually does not know the db hostname. Use the hostname published to the host, typically localhost.

Conversely, a localhost URL inside the app container points to the app container itself. Change the URL per profile or environment variable to match where the process runs.

### 8.3. Wrong Username or Password

Check the value Spring actually receives, not just the value in a config file. IDE environment variables, container secrets, or command-line flags can override properties in YAML.

With the official PostgreSQL image, POSTGRES_USER and POSTGRES_PASSWORD are used when initializing an empty data directory. If a named volume already contains data, changing these variables does not automatically change an existing user's password. You can update the password via SQL when logged in with sufficient privileges:

~~~sql
ALTER USER app WITH PASSWORD 'new-local-password';
~~~

Then update the secret used by the application. Do not place real passwords in migrations, source code, or logs.

### 8.4. Database Does Not Exist

Verify the database name in the URL. You can list databases using psql:

~~~sql
\l
~~~

In Docker Compose, the PostgreSQL image's POSTGRES_DB variable only creates the default database when initializing a fresh data directory. If the volume already exists, changing POSTGRES_DB does not create a new database automatically. Create the database using an account with appropriate privileges or run a controlled bootstrap procedure.

### 8.5. TLS and Certificates

Staging or production environments may require TLS connections. Do not disable certificate verification just to get a connection working. Check:

- Does the server require TLS?
- Which SSL mode is the driver using?
- Does the client trust the server's CA?
- Does the hostname match the information in the certificate?
- Is the certificate still valid and is the certificate chain complete?

SSL properties and URL syntax depend on the driver. Consult documentation for the exact driver version instead of copying JDBC driver options over to R2DBC.

## 9. Verifying Connection Pool and Timeouts

Non-blocking I/O does not mean an application can open unlimited connections. The database still has connection and resource limits. If the application uses an R2DBC pool, balance pool size against instance count, workload, and database limits.

Common parameters to watch:

| Parameter | Meaning |
|---|---|
| initial size | Initial number of connections created in the pool |
| max size | Maximum number of connections in the pool |
| max idle time | Time a connection may remain idle before eviction |
| max life time | Maximum lifetime of a connection |
| max acquire time | Maximum wait time to acquire a connection from the pool |
| validation | Mechanism for checking whether a connection is still usable |

Property names and support may vary across Spring Boot and r2dbc-pool versions. Only configure properties supported by your active version and when the pool library is present on the runtime classpath.

Illustrative pool configuration example:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
~~~

This configuration is not a universal recommendation for all applications. Pool max-size must account for application replica count. For instance, with 4 instances each allowed up to 10 connections, potential total connections from the application alone reach 40, excluding migration jobs, admin tools, and other clients.

If logs show requests waiting long to acquire a connection, distinguish between:

- Database slow at processing queries.
- Pool out of available connections.
- Old connections needing replacement.
- Transactions or publishers holding connections longer than expected.

Do not simply increase max-size when encountering timeouts. If the database is already near its limit, enlarging the pool can worsen the situation. Observe active connection count, acquire time, query time, and server load.

## 10. Distinguishing Connection Errors from Reactive Pipeline Errors

An application may have valid connection configuration yet still execute no queries because the publisher has not been subscribed to. Reactor uses a lazy model: creating a **Mono** or **Flux** normally describes work without necessarily performing I/O yet.

For example:

~~~java
Mono<Customer> customer = customerRepository.findById(42L);
~~~

The snippet above creates a publisher. If nothing subscribes or the framework does not consume that publisher, the query may not run. In WebFlux, the framework subscribes to the publisher returned by the controller. In tests, StepVerifier subscribes when verification starts.

Do not call **block()** or **subscribe()** casually just to force a query to run. Return the publisher to the calling layer or use appropriate testing tools. Calling block on an event-loop thread can stall the reactive pipeline.

One sign to watch out for is an application starting up cleanly while the first query fails. This can happen because connections are opened lazily on the first data operation. Clean startup only confirms the application context was created; it does not necessarily prove the database was reached successfully.

## 11. Readiness, Retries, and Resilience

### 11.1. Readiness Differs from a Running Process

A running Java process does not mean the application is ready to serve business traffic. If an API requires a database to handle requests, readiness should reflect reachability of required dependencies.

Spring Boot Actuator can provide an R2DBC health indicator when matching dependencies and auto-configuration are enabled. You can use the health endpoint in deployment platforms, but secure the endpoint and avoid publicly exposing connection details or internal information.

Liveness and readiness serve different purposes:

- **Liveness** answers whether the process is still alive or needs to be restarted.
- **Readiness** answers whether the instance is eligible to receive requests yet.

A temporary database disconnect does not always mean the process needs a restart. The appropriate response depends on architecture, reconnect capability, and operational policy.

### 11.2. Retries Must Be Bounded and Error-Classified

Certain transient failures such as network interruptions or a restarting database can be retried. However, retries cannot fix permanent configuration errors such as a wrong password, wrong hostname, or missing driver.

When designing retries:

- Bound retry count and total retry duration.
- Use backoff to avoid triggering a sudden storm of reconnects.
- Retry only errors classified as transient.
- Ensure retried operations are safe or idempotent.
- Track retry counts and failure reasons.

Illustrative example of a read operation with retry:

~~~java
return customerRepository.findById(customerId)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientDatabaseError));
~~~

The **isTransientDatabaseError** method should be implemented based on the driver's actual exception types and application policy. Do not blindly retry every exception; validation errors, invalid SQL, or authentication errors usually will not disappear after a few attempts.

## 12. Logging and Observing Failures Without Exposing Sensitive Information

When investigating connections, logs should help identify the environment, endpoint, and error type. Useful details to record:

- Active profile.
- Driver and driver version.
- Hostname, port, and database name if policy allows.
- Error timestamp, request ID, or trace ID.
- Exception type and SQL state if supplied by the driver.
- Connection wait duration and query execution time.

Never log passwords, tokens, connection URLs containing credentials, or all environment variables. Nor should you enable bind-parameter logging in production if parameters might contain personal data or secrets.

You can distinguish ConnectionFactory initialization errors, pool acquisition errors, authentication errors, and SQL execution errors by inspecting the exception cause chain. Outer log messages often only say a repository operation failed; deeper root causes hold socket, DNS, authentication, or driver details.

## 13. Troubleshooting Checklist When the Application Cannot Connect

When a new environment cannot connect to the database, work through this order:

1. **Profile:** verify SPRING_PROFILES_ACTIVE and matching configuration files.
2. **Properties:** check resolved R2DBC URL, username, and password; check whether environment variables or run arguments override files.
3. **Driver:** confirm the database's R2DBC driver is on runtimeClasspath and the URL uses the right scheme.
4. **Hostname:** use localhost from the host or service DNS from within the same container network.
5. **Port:** verify the database is listening and port mappings/firewalls permit connections.
6. **Database:** confirm the database exists and the server is ready.
7. **Credentials:** test with a standalone database client using the same host, port, database, and user.
8. **TLS:** verify SSL mode and trust chain according to environment requirements.
9. **Pool:** check pool dependency, connection limits, acquire timeout, and stale connections.
10. **Reactive execution:** ensure publishers are consumed by the framework or a valid subscriber.
11. **Readiness:** run a check query through the application itself or via a health indicator.
12. **Observability:** inspect root causes and logs with a correlation ID; redact all secrets before sharing.

When modifying configuration values, change only one group of factors at a time and re-test. This helps pinpoint the real cause instead of changing multiple settings at once and not knowing which change fixed the problem.

## 14. Conclusion

Verifying R2DBC configuration per environment is the process of confirming the active profile, resolved properties, driver, URL, hostname, port, database, credentials, TLS, and connection pool. Different environments often need different endpoints; in particular, localhost on the host and localhost inside a container mean different things.

When encountering initial connection errors, diagnose layer by layer from configuration down to networking, the database, authentication, and actual queries. Testing with a standalone database client separates infrastructure issues from Spring issues; running a simple query via DatabaseClient or a health indicator verifies the exact connection path the application uses. Combining externalized configuration, proper secret management, readiness checks, and bounded retries makes a Spring Data R2DBC application easier to deploy and operate.
