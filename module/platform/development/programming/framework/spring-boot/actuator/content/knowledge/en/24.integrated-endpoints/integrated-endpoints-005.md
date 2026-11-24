# Inspecting Database Changes with the `liquibase` Endpoint

## 1. From Schema Changes to Deployed Evidence

Suppose an application version requires a `note` table and a `status` column. The source code already describes creating the table, yet when deploying you still need to know which changes the database your application connects to has recorded. That is a different question from merely checking whether the application returns HTTP 200.

Actuator's `liquibase` endpoint provides information about **change sets recorded by Liquibase in the database**. The default HTTP path is `GET /actuator/liquibase`. It is a tool for observing change history; this read operation is not a command to run migrations or rollbacks. [Spring Boot 3.3 Liquibase API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html)

Concepts to grasp upfront:

- **Migration:** a managed change to the database, such as creating a table or adding a column.
- **Changelog:** a file describing a collection of changes and their declaration order.
- **Change set:** a unit of change identified and tracked by Liquibase.
- **`DATABASECHANGELOG` history table:** where Liquibase stores information about recorded change sets.

A change set is identified by the tuple **`id` + `author` + changelog path**, not `id` alone. Therefore, when comparing two environments, match the full identifier instead of seeing the same sequence number and assuming it is the same change. [DATABASECHANGELOG table](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

This article uses **Java 21, Spring Boot 3.3.13, and Liquibase managed by Boot's BOM**. This Boot branch manages `liquibase-core` version `4.27.0`. [Dependency versions catalog](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html)

## 2. Where Does the Endpoint Sit in the Migration Lifecycle?

Typical flow in a Boot application:

```text
Changelog packaged with the application
    -> Liquibase connects to the database at startup
    -> checks recorded change sets
    -> applies eligible changes
    -> records entries in the history table
    -> Actuator allows reading the recorded info
```

Adding `liquibase-core` to a properly configured Boot application allows migrations to run at startup. Changelogs can use YAML, JSON, XML, or SQL; the location is controlled by `spring.liquibase.change-log`. The example in this article chooses JSON to represent the data structure clearly. [Database initialization with Liquibase](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html)

Separate three questions:

| Question | Evidence to Cross-Check |
| --- | --- |
| Which change sets has Liquibase recorded? | `liquibase` endpoint or corresponding history table |
| Which changes in the current changelog are not yet deployed? | Cross-check changelog, filters, and migration check tools |
| Does the schema currently have the expected tables/columns? | Metadata or direct query against the exact database |

These three questions are related, not interchangeable. A history record does not automatically detect someone modifying the schema manually after migration.

## 3. Standalone Runnable Practice Project

### 3.1. File Structure and Dependencies

Prepare JDK 21, Gradle 8.5, and a new practice directory:

```text
liquibase-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/liquibase/LiquibaseReadApplication.java
    └── resources/
        ├── application.properties
        └── db/changelog/changelog.json
```

`settings.gradle`:

```groovy
rootProject.name = 'liquibase-read-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.liquibase:liquibase-core'
    runtimeOnly 'com.h2database:h2'
}

application {
    mainClass = 'lab.liquibase.LiquibaseReadApplication'
}
```

The application uses file-based H2 so history persists across runs in the same working directory. The practice project uses only Liquibase to manage the schema; no JPA or `schema.sql`/`data.sql` files are needed.

### 3.2. Connection and HTTP Exposure Configuration

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

spring.datasource.url=jdbc:h2:file:./data/liquibase-lab;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=

spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/changelog.json

management.endpoints.web.exposure.include=health,liquibase
```

The loopback address and H2 credentials above are for local experimentation. The `./data/liquibase-lab` path is resolved relative to the process's working directory; keep the same directory when testing across multiple restarts.

`liquibase` is enabled by default in Boot 3.3, but HTTP exposes only `health` by default. If the application sets `management.endpoints.enabled-by-default=false`, enable it explicitly with `management.endpoint.liquibase.enabled=true`. HTTP exposure and access permissions are separate configuration layers; `exclude` takes precedence over `include`. [Actuator endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

The example does not add Spring Security. In an authenticated application, the caller must also satisfy the active access policy; adding an endpoint name to `include` does not automatically grant user permissions.

### 3.3. Two Change Sets with a Dependency Relationship

`src/main/resources/db/changelog/changelog.json`:

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "001-create-note",
        "author": "lab",
        "comment": "Create the note table",
        "changes": [
          {
            "createTable": {
              "tableName": "note",
              "columns": [
                {
                  "column": {
                    "name": "id",
                    "type": "BIGINT",
                    "constraints": {
                      "primaryKey": true,
                      "nullable": false
                    }
                  }
                },
                {
                  "column": {
                    "name": "title",
                    "type": "VARCHAR(200)",
                    "constraints": {
                      "nullable": false
                    }
                  }
                }
              ]
            }
          }
        ]
      }
    },
    {
      "changeSet": {
        "id": "002-add-status",
        "author": "lab",
        "comment": "Add note status",
        "changes": [
          {
            "addColumn": {
              "tableName": "note",
              "columns": [
                {
                  "column": {
                    "name": "status",
                    "type": "VARCHAR(20)",
                    "defaultValue": "DRAFT",
                    "constraints": {
                      "nullable": false
                    }
                  }
                }
              ]
            }
          }
        ]
      }
    }
  ]
}
```

The first change set creates the table with two columns; the second change set adds `status` to the existing table. `createTable` and `addColumn` are the corresponding Liquibase change types. [createTable](https://docs.liquibase.com/change-types/create-table.html), [addColumn](https://docs.liquibase.com/change-types/add-column.html)

Do not rely on numeric prefixes in `id` as an automatic sorting mechanism: in the example, order comes from how change sets are declared in the changelog.

### 3.4. Startup Code and Schema Evidence

`src/main/java/lab/liquibase/LiquibaseReadApplication.java`:

```java
package lab.liquibase;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class LiquibaseReadApplication {

    public static void main(String[] args) {
        SpringApplication.run(LiquibaseReadApplication.class, args);
    }

    @Bean
    ApplicationRunner showNoteColumns(JdbcTemplate jdbc) {
        return args -> {
            String sql = """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'PUBLIC'
                      AND TABLE_NAME = 'NOTE'
                    ORDER BY ORDINAL_POSITION
                    """;
            var columns = jdbc.queryForList(sql, String.class);
            System.out.println("note-columns=" + columns);
        };
    }
}
```

The check reads H2 metadata after application initialization. H2 stores column metadata and column order in `INFORMATION_SCHEMA.COLUMNS`. [H2 system metadata](https://h2database.com/html/systemtables.html)

In the practice directory, with Gradle 8.5 and JDK 21 available:

```shell
gradle run
```

You can use `./gradlew run` or `.\gradlew.bat run` if the project already has a matching Gradle Wrapper. With a fresh database and the two change sets above, the line printed by the example code itself is:

```text
note-columns=[ID, TITLE, STATUS]
```

The console also contains Boot, HikariCP, and Liquibase logs. That line verifies the columns are present; the next step uses Actuator to inspect the history Liquibase recorded.

## 4. Sending a Request and Reading the Response Structure

Keep the application running and open a second terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/liquibase
```

In PowerShell, use `curl.exe` if `curl` is mapped to another command. A successful request returns HTTP 200 with JSON. The following example retains only identifying and execution-type fields for easy reading:

```json
{
  "contexts": {
    "application": {
      "liquibaseBeans": {
        "liquibase": {
          "changeSets": [
            {
              "id": "001-create-note",
              "author": "lab",
              "execType": "EXECUTED"
            },
            {
              "id": "002-add-status",
              "author": "lab",
              "execType": "EXECUTED"
            }
          ]
        }
      }
    }
  }
}
```

This is a **response excerpt**, not the verbatim full JSON. The actual response also includes the changelog path, checksum, timestamps, execution order, and other metadata. `application` is a common context ID in simple apps; `liquibase` is the default bean name in the example. The structure is specified by the [Boot 3.3 Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html).

Read from outside in:

```text
contexts
    -> Spring ApplicationContext identifier
        -> liquibaseBeans
            -> Liquibase bean name
                -> changeSets
                    -> per-change-set details
```

Do not assume every application has exactly one context or one bean. A system using multiple data sources may have multiple Liquibase configurations; identify the exact data branch before comparing.

## 5. Understanding Fields Without Misinterpreting Their Meaning

### 5.1. Identifiers and Descriptions

| Field | How to Use |
| --- | --- |
| `id`, `author`, `changeLog` | Match the full change set identity. |
| `description` | Description of change types, usually generated from declared changes. |
| `comments` | Author comments. |
| `contexts`, `labels` | Conditional/context metadata of the change set. |
| `tag` | History milestone tag, if any. |

The `changeLog` value is the path recorded by Liquibase. It can be affected by packaging, declared path, or logical path configuration; read the actual value instead of reconstructing it from a short filename. The default history table stores corresponding columns such as `ID`, `AUTHOR`, `FILENAME`, `DESCRIPTION`, `COMMENTS`. [Identity and history columns](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

There are two meanings of `contexts` in the same document:

- `contexts` at the JSON root are **Spring ApplicationContexts**.
- `contexts` inside a change set are **Liquibase context metadata**.

They also do not automatically equal Spring profiles like `dev` or `prod`. To know which filters were actually active, read the Liquibase configuration for that specific deployment.

### 5.2. Timestamp, Deployment Batch, and Order

`dateExecuted` indicates the recorded timestamp; `deploymentId` helps correlate change sets belonging to the same deployment run; `orderExecuted` is the recorded execution sequence. Do not treat `id` as an auto-increment sequence number, or `orderExecuted` as a single global counter shared across all environments and runs.

When investigating historical order, cross-check both timestamp and order instead of sorting by a single number. Liquibase only guarantees `ORDEREXECUTED` increases within a single update; separate updates should not be inferred as a single continuous global sequence. [Meaning of DATEEXECUTED, ORDEREXECUTED, and DEPLOYMENT_ID](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

Timestamps and deployment IDs depend on runtime. Therefore, this article does not show fake timestamps for you to match as fixed outputs.

### 5.3. `execType` Is Not Only `EXECUTED`

The Boot 3.3 REST contract lists the values `EXECUTED`, `FAILED`, `SKIPPED`, `RERAN`, `MARK_RAN`. [The execType field in the API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html)

How to approach reading them:

- `EXECUTED`: history records that the change set was executed.
- `RERAN`: the change set was re-executed; examine policies like `runOnChange`/`runAlways` and related deployment history.
- `MARK_RAN`: marked as ran; do not treat this as evidence that table-creation/column-addition statements actually ran during that operation.
- `FAILED` or `SKIPPED`, if present: inspect configuration, preconditions, and logs to explain rather than lumping them into the success bucket.

Having `FAILED` in the contract does not mean the endpoint retains every failed migration attempt. A startup failure can prevent the application from serving HTTP; history might also lack the new row you are looking for.

Liquibase generally tries to execute a change set inside a transaction when the database supports it, though DDL transactionality depends on the database engine and configuration. Therefore, a failure must be cross-checked against both logs and actual schema state. [runInTransaction](https://docs.liquibase.com/reference-guide/changelog-attributes/runintransaction)

### 5.4. What Does Checksum Tell You?

`checksum` is a value Liquibase uses to track change set contents. It is not a checksum of the entire changelog file and not a hash of the entire existing schema. The prefix in a checksum string also relates to the algorithm version. [Change set checksums](https://docs.liquibase.com/concepts/changelogs/changeset-checksums.html)

Therefore:

1. Having checksums in the endpoint does not prove the database was never modified outside Liquibase.
2. Two results with different checksums must be compared against exact identity, Liquibase version, and deployed content.
3. Reading the endpoint does not replace validating the current changelog against history stored in the database.

For ordinary already-deployed change sets, add a new change set for subsequent changes. Editing old content can trigger checksum validation errors. `runOnChange` is an intentional mechanism for suitable cases, not a switch to enable broadly to silence errors. [runOnChange rules](https://docs.liquibase.com/reference-guide/changelog-attributes/runonchange)

## 6. Filtering Information When Responses Are Large

If `jq` is installed, you can extract the rows you need to inspect. The following example is for Bash and preserves both context and bean identifiers:

```bash
curl -fsS http://127.0.0.1:8080/actuator/liquibase \
  | jq '[
      .contexts | to_entries[] as $ctx
      | $ctx.value.liquibaseBeans | to_entries[] as $bean
      | $bean.value.changeSets[]
      | {
          context: $ctx.key,
          bean: $bean.key,
          changeLog: .changeLog,
          id: .id,
          author: .author,
          execType: .execType
        }
    ]'
```

`to_entries` preserves object key names so the output does not lose context and bean origin. These filtering/projection operations are described in the [jq manual](https://jqlang.org/manual/). When using this for deployment checks, match the tuple `changeLog`, `id`, `author` of the exact data source.

For this article's single-bean project, you can quickly inspect the list of IDs:

```bash
curl -fsS http://127.0.0.1:8080/actuator/liquibase \
  | jq '[.contexts[].liquibaseBeans[].changeSets[].id] | sort'
```

Expected output on a fresh practice database:

```json
[
  "001-create-note",
  "002-add-status"
]
```

The command sorts strings for stable presentation; that is not migration execution order. This short ID list is only a quick check for the practice article, not a replacement for full identifiers in multi-changelog systems.

## 7. Procedure for Verifying a Deployment

### 7.1. Identify the Right Target Before Reading History

Record the queried application/instance, environment, context, Liquibase bean, and associated data source configuration. Liquibase configuration may use `@LiquibaseDataSource` or `spring.liquibase.url/user/password` properties to select a dedicated data source. [Selecting a DataSource for Liquibase](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html)

This matters when the endpoint shows all change sets yet business queries cannot find the table: the two operations may be looking at two different databases or two different schemas.

### 7.2. Cross-Check Three Layers of Evidence

For the article's example:

1. **Deployment source:** the changelog has `001-create-note` then `002-add-status`, both with author `lab`.
2. **Recorded history:** the matching Liquibase branch has both identifiers with the expected execution type.
3. **Actual schema:** the metadata query in Java returns `ID`, `TITLE`, `STATUS`.

If the three layers disagree, pinpoint which layer diverges before changing configuration. For instance, seeing `MARK_RAN` while missing a column is a different situation from the migration never having been deployed to that database.

You can query the history table directly with a SQL client connected to the right target:

```sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE,
       DATEEXECUTED, ORDEREXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
```

That is the default table name. If the project changed the history table name or its schema, use the corresponding configuration. With file-based H2 currently open by the application, another SQL process may not be able to open the same file; in the experiment, you can stop the application and then connect to that exact file to read it.

### 7.3. Things the Endpoint Does Not Confirm on Its Own

This endpoint does not provide a complete list of all pending changes in the current changelog, does not check all schema drift, does not test rollback capability, and does not retain full audit-level event history.

When you need to find undeployed change sets, use the proper Liquibase workflow, such as the `status` command with the exact changelog, connection, and filters. `status` is designed to list undeployed change sets. [status command](https://docs.liquibase.com/commands/change-tracking/status.html)

When you need to check changelog structure, use the validation step matching your version. Even if `validate` passes, it does not guarantee all SQL will execute cleanly on the target database engine. [Scope of validate](https://docs.liquibase.com/commands/utility/validate.html)

Do not use `clear-checksums`, marking history, or rollback merely to make a check output look as expected. First understand the root cause of the discrepancy and the impact on data.

## 8. Practice Adding One More Change and Re-Reading

After the first run, stop the application. Add a **new element** after the second change set in the `databaseChangeLog` array of the same JSON file; place the comma properly between elements:

```json
{
  "changeSet": {
    "id": "003-add-source",
    "author": "lab",
    "comment": "Add note source",
    "changes": [
      {
        "addColumn": {
          "tableName": "note",
          "columns": [
            {
              "column": {
                "name": "source",
                "type": "VARCHAR(20)",
                "defaultValue": "manual",
                "constraints": {
                  "nullable": false
                }
              }
            }
          ]
        }
      }
    ]
  }
}
```

The JSON snippet above is one element to append to the changelog, not a standalone root changelog. Keep the two already-applied change sets intact, then run again from the **same working directory** to connect to the same previous H2 file.

Expected results:

- The metadata line becomes `note-columns=[ID, TITLE, STATUS, SOURCE]`.
- The endpoint now also includes `003-add-source` with author `lab` and the corresponding execution type.
- The two original change sets remain present by their identifiers; under the example's normal configuration, they are not re-executed merely because the application restarted.

Calling GET multiple times only reads history; it does not add new columns or increase the number of history records. If the application fails to start due to the changelog, start with startup logs rather than waiting for the endpoint to return a failure record.

## 9. Symptom-Based Troubleshooting

| Symptom | What to Check |
| --- | --- |
| 404 at `/actuator/liquibase` | Check URL, port/base path, endpoint enablement, HTTP exposure, and matching Liquibase bean. |
| 401 or 403 | Check endpoint authentication and authorization. |
| Unreachable after deployment | Check process status and startup logs, including connection or migration errors. |
| Expected change set missing | Right database/schema/changelog/profile/filters and deployed build? |
| History has record but table/column missing | Check `execType`, exact schema, and whether schema was modified outside Liquibase. |
| Checksum error | Cross-check identifier, old content, Liquibase version, and rerun policy. |
| Endpoint errors when reading | Check connection, permissions to read history table, and application logs. |

HTTP 200 only indicates the read request succeeded in that context. Concluding "the database deployment is right" requires tying expected change sets to related schema/data evidence.

Returned information can expose table names, changelog paths, and internal comments. Grant read permissions based on operational need and store connection credentials in appropriate secret configuration.

## 10. Knowledge Self-Check

1. Why shouldn't you use `id` alone to compare change sets between two changelogs?
2. How does `contexts` at the JSON root differ from `contexts` inside a change set?
3. Why is `MARK_RAN` not enough to prove the SQL actually ran?
4. Do checksums detect every manual schema change?
5. If a migration prevents the application from starting, why can't you rely on the endpoint to see the full error?
6. What additional evidence beyond HTTP 200 is needed to confirm a new column exists in the exact target database?

A complete answer connects identity, data source, execution history, and actual structure; that is how to use the `liquibase` endpoint to verify a change on solid grounds.
