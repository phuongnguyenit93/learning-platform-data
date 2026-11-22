# Spring Boot 2 to 3: Java baseline and Jakarta ecosystem changes

Migrating an application from **Spring Boot 2.x to Spring Boot 3.x** is a major platform upgrade, not simply bumping a plugin or dependency version. Spring Boot 3 requires **Java 17 or newer**, builds on **Spring Framework 6**, replaces Java EE `javax.*` APIs with **Jakarta EE** APIs, and upgrades core components including Spring Security, Spring Data, Hibernate ORM, embedded Servlet containers, and observability tooling.

Because these changes touch compilation, reflection, annotations, serialization, filter chains, persistence, and deployment directly, an application can break immediately at compile time or fail only along specific execution paths. For instance, sources using `javax.servlet.Filter` no longer match Spring Framework 6's Servlet contract; entities carrying `javax.persistence.Entity` may go unrecognized under Jakarta Persistence; older security libraries may be incompatible with Spring Security 6; or custom auto-configurations may stop loading as before.

In **Java Advance Compatibility Migration**, the effective approach is isolating root causes: **JDK baseline**, **Jakarta namespace**, **framework/dependency version shifts**, **configuration and default behavior changes**, and finally **testing on a real runtime environment**. This lesson lays out a step-by-step migration plan with Gradle, Maven, Java, security config, JPA, Servlet, observability examples, and a verification matrix.

## 1. Understanding the upgrade scope: Boot 3 is not merely Boot 2 running on newer Java

A Spring Boot 2.x application may run on a newer JDK in suitable configurations, yet that does not mean the codebase is ready for Spring Boot 3. The upgrade spans multiple axes:

| Axis | Typical Boot 2.x foundation | Moving to Boot 3.x |
|---|---|---|
| Java baseline | Depends on Boot 2 branch; many projects start from Java 8/11 | **Java 17 minimum** |
| Spring Framework | Spring Framework 5.x | Spring Framework 6.x |
| Jakarta / Java EE | Most web, JPA, and validation integrations use `javax.*` | Moves to matching `jakarta.*` APIs |
| Servlet container | E.g., Tomcat 9 with `javax.servlet.*` | Jakarta Servlet containers, e.g., Tomcat 10.1 in Boot 3.0 |
| Persistence | Hibernate ORM 5.x in common Boot 2 lines | Hibernate ORM 6.x in Boot 3 |
| Spring Data | 2.x line in Boot 2 | 3.x line in Boot 3 |
| Security | Spring Security 5.x | Spring Security 6.x |
| Observability | Some systems use Sleuth or custom metrics | Micrometer Observation/Tracing is the primary integration path |
| Runtime/configuration | Boot 2 properties, auto-config, and defaults | Keys, registration mechanisms, and defaults changed |

This table is architectural guidance for the **2.x → 3.x** path, not a substitute for the **exact patch/minor compatibility matrix** chosen by your project. Boot 3.x minor releases also continue evolving between versions.

Key takeaway: **upgrading to JDK 17 is a necessary prerequisite for Boot 3, not sufficient proof that migration will succeed.**

## 2. Java 17 is a minimum baseline, not an optional choice

Spring Boot 3.0 requires Java 17 or newer. If the application currently runs on Java 8 or Java 11, you must upgrade the baseline before or alongside upgrading the framework.

Check all execution groups:

1. **Build JVM:** JDK running Gradle/Maven and plugins.
2. **Compiler JDK:** JDK compiling sources, annotation processors, and generated sources.
3. **Source/bytecode target:** language level, class-file target, and Java SE APIs for the application.
4. **Test JVM:** JVM running unit/integration tests.
5. **Production runtime:** real JDK inside VMs, images, containers, or application servers.
6. **Auxiliary tooling:** JaCoCo, Mockito/Byte Buddy, APM agents, code generators, and static analyzers.

A pipeline can compile with Java 17 yet deploy the artifact into a container still running Java 11, triggering `UnsupportedClassVersionError`. Conversely, the runtime JDK may be Java 17 while an old annotation processor relying on `com.sun.tools.javac.*` breaks the build.

### 2.1. Gradle toolchain example

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_3_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`REPLACE_WITH_VERIFIED_BOOT_3_VERSION` is a **placeholder**, not a literal version to run verbatim. Choose a compatible Boot 3.x and Gradle plugin version from docs for your target branch while also verifying the Gradle wrapper runs cleanly on the chosen JDK.

`options.release = 17` specifies the compiler's source language, bytecode target, and Java SE API target where supported. It does not force third-party libraries to match class-file target 17.

### 2.2. Maven example

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

In a Spring Boot Maven project using the appropriate parent/BOM, `java.version` typically establishes the Java baseline. For customized builds, inspect the Maven Compiler Plugin and effective `maven.compiler.release`. The XML snippet above is a fragment, not a complete POM.

### 2.3. Checking the same JDK across environments

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

Commands are meaningful only when executed in the exact environments and toolchains used by builds/deployments. Never infer that `java -version` on a laptop matches the JDK in production containers.

## 3. Why consider stepping through Spring Boot 2.7 first?

For applications on an older Boot 2.x release, an easier-to-control path is often:

~~~text
Old Spring Boot 2.x
       |
       | Upgrade dependencies, clean up warnings, ensure tests
       v
Appropriate Spring Boot 2.7.x
       |
       | Move to Java 17, prepare APIs/configs and tests
       v
Target Spring Boot 3.x
       |
       | Handle Jakarta + Security/Data/Observability
       v
Stable deployment
~~~

Boot 2.7 is a helpful stepping stone because it sits immediately prior to Boot 3. However, it is **not mandatory** for every system to cut a separate production release on 2.7 before moving to 3; this is a risk-reduction strategy to separate variables.

At the stepping stone:

- Upgrade plugins/test tools to versions supporting Java 17.
- Inspect the dependency graph and library support for Boot 3.
- Replace deprecated APIs where clear migration paths exist.
- Verify integration tests, database migrations, and security behavior.
- Capture baselines for startup, request mapping, error responses, metrics, latency, and resource usage.
- Avoid upgrading many unrelated libraries in the same commit where possible.

**Do not treat passing Boot 2.7 builds as proof that the application already uses Jakarta.** Most namespace shifts and major framework updates still happen when moving to Boot 3.

## 4. Jakarta EE: changing namespaces changes API contracts

Legacy Java EE technologies used `javax.*` packages. The Jakarta EE 9 ecosystem moved many APIs to `jakarta.*`. Spring Framework 6 and Boot 3 integrate with the modern Jakarta ecosystem.

Example:

~~~java
// Before: Servlet/JPA/Validation app using Java EE namespace
import javax.servlet.Filter;
import javax.persistence.Entity;
import javax.validation.Valid;
import javax.annotation.PostConstruct;
~~~

Converting the corresponding APIs:

~~~java
// After: corresponding Jakarta APIs in Boot 3
import jakarta.servlet.Filter;
import jakarta.persistence.Entity;
import jakarta.validation.Valid;
import jakarta.annotation.PostConstruct;
~~~

This is not merely “text replacement” in source code. **Type identity depends on the full package name.** `javax.servlet.Filter` and `jakarta.servlet.Filter` are two distinct types despite sharing the short name `Filter`. A library compiled for javax Servlet will not be recognized by a Jakarta Servlet container; a Jakarta Persistence framework will not treat an entity marked with `javax.persistence.Entity` as an entity.

### 4.1. Common API group mapping table

| Before (Boot 2 / Java EE API) | After (Boot 3 / Jakarta API) | Accompanying tasks |
|---|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` | Servlets, Filters, Listeners, Request/Response wrappers |
| `javax.persistence.*` | `jakarta.persistence.*` | Entities, repositories, converters, JPA customizations |
| `javax.validation.*` | `jakarta.validation.*` | Bean Validation annotations and validators |
| `javax.annotation.*` (e.g., `PostConstruct`) | `jakarta.annotation.*` | Lifecycle annotations, dependencies |
| `javax.transaction.*` (Jakarta Transactions API) | `jakarta.transaction.*` | Transaction annotations/APIs if using Jakarta Transactions |
| `javax.mail.*` | `jakarta.mail.*` | Mail APIs/providers and integrations |
| `javax.activation.*` | `jakarta.activation.*` | Activation API dependencies |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` | JAX-RS libraries if used by the app |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` | JAXB APIs/implementations if migrating to the Jakarta line |

The table does not mean every Boot 3 application uses all of these APIs, nor that changing packages alone suffices without upgrading implementations.

### 4.2. Do not replace all javax.* with jakarta.*

Many Java SE APIs retain the `javax.*` namespace and **must not be changed**:

- `javax.net.ssl.*` for TLS.
- `javax.crypto.*` for cryptography.
- `javax.sql.*` for DataSource and JDBC APIs.
- `javax.naming.*` for JNDI.
- `javax.xml.parsers.*`, `javax.xml.transform.*` for Java SE XML APIs.
- `javax.management.*` for JMX.
- `javax.annotation.processing.*` for annotation processing.

Conversely, `javax.persistence.*` and `javax.servlet.*` in Jakarta integrations must be updated. Every import should be classified by **API owner and actual library**, rather than blindly running a repository-wide rename regex.

### 4.3. Some javax types carry distinct meanings

An important example: `javax.transaction.xa.*` belongs to Java SE X/Open XA interfaces, so not every `javax.transaction.*` type shares the same migration strategy. Inspect concrete packages and modules rather than looking only at prefixes.

## 5. Avoid mixing javax and jakarta in the same integration layer

A frequent migration error is keeping both API generations at the same extension point:

~~~text
Spring Framework 6 / Boot 3
         |
         +--> Jakarta Servlet Filter
         |
         +--> Legacy library expects javax.servlet.Filter
                                      ^
                                      |
                                  incompatible
~~~

If a legacy library returns `javax.servlet.Filter`, calling code cannot turn it into `jakarta.servlet.Filter` by casting. The two types reside in different packages with no inheritance relationship.

Symptoms:

- `incompatible types` at compile time.
- `ClassNotFoundException: javax.servlet.Filter` or `NoClassDefFoundError` at runtime.
- Beans fail to register or callbacks fail to fire because annotations belong to different namespaces.
- Frameworks fail to recognize entities/validators/listeners.
- The servlet container fails to load/wire filter chains.
- The dependency graph contains both `javax.servlet-api` and `jakarta.servlet-api`.

Having both JARs on the classpath may not fail the build immediately, yet you **cannot use a `javax` type as an implementation of the corresponding `jakarta` contract**.

### 5.1. Do not add javax API libraries just to clear compile errors

If a library demands `javax.servlet-api` in a Boot 3 project, adding the legacy artifact may silence import errors without solving Jakarta container integration. Upgrade or replace the **extension library itself**, rather than adding the old API JAR.

## 6. Servlet containers and web applications

Boot 3 uses Jakarta-compatible Servlet APIs. For example, in Boot 3.0, embedded Tomcat moves to Tomcat 10.1, where the Servlet API uses the `jakarta.servlet` namespace.

Impacted components include:

- `Filter` and `FilterChain`.
- `ServletRequest`, `HttpServletRequest`, `HttpServletResponse`.
- `ServletContextListener`, `HttpSessionListener`.
- Custom servlet registrations.
- Servlet API wrappers.
- Third-party servlet filters, SSO adapters, monitoring integrations.
- WAR deployment onto external application servers.

### 6.1. Custom Filter before and after example

Before:

~~~java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.ServletException;
import java.io.IOException;

public final class LegacyRequestFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

After:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.ServletException;
import java.io.IOException;

public final class RequestFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
~~~

This illustrates the contract change. If the Filter is registered via a Spring bean or `FilterRegistrationBean`, verify generic types and imports across all related classes.

### 6.2. A WAR cannot be deployed arbitrarily onto legacy javax containers

A WAR built on Spring Framework 6/Jakarta Servlet cannot deploy to a Servlet container supporting only `javax.servlet`, such as the Tomcat 9 line. When deploying to an external container, verify the **Jakarta Servlet API level and container support matrix** matching your chosen Boot minor/patch release.

### 6.3. WebFlux is not Servlet

Applications running Spring WebFlux on Netty do not necessarily follow the same Filter/Servlet pipeline as Spring MVC; nevertheless, they run on Spring Framework 6 and can experience Jakarta changes in Validation or integrations. Never force `jakarta.servlet-api` onto every Boot 3 app if its architecture does not use the Servlet stack.

## 7. Spring MVC: verify request mappings and behavioral shifts

Even after controllers compile following import updates, web behavior can differ between Spring Framework 5 and 6.

One notable change is **trailing slash matching**: route configurations/mappings may no longer automatically treat `/orders` and `/orders/` as identical by default.

Example:

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderController {

    @GetMapping
    public List<String> all() {
        return List.of("A", "B");
    }
}
~~~

Test both:

~~~text
GET /orders
GET /orders/
~~~

Do not assume both paths return the same status/body when upgrading the framework. If API contracts require supporting both, configure explicit mappings or redirects intentionally and test with real HTTP clients.

Other behaviors to inspect:

- Path matching and path variables.
- Request parameter parsing.
- Content negotiation and media types.
- Message converters and serialization.
- Exception handling via `@ControllerAdvice`.
- Error response shapes and HTTP status codes.
- Multipart uploads.
- Validation and default error messages.
- CORS and Spring Security filter behavior.

### 7.1. Spring MVC tests protect API contracts

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void listsOrders() throws Exception {
        mvc.perform(get("/orders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0]").value("A"));
    }
}
~~~

The snippet assumes corresponding static imports for JUnit, MockMvc request builders, and matchers. The goal is testing the **HTTP contract**, not just controller compilation.

## 8. Jakarta Persistence and Hibernate ORM 6

Spring Boot 3 upgrades persistence to Jakarta Persistence; common Boot 3 releases ship Hibernate ORM 6. This is one of the areas most prone to changes deeper than package names.

Before:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;
}
~~~

After:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    protected OrderEntity() {
    }

    public OrderEntity(Long id) {
        this.id = id;
    }

    public Long getId() {
        return id;
    }
}
~~~

This example shows only a minimal entity; ID generation strategies, constraints, and association mappings depend on your real schema.

### 8.1. Components to audit

- `@Entity`, `@Table`, `@Id`, `@GeneratedValue`.
- `@OneToMany`, `@ManyToOne`, `@JoinColumn`, and fetching behavior.
- `AttributeConverter`, custom types, and custom user types.
- Custom `Dialect`s and Hibernate interceptors/listeners.
- JPQL/HQL and native queries.
- Criteria API.
- Pagination, sorting, and query parameter binding.
- Identifier generation and database sequence naming.
- Schema validation and DDL generation.
- Second-level caches and transaction boundaries.

Never assume changing `javax.persistence.Entity` to `jakarta.persistence.Entity` preserves every query semantic of Hibernate 5. Hibernate ORM 6 changes query models, type systems, SQL generation, and numerous extension APIs internally.

### 8.2. Queries and custom Hibernate APIs

A repository extending `JpaRepository` may still compile cleanly while complex HQL/JPQL or custom dialects require updates. Run integration tests against the **exact target database engine/version and representative data**, not only embedded H2 if production uses another engine.

### 8.3. Schema shift risks

An ORM major upgrade can change default sequences, identifier handling, or SQL type mappings. Never enable auto DDL update in production assuming migrations stay safe.

Deployment guidance:

1. Use Flyway/Liquibase or controlled schema migration workflows.
2. Back up critical schemas and data beforehand.
3. Compare generated/expected DDL against actual schemas.
4. Run `validate` in appropriate environments where possible.
5. Verify inserts/updates/deletes, optimistic locking, transactions, and query plans.
6. Prepare data rollback plans if the ORM or migration alters schemas.

## 9. Spring Data 3 and repository integration

Spring Data 3 aligns with Spring Framework 6/Jakarta alongside API evolutions within Spring Data itself.

A standard interface:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {
}
~~~

Renaming `JpaRepository` itself may not be needed, yet entity imports and Hibernate integration must align. If projects include custom repositories, converters, event listeners, auditing, projections, or specialized query generation, audit those separately.

Potential issues:

- Derived queries referencing renamed properties.
- `@Query` using incompatible HQL/JPQL syntax.
- Return types and pagination semantics affecting clients.
- Auditing annotations/bean configurations changed.
- Custom Hibernate session code failing to compile.
- Multi-datasource configs needing synchronized properties and transaction managers.
- Legacy migrations or DDL assumptions breaking.

Never treat clean application startup as proof that every repository query works; some queries are only parsed or executed upon invocation.

## 10. Bean Validation: jakarta.validation replaces javax.validation

Bean Validation annotations belong to the Jakarta namespace in Boot 3.

Before:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Size;
~~~

After:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

DTO example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @Size(min = 1, max = 40) String note) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class OrderWriteController {

    @PostMapping("/orders")
    public String create(@Valid @RequestBody CreateOrderRequest request) {
        return request.customerId();
    }
}
~~~

Ensure the project includes a matching **validation implementation**, typically via the Spring Boot validation starter when using Bean Validation. Compiling `jakarta.validation.*` imports does not prove the runtime validator is active.

### 10.1. Watch out for custom validators

Custom `ConstraintValidator` implementations and custom annotations must use the same Jakarta Validation contract:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
~~~

A custom validator still implementing `javax.validation.ConstraintValidator` will not align with the implementation used by Boot 3.

### 10.2. Verifying validation errors

When upgrading frameworks, protect contracts around HTTP 400 responses, field errors, message keys, locales, and formats expected by frontends/clients. Namespace updates must never silently disable validation along a request path.

## 11. Lifecycle annotations and other Jakarta APIs

Example:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

If an app has `javax.annotation.PostConstruct` via a legacy dependency, do not leave old imports intact simply because the build compiles. Spring Framework 6 uses the matching Jakarta contracts for relevant lifecycle integrations.

Review additional libraries:

- Jakarta Mail and mail-sending APIs.
- Jakarta Activation if handling MIME attachments.
- JAXB/Jakarta XML Binding if serializing XML.
- Jakarta Transactions if using `jakarta.transaction.*` types.
- Jakarta WebSocket if using WebSocket APIs.
- JAX-RS if the project uses Jersey/RESTEasy or another provider.

**Not every Boot 3 service needs to upgrade every Java EE library to Jakarta in one pass.** Only APIs actually used within an active integration require migration, yet all participants inside the same integration must pick a compatible API generation.

## 12. Spring Security 6: configuring the filter chain

A major shift in the Boot 2 → 3 transition is Spring Security 6. Legacy configuration patterns were deprecated and removed in newer versions—most notably extending `WebSecurityConfigurerAdapter`.

### 12.1. Legacy configuration example

~~~java
@Configuration
@EnableWebSecurity
public class LegacySecurityConfiguration
        extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
                .and()
                .httpBasic();
    }
}
~~~

This illustrates legacy code needing migration, not a template to use with Spring Security 6.

### 12.2. Configuring with `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Here `SecurityFilterChain` is the bean used by Spring Security to construct the filter chain. This short snippet illustrates API structure without covering authentication providers, password encoding, CORS, session policy, or CSRF config for a specific system.

### 12.3. authorizeRequests, antMatchers, and requestMatchers

Audit old APIs like `authorizeRequests()`, `antMatchers()`, and `mvcMatchers()` across security configurations; map them to Security 6's `authorizeHttpRequests()` and `requestMatchers()` using the appropriate matcher types.

Do not swap matchers mechanically when pattern semantics differ. Write tests covering permitted URLs, denied URLs, HTTP methods, and endpoints with trailing slashes.

### 12.4. CSRF and session management

Never blindly add `csrf.disable()` just to make integration tests pass after migration. For apps using cookies/sessions, CSRF protection can be an essential control. If a stateless API uses bearer tokens by design, CSRF decisions must align with your threat model and actual authentication configuration.

### 12.5. Method security

Some projects move from `@EnableGlobalMethodSecurity` to `@EnableMethodSecurity` and review `@PreAuthorize`/`@PostAuthorize` annotations. Verify method-level security rules, SpEL expressions, and service-layer behavior after upgrading.

## 13. OAuth2, JWT, and application security

If an application acts as an OAuth2 client, resource server, or authorization server, inventory:

- Spring Security OAuth2 modules and versions.
- Resource server JWT decoders and JWK retrieval.
- Issuer/audience validation.
- Authorities/roles mapping.
- Sessions, login redirects, and logout.
- CORS and CSRF.
- Authorization at HTTP request and method levels.
- Third-party authentication adapters or SSO libraries.

An adapter coupled to `javax.servlet.*` cannot be treated as Jakarta Servlet-compatible merely because it worked on Boot 2. Obtain a release supporting Boot 3/Spring Security 6, or replace the integration per provider documentation.

### 13.1. Do not weaken security to claim “migration passed”

Some startup failures disappear if you drop filters, permit all URLs, or skip token validation. That is not a successful migration. Write tests proving:

- Public endpoints stay public.
- Protected endpoints still enforce authentication.
- Scope/role/claim rules retain exact semantics.
- Tokens with invalid issuers/signatures/audiences are rejected.
- Session/login/logout flows work if used by the app.
- Unauthorized and forbidden responses obey API contracts.

## 14. Dependency graphs and BOMs: never mix incompatible versions

Spring Boot typically manages dependencies via the **Spring Boot BOM** or parent/build plugins. Moving from Boot 2 to 3 updates dozens of versions in tandem.

Common mistakes:

- Leaving a Spring Framework 5 JAR in one module while core uses Spring Framework 6.
- Leaving a Hibernate 5 extension while Boot 3 manages Hibernate 6.
- Adding `javax.servlet-api` merely to compile a legacy library.
- Pulling an old Spring Security 5 JAR into a Security 6 application.
- Letting an internal BOM override versions back to Boot 2 pins.
- Mixing `spring-boot-starter-*` dependencies across major versions.
- Carrying legacy implementations inside shaded JARs.
- Running Java agents/bytecode libraries incompatible with Java 17.

### 14.1. Gradle: checking dependency selection

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency hibernate-core \
  --configuration runtimeClasspath
~~~

These reference commands must adapt subproject/configuration names to your repository. Never manually override Spring Framework or Hibernate versions without checking the compatibility matrix for your target Boot minor release.

### 14.2. Maven: viewing effective dependency versions

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

If using Spring Boot parent, verify the exact parent version. If importing the Spring Boot BOM via `dependencyManagement`, inspect other BOMs for conflicts and check final resolved versions.

### 14.3. Separating direct and transitive dependencies

A starter may bring in the new implementation version while a legacy library transitively pulls in the old implementation. Inspect the resolved graph and final artifact rather than assuming “Boot 3 starter in the POM is enough”.

## 15. Gradle Boot 3 and Jakarta dependencies example

A minimal build script example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_3_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_COMPATIBLE_PLUGIN_VERSION'
}

group = 'com.example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This configuration is an **illustrative example**, not directly runnable until version placeholders are replaced. Choose plugin management versions matching your Gradle wrapper and Boot release. Depending on the project, another BOM/platform mechanism may substitute for `io.spring.dependency-management`; you do not have to copy one single dependency-management style blindly across every repository.

Note: adding the Spring Security starter may require more explicit authentication/authorization configuration. Simply adding the starter does not guarantee Boot 2 policies remain identical.

## 16. Maven Boot 3 parent example

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_VERIFIED_BOOT_3_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

The version placeholder must be replaced with an actual Boot 3.x release chosen per product support policy. This is a minimal Maven example excluding application-specific dependencies.

## 17. Auto-configuration: registration changes

Spring Boot extension libraries often ship auto-configurations. In many libraries written for Boot 2, auto-configuration classes were listed in `META-INF/spring.factories` under `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.

In Boot 3, auto-configuration registration uses the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example file contents:

~~~text
com.example.orders.autoconfig.OrderClientAutoConfiguration
com.example.orders.autoconfig.OrderMetricsAutoConfiguration
~~~

These are hypothetical class names illustrating the resource format.

### 17.1. Why does a Boot 2 library fail to auto-configure on Boot 3?

If an internal starter registers auto-configurations **only** via the legacy mechanism and has not migrated properly, expected beans may never be created. Symptoms include `NoSuchBeanDefinitionException`, inactive configuration, or malfunctioning features.

When migrating internal libraries:

1. Identify all auto-configuration classes.
2. Adopt the registration mechanism supported by Boot 3.
3. Verify conditions such as `@ConditionalOnClass` and `@ConditionalOnProperty`.
4. Check imports for leftover `javax.*` references or replaced types.
5. Run `ApplicationContext` tests for the starter on Boot 3.

### 17.2. Do not delete all spring.factories entries indiscriminately

`spring.factories` served multiple extension mechanisms beyond auto-configuration. Moving **auto-configuration registration** does not mean every other entry in that file should be deleted. Inspect what framework extension each key serves and how the target Spring Boot release supports it.

## 18. application.properties and application.yml configuration

Boot 3 changes several configuration property keys and defaults. When upgrading, compare against configuration metadata for your **target Boot version**.

Areas to audit:

- HTTP server, sessions, and compression.
- DataSources, pools, JPA/Hibernate.
- Redis and Spring Data integrations.
- Actuator endpoint exposure.
- Logging, tracing, metrics, and management endpoints.
- Security OAuth2 client/resource-server properties.
- Config imports, environment variables, profiles.
- Third-party starter namespaces.
- Kubernetes/readiness/liveness properties.

Never assume every legacy property still binds after bumping versions. A renamed key may be silently ignored or trigger a warning depending on system setup.

### 18.1. Spring Boot Properties Migrator

During upgrades, Spring Boot offers `spring-boot-properties-migrator` to help detect/migrate changed configuration properties. It can be added **temporarily** as a dependency while auditing the application per guidance for your target Boot release, then removed once configs are updated.

Do not treat the properties migrator as a permanent solution or a substitute for reading migration guides. It cannot fix every custom property, Java namespace shift, or external integration behavior.

### 18.2. Obsolete configuration may silently stop applying

If a key is no longer recognized, the application can start up using new defaults, producing failures subtler than compile errors. Test real effects: connection pool sizes, timeouts, metric exposure, session cookies, server ports, and security policies.

## 19. Logging, Actuator, and observability

In Boot 3, observability centers heavily on **Micrometer Observation** and modern tracing/metrics integration. Systems previously using Spring Cloud Sleuth must evaluate migrating to Micrometer Tracing or a compatible solution.

### 19.1. Changing libraries alone is not enough to preserve tracing

When replacing the observability stack, check:

- Trace IDs and span IDs are created and propagated.
- HTTP/messaging/database instrumentation works.
- Context propagation format across services matches.
- MDC logging and log correlation work.
- Sampling policies apply properly.
- OTLP/Zipkin/exporter configs match if used.
- Metric tags/names keep dashboards compatible.
- Actuator endpoints and access controls are configured.

A service can build and serve HTTP 200 responses while breaking distributed traces or renaming metrics, blinding production monitoring.

### 19.2. Avoid unintentionally exposing Actuator endpoints

Upgrading Boot can alter defaults and management property keys. Verify which endpoints are enabled and exposed over HTTP/JMX, and enforce proper authentication/authorization. Never open `/actuator/**` publicly just to restore monitoring checks post-migration.

### 19.3. Dashboards must be migrated with verification

If metric names or tags changed, update dashboards and alerts deliberately. Never assume having `/actuator/health` respond proves monitoring, tracing, and SLOs remain intact.

## 20. Testing stack: JUnit, Mockito, and bytecode tooling

Boot 3 pairs with newer testing libraries. Older dependencies may not support Java 17, Spring Framework 6, or newer bytecode patterns.

Inspect:

- Spring TestContext framework.
- `@SpringBootTest` and test slices (`@WebMvcTest`, `@DataJpaTest`).
- JUnit Platform/Jupiter and test runners.
- Mockito, Byte Buddy, and agent-based mocking.
- Testcontainers/database driver versions.
- JaCoCo, SpotBugs, and static analyzers.
- JSON/XML test assertions.
- MockMvc request mappings and security tests.
- ApplicationContext loading and custom bean configurations.

### 20.1. Test classes must use Jakarta imports

Tests building fake servlet requests/filters with `javax.servlet.*` will no longer exercise the Jakarta Servlet contract. Upgrade test helpers, mocks, and fake implementations alongside the framework.

### 20.2. Testing Bean Validation enforcement

Do not check only that DTOs compile. Send constraint-violating requests and assert HTTP responses, field errors, locales/messages, and that database state stays untouched.

### 20.3. Testing with realistic data

H2 or embedded databases can handle SQL and type mapping differently from Postgres/MySQL/Oracle used in production. Hibernate 6 upgrades demand integration tests against a matching database engine—especially for custom HQL, identifiers, and schema assumptions.

## 21. Spring Native/AOT and executable packaging

Spring Boot 3 supports modern AOT and native-image workflows. However, **not every Boot 3 application must move to GraalVM native images**. Standard JVM deployment remains completely valid.

If adopting AOT/native images, investigate further:

- Reflection metadata and runtime hints.
- Resource/proxy/serialization hints.
- Dynamic class loading.
- Native-compatible libraries.
- Build-time vs. runtime class initialization.
- Binary testing and observability.
- Target image architecture and toolchains.

Never bundle moving from Boot 2 to 3 together with switching from a JVM JAR to a native image unless required by a specific product goal. Doing both simultaneously obscures root causes.

## 22. Third-party dependencies commonly needing version upgrades

Libraries in the Spring Boot ecosystem generally require releases supporting Spring Framework 6 and Jakarta EE:

- API documentation / OpenAPI integrations.
- Servlet filters, authentication adapters, and SSO clients.
- ORM extensions, database mapping, and auditing libraries.
- Custom Bean Validation providers.
- Messaging connectors.
- Spring Cloud components.
- Scheduler, batch, caching, and distributed lock libraries.
- Third-party Spring integration starters.
- APM/tracing agents.
- Code generation, annotation processing, and testing tools.

A library claiming support for “Java 17” **does not necessarily support Boot 3**. It may run on JVM 17 while still compiled against Spring 5/`javax.servlet.*`. Verify **both Java version and Spring/Jakarta compatibility** for the exact artifact.

### 22.1. Spring Cloud compatibility

If using Spring Cloud, do not retain a release train built for Boot 2 expecting it to work with Boot 3. Select a Spring Cloud/Spring Boot combination officially supported for your target minor branch, then inspect Gateway, Config, Discovery, Circuit Breaker, LoadBalancer, and concrete starters.

### 22.2. Springdoc/OpenAPI and Swagger integrations

Legacy Swagger/OpenAPI integrations can directly depend on Spring MVC internals or `javax.servlet.*`, crashing startup. Select a Boot 3-compatible release and test documentation endpoints, generated schemas, security metadata, and API grouping—not just compiling the new dependency.

### 22.3. Spring Batch, schedulers, and persistent state

Sibling ecosystem frameworks can alter metadata structures, APIs, and database schemas. If using Spring Batch or job schedulers, assess separate migrations for repository metadata, schedules, retries, and in-flight job states. Never assume updating the BOM preserves state models across all subsystems.

## 23. Classifying compile and runtime errors after upgrading Boot

| Error/symptom | Possible cause | Priority action |
|---|---|---|
| `package javax.servlet does not exist` | Code/library still on legacy Servlet namespace | Switch to Jakarta imports, upgrade compatible libraries |
| `incompatible types: javax.servlet.Filter ... jakarta.servlet.Filter` | Two type systems mixed | Replace library/contract, do not cast |
| `ClassNotFoundException: javax.persistence.Entity` | Legacy dependency or reflection config | Move to Jakarta Persistence and compatible provider |
| Entities unrecognized | Annotations still `javax.persistence.Entity` or scan config broken | Check imports, entity scanning, and ORM integration |
| `NoSuchMethodError` on Spring/Hibernate classes | Version conflict or ABI mismatch | Inspect BOM and runtime dependency graph |
| `NoSuchBeanDefinitionException` after starter upgrade | Auto-config failed to load or conditions changed | Inspect `AutoConfiguration.imports` and conditions |
| Security config fails to compile | Security 5 APIs removed/changed | Migrate to `SecurityFilterChain` and request matchers |
| 404 on URLs with trailing slashes | Request-matching behavior changed | Test route contracts; declare mappings/redirects explicitly |
| Validation fails to trigger | Legacy annotations used or missing implementation | Jakarta Validation and starter/config |
| SQL/HQL queries fail | Hibernate ORM 6 semantics/APIs changed | Integration tests against real DB; update queries |
| Metrics/traces missing | Observability stack or exporters changed | Update Micrometer/Tracing configs and pipelines |
| `UnsupportedClassVersionError` | Runtime JVM older than class files | Align on Java 17+ runtime |
| Java agent fails to instrument | Outdated agent/ASM/Byte Buddy version | Upgrade bytecode tooling |
| Tests pass yet behavior differs | Defaults and properties changed | Contract/integration tests and config audit |

Never blame “Jakarta” for every post-Boot-upgrade failure when stack traces point to dependency conflicts, HQL shifts, or ignored config properties. Inspect root exceptions, resolved version graphs, and real integration points.

## 24. Inventory workflow by namespace across sources

Audit sources and configs with searches:

~~~bash
rg -n "javax\.servlet|javax\.persistence|javax\.validation|javax\.annotation|javax\.transaction|javax\.mail" \
  src
~~~

Use tooling suited to your OS; `rg` is ripgrep. Its output is a **list requiring classification**, not a list to replace blindly.

Groups to examine separately:

1. Direct imports in hand-written sources.
2. Generated sources/templates.
3. Annotation processors generating `javax.*` code.
4. Third-party libraries or shaded JARs.
5. Reflection class names in `Class.forName` or configs.
6. Test fixtures and mock implementations.
7. Documentation with old examples excluded from compilation.
8. Application server or deployment packaging configs.

### 24.1. Never use repository-wide text replacement as your sole tool

Replacing every `javax.` with `jakarta.` can break valid Java SE APIs and cause subtle compilation failures. Perform migrations using API-aware IDE refactorings, OpenRewrite recipes, or an audited API mapping list; then inspect imports and dependency graphs.

## 25. OpenRewrite and migration automation

Source transformation tools like OpenRewrite can automate many import, API, and config updates via recipes. They shine in large repositories where transformations are clearly encoded by tool authors.

Still, automated rewrites do not cover:

- SQL/schema compatibility.
- Security policy semantics.
- Runtime plugins lacking Jakarta support.
- Client API/HTTP contracts.
- Observability and metric dashboards.
- Custom reflection/bytecode transformations.
- Deployment and container compatibility.
- Data formats and rollback.

A safe workflow runs recipes on a separate branch, reviews diffs, compiles, inspects dependency graphs, and runs integration tests. Never treat “recipe completed” as proof the framework migration succeeded.

## 26. Controlled migration strategy

A practical roadmap:

### Phase A — Capture Boot 2 baseline

Record exact Boot 2 version, JDK, framework dependencies, build plugins, runtime image, integration contracts, database schema, security policies, and observability baselines. Verify existing tests actually execute and preserve logs/artifacts.

### Phase B — Move to an appropriate Boot 2.7 release

Upgrade dependencies and clean up deprecated APIs achievable on Boot 2. Do not defer all tooling upgrades until swapping the parent/plugin to Boot 3.

### Phase C — Upgrade Java baseline to 17

Align build/test/runtime toolchains and images. Address annotation processors, Java agents, and bytecode analyzers. Run tests on Java 17 before changing major framework generations when project strategy allows.

### Phase D — Migrate Jakarta and third-party libraries

Update imports accurately, upgrade Servlet/ORM/validation/mail/integration libraries for Jakarta compatibility, and remove unnecessary javax dependencies. Update generated code and shared internal libraries.

### Phase E — Upgrade Spring Boot 3 and framework stack

Pick a Boot 3 target patch/minor aligned with support policy; update parents/plugins/BOMs, Security 6 configs, Hibernate 6 integrations, auto-config registrations, and properties.

### Phase F — Verify behavior

Execute unit/integration/contract tests—especially HTTP mappings, validation, security, JPA queries/DDL, messaging, and observability. Assess runtime performance.

### Phase G — Staged rollout

Use staging/canary/rolling deployments as appropriate; monitor 4xx/5xx rates, authentication errors, database exceptions, metrics, traces, and resource usage. Keep rollback plans covering both artifacts and data.

### Phase H — Clean up temporary dependencies

Remove the properties migrator, compatibility adapters, obsolete imports/APIs, and unneeded runtime flags; update runbooks, BOMs, SBOMs, and ownership.

Systems do not all have to run these phases as separate releases in one rigid sequence, yet each phase needs **completion criteria and evidence** to isolate root causes when issues appear.

## 27. Module-by-module migration in a monorepo

A monorepo might look like:

~~~text
platform/
├── common-model/
├── persistence/
├── web-api/
├── security/
├── external-client/
├── admin-service/
└── integration-tests/
~~~

Never let `common-model` or `persistence` publish public interfaces referencing `javax.persistence.*` if Boot 3 services expect matching Jakarta types. This may require reshaping dependency boundaries.

### 27.1. One shared library for both Boot 2 and Boot 3?

If a library's public API exposes `javax.servlet.Filter` or `javax.persistence.Entity`, reusing one unchanged artifact across both generations is generally unviable at those extension points. Options include:

- Splitting Servlet/JPA-independent core logic from adapters.
- Publishing separate javax and jakarta adapter artifacts.
- Defining pure-Java DTOs/interfaces for business contracts.
- Migrating services in compatible cohorts.
- Setting a compatibility window and deprecation plan for the old variant.

Avoid forcing one library to mix both javax and jakarta APIs in public signatures without explicit architecture; doing so increases coupling and classpath conflict risks.

### 27.2. REST contracts can remain stable despite Java API shifts

A server migrating `javax.servlet` to `jakarta.servlet` can preserve its HTTP JSON contract for external clients if URLs, JSON schemas, headers, status codes, and auth semantics stay unchanged. This is why protecting **client-facing contracts** with tests matters more than trying to preserve internal source imports.

## 28. Designing regression tests by risk area

| Area | Scenarios to verify | Why it matters |
|---|---|---|
| Startup | `ApplicationContext` load, auto-config, custom beans | Catches starter/condition incompatibilities |
| Java baseline | JDK 17+ build/test/runtime | Prevents class-file mismatches |
| Routing | URIs, slashes, path variables, HTTP methods | Detects Spring MVC behavioral shifts |
| JSON | Serialization/deserialization, enums, dates | Preserves API contracts |
| Validation | Constraint-violating requests and error bodies | Detects missing Jakarta Validation |
| Security | Public/private endpoints, auth, CSRF, CORS | Prevents security regressions |
| JPA | CRUD, queries, relations, converters | Hibernate 6 behavioral shifts |
| Database | Schemas, sequences, migrations, locking | Prevents data loss/regressions |
| Messaging | Producers/consumers, serialization, retries | Integration compatibility |
| Observability | Metrics, trace propagation, health | Prevents monitoring blind spots |
| Deployment | WAR/JAR/container, ports, readiness | Jakarta runtime compatibility |
| Performance | Startup, p95/p99, heap, pools | Catches post-upgrade regressions |
| Rollback | Old/new data/API compatibility | Keeps rollback viable on incident |

A test suite asserting only HTTP 200 on `/actuator/health` does not prove business flows, database queries, and security controls are intact.

### 28.1. Security negative tests

Beyond testing allowed requests, test requests **that must be rejected**. For instance, a resource server must reject tokens with wrong issuers or insufficient scopes. Testing only happy paths after migration can miss overly permissive configurations.

### 28.2. JPA tests with migration schemas

Run tests on databases matching production where possible, with Flyway/Liquibase scripts and representative datasets. Verify zero unintended DDL mutations, sequence mismatches, or misbehaving queries.

### 28.3. Comparing observability

Save metric/trace baselines prior to migration. Afterward, verify metric names, labels, trace correlation, log fields, and alerts—not just that actuator endpoints exist.

## 29. Common mistakes

### 29.1. “Just change the Spring Boot version”

Wrong, because Boot 3 simultaneously alters the Java baseline, Spring Framework, Jakarta APIs, and numerous ecosystem dependencies. You need a risk-scoped plan.

### 29.2. “Replace all javax with jakarta”

Breaks `javax.net.ssl`, `javax.sql`, `javax.crypto`, and other Java SE APIs. Classify carefully by package/API owner.

### 29.3. “Add javax.servlet-api to keep legacy libraries working”

That is not a valid bridge between Java EE Servlet and Jakarta Servlet. Use a Jakarta-compatible library release or an explicit contract adapter.

### 29.4. “Application started, so ORM is healthy”

Queries, converters, sequence generators, or writes can fail only at execution time. Test against representative data and database engines.

### 29.5. “Delete Security config to get tests passing”

If `WebSecurityConfigurerAdapter` fails to compile, migrate to Security 6's configuration model and verify policies—never strip protections or permit all URLs.

### 29.6. “Upgrade a single dependency ignoring the BOM”

Bumping Spring Framework/Hibernate/Security piecemeal risks runtime linkage errors. Favor compatible versions aligned with your chosen Boot release.

### 29.7. “Properties migrator will fix everything”

It assists with configuration keys only, not Java APIs, data schemas, security policies, or behavioral changes. Use it temporarily and remove it afterward.

### 29.8. “No need to test external containers”

A Jakarta WAR cannot be assumed to run on containers supporting only `javax.servlet`. Verify Servlet API levels and server versions.

### 29.9. “Existing Sleuth/metrics will keep working unchanged”

Observability requires dedicated migration and verification. A service running business logic without distributed traces still impairs production operations.

### 29.10. “Rollback just means re-running the old image”

If Hibernate migrations or the new service changed database schemas/data, reverting to the Boot 2 image may be unsafe. Build realistic data-compatibility and rollback plans.

## 30. Checklist before shipping Boot 3 to production

- [ ] Selected exact Boot 3 minor/patch release and read relevant migration/release notes.
- [ ] Set Java 17+ baseline across compiler, tests, and production JVMs.
- [ ] Confirmed build tool wrappers, plugins, and Java agents support the target JDK.
- [ ] Verified dependency graph does not accidentally mix Spring Framework 5/6 versions.
- [ ] Migrated required Servlet, JPA, Validation, and lifecycle APIs to Jakarta.
- [ ] Preserved Java SE `javax.*` APIs untouched without blind replacement.
- [ ] Confirmed third-party starters and shared internal libraries support Boot 3/Jakarta.
- [ ] Tested `SecurityFilterChain` and HTTP/method authorization rules.
- [ ] Verified HTTP endpoints, path/trailing-slash mappings, and error contracts.
- [ ] Verified DTO Bean Validation and custom `ConstraintValidator` implementations use Jakarta properly.
- [ ] Verified entities/repositories, Hibernate 6, queries, converters, and DDL.
- [ ] Prepared backups, validation, and rollback strategies for database migrations.
- [ ] Registered internal starter auto-configurations via Boot 3's mechanism.
- [ ] Audited configuration property keys/defaults and removed the properties migrator once done.
- [ ] Verified observability, tracing, Actuator security, and alerts.
- [ ] Confirmed coverage tooling, test runners, and static analyzers work on the new JDK.
- [ ] Passed integration tests against representative databases, brokers, and external services.
- [ ] Verified JAR/WAR/container artifacts match JDK and Jakarta container compatibility.
- [ ] Compared performance/resources and tested restarts/failure recovery.
- [ ] Prepared rollout, monitoring, data compatibility, and rollback runbooks.

This checklist is lesson guidance, **not confirmation that any specific project has executed or passed these steps**.

## 31. Migration report template

A structured template for recording technical status:

~~~yaml
springBootMigration:
  application: "orders-service"
  from:
    springBoot: "2.7.x"
    java: "11"
    servletApi: "javax.servlet"
  target:
    springBoot: "3.x"
    java: "17"
    servletApi: "jakarta.servlet"
  dependencies:
    springFramework6Reviewed: false
    springSecurity6Reviewed: false
    hibernate6Reviewed: false
    thirdPartyStartersReviewed: false
  source:
    jakartaImportsMigrated: false
    javaSeJavaxImportsPreserved: false
    generatedCodeReviewed: false
  config:
    autoConfigurationReviewed: false
    propertiesReviewed: false
    securityPolicyVerified: false
  tests:
    startupPassed: false
    webContractPassed: false
    validationPassed: false
    persistencePassed: false
    observabilityPassed: false
    productionLikeRuntimePassed: false
  deployment:
    canaryPlanned: false
    rollbackPlanned: false
  owner: "application-team"
  status: "in-progress"
~~~

Service names and values are illustrative only. In real reports, replace `3.x` with the exact release, along with build/commit IDs, artifact checksums, test results, evidence links, and approver.

## 32. Core principles

- **Spring Boot 3 requires Java 17 or newer** and builds on Spring Framework 6, so Boot 2 → 3 is a platform baseline upgrade, not just bumping a parent/plugin version.
- **Jakarta moves many enterprise APIs from javax to jakarta**, notably Servlet, JPA, and Validation. Never apply bulk renames to Java SE APIs like `javax.net.ssl` or `javax.sql`.
- **`javax.servlet.Filter` and `jakarta.servlet.Filter` are two distinct types.** Adding a legacy API JAR does not make an old library Jakarta-compatible.
- **Servlet containers, ORM, Security, Spring Data, and third-party starters must all align** with your target Boot 3 release.
- **Hibernate ORM 6 demands inspecting queries, custom types, and identifier/schema behavior**, not merely updating entity imports.
- **Spring Security 6 centers on `SecurityFilterChain`**, while requiring verification of HTTP and method authorization, CSRF, token validation, and negative tests.
- **Auto-configuration and configuration properties changed**, requiring audits of internal starters, resource registrations, and defaults.
- **Observability requires dedicated migration** when using Sleuth/tracing or relying on historical metrics/alerts.
- **Build and runtime JDKs can differ**, so verify compilers, test runners, Java agents, packaged artifacts, and production images.
- **Upgrades require integration/contract/security/data tests**, never concluding readiness from compile success or `ApplicationContext` startup alone.
- **Stage Boot 2.7, Java 17, Jakarta/framework upgrades, and production rollouts** where helpful to reduce the number of changing variables per step.
- **Rollback must account for schemas/data and API contracts**, not merely re-running the old container image.

When migrating from Spring Boot 2 to 3, the sustainable goal is bringing the entire system onto **a consistent Java 17+ and Jakarta foundation**, updating libraries interacting with Spring Framework 6, upholding security/data contracts, and proving behavior on the target runtime. That ensures Java Advance Compatibility Migration finishes not only cleanly at compile time, but safely across deployment, operations, and future upgrades.
