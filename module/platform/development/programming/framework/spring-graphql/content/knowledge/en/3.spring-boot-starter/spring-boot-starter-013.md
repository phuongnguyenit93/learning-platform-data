# Configuration with Application Properties

Spring Boot lets you configure Spring for GraphQL through properties prefixed with **spring.graphql**. Instead of writing Java configuration for every standard setting, an application can declare endpoints, schema locations, GraphiQL, WebSocket, RSocket, and CORS in **application.properties** or **application.yml**.

Spring Boot binds these properties into its auto-configuration. When the application starts, Boot uses the classpath and configuration values to create required components such as `GraphQlSource`, HTTP endpoints, and supported transport adapters. Property-based configuration lets you adjust behavior per deployment environment without editing code.

This lesson covers how configuration is organized, commonly used Spring GraphQL properties, writing settings in properties/YAML, profiles, environment variables, checking effective values, and the limits of declarative configuration.

## 1. Role of Application Properties

Spring Boot uses externalized configuration to read settings from multiple sources: properties/YAML files, environment variables, Java system properties, command-line arguments, and other property sources. Values are bound into configuration groups published by libraries or the application.

For Spring for GraphQL, most integration properties start with:

~~~text
spring.graphql
~~~

Example:

~~~properties
spring.graphql.path=/api/graphql
spring.graphql.graphiql.enabled=false
~~~

These two values change the HTTP endpoint and the enabled state of GraphiQL, respectively. Spring Boot reads the configuration when creating the application context, and auto-configuration then uses the bound values.

Properties fit settings that can be expressed as single values, lists, paths, or durations. Behavior requiring custom logic—such as resource-level authorization, custom scalar conversion, interface/union resolution, DataLoader, or business exception handling—typically requires Java beans, annotations, or dedicated configuration.

Not every property starting with **spring.graphql** is available in every Spring Boot version. Use configuration metadata and documentation for your project's exact Spring Boot version to verify names, data types, and default values.

## 2. Configuring the HTTP Endpoint

The most basic property is **spring.graphql.path**. The default value is usually **/graphql**. You can change the endpoint to match your application's URL conventions:

~~~properties
spring.graphql.path=/api/graphql
~~~

After changing it, clients send requests to the new path. Example:

~~~http
POST /api/graphql HTTP/1.1
Content-Type: application/json

{
  "query": "{ books { id title } }"
}
~~~

The GraphQL endpoint path should be distinguished from the web application's context path. For example, if Spring MVC has:

~~~properties
server.servlet.context-path=/catalog
spring.graphql.path=/api/graphql
~~~

The external URL will include both the context path and the GraphQL path:

~~~text
/catalog/api/graphql
~~~

With WebFlux, the application base path can be configured via WebFlux properties. When running behind a reverse proxy or API gateway, verify both the URL clients see and the URL the backend actually receives. Changing **spring.graphql.path** does not automatically update routes on proxies, firewalls, or gateways.

### Choosing the HTTP Runtime

Spring for GraphQL can integrate with Spring MVC or Spring WebFlux. Choosing the web stack depends primarily on dependencies and the application context type initialized by Spring Boot:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

If the application uses WebFlux, replace the Web MVC starter with the corresponding WebFlux starter:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

There is no **spring.graphql.mvc.enabled** or **spring.graphql.webflux.enabled** property to switch runtimes arbitrarily. The classpath and web application configuration determine which integration activates. Avoid adding both web starters unless your project has a clear reason, as doing so can make web application type selection less predictable.

## 3. Configuring Schema Locations and File Extensions

Spring Boot searches for SDL files on the classpath at the default location, typically:

~~~text
classpath:graphql/**/
~~~

Schema files typically use **.graphqls** or **.gqls** extensions. You can declare different locations using:

~~~properties
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Example resource layout:

~~~text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── book.graphqls
    ├── author.graphqls
    └── input/
        └── book-input.gqls
~~~

Spring GraphQL merges discovered schema definitions into one executable GraphQL schema. Hence, multiple files can define distinct types or extend an existing type using **extend type**. Every type must have a valid definition in the combined schema.

Multiple location patterns can be specified, depending on how your Spring Boot version's binder supports them:

~~~properties
spring.graphql.schema.locations=classpath:graphql/,classpath:shared-graphql/
~~~

If the application packages schemas inside a dependency JAR or across multiple modules, choose a location pattern capable of locating resources inside those artifacts. Do not assume relative filesystem paths from the working directory behave like classpath resources.

When schemas are not found, check:

1. Whether SDL files live under a resource directory packaged into the artifact.
2. Whether filenames use an extension included in the configured list.
3. Whether locations use the right prefix such as **classpath:** or required wildcards.
4. Whether any profile or environment variable overrides the default location.
5. Whether the schema has syntax errors or references undefined types.

## 4. Configuring with application.properties

Basic configuration example for a book management application:

~~~properties
spring.application.name=book-catalog

# GraphQL HTTP endpoint
spring.graphql.path=/api/graphql

# SDL schema
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls

# Enable GraphiQL only in development
spring.graphql.graphiql.enabled=false

# WebSocket transport for subscriptions
spring.graphql.websocket.path=/api/graphql
spring.graphql.websocket.connection-init-timeout=60s

# RSocket route if the application enables RSocket transport
spring.graphql.rsocket.mapping=graphql
~~~

Configuration groups can be separated by function. This helps readers immediately see which endpoints, schemas, and transports are active.

### Equivalent Configuration in application.yml

If the project uses YAML, the configuration can be written as:

~~~yaml
spring:
  application:
    name: book-catalog
  graphql:
    path: /api/graphql
    schema:
      locations: classpath:graphql/
      file-extensions:
        - .graphqls
        - .gqls
    graphiql:
      enabled: false
    websocket:
      path: /api/graphql
      connection-init-timeout: 60s
    rsocket:
      mapping: graphql
~~~

Both formats represent the same configuration. Use **application.properties** when the team prefers flat key-value pairs; use **application.yml** when configuration has nested hierarchies. Avoid declaring the same key across multiple files without understanding precedence rules, as the final effective value may differ from what readers expect.

## 5. Commonly Used Spring GraphQL Properties

The table below summarizes common property groups. Defaults may change across Spring Boot versions, so check the configuration metadata for your dependencies.

| Property | Purpose |
|---|---|
| **spring.graphql.path** | Path of the HTTP GraphQL endpoint |
| **spring.graphql.schema.locations** | Locations or patterns to search for schema files |
| **spring.graphql.schema.file-extensions** | SDL file extensions to scan |
| **spring.graphql.schema.printer.enabled** | Enables/disables Spring Boot schema printing support |
| **spring.graphql.graphiql.enabled** | Enables/disables the GraphiQL UI |
| **spring.graphql.graphiql.path** | Path serving the GraphiQL UI |
| **spring.graphql.websocket.path** | Path of the WebSocket endpoint |
| **spring.graphql.websocket.connection-init-timeout** | Timeout waiting for the WebSocket connection initialization message |
| **spring.graphql.rsocket.mapping** | Route/mapping for GraphQL over RSocket |
| **spring.graphql.cors.allowed-origins** | List of origins permitted for cross-origin access |
| **spring.graphql.cors.allowed-methods** | HTTP methods permitted via CORS |
| **spring.graphql.cors.allowed-headers** | Request headers permitted |
| **spring.graphql.cors.allow-credentials** | Whether credentials may be sent over CORS |
| **spring.graphql.cors.max-age** | Cache duration for CORS preflight responses |

Not all groups take effect unless the corresponding transport is on the classpath or activated. For instance, setting **spring.graphql.websocket.path** does not automatically add the WebSocket runtime dependency to your application.

## 6. Enabling GraphiQL for Development

GraphiQL is a browser UI for writing and sending GraphQL operations, inspecting results, and exploring the schema. It can be enabled with:

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
~~~

When enabled, developers can open the configured path to test Queries, Mutations, and variables. GraphiQL is helpful while learning, developing, and debugging an API.

Do not enable developer UIs by default in production environments. This tool can expose schema details or invite users to run unwanted operations. If production needs operational tooling, lock down access with security policies and enable only what is necessary.

Example split configuration:

**application-dev.properties**

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
~~~

**application-prod.properties**

~~~properties
spring.graphql.graphiql.enabled=false
~~~

GraphiQL is a developer tool. Enabling GraphiQL does not replace GraphQL field authorization, nor does it configure CORS for your frontend.

## 7. Configuring WebSocket and Subscriptions

If the application needs subscriptions over WebSocket, you can declare:

~~~properties
spring.graphql.websocket.path=/api/graphql
spring.graphql.websocket.connection-init-timeout=60s
~~~

The WebSocket path is configured independently from **spring.graphql.path**. If you want HTTP and WebSocket to share a path, set both to the same value. Sharing a path does not mean they share the same transport mechanism: HTTP sends request-response exchanges, while WebSocket performs a handshake and exchanges messages over a long-lived connection.

**connection-init-timeout** limits how long the server waits for the protocol's connection initialization message. This is a connection-setup timeout, not the maximum lifetime of an active subscription. Subscriptions require their own timeout, concurrency limit, cleanup, and reconnection policies.

For WebSocket to work, the application needs the WebSocket dependency matching its Spring MVC or WebFlux stack. Reverse proxies must also forward upgrade headers and keep connections alive long enough. When configuration fails to work, check dependencies, paths, proxies, and the protocol used by clients.

## 8. Configuring RSocket

Spring for GraphQL can serve GraphQL over RSocket if the application has RSocket integration and a compatible runtime. The mapping property defines the route used:

~~~properties
spring.graphql.rsocket.mapping=graphql
~~~

Clients send GraphQL payloads to the matching route using an interaction model supported by the server. Request-response normally suits Queries or Mutations; request-stream suits continuously emitted results.

RSocket is not merely a different way to specify an HTTP URL. It has its own protocol, routes, metadata, and interaction models. During deployment, verify RSocket server/client dependencies, security metadata, serialization, gateways, and observability tools. If an application only needs a request-response API for browsers, HTTP is usually simpler; if it needs web subscriptions, WebSocket is the more familiar choice.

Setting **spring.graphql.rsocket.mapping** does not automatically create routes in an API gateway or service mesh. External infrastructure still must be configured to route traffic to the right RSocket server.

## 9. Configuring CORS for the Frontend

CORS controls whether a browser allows a web page from one origin to call resources on another origin. If frontend and backend run on different origins, configure allowed origins, methods, and headers accordingly.

Example allowing only a development frontend origin:

~~~properties
spring.graphql.cors.allowed-origins=http://localhost:3000
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
spring.graphql.cors.allow-credentials=false
spring.graphql.cors.max-age=30m
~~~

When deploying to production, replace the local origin with the actual domain:

~~~properties
spring.graphql.cors.allowed-origins=https://app.example.com
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
spring.graphql.cors.allow-credentials=true
~~~

When credentials are enabled, do not use the wildcard origin **\***. Declare explicit origins or constrained origin patterns per your application's requirements. CORS is neither authentication nor authorization; it is a browser policy governing JavaScript access to responses. Non-browser clients can still invoke the endpoint without server-side protection.

If the application already configures CORS in Spring Security or an API gateway, ensure the layers do not conflict. GraphQL endpoint CORS settings do not necessarily replace the entire application's CORS policy.

## 10. Profiles and Environment-Specific Configuration

An application typically has local, test, staging, and production environments. Avoid editing the same file before every deployment. Spring Boot supports profile-specific configuration.

**application.properties** holds shared settings:

~~~properties
spring.application.name=book-catalog
spring.graphql.path=/api/graphql
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

**application-dev.properties**:

~~~properties
spring.graphql.graphiql.enabled=true
spring.graphql.graphiql.path=/graphiql
spring.graphql.websocket.path=/api/graphql
~~~

**application-prod.properties**:

~~~properties
spring.graphql.graphiql.enabled=false
spring.graphql.websocket.path=/api/graphql
spring.graphql.cors.allowed-origins=https://app.example.com
spring.graphql.cors.allowed-methods=GET,POST
spring.graphql.cors.allowed-headers=Authorization,Content-Type
~~~

Activate a profile via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=dev
~~~

Or pass it when launching the application:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Profiles let you keep one codebase while varying settings by environment. Security, origins, GraphiQL, and endpoint settings should be reviewed when switching profiles. Never place passwords, private keys, or access tokens in committed configuration files; use a secret manager or environment variables managed by the deployment platform.

## 11. Overriding via Environment Variables and Command Line

In containers or cloud platforms, configuration is often passed through environment variables. Spring Boot supports relaxed binding to map property names to environment variable names.

Examples:

| Property | Environment variable |
|---|---|
| **spring.graphql.path** | **SPRING_GRAPHQL_PATH** |
| **spring.graphql.websocket.path** | **SPRING_GRAPHQL_WEBSOCKET_PATH** |
| **spring.graphql.graphiql.enabled** | **SPRING_GRAPHQL_GRAPHIQL_ENABLED** |
| **spring.graphql.schema.locations** | **SPRING_GRAPHQL_SCHEMA_LOCATIONS** |
| **spring.graphql.websocket.connection-init-timeout** | **SPRING_GRAPHQL_WEBSOCKET_CONNECTIONINITTIMEOUT** |

Spring Boot's rule for converting environment variable names replaces dots with underscores, removes hyphens, and uppercases the result. Hence, hyphenated words in a property name are not necessarily separated by underscores in the environment variable.

Example in PowerShell:

~~~powershell
$env:SPRING_GRAPHQL_PATH = "/api/graphql"
$env:SPRING_GRAPHQL_GRAPHIQL_ENABLED = "false"
java -jar app.jar
~~~

You can override via command-line arguments:

~~~bash
java -jar app.jar --spring.graphql.path=/internal/graphql
~~~

When the same property appears in multiple sources, Spring Boot applies externalized configuration precedence rules. Values from command-line arguments or system environment variables can override values in configuration files. When an application runs on the wrong endpoint, check config files, active profiles, environment variables, and command-line arguments.

## 12. Configuring Lists and Durations

Several properties accept lists, such as schema locations, file extensions, allowed origins, and allowed methods. In **application.properties**, lists are typically comma-separated:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.cors.allowed-methods=GET,POST
~~~

In YAML, they can be written as sequences:

~~~yaml
spring:
  graphql:
    schema:
      file-extensions:
        - .graphqls
        - .gqls
    cors:
      allowed-methods:
        - GET
        - POST
~~~

Duration properties can specify explicit units:

~~~properties
spring.graphql.websocket.connection-init-timeout=60s
~~~

Including units such as **ms**, **s**, or **m** makes the intended value clear and prevents mistaking bare integers for milliseconds versus seconds. Avoid setting an overly long timeout to mask connectivity problems; treat handshake timeout, operation processing time, and subscription lifetime as separate policies.

## 13. Properties Do Not Replace Java Configuration

Application properties only control options published by Spring Boot. Many Spring for GraphQL behaviors require runtime logic or Java components.

| Requirement | Typically Appropriate Approach |
|---|---|
| Change the HTTP endpoint | **spring.graphql.path** |
| Select SDL locations | **spring.graphql.schema.locations** |
| Enable GraphiQL | **spring.graphql.graphiql.enabled** |
| Choose the WebSocket path | **spring.graphql.websocket.path** |
| Basic CORS setup | **spring.graphql.cors.*** |
| Map Query/Mutation/fields | Annotated controllers such as **@QueryMapping**, **@SchemaMapping** |
| Batch data loading to reduce N+1 | **@BatchMapping** or DataLoader |
| Custom scalar conversion | GraphQL scalar/coercing and runtime wiring |
| Concrete type resolution for interfaces/unions | TypeResolver/runtime wiring |
| Standardize business errors | DataFetcherExceptionResolver |
| Field/resource authorization | Spring Security and permission checks in services/resolvers |
| Add instrumentation | GraphQL Java Instrumentation or matching integration |

For example, there is no global property to automatically turn every relationship field into a batch resolver. You must design a batch loader or use **@BatchMapping** with appropriate Java logic. Likewise, enabling CORS does not create per-field authorization policies.

When you need to change auto-configuration behavior, inspect which beans Spring Boot creates and which extension points Spring for GraphQL provides. Only define custom beans when a specific requirement calls for it; a replacement bean can cause part of default auto-configuration to back off.

## 14. Verifying Effective Configuration

When a property does not behave as expected, check in order:

1. **Property name:** are spelling, prefix, and hierarchy accurate?
2. **Version:** does the property exist in the application's Spring Boot version?
3. **Profile:** is the expected profile active?
4. **Override sources:** do environment variables, system properties, or command-line args override the file?
5. **Classpath:** are dependencies for MVC, WebFlux, WebSocket, or RSocket present?
6. **Resources:** are SDL files packaged and matched by the location pattern?
7. **External infrastructure:** do reverse proxies, gateways, and CORS policies match the endpoint?
8. **Auto-configuration:** does a custom bean alter auto-configuration conditions?

Spring Boot Actuator can help inspect the environment and registered beans if the application integrates and properly secures management endpoints. Never expose full environment or configuration endpoints to untrusted users, as they can leak sensitive information.

IDEs with Spring Boot configuration metadata support can autocomplete property names, data types, and descriptions. This is a reliable way to verify property names against your actual dependencies. When configuration fails to bind, inspect startup logs and warnings about unrecognized properties rather than silently assuming values took effect.

## 15. Complete Configuration Example Across Two Environments

A practical setup can keep shared settings in `application.yml`:

~~~yaml
spring:
  application:
    name: book-catalog
  graphql:
    path: /api/graphql
    schema:
      locations: classpath:graphql/
      file-extensions:
        - .graphqls
        - .gqls
    websocket:
      path: /api/graphql
      connection-init-timeout: 60s
~~~

In `application-dev.yml`:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: true
      path: /graphiql
    cors:
      allowed-origins:
        - http://localhost:3000
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Authorization
        - Content-Type
~~~

In `application-prod.yml`:

~~~yaml
spring:
  graphql:
    graphiql:
      enabled: false
    cors:
      allowed-origins:
        - https://app.example.com
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Authorization
        - Content-Type
      allow-credentials: true
~~~

In production configurations with credentials, origins must be specified explicitly. Secrets used for authentication remain managed via a secret store or deployment environment rather than committed into repository configuration examples.

## 16. Common Configuration Issues

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Calling **/graphql** returns 404 after changing path | Client or proxy still calls the old path | Check **spring.graphql.path**, context path, and gateway |
| Schema fails to load | Location or file extension mismatch | Check **spring.graphql.schema.locations** and resources in the artifact |
| GraphiQL cannot be opened | Disabled or wrong path | Check **spring.graphql.graphiql.enabled** and path |
| WebSocket handshake fails | Missing dependency, wrong path, or proxy fails to upgrade | Check web stack, **spring.graphql.websocket.path**, and proxy |
| Subscription disconnects early | Timeout or connection limits on proxy/server | Check connection timeout, idle timeout, and cleanup |
| Frontend reports CORS error | Origin, method, or header not allowed | Check **spring.graphql.cors.*** and Security/gateway policies |
| Property exists in file but has no effect | Wrong version, typo, or overridden by another source | Check metadata, active profile, environment, and command line |
| RSocket route does not receive requests | Missing RSocket runtime or route mismatch | Check dependencies, mapping, and server/gateway settings |

## 17. Workflow for Configuring a New Application

When starting a new Spring for GraphQL service, follow this sequence:

1. Choose the MVC or WebFlux web stack and add the appropriate starter.
2. Place SDL schemas under the default resource location or declare custom locations.
3. Set the HTTP endpoint via **spring.graphql.path** if changing the default convention.
4. Enable GraphiQL only in development or controlled environments.
5. If Subscriptions are needed, add WebSocket support and configure path and timeouts.
6. If RSocket communication is needed, configure the RSocket runtime, mapping, and metadata.
7. Configure CORS for actual frontend origins.
8. Separate profiles and secrets by deployment environment.
9. Verify property binding, schema loading, endpoints, and transports with appropriate tests.
10. Review custom beans to ensure they do not unintentionally replace needed auto-configuration.

Application properties let Spring Boot adjust common Spring for GraphQL settings cleanly and consistently. Once you understand which properties belong to schemas, endpoints, transports, or environments, developers can handle most operational adjustments without cluttering resolver logic. Requirements involving business logic or custom runtime behavior should still be implemented through Spring for GraphQL and GraphQL Java extension points.
