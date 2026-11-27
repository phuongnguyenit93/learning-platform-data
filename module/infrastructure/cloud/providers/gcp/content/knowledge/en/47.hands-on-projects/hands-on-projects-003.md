# Spring Boot REST API Project on Cloud Run and Cloud SQL

In this project, learners build and deploy a **Java Spring Boot REST API** for task management (Task API), using **Cloud SQL for PostgreSQL** as the database and **Cloud Run** as the application runtime platform. Rather than deploying a single "Hello World" endpoint, we go through the full lifecycle: organizing a Google Cloud project, designing data and source code, authentication and authorization, testing, creating the database, managing passwords, building/deploying, calling the API, observing behavior, optimizing cost, and tearing down resources.

This is a hands-on exercise in the **CLOUD_PROVIDERS_GCP** module: learners apply knowledge of projects, IAM, and VPC together with Compute Engine/GKE/Cloud Run, storage, databases, release automation, and reliability/cost monitoring. The project chooses Cloud Run because a stateless HTTP app does not require managing VMs or clusters; it chooses Cloud SQL because SQL transactions and relational data are needed. Examples use **Java 21**, **Spring Boot 3.5.x**, **Maven**, **PostgreSQL 16**, and **Cloud SQL Java Connector**. In real usage, check runtime support schedules and dependency patches at deployment time.

> **Lab Boundaries:** The `gcloud` commands in this lesson are instructions for learners to run deliberately on **their own sandbox project**. They can create resources that **incur charges**, especially the Cloud SQL instance. This lesson does not automatically execute commands, does not create resources in the learner's account, and never requires placing credentials or passwords into source control.

## 1. Learning Outcomes

After completing this project, learners will be able to:

1. Structure a REST API consisting of controller, repository, model, and database migration.
2. Design endpoints to create, list, view, complete, and delete tasks.
3. Validate input data, return appropriate HTTP statuses, and avoid unsafe SQL string concatenation.
4. Run the application with local PostgreSQL and write automated tests using JUnit 5/Testcontainers.
5. Create a Cloud SQL PostgreSQL instance and database in an authorized GCP project.
6. Use Cloud SQL Java Connector to connect to Cloud SQL via IAM over an encrypted connection; distinguish IAM from PostgreSQL login privileges.
7. Store the DB password in Secret Manager instead of code, Docker images, or Git.
8. Create a least-privilege Cloud Run service account and deploy the app from source via Cloud Build/buildpacks.
9. Call the authenticated API, inspect logs/metrics, calculate a connection budget, troubleshoot errors, and roll back revisions.
10. Delete in-scope resources after the lab to avoid ongoing charges.

### 1.1. API Specification

| Method | Path | Meaning | Expected Result |
|---|---|---|---|
| `POST` | `/api/tasks` | Create a task | `201 Created` and new object |
| `GET` | `/api/tasks` | List up to 100 latest tasks | `200 OK` |
| `GET` | `/api/tasks/{id}` | View details | `200 OK` or `404 Not Found` |
| `PATCH` | `/api/tasks/{id}/complete` | Mark as completed | `200 OK` or `404 Not Found` |
| `DELETE` | `/api/tasks/{id}` | Delete a task | `204 No Content` or `404 Not Found` |
| `GET` | `/actuator/health` | Check process readiness | `200 OK` when healthy |

The API uses JSON, UTF-8 encoding, and UTC timestamps. To avoid unbounded queries, the list endpoint in this exercise version returns at most 100 records. Extensions add cursor-based pagination and user-level authentication/authorization.

### 1.2. Target Architecture

~~~mermaid
flowchart LR
    Dev[Developer / CI] -->|Source deployment| Build[Cloud Build + buildpacks]
    Build --> Reg[Artifact Registry image]
    Reg --> Run[Cloud Run tasks-api]
    Caller[Authenticated caller] -->|HTTPS + ID token| Run
    Run -->|ADC / Cloud SQL Java Connector| SQL[(Cloud SQL PostgreSQL)]
    Secret[Secret Manager: DB password] -->|Cloud Run secret reference| Run
    SA[Runtime service account] -->|IAM Cloud SQL Client + Secret Accessor| Run
    Run --> Logs[Cloud Logging / Monitoring]
~~~

**Request path:** authorized caller invokes Cloud Run → Spring Boot controller → JdbcTemplate/HikariCP → PostgreSQL database. Cloud Run may spin up additional instances as traffic rises; each instance opens its own connection pool, so total database connections must be bounded.

**Deployment path:** source repository → Cloud Build/buildpacks → container image in Artifact Registry → Cloud Run revision. Cloud Run stores no business state; the database on Cloud SQL is the authoritative data store.

## 2. Requirements and Safety Conditions

### 2.1. Local Tools

- JDK 21 and Maven or Maven Wrapper; verify with `java -version` and `./mvnw -version`.
- Docker/Podman to run local PostgreSQL and Testcontainers.
- Google Cloud CLI (`gcloud`) signed in.
- An HTTP client such as `curl`, HTTPie, or Postman.
- A Java IDE/editor and basic familiarity with Maven, SQL, and Spring MVC.

If running on Windows, use PowerShell equivalents or WSL for the Bash shell examples. `export`, `$(...)`, and line continuation `\` are written for Bash, not for direct pasting into PowerShell 5.1.

### 2.2. GCP Project and Billing

Use a **dedicated GCP lab project**, not a production project. Learners need permissions to enable services and create Cloud SQL instances, service accounts, secrets, and Cloud Run deployments; in organizational environments, a platform admin may provision these steps.

| Item | Typically Required Role/Permission | Scope |
|---|---|---|
| Enable APIs | Service Usage Admin or equivalent | Lab project |
| Create Cloud SQL | Cloud SQL Admin or custom role | Lab project |
| Create runtime identity | Service Account Admin | Lab project |
| Deploy Cloud Run | Cloud Run Admin/Developer, Service Account User | Service/project |
| Source build | Cloud Run Source Developer and appropriate build service account | Lab project |
| Read secret at runtime | Secret Manager Secret Accessor | Single secret |
| Connect to Cloud SQL via connector | Cloud SQL Client | Project hosting instance |
| Invoke private service | Cloud Run Invoker | Specific service |

Do not grant `Owner` or `Editor` to the runtime service account to "fix" permission errors. The **deployer**, **build identity**, and **runtime identity** roles have distinct responsibilities.

### 2.3. Expected Costs

Cloud Run bills per resource/request, whereas a **Cloud SQL instance incurs charges even with zero requests**, alongside storage, backups, networking, builds, and logging. Enable Cloud Billing budgets/alerts on the lab project; a budget alert is **not a hard cap**. Prepare to delete resources promptly upon completion.

### 2.4. Sample Parameters

The following variables are used consistently throughout the lesson:

~~~bash
export PROJECT_ID="YOUR_UNIQUE_GCP_PROJECT_ID"
export REGION="asia-southeast1"
export SERVICE="tasks-api"
export SQL_INSTANCE="tasks-pg-lab"
export DB_NAME="tasksdb"
export DB_USER="tasks_app"
export SA_NAME="tasks-api-runtime"
export SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
export INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$SQL_INSTANCE"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
~~~

Replace placeholder values with your authorized project and region. Cloud Run and Cloud SQL are placed in the **same region** to reduce latency, network cost, and cross-region dependencies. In production, region selection must satisfy data residency, quota, service availability, HA/DR, and SLOs.

## 3. Preparing the GCP Project and APIs

### 3.1. Checking Identity and Project

~~~bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
gcloud auth list
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"
~~~

`gcloud auth login` authenticates the CLI. Java client libraries use **Application Default Credentials (ADC)**, which may differ from the CLI identity. Inside Cloud Run, ADC is automatically obtained from the **runtime service account**; no JSON key copy is required.

### 3.2. Enabling APIs

~~~bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
~~~

If an organization policy blocks an API or quota, pause for administrator approval; do not switch to a production project as a workaround. Enabling APIs requires the appropriate Service Usage role.

### 3.3. Billing and Guardrails

Before creating the database:

1. Verify the project is linked to the proper test billing account.
2. Create a budget and notify the owner.
3. Identify who has permission to delete the Cloud SQL instance after the session.
4. Review Cloud SQL pricing in the target region and confirm the sizing is minimal enough for the lab.
5. Follow a naming convention with a lab suffix, and avoid storing customer data.

Never delete or modify resources with the same name in another project; always pass `--project="$PROJECT_ID"` or verify the active project in admin commands.

## 4. Creating the Spring Boot Project with Maven

### 4.1. Recommended Directory Structure

~~~text
tasks-api/
├── pom.xml
├── mvnw
├── .mvn/
├── project.toml
├── src/
│   ├── main/
│   │   ├── java/com/example/tasks/
│   │   │   ├── TasksApplication.java
│   │   │   ├── TaskDtos.java
│   │   │   ├── TaskRepository.java
│   │   │   ├── TaskController.java
│   │   │   └── CloudSqlDataSourceConfig.java
│   │   └── resources/
│   │       ├── application.yml
│   │       └── db/migration/V1__create_tasks.sql
│   └── test/java/com/example/tasks/
│       └── TaskApiIntegrationTest.java
└── .gitignore
~~~

The code blocks below correspond to the files of the same name. You can generate a skeleton via [Spring Initializr](https://start.spring.io/) with Java 21, Maven, Spring Web, JDBC, Validation, Actuator, and PostgreSQL, or start with an empty Maven project and populate the configuration below.

### 4.2. Maven pom.xml

This example pins Spring Boot 3.5.16 (an actual release in the 3.5 line) and Cloud SQL Java Connector 1.30.0. These versions are for the **lab at the time of writing**; in production, evaluate security advisories, compatibility, and newer patches. Do not use a `LATEST` placeholder version in builds.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>tasks-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
      <groupId>org.flywaydb</groupId>
      <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud.sql</groupId>
      <artifactId>postgres-socket-factory</artifactId>
      <version>1.30.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>postgresql</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
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
~~~

The Spring Boot parent manages many dependency and plugin versions; override only with sound control requirements. Commit the Maven Wrapper to the repository so CI and developers use the exact same Maven version.

### 4.3. Main Class

File `src/main/java/com/example/tasks/TasksApplication.java`:

~~~java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TasksApplication {
    public static void main(String[] args) {
        SpringApplication.run(TasksApplication.class, args);
    }
}
~~~

### 4.4. DTOs and Validation

File `src/main/java/com/example/tasks/TaskDtos.java`:

~~~java
package com.example.tasks;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;

record CreateTaskRequest(
        @NotBlank @Size(max = 200) String title) {
}

record TaskResponse(
        long id, String title, boolean completed, Instant createdAt) {
}
~~~

Both records are used within the same package, so they can be package-private in a single file. Validation triggers when the controller uses `@Valid`. Never interpolate user input directly into table or column names in SQL.

## 5. Designing the PostgreSQL Table and Migration

### 5.1. Schema

File `src/main/resources/db/migration/V1__create_tasks.sql`:

~~~sql
CREATE TABLE tasks (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_created_at
    ON tasks (created_at DESC, id DESC);
~~~

**Flyway** discovers migration files named `V1__*.sql` and tracks schema history in the `flyway_schema_history` table. When releasing a V2 migration, create a new file; never modify V1 after it has been applied to a shared environment. In production, run schema migrations via a dedicated deployment step or Cloud Run Job with its own database identity rather than letting every Cloud Run instance execute DDL during startup.

### 5.2. application.yml Configuration

File `src/main/resources/application.yml`:

~~~yaml
server:
  address: 0.0.0.0
  port: ${PORT:8080}

spring:
  application:
    name: tasks-api
  flyway:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot reads the `PORT` provided by Cloud Run or falls back to 8080 locally. Do not expose all Actuator endpoints to the Internet. Cloud Run request authentication only controls who can invoke the service; the application still needs domain-level authentication/authorization if serving multiple users with distinct permissions.

## 6. Repository: Safe SQL Queries

File `src/main/java/com/example/tasks/TaskRepository.java`:

~~~java
package com.example.tasks;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private static final RowMapper<TaskResponse> TASK_MAPPER =
            (rs, rowNumber) -> fromRow(rs);

    private final JdbcTemplate jdbc;

    public TaskRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<TaskResponse> findRecent() {
        return jdbc.query("""
                SELECT id, title, completed, created_at
                FROM tasks
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """, TASK_MAPPER);
    }

    public Optional<TaskResponse> findById(long id) {
        return jdbc.query("""
                SELECT id, title, completed, created_at
                FROM tasks WHERE id = ?
                """, TASK_MAPPER, id).stream().findFirst();
    }

    public TaskResponse create(String title) {
        Long id = jdbc.queryForObject(
                "INSERT INTO tasks(title) VALUES (?) RETURNING id",
                Long.class, title);
        return findById(id).orElseThrow();
    }

    public boolean complete(long id) {
        return jdbc.update(
                "UPDATE tasks SET completed = TRUE WHERE id = ?", id) == 1;
    }

    public boolean delete(long id) {
        return jdbc.update("DELETE FROM tasks WHERE id = ?", id) == 1;
    }

    private static TaskResponse fromRow(ResultSet rs)
            throws SQLException {
        return new TaskResponse(
                rs.getLong("id"),
                rs.getString("title"),
                rs.getBoolean("completed"),
                rs.getTimestamp("created_at").toInstant());
    }
}
~~~

The SQL queries use `?` placeholders and `JdbcTemplate` parameter binding rather than concatenating input into SQL strings. For larger applications, extract a service layer to hold business rules, transactions, authorization, and idempotency instead of keeping everything in the controller.

## 7. Controller: REST Endpoints and HTTP Semantics

File `src/main/java/com/example/tasks/TaskController.java`:

~~~java
package com.example.tasks;

import jakarta.validation.Valid;
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskRepository repository;

    public TaskController(TaskRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<TaskResponse> list() {
        return repository.findRecent();
    }

    @GetMapping("/{id}")
    public TaskResponse get(@PathVariable long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Task not found"));
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @Valid @RequestBody CreateTaskRequest request) {
        TaskResponse created =
                repository.create(request.title().trim());
        return ResponseEntity
                .created(URI.create("/api/tasks/" + created.id()))
                .body(created);
    }

    @PatchMapping("/{id}/complete")
    public TaskResponse complete(@PathVariable long id) {
        if (!repository.complete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Task not found");
        }
        return get(id);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (!repository.delete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Task not found");
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

### 7.1. Why These Status Codes?

- `201 Created` with `Location`: resource was created.
- `200 OK`: returns resource representation on successful GET/PATCH.
- `204 No Content`: deleted successfully with no response body.
- `400 Bad Request`: invalid input data caught by `@Valid`.
- `404 Not Found`: no task exists with the requested ID.
- `500 Internal Server Error`: unexpected failure, requiring logging and remediation; never return stack traces or SQL passwords to callers.

This simple lab app does not yet include standard pagination, user isolation, rate limiting, or concurrent edit protection. Those are extensions, not built-in properties provided automatically by Cloud Run.

## 8. Running and Testing with Local PostgreSQL

### 8.1. Running the PostgreSQL Container

Use the example password below **only on your local/test machine**; never use it for Cloud SQL or production:

~~~bash
docker run --rm -d \
  --name tasks-postgres-local \
  -e POSTGRES_DB=tasksdb \
  -e POSTGRES_USER=tasks_local \
  -e POSTGRES_PASSWORD=local-lab-only \
  -p 5432:5432 \
  postgres:16
~~~

Set environment variables and run the application:

~~~bash
export SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:5432/tasksdb"
export SPRING_DATASOURCE_USERNAME="tasks_local"
export SPRING_DATASOURCE_PASSWORD="local-lab-only"

./mvnw spring-boot:run
~~~

When running locally without the `cloud` profile enabled, Spring Boot auto-configures the `DataSource` from these environment variables. Flyway creates the `tasks` table in the local database. If port 5432 is already in use, update the Docker port mapping and JDBC URL accordingly.

### 8.2. Calling the Local API

~~~bash
curl -i http://localhost:8080/actuator/health

curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Write Spring Boot documentation"}'

curl -s http://localhost:8080/api/tasks
curl -s http://localhost:8080/api/tasks/1
curl -i -X PATCH http://localhost:8080/api/tasks/1/complete
curl -i -X DELETE http://localhost:8080/api/tasks/1
~~~

ID `1` only applies if this is the first record. On a database with existing data, read the `id` from the POST response instead of assuming it.

### 8.3. Manual Verification Matrix

| Action | Expected |
|---|---|
| POST valid title | 201, has ID, `completed=false` |
| GET created ID | 200, matching content |
| PATCH complete | 200, `completed=true` |
| DELETE by ID | 204 |
| GET after DELETE | 404 |
| POST blank title | 400, no record created |
| POST title longer than 200 chars | 400 |

## 9. Automated Integration Testing with Testcontainers

Testcontainers runs an ephemeral PostgreSQL container during tests, verifying Flyway, JDBC, and REST endpoints without requiring live GCP resources.

File `src/test/java/com/example/tasks/TaskApiIntegrationTest.java`:

~~~java
package com.example.tasks;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.http.ResponseEntity;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskApiIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16");

    @Autowired
    TestRestTemplate http;

    @Test
    void createThenReadTask() {
        ResponseEntity<TaskResponse> created =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest("test from JUnit"),
                        TaskResponse.class);

        assertThat(created.getStatusCode().value()).isEqualTo(201);
        assertThat(created.getBody()).isNotNull();

        long id = created.getBody().id();
        TaskResponse loaded =
                http.getForObject("/api/tasks/" + id,
                        TaskResponse.class);

        assertThat(loaded.title()).isEqualTo("test from JUnit");
        assertThat(loaded.completed()).isFalse();
    }
}
~~~

Run:

~~~bash
./mvnw -B clean verify
~~~

Note: Docker must be running for Testcontainers to start PostgreSQL. Even if a local Docker container is running on port 5432, `@ServiceConnection` wires the test container's datasource rather than your development database. This test verifies REST + real PostgreSQL, **not IAM, networking, or Cloud SQL**; a post-deploy smoke/integration test on the GCP project is still required.

### 9.1. Additional Tests to Add

- POST blank title and title exceeding 200 characters → 400.
- GET/PATCH/DELETE with a non-existent ID → 404.
- Create multiple tasks, verify ordering and the 100-item limit.
- Test concurrent updates and transactions as business rules grow.
- Test Flyway migrations on a clean database.
- Test database timeout errors and health behavior.
- Test that passwords or secret values are never written to logs.

## 10. Creating Cloud SQL PostgreSQL in the Lab Project

### 10.1. Creating the Instance

This step **incurs continuous charges**; confirm project/region before running:

~~~bash
gcloud sql instances create "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-custom-1-3840 \
  --region="$REGION" \
  --storage-size=10 \
  --assign-ip
~~~

This example uses a small lab instance sizing, not a production template. Depending on quotas, organizational policies, region, and catalog changes, the tier may need adjustment. For production environments, evaluate HA, backups/PITR, maintenance windows, deletion protection, private IP, and DR rather than reusing the lab configuration as-is.

### 10.2. Checking Status and Connection Name

~~~bash
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="table(name,region,state,connectionName)"
~~~

The connection name has the form `PROJECT_ID:REGION:INSTANCE`. It is not a password. The Cloud SQL Java Connector uses this name to locate the instance, fetch connection metadata, and establish an authenticated/encrypted connection.

### 10.3. Creating the Database

~~~bash
gcloud sql databases create "$DB_NAME" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

### 10.4. Creating the PostgreSQL User

In the Console, select the Cloud SQL instance → **Users** → create a built-in PostgreSQL user named `tasks_app` with a **strong, lab-unique password**. Alternatively, create the user via `gcloud` and set the password with an interactive prompt so the password never enters shell history:

~~~bash
gcloud sql users create "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID"

gcloud sql users set-password "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --prompt-for-password
~~~

Never print passwords to logs or commit them to Git. The first command creates the user, but password authentication will not work until the password is set. If Cloud SQL organization policy or CLI version requires a different workflow, use the Console to create the user and set the password equivalently.

In the lab, this user needs enough privileges to create Flyway tables in `tasksdb`. In **production**, separate a **migration user** with DDL privileges from a **runtime user** restricted to SELECT/INSERT/UPDATE/DELETE on tables and USAGE on sequences; PostgreSQL privileges must be configured at the database/schema level, not solely via the `Cloud SQL Client` IAM role.

### 10.5. Public IP or Private IP?

This guide uses Cloud SQL **public IP** and the **Cloud SQL Java Connector** to keep the lab concise. Connecting through the connector uses IAM to authorize connection setup, encrypts transport, and still performs database authentication. It does not mean opening PostgreSQL freely to the Internet; never configure overly broad authorized networks such as `0.0.0.0/0`.

For production requiring private connectivity, use Cloud SQL private IP/PSC per architecture along with **Cloud Run Direct VPC egress** or Serverless VPC Access as appropriate. When choosing private IP in the Java connector, set `ipTypes=PRIVATE` and ensure the network path exists. **The connector does not create network paths if VPC routes do not exist.**

## 11. Storing the DB Password in Secret Manager

### 11.1. Creating the Secret

~~~bash
gcloud secrets create tasks-db-password \
  --project="$PROJECT_ID" \
  --replication-policy=automatic
~~~

In the Google Cloud Console → **Secret Manager** → `tasks-db-password` → **Add new version**, enter the exact password set for DB user `tasks_app`. Entering via the UI avoids placing plaintext passwords in command arguments and shell history. Note the new version (typically `1` for a new secret).

In automated environments, use an appropriate secret provisioning pipeline or stdin/secret manager integration; never put passwords in YAML/source code, Dockerfiles, build logs, or `--set-env-vars`.

### 11.2. Creating the Runtime Service Account

~~~bash
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run tasks-api runtime"
~~~

### 11.3. Granting Scoped Permissions

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/cloudsql.client"

gcloud secrets add-iam-policy-binding tasks-db-password \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
~~~

`roles/cloudsql.client` enables Cloud SQL connectivity; it **does not replace** PostgreSQL user credentials or internal SQL privileges. Secret Accessor is granted **on a single secret**, not across all project secrets. Never grant Cloud SQL Admin or Secret Manager Admin to the runtime just because the application needs to read/write tasks.

## 12. Connecting via JDBC from Cloud Run Using Cloud SQL Java Connector

Use Cloud SQL Java Connector as a socket factory for the PostgreSQL JDBC driver. It uses the **runtime service account's ADC** to authenticate to Cloud SQL, requiring no JSON credential files.

### 12.1. DataSource Configuration for the cloud Profile

File `src/main/java/com/example/tasks/CloudSqlDataSourceConfig.java`:

~~~java
package com.example.tasks;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("cloud")
public class CloudSqlDataSourceConfig {
    @Bean
    DataSource dataSource(
            @Value("${DB_NAME}") String database,
            @Value("${DB_USER}") String username,
            @Value("${DB_PASS}") String password,
            @Value("${INSTANCE_CONNECTION_NAME}") String instance) {

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql:///" + database);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000);
        config.setIdleTimeout(600000);
        config.setMaxLifetime(1800000);

        config.addDataSourceProperty(
                "socketFactory",
                "com.google.cloud.sql.postgres.SocketFactory");
        config.addDataSourceProperty(
                "cloudSqlInstance", instance);
        config.addDataSourceProperty("ipTypes", "PUBLIC");
        config.addDataSourceProperty(
                "cloudSqlRefreshStrategy", "lazy");

        return new HikariDataSource(config);
    }
}
~~~

In **cloud** mode, the `DataSource` bean is built from `DB_NAME`, `DB_USER`, `DB_PASS`, and `INSTANCE_CONNECTION_NAME`. In local/test mode, the `cloud` profile is inactive so Spring Boot uses auto-configuration with `SPRING_DATASOURCE_URL` or Testcontainers.

Google Cloud recommends `cloudSqlRefreshStrategy=lazy` for serverless workloads to avoid background refresh threads running when CPU is not continuously allocated. `ipTypes=PUBLIC` fits the public-IP Cloud SQL lab; switch to `PRIVATE` only after creating a private IP and VPC egress path.

**Do not accidentally mix two mechanisms:** the Java Connector connects via the configured socket factory; `--add-cloudsql-instances` is not required just to mount a Unix socket in this example. If you choose Cloud Run's built-in Cloud SQL connection/Unix socket instead of the Java Connector, JDBC configuration and socket mounting differ.

### 12.2. Calculating the Connection Pool Budget

For example, with Cloud Run `--max-instances=3` and Hikari `maximumPoolSize=5` per instance:

\[
\text{MaxConnections}_{\text{API}} \approx
3 \times 5 = 15 .
\]

You must also add migrations, admin sessions, jobs, and other services sharing the Cloud SQL instance. Raising `max-instances` to 50 while leaving pool size at 20 could demand up to 1,000 connections, exceeding instance capacity. Use load testing, timeouts, backpressure, or dedicated connection pooling as appropriate instead of blindly raising application limits.

### 12.3. Flyway at Runtime

For the lab, Flyway runs schema migrations at application startup. For production:

- Separate Flyway into a CI/CD migration step or a Cloud Run Job with a DB DDL role.
- Run backward-compatible migrations before shifting traffic.
- Deploy the new image/revision only after migrations pass.
- Never alter an already-applied V1 migration.
- Verify database schema backups and rollback strategies for breaking changes.

## 13. Building and Deploying from Source to Cloud Run

### 13.1. Pinning the Java Runtime in Buildpacks

File `project.toml` at the repository root:

~~~toml
[[build.env]]
name = "GOOGLE_RUNTIME_VERSION"
value = "21"
~~~

Cloud Buildpacks reads this setting to pick the Java major version instead of silently choosing a newer default. Maven compiles with Java 21, and the runtime container also runs Java 21. When upgrading the JDK, check Spring Boot/dependency compatibility, class-file version, base image, and Cloud Run support schedules.

### 13.2. Build and Test Before Deploying

~~~bash
./mvnw -B clean verify
~~~

Do not skip tests in CI just to build faster. If a developer machine lacks Docker, fix the Testcontainers environment; do not remove integration tests without a replacement.

### 13.3. Build Identity Permissions

Deploying from source uses Cloud Build and Artifact Registry. Beyond the deployer's permissions (`roles/run.sourceDeveloper`, Service Account User on the runtime identity, and deploy permissions), the **Cloud Build service account** needs the corresponding build/deploy permissions, typically including `roles/run.builder` per Cloud Run documentation. Default build identities vary depending on project setup and organization policy.

If Cloud Build returns `PERMISSION_DENIED`, verify which identity is executing the build before granting roles. Never blindly grant `Owner`/`Editor` to the default service account.

### 13.4. Deployment Command

From the directory containing `pom.xml`:

~~~bash
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --source=. \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="SPRING_PROFILES_ACTIVE=cloud,DB_NAME=$DB_NAME,DB_USER=$DB_USER,INSTANCE_CONNECTION_NAME=$INSTANCE_CONNECTION_NAME" \
  --update-secrets="DB_PASS=tasks-db-password:1" \
  --no-allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=20 \
  --max-instances=3 \
  --min-instances=0
~~~

Explanation of flags:

- `--source=.`: Cloud Build/buildpacks builds an image from source, stores it in Artifact Registry, and deploys it.
- `--service-account`: assigns the dedicated runtime identity to the Cloud Run revision.
- `SPRING_PROFILES_ACTIVE=cloud`: activates the Cloud SQL Java Connector configuration.
- `--update-secrets`: Cloud Run injects the DB password from Secret Manager on instance startup.
- `--no-allow-unauthenticated`: keeps the API private so only callers with Invoker permission can reach it.
- `--max-instances=3`: caps initial scaling to protect Cloud SQL.
- `--min-instances=0`: allows scaling to zero when idle, which may incur cold starts.

In production, deploy an immutable image digest that has already been built, tested, and scanned, promoting it across environments instead of rebuilding from source at each deployment. Depending on organization policies, Cloud Run source deployment may require additional Artifact Registry permissions, Cloud Build service account roles, quotas, or repository setup.

### 13.5. Checking Status

~~~bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="table(metadata.name,status.url,status.latestReadyRevisionName)"

gcloud run revisions list \
  --service="$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

If the service is not ready, inspect Cloud Logging before making arbitrary config changes. Common issues include missing secrets, wrong user/password, missing `Cloud SQL Client` role, Java connector failing to reach the IP, Flyway DDL rejection, or `PORT`/startup timeout issues.

## 14. Calling the Authenticated REST API

### 14.1. Granting Invoker to the Test Caller

The caller testing the API must be granted `roles/run.invoker` on the service. An administrator can run:

~~~bash
export TEST_CALLER_EMAIL="YOUR_ACCOUNT_EMAIL"

gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="user:$TEST_CALLER_EMAIL" \
  --role="roles/run.invoker"
~~~

Do not grant Invoker to `allUsers` if the lab intentionally tests a private service. For CI or service-to-service calls, grant it to a specific caller service account.

### 14.2. Retrieving the Service URL

~~~bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')"

echo "$SERVICE_URL"
~~~

### 14.3. Calling the API with an ID Token

~~~bash
export ID_TOKEN="$(gcloud auth print-identity-token)"

curl -i "$SERVICE_URL/actuator/health" \
  -H "Authorization: Bearer $ID_TOKEN"

curl -i -X POST "$SERVICE_URL/api/tasks" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Deploy Spring Boot on Cloud Run"}'

curl -s "$SERVICE_URL/api/tasks" \
  -H "Authorization: Bearer $ID_TOKEN"
~~~

Do not write tokens to files, shell history, or public logs. If organizational identity causes `gcloud auth print-identity-token` to mint a token with the wrong audience or lacking invoke access, use `gcloud run services proxy` or configure an identity token targeting the service audience. Service IAM authentication requires an **ID token**, not an arbitrary Google Cloud access token.

### 14.4. Expected Output

Example on successful POST:

~~~http
HTTP/1.1 201 Created
Location: /api/tasks/1
Content-Type: application/json

{
  "id": 1,
  "title": "Deploy Spring Boot on Cloud Run",
  "completed": false,
  "createdAt": "2026-11-19T08:00:00Z"
}
~~~

The ID and timestamp are examples. To prove persistence, issue a GET for the same task after the service scales down and back up or after deploying a new revision; the data must still exist in Cloud SQL.

## 15. End-to-End Testing and Acceptance Criteria

### 15.1. Functional Acceptance

| Test case | Input | Passing Result |
|---|---|---|
| Health | GET `actuator/health` | 200, status UP |
| Create task | POST JSON with valid title | 201, Location header, non-null id |
| Query task | GET newly created id | 200, accurate title and completed flag |
| List tasks | GET `/api/tasks` | 200, includes newly created task |
| Complete task | PATCH `/{id}/complete` | 200, `completed=true` |
| Delete task | DELETE `/{id}` | 204 |
| Unknown id | GET non-existent id | 404 |
| Validation | POST blank title | 400 |
| Private endpoint | Call without token | 401/403 per protection layer |
| Persistence | Deploy new revision and GET task | Data still exists |

### 15.2. Non-Functional Acceptance

- API does not leak passwords, stack traces, or sensitive JDBC URLs.
- Runtime service account holds only required permissions.
- Health checks and startup do not time out under normal conditions.
- Database reads/writes go through the secured connector.
- Cloud Run logs capture request method, status, and latency; application logs omit unnecessary PII.
- Database connection count stays within budget.
- Backup/restore plan and cost limits exist; lab teardown steps are documented.
- Revisions can be rolled back, and schema/database handling during rollback is defined.

## 16. Logging, Monitoring, and Troubleshooting

### 16.1. Viewing Cloud Run Logs

~~~bash
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100
~~~

In the Console, inspect the Cloud Run service → **Logs**, **Metrics**, and **Revisions**. Monitor request count, p95/p99 latency, 4xx/5xx rates, CPU/memory, instance count, and startup time. You can add Micrometer/OpenTelemetry and Cloud Trace as advanced extensions.

### 16.2. Inspecting Cloud SQL

Cloud SQL Console → instance → **Overview/Monitoring/Logs/Query Insights** (if enabled). Monitor active connections, CPU, disk space, transaction throughput, and query latency. Use logs to distinguish network issues, IAM connector failures, PostgreSQL password mismatches, and schema errors.

### 16.3. Error Troubleshooting Table

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cloud Run container fails readiness | App not listening on `PORT` or startup error | Logs, bind `0.0.0.0`, `server.port` |
| `Cloud SQL API has not been used` | API not enabled | Check `sqladmin.googleapis.com` |
| `PERMISSION_DENIED` from connector | Runtime SA missing `Cloud SQL Client` | Service identity and IAM policy |
| `password authentication failed` | Wrong `DB_USER`/`DB_PASS` | Secret version, Cloud SQL Users, PostgreSQL logs |
| `connection timed out` | Wrong IP path/region or network issue | Public IP, connector, private VPC egress |
| `relation "tasks" does not exist` | Flyway migration not applied | Flyway logs, schema, and `DB_NAME` |
| `permission denied for schema public` | DB user lacks DDL/USAGE privileges | Check SQL grants and migration identity |
| `too many clients already` | Pool × instances too large | Hikari settings, Cloud Run max instances, DB connections |
| 401/403 calling URL | Missing ID token or Invoker permission | Token audience, IAM, service URL |
| 400 on valid POST | Malformed JSON or validation mismatch | Request body, `Content-Type`, `@Valid` |
| 404 after delete | Expected per contract | GET on deleted id must return 404 |
| 500 after schema deploy | Incompatible migration | Check revision, Flyway history, and rollback plan |
| Build fails on permissions | Cloud Build identity missing role | Build history, `roles/run.builder`, artifact access |

**Never fix these by adding `--allow-unauthenticated`, opening authorized networks to the entire Internet, committing DB passwords, or granting Owner to the runtime.** Isolate the failure by layer and grant the exact permission or configuration needed.

## 17. Data Safety, Operations, and Reliability

### 17.1. Stateless Compute, Stateful Database

Cloud Run instances can be stopped or replaced at any time, so:

- Do not store task data in a static `Map` or in-memory database.
- Do not rely on the local filesystem for durable data.
- Do not store persistent application sessions in a single instance's RAM.
- Manage transactions and schema changes in Cloud SQL.
- Ensure the service supports graceful shutdown and sensible retries.

### 17.2. Backups, HA, and RPO/RTO

Lab Cloud SQL setups may be trimmed down, but production requires evaluating backups, PITR, HA, regional availability, maintenance windows, and DR. **A successful backup job does not replace a restore drill.** If strict RTO/RPO targets apply, design and rehearse recovery.

### 17.3. Handling Load Increases

Cloud Run autoscaling increases instance count, which can improve HTTP throughput while also increasing connection pools and IOPS on Cloud SQL. If the database is the bottleneck, adding Cloud Run instances can increase error rates. Measure p95/p99 latency, active/pending pool connections, DB CPU, and max connections before tuning concurrency.

### 17.4. End-User Authorization Model

The lab API is protected by Cloud Run Invoker at the service level and **does not yet implement per-task/per-user authorization**. When evolving into a multi-user API, add end-user authentication (OIDC/JWT/appropriate session), owner/tenant authorization, audit trails, rate limiting, command idempotency, and personal data protection.

## 18. CI/CD, Images, and Rollback

### 18.1. Recommended Pipeline

~~~mermaid
flowchart LR
    Git[Commit / PR] --> Build[Maven verify]
    Build --> Scan[Dependency / image scan]
    Scan --> Image[Build immutable image]
    Image --> Stage[Deploy staging]
    Stage --> Smoke[Integration + smoke tests]
    Smoke --> Prod[Controlled prod rollout]
    Prod --> Observe[Metrics / alerts]
~~~

In real CI/CD, use Cloud Build triggers or your organization's CI system, pinning Maven/JDK/plugin versions and image digests. Use a build/deploy service account separate from the runtime service account. Never auto-deploy to production from unapproved pull requests.

### 18.2. Cloud Run Revisions and Rollback

Cloud Run creates a new revision whenever configuration or the image changes. You can inspect revisions with:

~~~bash
gcloud run revisions list \
  --service="$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

When a new revision misbehaves, shift traffic back to a previously verified revision via the Console or `gcloud` traffic management. **Rolling back application code does not automatically roll back database schemas or written data.** Migrations must therefore be backward-compatible, with staged rollout plans.

### 18.3. Supply Chain Security

- Scan dependencies and images for CVEs; keep JDK and base images patched.
- Never bake secrets into images or build logs.
- Use Artifact Registry, least-privilege IAM, and record commit SHAs/image digests.
- Enforce provenance/SBOM and image signing policies where required by the organization.
- Isolate secrets, configuration, and build artifacts across dev/staging/prod.

## 19. Cleaning Up Resources and Ending the Lab

Cloud SQL continues billing even when Cloud Run receives zero requests. After capturing evidence and finishing the exercise:

### 19.1. Verify Project, Region, and Scope

~~~bash
gcloud config get-value project
gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

Verify these resources were **created specifically for the lab** and are not shared by another team or pipeline.

### 19.2. Delete the Cloud Run Service

~~~bash
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

### 19.3. Delete the Cloud SQL Instance

~~~bash
gcloud sql instances delete "$SQL_INSTANCE" \
  --project="$PROJECT_ID"
~~~

This command **destroys the database instance and its data**; do not run it without confirming scope, required backups, deletion protection, other clients, and ownership. If Cloud SQL deletion protection is enabled, follow approved administrative procedures rather than disabling protections in shared environments.

### 19.4. Delete the Secret and Service Account if Lab-Only

~~~bash
gcloud secrets delete tasks-db-password \
  --project="$PROJECT_ID"

gcloud iam service-accounts delete "$SA_EMAIL" \
  --project="$PROJECT_ID"
~~~

Also review Artifact Registry repositories/images and Cloud Build artifacts created by source deployment; retain or delete **only lab-specific artifacts** per retention/cost policy. Do not delete a repository shared across multiple services. Finally, check Cloud Billing to ensure no billable instances, disks, images, or services remain unintentionally.

## 20. Extension Exercises

1. **Pagination:** replace `LIMIT 100` with keyset pagination over `created_at` and `id`, returning a `nextPageToken`.
2. **Service layer:** add a `TaskService` holding transactions and business rules; keep the controller focused on HTTP.
3. **Authentication:** integrate Identity Platform or OIDC/JWT and enforce authorization by task owner.
4. **Idempotency:** add an `Idempotency-Key` header for POST so retries do not create duplicates.
5. **Audit:** record `created_by`, `updated_at`, `version`, and structured logs with trace IDs.
6. **Optimistic locking:** add a `version` column and return 409 when two clients edit the same task concurrently.
7. **CI/CD:** set up a Cloud Build trigger running Maven verify → scan → deploy staging → smoke test.
8. **Private IP:** migrate Cloud SQL to private connectivity with Cloud Run Direct VPC egress and `ipTypes=PRIVATE`.
9. **Migrations:** split Flyway into a deployment job with a DDL role; limit runtime to DML privileges only.
10. **Observability:** integrate OpenTelemetry, define a 99.9% availability SLO, and alert on error budget burn.
11. **Load testing:** test different concurrency and `max-instances` values while measuring DB connection saturation and p99 latency.
12. **DR:** back up and restore Cloud SQL to a test instance, verifying RPO/RTO.

## 21. Lab Acceptance Checklist

### Source Code and Tests

- [ ] `pom.xml`, Maven Wrapper, and Java 21 in place.
- [ ] Spring Boot runs locally with PostgreSQL in Docker.
- [ ] Flyway creates the `tasks` table and records migration history.
- [ ] REST endpoints match methods, status codes, and JSON contract.
- [ ] Validation returns 400 on invalid titles.
- [ ] JUnit/Testcontainers tests pass.
- [ ] No plaintext DB passwords or service account keys in Git.

### Google Cloud and Deployment

- [ ] Project/region/billing confirmed and budget alert enabled.
- [ ] Cloud SQL instance, database, and user belong to the lab project.
- [ ] Secret Manager holds the DB password; it is not baked into the image.
- [ ] Runtime service account has `Cloud SQL Client` and access only to the required secret.
- [ ] Cloud Run source deployment succeeded with Java 21 and the `cloud` profile.
- [ ] API is private; only callers granted Invoker can call it.
- [ ] Verified 201/200/204/400/404 responses and persistence across revisions.

### Operations and Cleanup

- [ ] Logs/metrics available to diagnose startup/database errors.
- [ ] Connection pool × max instances fits within the DB connection budget.
- [ ] HA, backup, DR, cost risks, and extension tests documented.
- [ ] Test evidence and service/revision details recorded.
- [ ] Unused lab resources deleted within exact scope.
- [ ] Verified no Cloud SQL instances continue incurring charges.

## 22. Official Documentation

- [Build and deploy a Java Spring Boot app to Cloud Run](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Deploy services from source code](https://cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [Cloud Run IAM authentication](https://cloud.google.com/run/docs/authenticating/overview)
- [Configure Cloud Run secrets](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Connect Cloud Run to Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Connect using Cloud SQL language connectors](https://cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory)
- [Cloud SQL PostgreSQL users](https://cloud.google.com/sql/docs/postgres/create-manage-users)
- [Cloud SQL IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL backup and recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/backup-options)
- [Cloud Build default and user-specified service accounts](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Spring Boot Data SQL](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot testing with Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Flyway documentation](https://documentation.red-gate.com/flyway)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)

## 23. Summary

Deploying a Spring Boot REST API successfully on GCP takes more than a running container. With Cloud Run and Cloud SQL, learners practice separating **stateless compute** from **stateful data**, managing database schemas, connecting via IAM/connectors, storing secrets securely, bounding connection pools, using Cloud Build, and verifying authenticated APIs. The project is complete when test results are verified, data persists across revisions, the learner understands security and operational responsibility boundaries, and **lab resources can be safely torn down**. This forms a foundation for extending applications toward CI/CD, HA, reliability observability, FinOps, and more complex cloud-native architectures.
