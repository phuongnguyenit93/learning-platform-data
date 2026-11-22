# Aligning Servlet, JPA, Validation, and Related Jakarta APIs

## 1. Context: Upgrading to Jakarta Is More Than Fixing Imports

When migrating an enterprise Java system from legacy Java EE to Jakarta EE, failures commonly surface at boundaries between seemingly independent components: Servlet containers, JPA providers, Bean Validation providers, transaction managers, CDI, JSON/XML libraries, security filters, and generated code.

An application may have replaced every source import from `javax.servlet` to `jakarta.servlet` while still deploying to an older Servlet container that only understands `javax.servlet`. Or entities may use `jakarta.persistence` while the ORM provider, annotation processor, and `persistence.xml` still belong to the `javax.persistence` generation. Similarly, `jakarta.validation` annotations may compile cleanly yet fail to execute at runtime when a Bean Validation provider or corresponding integration is missing.

**Aligning Jakarta APIs** means choosing a consistent set across:

1. Target Jakarta EE or framework version.
2. API namespaces used by source code, bytecode, and annotations.
3. Matching providers/implementations for Servlet, Persistence, Validation, and other services.
4. Servlet container, application server, or embedded runtime.
5. Direct dependencies, transitive dependencies, BOMs, and packaging scope.
6. XML config files, generated sources, reflection, service providers, and deployment config.
7. Integration tests for HTTP contracts, databases, validation, and transactions on the real runtime.

In **Java Advance Compatibility Migration**, this transition often happens alongside JDK and framework upgrades. Therefore, distinguish changes coming from the JDK from changes coming from the Jakarta ecosystem to address the exact root cause.

## 2. Distinguishing Java EE, Jakarta EE, and Java SE

### 2.1. Namespace Milestones

Java EE previously supplied numerous Enterprise APIs under `javax.*` packages, such as `javax.servlet`, `javax.persistence`, and `javax.validation`.

When transferred to the Eclipse Foundation, Jakarta EE initially preserved many `javax.*` packages in Jakarta EE 8. **Jakarta EE 9** marked the major namespace transition of most Enterprise APIs from `javax.*` to `jakarta.*`.

Accordingly:

- Java EE 8 typically uses `javax.servlet`, `javax.persistence`, and `javax.validation`.
- Jakarta EE 8 still largely retains the corresponding `javax.*` namespaces.
- Jakarta EE 9 and later move the relevant Jakarta Enterprise APIs to `jakarta.*`.
- Java SE APIs such as `javax.sql`, `javax.crypto`, `javax.xml.parsers`, or `javax.annotation.processing` do **not** automatically move to `jakarta.*`.

In other words, the package rename is a Jakarta EE milestone, not a rule applying to every package starting with `javax` in the JDK.

### 2.2. Sample Technology Matrix

| Component | Legacy `javax`-generation platform | Modern `jakarta`-generation platform |
|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Servlet annotations | `javax.servlet.annotation.*` | `jakarta.servlet.annotation.*` |
| Persistence / JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` |
| Jakarta EE Transactions | Corresponding `javax.transaction.*` | `jakarta.transaction.*` |
| CDI | `javax.enterprise.*` and `javax.inject.*` | `jakarta.enterprise.*` and `jakarta.inject.*` |
| REST / JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| WebSocket | `javax.websocket.*` | `jakarta.websocket.*` |
| JSON-B / JSON-P | `javax.json.bind.*` / `javax.json.*` | `jakarta.json.bind.*` / `jakarta.json.*` |
| Mail/Activation (stack-dependent) | `javax.mail.*` / `javax.activation.*` | `jakarta.mail.*` / `jakarta.activation.*` |

This table is a guide to recognition, not advice to add every dependency at once. Each application should include only the APIs it actually uses and let the platform/framework align versions wherever possible.

### 2.3. Related Jakarta EE Versions

A common illustrative matrix:

| Platform generation | Servlet | Persistence | Bean Validation | Namespace |
|---|---|---|---|---|
| Java EE 8 | Servlet 4.x | JPA 2.2 | Bean Validation 2.x | javax |
| Jakarta EE 9 | Jakarta Servlet 5.0 | Jakarta Persistence 3.0 | Jakarta Bean Validation 3.0 | jakarta |
| Jakarta EE 10 | Jakarta Servlet 6.0 | Jakarta Persistence 3.1 | Jakarta Bean Validation 3.0 | jakarta |

For subsequent releases, consult the compatibility matrix of your chosen platform, framework, and application server; never assume sharing the `jakarta` namespace makes all major/minor versions interchangeable.

**Key takeaway:** package namespace is only one dimension of compatibility. Frameworks, containers, ORM/Validation providers, and minimum Java baselines must also align.

## 3. Building a Compatibility Matrix Before Modifying Source Code

Before migrating, document current components and targets clearly:

| Layer | Current State | Target State | Question to Confirm |
|---|---|---|---|
| JDK runtime | Legacy Java | Target JDK | What minimum Java version does the framework/provider require? |
| Servlet API | javax.servlet | jakarta.servlet | Does the container execute the matching Jakarta Servlet version? |
| Web runtime | Old container | New container/embedded runtime | Do WARs and filters have the right namespace and lifecycle? |
| Persistence API | javax.persistence | jakarta.persistence | Do ORM provider and JPA metadata belong to the same generation? |
| ORM | Legacy Hibernate/EclipseLink | Provider supporting Jakarta Persistence | Do entity mapping, DDL, queries, and caching change? |
| Bean Validation API | javax.validation | jakarta.validation | Are the provider and integration actually invoked? |
| Transactions | Legacy JTA/framework transactions | Jakarta Transaction or current abstraction | Are commit/rollback boundaries preserved accurately? |
| Injection/CDI | javax.inject/enterprise | jakarta.inject/enterprise | Does the container instantiate/inject objects under new annotations? |
| REST/JSON | Legacy JAX-RS/JSON-B or framework | Jakarta-compatible stack | Do DTOs/serialization/HTTP statuses preserve contracts? |
| Build/runtime dependencies | Multiple transitive versions | Aligned BOM/stack | Are duplicate `javax`/`jakarta` APIs or providers present? |

Example of a controlled selection:

~~~text
Target JDK
      │
      ▼
Jakarta-compatible framework / application server
      │
      ├── Servlet API + container: same generation
      ├── Persistence API + ORM provider: same generation
      ├── Validation API + implementation: same generation
      ├── Transaction integration: matches runtime
      ├── CDI/injection and security: same namespace
      └── REST/JSON/WebSocket/Mail if used by the application
~~~

All APIs do not need the exact same major version number. For example, Servlet 6.0 and Persistence 3.1 belong together in one Jakarta EE platform release; what matters is **the supported set published by the platform**, rather than forcing every library to "6.0."

## 4. Aligning Jakarta Servlet and the Servlet Container

### 4.1. Changes in Java Source

For a legacy servlet:

~~~java
import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
~~~

After migrating the application to Jakarta Servlet:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

Example simple servlet:

~~~java
package com.example.web;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("OK");
    }
}
~~~

This compiles against a matching Jakarta Servlet API. However, it works as a servlet only when executed inside a container or embedded environment supporting that `jakarta.servlet` generation.

### 4.2. `javax`-Generation Containers Cannot Load Jakarta Servlets as Before

A common mistake is switching source imports to `jakarta.servlet` while still deploying the WAR to a container that only supplies `javax.servlet`.

Generation distinction examples:

- Older container lines like Tomcat 9 support the matching `javax`-generation Servlet API.
- Container lines supporting Jakarta EE 9+, such as Tomcat 10.x, use the `jakarta.servlet` package.
- Even across Jakarta lines, verify the specific Servlet API version implemented by the container.

Never look at a name like "Tomcat 10" and assume any Servlet API version is supported: container minor versions and releases determine the implemented Servlet specification.

### 4.3. Who Provides the Servlet API?

When deploying a WAR to an external servlet container, the container normally provides the Servlet API at runtime. The project needs the API to compile yet should not bundle another copy of the Servlet API inside `WEB-INF/lib` if the container supplies the matching version.

For executable/embedded web applications, the framework and embedded container must supply the full runtime implementation, and framework dependency management typically coordinates alignment across components.

| Deployment Model | Dependency Approach |
|---|---|
 WAR on external Jakarta container | Servlet API is usually `compileOnly`/`provided`; container supplies runtime. |
 Embedded server or executable JAR | Framework/starter or embedded runtime dependency provides Servlet implementation. |
 Full Jakarta EE application server | Server manages multiple APIs/implementations per platform; avoid bundling duplicates out of habit. |
 Library providing a Servlet Filter | Compile against the right Servlet API; document minimum container/runtime needed by consumers. |

If a WAR bundles a Servlet API conflicting with the container version, classloading conflicts or namespace/version mismatches can arise. Conversely, using `provided` scope where the real environment omits the API causes startup failures.

### 4.4. Filters, Listeners, and Spring Security

Important Servlet types go beyond `HttpServlet`:

- `Filter` and `FilterChain`.
- `ServletContextListener`, `HttpSessionListener`.
- `HttpServletRequestWrapper` and `HttpServletResponseWrapper`.
- Multipart upload, async servlets.
- `RequestDispatcher`, `ServletContext`, and error page settings.
- Framework security filter chains.

Example filter after migration:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class TraceFilter implements Filter {
    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

A Filter compiled against `javax.servlet.Filter` is **not** an implementation of `jakarta.servlet.Filter`. Therefore, beyond your own source code, upgrade filters provided by third-party libraries such as tracing, security, SSO, metrics, or upload frameworks.

### 4.5. Web Descriptors and Servlet Mapping

If the application uses `web.xml`, changing Java imports is insufficient. The XML descriptor may declare schemas/namespaces and structures from an older Servlet specification generation.

Illustrative descriptor for Jakarta Servlet 6.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

Schemas and versions must match your chosen container. For applications with security constraints, filters, servlet declarations, listeners, and session configs, review the entire descriptor rather than merely swapping `xmlns`.

## 5. Aligning Jakarta Persistence (JPA) and the ORM Provider

### 5.1. JPA Is the API; Hibernate/EclipseLink Is the Provider

Jakarta Persistence defines the API for entities, mapping, `EntityManager`, JPQL, lifecycle, and persistence context. An ORM provider such as Hibernate ORM or EclipseLink executes those operations.

Replacing:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.EntityManager;
~~~

with:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.EntityManager;
~~~

is only part of the change. The provider, runtime integration, generated metamodel, `persistence.xml`, transaction manager, and dependency graph must all recognize `jakarta.persistence`.

### 5.2. Jakarta Persistence Entity Example

~~~java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String displayName;

    protected Customer() {
        // Constructor for JPA.
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

This entity uses Jakarta Persistence annotations. An older provider searching only for `javax.persistence.Entity` will not recognize the entity or build the right mapping. Adding `jakarta.persistence-api` to the compile classpath does not turn an old provider into a Jakarta-compatible one.

### 5.3. Selecting a Compatible API and ORM Pair

| Component | What to Align |
|---|---|
| Entity annotations | `jakarta.persistence.*`. |
| Persistence API | Jakarta Persistence version matching your platform/framework. |
| ORM runtime | Provider supporting that exact API version. |
| Entity manager factory | Bootstrapped by framework/container or matching Persistence API. |
| Transaction manager | JTA/JDBC/framework transactions compatible with the provider. |
| Persistence metadata | `persistence.xml`, `orm.xml`, and mapping files matching the schema. |
| Annotation processor | Static metamodel generator or bytecode enhancer targeting matching annotations. |
| Database/JDBC driver | Driver running cleanly on the chosen JDK and ORM runtime. |
| Cache | Compatible second-level cache/provider, cache keys, and serialization. |

For example, upgrading from a `javax.persistence` Hibernate ORM line to a `jakarta.persistence` Hibernate ORM line may require updating the API, application code, persistence metadata, and framework integrations. Avoid manually forcing a Hibernate version far ahead of your framework BOM without verifying compatibility.

### 5.4. `persistence.xml` and XML Namespaces

For applications bootstrapping JPA via `persistence.xml`, the file typically resides at `META-INF/persistence.xml`. Across generations, check:

- Namespace and version of the persistence descriptor.
- Provider class name and properties.
- Persistence-unit transaction type.
- Data source and JDBC settings.
- Mapping files.
- Provider-specific property names that were deprecated or renamed.

Illustrative Jakarta Persistence 3.1 descriptor:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
             version="3.1">
    <persistence-unit name="appPU">
        <class>com.example.domain.Customer</class>
    </persistence-unit>
</persistence>
~~~

When a framework auto-configures the persistence unit, your project might not use this file. Do not create a `persistence.xml` solely because of a namespace migration; follow your real bootstrap setup.

### 5.5. JPQL, Schema Generation, and Database Behavior

Swapping JPA providers can change behavior beyond namespaces:

- JPQL/HQL-to-SQL translation and dialect rules.
- ID generation strategies, sequences, identity columns, and allocation sizes.
- Schema validation or DDL generation.
- Lazy loading and association fetch timing.
- Cascade, orphan removal, and dirty checking.
- Flush modes, transaction boundaries, and optimistic locking.
- JDBC batching, query plans, and pagination.
- Enum, JSON, temporal, UUID, and embeddable mappings.
- Caching, statistics, and generated SQL queries.

During migration, tests must verify data, constraints, transactions, and SQL behavior rather than checking only that `EntityManager` starts cleanly.

### 5.6. Keep `javax.persistence` Out of New Public/Domain APIs

For instance, a new repository using `jakarta.persistence.EntityManager` that still accepts `javax.persistence.criteria.Predicate` from an old library cannot treat the two type systems as interchangeable.

Prefer:

1. Upgrading repositories and companion libraries to the same JPA API generation.
2. If legacy consumers cannot upgrade yet, introducing an explicit adapter at controlled API boundaries.
3. Avoiding passing `EntityManager`, `Predicate`, or annotation metadata across bridges between generations.
4. Re-testing public APIs and binary compatibility for independent consumers.

Separating deployments/services or migrating the persistence module cleanly at a single boundary is usually far more maintainable than running two ORM provider generations over the same persistence context.

## 6. Aligning Jakarta Bean Validation

### 6.1. API, Provider, and Integration

Bean Validation uses annotations like `NotNull`, `NotBlank`, `Size`, `Min`, `Max`, `Email`, `Valid`, and the `Validator` mechanism to check object constraints.

Before migration:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
~~~

After migration:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

Distinguish three layers:

1. **Jakarta Validation API** holds annotations and interfaces.
2. **Validation provider** supplies the implementation, such as a matching Hibernate Validator release.
3. **Integration** triggers validation when desired: incoming HTTP requests, service method calls, persistence lifecycles, or CDI.

Having `@NotBlank` in bytecode does **not** make a POJO automatically validate at every usage site.

### 6.2. DTO Example Using `jakarta.validation`

~~~java
package com.example.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterCustomerRequest {
    @NotBlank
    @Size(max = 120)
    private String displayName;

    @NotBlank
    @Email
    private String email;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

In this example, validation runs only when the application calls `Validator` or the framework integrates Bean Validation for incoming requests. If you merely compile annotations and deserialize JSON, constraints may never execute.

### 6.3. Standalone Validation Example

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.Set;

public final class ValidationExample {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            RegisterCustomerRequest request = new RegisterCustomerRequest();
            request.setDisplayName("");
            request.setEmail("not-an-email");

            Set<ConstraintViolation<RegisterCustomerRequest>> violations =
                    validator.validate(request);

            System.out.println(violations.size());
        }
    }
}
~~~

Both the Jakarta Validation API and a matching provider must be on the runtime classpath. Message interpolation may also require an Expression Language implementation depending on provider/config. In framework- or container-managed environments, inject `Validator` or reuse container config instead of creating a new `ValidatorFactory` on every request.

### 6.4. Validation Areas Prone to Breakage

| Area | What to Verify |
|---|---|
| Request DTO | Does the framework invoke `@Valid`/`@Validated` and map errors per HTTP contract? |
| Nested objects | Does `@Valid` trigger cascading validation on nested fields? |
| Collections | Do element constraints on lists/maps work under the new provider/spec? |
| Method validation | Do interceptors/proxies apply to service methods? |
| JPA lifecycle | Is entity validation triggered per persistence policy and groups? |
| Custom constraints | Does the validator implement `jakarta.validation.ConstraintValidator`? |
| Groups | Are group sequences, default groups, and conversions intact? |
| Message interpolation | Are message bundles, locales, and EL providers present? |
| Violation mapping | Are property paths, error codes, HTTP responses, and messages stable? |

For example, an old custom constraint validator implementing `javax.validation.ConstraintValidator` does not turn into a Jakarta validator merely because DTO annotations changed.

### 6.5. Custom Constraint Migration

Legacy source:

~~~java
import javax.validation.Constraint;
import javax.validation.ConstraintValidator;
import javax.validation.ConstraintValidatorContext;
~~~

With Jakarta:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
~~~

Beyond imports, inspect:

- `@Constraint(validatedBy = ...)` references the updated class.
- `ConstraintValidator` generic type parameters match target data.
- Default messages, groups, payloads, and `@Retention`/`@Target` stay intact.
- The validation provider discovers the implementation.
- Message bundles and locales load via the right classloader.

### 6.6. Avoid Confusing the Two `ConstraintViolationException` Types

A common pitfall causing flawed exception handling:

- `jakarta.validation.ConstraintViolationException` represents Bean Validation failures.
- `org.hibernate.exception.ConstraintViolationException` is a Hibernate ORM exception typically representing database constraint violations.

Their simple names match while their semantics and packages differ. In migrated API exception handlers, use explicit imports or fully qualified types and pick appropriate HTTP statuses instead of collapsing both indiscriminately.

## 7. Aligning Servlet, Persistence, and Validation in a Single Flow

All three APIs often participate in a single request:

~~~text
HTTP client
    │
    ▼
Jakarta Servlet container / web framework
    │  Parse request + authentication
    ▼
Request DTO
    │
    ▼
Jakarta Bean Validation
    │  Validate input / reject invalid data
    ▼
Application service
    │  Authorization + business rules
    ▼
Transaction boundary
    │
    ▼
Jakarta Persistence + ORM provider
    │
    ▼
Database / JDBC driver
    │
    ▼
Response mapping / HTTP status
~~~

Alignment ensures requests traverse the complete flow:

1. Container accepts Servlet/JAX-RS classes in the new namespace.
2. Framework binds requests cleanly into DTOs.
3. Validation provider checks constraints and emits expected error responses.
4. Service enforces authorization prior to mutating data.
5. Transactions and `EntityManager` coordinate cleanly.
6. ORM executes SQL, commits/rolls back, and maps exceptions predictably.
7. Responses honor the wire contract or versioned changes.

Each layer compiling on its own does not prove cross-layer wiring works. For example, Validation API may be present while controllers never trigger validation; entities may carry `@NotNull` yet errors happen only when the database rejects `NOT NULL` columns.

### 7.1. The Two Constraint Layers Do Not Replace Each Other

Bean Validation checks objects against declared rules, whereas database constraints enforce integrity inside the database. A required email field may be validated on DTOs and entities while still keeping database constraints where appropriate.

During migration:

- Ensure invalid input is handled at boundaries per the API contract.
- Keep critical database constraints rather than removing them just because `@NotNull` exists.
- Test concurrency and transaction rollbacks when databases reject writes at flush/commit time.
- Distinguish validation errors from persistence/infrastructure errors in API responses.

## 8. Jakarta Transactions and Transaction Boundaries

Transactions bridge Persistence and the service layer. When moving stacks, verify who manages transactions:

- Jakarta Transaction API and application server transaction manager.
- Spring transaction abstraction and its transaction manager.
- Resource-local JPA transactions in standalone apps.
- Distributed/XA transactions if actually used.

For Jakarta:

~~~java
import jakarta.transaction.Transactional;
~~~

In Spring, another annotation exists:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

These two annotations are not the same Java class; your integration setup dictates how runtime handles them. Do not perform blind search-and-replace on transaction annotations without checking transaction managers, framework versions, and rollback semantics.

### 8.1. Behaviors to Test

- Transactions open and close at the intended service/use-case boundary.
- Validation failures trigger or avoid rollback according to policy.
- Whether database constraint violations occur at flush or commit time.
- Checked vs. runtime exceptions trigger rollback per published rules.
- Lazy-loaded associations are not accessed after persistence context closes unless planned.
- Async tasks and scheduled jobs establish proper transaction contexts.
- Nested calls/propagation, timeouts, locking, and isolation do not shift silently.

Swapping providers can leave basic CRUD passing while mid-batch failures commit partial state. That is a business regression requiring tests, not merely an API namespace issue.

### 8.2. `javax.transaction.xa` Remains a Special Case to Distinguish

Not every `javax.transaction` package changes. XA types such as `javax.transaction.xa.XAResource` remain part of Java SE/JDBC and must not be renamed automatically during a Jakarta Transactions migration.

This follows the same rule as `javax.sql`, `javax.crypto`, and other Java SE packages: verify module/API ownership before renaming.

## 9. Aligning CDI, Dependency Injection, and Lifecycle

Many Jakarta applications rely on CDI or a DI framework to wire servlet collaborators, persistence services, validators, and transaction interceptors.

Annotations to review:

~~~text
javax.inject.Inject          -> jakarta.inject.Inject
javax.inject.Named           -> jakarta.inject.Named
javax.enterprise.context.*   -> jakarta.enterprise.context.*
javax.annotation.PostConstruct -> jakarta.annotation.PostConstruct
~~~

This maps Jakarta EE-owned APIs only, not every `javax` package.

### 9.1. A Correct Import Does Not Prove Injection Works

Field example:

~~~java
import jakarta.inject.Inject;

public class CustomerController {
    @Inject
    CustomerService customerService;
}
~~~

If `CustomerController` is instantiated via `new` inside a plain Java SE app lacking an injection container or wiring mechanism, `customerService` will remain null despite the annotation.

During migration, check bean discovery, scanning, lifecycles, proxies, and integrations:

- `beans.xml` and discovery modes where applicable.
- Container-managed vs. manually instantiated objects.
- Package filters included/excluded by component scanning.
- Interceptors and decorators.
- Request/session/application scopes.
- Initialization/disposal and `@PostConstruct`/`@PreDestroy`.

If a framework changes component discovery rules between major versions, tests must boot the real application context and invoke entry points rather than checking compilation alone.

## 10. REST, JSON, WebSocket, and Companion Jakarta APIs

Servlet/JPA/Validation often interact with several companion Enterprise APIs:

| API | Jakarta Namespace | Migration Impact |
|---|---|---|
| Jakarta RESTful Web Services | `jakarta.ws.rs.*` | Resource annotations, filters, client/server providers, exception mappers. |
| Jakarta JSON Binding | `jakarta.json.bind.*` | DTO serialization/deserialization, adapters, field names, null handling. |
| Jakarta JSON Processing | `jakarta.json.*` | Streaming/DOM JSON APIs and providers. |
| Jakarta WebSocket | `jakarta.websocket.*` | Endpoints, sessions, handshakes, container implementations. |
| Jakarta Messaging | `jakarta.jms.*` | Connection factories, broker clients, transactions, providers. |
| Jakarta Mail | `jakarta.mail.*` | MIME, SMTP/IMAP clients, Activation, runtime providers. |
| Jakarta XML Binding | `jakarta.xml.bind.*` | JAXB annotations, runtime providers, generated classes. |
| Jakarta Security | `jakarta.security.enterprise.*` | Container authentication/identity store integration. |

Keep only required APIs in your dependency graph. When a framework already manages JSON, REST, or Servlet integration, avoid adding competing runtime providers that conflict during service discovery.

### 10.1. REST and Bean Validation

JSON endpoint example:

~~~java
import jakarta.validation.Valid;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.MediaType;

@Path("/customers")
public class CustomerResource {
    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    public void create(@Valid RegisterCustomerRequest request) {
        // Delegation to service.
    }
}
~~~

This works only when paired with a matching Jakarta REST runtime and Validation integration. Do not assume every JAX-RS implementation enables the exact same Bean Validation provider automatically without checking supported configs/APIs.

Beyond annotations, inspect HTTP status codes, JSON field names, error payloads, and filters; changing serializers/providers can alter wire contracts even when URLs stay unchanged.

### 10.2. WebSocket / JSON-B / XML

For WebSocket, verify handshakes, endpoint registration, and message converters against container versions. For JSON-B/XML, changing namespaces often swaps providers, altering how dates, enums, nulls, or XML schemas parse.

When using sources generated from WSDL, XSD, or OpenAPI, upgrade generators to compatible generations too. Generated files referencing `javax.*` usually need regenerating with updated tooling rather than manual edits to generated code alone.

## 11. Maven and Gradle: Centralized Version Management

### 11.1. What Role Do BOMs and Platforms Play?

During a Jakarta migration, picking individual API and provider versions separately invites skew. Use:

- Jakarta EE platform BOM when targeting the platform and its managed APIs.
- Framework BOMs/parents such as Spring Boot when using that framework.
- Official application server/runtime dependency management.
- Centrally governed dependency constraints or version catalogs.

**A BOM helps align versions**, yet cannot guarantee provider compatibility if you explicitly override components outside the supported matrix. Not every BOM includes ORMs, validation providers, servlet containers, and drivers at the same tier either.

### 11.2. Maven Example with `dependencyManagement`

Illustrative Jakarta EE 10 BOM example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>jakarta.platform</groupId>
            <artifactId>jakarta.jakartaee-bom</artifactId>
            <version>10.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>
~~~

This illustrates a Jakarta EE 10 baseline; verify exact BOM artifacts, versions, and scopes against your stack. Importing a BOM does not add every API or runtime provider to the application; dependencies still must be declared explicitly or provided by the runtime container.

On full Jakarta EE application servers, follow the server's recommended aggregate API coordinate instead of listing individual specs piecemeal. For embedded apps, bundle framework-managed runtime implementations instead.

### 11.3. Gradle Kotlin DSL Platform Example

~~~kotlin
plugins {
    java
}

dependencies {
    compileOnly(platform("jakarta.platform:jakarta.jakartaee-bom:10.0.0"))
    compileOnly("jakarta.servlet:jakarta.servlet-api")
    compileOnly("jakarta.persistence:jakarta.persistence-api")
    compileOnly("jakarta.validation:jakarta.validation-api")
}
~~~

This example fits modules compiling against APIs supplied by an **external Jakarta EE runtime**. Never copy this `compileOnly` configuration into standalone applications that must package APIs/providers without an external container. Pick scopes based on real packaging and deployment.

For Spring Boot apps, prefer Spring Boot's own dependency management and starters instead of assembling individual Servlet/JPA/Validation APIs and providers manually.

### 11.4. Inspecting the Resolved Dependency Graph

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence \
    --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

These commands answer:

- Which library still pulls in a legacy `javax.*` artifact?
- Is a Jakarta API present at compile time without a runtime provider?
- Are multiple versions of Servlet/Persistence/Validation APIs resolving together?
- Is the Servlet API bundled inside the WAR or supplied by the container?
- Do overrides break framework BOM compatibility?

Important caveat: **both `javax` and `jakarta` packages can legitimately coexist on a classpath because Java SE `javax` APIs remain completely valid**. Never delete every `javax`-prefixed dependency blindly.

## 12. Differences Between API JARs and Runtime Implementations

| Technology | API | Runtime / Implementation |
|---|---|---|
| Servlet | `jakarta.servlet-api` | Compatible Servlet container such as Tomcat/Jetty/Undertow. |
| Persistence | `jakarta.persistence-api` | Compatible ORM/JPA provider such as Hibernate ORM or EclipseLink. |
| Bean Validation | `jakarta.validation-api` | Hibernate Validator or another compatible provider. |
| CDI | `jakarta.enterprise.cdi-api`, injection APIs | Matching CDI container/integration. |
| Jakarta REST | `jakarta.ws.rs-api` | Compatible JAX-RS runtime/provider. |
| JSON-B | `jakarta.json.bind-api` | Matching JSON-B implementation. |
| JAXB | `jakarta.xml.bind-api` | Matching JAXB runtime implementation. |

Some application servers and framework starters distribute both APIs and providers; declaring them manually can introduce version conflicts. Conversely, adding only an API dependency makes code compile without providing runtime behavior.

### 12.1. Typical Runtime Failures

| Error | Possible Cause |
|---|---|
| `ClassNotFoundException: jakarta.servlet.Filter` | Servlet API/runtime missing or running on a `javax`-era container. |
| `NoClassDefFoundError: javax.persistence.Entity` | Dependency not migrated to Jakarta or missing legacy runtime class. |
| Bean Validation provider not found | `jakarta.validation-api` present without matching implementation. |
| Not a managed type / Unknown entity | ORM provider fails to recognize entity, or scanning/persistence unit mismatch. |
| `AbstractMethodError` / `NoSuchMethodError` | API, provider, or companion dependency version mismatch. |
| `InaccessibleObjectException` | Provider/framework uses reflection into un-opened JPMS packages. |
| `ServiceConfigurationError` | Service provider metadata points to wrong class or mixes generations. |

These messages guide triage; confirm stack traces, classloaders, runtime artifacts, and dependency graphs before drawing conclusions.

## 13. Binary-Level Namespace Mismatches

Java identifies types by their fully qualified binary name. `javax.servlet.Filter` and `jakarta.servlet.Filter` are two distinct interfaces; the same holds for `javax.persistence.EntityManager` and `jakarta.persistence.EntityManager`.

A class compiled against `javax.servlet.Filter`:

~~~text
LegacyFilter implements javax.servlet.Filter
~~~

cannot turn into:

~~~text
ModernFilter implements jakarta.servlet.Filter
~~~

merely by dropping `jakarta.servlet-api.jar` onto the runtime classpath. The JVM still sees two unrelated binary names.

Similarly, the annotation `javax.persistence.Entity` differs from `jakarta.persistence.Entity`, so an ORM provider scanning only Jakarta-generation annotations ignores legacy entities.

### 13.1. Impact on Public Library APIs

Suppose a library previously published:

~~~java
public void register(javax.servlet.Filter filter);
~~~

After migrating to:

~~~java
public void register(jakarta.servlet.Filter filter);
~~~

this changes the method descriptor and constitutes a **breaking binary API change**. Clients compiled against the old version cannot call the new method directly. Version clearly, offer an adapter/bridge if feasible, or maintain compatibility lines during transition periods.

### 13.2. Avoid Running Both Generations in One Uncontrolled Classloader

Large applications may temporarily include both `javax` and `jakarta` JARs to serve independent modules. Even so:

- Providers and framework scanners may understand only one generation.
- Annotations do not translate automatically.
- Java binary signatures remain distinct.
- Containers enforce a single servlet namespace contract per deployment.
- Two ORM providers sharing one database/entity model risk lifecycle and transaction conflicts.

If legacy and new stacks must coexist simultaneously, enforce clear boundaries: separate processes/services, protocol-level adapters, or controlled migration plans. Two packages coexisting on a classpath never guarantees the whole application functions.

## 14. Commonly Overlooked Generated Code and Metadata

Enterprise systems contain many artifacts beyond hand-written Java sources:

1. Code generated from OpenAPI, WSDL, or XSD.
2. JPA static metamodel classes.
3. Annotation processor outputs.
4. Third-party Servlet filters and initializers.
5. JAX-RS resource proxies and CDI decorators.
6. XML descriptors: `web.xml`, `persistence.xml`, `orm.xml`, `validation.xml`.
7. `META-INF/services` and extension discovery files.
8. Framework auto-configuration and reflection metadata.
9. Test fixtures or mocks implementing legacy APIs.

### 14.1. JPA Static Metamodels

If generated sources contain:

~~~java
import javax.persistence.metamodel.SingularAttribute;
~~~

then even after migrating entities to `jakarta.persistence`, the generated metamodel stays on `javax` and causes mismatches. Upgrade the processor to one supporting Jakarta Persistence and regenerate sources/bytecode from updated entities.

### 14.2. `validation.xml`

If the application uses `META-INF/validation.xml`, verify schemas, namespaces, and provider class names against the target Jakarta Validation version. Check XML constraint mapping files and message bundles as well.

Avoid creating a new `validation.xml` unnecessarily when framework defaults suffice; if an old file exists, verify which parser reads it.

### 14.3. Classpath Service Discovery

Some providers resolve via Java `ServiceLoader` or `META-INF/services`. Service descriptor filenames use binary interface names, so legacy `javax.*` descriptors cannot register corresponding `jakarta.*` providers.

When building fat JARs or shading, check `META-INF/services` merging rules. Dropping or overwriting service entries leaves validation/JPA/JSON runtimes unable to locate providers even when dependencies are bundled.

### 14.4. Reflection and JPMS

On the module path, Java enforces `exports`/`opens` boundaries. JPA and Validation providers often inspect fields and constructors reflectively:

- Inspect `module-info.java` when using JPMS.
- Identify packages needing `opens` to frameworks/providers.
- Avoid opening whole modules indiscriminately merely to silence errors.
- Test on the exact JDK, runtime provider, and classpath/module-path deployment mode.

Migrating to Jakarta does not force every application onto JPMS, yet apps already using the module path must validate module encapsulation boundaries.

## 15. Migrating Spring-Based Applications

A common scenario is upgrading legacy Spring Framework / Spring Boot applications to lines built around Jakarta APIs.

Involved components:

- Spring MVC / Servlet request pipeline.
- Spring Security filters and authentication.
- JPA/Hibernate integration and transaction managers.
- Framework-integrated Jakarta Bean Validation.
- Embedded servlet containers.
- JSON serialization.
- Exception handling and API error responses.
- Minimum JDK required by the framework release.

### 15.1. Why Use Starters/BOMs?

In Spring Boot applications, the target release's dependency management curates Spring, Hibernate, validation providers, and embedded containers tested to work together. Pinning a Hibernate ORM or Servlet API version far from the starter's alignment risks breaking binary/runtime compatibility.

Accordingly:

1. Select a framework release from its compatibility matrix and target JDK.
2. Follow framework starters and dependency management.
3. Update source imports and companion integration modules together.
4. Override dependencies only with verified justification, such as security patches.
5. Execute integration tests with the real framework application context and embedded container.

### 15.2. Never Mix Frameworks Using Different Servlet API Generations

A security filter JAR built against `javax.servlet.Filter` cannot act as a filter inside a Jakarta Servlet container. Upgrade to a library built for the Jakarta stack.

Similarly, an ORM plugin expecting `javax.persistence.EntityManager` cannot accept `jakarta.persistence.EntityManager`. Before upgrading frameworks, inventory third-party integrations tightly coupled to Servlet/JPA/Validation to avoid last-minute blockers.

## 16. Layered Testing After Alignment

### 16.1. Servlet HTTP Contract Tests

Verify:

- Context paths, servlet registration, and URL mappings.
- Filter/listener invocation order.
- Content types, character encodings, and multipart uploads.
- Sessions, cookie flags, CSRF, CORS, and security enforcement.
- Async requests and timeouts.
- Error pages, exception translation, and HTTP status codes.
- Behavior when deployed as a WAR or run embedded, matching real artifacts.

Do not rely solely on unit tests calling services directly. Filter registration errors often surface only through a live HTTP runtime.

### 16.2. Persistence Integration Tests

Verify:

- Entity scanning, `@Entity`/`@Id`, and field mappings.
- `EntityManagerFactory`/`EntityManager` startup.
- Insert/update/delete, flush/commit, and rollback.
- Lazy/eager fetching, cascades, and orphan removal.
- JPQL/criteria queries, pagination, sorting, and locking.
- Generated IDs and schema migrations.
- Database constraints, JDBC dialects, and timezones.
- Transaction boundaries and second-level cache if enabled.

Test dialect-sensitive behaviors against real matching databases/containers. An in-memory database from a different vendor cannot verify all production SQL semantics.

### 16.3. Bean Validation Tests

Verify:

- Invalid DTOs are caught.
- Valid DTOs pass validation.
- Nested `@Valid` cascades cleanly.
- Custom validators execute.
- Service-boundary method validation runs.
- Constraint groups and interpolated messages match expectations.
- HTTP mapping of constraint violations stays intact.
- JPA lifecycle validation if relied upon.

Tests must distinguish "annotation exists in source" from "runtime invokes the validator." Combine direct `Validator` tests with HTTP/service framework integration tests.

### 16.4. Cross-Layer Tests

An essential test scenario:

~~~text
POST /customers with invalid payload
    → Servlet/JAX-RS route matched
    → Bean Validation detects errors
    → No record created in database
    → Stable HTTP error contract

POST /customers with valid payload
    → Authentication/authorization succeeds
    → Service begins transaction
    → ORM persists entity
    → Commit succeeds
    → Response contains properly formatted ID
~~~

Write a separate test forcing a database or business-rule error to confirm rollback. If constraints fire at flush/commit rather than DTO validation, errors happen later in the transaction lifecycle.

## 17. Symptoms and Triage

| Symptom | Possible Cause | Investigation |
|---|---|---|
| `ClassNotFoundException` `jakarta.servlet.*` | Running on an old container or missing Servlet runtime API. | Inspect WAR/JAR, server version, and classloader. |
| `ServletException` starting filters | Third-party filter still uses `javax.servlet`. | Check implemented interfaces and dependency origin. |
| Not a managed type | Un-migrated entity annotations, broken scan, or JPA provider skew. | Check entity imports, provider, and entity scan packages. |
| `EntityManagerFactory` startup fails | Provider, persistence unit, schema, or JDBC config error. | Inspect root cause and resolved versions. |
| Validation provider missing | API present without implementation. | Inspect classpath/provider metadata and starters. |
| `@Valid` silently skipped | Validation integration disabled or execution bypasses framework. | Integration tests through controller/service runtime. |
| `NoSuchMethodError` / `AbstractMethodError` | Provider vs. API/framework version skew. | Trace loaded JARs; inspect BOM/overrides. |
| Transaction fails to roll back | Transaction manager, proxy, or annotation semantics changed. | Test failure paths, propagation, and rollback rules. |
| 404 or missing filters | Servlet mappings, context path, or security chain changed. | Test against real deployment and descriptors/annotations. |
| HTTP response schema shifts | New serializer/provider or exception mapper behavior. | Contract snapshots and behavioral tests. |
| `InaccessibleObjectException` | Reflection blocked by module encapsulation or old library. | Check JPMS, providers, and JDK settings. |

No single namespace-replacement script fixes every symptom. Always pinpoint the failing layer: compilation, dependency resolution, classloading, provider discovery, bootstrap, business logic, or deployment.

## 18. Source and Dependency Auditing Tools

### 18.1. Scanning Java Imports

In repositories with ripgrep:

~~~bash
rg -n "javax[.](servlet|persistence|validation|ws[.]rs|inject|enterprise|transaction|annotation)" src
rg -n "jakarta[.](servlet|persistence|validation|ws[.]rs|inject|enterprise|transaction|annotation)" src
~~~

This serves as an initial scan. Valid Java SE `javax` packages must remain intact if used, and generated sources or config files may live outside `src`.

### 18.2. Scanning XML and Service Metadata

Inspect:

~~~text
src/main/webapp/WEB-INF/web.xml
src/main/resources/META-INF/persistence.xml
src/main/resources/META-INF/validation.xml
src/main/resources/META-INF/orm.xml
META-INF/services/
Generated sources
Framework-specific descriptors
~~~

Paths vary across projects; not every file will necessarily exist.

### 18.3. Inspecting Artifacts and Runtime Dependencies

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.validation \
    --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree
~~~

Actual deployment classpaths may diverge from build dependency trees when external application servers supply libraries. When diagnosing `NoClassDefFoundError` or `LinkageError`, capture the exact JAR path and classloader serving the loaded class.

### 18.4. Automated Namespace Migration Tools

Tools exist to rewrite `javax` to `jakarta` in source code, bytecode, or deployment archives, such as OpenRewrite migration recipes or application-server Java EE/Jakarta deployment transformers.

They reduce mechanical work yet do not automatically:

- Choose matching ORM or Validation providers.
- Upgrade Servlet containers.
- Fix transaction semantics.
- Preserve binary compatibility for legacy public methods.
- Adjust database schemas, queries, or HTTP contracts.
- Prove integration behavior across real runtime topology.

Treat automated transformation output as **one step in the migration**, never proof of completion.

## 19. Controlled Migration Roadmap

### Phase A — Inventory and Lock Baseline

1. Record current JDK, framework, container, Servlet API, ORM provider, Validation provider, and runtime artifacts.
2. Save resolved compile and runtime dependency graphs.
3. Separate modules using `javax.*`, modules already on `jakarta.*`, and unchanged Java SE `javax` APIs.
4. Capture baseline HTTP/API contracts, JPA queries, and representative test datasets.
5. Catalog generated code, XML descriptors, third-party filters, and external integrations.

### Phase B — Choose Target Stack

1. Select compatible framework/Jakarta EE platform and container releases.
2. Pair compatible JPA/ORM, Validation providers, and transaction integrations.
3. Verify the minimum JDK across the whole stack.
4. Standardize around a BOM/parent or dependency management baseline.
5. Flag any modules/services blocked from simultaneous migration.

### Phase C — Migrate Source and Configuration

1. Update Enterprise imports within verified scope.
2. Upgrade frameworks and third-party adapters.
3. Update active `web.xml`, `persistence.xml`, `validation.xml`, and descriptors.
4. Upgrade code generators/annotation processors and regenerate sources.
5. Remove obsolete APIs/providers once unused.

### Phase D — Verify Runtime Wiring

1. Boot the application on the target JDK and container.
2. Verify Servlet routes, filters, and listeners.
3. Bootstrap ORM, load entities, and run database integration tests.
4. Exercise Bean Validation across requests and services.
5. Test transaction rollback, security, and serialization.
6. Run contract tests with API consumers.

### Phase E — Roll Out and Retire Shims

1. Verify on staging matching production server/container versions.
2. Roll out incrementally where architecture allows.
3. Monitor startup failures, HTTP 4xx/5xx rates, DB transactions, and validation anomalies.
4. Maintain rollback plans accounting for schema, data, and session serialization.
5. Remove transitional adapters/branches only once consumers and integrations finish migrating.

## 20. Common Mistakes

| Mistake | Consequence | Better Approach |
|---|---|---|
| Replacing every `javax` with `jakarta`. | Breaks Java SE packages like `javax.sql` and `javax.crypto`. | Rename only Enterprise APIs in migration scope. |
| Fixing only Servlet imports. | WAR fails on old containers; filters fail to load. | Upgrade containers and third-party servlet integrations. |
| Adding only `jakarta.persistence-api`. | Old ORM providers ignore entities or fail bootstrap. | Align JPA provider, framework, metadata, and transactions. |
| Adding only `jakarta.validation-api`. | Constraint annotations compile yet never run. | Supply provider and verify validation integration. |
| Mixing versions arbitrarily. | `LinkageError`, startup crashes, skewed transaction behavior. | Use BOMs/compatibility matrices and verify with tests. |
| Bundling Servlet API unguarded into external-container WARs. | Duplicate classes/providers and classloading clashes. | Use `provided`/`compileOnly` when server supplies the API. |
| Leaving `javax` generated code in a Jakarta project. | Compile/runtime skew and broken provider discovery. | Upgrade generators, regenerate, and inspect outputs. |
| Ignoring XML descriptors. | Scanners/metadata keep old namespaces. | Check `web.xml`, `persistence.xml`, `validation.xml`, `orm.xml`. |
| Treating same-named `@Transactional` annotations as identical. | Wrong rollback semantics or inactive interceptors. | Confirm transaction manager and annotation integration. |
| Testing only successful CRUD. | Misses rollback bugs, constraints, lazy loading, and tenant security. | Test success and failure paths across layers. |
| Testing only via mocked controllers. | Hides Filter/Servlet container/provider bugs. | Run integration tests through a real runtime. |
| Assuming having both `javax` and `jakarta` JARs guarantees compatibility. | Binary type and annotation names stay distinct. | Enforce clean boundaries and avoid uncontrolled mixing. |

## 21. Migration Verification Checklist

Checklist for Servlet/JPA/Validation modules:

- [ ] Target JDK and minimum framework Java requirement confirmed.
- [ ] Jakarta EE platform, framework, and container versions cross-checked.
- [ ] Servlet API and Servlet runtime share the same namespace and specification.
- [ ] Every filter, listener, and initializer has a Jakarta-compatible version.
- [ ] JPA annotations, Persistence API, and ORM provider belong to the same generation.
- [ ] Database driver, transaction manager, and persistence metadata verified.
- [ ] Bean Validation API, provider, message interpolation, and integration active.
- [ ] Custom validators, method validation, `@Valid`, and constraint groups tested.
- [ ] CDI/injection, transaction, REST, JSON, and WebSocket APIs aligned if used.
- [ ] Generated code and XML descriptors contain no stale-generation references.
- [ ] Java SE `javax` packages were not removed erroneously.
- [ ] Dependency graph and packaging/runtime scopes verified.
- [ ] HTTP API contract tests cover failures, validation errors, and security.
- [ ] JPA transactions, rollbacks, DB constraints, and lazy loading tested.
- [ ] Real container/runtime tests executed alongside rollout monitoring.

This checklist guides real migrations; items require evidence from builds, tests, and deployments rather than being marked done merely from reading.

## 22. Integrated Scenario Example: Customer Management App

Suppose a legacy application runs:

~~~text
Legacy Java
  └─ javax Servlet
      └─ javax.validation DTO
          └─ Service
              └─ javax.persistence JPA + legacy ORM
                  └─ Database
~~~

Target state after migration:

~~~text
JDK supported by target stack
  └─ Jakarta Servlet container / MVC framework
      └─ jakarta.validation DTO + provider
          └─ Service + transaction integration
              └─ jakarta.persistence + compatible ORM provider
                  └─ Database
~~~

Test plan:

**Valid case:** submit a customer creation request with valid `displayName` and `email`; controller route matches; validator passes; service opens a transaction; JPA persists; database commits; response returns formatted ID matching contract.

**Invalid DTO case:** missing `displayName` or invalid `email`; Bean Validation runs, response carries structured validation errors, and no record enters the database.

**Database rejection case:** trigger a unique constraint violation in tests; exception is classified accurately, transaction rolls back cleanly, and no half-written data persists.

**Unauthorized case:** a tenant-A user attempts to modify a tenant-B customer; server denies access before data mutation without leaking out-of-scope records.

**Generation-skew runtime case:** attempt deploying a Jakarta artifact onto a `javax`-only container in a test environment; confirm pipeline or smoke checks catch the mismatch before reaching production.

These scenarios show that Servlet, Persistence, and Validation are truly aligned only when **end-to-end cross-layer request flows** behave consistently across both success and failure cases.

## 23. Conclusion

Aligning Servlet, JPA, Validation, and related Jakarta APIs means coordinating **namespaces, specification versions, implementations/providers, frameworks/containers, dependency graphs, metadata, and runtime behavior**. Renaming `javax.servlet` to `jakarta.servlet`, `javax.persistence` to `jakarta.persistence`, or `javax.validation` to `jakarta.validation` is necessary on corresponding stacks, yet insufficient while providers, code generators, XML descriptors, or application servers stay on older generations.

A safe path starts from an inventory, picks a coherent platform/BOM, verifies who supplies the Servlet runtime, JPA provider, Bean Validation provider, and transaction manager, updates source/config/generated code together, and validates HTTP, data, and authorization contracts on the target JDK and container.

**The goal is not purging every string `"javax"` from the repository, but ensuring each Enterprise Java API uses the right generation, executes with a matching provider, and upholds business guarantees throughout the move to Jakarta.**
