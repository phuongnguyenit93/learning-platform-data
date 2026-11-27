# GraphQL HTTP Endpoint

Spring for GraphQL provides an HTTP endpoint for clients to send a GraphQL operation to the server and receive the execution result as JSON. When using Spring Boot, `spring-boot-starter-graphql` auto-configures the GraphQL integration; the application also needs a web starter to run an HTTP server.

By default, the endpoint path is `/graphql`. Operations such as queries and mutations all go through this endpoint. Java methods annotated with `@QueryMapping` or `@MutationMapping` handle fields in the GraphQL schema; they do not create separate HTTP URLs by themselves.

## 1. HTTP Processing Flow

A GraphQL request goes through the following main steps:

```mermaid
flowchart LR
    A[GraphQL client] -->|HTTP request| B[/graphql endpoint]
    B --> C[Spring for GraphQL]
    C --> D[GraphQL schema and resolvers]
    D --> E[GraphQL result]
    E -->|JSON response| A
```

The HTTP handler receives the request, passing the GraphQL document along with variables to the engine for validation and execution against the schema. Spring for GraphQL controllers supply data for the requested fields. The returned result contains `data`, `errors`, or both.

The endpoint is the HTTP communication boundary for GraphQL. The schema and resolvers determine what data clients can request; the `/graphql` path determines where clients send requests.

## 2. Adding Dependencies for Spring Boot

With Maven, add the GraphQL starter and a web starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <!-- Use Spring MVC to serve HTTP -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

If the application uses the reactive stack, you can replace `spring-boot-starter-web` with `spring-boot-starter-webflux`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

With Gradle, the corresponding dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Choose the web starter according to your application's architecture. Spring Boot uses that web stack to create the HTTP server and register the GraphQL handler. Let Spring Boot dependency management control Spring library versions compatible with the Boot version in use.

## 3. Creating a Minimal Schema and Resolver

Spring Boot looks for GraphQL schemas in `src/main/resources/graphql/` by default. Create `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    greeting(name: String!): String!
}
```

The schema declares a `greeting` field, which accepts a `name` argument and returns a non-null string. Next, create a controller to handle that field:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingController {

    @QueryMapping
    public String greeting(@Argument("name") String name) {
        return "Hello, " + name + "!";
    }
}
```

`@QueryMapping` maps the method to the `greeting` field of the root `Query` type. `@Argument` extracts the argument with the same name from the GraphQL request. When the application starts, Spring Boot loads the schema and registers the controller through auto-configuration and component scanning.

This example uses a query to illustrate the path from an HTTP request to a resolver. Mutations are also sent to the same HTTP endpoint; mutation resolvers are typically declared with `@MutationMapping` and corresponding fields in the schema's `type Mutation`.

## 4. Configuring the Endpoint Path

Without explicit configuration, Spring Boot uses `/graphql`. You can change the path in `src/main/resources/application.properties`:

```properties
spring.graphql.path=/api/graphql
```

After this change, clients send requests to `/api/graphql`. Update URLs in clients, reverse proxies, and security configurations accordingly. If the application also has a servlet context path or is deployed under another base path, the external URL may include that prefix as well.

Spring Boot can also enable the GraphiQL UI for testing queries in the browser:

```properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
```

GraphiQL is a development tool, not a GraphQL execution endpoint replacing `/graphql`. Only enable this UI in environments where it is needed, and restrict access if deployed to shared environments.

Several commonly used properties:

| Property | Meaning |
| --- | --- |
| `spring.graphql.path` | HTTP path that receives GraphQL requests; defaults to `/graphql`. |
| `spring.graphql.schema.locations` | Locations to search for schemas; defaults to `classpath:graphql/**/`. |
| `spring.graphql.graphiql.enabled` | Enables or disables the GraphiQL UI; disabled by default. |
| `spring.graphql.graphiql.path` | Path where the GraphiQL UI is served when enabled. |

You only need to declare these properties when overriding defaults or making environment-specific profile settings explicit.

## 5. Sending GraphQL Requests over HTTP

GraphQL HTTP requests are typically sent via `POST` with a JSON body. The body can contain the fields:

- `query`: the GraphQL document to execute.
- `variables`: an object containing values for variables in the document.
- `operationName`: the name of the operation to select when the document contains multiple operations.
- `extensions`: extension metadata depending on the client and server.

Example calling the default endpoint with `curl`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "query Greeting($name: String!) { greeting(name: $name) }",
    "variables": { "name": "An" },
    "operationName": "Greeting"
  }'
```

With the schema and controller above, the response looks like:

```json
{
  "data": {
    "greeting": "Hello, An!"
  }
}
```

`Content-Type` describes the format of the body sent to the server. `Accept` indicates which response format the client expects. In this example, both the request body and response use JSON.

HTTP GET can also be used for queries when both client and server support passing parameters via URL. Mutations must not be sent via GET; use POST for mutations. For sensitive data or long variables, POST is generally preferable because GET parameters appear in the URL and can end up in access logs or browser history.

## 6. Distinguishing HTTP Errors from GraphQL Errors

Not every error when calling GraphQL means the HTTP endpoint is down. Examine both the HTTP status and the response body:

- Errors at the HTTP or request transport layer, such as invalid JSON or an unsupported method, may be answered with an HTTP error status code.
- GraphQL syntax errors, validation errors, or errors thrown during resolver execution are represented in the `errors` field of the GraphQL response.
- A response can contain both `data` and `errors` if some fields execute successfully while another field fails.

Example response structure when a field encounters an error:

```json
{
  "data": {
    "greeting": null
  },
  "errors": [
    {
      "message": "Unable to process request",
      "path": ["greeting"]
    }
  ]
}
```

This is an illustrative structural example, not a fixed Spring error message. The exact HTTP status code depends on the error type, HTTP handler, and application configuration. Therefore, clients should inspect `data` and `errors` rather than checking only the status code.

## 7. Testing the HTTP Endpoint

A test that only invokes a resolver or the GraphQL execution engine does not verify that the HTTP endpoint is registered properly. To test both the path and the transport, you can start the application on a random port and use `HttpGraphQlTester`.

Add the Spring GraphQL test library if the project does not already include it:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

Example test with Spring Boot:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphqlHttpEndpointTest {

    @Value("${local.server.port}")
    int port;

    @Test
    void queryCanBeExecutedOverHttp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        HttpGraphQlTester tester = HttpGraphQlTester.create(webTestClient);

        tester.document("query Greeting($name: String!) { greeting(name: $name) }")
                .variable("name", "An")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, An!");
    }
}
```

This test sends an HTTP request to the port started by Spring Boot, then asserts the returned value at path `data.greeting`. If you only want to test the schema and resolvers without testing the HTTP transport, you can use execution-level GraphQL testing tools; the two types of tests answer different questions.

## 8. Resolving Common Configuration Issues

| Symptom | What to Check |
| --- | --- |
| Receiving `404 Not Found` | Does the URL match `spring.graphql.path`, the port, context path, and application base path? |
| Receiving `405 Method Not Allowed` | Is the client using an HTTP method supported by the endpoint? Mutations must use POST. |
| Request rejected before reaching GraphQL | Check JSON syntax, `Content-Type`, CORS settings, and Spring Security. |
| Response contains `errors` | Check field names, argument types, schema definitions, and resolver errors. |
| Application fails to start | Check schema syntax, schema file location, dependencies, and auto-configuration logs. |
| Cannot open GraphiQL | Check `spring.graphql.graphiql.enabled` and the configured GraphiQL path. |

When Spring Security is enabled, protect `/graphql` according to the application's authentication and authorization mechanisms. For applications using sessions and CSRF protection, POST requests from browsers must include a valid CSRF token. CORS should also be configured for the origins actually allowed to access the API. Do not disable security protections just to make a test request succeed.

## 9. Checklist When Exposing the Endpoint

1. Include `spring-boot-starter-graphql` and the appropriate web starter.
2. Place schemas in the resource location scanned by Spring Boot.
3. Ensure controllers and resolvers are detected by component scanning.
4. Have clients call the right GraphQL path, which defaults to `/graphql`.
5. Send requests with a valid GraphQL document, variables, and HTTP headers.
6. Handle both `data` and `errors` in client responses.
7. Protect the endpoint with authentication, authorization, and CORS suited to the deployment environment.

Once these points are in place, your Spring Boot application can accept GraphQL operations over HTTP. Aspects such as schema design, `@BatchMapping`, DataLoader, and resolver error handling continue to determine the API's execution quality, while the HTTP endpoint handles delivering client requests into Spring for GraphQL.
