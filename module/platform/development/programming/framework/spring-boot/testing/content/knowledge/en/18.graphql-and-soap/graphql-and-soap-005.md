# HttpGraphQlTester and Verifying Transport and Authentication in Spring Boot

A GraphQL resolver might return the right data when invoked directly while the network-facing **POST /graphql** endpoint is still broken: the HTTP path is unmapped, Content-Type is rejected, the Authorization header is stripped, Spring Security returns 401/403 before reaching GraphQL, or an authenticated account is allowed to read fields beyond its privileges. Therefore, when the topic is **HttpGraphQlTester and verifying transport and authentication**, you cannot merely assert the value returned by a **@QueryMapping** method.

**HttpGraphQlTester** from Spring for GraphQL uses **WebTestClient** to send GraphQL requests over **HTTP transport**. Crucially, the exact same HttpGraphQlTester API can run with WebTestClient **bindToServer** (a real HTTP server) or a client attached to a mock web stack (no real socket). To prove routing, HTTP authentication, and responses on a running port, the test must explicitly configure **bindToServer** alongside **@SpringBootTest(webEnvironment = RANDOM_PORT)**; when asserting HTTP 401, 403, 415, or headers, keep a raw WebTestClient to test the transport layer.

The hands-on lab uses **Java 17, Spring Boot 3.4.5, Boot-managed Spring for GraphQL, Spring Security, JUnit Jupiter, and Gradle**. All usernames and passwords are local sample data; do not use this password storage pattern in production.

## 1. Three verification layers of a GraphQL HTTP request

A GraphQL request over HTTP typically looks like this:

~~~http
POST /graphql HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Authorization: Basic <base64-of-test-credentials>

{
  "query": "query Greet($name: String!) { greeting(name: $name) }",
  "operationName": "Greet",
  "variables": { "name": "Lan" }
}
~~~

The Authorization line in the example illustrates the format, not usable credentials. On the server side, processing proceeds through these layers:

~~~text
HTTP client / HttpGraphQlTester
         |
         v
TCP + HTTP: path, method, headers, Content-Type, JSON body
         |
         v
Servlet filters / Spring Security
  - Authenticates identity from Authorization
  - Permits/blocks request into /graphql
  - Can return HTTP 401/403 before GraphQL engine
         |
         v
Spring GraphQL HTTP handler
  - Reads query, variables, operationName
  - Validates GraphQL document and executes resolvers
  - Can return HTTP 200 with "data" and "errors"
         |
         v
DataFetcher / @QueryMapping / service
  - Business result
  - Field-level method authorization (if configured)
         |
         v
GraphQL response over HTTP
~~~

There are three distinct kinds of evidence:

| Layer | Question | Appropriate tool |
| --- | --- | --- |
| GraphQL execution | Do query/variables/schema/resolvers return the right data and GraphQL errors? | **GraphQlTester** or HttpGraphQlTester |
| HTTP transport | Are URL, method, Content-Type, HTTP status, response headers, and security filters right? | Direct **WebTestClient**; HttpGraphQlTester for successful HTTP requests |
| Authentication/authorization | Are anonymous users, wrong credentials, wrong roles, and restricted fields blocked at the right boundary? | WebTestClient for **HTTP 401/403**, HttpGraphQlTester or WebTestClient for **GraphQL errors** |

**Do not confuse HTTP 200 with business success.** GraphQL can return HTTP 200 with an **errors** array when a data fetcher fails. Conversely, HTTP 401 or 403 returned by Spring Security before reaching GraphQL typically does not carry a full GraphQL response structure.

## 2. How HttpGraphQlTester differs from GraphQlTester and WebTestClient

**GraphQlTester** is the common API for writing documents, setting variables, executing, and asserting GraphQL data/errors. **HttpGraphQlTester** is the variant that uses WebTestClient to execute GraphQL requests over HTTP. **WebTestClient** is a general HTTP client used to assert status codes, headers, cookies, and raw bodies.

| Tool | HTTP transport? | Real socket? | Strength | Does not replace |
| --- | --- | --- | --- | --- |
| ExecutionGraphQlServiceTester | No, calls server-side GraphQL service | No | Tests schema/resolvers/data fetchers | HTTP security filters, networking |
| WebGraphQlTester | Passes through WebGraphQlHandler without a network client | No | Tests WebGraphQlInterceptor/headers and execution | Sockets/real transport |
| HttpGraphQlTester with MockMvcWebTestClient | HTTP semantics via mock MVC | **No** | Web handlers/filters in mock context | Real TCP port/container |
| **HttpGraphQlTester with WebTestClient.bindToServer** | **Yes, HTTP** | **Yes**, when a real server is running | GraphQL documents/variables/data over real HTTP | Convenient assertion of arbitrary raw HTTP statuses like 401/403 |
| **Direct WebTestClient.bindToServer** | **Yes, HTTP** | **Yes** | HTTP 401/403, content negotiation, raw JSON errors, headers | GraphQL-specific assertion DSL |

Some examples use **@GraphQlTest**. That is a **GraphQL test slice**, normally configuring GraphQlTester or an execution tester to test GraphQL without starting a server. It fits schema/resolver logic, **and does not prove** that the live endpoint at /graphql passes through Spring Security HTTP filters.

### Two valid ways to configure HttpGraphQlTester

**Pass an already-built WebTestClient to the tester:**

~~~java
WebTestClient transport = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port + "/graphql")
        .build();

HttpGraphQlTester tester = HttpGraphQlTester.create(transport);
~~~

**Or pass a WebTestClient.Builder into the tester's builder:**

~~~java
HttpGraphQlTester tester = HttpGraphQlTester.builder(
        WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port + "/graphql"))
        .headers(headers ->
                headers.setBasicAuth("reader", "reader-pass"))
        .build();
~~~

Both snippets are **excerpts**, requiring proper imports for WebTestClient and HttpGraphQlTester plus the port from @LocalServerPort. **create(WebTestClient)** and **builder(WebTestClient.Builder)** are HttpGraphQlTester 1.3.x APIs compatible with the Spring Boot 3.4.x line in this example.

**Do not hardcode port 8080** in RANDOM_PORT tests: read the actual port from @LocalServerPort and build the URL from it. Do not confuse base URLs http://host:port and http://host:port/graphql; for the dedicated GraphQL tester, the base URL must point directly to the GraphQL endpoint.

## 3. Crucial transport rule: HTTP errors vs. GraphQL errors

The same word **"error"** covers two categories:

**A. HTTP-layer rejection**, usually before the GraphQL engine runs:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="..."
~~~

Or:

~~~http
HTTP/1.1 403 Forbidden
~~~

HTTP 401 typically means missing valid identity or wrong credentials; HTTP 403 typically means the identity is authenticated but unauthorized for this HTTP resource. The response body may be generated by Spring Security, Boot's ErrorController, a custom entry point, or a reverse proxy. **Do not assume a 401/403 response is always GraphQL JSON** containing an errors array.

**B. GraphQL execution error after the HTTP request is accepted:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": { "secret": null },
  "errors": [
    {
      "message": "generic execution error",
      "path": ["secret"]
    }
  ]
}
~~~

This is a **structural illustration**, not a guarantee that the server or framework uses the exact same message or Content-Type. When a data fetcher fails while GraphQL execution completes per protocol, HTTP 200 with errors can be an entirely valid response. Under GraphQL-over-HTTP, HTTP status also depends on the error phase and content negotiation; do not apply a blanket rule that "every GraphQL error is HTTP 200" to malformed requests, pre-execution validation errors, or other media types.

**Assertion selection rule:** to prove the security filter rejected a request to /graphql, use WebTestClient.expectStatus().isUnauthorized() or isForbidden(). To prove a resolver/field was denied inside an HTTP-permitted GraphQL operation, use HttpGraphQlTester.execute().errors() or raw HTTP assertions on status and errors.

### GraphQlTester watches for errors by default

When asserting **.path("greeting").entity(String.class).isEqualTo(...)**, GraphQlTester also verifies GraphQL errors; a payload containing errors should not be treated as a pass just because one data path holds a value.

To **expect GraphQL errors**, use:

~~~java
tester.document("{ secret }")
        .execute()
        .errors()
        .satisfy(errors ->
                assertFalse(errors.isEmpty()));
~~~

**.errors().satisfy(...)** lets you inspect the error list and acknowledge those errors as expected. You can use **.errors().expect(predicate).verify()** to check a specific error type/property per contract. When an application needs to verify partial data alongside errors, handle the errors explicitly before asserting the remaining valid data paths.

Never use a global **.errorFilter(error -> true)** just to ignore all errors; that turns unexpected errors into green tests.

## 4. HTTP authentication and field-level authorization are two separate layers

Spring Security can protect **POST /graphql** using a **SecurityFilterChain**. URL-level matchers only see the HTTP method and path, so they normally do not know whether the GraphQL document inside reads **greeting** or **secret**. Because every query can go to the same URL, URL matchers alone cannot enforce field-level permissions.

Illustrative policy in the example:

- **Anonymous**: POST /graphql without Basic credentials -> HTTP **401**.
- **reader** with ROLE_READER: POST /graphql permitted by HTTP; greeting query succeeds.
- **guest** with ROLE_GUEST: POST /graphql denied by the filter chain -> HTTP **403**.
- **admin** with ROLE_ADMIN: POST /graphql permitted; allowed to read the secret field.
- **reader** querying the secret field: HTTP request accepted, but the service method with **@PreAuthorize("hasRole('ADMIN')")** denies access at data fetching. Result can be **HTTP 200 with GraphQL errors**.
- **admin** querying secret: returns **secret-for-admin**, no GraphQL errors.

**@EnableMethodSecurity** is required to activate @PreAuthorize annotations in the example; adding spring-boot-starter-security alone does not enable method security. Place the annotation on a **Spring-managed service method**, not a private method or self-invocation in the same class, so the AOP proxy intercepts the call.

**CSRF:** in a browser app using sessions/cookies, GraphQL POST requests can be blocked by CSRF protection (HTTP 403) before GraphQL authentication/authorization runs. The example uses Basic Auth for a demo API and **ignores CSRF only on /graphql** to focus on authentication and roles. That choice **is not a production default**; when using cookie-based auth, evaluate CSRF risk carefully and test CSRF tokens. Never disable all security just to make tests pass.

## 5. Runnable project: Spring Boot 3.4.5 + GraphQL + Spring Security

The example below uses the Spring MVC servlet stack. Add **spring-boot-starter-webflux in testImplementation** to obtain WebTestClient plus the HTTP client implementation for tests; the application **remains MVC** because spring-boot-starter-web is present and Spring Boot prefers MVC when both MVC and WebFlux are on the classpath. No separate WebFlux server is started.

File tree:

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/resources/graphql/schema.graphqls
src/main/java/com/example/graphqlsecure/GraphQlSecureApplication.java
src/main/java/com/example/graphqlsecure/SecurityConfig.java
src/main/java/com/example/graphqlsecure/GreetingGraphQlController.java
src/main/java/com/example/graphqlsecure/SecretService.java
src/test/java/com/example/graphqlsecure/GraphQlHttpTransportTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'secure-graphql-http-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Dependency explanation:**

- **spring-boot-starter-graphql** provides the Spring for GraphQL runtime and schema support.
- **spring-boot-starter-web** configures the application with a Spring MVC servlet HTTP endpoint.
- **spring-boot-starter-security** adds the servlet security filter chain and Basic Auth.
- **spring-graphql-test** contains HttpGraphQlTester/GraphQlTester; starter-test **does not guarantee** GraphQL-specific testers.
- **spring-boot-starter-webflux** is only on the test classpath so WebTestClient has a transport client implementation. Do not convert the app to WebFlux and do not use @WebFluxTest.
- The Spring Boot BOM aligns compatible Spring/Spring GraphQL/Spring Security versions; avoid pinning an arbitrary reactor-netty/webflux version outside the BOM.

**src/main/resources/application.yml**

~~~yaml
spring:
  graphql:
    path: /graphql
    graphiql:
      enabled: false
~~~

The GraphQL endpoint path in this example is **POST /graphql**. GraphiQL UI is disabled so no unnecessary UI is exposed in the demo. GraphiQL is a developer tool, not the GraphQL execution endpoint; never enable it in production just because a test needs to run queries.

### 5.1. GraphQL schema

**src/main/resources/graphql/schema.graphqls**

~~~graphql
type Query {
  greeting(name: String!): String!
  secret: String
}
~~~

**greeting(name:)** requires a non-null String. **secret** is nullable so that when the data fetcher is denied, GraphQL can return **data.secret = null** with an errors entry instead of non-null propagation turning the entire data object into null. This is an intentional choice to demonstrate a **GraphQL execution error**.

No schema field models HTTP response status; those belong to the transport/security layer outside GraphQL. SOAP has its own XML envelope, SOAPAction, Fault, and WS-Security semantics—do not use HttpGraphQlTester to test SOAP transport.

### 5.2. Application class

**src/main/java/com/example/graphqlsecure/GraphQlSecureApplication.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlSecureApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlSecureApplication.class, args);
    }
}
~~~

Placing the classes and schema at the standard paths lets Spring Boot auto-discover the GraphQL schema at classpath:graphql/** and register the GraphQL HTTP handler at /graphql. The Java snippets compile against Java 17 and the dependencies in build.gradle.

### 5.3. SecurityFilterChain and three demo users

**src/main/java/com/example/graphqlsecure/SecurityConfig.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/graphql"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/graphql")
                    .hasAnyRole("READER", "ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER").build(),
            User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN").build(),
            User.withUsername("guest")
                .password("{noop}guest-pass")
                .roles("GUEST").build());
    }
}
~~~

**Why these expected statuses?**

- Anonymous POST does not satisfy **hasAnyRole**; the httpBasic authentication entry point responds with **401 Unauthorized**.
- Guest authenticates successfully yet only has ROLE_GUEST, outside the allowlist, resulting in **403 Forbidden**.
- Reader and admin can reach the **HTTP endpoint**, which does not imply they can read every GraphQL field.
- **anyRequest().denyAll()** blocks URLs other than POST /graphql, preventing accidental exposure of other endpoints in the sample.
- **csrf.ignoringRequestMatchers("/graphql")** ignores CSRF only on the one Basic Auth URL in this demo, rather than disabling CSRF application-wide.

**Security note:** **{noop}** passwords are for instructional use only—they do not hash secrets and are unfit for production. Real apps must use a strong PasswordEncoder, secret management, HTTPS, rate limiting, and proper credential/role management. Basic Auth over plain HTTP like localhost in tests is unsafe for sending credentials over public networks.

### 5.4. Resolvers and method security

**src/main/java/com/example/graphqlsecure/SecretService.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecretService {
    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret() {
        return "secret-for-admin";
    }
}
~~~

**src/main/java/com/example/graphqlsecure/GreetingGraphQlController.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingGraphQlController {
    private final SecretService service;

    public GreetingGraphQlController(SecretService service) {
        this.service = service;
    }

    @QueryMapping
    public String greeting(@Argument String name) {
        return "Hello, " + name;
    }

    @QueryMapping
    public String secret() {
        return service.readSecret();
    }
}
~~~

Spring GraphQL maps **greeting** and **secret** to fields on the Query type, not HTTP REST @GetMapping endpoints. **@Argument String name** extracts the name variable from GraphQL input after document validation. For **secret**, the controller delegates to the **Spring-managed SecretService**, ensuring @PreAuthorize passes through the AOP proxy. Self-invoking **this.readSecret()** inside the same bean would bypass method security proxies.

When reader queries secret, the HTTP filter permits reader into /graphql, then @PreAuthorize on the service rejects the call. Spring GraphQL turns the data fetcher exception into **GraphQL errors**. Public error wording may be masked by the framework; tests should assert error presence and path rather than **depending on internal text** from AccessDeniedException.

## 6. Real HTTP tests with HttpGraphQlTester and WebTestClient

**src/test/java/com/example/graphqlsecure/GraphQlHttpTransportTest.java**

~~~java
package com.example.graphqlsecure;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class GraphQlHttpTransportTest {
    @LocalServerPort
    private int port;

    private WebTestClient rawHttp;
    private HttpGraphQlTester baseTester;
    private HttpGraphQlTester readerTester;
    private HttpGraphQlTester adminTester;

    @BeforeEach
    void configureClients() {
        String root = "http://127.0.0.1:" + port;

        rawHttp = WebTestClient.bindToServer()
                .baseUrl(root)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        WebTestClient gqlHttp = WebTestClient.bindToServer()
                .baseUrl(root + "/graphql")
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        baseTester = HttpGraphQlTester.create(gqlHttp);

        readerTester = baseTester.mutate()
                .headers(headers ->
                    headers.setBasicAuth("reader", "reader-pass"))
                .build();

        adminTester = baseTester.mutate()
                .headers(headers ->
                    headers.setBasicAuth("admin", "admin-pass"))
                .build();
    }

    @Test
    void runtimePortIsAssignedByRealServer() {
        assertTrue(port > 0);
    }

    @Test
    void unauthenticatedGraphQlPostIsHttp401() {
        rawHttp.post().uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicCredentialsAreHttp401() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "wrong-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedButWrongRoleIsHttp403() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("guest", "guest-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerUsesHttpHeaderAndGraphQlVariables() {
        readerTester.document("""
                query Greet($name: String!) {
                  greeting(name: $name)
                }
                """)
                .variable("name", "Lan")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, Lan");
    }

    @Test
    void adminCanReadProtectedGraphQlField() {
        adminTester.document("{ secret }")
                .execute()
                .path("secret")
                .entity(String.class)
                .isEqualTo("secret-for-admin");
    }

    @Test
    void readerGetsGraphQlErrorForProtectedField() {
        readerTester.document("{ secret }")
                .execute()
                .errors()
                .satisfy(errors -> assertFalse(errors.isEmpty()));
    }

    @Test
    void fieldAuthorizationErrorCanStillBeHttp200() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query", "{ secret }"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.errors[0].path[0]")
                    .isEqualTo("secret");
    }

    @Test
    void rawHttpAlsoChecksSuccessContract() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "query", "query Greet($name: String!) "
                                + "{ greeting(name: $name) }",
                        "operationName", "Greet",
                        "variables", Map.of("name", "Mai")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.data.greeting")
                    .isEqualTo("Hello, Mai");
    }
}
~~~

**This section uses two tools to prove two distinct layers:**

1. **HttpGraphQlTester** for successful queries and expected GraphQL-level errors. It extracts data paths with **path(...).entity(...)** while managing request documents and variables. **mutate().headers(...)** derives independent testers for reader and admin without mutating headers on a shared tester across tests.
2. **Raw WebTestClient** for security filter **401/403** status codes, without pretending GraphQL executed the query when rejected earlier. It also inspects the raw HTTP 200 response containing **errors** when reader is denied by **field-level authorization**.
3. **@LocalServerPort** supplies the real random port; **bindToServer** issues HTTP requests over loopback rather than a mock servlet. **responseTimeout(5s)** bounds real client wait time; this is not an application SLA requirement of 5s.
4. **Basic Authorization** is set in headers, distinct from GraphQL variables. Never put credentials inside the GraphQL document or query string where they could be logged or cached.
5. In the test where reader is blocked on a field, **do not assert a specific exception message** because Spring GraphQL may mask security error details; asserting status=200 along with errors.path is evidence of the **GraphQL execution** phase.

**Code notes:** importing assertNotEquals is an unused import that compiles cleanly; it can be removed if your IDE flags unused imports. There are no stateful DB operations or thread sleeps, so tests isolate cleanly. Each test creates fresh WebTestClient/tester instances in @BeforeEach while the Spring ApplicationContext and embedded server may be reused via the **TestContext cache** across methods. The port is read after server startup rather than hardcoded.

### Why not use HttpGraphQlTester for 401/403?

HttpGraphQlTester works best when the GraphQL transport returns a **valid GraphQL tester response**, typically HTTP 200 with JSON data/errors. When the server responds with **HTTP 401/403**, the tester can fail at the transport step before reaching .errors(), because that response is not an expected GraphQL execution result. To test status codes directly, **WebTestClient.expectStatus()** states the contract clearly.

If a test uses **GraphQlTester.errors().satisfy(...)** for every error case, it can miss that the request was blocked by an HTTP filter before reaching the GraphQL engine. Conversely, asserting only raw HTTP 200 does not prove the operation returned the right data.

## 7. Interpreting results: four distinct security cases

| Scenario | Authorization header | Deciding layer | Expected HTTP status | GraphQL data/errors |
| --- | --- | --- | --- | --- |
| Unauthenticated | None | HTTP Basic/Spring Security | **401** | GraphQL envelope not required |
| Wrong credentials | Basic with wrong password | Authentication provider | **401** | GraphQL envelope not required |
| Guest logged in but lacks role | Basic guest/GUEST | URL SecurityFilterChain | **403** | GraphQL envelope not required |
| Reader queries greeting | Basic reader/READER | HTTP allow + resolver | **200** | data.greeting, no errors |
| Admin queries secret | Basic admin/ADMIN | HTTP allow + method @PreAuthorize | **200** | data.secret, no errors |
| Reader queries secret | Basic reader/READER | HTTP allow, method security denies | **200** in demo | errors[0].path contains secret, data.secret may be null |

This table reflects the **demo project's contract**, not a mandatory HTTP status table for all GraphQL servers. Custom security configurations can change status codes and error bodies. The GraphQL-over-HTTP media type **application/graphql-response+json** can also change how pre-execution request/validation errors behave; check the Accept and Content-Type headers sent by real clients.

### Flow of a successful request

~~~text
POST /graphql + Basic reader + GraphQL query greeting
 -> HttpSecurity: authenticated + ROLE_READER => ALLOW
 -> Spring GraphQL: parse/validate document
 -> GreetingGraphQlController.greeting("Lan")
 -> "Hello, Lan"
 -> HTTP 200 + {"data":{"greeting":"Hello, Lan"}}
~~~

### Flow of a guest request without the required role

~~~text
POST /graphql + Basic guest + query greeting
 -> Authentication succeeds (guest is valid)
 -> hasAnyRole(READER, ADMIN) => DENY
 -> HTTP 403
 -> GraphQL controller does not need to run
~~~

### Flow of reader accessing a sensitive field

~~~text
POST /graphql + Basic reader + query secret
 -> HTTP security ALLOW /graphql
 -> GraphQL parse/validate succeeds
 -> GreetingGraphQlController.secret()
 -> SecretService.readSecret() via Spring AOP proxy
 -> @PreAuthorize hasRole('ADMIN') => DENY
 -> GraphQL data-fetching error
 -> HTTP 200 + errors, not a valid secret result
~~~

**Do not use HTTP URL filters to replace field-level permissions** when a single GraphQL endpoint exposes multiple operations. An account allowed to call /graphql **must not be assumed** authorized to read every field or object. With multi-tenant data, test ownership, resource-level security, and principal propagation into asynchronous DataFetchers.

## 8. How to run the project and test manually via HTTP

With a Gradle Wrapper compatible with Java 17 and Boot 3.4.x, run:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.graphqlsecure.GraphQlHttpTransportTest
./gradlew bootRun
~~~

On Windows, use **gradlew.bat** instead of ./gradlew. The JUnit tests in section 6 **are designed to PASS** when sources, dependencies, and configuration match the lesson. That is an **outcome expected from code logic**, not stdout from an actually executed build; the RANDOM_PORT port varies per run.

After bootRun, Spring Boot's default servlet HTTP server listens on 8080 unless overridden by environment/config, so you can try:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "reader:reader-pass" \
  --data '{"query":"{ greeting(name: \"Lan\") }"}'

curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "guest:guest-pass" \
  --data '{"query":"{ greeting(name: \"Lan\") }"}'

curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "admin:admin-pass" \
  --data '{"query":"{ secret }"}'
~~~

These lines use **\\** for line continuation in Unix shells, not Windows PowerShell. On Windows, run an equivalent single-line curl.exe command. Never run commands with real credentials from shell history in production.

**Expected results:** reader greeting returns data.greeting = "Hello, Lan"; guest receives HTTP 403; admin secret returns "secret-for-admin". When reader queries secret, the response contains errors from field-level method security (the message may be generic) and must never expose the secret value.

## 9. Verifying HTTP headers and GraphQL variables properly

### Query document, operationName, and variables

A GraphQL POST JSON body can contain:

~~~json
{
  "query": "query Greet($name: String!) { greeting(name: $name) }",
  "operationName": "Greet",
  "variables": { "name": "Lan" }
}
~~~

**query** is the document; **operationName** selects an operation when the document has multiple operations; **variables** supplies values. With HttpGraphQlTester, you do not manually serialize the request JSON:

~~~java
readerTester
        .document("""
            query Greet($name: String!) {
              greeting(name: $name)
            }
            """)
        .variable("name", "Lan")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, Lan");
~~~

This excerpt comes from the runnable test. **Do not concatenate user input directly into the query string** when variables can be used; variables separate data from the document, avoid escaping bugs, and enforce schema type checks.

### HTTP authentication headers

HttpGraphQlTester supports configuring headers via its builder, for example:

~~~java
HttpGraphQlTester asAdmin = readerTester.mutate()
        .headers(headers ->
                headers.setBasicAuth("admin", "admin-pass"))
        .build();
~~~

This is an **excerpt**. Calling **mutate()** creates a new tester instance, avoiding mutating shared credentials on a common tester when tests run concurrently. If you want to avoid inheriting previous Basic headers from mutate behavior, derive the admin tester from **baseTester** as in section 6; that keeps header origins explicit.

For Bearer tokens in a real project:

~~~java
HttpGraphQlTester bearerTester = baseTester.mutate()
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .build();
~~~

**Excerpt:** accessToken should be minted by a test identity provider or valid test fixture; never hardcode production tokens in source code. When testing JWTs, verify signature, issuer, audience, expiry, scopes, and HTTP/field authorization per policy, not merely "some token string is present."

### To prove a header reached the server, test behavior

Calling **headers.setBasicAuth** alone does not prove the filter authenticated it; tests must observe:
- Reader request with valid credentials => HTTP passes, GraphQL greeting returns data.
- Guest with valid credentials but wrong role => HTTP 403.
- Wrong password => HTTP 401.
- Admin with valid credentials => field security allows secret.
- Reader with valid credentials => GraphQL field security rejects secret.

These five pieces of evidence distinguish **header presence**, **valid authentication**, **URL authorization**, **field authorization**, and **business response**.

## 10. Testing HTTP errors from JSON or content negotiation

HTTP input errors are distinct from GraphQL execution errors. Depending on the version/framework:

- **POST** missing or using the wrong Content-Type can return **415 Unsupported Media Type**.
- Malformed JSON bodies can return **400 Bad Request** before GraphQL validation.
- Syntactically or schema-invalid GraphQL documents produce GraphQL request errors, with status varying by server and Accept negotiation.
- Requests exceeding size limits can get 413 from the servlet container or proxy.
- Rate limiters or API gateways can return 429 before GraphQL resolvers execute.

Do not catch these statuses with **GraphQlTester.errors()** when the HTTP layer returns a non-200 response. Use WebTestClient and assert **HTTP status plus body/headers per policy**, noting whether the request passes through security filters beforehand.

Example checking request headers without assuming an unconfigured status code:

~~~java
rawHttp.post()
        .uri("/graphql")
        .headers(h -> h.setBasicAuth("reader", "reader-pass"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting(name: \"Lan\") }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello, Lan");
~~~

Here we pin Content-Type per the test contract and assert the successful payload. Wrong Content-Type cases, when important for the API, need separate tests matching the actual status returned by your framework/version.

## 11. GraphQL errors: message, path, extensions, and authorization

A GraphQL error typically has **message**, **locations**, **path**, and optionally **extensions**. Verification should prioritize **stable application-defined properties** rather than internal messages, traces, or stack data that the framework masks to prevent information disclosure.

In the demo, the GraphQL schema defines nullable field **secret**, so when method security denies access, the post-execution response typically contains:
- **data.secret = null**
- non-empty **errors**
- error path pointing to **secret**

If a field is declared non-null and its fetcher errors, GraphQL null bubbling can set **parent data or the entire data object = null**, so do not assume one fixed partial-data shape across different schemas. When an app registers a custom **DataFetcherExceptionResolver**, error classification/codes can differ and may map AccessDeniedException to a team-defined **FORBIDDEN** extension; in that case, assert the extension code contract instead of guessing framework defaults.

**Never expose stack traces or sensitive exception messages** in client responses just to make test assertions easier. Combining **errors.path**, application-controlled **extensions.code**, and allow/deny behavior is far safer.

### When a single query contains both permitted and forbidden fields

GraphQL lets a client query multiple fields in one operation. If one field is forbidden, other fields may still return data depending on schema nullability and execution semantics. Tests should check:
1. Permitted fields return accurate data.
2. Forbidden fields never leak secrets.
3. Matching error path/code is present.
4. Authorization is not bypassed via aliases, fragments, or nested resolvers.

URL security only sees the **/graphql** path and cannot distinguish queried fields; to test multi-field authorization thoroughly, write integration tests with multiple roles/tenants and real data fetchers.

## 12. Comparing test slices and full integration tests

Available test options:

**@GraphQlTest(GreetingGraphQlController.class)** scopes to GraphQL infrastructure and the controller, typically without opening an HTTP socket. When the controller needs SecretService, use **@MockitoBean** or an appropriate @Import. It works well for schema/data-fetcher mapping, yet provides no evidence of transport authentication.

**@SpringBootTest(webEnvironment = MOCK)** + WebGraphQlTester can exercise handlers in memory, without necessarily testing Servlet filters or TCP sockets.

**@SpringBootTest(webEnvironment = RANDOM_PORT)** + HttpGraphQlTester uses WebTestClient.bindToServer to issue real HTTP requests, verifying the GraphQL endpoint through the servlet HTTP pipeline and Spring Security.

**HttpGraphQlTester + MockMvcWebTestClient.bindToApplicationContext(...)** can test mock servlet transport/filter behavior in Spring MVC without launching a real server. The tester API looks identical, yet conclusions about **network transport** must differ.

| Goal | Recommended tool/setup |
| --- | --- |
| Test @QueryMapping returns expected data without HTTP | @GraphQlTest + GraphQlTester |
| Test schema validation and resolver wiring | GraphQlTester or ExecutionGraphQlServiceTester |
| Test WebGraphQlInterceptor/headers at handler | WebGraphQlTester |
| Test MVC mock HTTP handler/filters | HttpGraphQlTester via MockMvcWebTestClient |
| Test HTTP URL, Basic/Bearer, 401/403, and real data | **RANDOM_PORT + HttpGraphQlTester + WebTestClient** |
| Test WebSocket subscription auth | WebSocketGraphQlTester, never substitute an HTTP tester |
| Test SOAP envelope/SOAPAction/WS-Security | Dedicated SOAP test client, never use HttpGraphQlTester |

**SOAP belongs to the other branch of the "GraphQL and SOAP" module**: SOAP transport uses XML Envelopes, XML Schemas, SOAPAction, and distinct SOAP Fault/WS-Security mechanisms. In this lesson it is compared only to prevent misusing the wrong tester; the core focus remains HttpGraphQlTester.

## 13. Common mistakes when testing authentication and transport

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| IDE cannot find HttpGraphQlTester | Missing **spring-graphql-test** in testImplementation | Add the proper dependency per the Spring Boot BOM |
| Cannot find WebTestClient | Missing Spring WebFlux test client/connector | Add starter-webflux in testImplementation only for MVC apps |
| HttpGraphQlTester test runs without an HTTP server | WebTestClient bound via bindToApplicationContext or MockMvcWebTestClient | Use bindToServer + RANDOM_PORT |
| GET/POST GraphQL returns 404 | Wrong spring.graphql.path or URL in tester | Verify /graphql, context path, and actual port |
| GraphQL test gets 401 despite valid user | Authorization header not sent, wrong path, or wrong password | Inspect Basic header and server security config |
| GraphQL test gets 403 on POST | Blocked by CSRF or insufficient role | Distinguish CSRF vs Authorization, inspect tokens/security config |
| Guest allowed to execute query | Matcher fails to protect /graphql or custom SecurityFilterChain inactive | Assert 403 with an authenticated user lacking the role |
| Reader querying secret receives data | Missing @EnableMethodSecurity, @PreAuthorize self-invocation, or unproxied service | Place method security on a proxied bean; assert denial |
| Reader querying secret gets error, test expects HTTP 403 | Failure occurs at data fetcher after HTTP allow | Assert HTTP 200 + GraphQL errors per contract |
| Test calls .errors() yet HTTP response is 401 | GraphQlTester is not meant as a status tester for arbitrary non-200 responses | Use WebTestClient.expectStatus() |
| Test passes yet secret leaks in multi-field query | Aliases, fragments, or nested data fetchers untested | Write permission tests per operation and object |
| GraphQL error message changes across framework versions | Relying on internal exception strings | Assert stable error paths/codes from resolvers |
| MockMvc test passes yet production transport fails | TCP/TLS/network/proxy untested | Add RANDOM_PORT or deployment-level integration tests |
| Wrong Content-Type gets 415 | Not sending application/json or wrong Accept | Set proper request headers; test 415 intentionally |
| JSON response has both data and errors | Partial success per GraphQL semantics | Inspect both rather than HTTP status alone |
| Credentials leak across roles between tests | Mutating shared tester/header across the suite | Create new testers with mutate from base, keeping identities isolated |
| RANDOM_PORT test connects to 8080 | Hardcoded port instead of local.server.port | Use @LocalServerPort and dynamic root URL |
| Role test passes alone, fails in suite | Different context cache/security config/profile, shared state | Isolate fixtures, configure explicitly, avoid global mutation |

## 14. Security and test data: limits to remember

**Credentials:** `{noop}` passwords in the example are purely illustrative. Production systems must encrypt/hash passwords, enforce HTTPS, manage secrets via vaults/environment variables, and avoid logging Authorization headers. Never commit real user tokens into the repository.

**CSRF:** when using browser sessions/cookies, ignoring CSRF on /graphql may be inappropriate. Assess the real attack surface; if CSRF protection applies, test a missing-token request => 403 and a valid-token request => success using a cookie/session-capable HTTP client.

**GraphQL depth/complexity:** an authenticated URL does not make arbitrary operations safe. Limit query depth, complexity, field authorization, pagination, introspection policy, and batch abuse where needed.

**Multi-tenancy/ownership:** hasRole('ADMIN') is a simple example; with real data, queries must verify the caller has access to the **specific object**, not merely a URL role. Include "valid token, wrong tenant/resource" tests.

**Error masking:** authorization and validation failures must not accidentally leak secrets or stack traces. Server logs can retain correlation IDs and diagnostics; HTTP GraphQL errors must return sanitized details.

**Timeouts/concurrency:** WebTestClient's responseTimeout is a test bound; it does not prove SLAs, server timeouts, connection pooling, or production retries. Write dedicated integration/load tests when those are contractual.

**Context cache:** @SpringBootTest can reuse the ApplicationContext across methods. None of the demo tests mutate server-side state. For DB-writing GraphQL mutations, the real HTTP client and server typically execute in separate threads/transactions; @Transactional on a JUnit method does not roll back the HTTP server's DB transaction. Clean up data with an explicit strategy.

## 15. Self-check exercises

**A.** HttpGraphQlTester returns the right greeting using MockMvcWebTestClient. Does that prove the TCP port for /graphql works live? **Not yet**. You need bindToServer and a real server test.

**B.** An anonymous request to /graphql returns HTTP 401. Should you call GraphQlTester.errors() to verify authentication? **Unnecessary and error-prone**; use WebTestClient.expectStatus().isUnauthorized().

**C.** Guest logs in validly with role GUEST and gets HTTP 403. What was verified? **URL authorization** rejecting an unprivileged identity, distinct from a wrong password.

**D.** Reader queries greeting successfully, while querying secret returns HTTP 200 with errors. Is that a security bug? **Not necessarily**. That is field-level authorization at the execution layer; a GraphQL error response is the fitting contract.

**E.** Adding a URL SecurityFilterChain allowing ROLE_READER on /graphql—can reader safely access all GraphQL fields? **No**; you need field/service/resource-level authorization.

**F.** Why must tests use @LocalServerPort? **RANDOM_PORT** assigns a different actual port at runtime, so 8080 cannot be assumed.

**G.** Why must @PreAuthorize be placed on SecretService called by the controller? Because **method security relies on proxies**, and self-invocation can bypass advice.

**H.** To verify a wrong Content-Type returns 415 or an HTTP error, which tester should you use? **Raw WebTestClient**, asserting status/body per your framework/version.

**I.** Can HttpGraphQlTester be used to test SOAP XML bodies? **No**. SOAP requires test clients and assertions tailored to envelopes and WS-Security.

### Final review checklist

- Have I distinguished GraphQlTester, HttpGraphQlTester, and WebTestClient?
- Is WebTestClient using **bindToServer** or a mock context? Do transport conclusions match?
- Do RANDOM_PORT tests use **@LocalServerPort** instead of hardcoded 8080?
- Are endpoint path, POST, Content-Type, variables, and operationName verified?
- Are HTTP 401 for anonymous/bad credentials and HTTP 403 for authenticated wrong role tested?
- Is GraphQL 200 + errors from field-level authorization distinguished from HTTP 403?
- Are HTTP security and @EnableMethodSecurity/@PreAuthorize properly enabled?
- Is a separate tester created per identity without leaking headers to other tests?
- Do error assertions avoid relying on internal messages or exposing secrets?
- Are schema nullability, partial data, extensions, and error paths interpreted properly?
- Are CSRF, HTTPS, resource/tenant authorization, and query complexity addressed for production?
- Are dedicated tests used for other transports (WebSocket, SOAP) instead of misusing an HTTP tester?
- Have I verified the actual security configuration instead of disabling filters to make tests pass?

**Conclusion:** **HttpGraphQlTester** lets you send GraphQL documents/variables and assert data/errors over HTTP, yet proof about transport depends on **whether WebTestClient is bound to a real server**. For **transport and authentication testing**, use **@SpringBootTest(RANDOM_PORT)** + **WebTestClient.bindToServer** to hit the live port, **HttpGraphQlTester** for valid queries and GraphQL errors, and **raw WebTestClient** for HTTP 401/403, headers, and non-GraphQL statuses. URL security only guards /graphql; field-level authorization must be tested separately so not every caller allowed on the endpoint can read all data.

## Official documentation

- Spring for GraphQL 1.3 — Testing (HTTP tester, builders, errors): https://docs.spring.io/spring-graphql/docs/1.3.x/reference/html/#testing
- Spring GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring GraphQL — Security: https://docs.spring.io/spring-graphql/reference/security.html
- Spring GraphQL 1.3 — HttpGraphQlTester API: https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/HttpGraphQlTester.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Security — Servlet Authorization and Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html