# `ExecutionGraphQlServiceTester` vs. Testing GraphQL over HTTP

In Spring Boot, a GraphQL query can be tested at **several different boundaries**. We can invoke Spring's GraphQL execution service directly, or send an **HTTP POST /graphql** to test the web path. Both approaches can use the same `GraphQlTester.document(...).execute().path(...)` syntax, yet **a passing test does not prove the same thing**.

- **`ExecutionGraphQlServiceTester`** runs through **`ExecutionGraphQlService`**, requiring no HTTP client, router, Servlet/Netty server, HTTP headers, or sockets. It is suited for testing the GraphQL schema, field mappings, `@QueryMapping`/`@MutationMapping`, argument binding, `DataFetcher`s, and data/errors returned by GraphQL execution.
- **`HttpGraphQlTester`** uses **`WebTestClient`** to send requests at the **HTTP** layer. However, `WebTestClient` can be bound **to a mock web context without sockets** or **to a real server**. Therefore, seeing `HttpGraphQlTester` in a test is not enough to claim network testing.
- **`WebGraphQlTester`** is the middle step: it runs through **`WebGraphQlHandler` and the `WebGraphQlInterceptor` chain** using simulated transport information, **without needing a real HTTP client or server**.

This article explains how to choose based on your goal, configuring `@GraphQlTest`/`@SpringBootTest`, the difference between **HTTP status** and **GraphQL errors**, and a complete **Java 17 + Spring Boot 3.5 + JUnit Jupiter** sample project covering GraphQL execution units, mock HTTP, and a real HTTP server.

## 1. Spring GraphQL architecture: the layers traversed

```text
GraphQL document: query { greeting(name: "Mai") }
      |
      +--- ExecutionGraphQlServiceTester --------------------+
      |                                                       |
      |     (no client, no HTTP, no socket)                   |
      |                                                       v
      |                                            ExecutionGraphQlService
      |                                                       |
      +--- WebGraphQlTester --> WebGraphQlHandler ------------+
      |                        + WebGraphQlInterceptor         |
      |                                                       |
      +--- HttpGraphQlTester --> WebTestClient --> HTTP ------+
                               |                  |           |
                               |                  +-- mock ---+
                               |                  |           |
                               |                  +-- TCP server
                               |
                               +-- request encoding, status,
                                   headers, transport route
                                                       |
                                                       v
                                             GraphQlSource / GraphQL Java
                                                       |
                                                       v
                                           Schema, @QueryMapping, DataFetcher
                                                       |
                                                       v
                                             ExecutionResult (data/errors)
```

The diagram shows **boundaries** rather than implying every Spring object must traverse a single fixed path. On a real server, an HTTP request is normally received by the Spring MVC or WebFlux transport, then passed to `WebGraphQlHandler` and `ExecutionGraphQlService`; in direct execution tests, the transport leg is skipped.

**`ExecutionGraphQlService`** is Spring GraphQL's abstraction for GraphQL Java execution. `DefaultExecutionGraphQlService` uses a `GraphQlSource` to access the GraphQL schema and runtime wiring. Testing at this layer still catches schema errors, resolver/argument mapping bugs, and exception resolution—it is **not** a plain Java unit test instantiating a controller with `new` and asserting a string.

### Same assertion API, different subject under test

```java
tester.document("""
        query Greeting($who: String!) {
            greeting(name: $who)
        }
        """)
    .variable("who", "Mai")
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("Hello, Mai!");
```

This is a **snippet inside a test class** that already holds a `tester` variable of type `GraphQlTester` or a suitable subtype; the runnable files are in section 6. Key point: the methods `document`, `variable`, `execute`, `path`, and `entity` **do not reveal whether the test uses HTTP**. You must inspect how the tester was **created or bound**.

## 2. Comparison matrix for choosing the right test level

| Goal / Property | `ExecutionGraphQlServiceTester` | `WebGraphQlTester` | `HttpGraphQlTester` bound to mock | `HttpGraphQlTester` bound to real server |
|---|---|---|---|---|
| Executes GraphQL schema, fields, and resolvers | **Yes** | **Yes** | **Yes** | **Yes** |
| `@QueryMapping`, arguments, query variables | Yes, if context has controllers and wiring | Yes, if context has controllers and wiring | Yes | Yes |
| `GraphQL data/errors` | **Yes** | **Yes** | **Yes** | **Yes** |
| `WebGraphQlInterceptor` chain | **Bypassed by default** | **Yes** | Yes via web transport when configured | Yes via web transport |
| HTTP `/graphql` endpoint registered | **No** | **No** | **Yes in mock HTTP context** | **Yes on real server** |
| HTTP method, Content-Type, Accept, status, headers | **No** | Can simulate header info for interceptors, but does not test HTTP encoding/status | **Yes, at mock HTTP layer** | **Yes, over real HTTP** |
| Servlet/WebFlux filter/security chain | **Not tested** | **Does not run full filter chain** | Yes if web context/filters are configured | Yes if server/filters are configured |
| Socket/TCP/embedded server startup | **No** | **No** | **No** | **Yes** |
| Browser CORS/preflight, TLS/proxy, production deployment | No | No | Only partial mock HTTP configuration | Incomplete if calling localhost only |
| Relative speed | Usually fastest among Spring GraphQL tests | No server needed | No server needed | Slower due to server startup/binding |
| When to use | GraphQL execution contract | Request context/interceptors | Spring HTTP mapping/encoding without sockets | End-to-end app HTTP over loopback |

Read the table carefully: every "Yes" holds only when **assertions actually verify that behavior** and the context includes the needed beans. `HttpGraphQlTester` mainly focuses on the **GraphQL payload**, and does not directly expose raw HTTP status assertions on the same `GraphQlTester` API; to assert exact transport status codes and headers, use `WebTestClient` or an HTTP client at the same boundary.

## 3. `ExecutionGraphQlServiceTester`: server-side tester without transport

Spring GraphQL provides a factory method:

```java
import org.springframework.graphql.execution.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlService executionService = /* bean from Spring context */ null;
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionService);
```

This snippet **illustrates the API signature**; it does not run standalone because `executionService` is not obtained from a Spring context. In a real test, use `@Autowired ExecutionGraphQlService` or inject the bean via constructor. This factory exercises **GraphQL server execution** directly without `WebTestClient`.

When you need to customize `ExecutionInput`, use the builder:

```java
ExecutionGraphQlServiceTester customized =
        ExecutionGraphQlServiceTester.builder(executionService)
                .configureExecutionInput((input, builder) ->
                        builder.graphQLContext(java.util.Map.of(
                                "requestSource", "test"))
                                .build())
                .build();
```

This is a snippet inside a test with a real `executionService`; customizing `ExecutionInput` helps when resolvers read GraphQL context or need an `ExecutionId`. However, **it does not replace testing HTTP header → GraphQL context**: if production relies on a `WebGraphQlInterceptor` extracting `X-Tenant` from headers, direct execution tests do not prove that header extraction runs.

**When appropriate:**

- Testing SDL schema, types/fields, arguments, data fetchers, and resolvers.
- Testing GraphQL query/mutation logic, field projection, nullability, validation errors, and mapped exceptions.
- Testing `DataLoader`/resolver integration **provided** they are actually configured in the test context.
- Isolating GraphQL execution bugs from web transport during debugging.
- Catching contract issues quickly on PRs before running heavier HTTP integration tests.

**Do not use it to claim:** `POST /graphql` is routed properly, JSON content-type is accepted, authorization filters work, CORS preflight is allowed, an HTTP port is open, or external network clients can connect.

## 4. How does `@GraphQlTest` create the tester and scope?

In **Spring Boot 3.5**, `@GraphQlTest` focuses on GraphQL execution without HTTP transport. It loads key Spring GraphQL beans: `@Controller`, `@ControllerAdvice`, `RuntimeWiringConfigurer`, `DataFetcherExceptionResolver`, `GraphQlSourceBuilderCustomizer`, `Instrumentation`, and related conversion/JSON components.

```java
@GraphQlTest(GreetingGraphQlController.class)
class GreetingGraphQlSliceTest {
    @Autowired
    GraphQlTester graphQlTester;
}
```

This is a configuration skeleton; the runnable example is in section 6. `@GraphQlTest` auto-configures **`GraphQlTester`** for immediate testing. If you want to emphasize the execution layer explicitly, you can autowire `ExecutionGraphQlService` and create **`ExecutionGraphQlServiceTester`** via its factory as shown in the lab.

**The slice intentionally avoids auto-scanning** `@Service`, `@Repository`, and most general `@Component` beans. When a controller needs `GreetingService`, use `@MockitoBean` on a test field inside the slice to supply the collaborator. `@MockitoBean` comes from **Spring Framework 6.2+**; Spring Boot 3.5 supports it. When a test only needs to verify GraphQL mapping and responses, mocking the service is the right boundary; to prove a real service integrates with a repository, use `@SpringBootTest` or an appropriate multi-layer test.

If the schema cannot be found, check `src/main/resources/graphql/*.graphqls` or `*.gqls` and `spring.graphql.schema.locations`. **A schema is mandatory**: a `@QueryMapping` annotation on a method does not automatically create the corresponding SDL field. Never write a GraphQL slice test with just a controller class while omitting the schema and assuming the framework will infer all fields.

## 5. HTTP GraphQL: same tester, two transport modes

### 5.1. Mock HTTP with `@AutoConfigureHttpGraphQlTester`

With Spring Boot 3.5:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class MockHttpGraphQlTest {
    @Autowired
    HttpGraphQlTester tester;
}
```

This is a configuration snippet needing imports and `@Test` methods as in a complete file. Even though the tester name includes **Http**, `MOCK` mode **opens no TCP port**. Spring Boot configures `HttpGraphQlTester` using an appropriate `WebTestClient` (MVC mock via the MockMvc bridge, or WebFlux mock), exercising web endpoint routing and serialization without a real server.

**Evidence:** the GraphQL query enters the GraphQL HTTP endpoint inside a **web test context**, catching routing or configuration bugs at that layer. **Not proved:** port binding, networking, TLS, and deployment conditions.

### 5.2. Live HTTP with `@SpringBootTest(RANDOM_PORT)`

With `RANDOM_PORT`, Spring Boot starts a real embedded web server on a random port. When `spring-graphql-test` and HTTP test client dependencies are present, Boot **auto-configures `HttpGraphQlTester`** targeting that server:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealGraphQlHttpTest {
    @Autowired
    HttpGraphQlTester tester;
}
```

In this mode `HttpGraphQlTester` sends real HTTP over loopback to the server. Never hardcode `8080`; when you need to assert raw status codes or headers, inject `@LocalServerPort` and build `WebTestClient.bindToServer().baseUrl("http://127.0.0.1:" + port)`.

**Warning:** being able to **inject** `HttpGraphQlTester` is not enough to claim real HTTP integration: check whether `@SpringBootTest(webEnvironment=RANDOM_PORT/DEFINED_PORT)` is used or how the tester was bound. `HttpGraphQlTester.create(WebTestClient.bindToApplicationContext(...))` is still in-process/mock.

### 5.3. Manual construction without Spring Boot auto-configuration

Here are two **contrasting** configurations:

```java
// WebTestClient mocking a WebFlux ApplicationContext:
WebTestClient mock = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .baseUrl("/graphql")
        .build();
HttpGraphQlTester mockTester = HttpGraphQlTester.create(mock);

// Real WebTestClient targeting a running server:
WebTestClient real = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port + "/graphql")
        .build();
HttpGraphQlTester realTester = HttpGraphQlTester.create(real);
```

These snippets assume you have a `context` (Reactive `WebApplicationContext`) or a real server `port`. For Servlet MVC mock testing, use **`MockMvcWebTestClient.bindToApplicationContext(...)`** instead of binding a WebFlux application context. Both call `HttpGraphQlTester.create(...)`, yet their test boundaries are completely different.

## 6. Complete Java 17 + Spring Boot 3.5 + GraphQL example

The application exposes one GraphQL field:

```graphql
type Query {
    greeting(name: String!): String!
}
```

Valid query:

```graphql
query Greeting($who: String!) {
    greeting(name: $who)
}
```

With `who = "Mai"`, expected GraphQL data is `{"greeting":"Hello, Mai!"}`. We write three test groups to distinguish the layers:

1. **GraphQL execution slice** — `@GraphQlTest` + `ExecutionGraphQlServiceTester`, mocked collaborator.
2. **Mock HTTP transport** — `@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester`, real service, no sockets.
3. **Real HTTP server** — `@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester`; plus direct `WebTestClient` to assert **HTTP status, headers, and JSON envelope**.

There is no database, authentication, or external API. This isolates the nature of each tester from out-of-scope dependencies.

### 6.1. Directory tree

```text
graphql-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/graphql/
    │   │   ├── GraphQlDemoApplication.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingGraphQlController.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/java/com/example/graphql/
        ├── GreetingExecutionTest.java
        ├── GreetingMockHttpTest.java
        └── GreetingRealHttpTest.java
```

### 6.2. `pom.xml`: two distinct transport scopes

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>graphql-test-levels</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-graphql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.graphql</groupId>
            <artifactId>spring-graphql-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

**Why is `spring-boot-starter-webflux` in test scope?** In this runtime application we chose **Spring MVC** with `spring-boot-starter-web`, whereas `WebTestClient` used by HTTP GraphQL tests depends on reactive client/test libraries; Spring Boot 3.5 instructs adding the WebFlux test dependency if not already present. Keeping it in **test scope** avoids converting the production application to WebFlux; when both MVC and WebFlux are on the classpath, Boot normally still prefers Servlet MVC.

`spring-graphql-test` supplies `ExecutionGraphQlServiceTester` and `HttpGraphQlTester`; `spring-boot-starter-test` supplies JUnit Jupiter and Mockito. The Spring Boot BOM keeps versions synchronized; do not pin a different GraphQL Java or Spring Test line without need and compatibility proof.

### 6.3. Declaring the GraphQL schema

File **`src/main/resources/graphql/schema.graphqls`**:

```graphql
type Query {
    greeting(name: String!): String!
}
```

Spring Boot automatically discovers `*.graphqls`/`*.gqls` in `classpath:graphql/**/` (default configuration). `String!` after `name` means a required non-null argument. `String!` after the field means a non-null result; if the resolver returns null or throws without being handled into a value, GraphQL emits an error and applies **null propagation** per the schema, unlike standard HTTP 404/500.

### 6.4. Application and service

File **`src/main/java/com/example/graphql/GraphQlDemoApplication.java`**:

```java
package com.example.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlDemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/graphql/GreetingService.java`**:

```java
package com.example.graphql;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Business logic is intentionally simple to focus on GraphQL execution vs. HTTP transport. If a real service accesses a database or remote system, an execution test with `@MockitoBean` does not prove that integration.

### 6.5. Resolver with `@Controller` and `@QueryMapping`

File **`src/main/java/com/example/graphql/GreetingGraphQlController.java`**:

```java
package com.example.graphql;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingGraphQlController {
    private final GreetingService service;

    public GreetingGraphQlController(GreetingService service) {
        this.service = service;
    }

    @QueryMapping
    public String greeting(@Argument String name) {
        return service.greet(name);
    }
}
```

`@QueryMapping` is not HTTP `@GetMapping`; it maps the method to the `greeting` field on `Query` in the GraphQL schema. `@Argument` binds the GraphQL `name` argument. The HTTP endpoint **`/graphql`** is registered by the framework when both GraphQL and web starters are present; the controller does not define `@PostMapping("/graphql")`.

## 7. Test A: `@GraphQlTest` + `ExecutionGraphQlServiceTester`

File **`src/test/java/com/example/graphql/GreetingExecutionTest.java`**:

```java
package com.example.graphql;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.execution.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(GreetingGraphQlController.class)
class GreetingExecutionTest {
    @Autowired
    private ExecutionGraphQlService executionService;

    @MockitoBean
    private GreetingService greetingService;

    private ExecutionGraphQlServiceTester tester;

    @BeforeEach
    void createTester() {
        tester = ExecutionGraphQlServiceTester.create(executionService);
    }

    @Test
    void resolvesDataThroughGraphQlExecutionWithoutHttp() {
        when(greetingService.greet("Mai")).thenReturn("Hello, Mai!");

        tester.document("{ greeting(name: \"Mai\") }")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, Mai!");

        verify(greetingService).greet("Mai");
    }

    @Test
    void bindsVariablesAndResolvesSelectedField() {
        when(greetingService.greet("An")).thenReturn("Hello, An!");

        tester.document("""
                    query Greeting($who: String!) {
                        greeting(name: $who)
                    }
                    """)
                .variable("who", "An")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, An!");

        verify(greetingService).greet("An");
    }

    @Test
    void reportsGraphQlSchemaValidationError() {
        tester.document("{ fieldThatDoesNotExist }")
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());

        verifyNoInteractions(greetingService);
    }
}
```

**Explanation of results:**

- Tests 1 and 2 verify the schema, `@QueryMapping` resolver, argument binding, and GraphQL data field with a mocked collaborator. No HTTP client is involved.
- Test 3 sends a **schema-invalid GraphQL document**. GraphQL execution returns an `errors` list and has no reason to call the service. `.errors().satisfy(...)` asserts the error is present instead of letting the tester fail on an unexpected error.
- `@MockitoBean` is Spring Framework 6.2+'s bean override, fitting Boot 3.5. Services are not auto-scanned in the GraphQL slice, so the mock is intentional.
- The test **does not verify** `POST /graphql` routing, HTTP status 200/400, Content-Type, auth filters, or server ports.

If you just want the auto-configured tester without invoking the factory directly, `@GraphQlTest` also provides **`@Autowired GraphQlTester graphQlTester`**. This example intentionally autowires `ExecutionGraphQlService` and constructs `ExecutionGraphQlServiceTester` to highlight **which layer** the tester operates at.

## 8. Test B: `HttpGraphQlTester` in a MOCK web environment

File **`src/test/java/com/example/graphql/GreetingMockHttpTest.java`**:

```java
package com.example.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class GreetingMockHttpTest {
    @Autowired
    private HttpGraphQlTester tester;

    @Test
    void routesGraphQlDocumentThroughMockHttpTransport() {
        tester.document("{ greeting(name: \"Mai\") }")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, Mai!");
    }
}
```

This test loads the **full Spring Boot context** with the real service, web MVC setup, and framework-registered GraphQL endpoint; `@AutoConfigureHttpGraphQlTester` provides the HTTP-oriented tester. However, because of `WebEnvironment.MOCK`, requests still run **in-process**, with no embedded server listening on TCP.

Advantages over Test A: it verifies HTTP endpoint registration in the mock web stack and uses the **real service** instead of a mock. Remaining gap: it does not prove that a socket or embedded server binds successfully at runtime.

## 9. Test C: `HttpGraphQlTester` over a real HTTP server, with raw HTTP assertions

File **`src/test/java/com/example/graphql/GreetingRealHttpTest.java`**:

```java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingRealHttpTest {
    @Autowired
    private HttpGraphQlTester tester;

    @LocalServerPort
    private int port;

    @Test
    void graphQlTesterVerifiesDataOverRealHttpServer() {
        tester.document("""
                    query Greeting($who: String!) {
                        greeting(name: $who)
                    }
                    """)
                .variable("who", "Mai")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, Mai!");
    }

    @Test
    void webTestClientVerifiesHttpStatusHeadersAndGraphQlEnvelope() {
        WebTestClient rawHttp = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        rawHttp.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "query", "{ greeting(name: \"Mai\") }"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.data.greeting").isEqualTo("Hello, Mai!");
    }
}
```

The first test uses **`HttpGraphQlTester`**, auto-configured by Spring Boot against the `RANDOM_PORT` server, to assert GraphQL data. The second uses **raw `WebTestClient.bindToServer()`** with `@LocalServerPort` to explicitly verify **HTTP POST /graphql**, HTTP **200**, JSON response media type, and the `$.data.greeting` envelope. These provide complementary, non-conflicting evidence.

**Execution preconditions:** loopback networking permits binding a socket; test dependencies such as `WebTestClient`/reactor client are available. With no authentication or DB in this example, valid requests return 200. If a real app adds Spring Security, CSRF policies, gateways, or specific profiles, supply the matching auth/test setup instead of blindly copying an expected 200.

## 10. Running the example and reading results

The example has **6 `@Test` methods**: 3 execution tests + 1 mock HTTP + 2 real HTTP. With the Maven setup in section 6 and an environment allowing loopback sockets, the expected outcome is **6 tests passed, 0 failures**.

From the directory containing `pom.xml`, if Maven is installed:

```bash
mvn test
```

If the project includes the Maven Wrapper:

```bash
./mvnw test
```

Or run each boundary separately:

```bash
mvn -Dtest=GreetingExecutionTest test
mvn -Dtest=GreetingMockHttpTest test
mvn -Dtest=GreetingRealHttpTest test
```

On Windows, use `mvnw.cmd` when the wrapper is present, or `mvn` if Maven is installed. `@SpringBootTest(RANDOM_PORT)` starts an embedded HTTP server on a dynamic port, reducing port conflicts in CI.

`GreetingExecutionTest` is usually the lightest because it avoids starting a web context or server. `GreetingMockHttpTest` starts the full context without opening a socket. `GreetingRealHttpTest` starts the server and performs live HTTP calls. This is a **scoped test hierarchy**; do not force every test onto a real server just to feel "more integrated."

## 11. GraphQL errors vs. HTTP errors: assert both layers

A GraphQL response uses this envelope:

```json
{
  "data": {
    "greeting": "Hello, Mai!"
  }
}
```

When GraphQL execution encounters an error, the response can include `errors`:

```json
{
  "data": {
    "greeting": null
  },
  "errors": [
    {
      "message": "Example error",
      "path": ["greeting"]
    }
  ]
}
```

The JSON above only **illustrates partial-data structure**; with the example schema's `greeting: String!`, an error on a non-null field **propagates null up to `data: null`**, so do not use that partial-data snippet as a literal expected output for the hands-on lab.

**Do not conflate the two error layers:**

| Situation | GraphQL response | HTTP response |
|---|---|---|
| Valid query, resolver succeeds | Populated `data`, normally no `errors` | Normally **200** |
| Resolver throws, GraphQL execution produces response | May have partial/null `data` and `errors` | **Can still be 200**; not 500 by default |
| Document invalid against schema | Validation `errors`, `data` usually absent/null | May be **400** or another status depending on media type/spec/framework |
| Malformed HTTP JSON body or wrong Content-Type | May be rejected **before GraphQL execution** | HTTP **400/415** or matching policy |
| Missing HTTP authentication/authorization | Request may be rejected by security filter before resolver | HTTP **401/403** per policy |
| Missing `/graphql` route | No GraphQL response | HTTP **404** |

**Key point:** by default, `GraphQlTester` fails when a GraphQL response contains unexpected `errors`. To assert an expected error, use:

```java
tester.document("{ notARealField }")
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
```

This is a snippet inside a test with `tester` and AssertJ imported, as in Test A. To check a specific error, use `.errors().expect(predicate).verify()`, or `satisfy` to inspect `message`, `path`, and `extensions.classification` per your schema/error resolver.

However, **`GraphQlTester` is not a general-purpose tool for checking all raw HTTP statuses and headers**. When HTTP status itself is a requirement, use `WebTestClient` (as in Test C) or a real HTTP client. Never assert `path("greeting")` alone and conclude "the API returned 200 and the right Content-Type" without verifying HTTP.

## 12. Headers, security, interceptors, and GraphQL context

A real GraphQL API often uses `Authorization`, `X-Tenant`, locale, or correlation IDs. That data passes through HTTP filters/security and `WebGraphQlInterceptor`, and can then be placed into the **GraphQL context** for resolvers to read.

```text
HTTP header X-Tenant: shop-a
      |
      v
Security / Servlet or WebFlux filters
      |
      v
WebGraphQlInterceptor
      |
      v
GraphQL context / ExecutionInput
      |
      v
DataFetcher / @SchemaMapping
```

`ExecutionGraphQlServiceTester` skips the **beginning** of this pipeline. Injecting `graphQLContext` manually into `ExecutionInput` only proves the resolver uses the supplied context—**not** that the server reads the HTTP header and enforces tenant authorization.

`WebGraphQlTester` runs through `WebGraphQlHandler` and the interceptor chain with simulated headers. It fits testing `X-Tenant` → GraphQL context **without starting a web transport**, though it still skips HTTP filters, CORS, and sockets.

`HttpGraphQlTester` allows setting headers:

```java
HttpGraphQlTester tenantTester = tester.mutate()
        .headers(headers -> headers.set("X-Tenant", "shop-a"))
        .build();
```

This is a snippet in a class holding `HttpGraphQlTester tester`; builder methods depend on the Spring GraphQL version in use. When bound to mock HTTP, headers traverse the **mock web context**; when bound to a real server, they travel over a **real HTTP request**. When testing authentication, supply test-fixture credentials and assert access control; never embed production tokens or bypass security filters.

For CORS `OPTIONS` preflight, `Content-Type`, `Accept`, payload size limits, and proxy behavior, write **HTTP-focused tests**. GraphQL execution testers cannot prove those policies.

## 13. Do queries, mutations, and subscriptions share the same tester?

### Queries and mutations

Both the execution tester and HTTP tester use `.document(...).execute()` for queries and mutations. When a mutation returns data, inspect `path`/entity; if there is no `data` to check, use `executeAndVerify()` in Spring GraphQL's API to verify zero GraphQL errors.

**Transaction note:** with `@SpringBootTest(RANDOM_PORT)`, the test client and the server handling the mutation typically run on **different threads and transaction boundaries**. `@Transactional` on a test method **does not roll back** database commits made by the server-side request. Use a dedicated test DB and explicit cleanup/fixtures rather than `@DirtiesContext` as a substitute for data cleanup.

### Subscriptions and streaming

For subscriptions, GraphQL Java can return a Publisher; `ExecutionGraphQlServiceTester` and `WebGraphQlTester` support testing subscriptions directly with `executeSubscription()`. `WebSocketGraphQlTester` uses the WebSocket transport, making it right for testing sessions, connections, and GraphQL-over-WebSocket.

```java
Flux<String> events = executionTester
        .document("subscription { notifications }")
        .executeSubscription()
        .toFlux("notifications", String.class);

StepVerifier.create(events)
        .expectNext("one", "two")
        .thenCancel()
        .verify();
```

This is an **API snippet** assuming the schema defines subscription `notifications` and both `executionTester` and a publisher are available; it is not a standalone test. For standard request/response HTTP GraphQL, do not use `HttpGraphQlTester` by default for unbounded subscriptions. Some versions/transports support SSE, which requires an appropriate SSE reader and `Accept: text/event-stream`; if the WebSocket protocol is required, test against real WebSocket client and server configuration.

## 14. Choosing wisely in real-world projects

| Risk to catch | Recommended test |
|---|---|
| SDL `String!`, argument `name`, `@QueryMapping` bind properly | **`@GraphQlTest` + `ExecutionGraphQlServiceTester`** |
| Resolver and Spring GraphQL exception resolver produce proper `errors` | Execution tester in a context with the exception resolver |
| `X-Tenant` header transferred into context by GraphQL interceptor | **`WebGraphQlTester`**, or HTTP tester when full HTTP is needed |
| `POST /graphql` route/JSON body works without needing sockets | **`@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester`** |
| Security, HTTP status, cookies/headers in web stack | **`HttpGraphQlTester` + raw WebTestClient** in mock or full HTTP per goal |
| Real embedded server binds a port and accepts HTTP POST | **`@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester`** |
| DB queries, transactions, DataLoader, and multiple real services | Integration test with compatible test DB; minimal mocking |
| GraphQL subscriptions over WebSocket | **`WebSocketGraphQlTester`** with server and protocol config |
| CORS, TLS termination, gateway, deployment networking | HTTP/deployment-level tests in an environment containing those components |
| Pure Java service logic | Plain JUnit/Mockito, **no GraphQL tester needed** |

A practical strategy uses **many fast execution tests** for GraphQL schema and resolver cases, **several mock HTTP tests** for web integration, and **a few live HTTP tests** for critical paths. There is no universal fixed ratio; choose based on product risk.

## 15. Spring Boot / Spring GraphQL version differences

The example above pins **Spring Boot 3.5.0** to keep imports exact:

```java
// Spring Boot 3.5:
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;

// Spring for GraphQL test:
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
```

These are **illustrative import lines**, not a standalone Java file. `spring-graphql-test` is a dedicated test dependency. `spring-boot-starter-graphql` provides GraphQL service/schema support at runtime, yet **does not automatically turn an app without a web starter into an HTTP API**. Exposing over Servlet MVC requires a web starter, and testing HTTP clients requires matching test client dependencies on the classpath.

In **Spring Boot 4.x**, test modules and starters were split by technology—for example, **`spring-boot-graphql-test`**—and **auto-configuration annotation packages changed** compared to Boot 3.5. Spring GraphQL also evolves across releases; always check the Javadoc and dependency tree **for the exact version you are running** instead of copying Boot 3.5 imports into Boot 4 while only changing the `pom.xml` parent.

In Spring Boot 3.5, the GraphQL HTTP path property is **`spring.graphql.http.path`** (defaulting to `/graphql`). If you encounter `spring.graphql.path` in older Boot docs, do not assume it remains the primary property in 3.5/4.x. Execution tests are unaffected by changing the transport URL; live HTTP tests must match the configured path.

## 16. Common issues and diagnosis

| Symptom | Likely cause | Resolution |
|---|---|---|
| `ExecutionGraphQlServiceTester` passes but HTTP returns 404 | Schema/resolver is fine, but HTTP transport is unregistered or path changed | Check web starter, `spring.graphql.http.path`, and raw HTTP tests |
| GraphQL execution test fails to inject service | `@GraphQlTest` intentionally excludes `@Service` | `@MockitoBean` or `@Import` small dependency; full test if real service is needed |
| `HttpGraphQlTester` fails to inject | Missing `spring-graphql-test`, `WebTestClient` test dependency, or wrong auto-config mode | Check starter-graphql, web/webflux test classpath, and test annotations |
| `HttpGraphQlTester` passes without starting a real server | Tester is bound to a mock context | Use `RANDOM_PORT` and verify real port/HTTP traffic |
| HTTP returns 200 even though GraphQL query failed | GraphQL execution error in `errors`; HTTP status is not 500 by default | Check `.errors()` and raw response `errors` |
| `GraphQlTester.execute()` fails when expecting an error | Tester treats unexpected errors as failures by default | Use `.errors().expect(...)` or `.satisfy(...)` |
| Raw HTTP test gets 401/403 | Blocked by security filter or CSRF policy | Configure credentials/CSRF for context and test policy |
| Tenant header missing inside resolver | `WebGraphQlInterceptor` did not run or header wasn't propagated | Use `WebGraphQlTester` or HTTP tester, check interceptor |
| `@QueryMapping` exists but field cannot be queried | GraphQL SDL missing field, or type/name mismatch | Update `schema.graphqls`, assert validation error |
| Execution test passes, CORS preflight fails | Execution tester bypasses HTTP CORS layer | Test HTTP OPTIONS, origin, and allowed headers/methods |
| HTTP request JSON parser fails | Valid GraphQL document but wrong HTTP body or Content-Type | Verify POST body `{"query": "..."}`, Accept/Content-Type |
| Subscription test hangs | Stream never completes and lacks cancel/timeout | `StepVerifier.thenCancel()` and timeout; use appropriate subscription tester |
| Live mutation leaks data into next test | Server transaction differs from test transaction | Dedicated test DB, isolated cleanup/fixtures |
| Boot 4 compilation fails on tester annotations | Module/package paths changed | Match imports and dependencies to your Boot/Spring GraphQL release |

## 17. Pre-completion checklist

- [ ] Can I state whether a test proves **GraphQL execution, `WebGraphQlInterceptor`, or HTTP transport**?
- [ ] Do I avoid assuming the name `HttpGraphQlTester` guarantees a real socket?
- [ ] For resolver/schema logic, do I use `@GraphQlTest` and execution tester where appropriate?
- [ ] Do I remember `@GraphQlTest` does not auto-load regular services/repositories?
- [ ] Do I distinguish tests with mocked collaborators from tests with real services and DBs?
- [ ] When header → GraphQL context is required, have I tested `WebGraphQlInterceptor` or the HTTP layer rather than manually setting context on `ExecutionInput`?
- [ ] When HTTP status, headers, Content-Type, or routes matter, do I use raw HTTP client assertions?
- [ ] When a real socket/server is needed, do I use `RANDOM_PORT` without hardcoding ports?
- [ ] Do GraphQL `data` and `errors` both have contract assertions instead of inferring GraphQL errors from status?
- [ ] For non-null fields, do I understand null propagation on resolver failure?
- [ ] Are `*.graphqls` schemas present with field/argument names matching resolvers?
- [ ] Do subscriptions pick an appropriate tester/transport and include cancel/timeouts?
- [ ] Do I avoid expecting test-thread transactions to roll back server-committed HTTP mutations?
- [ ] Have I verified classpath/test modules, imports, and property names for the actual Spring Boot version?
- [ ] Did I run tests with the build tool and match conclusions to the **tested boundary** instead of merely seeing "Tests passed"?

**Conclusion:** **`ExecutionGraphQlServiceTester` proves GraphQL execution inside Spring, not HTTP.** `WebGraphQlTester` adds the web handler and interceptors; `HttpGraphQlTester` exercises HTTP transport **only as deeply as whether it is bound to a mock or a real server**. When the goal is GraphQL data and errors, `GraphQlTester` offers a uniform API; when the goal is HTTP status, headers, security, or networking, add assertions at the **corresponding HTTP layer**.

### Official documentation

- [Spring GraphQL — Testing: ExecutionGraphQlServiceTester, WebGraphQlTester, and HttpGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Spring GraphQL HTTP Transport and Schema](https://docs.spring.io/spring-boot/3.5/reference/web/spring-graphql.html)
- [Spring Boot 3.5 — Common Application Properties: `spring.graphql.http.path`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.x — Testing Spring GraphQL](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)