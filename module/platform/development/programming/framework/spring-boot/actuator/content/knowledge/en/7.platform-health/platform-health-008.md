# Identifying Auto-Configured Health Indicators for Database, Redis, Disk Space, and Related Services

## 1. Where does a health result come from?

An application starting successfully does not guarantee it can use its database, connect to Redis, or still have enough space to write files. In Spring Boot Actuator, a health indicator executes a check with a defined scope and returns a status such as `UP` or `DOWN`. That gives operators additional evidence about the resources the application depends on.

For example, an order management application might need three distinct answers:

- `db`: can the application obtain and validate a JDBC connection to the database?
- `redis`: can the application perform a Redis check using its active connection configuration?
- `diskSpace`: does the filesystem at the chosen path still have sufficient usable space?

Each answer is meaningful only within the bounds of that check. `db=UP` does not prove all tables and business queries work; `redis=UP` does not prove all cached data is accurate; `diskSpace=UP` does not prove every directory is writable.

This lesson uses Spring Boot **3.3.x**, with a standalone example pinned to **3.3.0**, running on **JDK 21**. The goal is to know which indicators can be auto-configured, why one is present or absent, and how to read results. Designing custom indicators and probe policies for orchestrators are separate topics.

### Terms to connect together

| Term | Role |
| --- | --- |
| `HealthIndicator` | Performs a check and returns `Health`. |
| `HealthContributor` | Component participating in the health tree; may be an indicator or a composite. |
| `CompositeHealthContributor` | Groups multiple child components, such as multiple `DataSource`s under the `db` branch. |
| `HealthContributorRegistry` | Registry for looking up registered components by name. |
| Health endpoint | Reads the health tree and exposes results; default HTTP path is `/actuator/health`. |

Picture the sequence: **resource configured → health component registered → check runs → status aggregated → allowed information displayed**. A missing link produces different symptoms.

## 2. "Auto-configured" is conditional

Actuator does not scan the network to discover MySQL, Redis, or mail servers on its own. It relies on classes on the classpath, existing beans, and application configuration.

For an external resource, four layers of conditions can be traced:

1. **Libraries:** the application has the appropriate integration library, usually brought in via a starter.
2. **Resource bean:** Spring has created a bean such as `DataSource`, `RedisConnectionFactory`, or the corresponding bean.
3. **Health condition:** the indicator is enabled and auto-configuration has not yielded to an application-provided bean.
4. **Observation:** the health endpoint is exposed, the request is authorized, and visibility policy permits seeing components or details.

The fourth layer governs what users see over HTTP; it does not replace the three layers that create the indicator. Simply adding `management.health.redis.enabled=true` will not create a Redis client when the library or connection bean is missing.

An example from Spring Boot 3.3's JDBC configuration: `DataSourceHealthContributorAutoConfiguration` requires the relevant JDBC classes, a `DataSource` bean, and the health enablement condition keyed by `db`. The contributor factory method also checks for the absence of beans named `dbHealthIndicator` and `dbHealthContributor`. Therefore, you cannot conclude "Actuator was added, so `db` is definitely present". See [Spring Boot 3.3 JDBC Auto-Configuration Source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/jdbc/DataSourceHealthContributorAutoConfiguration.java).

### Three states easily conflated

| Observation | What can be concluded? | Further evidence to look for |
| --- | --- | --- |
| `db` not visible in JSON | Not enough to say the database is broken or the indicator does not exist. | Visibility policy, health group being called, registry, condition evaluation report. |
| `db` present with status `DOWN` | Contributor exists; the check failed. | Connection errors, authentication, pool, validation query, and related logs. |
| Application fails to start | No serving endpoint exists yet to query health. | Bean creation failure, driver, resource config, or other startup error. |

## 3. Quick identification map

The table below highlights common cases. The beans are starting points for inspection, not an exhaustive list of every condition annotation on each configuration.

| Resource | Health config key | Common component name | Sign the resource is integrated |
| --- | --- | --- | --- |
| Database via JDBC | `db` | `db` | `DataSource` and suitable Spring JDBC infrastructure present. |
| Redis | `redis` | `redis` | `RedisConnectionFactory` or `ReactiveRedisConnectionFactory` present. |
| Disk space | `diskspace` | `diskSpace` | No network service needed; uses a path on the process's filesystem. |
| Simple always-succeeding check | `ping` | `ping` | `PingHealthIndicator` does not check external servers. |
| MongoDB | `mongo` | `mongo` | Corresponding Mongo infrastructure, such as `MongoTemplate` or reactive variant. |
| RabbitMQ | `rabbit` | `rabbit` | Spring AMQP infrastructure, such as `RabbitTemplate`. |
| Mail server | `mail` | `mail` | Suitable `JavaMailSenderImpl` present. |
| Elasticsearch | `elasticsearch` | `elasticsearch` | Compatible client supported by Actuator present. |
| JMS | `jms` | `jms` | `jakarta.jms.ConnectionFactory` present. |
| LDAP | `ldap` | `ldap` | Suitable Spring LDAP infrastructure, such as `LdapOperations`. |

Spring Boot also has integrations such as Cassandra, Couchbase, Neo4j, Hazelcast, and InfluxDB. Do not add them just to make the health tree longer: only resources the application actually uses carry operational meaning. The list depends on version; check [Spring Boot 3.3 Indicator Catalog](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.auto-configured-health-indicators) when working with a specific integration.

**Note on spelling:** the property key is `management.health.diskspace.enabled`, whereas the default component name and path segment is `diskSpace`, e.g. `/actuator/health/diskSpace`. Do not derive an arbitrary config key from the component name's casing.

## 4. JDBC: what can the `db` branch check?

### Conditions for appearance

An application normally has a `DataSource` when a driver, JDBC infrastructure, and valid connection configuration are present. JPA can also use `DataSource`, so a JPA application can have the `db` branch without writing a custom indicator.

The key factor is the actual resource bean. Having a URL string in configuration alone does not guarantee a `DataSource` was created; conversely, an application-declared `DataSource` can still be recognized by health auto-configuration if other conditions are met.

### Check mechanism and limits

`DataSourceHealthIndicator` works through the application's `DataSource`. In the Spring Boot 3.3 branch referenced here, it retrieves the database product name and validates the connection using a supplied validation query, or via `Connection.isValid(...)` when no query is supplied. Auto-configuration may obtain a query from pool metadata. Do not assume every database engine runs an exact `SELECT 1` query. See [DataSourceHealthIndicator Mechanics](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/jdbc/DataSourceHealthIndicator.java).

Receiving `UP` gives evidence that the connection check just performed succeeded. It does not give evidence that migrations created all tables, that the account has all business permissions, that long transactions will not deadlock, or that reporting queries will run fast.

A typical scenario: the connection is valid, yet the `orders` table has not been created. The `db` branch can still be `UP`, while an order-reading API fails because the table is missing. The two results do not contradict because they check two different things.

### Multiple data sources

If multiple `DataSource` beans exist, the `db` branch can contain multiple child components instead of a flat indicator. Child names help identify which source has a problem. Illustrative structure example, not a fixed output for every application:

```json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN",
      "components": {
        "ordersDataSource": { "status": "UP" },
        "reportingDataSource": { "status": "DOWN" }
      }
    }
  }
}
```

Do not modify connection details of `ordersDataSource` just because `db`'s overall status is `DOWN`. First read which child component failed. With routing data sources, also inspect target sources and `management.health.db.ignore-routing-data-sources`; do not assume the aggregate branch is a single connection.

### Why can `db` still go `DOWN` while the application is running?

After startup, the database may lose network connectivity, the account may have privileges revoked, or the pool may no longer dispense a connection within the wait timeout. Health reflects the probe at the moment it is called, not a certificate valid forever since startup.

Nor should you assume all connection failures wait until health is called: pool configuration, migration steps, or startup tasks can make the application fail immediately at startup.

## 5. Redis: checking with the application's own client

### Recognizing synchronous and reactive paths

The synchronous branch uses `RedisConnectionFactory`. The reactive branch relies on `ReactiveRedisConnectionFactory` and Reactor. Both tie to the `redis` config key; do not infer there must be two JSON components merely because both API types are present.

With a typical Lettuce setup, the connection bean can satisfy both types. In Spring Boot 3.3 auto-configuration, the reactive branch is considered first; bean conditions on `redisHealthIndicator` or `redisHealthContributor` cause the synchronous configuration to back off. Thus, even a Spring MVC application can see `RedisReactiveHealthIndicator` as the implementation; do not guess the implementation solely from MVC/WebFlux choice. Compare [Synchronous Redis Auto-Config](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/data/redis/RedisHealthContributorAutoConfiguration.java) and [Reactive Redis Auto-Config](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/data/redis/RedisReactiveHealthContributorAutoConfiguration.java).

### Do not equate health with the `PING` command

In Spring Boot 3.3.0 code:

- Synchronous `RedisHealthIndicator` acquires a connection and reads `INFO`; for a cluster connection, it reads cluster info.
- `RedisReactiveHealthIndicator` uses `INFO server` for non-cluster setups and reads cluster info for cluster setups.

Therefore, running `redis-cli PING` and receiving `PONG` does not prove the application's account is allowed to run the command the indicator needs. An account might be allowed `PING`, `GET`, `SET` yet blocked by ACL from `INFO`, causing health to fail. Check with the same host, port, TLS, account, and command permissions as the application's client. See [Synchronous Redis Indicator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/data/redis/RedisHealthIndicator.java) and [Reactive Redis Indicator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/data/redis/RedisReactiveHealthIndicator.java).

A Redis server may be running while the application cannot reach it due to DNS, network, certificates, or password. Thus, health is read from the application process's perspective, not by an administrator seeing the Redis process on another machine.

`redis=UP` also does not verify that expected data exists, key structures are valid, Lua scripts run, or transactional business logic works as intended. With multiple connection factories, inspect each child component to determine which configuration failed.

### Connection configuration is not indicator configuration

The snippet below is for Spring Boot 3.3, when the application already has the Redis starter and a local Redis running:

```properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379
spring.data.redis.connect-timeout=1s
spring.data.redis.timeout=1s
management.health.redis.enabled=true
```

Keys `spring.data.redis.*` configure the client; `management.health.redis.enabled` controls auto-configuration of the check. The timeout values here are choices for a learning environment, not a guarantee that the entire HTTP health call always completes in exactly one second.

## 6. Disk space: the `diskSpace` branch measures what the process sees

`DiskSpaceHealthIndicator` does not need MySQL or Redis. It reads usable space on the filesystem at a path, then compares it against a minimum threshold. In Spring Boot 3.3.0, the default path is `.` and the threshold is `10MB`, corresponding to `10 × 1024 × 1024 = 10,485,760` bytes.

The status condition is:

```text
usableSpace >= threshold  → UP
usableSpace < threshold   → DOWN
```

The path `.` is resolved relative to the process's working directory. It does not automatically point to the source code directory, database data directory, or every drive on the machine. See [DiskSpaceHealthIndicatorProperties Defaults](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/system/DiskSpaceHealthIndicatorProperties.java) and [Comparison in DiskSpaceHealthIndicator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/system/DiskSpaceHealthIndicator.java).

Example configuration to check an existing data directory:

```properties
management.health.diskspace.path=/var/lib/orders
management.health.diskspace.threshold=500MB
```

On Windows, replace the path with a valid path for the runtime environment, such as `C:/orders-data`. This property does not create the directory. Choosing the wrong path can yield results that do not reflect the partition the application needs.

Inside a container, the check uses the filesystem seen by the container. If critical data resides on a volume different from the working directory, specify a path on that volume. Do not take the personal host machine's disk space to infer results inside the container.

When details are allowed to be shown, fields such as `total`, `free`, `threshold`, `path`, and `exists` may appear. `free` is the usable space read by Java for that path. Numbers and paths depend on the host machine; they are not fixed outputs to copy verbatim.

This check does not substitute for testing file writes, directory permissions, I/O latency, or data integrity. A filesystem with plenty of space that is read-only can still fail the application's write workload.

## 7. Hands-on: seeing auto-configured indicators

The following example is **a standalone Maven project**, requiring no additional controller. It starts with web and Actuator to observe `diskSpace` and `ping`, and only then adds JDBC or Redis to see how resources affect the health tree.

### 7.1. Creating three files

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/learning/healthdemo/HealthDemoApplication.java`:

```java
package learning.healthdemo;

import java.util.TreeSet;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.HealthContributorRegistry;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printHealthContributors(HealthContributorRegistry registry) {
        return args -> {
            var names = new TreeSet<String>();
            registry.forEach(contributor -> names.add(contributor.getName()));
            System.out.println("contributors=" + names);
        };
    }
}
```

`TreeSet` sorts names so the observed line is deterministic. Listing names does not call `health()` and does not prove resources are `UP`; it only tells which contributors were registered.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
```

`show-details=always` is used for this loopback-bound example to inspect evidence. In deployment, choose an appropriate visibility policy and access permissions because health details can expose paths, product names, and connection errors.

### 7.2. Running and reading the initial status

In the directory containing `pom.xml`, verify Maven uses JDK 21 and run:

```shell
java -version
mvn -version
mvn spring-boot:run
```

On Windows you can invoke `mvn.cmd`. This is a multi-file Spring Boot application with library dependencies, so do not compile with a standalone `javac HealthDemoApplication.java` command. Maven resolves the classpath and compiles the project's Java code.

With the exact sample configuration, not running in a Kubernetes environment, and no other contributors added, the line printed by the application is:

```text
contributors=[diskSpace, ping]
```

Other Spring Boot startup lines still appear around it. Open a second terminal and call:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/health/ping
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias for a PowerShell cmdlet. For the `/ping` path, default HTTP is `200` and the body is:

```json
{"status":"UP"}
```

At the root path, look for the `diskSpace` and `ping` branches. If space at the checked path meets the threshold, both are `UP`. Do not expect `db` or `redis`: the current example has not integrated those two resources. `ping=UP` here also does not mean the application pinged MySQL, Redis, or a network address.

### 7.3. Adding JDBC and H2 to observe `db`

Stop the application, add these two dependencies **inside the existing `dependencies` section**, keeping the original two dependencies intact:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

Add to the properties file:

```properties
spring.datasource.url=jdbc:h2:mem:healthdemo
spring.datasource.username=sa
spring.datasource.password=
```

Re-run the same Maven command. With no other environment or contributor changes, the printed line becomes:

```text
contributors=[db, diskSpace, ping]
```

Then call:

```shell
curl -i http://127.0.0.1:8080/actuator/health/db
```

The expected result is status `UP` when the H2 connection is valid; details identify the product as H2. JSON key ordering carries no meaning. This test illustrates that **having JDBC infrastructure and a `DataSource` adds `db`**, not that Actuator creates a business database for the application automatically.

### 7.4. Optional: adding Redis

Only perform this step when you have a Redis instance for your learning environment. Stop the application, add the following dependency inside `dependencies`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Add the Redis configuration from section 5, restart, and call `/actuator/health/redis`. If the client is created and the contributor is registered, the `redis` branch appears; its status depends on actual connectivity and the check. Do not hardcode a fixed Redis version number into expected output because each learner's environment may differ.

If Redis is unreachable yet the application still starts, the branch can return `DOWN`. If startup itself failed during initialization, resolve the startup failure first; you cannot use HTTP health of that process yet.

## 8. Enabling/disabling indicators differs from hiding information

These three options solve three different problems:

| Configuration | Meaning |
| --- | --- |
| `management.health.redis.enabled=false` | Prevents auto-configuration from creating the Redis contributor under this mechanism. |
| `management.endpoint.health.show-details=never` | Hides details in the response; does not make the check disappear. |
| `management.endpoints.web.exposure.include=health` | Exposes the health endpoint over HTTP; does not add libraries or resource beans. |

To view component names without showing details, you can use:

```properties
management.endpoint.health.show-components=always
management.endpoint.health.show-details=never
```

Then `db` or `redis` along with their statuses are still visible, without receiving all detail fields. Do not conclude a resource is healthy merely because error details are hidden.

You can disable defaults and selectively enable specific indicators managed by auto-configuration:

```properties
management.health.defaults.enabled=false
management.health.diskspace.enabled=true
management.health.ping.enabled=true
```

This option is not a switch that deletes custom health beans declared by the application. Similarly, setting `management.health.db.enabled=false` does not delete `DataSource`, does not remove the need for the database, and does not fix a broken connection; it changes the auto-configured check's participation condition. Look up key names in [Spring Boot 3.3 Actuator Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/).

## 9. Evidence-based diagnostic workflow

### When an expected indicator is missing

1. Confirm you are calling the right process, port, context path, and management path. The example uses default `/actuator`; real projects may have changed it.
2. Check `show-components` and `show-details` policies, access permissions, and whether you are calling a health group that filters components.
3. Check runtime libraries, resource beans, and active profiles/configuration. Having a config file in source control does not prove the process loaded it.
4. Check `management.health.<key>.enabled`, the global default value, auto-configuration exclusions, and custom beans that might replace the default component.
5. Run the application with the condition evaluation report to see which conditions matched or did not match. With the sample Maven project, you can use:

```shell
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Look for classes such as `DataSourceHealthContributorAutoConfiguration`, `RedisHealthContributorAutoConfiguration`, `RedisReactiveHealthContributorAutoConfiguration`, and `DiskSpaceHealthContributorAutoConfiguration`. The condition report helps explain **why a bean was or was not created**; it does not replace health results when a resource is checked.

### When an indicator exists yet returns `DOWN`

| Component | Priority evidence | Premature conclusion to avoid |
| --- | --- | --- |
| `db` | Child components, connection acquisition errors, auth, pool, driver, and validation query. | "The entire database is dead." |
| `redis` | Active client, DNS/TLS, account, ACL for `INFO` or cluster commands, timeout. | "PING succeeded so Actuator must be wrong." |
| `diskSpace` | `path`, `exists`, `free`, `threshold`, volume as seen from the process. | "Host server disk has free space so this branch cannot be DOWN." |
| `mail`, `rabbit`, or other services | Exact client, endpoint, permissions, and check operation of that implementation. | "One connection check proved every business feature works." |

When HTTP returns `503`, still read the JSON to see which branch failed; when HTTP returns `401`, `403`, or `404`, check access and routing first instead of treating it as proof the database is broken. Under default mapping configuration, health `DOWN` and `OUT_OF_SERVICE` are returned via HTTP `503`. If the application customized mapping or aggregation, read the actual configuration.

There is no single global timeout property guaranteeing every indicator stops on time. Wait durations also depend on clients, pools, check operations, and network environment. Slow-indicator logging thresholds are an observation mechanism; do not mistake them for a mechanism that cancels running operations.

## 10. Self-checking your ability to read the health tree

**Scenario 1:** `/actuator/health` returns only `{"status":"UP"}`. Can you assert the application has no Redis indicator?

No. First inspect the visibility policy and registered contributors. An aggregated response with components hidden does not list the checks.

**Scenario 2:** `db=UP` yet the API fails due to a missing `orders` table. Is the indicator wrong?

There is no evidence the indicator is wrong. A JDBC connection check does not verify the existence and correctness of the entire business schema.

**Scenario 3:** `redis-cli PING` succeeds yet the `redis` branch reports a permission error on `INFO`. What should be checked?

Verify whether the CLI and application use the same configuration, then compare command permissions actually invoked by the health implementation. `PING` succeeding does not grant permission for `INFO`.

**Scenario 4:** the application writes data on a separate volume, yet `diskSpace.path=.` checks another partition. Is an `UP` result enough to guarantee the data-writing location has free space?

No. Choose a path reflecting the filesystem that needs to be observed; checking free space still does not replace write-permission checks and I/O behavior.

After these scenarios, aim to identify three facts for every component in your application: **which resource bean makes it appear, which operation produces its status, and what lies outside the proof scope of that operation**.
