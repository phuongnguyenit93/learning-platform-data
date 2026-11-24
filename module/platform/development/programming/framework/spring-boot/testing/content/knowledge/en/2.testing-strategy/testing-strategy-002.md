# Allocating Unit, Slice, and Integration Tests Across Spring Boot Architecture

## 1. Goals and Principles

This lesson answers the question: in a Spring Boot system, **which behaviors should be checked with unit tests, which need slice tests, and which paths require integration tests?** Allocation is based on *architectural boundaries, likely defect types, and feedback cost*, rather than enforcing a rigid ratio for every project.

After completing this lesson, you will be able to:
- Read a layered or hexagonal/clean architecture diagram to place tests at the right boundaries.
- Choose between JUnit 5 + Mockito (unit), `@WebMvcTest`/`@DataJpaTest` (slice), and `@SpringBootTest` (integration), and know what each type **does not** prove.
- Design a test suite for a feature from HTTP down to the database without repeating the exact same check at every layer.
- Establish a CI test execution policy based on risk rather than annotation counts.

The examples below use **Java 17, Maven, Spring Boot 3.5.7, JUnit Jupiter, and Mockito**. Spring Boot 4 changes the module/package of some testing annotations; when using Boot 4, check the documentation for your exact version to update dependencies/imports. **The boundary-based allocation strategy remains unchanged.**

## 2. Reading the Architecture Before Choosing Test Types

A simple MVC application:

```text
HTTP + JSON
    |
    v
CustomerController (web adapter: route, body, status)
    |
    v
CustomerService (application/use case: business rules)
    |
    v
CustomerRepository (outbound port / Spring Data adapter)
    |
    v
JPA + SQL database
```

In hexagonal/clean architecture, `CustomerService` should depend on a *port interface* and not directly on HTTP/JPA. In traditional layered architecture, a Spring Data repository may be used directly as a service dependency; the testing principle remains to choose the **smallest boundary capable of catching the defect you need to observe**.

| Type | What It Starts | Focus of Proof | What It Does Not Prove |
| --- | --- | --- | --- |
| **Unit** | Java objects, JUnit/Mockito; no Spring context needed | Rules, branches, state, interactions with fake/mocked ports | MVC mapping, dependency injection, SQL, serialization |
| **Slice** | Part of the Spring `ApplicationContext` and a subset of auto-configuration | The contract of *one adapter/layer*: HTTP, JSON, validation, JPA queries, mappings | The entire chain request → real service → real DB |
| **Integration** | Multiple layers together; typically `@SpringBootTest` and real or equivalent infrastructure | Bean wiring, transactions, configuration, cross-layer flows, real protocols/SQL | Every combination of business rules if only a few flows are exercised |

Terminology note: `@DataJpaTest` still integrates JPA with a database, but in **Spring Boot scope classification** it is a *persistence slice*. “Integration” in this lesson refers to tests connecting multiple layers or meaningful infrastructure. This distinction avoids naming debates when designing tests.

## 3. Allocation Map by Architectural Responsibility

| Component / Risk | Default Recommended Test | When to Escalate to Integration |
| --- | --- | --- |
| Domain: pricing, limits, state transitions, invariants | Unit, without Spring; boundary data and invalid cases | Rules depend on isolation, transactions, or multiple real services |
| Application service / use case | Unit, mock/fake **outbound ports**, assert return values and core side effects | `@Transactional`, retries, events, transaction boundaries, or wiring chains at risk of misconfiguration |
| REST controller, request/response, status, exception handler | `@WebMvcTest(Controller.class)` + `MockMvc`, mock service | Real security filters, multi-layer routing, serialization + database, full HTTP stack |
| Repository / JPA mapping, JPQL, constraints, queries | `@DataJpaTest`, running entities/repositories with a DB | Production-specific SQL/dialect/locks/migrations; use matching DB engine via Testcontainers |
| HTTP client / adapter calling external systems | Unit for data conversion; slice/client test with HTTP stub | TLS/auth/network timeouts, real protocol, and contract with real/staging system |
| Security, transactions, caching, message broker, scheduling | Targeted slice if supported; add focused integration | When behavior depends on full context, AOP/proxies, ACLs, brokers, or async coordination |
| Critical business flow where data loss is unacceptable | Unit for all branches + targeted adapter slices + integration for happy path and key failures | Cross-service contract / E2E smoke for deployment boundaries |

**Selection rule:** pure algorithmic defect → unit; single-adapter conversion/contract defect → slice; defect occurring only when **two real parts interact** → integration. A single behavior may need more than one test if those tests protect **different risks**.

Do not treat a mocked repository call verification as proof that data was saved. Do not treat `@WebMvcTest` as proof that the service works. Do not treat `@SpringBootTest` as automatically testing every exception branch.

## 4. Allocation Along a Functional Flow: Customer Registration

Suppose `POST /customers` receives an email, the service normalizes it to lowercase, checks for duplicates, and saves it to the database.

| Scenario | Primary Test | Reason |
| --- | --- | --- |
| Email with whitespace/uppercase must be normalized | **Service unit** | Pure data and service logic rule |
| Blank/malformed email is rejected | **Service unit** | Many boundary inputs, runs fast |
| Duplicate email does not call `save` | **Service unit** | Application decision; mock port checks interaction |
| JSON request binds, HTTP returns 201, `Location` and response match | **Web slice** | HTTP/Jackson/`MockMvc` contract |
| Business errors map to 400/409 | **Web slice** | Exception handler belongs to the web adapter |
| `findByEmail`, unique constraint, JPA mapping | **JPA slice** | Persistence + database contract |
| Real request through controller → real service → real repository saves record | **Integration** | Proves cross-layer wiring and transaction |
| Production DB uses Postgres, specific queries, or migrations | **Integration with Postgres Testcontainers** | H2 does not prove production dialect/DDL behavior |
| Endpoint authorization / JWT filter | **Security-focused integration** with real config | Decision lives in security chain and configuration |

Illustrative starting ratio for **100 test scenarios**: roughly 65 unit, 25 slice, 10 integration. This is a *planning heuristic, not a KPI*: algorithm-heavy domains may need 85% unit; CRUD-heavy or integration-heavy systems may need more slices/integration. Count **risks protected**, rather than forcing test counts to hit a percentage.

## 5. Runnable Maven Example: One Path, Four Layers of Protection

### 5.1. Project Structure

```text
pom.xml
src/main/java/com/example/testing/
  TestingApplication.java
  Customer.java
  CustomerRepository.java
  CustomerService.java
  CustomerController.java
  ApiErrorHandler.java
src/test/java/com/example/testing/
  CustomerServiceTest.java
  CustomerControllerTest.java
  CustomerRepositoryTest.java
  CustomerFlowIntegrationTest.java
```

`pom.xml`: the example pins Spring Boot 3.5.7 so the imports below stay consistent; in a real project, align the version with your project's BOM.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>testing-strategy</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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
```

`TestingApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

`Customer.java`:

```java
package com.example.testing;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {} // JPA requires a no-arg constructor

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

`CustomerRepository.java`:

```java
package com.example.testing;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    boolean existsByEmail(String email);
    Optional<Customer> findByEmail(String email);
}
```

`CustomerService.java` holds the use case. The email check below is intentionally simple for this lesson; production requires proper validation, normalization, and uniqueness handling policies.

```java
package com.example.testing;

import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public RegistrationReceipt register(String rawEmail) {
        String email = rawEmail == null
                ? ""
                : rawEmail.trim().toLowerCase(Locale.ROOT);

        if (!email.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) {
            throw new IllegalArgumentException("Invalid email");
        }
        if (repository.existsByEmail(email)) {
            throw new IllegalStateException("Email already exists");
        }

        Customer saved = repository.save(new Customer(email));
        return new RegistrationReceipt(saved.getId(), saved.getEmail());
    }

    public record RegistrationReceipt(Long id, String email) {}
}
```

`CustomerController.java` handles only HTTP; all registration rules reside in the service.

```java
package com.example.testing;

import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/customers")
public class CustomerController {
    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerService.RegistrationReceipt> create(
            @RequestBody CreateRequest request) {
        var result = service.register(request.email());
        return ResponseEntity
                .created(URI.create("/customers/" + result.id()))
                .body(result);
    }

    public record CreateRequest(String email) {}
}
```

`ApiErrorHandler.java` determines HTTP status codes for business errors.

```java
package com.example.testing;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> duplicated(IllegalStateException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", ex.getMessage()));
    }
}
```

### 5.2. Unit Test: Service Rules Without Starting Spring

`src/test/java/com/example/testing/CustomerServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {
    @Mock CustomerRepository repository;

    @Test
    void normalizesEmailBeforeSaving() {
        var service = new CustomerService(repository);
        when(repository.save(any(Customer.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        var result = service.register("  A@Example.COM  ");

        assertEquals("a@example.com", result.email());
        verify(repository).existsByEmail("a@example.com");
        verify(repository).save(
                org.mockito.ArgumentMatchers.argThat(c ->
                        "a@example.com".equals(c.getEmail())));
    }

    @Test
    void refusesDuplicateWithoutSaving() {
        var service = new CustomerService(repository);
        when(repository.existsByEmail("a@example.com")).thenReturn(true);

        assertThrows(IllegalStateException.class,
                () -> service.register("a@example.com"));

        verify(repository, never()).save(any(Customer.class));
    }

    @Test
    void invalidEmailDoesNotTouchPersistence() {
        var service = new CustomerService(repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.register("   "));

        verifyNoInteractions(repository);
    }
}
```

Here Mockito creates a fake repository, enabling branch and invocation checks. You **cannot** conclude from this unit test that Hibernate saves data, that constraints execute, or that `@Transactional` takes effect. Having the mock return an entity without an ID in `normalizesEmailBeforeSaving` is intentional: the test only verifies normalization, not database ID generation.

### 5.3. Web Slice Test: HTTP Contract and MVC

`src/test/java/com/example/testing/CustomerControllerTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CustomerController.class)
class CustomerControllerTest {
    @Autowired MockMvc mvc;
    @MockitoBean CustomerService service;

    @Test
    void createsHttpResponse() throws Exception {
        when(service.register("a@example.com")).thenReturn(
                new CustomerService.RegistrationReceipt(42L, "a@example.com"));

        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"a@example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/customers/42"))
                .andExpect(jsonPath("$.email").value("a@example.com"));
    }

    @Test
    void convertsBusinessErrorToConflict() throws Exception {
        when(service.register("a@example.com"))
                .thenThrow(new IllegalStateException("Email already exists"));

        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"a@example.com\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("Email already exists"));
    }
}
```

`@WebMvcTest` loads MVC configuration, the controller, advice, and `MockMvc`, replacing the service with `@MockitoBean`. It catches routing, HTTP status, binding, JSON, and handler bugs; it **does not** run the real use case or database. With Spring Security on the classpath, the slice typically includes the filter chain; use Spring Security test support and test authentication/authorization intentionally rather than disabling filters just to get green tests.

### 5.4. JPA Slice Test: Real Repository and Mapping

`src/test/java/com/example/testing/CustomerRepositoryTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired CustomerRepository repository;

    @Test
    void storesAndFindsByEmail() {
        Customer saved = repository.saveAndFlush(
                new Customer("db@example.com"));

        assertNotNull(saved.getId());
        Customer loaded = repository.findByEmail("db@example.com")
                .orElseThrow();
        assertEquals("db@example.com", loaded.getEmail());
    }
}
```

`@DataJpaTest` creates only the persistence slice (entities, Spring Data JPA, transactions, database), rolling back after each test by default. Because the H2 dependency is present, the example uses embedded H2. Choose this test type to check queries and mappings; if production uses PostgreSQL with JSONB, collations, locks, or specific migrations, **replace H2 with PostgreSQL Testcontainers** for tests requiring high fidelity. Note that rolling back after a test does not completely replace data cleanup for multi-threaded tests or a real HTTP server.

### 5.5. Integration Test: One Cross-Layer Flow, Real Beans

`src/test/java/com/example/testing/CustomerFlowIntegrationTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerFlowIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired CustomerRepository repository;

    @Test
    @Transactional
    void postCreatesCustomerThroughRealServiceAndRepository() throws Exception {
        mvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"FLOW@Example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.email").value("flow@example.com"));

        assertTrue(repository.findByEmail("flow@example.com").isPresent());
    }
}
```

This is a **full Spring context + MockMvc**, without starting a real HTTP server. It proves that the controller, service, JPA, and auto-configuration wire together properly. `@Transactional` here enables rollback under the same-thread MockMvc model; if you switch to `@SpringBootTest(webEnvironment = RANDOM_PORT)` and call via an HTTP client, server requests run in their own transactions, so **the test's transaction will not roll back server operations**. In that case, isolate data with a dedicated schema/container, explicit cleanup, or unique identifiers.

### 5.6. Running and Interpreting Results

Place all files at the paths above, with JDK 17+ and Maven installed:

```bash
mvn -q -Dtest=CustomerServiceTest test
mvn -q -Dtest=CustomerControllerTest test
mvn -q -Dtest=CustomerRepositoryTest test
mvn -q -Dtest=CustomerFlowIntegrationTest test
mvn -q test
```

The first four commands run one test class each; the last runs all four classes because their names end with `Test`. Success means Maven returns exit code 0 and all assertions pass; log/summary output depends on the environment, so do not assume a fixed stdout format. The source code *must* be compiled with Maven dependencies; running `javac` alone without the Spring/JUnit classpath will not compile, making `mvn test` the proper reproducible command for this example.

To test manually, run `mvn spring-boot:run` and send an HTTP request:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -d '{"email":"A@Example.com"}'
```

With an empty H2 database, the endpoint returns **201 Created**, header `Location: /customers/1` (the ID may differ if data already exists), and a JSON body containing `id` and email `a@example.com`. Sending the same email again returns **409 Conflict**. The example uses in-memory H2 and is not meant to demonstrate persistent storage after the application stops.

## 6. When Do You Need Deeper Tests Than Sample Slices?

**Database:** H2 suffices for basic CRUD and simple mappings, but may differ from PostgreSQL/MySQL in SQL dialect, collation, isolation, JSON/arrays, indexes, and constraints. For code depending on those features, run repository/integration tests against the same database engine and a version close to production, using Testcontainers + `@ServiceConnection` (compatible Spring Boot versions) or `@DynamicPropertySource`; add Testcontainers/JUnit dependencies and Docker when setting it up. Test Flyway/Liquibase migrations on a clean schema and verify that actual migrations execute.

**Inter-service communication:** Unit tests mock the HTTP client to check retry/timeout decisions; client-level tests with an HTTP stub verify requests/responses, 4xx/5xx errors, headers, and serialization; contract tests verify that both sides agree on the schema; a few E2E smoke tests across real deployments catch routing, auth, DNS, and compatibility issues. Do not replace hundreds of unit tests with a hard-to-diagnose E2E test.

**Events, queues, transactions:** For Kafka/RabbitMQ/outbox, unit-test the event selection logic; integration-test serialization, publish/consume, idempotency, retries, dead-letter handling, and commit/rollback. A mocked broker does not prove delivery semantics or concurrency behavior.

**Security:** Web slices cover 401/403 and endpoint role policies; integration tests cover `SecurityFilterChain`, filter ordering, token converters, method security, and critical endpoints. Distinguish between “unauthenticated” (401) and “authenticated but lacking permission” (403) per the actual configuration.

**AOP/proxies:** `@Transactional`, `@Cacheable`, retry annotations, and method security operate through Spring proxies/interceptors; unit tests calling the object directly usually do not trigger these mechanisms. Use targeted integration tests when the risk lies in proxy behavior.

## 7. Keeping the Test Suite Fast, Stable, and Reliable

1. **Behavior catalog first, annotations second.** List rules, adapter contracts, and infrastructure boundaries for each feature. Assign each risk to one primary verification location; duplicate only when a second layer protects a different risk.
2. **Mock at external boundaries.** Mock repositories/HTTP ports in service unit tests; mock the application service in web slices. Avoid mocking the class under test, JPA internals, or stubbing every call so tightly that the test merely mirrors implementation.
3. **Prefer meaningful outcome assertions.** In unit tests, assert data and critical side effects; in MVC, assert status, body/headers; in JPA, assert records/queries/constraints; in integration tests, assert observable final state. `verify(...)` is only helpful when the interaction itself is part of the contract.
4. **Independent data.** Each test builds its own fixture; keep clocks/UUIDs/ports controllable; use a fake clock instead of `Thread.sleep`; avoid relying on execution order, machine timezones, or fixed auto-increment IDs.
5. **Optimize context caching.** Sharing identical Spring test configurations lets `ApplicationContext` be reused. Overusing `@DirtiesContext` or needlessly varying profiles/properties/`@MockitoBean` slows tests down. Still, never sacrifice isolation merely for a cache hit.
6. **Organize by layer and speed.** CI on PRs should run unit + slice tests and core integration tests; infrastructure-heavy flows can run on merge/nightly, or on PRs when changes directly touch those boundaries. “Flaky” tests must be investigated, not hidden behind higher retry counts.
7. **Do not equate coverage with quality.** Line coverage can be high even when missing state checks, transaction bugs, or API contract breaks. Also evaluate branch/boundary coverage, mutation testing for complex domains, critical-bug detection, and feedback time.
8. **Clear separation of responsibilities.** For instance, the controller handles HTTP, the service handles normalization/duplication, and the repository handles persistence; if one class does all three, writing effective unit and slice tests becomes hard. Difficulty testing often signals poorly drawn architectural boundaries.

### Common Allocation Mistakes and Fixes

| Symptom | Consequence | Action |
| --- | --- | --- |
| Every test class uses `@SpringBootTest` | Slow, hard to isolate failures, heavy DB setup | Replace logic tests with unit tests; controller/JPA with slices; keep full-context for wiring |
| Controller test mocks `MockMvc` or service mocks itself | Fails to test real Spring HTTP or real decisions | Use auto-configured `MockMvc`; mock collaborators outside the boundary |
| Service unit test claims “DB saved” based on `verify(save)` | Misses mapping, DDL, and transaction bugs | Add `@DataJpaTest` and a cross-layer integration test |
| Only end-to-end happy path exists | Error branches hard to cover; bugs caught late | Push input matrices/edge cases down to unit tests; reserve E2E for vital journeys |
| Only H2 used for complex production SQL | Misses dialect/constraint/migration errors | Testcontainers with matching DB engine for high-risk areas |
| Tests depend on records created by other tests | Fails when run individually or repeated | Dedicated fixtures, transactions/cleanup/test namespaces |
| Testing via RANDOM_PORT and expecting test `@Transactional` to roll back server | Data leaks across runs | Isolate container/database or perform explicit cleanup |
| Running identical tests across 3 layers | Wastes time while adding little evidence | Differentiate goals: rules / adapter contracts / wiring |

## 8. Checklist for Applying This to a Real Spring Boot Module

Before adding tests, answer in order:

- **Architecture map:** where are inputs (HTTP/events/jobs), use cases, domain logic, ports, data adapters, and external systems?
- **Risks to catch:** business branches, serialization/validation, SQL/dialect, transactions, security, retries/events, wiring?
- **Smallest boundary:** no Spring needed → unit; exact single Spring adapter → slice; multiple beans/infrastructure interacting → integration.
- **Fidelity:** are mocks/fakes sufficient, or are real databases/brokers/servers needed? If using H2, which production assumptions remain untested?
- **Independent evidence:** do tests assert outputs and observable state without coupling to pointless internals; are fixtures isolated and tests repeatable?
- **CI budget:** unit and slices for fast feedback; critical integration on PRs; broader suites before release or when risk demands.

A well-strategized feature typically has **many unit tests for business branches, several slice tests for adapter contracts, and a few selective integration tests for high-value wiring paths**. This structure delivers fast feedback, pinpoints the failing layer, and still catches configuration/SQL errors that never surface under mocks.

## 9. Official References

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Current Spring Boot reference (check package changes when upgrading to Boot 4): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
