# Roles of Services, Adapters, Configuration, and Data Access Components

When a Spring Boot application only has a single REST controller returning a greeting, almost all code can sit in one class. Yet as soon as the application must handle HTTP requests, enforce business rules, save to a database, send notifications, and run background work, that approach quickly makes the code hard to understand, hard to test, and hard to change.

**Source code organization** is deciding what each component is responsible for, what it is allowed to call, and what it depends on. In a Spring Boot application, four important groups are:

- **Service:** executes or orchestrates a use case and its associated business rules.
- **Adapter:** translates external interactions into application calls, or translates application requests into calls to external technologies.
- **Configuration:** declares beans, wires dependencies, and provides environment configuration values.
- **Data access component:** performs save, read, update, and delete operations against a database or other storage source.

These roles are **responsibility boundaries**, not merely folder names or annotations. A class suffixed with Service that handles HTTP directly, opens JDBC connections, and writes SQL still has too many responsibilities.

## 1. Full Picture of a Request Moving Through the Application

Suppose we are building a task management application. A client wants to create a new task:

~~~http
POST /api/tasks
Content-Type: application/json

{"title":"Learn Spring Boot"}
~~~

The application needs to accept the request, validate the title, save the task, and return an identifier. Responsibilities can be split as follows:

~~~text
Client
   │ HTTP POST /api/tasks
   ▼
TaskController                        ← Inbound adapter: HTTP
   │ converts JSON into Java calls
   ▼
TaskService                           ← Service: rules and use case
   │ calls persistence contract
   ▼
TaskStore                             ← Port: application needs storage capability
   ▲
   │ implementation
TaskJpaAdapter                        ← Outbound adapter: JPA
   │ converts data model and calls library
   ▼
Spring Data JPA Repository            ← Data access mechanism
   │
   ▼
Database

TaskConfiguration                     ← Bean configuration, Clock, properties
   └── participates in wiring the system at startup
~~~

**Controller** knows HTTP methods, URLs, request bodies, and response statuses. **Service** knows what steps make up "create a task." **TaskStore** describes the storage need without mentioning SQL. **TaskJpaAdapter** knows how to persist using JPA. **Configuration** supplies the dependencies and values needed when the application context is initialized.

This is a **ports and adapters** style of organization. A small project can also use a simpler layered structure: controller → service → Spring Data repository. Both approaches are compared later in the lesson.

## 2. Service: Where Use Cases Are Expressed

A **Service** represents an operation meaningful to the application, such as:

- Creating a task after validating data.
- Confirming an order when sufficient inventory exists.
- Calculating shipping fees according to pricing rules.
- Approving a request based on status and business permissions.
- Orchestrating data persistence and emitting events after an operation completes.

In Spring, the **@Service** annotation is a specialized form of **@Component**. A class within component scanning scope is registered as a bean and can be supplied to other beans via dependency injection:

~~~java
package com.example.tasks.application;

import org.springframework.stereotype.Service;

@Service
public class TitleNormalizer {

    public String normalize(String title) {
        return title == null ? null : title.strip();
    }
}
~~~

The **@Service** annotation lets the container manage the class; it **does not create business rules by itself**. Method contents, the class contract, and how the class depends on other parts determine its actual role.

### Application Service vs. Domain Service

| Type | Responsibility | Examples |
|---|---|---|
| **Application service** | Orchestrates a use case, interacts with ports/repositories, sets transaction boundaries | CreateTaskService, CheckoutService |
| **Domain service** | Executes business rules that do not belong solely to a single entity | PricingPolicy, ShippingPolicy |

An application service can call a domain service to calculate a price and then save the result. If the business logic is simple, you do not have to create two separate kinds of classes. What matters is knowing which logic belongs to **the business** and which logic belongs to **communicating with technology**.

### What Should a Service Usually Not Do?

- Directly return **ResponseEntity**, choose HTTP status codes, or read **HttpServletRequest** when handling ordinary business logic.
- Write raw SQL or open database connections when persistence already has a dedicated component.
- Manually instantiate dependencies that Spring could inject, making substitution and testing harder.
- Read configuration strings across many places using scattered key names.
- Pack all business logic into a single giant **CommonService**.

A service is valuable when it expresses a **clear use case** or a related set of rules, not when it is a pass-through layer created just to fill out a layer count.

## 3. Adapter: The Boundary Communicating with the Outside World

An **Adapter** converts external interactions into a contract the application understands, or implements a contract so the application can talk to external technology.

### Inbound Adapters

Inbound adapters receive signals that initiate work:

| Adapter | Signal | Example |
|---|---|---|
| REST controller | HTTP request | POST /api/tasks |
| CLI runner | Terminal command and arguments | Import a CSV file |
| Message listener | Message from a queue/broker | Process an order event |
| Scheduled job | Periodic schedule | Generate a nightly report |

Different inbound adapters can call the same **TaskService**. When replacing a terminal command with an HTTP endpoint, the task-creation rules do not necessarily need to be rewritten.

### Outbound Adapters

Outbound adapters allow the application to use external resources or services:

| Application Needs | Port / Contract | Implementing Adapter |
|---|---|---|
| Save tasks | TaskStore | JPA, JDBC, file storage |
| Send emails | NotificationSender | SMTP, email provider API |
| Fetch exchange rates | ExchangeRateProvider | HTTP client |
| Store documents | FileStorage | Filesystem, object storage |
| Publish events | EventPublisher | Kafka, RabbitMQ |

Class names do not have to end with **Adapter**. You might see names like **EmailGateway**, **JpaTaskStore**, or **ExternalPaymentClient**. "Adapter" describes their actual responsibility.

### What Is a Port?

A **Port** is a contract the application uses to describe a capability it needs, typically written as a Java interface:

~~~java
package com.example.tasks.application;

import java.time.Instant;
import java.util.Optional;
import com.example.tasks.domain.Task;

public interface TaskStore {
    Task save(String title, Instant createdAt);
    Optional<Task> findById(Long id);
}
~~~

The service depends on the **TaskStore** interface rather than directly on **JpaRepository** or SQL queries. A JPA adapter can **implement TaskStore**:

~~~text
TaskService ──► TaskStore (interface)
                     ▲
                     │ implements
               TaskJpaAdapter
                     │
                     ▼
               Spring Data JPA
~~~

In this approach, business code and the persistence contract point inward; technical code implements the contract from the outside. This is the **dependency inversion** principle.

You do not need to force an interface onto every class. A port is useful when you want to decouple the application contract from a specific technology or when multiple interchangeable adapters may exist.

## 4. Data Access Components: What to Store and How?

A data access component typically handles creating, finding, updating, and deleting records. With Spring Data JPA, an interface extending **JpaRepository** already provides common operations like **save**, **findById**, **findAll**, and **deleteById**.

~~~java
package com.example.tasks.adapter.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SpringDataTaskRepository
        extends JpaRepository<TaskEntity, Long> {
}
~~~

Spring Data generates the repository implementation/proxy at runtime. You do not have to write a class implementing basic CRUD operations manually, though you still must declare entities, configure a datasource, and organize transactions appropriately.

### Distinguishing Three Kinds of Data Models

| Kind | Role | Examples |
|---|---|---|
| **HTTP DTO** | Request/response contract between client and API | CreateTaskRequest, TaskResponse |
| **Domain model** | Data and rules the business cares about | Task |
| **Persistence entity** | Maps data to database tables, columns, and relationships | TaskEntity |

A simple CRUD project may share some data types. As the system grows, separating DTOs from entities avoids tying the HTTP contract to the database schema, prevents exposing unintended fields, and controls data representation.

### How Do @Repository and @Service Differ?

**@Repository** is also a specialization of **@Component**, but it signifies a data access role. In Spring-supported and properly configured scenarios, this annotation also participates in translating persistence exceptions into Spring's **DataAccessException** hierarchy.

**@Service** signifies business logic or a use case. Both can receive dependencies via constructors. Changing an annotation merely to get the program to start does not solve responsibility separation.

## 5. Configuration: Wiring Beans and Managing Settings

**Configuration** defines how components are created, connected, and customized. Spring Boot has two common groups of mechanisms:

1. **Java configuration:** @Configuration, @Bean, @EnableConfigurationProperties, and related declarations.
2. **Externalized configuration:** application.yml, application.properties, environment variables, command-line arguments, and other sources.

Classes annotated with **@Service**, **@Component**, and **@Repository** are usually found by Spring through component scanning. However, objects from external libraries or standard Java, such as **java.time.Clock**, may require an explicit bean declaration:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

A service can inject **Clock** via its constructor instead of calling **Instant.now()** directly. During testing, **Clock.fixed(...)** provides a deterministic timestamp, avoiding reliance on wall-clock time.

### Grouping Configuration with @ConfigurationProperties

For example, a task title length limit defined in **application.yml**:

~~~yaml
app:
  tasks:
    max-title-length: 120
~~~

Create the configuration properties class:

~~~java
package com.example.tasks.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tasks")
public record TaskSettings(int maxTitleLength) {
}
~~~

Register the configuration properties and other beans:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(TaskSettings.class)
public class TaskConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Spring Boot binds the **app.tasks.max-title-length** key to **TaskSettings.maxTitleLength** following relaxed binding rules. The service only knows the typed Java configuration object and does not have to remember string key names.

The two classes **ClockConfiguration** and **TaskConfiguration** are **two different ways to illustrate registering Clock**. In the complete application example below, only **TaskConfiguration** is used, avoiding duplicate Clock beans with the same function.

### Configuration Is Not Where Business Logic Lives

**@Configuration** is suitable for creating HTTP clients, configuring a Clock bean, registering properties, or customizing infrastructure components. It should not contain shipping fee calculation logic or order approval rules.

Spring Boot also provides **auto-configuration**: when required dependencies and information are present, Boot automatically prepares many default beans, such as MVC or JPA components. The application's Java configuration should only add or customize what is genuinely needed.

## 6. Building a Small Example Combining All Four Roles

We will assemble these components into an application that creates and reads tasks. This example uses **Java, Spring Web, Spring Data JPA, and H2 Database**. On Spring Initializr, select the corresponding dependencies:

- **Spring Web** for writing REST controllers.
- **Spring Data JPA** for accessing the database via JPA.
- **H2 Database** for experimenting with an in-memory database.

Place the main class in package **com.example.tasks**, with this structure:

~~~text
src/main/java/com/example/tasks/
├── TaskApplication.java
├── domain/
│   └── Task.java
├── application/
│   ├── TaskStore.java
│   ├── TaskService.java
│   └── TaskNotFoundException.java
├── adapter/
│   ├── web/
│   │   ├── TaskController.java
│   │   └── TaskErrorHandler.java
│   └── persistence/
│       ├── TaskEntity.java
│       ├── SpringDataTaskRepository.java
│       └── TaskJpaAdapter.java
└── config/
    ├── TaskSettings.java
    └── TaskConfiguration.java

src/main/resources/
└── application.yml
~~~

Placing the **@SpringBootApplication** class in the root package lets default component scanning discover components in subpackages.

### 6.1. Startup Class

File **TaskApplication.java**:

~~~java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskApplication.class, args);
    }
}
~~~

This class boots the Spring Boot application; it does not directly execute business logic or access the database.

### 6.2. Domain Model

File **domain/Task.java**:

~~~java
package com.example.tasks.domain;

import java.time.Instant;

public record Task(Long id, String title, Instant createdAt) {
}
~~~

In this basic example, **Task** is an immutable record holding business data. It is not a JPA entity and carries no HTTP annotations. In larger systems, the domain model may contain richer behavior and invariants.

### 6.3. Data Access Port

File **application/TaskStore.java**:

~~~java
package com.example.tasks.application;

import java.time.Instant;
import java.util.Optional;
import com.example.tasks.domain.Task;

public interface TaskStore {

    Task save(String title, Instant createdAt);

    Optional<Task> findById(Long id);
}
~~~

The port expresses only what the application needs. It does not need to import **JpaRepository**, **EntityManager**, or a JDBC driver.

### 6.4. Service

File **application/TaskNotFoundException.java**:

~~~java
package com.example.tasks.application;

public class TaskNotFoundException extends RuntimeException {

    public TaskNotFoundException(long id) {
        super("Task not found with id=" + id);
    }
}
~~~

File **application/TaskService.java**:

~~~java
package com.example.tasks.application;

import java.time.Clock;
import java.time.Instant;

import com.example.tasks.config.TaskSettings;
import com.example.tasks.domain.Task;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskStore store;
    private final Clock clock;
    private final TaskSettings settings;

    public TaskService(
            TaskStore store,
            Clock clock,
            TaskSettings settings) {
        this.store = store;
        this.clock = clock;
        this.settings = settings;
    }

    @Transactional
    public Task create(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException(
                    "Task title must not be blank");
        }

        String normalized = title.strip();
        if (normalized.length() > settings.maxTitleLength()) {
            throw new IllegalArgumentException(
                    "Title exceeds "
                    + settings.maxTitleLength() + " characters");
        }

        return store.save(normalized, Instant.now(clock));
    }

    @Transactional(readOnly = true)
    public Task get(long id) {
        return store.findById(id)
                .orElseThrow(() -> new TaskNotFoundException(id));
    }
}
~~~

The service uses three dependencies injected by Spring:

- **TaskStore** to save/query tasks without depending directly on JPA.
- **Clock** to obtain time through a replaceable dependency.
- **TaskSettings** to read configured limits.

**@Transactional** sets a transaction boundary around the task creation use case. **@Transactional(readOnly = true)** describes a read operation and supplies optimization hints to the transaction manager/persistence provider; it is not a security mechanism preventing all write statements.

Spring normally applies transactions through proxies. If one method directly calls another method **within the same object**, that call may bypass the proxy and fail to trigger the transaction annotation as expected. In this example, the web controller calls the Spring-managed service, matching standard usage.

### 6.5. Persistence Entity

File **adapter/persistence/TaskEntity.java**:

~~~java
package com.example.tasks.adapter.persistence;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "task_items")
public class TaskEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false)
    private Instant createdAt;

    protected TaskEntity() {
        // Constructor for JPA.
    }

    public TaskEntity(String title, Instant createdAt) {
        this.title = title;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

**TaskEntity** is the persistence model. **jakarta.persistence** annotations describe the table and columns. Notice that the **length = 120** limit should align with the business configuration limit; in production implementations, manage consistency between schema and validation.

### 6.6. Spring Data Repository and Persistence Adapter

File **adapter/persistence/SpringDataTaskRepository.java**:

~~~java
package com.example.tasks.adapter.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SpringDataTaskRepository
        extends JpaRepository<TaskEntity, Long> {
}
~~~

File **adapter/persistence/TaskJpaAdapter.java**:

~~~java
package com.example.tasks.adapter.persistence;

import java.time.Instant;
import java.util.Optional;

import com.example.tasks.application.TaskStore;
import com.example.tasks.domain.Task;
import org.springframework.stereotype.Repository;

@Repository
public class TaskJpaAdapter implements TaskStore {

    private final SpringDataTaskRepository repository;

    public TaskJpaAdapter(SpringDataTaskRepository repository) {
        this.repository = repository;
    }

    @Override
    public Task save(String title, Instant createdAt) {
        TaskEntity entity = new TaskEntity(title, createdAt);
        TaskEntity saved = repository.save(entity);
        return toDomain(saved);
    }

    @Override
    public Optional<Task> findById(Long id) {
        return repository.findById(id).map(this::toDomain);
    }

    private Task toDomain(TaskEntity entity) {
        return new Task(
                entity.getId(),
                entity.getTitle(),
                entity.getCreatedAt());
    }
}
~~~

The adapter implements the **TaskStore** contract, calls Spring Data, and maps **TaskEntity** to **Task**. If storage changes, service code can remain intact provided the new adapter fulfills the same contract. The example assumes only **one bean** implements TaskStore; if multiple implementations exist, choose explicitly with **@Qualifier**, **@Primary**, or equivalent configuration.

### 6.7. Configuration and Database

File **config/TaskSettings.java**:

~~~java
package com.example.tasks.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.tasks")
public record TaskSettings(int maxTitleLength) {
}
~~~

File **config/TaskConfiguration.java**:

~~~java
package com.example.tasks.config;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(TaskSettings.class)
public class TaskConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

File **src/main/resources/application.yml**:

~~~yaml
app:
  tasks:
    max-title-length: 120

spring:
  datasource:
    url: jdbc:h2:mem:taskdb
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

**H2 in-memory** is for practice: data does not persist once the process exits. **ddl-auto: create-drop** tells Hibernate to create the schema on startup and drop it when the context closes, suitable only for test environments where data can be discarded. Real applications usually use controlled migrations such as Flyway or Liquibase.

Keys under **spring.datasource** control the database connection; **spring.jpa** relates to JPA/Hibernate; **app.tasks** is the application's configuration namespace. Boot leverages starters and auto-configuration to build appropriate technical components; **TaskConfiguration** adds Clock and registers TaskSettings.

### 6.8. Web Adapter

File **adapter/web/TaskController.java**:

~~~java
package com.example.tasks.adapter.web;

import java.net.URI;
import java.time.Instant;

import com.example.tasks.application.TaskService;
import com.example.tasks.domain.Task;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
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
        Task created = service.create(request.title());
        URI location = URI.create("/api/tasks/" + created.id());

        return ResponseEntity.created(location)
                .body(TaskResponse.from(created));
    }

    @GetMapping("/{id}")
    public TaskResponse get(@PathVariable long id) {
        return TaskResponse.from(service.get(id));
    }

    public record CreateTaskRequest(String title) {
    }

    public record TaskResponse(
            Long id,
            String title,
            Instant createdAt) {

        static TaskResponse from(Task task) {
            return new TaskResponse(
                    task.id(),
                    task.title(),
                    task.createdAt());
        }
    }
}
~~~

Both DTOs are written as nested records inside the controller to keep the example easy to follow; larger projects can extract them into separate files. The controller converts requests into service calls and converts results into HTTP responses. **ResponseEntity.created(...)** represents HTTP **201 Created** and a **Location** header pointing to the newly created task.

To translate business exceptions into HTTP responses, add file **adapter/web/TaskErrorHandler.java**:

~~~java
package com.example.tasks.adapter.web;

import com.example.tasks.application.TaskNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TaskErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalidInput(IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, exception.getMessage());
    }

    @ExceptionHandler(TaskNotFoundException.class)
    ProblemDetail taskNotFound(TaskNotFoundException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, exception.getMessage());
    }
}
~~~

With this approach, the service does not have to import **HttpStatus**. The web adapter decides which business errors become HTTP 400 or 404. When an application has many kinds of input errors, prefer dedicated business exception types rather than letting one handler catch every **IllegalArgumentException**.

### 6.9. Running and Observing

Run the project with **bootRun** if using Gradle or **spring-boot:run** if using Maven. With default web configuration, the server typically uses **localhost:8080**.

On Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Learn Spring Boot"}'
~~~

On Windows PowerShell:

~~~powershell
$body = @{ title = "Learn Spring Boot" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8080/api/tasks" -Method Post -ContentType "application/json" -Body $body
~~~

Illustrative response:

~~~http
HTTP/1.1 201 Created
Location: /api/tasks/1
Content-Type: application/json

{"id":1,"title":"Learn Spring Boot","createdAt":"2026-01-01T00:00:00Z"}
~~~

The **id** and **createdAt** above only illustrate the format; actual values are determined by the database and execution time. You can read it back:

~~~bash
curl http://localhost:8080/api/tasks/1
~~~

If the id exists, the application returns the data; if not, the service throws **TaskNotFoundException** and the web adapter returns **404**. When the title is blank or exceeds the limit, the service rejects creation and the web adapter returns **400**.

Tracing each piece in the POST request:

| Step | Class | Role |
|---|---|---|
| Receive HTTP | TaskController | Parse request DTO, call service |
| Process business logic | TaskService | Validate title, get time, coordinate transaction |
| Storage contract | TaskStore | Describe save/findById capability |
| Connect JPA | TaskJpaAdapter | Map TaskEntity, call repository |
| Interact with database | SpringDataTaskRepository | Execute operations via JPA |
| Return HTTP | TaskController | Build response DTO, status 201 and Location |
| Wire dependencies | TaskConfiguration | Create Clock, register TaskSettings at startup |

**Configuration does not sit between the controller and the database as a business step on every request**. It mainly ensures beans are ready in the ApplicationContext.

## 7. Dependency Direction Matters More Than Folder Names

In the example:

- **domain/Task.java** does not import Spring MVC or JPA.
- **application/TaskStore.java** does not import Spring Data.
- **TaskService** depends on ports, models, and configuration, without knowing table names.
- **adapter/persistence/** depends on ports and models to implement persistence.
- **adapter/web/** depends on the service to trigger use cases.

~~~text
Web adapter ──► Application service ──► Domain
                         │
                         ▼
                    TaskStore port
                         ▲
                         │
                    JPA adapter ──► Spring Data ──► Database

Spring container / configuration wires the beans.
~~~

In the example, the application service still uses Spring annotations such as **@Service** and **@Transactional**. This is a moderate level of separation: business logic avoids direct dependencies on HTTP and JPA while still using Spring for bean/transaction management. If a stricter pure-Java core is required, those infrastructure concerns can be moved outward, at the cost of a more complex structure.

### Organize by Layer or by Feature?

**By technical layer:**

~~~text
com.example.app/
├── controller/
│   ├── TaskController.java
│   └── UserController.java
├── service/
│   ├── TaskService.java
│   └── UserService.java
├── repository/
│   ├── TaskRepository.java
│   └── UserRepository.java
└── config/
~~~

**By feature:**

~~~text
com.example.app/
├── task/
│   ├── application/
│   ├── domain/
│   └── adapter/
├── user/
│   ├── application/
│   ├── domain/
│   └── adapter/
└── shared/
~~~

By-layer organization is approachable when there are few classes. When there are many features, by-feature organization puts files for the same business capability close together, clarifies ownership, and keeps **service/** from growing too large. Naming conventions matter less than having a **consistent dependency direction** and clear responsibilities.

## 8. The Simple Case: Service Calling JpaRepository Directly

Not every project needs a separate port and adapter. For a small CRUD application, the model:

~~~text
Controller → Service → JpaRepository → Database
~~~

can be clear enough. Simplified example, assuming **TaskRepository** extends JpaRepository and **TaskNotFoundException** is already defined:

~~~java
@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public TaskEntity get(Long id) {
        return repository.findById(id)
                .orElseThrow(() -> new TaskNotFoundException(id));
    }
}
~~~

The advantage is fewer interfaces and mappers. The drawback is that the service depends directly on Spring Data and JPA entities. If you later need to replace persistence or test business logic completely isolated from the database, this can affect more classes.

**Ports and adapters** bring technology isolation at the cost of extra files and mapping. Choose based on real complexity, not because every project needs the exact same structure.

## 9. Which Role Owns Transactions?

When a use case includes multiple data operations that must succeed together or roll back together, the **application service** is usually the right place to define transaction boundaries.

~~~text
CheckoutService.checkout(...)
  ├── Validate items
  ├── Deduct inventory
  ├── Save order
  └── Complete transaction
~~~

Example illustrating annotation placement:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void checkout(CheckoutCommand command) {
        // Database operations belonging to the same use case.
    }
}
~~~

The snippet above uses a hypothetical **CheckoutCommand** to illustrate a transaction boundary, not a class from the task management application we built.

Key points:

- **@Transactional** works through the corresponding transaction manager; it does not automatically create a distributed transaction spanning databases, emails, and HTTP APIs.
- By default, Spring normally rolls back on **RuntimeException** and **Error**; checked exceptions follow different rules unless configured otherwise.
- **readOnly = true** is a hint to the transaction infrastructure, not a security rule.
- When needing to both write to a database and send a message, design proper failure handling and consistency, such as a transactional outbox or controlled retry mechanism.

Transactions aligned with **use cases** are usually more natural than transactions tied rigidly to controllers, since the same business logic may be invoked from web, CLI, or worker processes.

## 10. How Does Dependency Injection Connect the Parts?

~~~text
Spring ApplicationContext
  ├── TaskController
  │      └── needs TaskService
  ├── TaskService
  │      ├── needs TaskStore
  │      ├── needs Clock
  │      └── needs TaskSettings
  ├── TaskJpaAdapter (implements TaskStore)
  │      └── needs SpringDataTaskRepository
  ├── SpringDataTaskRepository (proxy)
  ├── Clock (from @Bean)
  └── TaskSettings (from @ConfigurationProperties)
~~~

**Constructor injection** makes a class's dependencies explicit. With a single constructor, Spring normally does not require **@Autowired**. If a required bean is missing, multiple beans of the same type exist without a selection rule, or a circular dependency occurs, ApplicationContext startup can fail.

An example like **TaskService → NotificationService → TaskService** is a sign to review business ownership flows rather than enabling lazy initialization for all beans by default to hide the cycle.

## 11. One Service Can Be Called from Multiple Adapters

Suppose you want to create a task when the CLI runs. Another inbound adapter can reuse **TaskService**:

~~~java
@Component
class TaskImportCommand implements ApplicationRunner {

    private final TaskService tasks;

    TaskImportCommand(TaskService tasks) {
        this.tasks = tasks;
    }

    @Override
    public void run(ApplicationArguments args) {
        tasks.create("Task imported from CLI");
    }
}
~~~

Or a scheduled job:

~~~java
@Component
class DailyTaskJob {

    private final TaskService tasks;

    DailyTaskJob(TaskService tasks) {
        this.tasks = tasks;
    }

    @Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
    void createDailyTask() {
        tasks.create("Check start-of-day tasks");
    }
}
~~~

These two additional examples require the corresponding imports; the scheduler also requires enabling **@EnableScheduling**. Add them only if you truly want the application to run those tasks. The key takeaway is that **validation and persistence rules remain in the service**, regardless of whether the trigger arrives from HTTP, CLI, or a schedule.

## 12. Testing by Responsibility

Clean code organization helps design tests with the right scope:

| Component | What to Verify | Common Approach |
|---|---|---|
| **Service** | Title rules, business errors, orchestration | Fake/mock TaskStore and fixed Clock |
| **Web adapter** | Mapping, JSON, HTTP status, error responses | Test web layer with MockMvc or equivalent config |
| **Persistence adapter** | Entity mapping, queries, and data constraints | Integration test against an appropriate database |
| **Configuration** | Value binding, bean creation, selecting the right bean | Controlled Spring context tests |
| **End-to-end flow** | Request is persisted and can be read back | Integration test with required components |

A service using **TaskStore** is easy to test before a database is ready: the port can be replaced by an in-memory implementation. Conversely, entity mapping errors inside the persistence adapter fit integration tests better.

There is no need to write tests just to prove a getter calls another getter. Focus on **reliable behavior**: blank titles are rejected, valid tasks are saved, missing ids return 404, and transactions behave as required.

## 13. Common Code Organization Mistakes

### Controller Doing All the Work

~~~java
@PostMapping("/orders")
public ResponseEntity<?> create(@RequestBody OrderRequest request) {
    // Check all business rules.
    // Write SQL, calculate totals, send email, and decide retries.
    // Return HTTP response.
}
~~~

If a controller does too much, reusing the same business logic from a queue or CLI becomes hard. Let the HTTP adapter handle the protocol, the service handle the use case, and outbound adapters handle integration.

### Service Only Forwarding Meaninglessly

~~~java
public TaskEntity save(TaskEntity entity) {
    return repository.save(entity);
}
~~~

Not every forwarding method is wrong, yet if an entire service merely duplicates CRUD without expressing use cases, reconsider whether that layer adds real value.

### Repository Containing Non-Data Business Rules

Repositories can execute complex queries, but decisions like "how much discount does a VIP customer get" or "is an order approved" generally belong to domain/application. Do not automatically push all business logic into SQL just because it is possible.

### Configuration Becoming a Dumping Ground for Utilities

An oversized **AppConfig** class that creates beans while reading files, calculating prices, and sending HTTP requests blurs the line between wiring and processing. Configuration should focus on creating beans and configuring the application.

### Returning JPA Entities Directly via API

Entities may hold lazy-loading relationships or fields not meant for clients. Using explicit DTOs keeps the HTTP contract more independent from the schema and controls output data.

### Creating Interfaces for Every Class Without a Boundary to Protect

Ports are useful for avoiding technology lock-in or supporting multiple adapters, yet generating interfaces for every class without a need can make tracing code unnecessarily complex.

### Placing the Startup Class Outside Component Scanning Scope

If the **@SpringBootApplication** class sits inside a subpackage while services/controllers sit outside the default scan scope, Spring may not create beans. The common approach is placing the startup class in the root package containing the application's subpackages.

## 14. Identifying Responsibilities by Questions

| Question | Usually Appropriate Place |
|---|---|
| "Which HTTP path receives the request? Return 201 or 404?" | Web adapter / Controller |
| "How does the CLI command parse arguments and call business logic?" | CLI adapter / Runner |
| "When creating an order, what steps must happen?" | Application service |
| "How are pricing and discount rules determined?" | Domain model / Domain service |
| "Through what contract does the application need storage capability?" | Output port |
| "Where are domain models converted to JPA entities?" | Persistence adapter |
| "How are database queries written?" | Repository / Data access |
| "Where are external API URLs, timeouts, and title limits configured?" | Configuration properties |
| "How are a shared Clock or HTTP client created?" | @Configuration / @Bean |

These questions are more useful than looking solely at class names. An **OrderService** returning **ResponseEntity** carries HTTP responsibilities; an **OrderRepository** sending emails itself carries external integration responsibilities.

## 15. Principles to Keep Growing the Project

**Keep controllers thin and clear.** Controllers handle requests/responses, while services handle business actions. If a controller grows complex alongside the number of business rules, that is a signal to review boundaries.

**Place transactions at the use case when appropriate.** Multiple data updates sharing one business meaning typically belong in the same transaction boundary, rather than each adapter deciding independently.

**Prefer constructor injection.** Classes declare dependencies explicitly, making them easy to substitute in tests and exposing missing beans at startup.

**Isolate external integrations at changeable boundaries.** Databases, email providers, payment gateways, and message brokers often change independently of business rules.

**Group configuration by purpose.** Clearly named configuration objects prevent scattering string keys throughout code. Sensitive values should live in an appropriate secret source, not hardcoded in the repository.

**Avoid circular dependencies and unbounded shared packages.** When services call each other without clear direction, changing and testing code grows harder. Splitting by feature helps clarify use-case ownership.

**Choose an appropriate level of architecture.** Small CRUD REST APIs can start with controller → service → repository. As needs for testing, reuse, or swapping technologies arise, split out ports and adapters at the necessary boundaries.

## Conclusion

In Spring Boot, **services** execute and coordinate use cases; **adapters** connect the application to HTTP, CLI, schedulers, databases, or external systems; **configuration** creates beans and supplies settings; and **data access components** focus on storage and querying.

The key flow to remember is: **inbound adapter receives request → service processes business logic → output port/adapter accesses needed resources → inbound adapter returns result**. Configuration ensures dependencies are properly wired when the application starts.

When these responsibilities are clear, adding a new endpoint, moving a task to a worker, swapping a database, or testing a business rule causes minimal disruption to unrelated parts. That is the practical value of organizing source code around responsibility boundaries.
