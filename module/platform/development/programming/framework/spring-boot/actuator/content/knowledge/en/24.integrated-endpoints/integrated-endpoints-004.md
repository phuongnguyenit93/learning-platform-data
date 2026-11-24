# Inspecting Migration History with the `flyway` Endpoint

## 1. What Question Does This Endpoint Help Answer?

A Java code change may require adding a corresponding table, column, or seed data in the database. A migration is a database change described and managed in sequence. Flyway executes migrations and records history so subsequent deployments know which changes have already been applied.

When a feature reports a missing column, the operational question is not only "which Java build is running?", but also "has the database this application uses received the required migration yet?".

Spring Boot Actuator's built-in `flyway` endpoint exposes migration information from Flyway beans to the management interface:

~~~text
Migration files shipped with application
              +
Flyway history in database
              ↓
       Flyway.info().all()
              ↓
ApplicationContext → Flyway bean → migration list
              ↓
     GET /actuator/flyway
~~~

Three tasks must be kept distinct:

| Task | Tool/Mechanism |
| --- | --- |
| Observing migration information | `flyway` endpoint, or Flyway `info` |
| Applying database changes | Flyway `migrate` |
| Checking whether current migrations match history | Flyway `validate` |

GET on the endpoint is not a migration deployment button, does not perform `repair`, and does not provide validation results for the entire database structure. The endpoint's Java contract only declares the read operation `flywayBeans()`. Source: [FlywayEndpoint API in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/flyway/FlywayEndpoint.html).

This article uses Spring Boot **3.3.x**. The runnable example pins Boot **3.3.0**, Flyway **10.10.0**, and H2 **2.2.224**, with Java **17 or higher**. These are the versions used for the experiment; when working with another system, cross-check the exact versions that system uses.

## 2. Where Is History Stored, and How Should State Be Interpreted?

Flyway stores the record of applied migrations in the schema history table, named `flyway_schema_history` by default. The table name and containing schema can be configured. This history records details such as version, script, checksum, timestamp, and execution outcome.

However, **the `state` in the API is not just copying a `state` column from the history table**. Flyway compares the history in the database against the migrations found by the current application build and active configuration, and then determines the state.

For example:

- File V2 is in the application, while the database has only applied V1: V2 may be `PENDING`.
- The database already applied V2, but the application can no longer find the corresponding file: the state must be read in the relationship between history and current files.
- A `target` configuration limits the version: an unapplied migration may be `ABOVE_TARGET`, not `PENDING`.

Therefore, when investigating, identify **the application build, Flyway configuration, and target database** together. See [Flyway schema history table and states](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table).

In particular, in Boot 3.3, the endpoint calls **`Flyway.info().all()`**. The list can contain both applied migrations and unapplied migrations that Flyway resolves. Do not treat every element in the `migrations` array as a change that has already run successfully.

## 3. Requirements for the Endpoint to Appear over HTTP

A web application needs Actuator and at least one properly configured Flyway bean. When using Boot's auto-configuration, the Flyway dependency, JDBC DataSource, and related settings govern bean creation and migration initialization.

Example dependencies for the H2 lab, added to a Gradle project already managed by Spring Boot 3.3:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'com.h2database:h2'
}
~~~

This is a configuration snippet for an existing Spring Boot project, not a complete standalone Gradle project.

Illustrative configuration in `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: flyway-lab
  datasource:
    url: jdbc:h2:mem:flyway_web_lab;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  sql:
    init:
      mode: never
  flyway:
    enabled: true
    locations: classpath:db/migration

management:
  endpoint:
    flyway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,flyway
~~~

Three settings have distinct roles:

| Setting | Role |
| --- | --- |
| `spring.flyway.enabled` | Controls Boot's Flyway auto-configuration |
| `management.endpoint.flyway.enabled` | Enables/disables the management endpoint in Boot 3.3 |
| `management.endpoints.web.exposure.include` | Selects endpoints exposed over HTTP |

Enabling the endpoint does not automatically create a Flyway bean; exposing over HTTP does not automatically grant access permissions. If `exposure.exclude` is set, check it because it takes precedence over `include`. Source: [Actuator endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

With Boot 3.3, H2 is supported via `flyway-core`; some other databases require adding the corresponding Flyway module, such as `flyway-database-postgresql` for PostgreSQL. Do not infer from having a JDBC driver that full Flyway support exists for every database engine.

In typical configuration, Boot calls `Flyway.migrate()` at startup. This happens during initialization lifecycle, **not when an operator calls GET on the endpoint**. By default, scripts live under `classpath:db/migration`, with names like `V1__create_product.sql` — containing **two underscores** between version and description. Source: [Database initialization with Flyway in Boot 3.3](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html#howto.data-initialization.migration-tool.flyway).

If using JPA, avoid letting multiple mechanisms create/alter the schema independently without clear ownership. In the lab above, basic SQL init is turned off so table creation belongs to migrations.

## 4. Calling the Endpoint and Reading the Response Structure

With the lab's default port and management path:

~~~shell
curl -i "http://localhost:8080/actuator/flyway"
~~~

On Windows PowerShell where `curl` is an alias, use `curl.exe` if you want to invoke the actual curl tool. The example assumes the request has already been granted access.

An **illustrative** JSON body for a SQL migration that has run successfully:

~~~json
{
  "contexts": {
    "application": {
      "flywayBeans": {
        "flyway": {
          "migrations": [
            {
              "type": "SQL",
              "checksum": -120035678,
              "version": "1",
              "description": "create product",
              "script": "V1__create_product.sql",
              "state": "SUCCESS",
              "installedBy": "SA",
              "installedOn": "2026-11-06T03:00:00Z",
              "installedRank": 1,
              "executionTime": 7
            }
          ]
        }
      }
    }
  }
}
~~~

The checksum, duration, and timestamp in the JSON above are illustrative data, not fixed values for the script in this article. When practicing, take values from the actual response.

The path to the array to read is:

~~~text
contexts
  → ApplicationContext ID
    → flywayBeans
      → Flyway bean name
        → migrations
~~~

`application` and `flyway` are example keys. Do not hard-code that every system always has those exact two names. There may be multiple contexts, parent contexts, and multiple Flyway beans. In a multi-database system, match each bean against its DataSource/schema configuration before concluding a migration is present in the right place.

Fields to read:

| Field | Meaning |
| --- | --- |
| `version` | Migration version, if present |
| `description` | Description |
| `script` | Script name |
| `type` | Migration type |
| `state` | State determined by Flyway |
| `checksum` | Content verification value, if present |
| `installedBy` | Database account that executed it |
| `installedOn` | Timestamp applied |
| `installedRank` | Order in the application history |
| `executionTime` | Execution duration, in milliseconds |

The structure contract and units are described in [Boot 3.3 Actuator Flyway HTTP API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/flyway.html).

Common misreadings:

- `installedBy` is usually the database connection account; it does not prove a specific individual clicked deploy.
- `installedRank` is application order, not synonymous with version number. When applied out of order, the two values especially need to be read separately.
- Do not compare versions using ordinary string ordering: strings `"10"` and `"2"` do not reflect version order via character comparison alone.
- A negative checksum does not by itself mean an error; verify via Flyway's mechanism rather than relying on the numeric sign.
- Unapplied migrations do not yet have an installed timestamp, executor, rank, or duration. The corresponding fields may be unset/null.
- Repeatable migrations may not have a `version`. Do not force every migration to be `V1`, `V2`, or share the same set of non-null fields.

## 5. Reading State to Choose the Next Investigation Step

State names in the JSON are uppercase enum names. Several states commonly need distinguishing:

| State | How to Interpret Within Observation Scope |
| --- | --- |
| `SUCCESS` | Migration has been applied successfully |
| `PENDING` | Migration was found and is waiting to be applied |
| `ABOVE_TARGET` | Migration is above the configured target limit |
| `FAILED` | A failed migration is reflected by history/state |
| `MISSING_SUCCESS` | Migration succeeded previously but is no longer resolved from current sources |
| `FUTURE_SUCCESS` | Migration succeeded with a version higher than the highest version resolved from current sources |
| `OUT_OF_ORDER` | Migration was applied out of version order |
| `OUTDATED` / `SUPERSEDED` | States related to repeatable migration lifecycle |

This list does not replace the full state rules of a specific Flyway version. For example, state depends on migration sources, `target`, baseline, and actual history; you cannot diagnose every cause from a single enum name alone. Refer to [Flyway's state model](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table).

If you see V2 is `PENDING`, the next question is: is this the right application build and the right target database; did the pipeline intentionally hold off applying V2? Do not jump straight from "pending" to "must run immediately on this environment."

If you see `MISSING_SUCCESS` or `FUTURE_SUCCESS`, check the application artifact and `locations`: an older application build may be looking at a database already upgraded by a newer build. The endpoint reflects that relationship; it does not automatically prove the database is corrupted.

## 6. Java Experiment: Observing V2 Pending, Then Applying Separately

The following experiment uses an in-memory H2 database and directly calls **Actuator's `FlywayEndpoint` itself**. It does not start an HTTP server and does not use a real database.

Idea:

1. Create V1 adding table `product`, V2 adding column `price`.
2. Run Flyway the first time with `target=1` to apply only V1.
3. Create another Flyway bean pointing to the same database and same scripts, without a target limit.
4. Read the endpoint: V1 succeeded, V2 is pending.
5. Read again and verify V2 is still pending.
6. Call `migrate()` separately, then read again.

Removing the target limit in step 3 is intentional. If you continued using Flyway with `target=1`, V2's state could be `ABOVE_TARGET`, making that a different experiment.

### 6.1. Dependencies

In a separate lab directory, create `pom.xml`:

~~~xml
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
    <artifactId>flyway-history-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The Boot 3.3.0 parent manages the library versions used for the lab. Maven here only builds the dependency classpath; we use `javac` and `java` directly.

### 6.2. Complete Program

Place `FlywayHistoryDemo.java` alongside `pom.xml`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.flywaydb.core.Flyway;
import org.springframework.boot.actuate.flyway.FlywayEndpoint;
import org.springframework.context.support.GenericApplicationContext;

public class FlywayHistoryDemo {
    public static void main(String[] args) throws Exception {
        Logger.getLogger("org.flywaydb").setLevel(Level.OFF);
        Path directory = Files.createTempDirectory("flyway-history-demo-");
        Path v1 = directory.resolve("V1__create_product.sql");
        Path v2 = directory.resolve("V2__add_price.sql");
        try {
            Files.writeString(v1,
                    "CREATE TABLE product (id BIGINT PRIMARY KEY, name VARCHAR(100));");
            Files.writeString(v2,
                    "ALTER TABLE product ADD COLUMN price DECIMAL(12,2);");
            String url = "jdbc:h2:mem:flyway_history_demo;DB_CLOSE_DELAY=-1";
            String location = "filesystem:" + directory.toAbsolutePath();

            Flyway.configure().dataSource(url, "sa", "")
                    .locations(location).target("1").load().migrate();

            Flyway flyway = Flyway.configure().dataSource(url, "sa", "")
                    .locations(location).load();
            try (GenericApplicationContext context = new GenericApplicationContext()) {
                context.setId("lab");
                context.getBeanFactory().registerSingleton("flyway", flyway);
                context.refresh();
                FlywayEndpoint endpoint = new FlywayEndpoint(context);

                print("before read", endpoint);
                endpoint.flywayBeans();
                System.out.println("pending after read="
                        + flyway.info().pending().length);

                flyway.migrate();
                print("after migrate", endpoint);
                System.out.println("pending after migrate="
                        + flyway.info().pending().length);
            }
        } finally {
            Files.deleteIfExists(v2);
            Files.deleteIfExists(v1);
            Files.deleteIfExists(directory);
        }
    }

    private static void print(String label, FlywayEndpoint endpoint) {
        System.out.println(label);
        var migrations = endpoint.flywayBeans().getContexts()
                .get("lab").getFlywayBeans().get("flyway").getMigrations();
        for (var migration : migrations) {
            System.out.println("version=" + migration.getVersion()
                    + " state=" + migration.getState().name()
                    + " rank=" + migration.getInstalledRank());
        }
    }
}
~~~

The program creates exactly two scripts in a separate temporary directory and deletes them on completion. H2 runs in the process's memory. `DB_CLOSE_DELAY=-1` keeps this database alive across Flyway opening/closing connections within the same run; it does not turn data into persistent storage across processes.

The context is assigned ID `lab` and the `flyway` bean is registered explicitly, so the program knows the exact path to retrieve the list. When reading JSON from a real application, you must use the actual keys.

### 6.3. Compiling and Running

Requires JDK 17+ and Maven; fetching dependencies the first time requires connectivity to the Maven repository.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$flywayClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$flywayClasspath" FlywayHistoryDemo.java
java -cp ".;$flywayClasspath" FlywayHistoryDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
flyway_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$flyway_classpath" FlywayHistoryDemo.java
java -cp ".:$flyway_classpath" FlywayHistoryDemo
~~~

Program stdout:

~~~text
before read
version=1 state=SUCCESS rank=1
version=2 state=PENDING rank=null
pending after read=1
after migrate
version=1 state=SUCCESS rank=1
version=2 state=SUCCESS rank=2
pending after migrate=0
~~~

The program lowers Flyway's JUL log level to focus on the lines above; other logging configurations may still emit additional logs.

Points to be able to explain:

- `rank=null` for V2 before migration matches the fact that it has not been applied yet.
- `pending after read=1` proves the read operation does not apply V2.
- After the separate `migrate()` call, V2 has `SUCCESS` and installed rank 2.
- `pending after migrate=0` confirms no migrations remain pending in this exact script set and lab database.

This is evidence for the stated configuration, not an assumption that every environment has only two migrations or that every context ID is `lab`.

## 7. Applying This Observation Method to a Web Application

In the web application already configured in section 3, place two SQL scripts under:

~~~text
src/main/resources/db/migration/
├── V1__create_product.sql
└── V2__add_price.sql
~~~

Contents of V1:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100)
);
~~~

Contents of V2:

~~~sql
ALTER TABLE product ADD COLUMN price DECIMAL(12,2);
~~~

With a fresh lab database and default startup configuration, Boot runs migrations on startup; once the application is ready, GET typically shows both V1 and V2 as `SUCCESS`. This does not contradict the experiment in section 6, because the experiment deliberately stopped the first run at V1.

You can inspect all contexts and beans in PowerShell without assuming key names:

~~~powershell
$response = Invoke-RestMethod -Uri "http://localhost:8080/actuator/flyway"
$rows = foreach ($context in $response.contexts.PSObject.Properties) {
    foreach ($bean in $context.Value.flywayBeans.PSObject.Properties) {
        foreach ($migration in $bean.Value.migrations) {
            [pscustomobject]@{
                Context = $context.Name
                Bean = $bean.Name
                Version = $migration.version
                State = $migration.state
                Rank = $migration.installedRank
                Script = $migration.script
            }
        }
    }
}
$rows | Format-Table -AutoSize
~~~

This is a read-only projection; it does not alter migration state. If the system requires authentication, add the authentication method configured for that environment.

When tracking a release that requires V2, locate the exact migration in the exact bean and read `state`, rather than just looking for the name. Simply seeing V2 appear in the array is not enough: `PENDING` and `SUCCESS` lead to two different deployment conclusions.

## 8. Conclusions the Endpoint Does Not Guarantee

### 8.1. HTTP 200 Does Not Mean All Migrations Succeeded

`200` means the endpoint read operation succeeded at the HTTP layer. The returned array can still contain unapplied migrations or states requiring investigation. Monitoring tools must inspect the payload, not just check the HTTP status code.

The `flyway` endpoint also does not automatically convert those states into a `health` result according to your system's business rules. If deployments must be gated on migration state, that rule must be explicitly placed in deployment checks.

### 8.2. SUCCESS in History Does Not Replace Validate

Suppose V1 was already applied, and someone later edited the V1 file contents in the application package. Seeing a successful history row is not a checksum verification result between the two sides.

`validate` compares applied migrations against current migrations, including name, type, and checksum per Flyway configuration. Source: [Flyway Validate command](https://documentation.red-gate.com/flyway/reference/commands/validate).

Do not ask readers to recompute checksums manually with an arbitrary hash function and compare against the number in JSON. Use Flyway's own verification mechanism and the exact migration source set.

### 8.3. History Does Not Prove the Current Schema Was Never Altered Outside Flyway

If a column was dropped manually after V2 ran, the successful V2 record can still remain. History records the application event; it does not become an inspection of all current tables, columns, constraints, and data.

When an application error contradicts history, inspect the actual schema and the database the request is using, instead of re-reading the same `SUCCESS` row.

### 8.4. Not Every Failed Migration Can Be Observed Through a Running Application

If a migration fails during startup initialization, the application may fail to start up to the point of serving HTTP. In that case the endpoint is unavailable; the investigation sources are startup logs and database state.

Whether a failed run leaves traces or partial changes also depends on the database and transactions. Do not infer "no FAILED visible in the endpoint" as "no error ever occurred."

## 9. Handling Common Scenarios

| Symptom | What to Verify |
| --- | --- |
| Endpoint returns `404` | Are port/base path right; is endpoint enabled/exposed; is there a Flyway bean |
| Returns `401` or `403` | Authentication and authorization configuration for management paths |
| Expected migration missing | Right bean, datasource, schema, application build, and `locations`; is filename valid |
| V2 visible but feature still lacks column | Read `state`; cross-check actual database and current schema structure |
| One environment shows `PENDING`, another shows `SUCCESS` | Do they have the same application build, target config, and deployment plan |
| State is missing or future | Is the application package older or missing migrations compared to the database |
| App fails to come up after adding migration | Read startup logs; do not wait for an endpoint the process is not serving yet |
| Database access error when reading | Check connectivity, permissions to read metadata/history, and active Flyway config |

There is no built-in `POST /actuator/flyway/migrate` or `POST /actuator/flyway/repair` contract in this endpoint. Do not try to turn an observation request into a write operation by changing the HTTP method.

`repair` modifies the history table and does not automatically undo database objects left behind after an error. If history discrepancies must be handled, investigate the root cause and follow an approved database change procedure; do not treat it as a default step after reading an unexpected state. Source: [Scope of the Repair command](https://documentation.red-gate.com/flyway/reference/commands/repair).

Endpoint output can reveal script names, version structure, and execution accounts. Grant read permissions according to operational need; adding `flyway` to the HTTP exposure list does not replace application security.

## 10. Practicing Evidence Reading for a Release

Suppose a new release needs the `product.price` column added by V2.

1. Identify the exact environment, application build, and Flyway bean attached to the database containing the `product` table.
2. GET the endpoint, locate the V2 script, and read `state`, rather than just searching for the name.
3. If V2 is `PENDING`, check migration deployment status; sending another GET will not apply it.
4. If V2 is `SUCCESS` yet the feature still fails, inspect the actual datasource and current schema structure.
5. If you suspect a script was modified, use the deployment pipeline's `validate` step; do not conclude solely from the displayed checksum.

**Self-check exercises:**

- In the experiment, keep `target=1` for the observed Flyway bean and predict V2's state. Why does it differ from `PENDING`?
- Read the endpoint twice before `migrate()`. Which values show that V2 has not been applied yet?
- Explain why `installedRank=2` does not mean every migration on the system must carry version `"2"`.
- An older application build looks at a database already upgraded by a newer build: which sources must be checked before modifying history?
- What evidence do HTTP `200` and a single `SUCCESS` row provide, and what evidence is still missing to confirm the feature uses the right schema?

Every conclusion should be tied to a specific **context, Flyway bean, target database, and migration state** so others can verify it.
