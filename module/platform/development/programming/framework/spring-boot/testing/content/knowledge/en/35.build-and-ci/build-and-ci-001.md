# Separating Unit, Slice, Integration, and End-to-End Test Groups

In a Spring Boot project, if every check runs in a single `./gradlew test` task, a small change may have to wait for dozens of Spring context startups, migrations, containers, HTTP servers, and test services. Slow CI lengthens the feedback loop; CI that relies too heavily on mocks can be very fast but let real Spring configuration, JPA, transaction, or API bugs slip through. Separating test groups is not just labeling tests "fast/slow": it is how you define **verified boundaries**, cost levels, data isolation responsibilities, and corresponding quality gates.

This Knowledge article **"Separating Unit, Slice, Integration, and End-to-End Test Groups"** belongs to the **Build and CI** section of the **Spring Boot – testing** module. We will build a **Java 17+, Spring Boot 3.5.16, Gradle, JUnit Jupiter 5, Mockito, MockMvc, JPA/H2, and Java HttpClient** project; organize the four groups using JUnit `@Tag`, run them with dedicated Gradle tasks `unitTest`, `sliceTest`, `integrationTest`, and `e2eTest`, and then configure GitHub Actions to run the fast group on pull requests, integration checks in CI, and E2E against an **independently packaged/started application**.

**Core principle:** *Unit tests verify Java rules; slice tests verify a slice of Spring integration; integration tests verify multiple real components working together; E2E tests verify journeys through the public interface of a running deployment.* A test does not become "integration" just because it is named `SomeIntegrationTest`; nor does it become "unit" just because it runs fast. What matters most is **which bugs the test can detect and which ones it cannot see**.

## 1. Learning Objectives

- Distinguish unit, slice, integration, and E2E tests by dependency boundary, type of evidence, and risk.
- Know when to choose `@WebMvcTest`, `@DataJpaTest`, `@RestClientTest`, `@JsonTest`, `ApplicationContextRunner`, `@SpringBootTest`, or plain JUnit.
- Use JUnit `@Tag("unit")`, `@Tag("slice")`, `@Tag("integration")`, and `@Tag("e2e")`.
- Configure Gradle `Test` tasks with explicit `testClassesDirs` and `classpath`; do not rely on implicit test discovery.
- Understand how `useJUnitPlatform`, `includeTags`, `excludeTags`, and `--tests` combine.
- Ensure untagged tests are not **silently skipped** across all of CI.
- Know what Gradle `test`, `check`, and `build` run and whether integration/E2E groups are invoked.
- Separate PR checks, integration checks, nightly/release E2E, and account for skipped jobs.
- Distinguish running `@SpringBootTest(RANDOM_PORT)` inside the test JVM from E2E against a `java -jar` app started out-of-process.
- Use per-UUID/test-run isolated data, properly scoped transaction rollbacks, and cleanup via API/repository.
- Explain why a `@Transactional` test does not roll back server-side commits under `RANDOM_PORT`.
- Understand Spring TestContext cache, JUnit parallelism, and Gradle forks to avoid misguided optimizations.
- Know when to graduate from tag filtering to separate source sets / the JVM Test Suite plugin.
- Read JUnit XML/reports per task, detecting "0 tests executed yet green build".
- State the limits of conclusions accurately: do not infer load/performance/production readiness from a single test group alone.

## 2. Four Groups Are Four Scopes of Evidence

| Group | Primary Boundary | Real Components | Typically Faked/Bounded | Question to Answer |
|---|---|---|---|---|
| **Unit** | Java object/method | Domain/service logic | Repository, HTTP, clock | Are the rules and error branches correct? |
| **Slice** | A slice of Spring context | MVC+Jackson, JPA, or HTTP client adapter | Layers outside the slice | Is the controller/serializer/query/client contract right? |
| **Integration** | Multiple layers/dependencies | Full Spring context, server/DB per test | External services outside the declared scope | Do DI/transactions/HTTP/persistence work together? |
| **E2E** | Public API of a running app | Executable artifact and defined request path | Usually does not access internal beans/repositories in test | Does a real user journey work through the deployment? |

This is **the article's convention**, not a universal taxonomy. Some teams call full Spring context + real HTTP in the same JVM end-to-end; here it belongs to **integration** so that **E2E** is reserved for a test independent of Spring TestContext that only calls a started/deployed app.

A `@WebMvcTest` that runs slowly because the application slice includes Security filters is still a slice. A JUnit test using real Docker/PostgreSQL is integration even without the `@SpringBootTest` annotation. Classify by data sources and participating components, not by duration.

## 3. Practical Benefits of Separating Groups in CI

```text
Before:
  gradle test
    - 200 pure unit
    - 60 MVC/JPA slice
    - 20 Spring full-context
    - 8 Testcontainers
    - 5 calling shared staging
  => Slow PRs, prone to flaky network blocking every change

After:
  ./gradlew test
    - unit + slice + all untagged tests
    - fast check per commit

  ./gradlew integrationTest
    - self-owned app context/DB/server/container in CI

  ./gradlew e2eTest -Pe2eBaseUrl=http://127.0.0.1:18080
    - app JAR started separately, test only calls public HTTP
    - runs in a controlled job

  Each group has its own JUnit XML/HTML report and quality gate.
```

Splitting **must not** drop the only integration tests protecting transactions or DB dialects. If a bug only occurs at the boundary between two layers, cramming every test into the unit group to get low PR times will degrade coverage. Judge the final outcome by **feedback time, executed test count, independence, and defect-detection capability**.

## 4. Choosing the Minimal Scope Without Missing Bugs

| Hypothesized Bug | Minimal Appropriate Scope | How to Prove It |
|---|---|---|
| Empty title allowed on creation | Unit | Assert exception and no repository call |
| Completing twice is not blocked | Unit | State transition and exception |
| Wrong `POST /api/tasks` route | MVC slice | MockMvc assert 201/JSON |
| JSON field `completed` renamed | MVC slice | JSONPath |
| `findByTitleIgnoreCase` is broken | JPA slice | H2 query with mixed casing |
| Entity state not flushed | JPA slice/integration | flush-clear-reload |
| Service loses `@Transactional` | Real integration, no test transaction wrapper | Real HTTP + DB readback |
| Missing Spring bean | Integration | ApplicationContext fails |
| Executable JAR fails to start | E2E/packaging | java -jar + readiness |
| Misconfigured TLS/nginx/Ingress | E2E through real gateway | Network/auth contract |
| PostgreSQL-specific SQL | Integration with Postgres | Testcontainers + migrations |
| p95 under 100 RPS load | Dedicated performance/load | k6/Gatling, not measured by 1 JUnit assert |
| Downstream network loss | Fault-injection integration | Controlled proxy/downstream |

A `contextLoads()` test, even with `@SpringBootTest`, does not protect business logic. Quality comes from **assertions capable of failing when a bug exists**, not merely from creating a large ApplicationContext.

## 5. Test Pyramid, Cost, and Execution Frequency

The unit group is usually the largest because its cost is low and failure diagnosis is fast. Slice tests protect behaviors that unit mocks cannot see: Jackson, Spring MVC, Bean Validation, repository queries, and Data JPA. Integration tests protect wiring/transactions/HTTP/DB, while E2E tests protect journeys through a deployment. Do not force a rigid 70/20/10 ratio if the domain does not fit.

A practical Build/CI architecture can look like this:

- **Every pull request:** unit + slice, essential integration tests, and static analysis.
- **Before merging/main branch:** integration with isolated database/containers; required checks.
- **Nightly:** expensive/hard integration suites, flakiness analysis, and performance baseline.
- **Release candidate:** E2E against the deployment artifact, critical permission/tenant/rollback scenarios.
- **Production smoke:** narrowly scoped synthetic probes, not a substitute for E2E with data cleanup.

Frequency is a risk-budget decision. An integration test that runs in under 2 seconds and guards a high-impact bug can be worth running on PRs. An E2E suite taking 10 minutes on shared staging should not run on every code change if faster tests can protect most of the logic.

## 6. Hands-on Example: Checklist API with Persistence

We create a small API:

| Request | Result |
|---|---|
| `POST /api/tasks` body `{"title":"Release"}` | 201, new task with UUID, `completed=false` |
| `GET /api/tasks/{id}` | 200, id/title/completed |
| `POST /api/tasks/{id}/complete` | 200, `completed=true` |
| Complete the same task again | 409, `ALREADY_COMPLETED` |
| Empty title or longer than 80 chars | 400, `INVALID_TITLE` |
| Non-existent ID | 404, `TASK_NOT_FOUND` |
| `DELETE /api/tasks/{id}` | 204, used for E2E cleanup |

The layers:

```text
TaskController + TaskErrorAdvice
           |
           v
TaskService (@Transactional)
           |
           v
TaskRepository (Spring Data JPA)
           |
           v
ChecklistItem (H2 embedded)

Unit:         Service + Mockito repository
MVC slice:    Controller + MockMvc + Mockito service
JPA slice:    Repository + EntityManager + H2
Integration:  RANDOM_PORT + TestRestTemplate + real service/repo H2
E2E:          Java HttpClient -> separately started app JAR
```

The demo application has no authentication, multi-tenant ownership, concurrency load, or production DB migrations. Do not use it as-is to store customer data. The goal here is **separating test evidence and organizing it in Gradle/CI**.

## 7. Project Directory Tree

```text
spring-boot-test-groups/
  settings.gradle
  build.gradle
  src/main/java/com/example/testgroups/
    TestGroupsApplication.java
    ChecklistItem.java
    TaskRepository.java
    CreateTaskRequest.java
    TaskResponse.java
    InvalidTitleException.java
    MissingTaskException.java
    AlreadyCompletedException.java
    TaskService.java
    TaskController.java
    TaskErrorAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/testgroups/
    TaskServiceUnitTest.java
    TaskControllerSliceTest.java
    TaskRepositorySliceTest.java
    TaskHttpIntegrationTest.java
    TaskExternalE2ETest.java
  .github/workflows/
    verify.yml
```

The sample places **all four groups inside the same `src/test/java`** so the project is easy to copy, while Gradle Test tasks filter using JUnit tags. This is **runtime test filtering**: all groups still share the same test compilation classpath. Section 28 explains how to separate `sourceSets` or use the JVM Test Suite plugin when you want true dependency isolation.

## 8. Gradle Dependencies and Test Tasks

**`settings.gradle`**

```groovy
rootProject.name = 'spring-boot-test-groups'
```

**`build.gradle`** — complete file for the demo project:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

// PR fast group. Untagged tests are INCLUDED so they cannot
// silently disappear from every task.
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration', 'e2e'
    }
    reports.junitXml.required = true
    reports.html.required = true
}

tasks.register('unitTest', Test) {
    group = 'verification'
    description = 'Run unit-tagged tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'unit'
    }
}

tasks.register('sliceTest', Test) {
    group = 'verification'
    description = 'Run MVC/JPA slice-tagged tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'slice'
    }
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Run full-context integration tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'integration'
    }
    shouldRunAfter tasks.named('test')
    maxParallelForks = 1
}

tasks.register('e2eTest', Test) {
    group = 'verification'
    description = 'Run external E2E against approved local app.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'e2e'
    }
    systemProperty 'e2e.baseUrl',
            providers.gradleProperty('e2eBaseUrl').orElse('').get()
    maxParallelForks = 1
}
```

**Why assign `testClassesDirs` and `classpath` for custom Test tasks?** According to Gradle documentation, a new `Test` task does not automatically know which classes and execution classpath to use. Those two properties point explicitly to the compiled `test` source set. In newer Gradle versions, relying on defaults can result in `NO-SOURCE` or failing to find tests.

**Why does `test` use `excludeTags` instead of only `includeTags 'unit','slice'`?** If a developer forgets to add `@Tag` to a new test, an include-only configuration would skip it across all jobs. This pattern lets **untagged** tests run in `test`; CI should still have a tag audit step to classify them properly.

## 9. How `@Tag` Is Used in JUnit 5

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
class ExampleUnitTest {
    @Test
    void rule() {
        // Java-level assertion
    }
}
```

In the real files below, the tag is placed on the **test class**. JUnit Jupiter allows test methods to inherit class tags. Each class has **one primary scope tag**: `unit`, `slice`, `integration`, or `e2e`.

If a method is tagged with both `slice` and `integration`, it can run twice when CI invokes both tasks. If the behavior has side effects, this complicates data cleanup and causes double execution. You can add secondary tags such as `slow` or `postgres`, but do not mix primary scopes.

### 9.1. Which Task Runs Which Tests?

| Gradle task | Filter Type | Tests Run |
|---|---|---|
| `test` | exclude `integration`, `e2e` | Unit, slice, untagged |
| `unitTest` | include `unit` | Unit only |
| `sliceTest` | include `slice` | Slice only |
| `integrationTest` | include `integration` | Integration only |
| `e2eTest` | include `e2e` | E2E only |

`./gradlew check` and `./gradlew build` from the Java plugin run `test` by default, and **do not automatically run newly registered integration/e2e tasks** unless you add explicit dependencies or calls. Therefore reports must distinguish "fast pass" from "all stages pass".

## 10. Spring Boot Application Root

**`src/main/java/com/example/testgroups/TestGroupsApplication.java`**

```java
package com.example.testgroups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestGroupsApplication.class, args);
    }
}
```

Having one application root in the shared package helps `@WebMvcTest`, `@DataJpaTest`, and full `@SpringBootTest` find the right configuration. Tests must not add another `SpringBootApplication` inside test sources and cause every slice to load unintended config.

## 11. JPA Entity and Repository

**`src/main/java/com/example/testgroups/ChecklistItem.java`**

```java
package com.example.testgroups;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
@Table(name = "checklist_items")
public class ChecklistItem {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 80)
    private String title;

    @Column(nullable = false)
    private boolean completed;

    @Version
    private Long version;

    protected ChecklistItem() {
        // JPA constructor
    }

    public ChecklistItem(String id, String title) {
        this.id = Objects.requireNonNull(id);
        this.title = Objects.requireNonNull(title);
        this.completed = false;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isCompleted() {
        return completed;
    }

    public void complete() {
        if (completed) {
            throw new AlreadyCompletedException();
        }
        completed = true;
    }
}
```

**`src/main/java/com/example/testgroups/TaskRepository.java`**

```java
package com.example.testgroups;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TaskRepository
        extends JpaRepository<ChecklistItem, String> {

    Optional<ChecklistItem> findByTitleIgnoreCase(String title);
}
```

`@Version` provides optimistic locking under concurrent writes, but this article does not test concurrent multi-transaction contention; do not claim the system prevents all duplicate requests. `findByTitleIgnoreCase` creates a useful JPA slice scenario that a mock repository cannot verify.

## 12. Request/Response Records and Exception Types

**`src/main/java/com/example/testgroups/CreateTaskRequest.java`**

```java
package com.example.testgroups;

public record CreateTaskRequest(String title) {
}
```

**`src/main/java/com/example/testgroups/TaskResponse.java`**

```java
package com.example.testgroups;

public record TaskResponse(
        String id, String title, boolean completed) {
}
```

**`src/main/java/com/example/testgroups/InvalidTitleException.java`**

```java
package com.example.testgroups;

public class InvalidTitleException
        extends IllegalArgumentException {
}
```

**`src/main/java/com/example/testgroups/MissingTaskException.java`**

```java
package com.example.testgroups;

public class MissingTaskException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testgroups/AlreadyCompletedException.java`**

```java
package com.example.testgroups;

public class AlreadyCompletedException
        extends RuntimeException {
}
```

Use domain-specific exceptions so the controller advice maps exact error codes; do not catch all `RuntimeException`s and return `400`. Title validation is in `TaskService` without depending on the bean validation starter. If switching to `@Valid`/`@NotBlank`, you must add `spring-boot-starter-validation` and corresponding tests.

## 13. Real Service: Where Transactions and Business Rules Live

**`src/main/java/com/example/testgroups/TaskService.java`**

```java
package com.example.testgroups;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TaskResponse create(String title) {
        if (title == null
                || title.isBlank()
                || title.strip().length() > 80) {
            throw new InvalidTitleException();
        }

        ChecklistItem item = new ChecklistItem(
                UUID.randomUUID().toString(), title.strip());
        repository.save(item);
        return view(item);
    }

    @Transactional(readOnly = true)
    public TaskResponse read(String id) {
        return view(repository.findById(id)
                .orElseThrow(MissingTaskException::new));
    }

    @Transactional
    public TaskResponse complete(String id) {
        ChecklistItem item = repository.findById(id)
                .orElseThrow(MissingTaskException::new);
        item.complete();
        // Managed entity update is flushed at transaction commit.
        return view(item);
    }

    @Transactional
    public void delete(String id) {
        if (!repository.existsById(id)) {
            throw new MissingTaskException();
        }
        repository.deleteById(id);
    }

    private TaskResponse view(ChecklistItem item) {
        return new TaskResponse(
                item.getId(), item.getTitle(), item.isCompleted());
    }
}
```

Unit tests instantiate the service with `new TaskService(mockRepository)`, so **there is no Spring AOP transaction proxy**. Entity mutation in unit tests still flips the boolean, but DB commit is not proven. Integration tests over HTTP verify a repository readback after the request to catch cases where entity mutations are not persisted.

## 14. Controller and Advice: Public HTTP Boundary

**`src/main/java/com/example/testgroups/TaskController.java`**

```java
package com.example.testgroups;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @RequestBody CreateTaskRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request.title()));
    }

    @GetMapping("/{id}")
    public TaskResponse read(@PathVariable String id) {
        return service.read(id);
    }

    @PostMapping("/{id}/complete")
    public TaskResponse complete(@PathVariable String id) {
        return service.complete(id);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        service.delete(id);
    }
}
```

**`src/main/java/com/example/testgroups/TaskErrorAdvice.java`**

```java
package com.example.testgroups;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TaskErrorAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidTitleException.class)
    public ResponseEntity<ErrorBody> invalidTitle() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_TITLE"));
    }

    @ExceptionHandler(MissingTaskException.class)
    public ResponseEntity<ErrorBody> missingTask() {
        return ResponseEntity.status(404)
                .body(new ErrorBody("TASK_NOT_FOUND"));
    }

    @ExceptionHandler(AlreadyCompletedException.class)
    public ResponseEntity<ErrorBody> alreadyCompleted() {
        return ResponseEntity.status(409)
                .body(new ErrorBody("ALREADY_COMPLETED"));
    }
}
```

`TaskController` is a thin HTTP adapter. The MVC slice verifies method/path/status/JSON/advice; integration verifies controller→service→real JPA; E2E verifies behavior through the executable artifact. There is no Spring Security in the demo: a production application needs authentication/authorization and separate negative tests.

## 15. Test Properties to Avoid Touching a Real Database

**`src/test/resources/application.properties`**

```properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.datasource.generate-unique-name=true
spring.jpa.open-in-view=false
```

- `create-drop` is for embedded H2 in tests, **not** for production.
- `generate-unique-name` reduces the chance of multiple ApplicationContexts colliding on an H2 in-memory database name.
- `open-in-view=false` avoids relying on a persistence context staying open across HTTP serialization.
- Unit tests do not read these properties because they do not load Spring.
- E2E starts a separate JAR and **does not automatically load `src/test/resources`**; CI passes separate startup arguments.

For production databases, use Flyway/Liquibase migrations and test against a database with the matching dialect; H2 does not replace PostgreSQL locking, JSONB, or timezone/unique semantics.

## 16. Unit Test: No Spring, No Database, No Network

**`src/test/java/com/example/testgroups/TaskServiceUnitTest.java`**

```java
package com.example.testgroups;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@Tag("unit")
@ExtendWith(MockitoExtension.class)
class TaskServiceUnitTest {

    @Mock
    TaskRepository repository;

    TaskService service;

    @BeforeEach
    void setup() {
        service = new TaskService(repository);
    }

    @Test
    void createTrimsTitleAndWritesOneEntity() {
        TaskResponse result = service.create("  Release  ");

        ArgumentCaptor<ChecklistItem> captor =
                ArgumentCaptor.forClass(ChecklistItem.class);
        verify(repository).save(captor.capture());

        assertEquals("Release", result.title());
        assertFalse(result.completed());
        assertEquals("Release",
                captor.getValue().getTitle());
        assertEquals(result.id(), captor.getValue().getId());
    }

    @Test
    void invalidTitleDoesNotCallRepository() {
        assertThrows(InvalidTitleException.class,
                () -> service.create("   "));
        verifyNoInteractions(repository);
    }

    @Test
    void completeChangesDomainState() {
        ChecklistItem item = new ChecklistItem(
                "u1", "Plan");
        when(repository.findById("u1"))
                .thenReturn(Optional.of(item));

        TaskResponse result = service.complete("u1");

        assertTrue(item.isCompleted());
        assertTrue(result.completed());
        verify(repository).findById("u1");
    }

    @Test
    void duplicateCompletionFails() {
        ChecklistItem item = new ChecklistItem(
                "u2", "Review");
        item.complete();
        when(repository.findById("u2"))
                .thenReturn(Optional.of(item));

        assertThrows(AlreadyCompletedException.class,
                () -> service.complete("u2"));
    }

    @Test
    void missingTaskFails() {
        when(repository.findById("unknown"))
                .thenReturn(Optional.empty());

        assertThrows(MissingTaskException.class,
                () -> service.read("unknown"));
    }
}
```

**5 unit methods** check input boundaries, title normalization, state transitions, duplicate errors, and missing records. Mocks are per test with no shared Spring context. Do not use `@SpringBootTest` to prove a pure Java rule.

**Limitation:** `@Transactional` on the service **does not activate a proxy** in this test. If a developer removes the annotation, `completeChangesDomainState` still passes. This is intentional: transactions are verified in integration tests.

## 17. MVC Slice: Real MVC, Mocked Service

**`src/test/java/com/example/testgroups/TaskControllerSliceTest.java`**

```java
package com.example.testgroups;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("slice")
@WebMvcTest(TaskController.class)
class TaskControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    TaskService taskService;

    @Test
    void createReturns201AndJsonContract() throws Exception {
        when(taskService.create("Release"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", false));

        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Release\"}"))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.id").value("t1"),
                        jsonPath("$.completed").value(false));

        verify(taskService).create("Release");
    }

    @Test
    void getMapsTaskToJson() throws Exception {
        when(taskService.read("t1"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", false));

        mvc.perform(get("/api/tasks/t1"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Release"));
    }

    @Test
    void completionMapsToService() throws Exception {
        when(taskService.complete("t1"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", true));

        mvc.perform(post("/api/tasks/t1/complete"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.completed").value(true));
    }

    @Test
    void invalidTitleMapsTo400() throws Exception {
        when(taskService.create(""))
                .thenThrow(new InvalidTitleException());

        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"\"}"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_TITLE"));
    }

    @Test
    void duplicateCompletionMapsTo409() throws Exception {
        when(taskService.complete("t1"))
                .thenThrow(new AlreadyCompletedException());

        mvc.perform(post("/api/tasks/t1/complete"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("ALREADY_COMPLETED"));
    }
}
```

**5 slice methods** verify routes, JSON, HTTP responses, and exception advice. `@WebMvcTest` scans the selected controller, MVC infrastructure, and web components such as advice; `@MockitoBean` injects a mock service into the slice. When service validation is deleted in production, `invalidTitleMapsTo400` can still pass because the mock is configured to throw the exception: **unit tests prove validation**, and integration tests prove layer wiring.

## 18. JPA Slice: Real Queries and Dirty Checking with H2

**`src/test/java/com/example/testgroups/TaskRepositorySliceTest.java`**

```java
package com.example.testgroups;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("slice")
@DataJpaTest
class TaskRepositorySliceTest {

    @Autowired
    TaskRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void titleIgnoreCaseDerivedQueryWorks() {
        repository.saveAndFlush(
                new ChecklistItem("j1", "Release Notes"));

        assertTrue(repository.findByTitleIgnoreCase(
                "rElEaSe nOtEs").isPresent());
    }

    @Test
    void dirtyCheckingPersistsAfterFlushAndClear() {
        ChecklistItem item = repository.saveAndFlush(
                new ChecklistItem("j2", "Write docs"));

        item.complete();
        entityManager.flush();
        entityManager.clear();

        ChecklistItem loaded = repository.findById("j2")
                .orElseThrow();

        assertTrue(loaded.isCompleted());
        assertEquals("Write docs", loaded.getTitle());
    }
}
```

**2 JPA slice methods** use `@DataJpaTest`, which defaults to transaction rollback per test method. `flush/clear` verifies database state rather than state remaining in the first-level cache. A Mockito unit test returning a pre-built entity cannot catch query or SQL mapping bugs.

H2 does not guarantee all SQL/locking semantics match production. If the application uses PostgreSQL-specific queries or migrations, add an integration group with Postgres Testcontainers rather than treating H2 `@DataJpaTest` as a guarantee for every database.

## 19. Integration: Full Spring Context, Real HTTP, and Real Commits

**`src/test/java/com/example/testgroups/TaskHttpIntegrationTest.java`**

```java
package com.example.testgroups;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("integration")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    TaskRepository repository;

    private final List<String> ownedIds = new ArrayList<>();

    @AfterEach
    void cleanup() {
        for (String id : ownedIds) {
            if (repository.existsById(id)) {
                repository.deleteById(id);
            }
        }
    }

    private String create(String title) {
        ResponseEntity<TaskResponse> response =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(title),
                        TaskResponse.class);

        assertEquals(201, response.getStatusCode().value());
        assertNotNull(response.getBody());

        String id = response.getBody().id();
        ownedIds.add(id);
        return id;
    }

    @Test
    void createCompleteAndReadCommittedResult() {
        String id = create("Integration");

        ResponseEntity<TaskResponse> completed =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskResponse.class, id);

        assertEquals(200, completed.getStatusCode().value());
        assertNotNull(completed.getBody());
        assertTrue(completed.getBody().completed());

        ResponseEntity<TaskResponse> read =
                http.getForEntity(
                        "/api/tasks/{id}",
                        TaskResponse.class, id);

        assertEquals(200, read.getStatusCode().value());
        assertNotNull(read.getBody());
        assertTrue(read.getBody().completed());

        assertTrue(repository.findById(id)
                .orElseThrow().isCompleted());
    }

    @Test
    void badTitleReturns400AndDoesNotCreateTask() {
        long countBefore = repository.count();

        ResponseEntity<TaskErrorAdvice.ErrorBody> response =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(" "),
                        TaskErrorAdvice.ErrorBody.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_TITLE", response.getBody().code());
        assertEquals(countBefore, repository.count());
    }

    @Test
    void completingTwiceReturns409() {
        String id = create("Complete only once");

        ResponseEntity<TaskResponse> first =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskResponse.class, id);
        assertEquals(200, first.getStatusCode().value());

        ResponseEntity<TaskErrorAdvice.ErrorBody> second =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskErrorAdvice.ErrorBody.class, id);

        assertEquals(409, second.getStatusCode().value());
        assertNotNull(second.getBody());
        assertEquals("ALREADY_COMPLETED",
                second.getBody().code());
    }
}
```

**3 integration methods**, where Spring Boot starts an embedded server on a random port. TestRestTemplate sends actual local TCP requests; controller/service/repository/H2 are all real. The test **does not** have class-level `@Transactional`: the client thread and server transaction are separate, so a rollback on the test thread **does not** undo server commits.

`@AfterEach` deletes **only the IDs created by the test**, avoiding polluting other tests when the context/database cache is reused. When a CI process is killed, the Java lifecycle does not guarantee cleanup; an isolated H2 environment or per-job database provides an extra safeguard. Do not wipe an entire shared table just to save a few lines.

### 19.1. Why Is Integration Different from an MVC Slice?

If `TaskService.complete` loses `@Transactional`, entity mutation in a pure unit test still looks right, and an MVC slice mocks the service so its code does not run. Real HTTP integration with repository readback can detect **uncommitted data**. Do not use `@SpringBootTest + @MockitoBean TaskService` and conclude that service transactions have been tested: the mock replaced the very logic/AOP under test.

## 20. E2E: Black-Box Java HttpClient Against a Started App

E2E in this article **does not inject Spring beans, does not read repositories directly, and does not start a context in the JUnit test process**. It uses `java.net.http.HttpClient` to call the packaged `java -jar` application. To prevent accidentally sending POST/DELETE operations to shared staging/production, the demo **only allows a loopback base URL** with a specific port.

**`src/test/java/com/example/testgroups/TaskExternalE2ETest.java`**

```java
package com.example.testgroups;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("e2e")
class TaskExternalE2ETest {

    private static final ObjectMapper JSON =
            new ObjectMapper();

    @Test
    void createCompleteReadAndDeleteThroughPublicHttp()
            throws Exception {

        String base = System.getProperty(
                "e2e.baseUrl", "").replaceAll("/+$", "");

        // This educational E2E intentionally permits ONLY loopback.
        assertTrue(base.matches(
                "http://(127\\.0\\.0\\.1|localhost):[0-9]{2,5}"),
                "Set -Pe2eBaseUrl to an approved local HTTP port");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        String id = null;
        String title = "e2e-" + UUID.randomUUID();

        try {
            HttpRequest create = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            JSON.writeValueAsString(
                                    new CreateTaskRequest(title))))
                    .build();

            HttpResponse<String> created = client.send(
                    create, HttpResponse.BodyHandlers.ofString());

            assertEquals(201, created.statusCode());
            JsonNode body = JSON.readTree(created.body());
            id = body.get("id").asText();
            assertEquals(title, body.get("title").asText());
            assertFalse(body.get("completed").asBoolean());

            HttpRequest complete = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks/"
                                    + id + "/complete"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            HttpResponse<String> done = client.send(
                    complete, HttpResponse.BodyHandlers.ofString());
            assertEquals(200, done.statusCode());
            assertTrue(JSON.readTree(done.body())
                    .get("completed").asBoolean());

            HttpRequest read = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks/" + id))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> fetched = client.send(
                    read, HttpResponse.BodyHandlers.ofString());
            assertEquals(200, fetched.statusCode());
            assertTrue(JSON.readTree(fetched.body())
                    .get("completed").asBoolean());

        } finally {
            if (id != null) {
                HttpRequest delete = HttpRequest.newBuilder(
                                URI.create(base + "/api/tasks/" + id))
                        .timeout(Duration.ofSeconds(5))
                        .DELETE()
                        .build();

                HttpResponse<String> response = client.send(
                        delete, HttpResponse.BodyHandlers.ofString());
                assertEquals(204, response.statusCode(),
                        "E2E cleanup must delete test-owned task");
            }
        }
    }
}
```

**1 E2E method** creates/completes/reads/deletes a task via public HTTP. The input title includes a UUID so runs never collide. The base URL passed via Gradle property `-Pe2eBaseUrl` is forwarded as a JVM system property; if missing, the test **FAILS** rather than silently skipping. Connect/request timeouts are bounded.

**Honest limitations:** Local `java -jar` + H2 E2E proves executable JAR packaging/startup/HTTP/JPA on the test machine. It **does not** verify HTTPS Ingress, OAuth, production PostgreSQL, Redis, or multi-pod setups because those are not in this topology. Staging E2E needs an allowlist, test identity, environment approval, data isolation/retention, and a proper contract rather than just removing the regex safety guard.

### 20.1. Cleanup When CI Crashes

`finally` runs when the Java flow exits, but not if the process is killed or the server commits and the client loses the response **before obtaining the ID**. Production-grade E2E needs a test-run prefix/idempotency key, TTL or janitor, and an isolated tenant/database to handle orphaned records. In the demo, the app/H2 are created specifically for the job and stopped afterward, reducing unintended impact.

## 21. Total Test Count and Detection Scope

| Class | Tag | Methods | Primary Detection |
|---|---|---:|---|
| `TaskServiceUnitTest` | unit | 5 | Rules/validation/state |
| `TaskControllerSliceTest` | slice | 5 | Routes/JSON/advice |
| `TaskRepositorySliceTest` | slice | 2 | Derived query/JPA flush |
| `TaskHttpIntegrationTest` | integration | 3 | Real HTTP/wiring/commit |
| `TaskExternalE2ETest` | e2e | 1 | Black-box executable app |
| **Total** | | **16** | Layers with distinct responsibilities |

In the demo, `./gradlew test` is expected to run **12 methods** across unit+slice, without running the 3 integration/1 E2E methods. `./gradlew unitTest` runs 5; `sliceTest` runs 7; `integrationTest` runs 3; `e2eTest` runs 1 when invoked. These are **the test counts designed in the source**, **not** counts observed from an actual Gradle run.

## 22. Local Execution and Debugging Commands

```bash
# Gradle Wrapper must exist before using it.
./gradlew test

# Run groups independently:
./gradlew unitTest
./gradlew sliceTest
./gradlew integrationTest

# Select one method in the right task:
./gradlew unitTest \
  --tests com.example.testgroups.TaskServiceUnitTest.invalidTitleDoesNotCallRepository

# Build artifact, start server in another terminal:
./gradlew bootJar
java -jar build/libs/spring-boot-test-groups-0.0.1-SNAPSHOT.jar \
  --server.port=18080 \
  --spring.jpa.hibernate.ddl-auto=create-drop

# Once local server is ready:
./gradlew e2eTest -Pe2eBaseUrl=http://127.0.0.1:18080
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`, and use PowerShell line-continuation syntax or a single-line Java command. Tasks that have `includeTags` and a `--tests` filter apply **both** conditions; selecting an integration class via `unitTest --tests` does not change its tag.

**Note:** If the Gradle Wrapper is not yet present, generate it via Gradle/IDE per convention and commit `gradlew`, `gradlew.bat`, and `gradle/wrapper/*`. Having `build.gradle/settings.gradle` alone does not generate the wrapper.

## 23. Test Discovery: Verify Executed Method Counts Too

A pipeline can report **BUILD SUCCESSFUL** while running no tests because:

- A custom `Test` task is missing `testClassesDirs` or `classpath`.
- `@Tag("integration")` is missing due to forgetting or case mismatch.
- Files are placed in the wrong source directory or fail to compile.
- JUnit Platform/TestEngine is missing.
- `--tests` filters out the wrong class/method.
- All tests are `@Disabled` or skipped by assumptions.
- The Gradle task reports `NO-SOURCE`.
- The tag include/exclude expression is wrong.

Use:

```bash
./gradlew tasks --group verification
./gradlew test --info
./gradlew integrationTest --info
./gradlew e2eTest --dry-run
```

`--dry-run` **does not execute tests**; it only shows the task graph. Read JUnit XML / executed test counts in CI to confirm. Put guards requiring important test classes or minimum method counts per policy; when adding/removing tests, update the guard via code review. Do not treat a "0 tests executed" stage as a real integration pass.

## 24. Spring Context Cache and Execution Cost

The Spring TestContext cache keys on configuration including classes/locations, active profiles, properties, bean overrides, DynamicPropertySource customizers, and web resource context. Classes sharing **the same key** in the same JVM can reuse an ApplicationContext; however, pure unit tests need no context, and separate JVM forks/processes do not share the static cache.

**Spring Framework 6.2's default max size is 32 contexts, with LRU eviction.** You can change it via the JVM system property `spring.test.context.cache.maxSize` when measurements justify it, but do not raise it blindly and assume the suite will definitely be faster.

- `@WebMvcTest` has one context slice; `@DataJpaTest` has another key.
- `@SpringBootTest(RANDOM_PORT)` is a full web server context, distinct from MOCK.
- `@MockitoBean` qualifiers/names can affect the key; specify them consistently when targeting the same bean.
- Different `@ActiveProfiles`/`@TestPropertySource` create distinct valid contexts.
- `@DirtiesContext` forces eviction/reload; use it when the context is genuinely dirty, not just to delete one DB row.
- Gradle `maxParallelForks` and `forkEvery` involve reuse/memory/capacity trade-offs.
- E2E runs the app out-of-process and does not use JUnit's Spring TestContext cache.

**Mandatory condition:** Reuse the **Spring bean graph**, but never reuse **mutable test state** between methods. Roll back the DB, delete test-owned records, and reset Clocks/caches/mocks/threads rather than relying on execution order.

## 25. Per-Group Isolation

| State | Unit | Slice | Integration | E2E |
|---|---|---|---|---|
| Java object | Newly instantiated per test | Context singleton may be reused | Context reused, reset mutable state | Not accessed directly |
| Database | Mock repo | `@DataJpaTest` rollback | Unique IDs, proper boundary cleanup/test transaction | Test tenant/ID, cleanup via API |
| HTTP port | None | MockMvc opens no socket | RANDOM_PORT | Specified deployment port |
| File/temp | `@TempDir` if needed | `@TempDir` | Test-owned directory/container | API cleanup/TTL |
| Clock | Dedicated fixed/test clock | Explicitly controlled property/bean | Reset/sync background jobs | Do not force time on uncontrolled services |
| Message queue | Mock publisher | Usually mocked | Test topic/consumer group | Dedicated namespace |
| Credentials | Not needed | Fake test identity | Test-only credentials | Approved least-privilege identity |

**RANDOM_PORT and transactions:** Spring Boot docs note that the HTTP client and server execute in separate threads/transactions. `@Transactional` on a test method will not roll back server transactions. The sample uses `@AfterEach` by ID rather than calling `deleteAll()` on a shared database.

## 26. GitHub Actions: PR and Integration Are Two Gates

A sample workflow runs fast and integration in separate jobs, and E2E only when manually triggered. It requires the Gradle Wrapper to be committed. **`.github/workflows/verify.yml`**:

```yaml
name: Verify Spring Boot test groups

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Unit + slice + untagged
        run: ./gradlew test
      - name: Upload fast reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: fast-test-reports
          path: |
            build/test-results/test/**
            build/reports/tests/test/**

  integration:
    needs: fast
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Full Spring HTTP + H2
        run: ./gradlew integrationTest
      - name: Upload integration reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-reports
          path: |
            build/test-results/integrationTest/**
            build/reports/tests/integrationTest/**

  e2e:
    if: github.event_name == 'workflow_dispatch'
    needs: integration
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Build executable jar
        run: ./gradlew bootJar
      - name: Start isolated app and run E2E
        shell: bash
        run: |
          set -euo pipefail
          java -jar build/libs/spring-boot-test-groups-0.0.1-SNAPSHOT.jar \
            --server.port=18080 \
            --spring.jpa.hibernate.ddl-auto=create-drop \
            > e2e-app.log 2>&1 &
          app_pid=$!
          trap 'kill "$app_pid" 2>/dev/null || true' EXIT

          ready=0
          for attempt in $(seq 1 40); do
            if curl -fsS http://127.0.0.1:18080/actuator/health \
                 >/dev/null 2>&1; then
              ready=1
              break
            fi
            sleep 1
          done
          if [ "$ready" -ne 1 ]; then
            echo 'App did not start successfully' >&2
            exit 1
          fi

          ./gradlew e2eTest \
            -Pe2eBaseUrl=http://127.0.0.1:18080
      - name: Upload E2E reports and logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-test-reports
          path: |
            build/test-results/e2eTest/**
            build/reports/tests/e2eTest/**
            e2e-app.log
```

**Key points to know:**

- Action versions are based on official Gradle/GitHub examples available at writing time; enterprises may pin commit SHAs and check runner compatibility/security policies.
- Spring Boot Actuator provides the `/actuator/health` readiness probe in the lab; do not expose all actuator endpoints to the Internet by default.
- The `e2e` job **does not run automatically on PR/push** under this YAML, only on `workflow_dispatch`. If release policy requires E2E, create the corresponding required job/approval; a skipped job is not a PASS.
- `needs: fast/integration` makes downstream runs depend on upstream success; if upstream fails, E2E does not run.
- GitHub Actions jobs run on separate runners and do not automatically share build/test caches, artifacts, or Spring contexts.
- Uploading artifacts with `if: always()` saves XML/HTML/logs after failure; avoid tokens/passwords/private data in them.
- The E2E app starts using the CI runner's own JAR/H2, never calling external production.
- Shell `sleep 1` in readiness polling has a **40-attempt bound and success condition**, unlike a fixed sleep hoping the app is ready.

## 27. Test Reports Must Be Separated Per Gradle Task

Each Gradle `Test` task has its own XML and HTML output, typically:

```text
build/test-results/test/...
build/reports/tests/test/...

build/test-results/unitTest/...
build/reports/tests/unitTest/...

build/test-results/sliceTest/...
build/reports/tests/sliceTest/...

build/test-results/integrationTest/...
build/reports/tests/integrationTest/...

build/test-results/e2eTest/...
build/reports/tests/e2eTest/...
```

**Do not** report "all tests passed" just because `build/reports/tests/test/index.html` is green: that file does not represent `integration`/`e2e` when they are separate tasks. Summarize each stage with **PASS, FAIL, SKIPPED, NOT RUN** and actual executed test counts, and save per-job artifacts. Also do not use `ignoreFailures=true` or a retry plugin to turn failures "green" silently.

## 28. When to Use Source Sets or JVM Test Suite Instead of `@Tag`

Tags organize **runtime selection** quickly inside one source set. However, all test classes still compile/run against `testImplementation`:

- Unit tests can technically still import `@SpringBootTest` or Testcontainers.
- E2E tests still carry JUnit/Spring Test libraries even if unused.
- An optional dependency on the test classpath can hide a real "missing dependency" bug.
- A different classpath for a DB provider or native image cannot be created with `@Tag` alone.
- Test fixtures/inter-module dependencies may need compile-time restrictions.

When you need **dependency/source isolation**, move to separate source sets:

```text
src/test/java/               pure unit
src/sliceTest/java/          Spring slice tests
src/integrationTest/java/    Spring + containers + database
src/e2eTest/java/            black-box HTTP tests
```

The Gradle JVM Test Suite plugin also provides a test suites model. Migrating requires declaring separate source sets/configurations/compile/runtime classpaths and appropriate `Test` tasks, not merely moving folders. In the demo, tags are used to focus on **CI task splitting** first, then isolation can be improved as the project grows and justifies it.

### 28.1. Reference Source Set Snippet

```groovy
// Illustrative snippet; does not replace the full build.gradle in section 8.
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'
        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}
tasks.register('integrationTest', Test) {
    group = 'verification'
    testClassesDirs =
            sourceSets.integrationTest.output.classesDirs
    classpath =
            sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
```

**Do not paste this block below the demo `build.gradle`** without removing the old `integrationTest` task: Gradle forbids registering two tasks with the same name. Verify test compilation/runtime classpaths and fixtures after refactoring. Gradle's "Configuring integration tests" and JVM Test Suite docs are the canonical references to complete this.

## 29. Gradle Task Graph, Forks, and Parallel Execution

- `dependsOn`: adds a required task to the graph.
- `shouldRunAfter`: orders tasks when **both are already in the graph**, without pulling in new tasks.
- `mustRunAfter`: enforces strict ordering when both tasks are selected, also not a `dependsOn`.
- `maxParallelForks`: enables multiple test JVM processes, which can increase throughput but also raises CPU/memory usage and reduces cache reuse.
- `forkEvery`: spawns a new JVM after N test classes, which can prevent Spring TestContext cache reuse.
- Gradle Build Cache/Configuration Cache are **different** from Spring TestContext cache; a task cache hit does not mean tests executed this time.
- Splitting fast/integration/E2E jobs gives clear reporting, at the cost of dependency downloads/JVM startup overhead across runners.

If CI already runs `./gradlew test` in the fast job, do not accidentally add `integrationTest.dependsOn test` and re-run the fast suite inside the integration job. In YAML, `needs: fast` is the workflow-level gate; the Gradle integration task can run independently for debugging.

## 30. Test Isolation and Spring TestContext Cache

The TestContext cache reuses the same `ApplicationContext` key within the same JVM. It **does not reset all mutable state**:

- `@DataJpaTest` rolls back data per test transaction.
- Real HTTP server commits are not rolled back by test-client `@Transactional`.
- `@MockitoBean` mocks have a reset lifecycle; running in parallel with shared mocks requires care.
- Singleton caches, mutable Clocks, static fields, and SecurityContext ThreadLocals need isolation.
- `@Scheduled`/`@Async` jobs may run after a test and mutate fixtures.
- Redis/Kafka/object storage/file system do not participate in JPA transaction rollbacks.
- `@DirtiesContext` forces a context reload; use it only when the bean graph/state genuinely cannot be restored safely.

Spring Framework 6.2's TestContext cache **defaults to a maximum of 32 contexts** with LRU; the context key is affected by profiles, properties, context customizers, bean overrides, DynamicPropertySource, and web environment. Raising cache size does not fix flaky data leaks; measure context misses/CI elapsed time and isolate specific state.

## 31. Meaningful Testing Is Not Just Happy Paths

A trustworthy release pipeline needs **negative tests** at the right group levels:

- Unit: null/blank/too-long title, duplicate transitions, missing domain records.
- MVC slice: invalid JSON, wrong media type, 400/404/409 mapping, path/method contracts.
- JPA slice: unique constraints, case-insensitive derived queries, dirty checking, migrations.
- Integration: transaction rollback/commit, data readback after HTTP, exception mapping with real services.
- E2E: public 201→200→204 journey, authentication/tenant boundaries if the app has security.
- External dependencies: container unavailable, timeouts/circuit breakers, idempotency/compensation if present.
- Performance: RPS, p95, and error budgets via a dedicated load tool; do not call a unit test a load test.

**Do not duplicate the exact same assertion across all four groups while ignoring bugs specific to each group.** For example, an E2E test asserting only `status 200` can stay green even when `completed` is wrong; assert business state. Conversely, 100% unit branch coverage cannot substitute for JPA transaction integration.

## 32. Optimizing CI for Speed and Defect Detection

When the suite gets slow, investigate:

1. Total `Gradle test task wall time`, compilation, and dependency downloads.
2. Actual number of Spring contexts loaded and cache hits/misses.
3. `@DirtiesContext` usages and bean overrides/property variants causing key explosion.
4. Docker/Testcontainers image pulls and connection readiness.
5. Migrations/schema initialization.
6. Build/test JVM forks and parallel contention.
7. HTTP server startup and test environment waits.
8. Mock/external service latency, retries, and timeouts.
9. CI artifact upload time.
10. Flaky retry rates and hidden inter-test dependencies.

Optimization is **not** deleting all full-context tests. A worthy optimization improves feedback without reducing the **bug hypotheses protected**. Each test type should have a clear purpose: unit catches business rules, slice catches MVC/JPA config, integration catches transactions/wiring, and E2E catches startup/packaging/public journeys.

## 33. Flakiness, Shared Data, and Retries

Typical sources of flakiness:

| Symptom | Cause | Fix |
|---|---|---|
| Passes alone, fails in full suite | Static/singleton state leak | Reset/per-test data |
| H2 duplicate key across tests | Shared ID, no rollback | Unique IDs/transaction cleanup |
| E2E 404 at start | Server not ready or deploy in progress | Readiness + bounded retry |
| Port already in use | Fixed port across jobs | RANDOM_PORT or isolated ports |
| Test server timeout | Resource contention in CI | Limit forks, measure capacity |
| Cascading Spring context load failures | One root startup error | Find first failure, do not fix test-by-test |
| Docker container fails to run | CI lacks Docker/permissions | Set up job, do not skip silently |
| Order-dependent tests | Data from A used by B | Self-contained fixtures |
| Incorrect Mockito verification in parallel | Shared mock reset/race | Group/limit parallelism |
| E2E fails to delete task when process killed | Finally did not run | Test-owned environment/janitor |
| Test report green but 0 methods | Wrong tag/filter/task config | Check XML executed count |
| CI retry passes on 3rd attempt | Underlying race/network issue persists | Investigate first failure |

**Do not treat a green retry as fixing the test.** An integration test repeatedly needing retries indicates a race, resource contention, or broken teardown. Record the root cause and preserve first-failure artifacts instead of raising retries indefinitely.

## 34. Practice Designing Pipelines by Risk

For a real e-commerce application:

- Modifying pricing rules: pricing unit tests act as the fast gate.
- Modifying JSON pricing endpoint: MVC slice + contract test.
- Modifying Orders table/transactions: JPA slice + real DB integration required.
- Modifying Spring Security: MVC security slice + real HTTP authorization integration.
- Modifying Dockerfile/JAR config: E2E startup/health against the artifact.
- Modifying connection pooling: integration with real service + load baseline.
- Modifying queue events/async: integration with broker/test-run consumer group.
- Modifying production migrations: apply schema migrations on a DB of the same dialect.
- Modifying the full checkout journey: selected black-box E2E across the specified services.

For each change, ask: **Which bugs could slip past the current group?** If tests only prove the controller while the risk is transactional, add the right kind of integration test. Expanding E2E everywhere is not always the best answer because of high cost and poor fault localization.

## 35. Review Questions

### A. Tag or Source Set?

All tests are in `src/test/java`; a developer adds `@Tag("unit")`. Does this remove Spring Boot Test from the unit classpath?

**Answer:** No. Tags only filter at runtime. For compile/dependency isolation, use source sets/JVM Test Suite or separate modules.

### B. Default Test Task

With this `build.gradle`, does `./gradlew test` run `@Tag("integration")`?

**Answer:** No, because of `excludeTags 'integration','e2e'`. It still runs untagged tests to reduce the risk of silent omission.

### C. Gradle Build

Does a passing `./gradlew build` prove `e2eTest` passed?

**Answer:** No. The Java `check` task includes `test` by default and does not automatically pull in custom groups. Inspect the task graph and reports.

### D. MVC Slice

`@WebMvcTest` mocks `TaskService`, and the JSON 201 test passes. Does that guarantee the service `@Transactional` commits?

**Answer:** No; the real service did not run. Real HTTP integration + DB readback protects that layer.

### E. JPA Query

Mockito returns a canned `ChecklistItem` regardless of title, while the production IgnoreCase query is wrong. Which group catches this better?

**Answer:** `@DataJpaTest` with H2/real DB and mixed-case inputs.

### F. Real HTTP Rollback

`@SpringBootTest(RANDOM_PORT)` test client has `@Transactional`. Does a POST committed inside the server roll back with the test thread?

**Answer:** No. Client and server run on separate threads/transactions. Clean up by ID or use an isolated database.

### G. E2E Safety

A developer changes `-Pe2eBaseUrl` to the production URL for a quick check. Should the test send POST/DELETE requests there?

**Answer:** No. The demo blocks non-loopback hosts. Other environments require authorization, allowlists, and dedicated test-data policies.

### H. 0 Methods Executed

Gradle `integrationTest` reports SUCCESS, but JUnit XML contains zero methods. Can the integration gate be considered verified?

**Answer:** No. Check classpath, tags, and actual executed test counts.

### I. Parallel Forks

Increasing `maxParallelForks` from 1 to 8 causes two tests to target the same DB row and fixed file name. What happens?

**Answer:** Races/collisions. Increasing parallelism does not create isolation; use unique fixtures/schemas or restrict non-parallel-safe groups.

### J. HTTP 200 Is Not Enough

E2E asserts 200 from `GET /api/tasks/{id}` without checking `completed` after POST. What bug could slip through?

**Answer:** The task was not updated/committed, yet the endpoint still reads and returns 200. Assert business state and DB/API readback.

### K. Testcontainers

A test relies on PostgreSQL-specific SQL; is an in-memory H2 JPA slice enough?

**Answer:** No. Create integration tests with Postgres Testcontainers and corresponding migrations.

### L. Context Cache

Every test class adds `@DirtiesContext` just to delete one row. Why does this slow down builds?

**Answer:** It evicts/reloads contexts repeatedly; rollbacks or scoped cleanup are usually more appropriate.

### M. Skipped E2E Job

The workflow runs E2E only on `workflow_dispatch`, and a release hasn't triggered it. What should the release report state?

**Answer:** E2E NOT RUN, not PASS. If mandatory, configure the corresponding workflow/approval and required gate.

### N. Counting Tests

One method tagged with both `slice` and `integration` runs from two tasks. What can happen?

**Answer:** Duplicate execution and fixture side-effect collisions; use one primary tag or explicitly handle duplicate executions.

### O. CI Artifacts

The integration job fails, but report upload only runs under `if: success()`. How do you investigate?

**Answer:** It is hard because artifacts are missing. Use `if: always()` and retain XML/HTML/logs with secrets filtered out.

## 36. Implementation Checklist

- [ ] Clearly define unit/slice/integration/E2E by boundary and bug hypothesis.
- [ ] Every test class has one primary scope tag.
- [ ] Unit tests avoid full Spring context/external IO when unnecessary.
- [ ] MVC/JPA slices do not overuse `@SpringBootTest`.
- [ ] Integration tests keep the real beans/AOP/DB under test.
- [ ] E2E does not inject internal repositories/beans in the test process.
- [ ] JUnit Platform is enabled with `useJUnitPlatform`.
- [ ] Custom Test tasks have proper `testClassesDirs` and `classpath`.
- [ ] `test` does not skip all untagged tests.
- [ ] Executed test counts are checked; 0 tests is never treated as a real PASS.
- [ ] `unitTest/sliceTest/integrationTest/e2eTest` have per-task reports.
- [ ] `check/build` task graph has been verified.
- [ ] CI required checks match release/merge policy.
- [ ] E2E job has an allowlist, app readiness check, and bounded timeouts.
- [ ] Test data uses UUID/owner and cleans up owned resources properly.
- [ ] `RANDOM_PORT` integration tests do not rely on test transaction rollback.
- [ ] JPA slices use rollback/flush-clear as needed.
- [ ] H2 is not used to conclude all production SQL dialects are correct.
- [ ] Do not delete shared DB/table data not owned by the test.
- [ ] Mutable state/Mockito mocks/scheduled jobs have isolation.
- [ ] `@DirtiesContext` is used only when a context cannot be safely reused.
- [ ] Testcontainers lifecycle aligns with Spring context cache.
- [ ] CI forks/parallel tasks do not contend on ports/DB/file paths.
- [ ] Persisted state is tested to catch transaction bugs.
- [ ] E2E reflects the built artifact and real public API.
- [ ] Scripts do not send data to unapproved production/staging targets.
- [ ] CI artifacts are saved on failure and do not leak secrets.
- [ ] Test flakiness has an owner and root cause, not infinite retries.
- [ ] Reports distinguish PASS/FAIL/SKIPPED/NOT RUN.
- [ ] QA accurately distinguishes code reviewed from tests actually executed.

**Conclusion:** Separating unit, slice, integration, and end-to-end tests helps CI deliver fast feedback, control costs, and preserve enough evidence for critical bugs. **Unit** protects business rules; **slice** protects MVC/JPA/client framework behavior; **integration** protects wiring, transactions, and real persistence/HTTP; **E2E** protects the packaged/started product and public journeys. JUnit `@Tag` + Gradle `Test` tasks are an easy starting point, though you must still manage **isolation, test discovery, Spring caching, data, and environment permissions**. A fast pipeline full of skipped tests or mocked-out dependencies is not a quality pipeline.

### Official References

- Gradle — Testing in Java & JVM projects, Test tasks, JUnit Platform tags, test classes/classpath: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — JVM Test Suite plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Gradle — Test task DSL: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Spring Boot 3.5 — Testing Spring Boot Applications, @WebMvcTest/@DataJpaTest/@SpringBootTest RANDOM_PORT: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — Test-managed transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- JUnit Jupiter — Tagging and Filtering: https://docs.junit.org/5.13.4/writing-tests/tagging-and-filtering.html
- JUnit Jupiter — Build Support for Gradle: https://docs.junit.org/5.13.4/running-tests/build-support.html
- Official Gradle GitHub Actions setup (v6): https://github.com/gradle/actions/blob/main/docs/setup-gradle.md
- GitHub Actions — Storing and sharing build artifacts: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
- Java SE 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Testcontainers for Java — Integration testing: https://java.testcontainers.org/
