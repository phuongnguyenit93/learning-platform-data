# Config Class, Args Mapping, and Input Configuration Validation

## 1. The Problem: A Custom GatewayFilter Needs a Configuration Contract

**Spring Cloud Gateway Server WebFlux** receives a request, uses route predicates to find a matching route, executes the filter chain, optionally transforms the path/headers, discovers instances via `lb://service-id`, and proxies the request to a microservice. When built-in filters do not satisfy a custom policy, we can write a **custom GatewayFilterFactory**.

For example, a team wants to attach a per-route trace tag to requests received by the backend:

~~~http
X-Lab-Tag: catalog_v1
~~~

Instead of hardcoding it across multiple routes, we configure:

~~~yaml
filters:
  - name: AuditLabel
    args:
      headerName: X-Lab-Tag
      label: catalog_v1
      overwrite: true
      maxLabelLength: 32
~~~

The problem is not just adding a header. Gateway must know how to convert `args` from YAML into a **strongly typed Config class**, handle default values, and **reject invalid configuration before the filter processes traffic**. Otherwise, a typo or wrong boolean default could silently alter routing/security behavior without anyone noticing.

This lesson belongs to the **Custom Filters** chapter of the **SPRING_CLOUD_GATEWAY** module. The techniques here apply when developing an API Gateway using route predicates, filter chains, path/header transformations, service discovery, and authentication, rate limiting, circuit breaker, retry, TLS, and observability features. However, this exercise focuses on **Config, args mapping, and validation**, rather than turning an illustrative header into an authentication mechanism.

Objectives:

1. Write `AbstractGatewayFilterFactory<Config>` with the right name, type, and Spring registration.
2. Map configurations in both `name/args` form and positional shortcut form.
3. Use typed fields, defaults, Jakarta Bean Validation, and cross-property rules.
4. Distinguish parse/binding errors, validation errors, route resolution errors, and request runtime errors.
5. Test valid configs, missing fields, wrong types, dangerous values, and route refresh.

> **Scope:** This lesson targets **Gateway Server WebFlux**, not Gateway Server MVC. The two variants have different APIs for registering custom filters. Choose a Spring Boot/Spring Cloud BOM and starter compatible with your runtime version.

## 2. Journey of a Config Object

A route definition contains a filter name and an argument map:

~~~yaml
- id: catalog-api
  uri: http://localhost:9091
  predicates:
    - Path=/api/catalog/**
  filters:
    - name: AuditLabel
      args:
        headerName: X-Lab-Tag
        label: catalog_v1
        overwrite: true
~~~

Conceptual flow:

~~~mermaid
flowchart TD
    Y["YAML/RouteDefinition<br/>filters name + args"] --> F["Find GatewayFilterFactory<br/>name = AuditLabel"]
    F --> B["Binding/Conversion<br/>args → Config"]
    B --> V["Validate fields and<br/>cross-property rules"]
    V --> A["factory.apply(config)<br/>creates GatewayFilter"]
    A --> R["Runtime route"]
    R --> Q["Request matches route"]
    Q --> H["filter(exchange, chain)<br/>transforms request"]
    H --> D["Send downstream"]
~~~

These are **two distinct phases**:

- **Configuration/route materialization:** find the factory bean, bind args, validate, and call `apply(config)`.
- **Runtime:** execute `GatewayFilter.filter(exchange, chain)` on each HTTP request that matches the route.

Some versions/route sources materialize routes **lazily**, for example when subscribing to the route stream or on refresh. Therefore, you should not promise that every bad configuration will certainly crash the JVM at startup. The deployment pipeline must **force verification of loaded routes and run smoke tests**, rather than relying solely on the process staying alive.

| Component | Role |
| --- | --- |
| `GatewayFilterFactory<C>` | Contract for creating a filter from config |
| `AbstractGatewayFilterFactory<C>` | Convenient base class for WebFlux factories |
| `Config` | Object holding route parameters after binding |
| `shortcutFieldOrder()` | Defines field names/order for shortcuts |
| `GatewayFilter` | Reactive function processing request/response |
| `RouteDefinition` and `FilterDefinition` | Route/filter data from YAML or another source |
| `RouteDefinitionRouteLocator` | Converts route definitions into runtime routes |
| `GlobalFilter` | Filter applied Gateway-wide, unlike per-route factories |

### Naming Convention and Bean Registration

Standard class name:

~~~java
AuditLabelGatewayFilterFactory
~~~

Name used in YAML:

~~~yaml
name: AuditLabel
~~~

The custom class must be a **Spring bean**, e.g. annotated with `@Component` or returned by a `@Bean` method, and reside in a component-scanned package. Spring Cloud Gateway recommends ending the class name with **`GatewayFilterFactory`**. Do not rely on class name variants missing that suffix, as they are not a long-term supported convention.

## 3. Designing a Typed and Constrained Config Class

We use four properties:

| Field | Java Type | Required? | Rules |
| --- | --- | --- | --- |
| `headerName` | `String` | Yes | Only headers starting with `X-`, safe characters |
| `label` | `String` | Yes | Short token containing only letters, digits, dots, underscores/hyphens |
| `overwrite` | `Boolean` | Yes | `true` uses set, `false` uses append |
| `maxLabelLength` | `Integer` | Default 32 | Within [1,64], label length must not exceed this limit |

**Why `Boolean` instead of `boolean`?** For a required boolean, `Boolean` distinguishes **missing** (`null`) from `false`. With a primitive, a missing value silently becomes `false` and bypasses some checks.

**Why not put everything in a `Map<String,Object>`?** Typed Config clarifies the contract, supports conversion/validation, and catches errors early. An untyped map should only be used for genuinely dynamic data with its own controlled schema.

### Does Validation Run Automatically?

In Spring Boot 3+/4+, Bean Validation uses the **`jakarta.validation.*`** namespace. Annotations like `@NotBlank`, `@Pattern`, `@Min`, `@Max`, and `@NotNull` describe constraints. However, **do not simply put `@Validated` on Config and assume every GatewayFilterFactory binding path automatically runs validation like `@ConfigurationProperties`**.

This lesson uses an explicitly testable approach: inject `jakarta.validation.Validator` and call `validator.validate(config)` **inside `apply(config)`** before creating the GatewayFilter. In addition, validate **cross-field** constraints, such as `label.length() <= maxLabelLength`.

## 4. Complete `AuditLabelGatewayFilterFactory` Implementation

Add a Bean Validation provider to the Gateway WebFlux project; for example, with Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

The application must also have the Gateway WebFlux starter and a compatible Spring Cloud BOM. Gateway 4.3.x/5.x provides the dedicated WebFlux starter `spring-cloud-starter-gateway-server-webflux`; many older 4.2.x releases use `spring-cloud-starter-gateway`. Do not add the Servlet MVC starter when using the WebFlux filter API.

Create `src/main/java/demo/gateway/filters/AuditLabelGatewayFilterFactory.java`:

~~~java
package demo.gateway.filters;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;

@Component
public class AuditLabelGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
                AuditLabelGatewayFilterFactory.Config> {

    private final Validator validator;

    public AuditLabelGatewayFilterFactory(Validator validator) {
        super(Config.class);
        this.validator = validator;
    }

    // AuditLabel=X-Lab-Tag,catalog_v1,true
    @Override
    public List<String> shortcutFieldOrder() {
        return List.of("headerName", "label", "overwrite");
    }

    @Override
    public GatewayFilter apply(Config config) {
        validateConfig(config);

        // Immutable snapshot of validated configuration.
        final String headerName = config.getHeaderName();
        final String label = config.getLabel();
        final boolean overwrite = config.getOverwrite();

        return (exchange, chain) -> {
            ServerHttpRequest request = exchange.getRequest()
                    .mutate()
                    .headers(headers -> {
                        if (overwrite) {
                            headers.set(headerName, label);
                        } else {
                            headers.add(headerName, label);
                        }
                    })
                    .build();

            return chain.filter(
                    exchange.mutate().request(request).build());
        };
    }

    private void validateConfig(Config config) {
        if (config == null) {
            throw new IllegalArgumentException(
                    "AuditLabel config must not be null");
        }

        Set<ConstraintViolation<Config>> violations =
                validator.validate(config);
        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(
                    "Invalid AuditLabel filter configuration",
                    violations);
        }

        // Cross-property rule, after @NotNull/@NotBlank.
        if (config.getLabel().length() > config.getMaxLabelLength()) {
            throw new IllegalArgumentException(
                    "AuditLabel label exceeds maxLabelLength");
        }
    }

    public static class Config {
        @NotBlank
        @Pattern(regexp = "X-[A-Za-z0-9-]{1,60}")
        private String headerName;

        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9._-]{1,64}")
        private String label;

        @NotNull
        private Boolean overwrite;

        @NotNull
        @Min(1)
        @Max(64)
        private Integer maxLabelLength = 32;

        public String getHeaderName() {
            return headerName;
        }
        public void setHeaderName(String headerName) {
            this.headerName = headerName;
        }

        public String getLabel() {
            return label;
        }
        public void setLabel(String label) {
            this.label = label;
        }

        public Boolean getOverwrite() {
            return overwrite;
        }
        public void setOverwrite(Boolean overwrite) {
            this.overwrite = overwrite;
        }

        public Integer getMaxLabelLength() {
            return maxLabelLength;
        }
        public void setMaxLabelLength(Integer maxLabelLength) {
            this.maxLabelLength = maxLabelLength;
        }
    }
}
~~~

### Reviewing the Design Decisions in the Code

1. `super(Config.class)` declares the binding type the factory accepts.
2. `@Component` ensures Spring creates the filter bean; the class is in a scanned package.
3. `Config` has an implicit no-arg constructor and **public getters/setters**.
4. `shortcutFieldOrder()` lists **exactly three fields** accepted from the shortcut string; the fourth field keeps its default when omitted.
5. `validator.validate(config)` **actually executes** the validation annotations, rather than relying on an unclear automatic mechanism.
6. After annotations guarantee non-null values, the code checks `label.length() <= maxLabelLength`.
7. Config is read **once in `apply(config)`**, with values copied into final local variables before creating the lambda. Never put request-specific state into Config.
8. The filter creates a mutated `ServerHttpRequest` and passes the new request via `exchange.mutate().request(...).build()`.
9. `headers.set` **replaces** the old value; `headers.add` **appends** another value, which can produce repeated headers.
10. Do not call `block()` on the Netty event-loop or unnecessarily modify the request body.

### Why Validate Before the Lambda?

`Config` belongs to the **route definition**, not data that changes per request. Moving validation into the lambda wastes validation overhead on every request and delays surfacing config errors until traffic arrives. Validating in `apply(config)` allows the route to be evaluated as soon as it is converted from definition to runtime filter. If route definitions are refreshed, the new config goes through this bind/validate step again.

## 5. Two Ways to Map Args

### 5.1. Fully Expanded: Explicit Field Names

~~~yaml
filters:
  - name: AuditLabel
    args:
      headerName: X-Lab-Tag
      label: catalog_v1
      overwrite: true
      maxLabelLength: 32
~~~

Meaning:

~~~text
args.headerName      → Config.setHeaderName("X-Lab-Tag")
args.label           → Config.setLabel("catalog_v1")
args.overwrite       → Config.setOverwrite(Boolean.TRUE)
args.maxLabelLength  → Config.setMaxLabelLength(32)
~~~

The binder converts YAML values to the matching Java types. If `overwrite: not_boolean` cannot be converted to `Boolean`, that is a **binding/type conversion error**, which can occur before reaching the validator in our example code.

When a config has many fields, booleans, lists, long strings, or values containing commas, **prefer full `name/args`** because it is easier to review and inspect.

### 5.2. Shortcut: Order-Dependent

In the factory:

~~~java
return List.of("headerName", "label", "overwrite");
~~~

Corresponds to:

~~~yaml
filters:
  - AuditLabel=X-Lab-Tag,catalog_v1,true
~~~

| Position | Field name | Value received from shortcut | Type after binding |
| ---: | --- | --- | --- |
| 1 | `headerName` | `X-Lab-Tag` | String |
| 2 | `label` | `catalog_v1` | String |
| 3 | `overwrite` | `true` | Boolean |

`maxLabelLength` is not in the shortcut list, so it remains the default 32. Shortcut syntax works well for short values that do not contain commas and are strictly documented.

~~~yaml
# CORRECT
- AuditLabel=X-Lab-Tag,catalog_v1,true

# WRONG: swapped order, last value cannot convert to boolean
- AuditLabel=X-Lab-Tag,true,catalog_v1

# WRONG: missing overwrite, validation must catch null
- AuditLabel=X-Lab-Tag,catalog_v1
~~~

Do not use shortcut syntax for free-form strings containing commas or nested structures without verifying the parser rules of your Gateway version. Gateway also offers `ShortcutConfigurable.shortcutType()` for other argument forms, but this lesson's factory **only needs the default shortcut**.

## 6. Route Configuration by Gateway Server WebFlux Version

Gateway runs on `localhost:8080`, echo backend on `localhost:9091`; the `/api/demo/**` route uses the custom filter and strips the `api` prefix.

### Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: custom-filter-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: demo-audit-label
              uri: http://localhost:9091
              predicates:
                - Path=/api/demo/**
                - Method=GET
              filters:
                - name: AuditLabel
                  args:
                    headerName: X-Lab-Tag
                    label: gateway_v1
                    overwrite: true
                    maxLabelLength: 32
                - StripPrefix=1
~~~

### Gateway Server WebFlux 4.2.x / 4.3.x

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: demo-audit-label
          uri: http://localhost:9091
          predicates:
            - Path=/api/demo/**
            - Method=GET
          filters:
            - AuditLabel=X-Lab-Tag,gateway_v1,true
            - StripPrefix=1
~~~

**Only use the routes namespace for the version you are running.** Gateway 4.3.x still supports route definitions under `spring.cloud.gateway.routes` in 4.3 documentation; Gateway 5.x uses `spring.cloud.gateway.server.webflux.routes`. Do not infer all other property names solely from the route namespace, especially properties that change across major upgrades.

### Expected Result

Client sends:

~~~http
GET /api/demo/echo HTTP/1.1
Host: localhost:8080
X-Lab-Tag: client_supplied
~~~

Gateway selects the route, `AuditLabel` uses `overwrite=true` to replace the value with `gateway_v1`, and then `StripPrefix=1` turns the backend path into `/demo/echo`.

In this example, the custom filter **does not read the body**, does not cache the body, and does not create new requests per downstream attempt beyond the header transformation requirement. Do not treat a header-adding filter as a security token validator.

## 7. Hands-On Echo Backend: Verifying That Config Actually Works

Create a standalone Spring Boot WebFlux application with `spring-boot-starter-webflux` on port 9091:

~~~yaml
# Backend application.yml
server:
  port: 9091
~~~

Main class `src/main/java/demo/echo/EchoApplication.java`:

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/echo/EchoController.java`:

~~~java
package demo.echo;

import java.util.List;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/demo/echo")
    public Map<String, Object> echo(ServerHttpRequest request) {
        List<String> tags =
                request.getHeaders()
                        .getOrDefault("X-Lab-Tag", List.of());
        return Map.of(
                "path", request.getPath().value(),
                "tags", tags);
    }
}
~~~

This backend is **strictly for lab use**. Never expose an echo endpoint that returns tokens, cookies, identity data, or sensitive bodies in production.

Open two terminals in the two separate projects (backend and Gateway), and run with Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can use `mvnw.cmd spring-boot:run`. The examples only describe how to practice on your own; this guide **does not claim to have executed builds/tests in the repository environment**.

### 7.1. Testing the First Request

~~~bash
curl -i "http://localhost:8080/api/demo/echo"
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"path":"/demo/echo","tags":["gateway_v1"]}
~~~

This demonstrates that:

1. Route `demo-audit-label` was loaded and the `Path/Method` predicates matched.
2. Factory `AuditLabelGatewayFilterFactory` was resolved by name `AuditLabel`.
3. Config was bound and `apply(config)` returned a GatewayFilter.
4. `StripPrefix=1` converted the public path to the backend path.

### 7.2. Testing Overwrite of a Client-Supplied Header

~~~bash
curl -i "http://localhost:8080/api/demo/echo" \
  -H "X-Lab-Tag: client_supplied"
~~~

With `overwrite=true`, the backend must still receive `gateway_v1`, not `client_supplied`.

If switched to `overwrite=false`, the backend can receive **two values**: the client-sent value and the Gateway-added value. This is only an example showing the difference between `headers.set` and `headers.add`; **never use append for identity or permission headers that the backend will trust**.

### 7.3. Switching to Shortcut Syntax

Change the filter definition to:

~~~yaml
filters:
  - AuditLabel=X-Lab-Tag,short_v2,true
  - StripPrefix=1
~~~

Reload routes or restart Gateway according to your version's workflow. Call the GET endpoint again; the tag value is expected to change to `short_v2`. If the backend still sees `gateway_v1`, check whether Gateway **refreshed routes** or whether the request hit another replica using old config.

### 7.4. Distinguishing Route Mismatch from Config Errors

~~~bash
# Route only matches GET
curl -i -X POST "http://localhost:8080/api/demo/echo"

# Path outside predicate
curl -i "http://localhost:8080/other/echo"
~~~

When no other matching route/handler exists, the response may be 404. **This does not prove the custom factory config is wrong**: an unmatched route does not run its GatewayFilter.

## 8. Misconfiguration: Binding Error or Validation Error?

### 8.1. Missing Required Field

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: gateway_v1
    # Missing overwrite
~~~

In code, `overwrite` is a `Boolean` without a default value; `@NotNull` catches the missing field when `validator.validate(config)` runs. If primitive `boolean` were used, a missing value could become `false` and evade this check.

### 8.2. Wrong Data Type

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: gateway_v1
    overwrite: not_boolean
~~~

When the binder cannot convert that string to `Boolean`, configuration can fail **before reaching Bean Validation**. Therefore, catching only `ConstraintViolationException` is not enough to cover every config error.

### 8.3. Policy-Invalid Values

~~~yaml
# Disallowed in this example
headerName: Authorization

# Does not match label pattern
label: "text with spaces"

# Out of allowed range
maxLabelLength: 999
~~~

These trigger `@Pattern`, `@Pattern`, and `@Max` errors respectively. For a production Gateway, maintain an allowlist for created/modified headers to avoid accidentally overwriting `Authorization`, `Cookie`, `Host`, or forwarded headers.

### 8.4. Cross-Field Constraint

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: very_long_label
    overwrite: true
    maxLabelLength: 5
~~~

Each field can have the right type and be individually valid, yet `label.length() > maxLabelLength`. The manual check in `validateConfig()` prevents creating a route with an invalid combination.

### 8.5. Typo in Args Key Name

~~~yaml
args:
  headerName: X-Lab-Tag
  label: gateway_v1
  overwite: true  # Misspelled overwrite
~~~

Depending on the binder/version, unknown keys may be rejected or silently ignored. In this example, if the key is ignored, `overwrite` remains null and violates `@NotNull`.

**Do not assume every unknown arg always causes an error.** For security-sensitive config, validate key names via schema/CI and real binding tests rather than relying on framework defaults.

## 9. Automated Testing for Config and GatewayFilterFactory

### 9.1. Unit Testing Without Booting the Whole Gateway

With JUnit Jupiter, AssertJ, and a Jakarta Bean Validation provider:

~~~java
package demo.gateway.filters;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AuditLabelConfigTest {

    private static final ValidatorFactory VALIDATORS =
            Validation.buildDefaultValidatorFactory();

    private final Validator validator = VALIDATORS.getValidator();
    private final AuditLabelGatewayFilterFactory factory =
            new AuditLabelGatewayFilterFactory(validator);

    private AuditLabelGatewayFilterFactory.Config validConfig() {
        var c = new AuditLabelGatewayFilterFactory.Config();
        c.setHeaderName("X-Lab-Tag");
        c.setLabel("gateway_v1");
        c.setOverwrite(true);
        return c;
    }

    @Test
    void rejectMissingOverwrite() {
        var c = validConfig();
        c.setOverwrite(null);

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(
                        jakarta.validation.ConstraintViolationException.class);
    }

    @Test
    void rejectSensitiveHeader() {
        var c = validConfig();
        c.setHeaderName("Authorization");

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(
                        jakarta.validation.ConstraintViolationException.class);
    }

    @Test
    void rejectCrossFieldMismatch() {
        var c = validConfig();
        c.setMaxLabelLength(3);

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("maxLabelLength");
    }

    @AfterAll
    static void closeValidatorFactory() {
        VALIDATORS.close();
    }
}
~~~

This test suite actually invokes `factory.apply(config)` to prove **validation executes**, rather than merely checking that annotations exist. You should add tests for valid values and label formatting, while remembering that unit tests **do not verify that YAML is mapped correctly by the Gateway binder**.

### 9.2. Integration Tests Must Exercise the Real Binding Path

With `@SpringBootTest`, `WebTestClient`, and a backend stub/WireMock, verify:

1. Full `name/args` config is read and the backend receives the header.
2. Shortcut accepts the right order and boolean conversion.
3. Invalid boolean fails in the binding/conversion phase.
4. Missing/invalid fields are rejected by validation.
5. An unregistered factory produces a **GatewayFilterFactory not found** error.
6. No route silently drops a mandatory filter when a definition is malformed.
7. Route refresh also re-validates the new Config.

If the framework materializes routes lazily, tests must **trigger route definition resolution** or send an appropriate request; simply asserting that the ApplicationContext starts is not enough.

### 9.3. Negative Test Matrix

| Input | Expected outcome |
| --- | --- |
| Valid full args | Filter created, correct header |
| Valid shortcut | Equivalent behavior |
| Missing `headerName` | Validation error |
| Missing `label` | Validation error |
| Missing `overwrite` | Validation error |
| `overwrite: abc` | Binding/conversion error |
| `headerName: Authorization` | Validation error |
| `label: "a b"` | Validation error |
| `maxLabelLength: 0` or 65 | Validation error |
| Label longer than maxLabelLength | Cross-field validation error |
| Typo `overwite` | Filter must not run with a wrong fallback |
| Factory not scanned | Name resolution error |
| Request does not match `Path/Method` | Filter does not run |

Do not turn all of these errors into HTTP 400. These are **system configuration errors** that should normally block deployment/route publication; they are not per-request caller errors.

## 10. Defaults, Enums, Lists, and Nested Config

### 10.1. Only Use Intentional Defaults

~~~java
private Integer maxLabelLength = 32;
~~~

Optional fields can have useful defaults. However, for security-relevant fields such as `authRequired` or `failOpen`, a dangerous default can turn a typo into **open access**. Require explicit declaration or choose a fail-safe default and verify the logic.

### 10.2. Enums Instead of Free-Form Strings

If a filter supports two modes:

~~~java
public enum WriteMode {
    OVERWRITE,
    APPEND
}
~~~

Using `WriteMode mode` helps the binder/validator reject values outside the allowed set. However, enum checks **do not replace** checking which modes are permitted on a given route.

### 10.3. List and Nested Object Configurations

When there are multiple rules, declare `List<T>` or typed nested Config classes:

~~~yaml
# Hypothetical schema example; no CustomPolicyGatewayFilterFactory exists yet
- name: CustomPolicy
  args:
    enabled: true
    allowedMethods:
      - GET
      - POST
    limits:
      maxBodyBytes: 131072
      timeoutMillis: 500
~~~

To use this, you must implement the actual factory/Config, binding, and **per-element** validation. Comma-separated shortcut syntax is not suitable for complex configs. For `Duration`/`DataSize` fields, define explicit units and validate ranges, overflows, and negative values.

### 10.4. Do Not Put Secrets in Args

Route definitions can be logged, exposed via Actuator routes, stored in Config Server, or appear in CI pipelines. **Never put private keys, bearer tokens, or client secrets** in `filters[].args`. If a factory needs credentials, use a secret manager / injected bean and avoid printing sensitive data in `toString()` or validation exceptions.

## 11. Config Is Not the Place to Store Per-Request State

The factory is typically a Spring singleton, and a filter created from Config can process **multiple concurrent requests**. Never use `Config` to store a user's counter, body content, or request ID:

~~~java
// WRONG: illustrates flawed thinking, not usable code in apply()
config.setLabel(requestIdOfCurrentUser);
~~~

If requests A and B mutate the same Config object, they can overwrite each other's data and leak state. For per-request data, use local variables inside the filter, `ServerWebExchange.getAttributes()`, or Reactor Context where appropriate. For distributed state like quotas, use a dedicated store with clear concurrency semantics.

In this lesson's factory, `headerName/label/overwrite` are captured after validation; every request only reads those values. If Config changes from a remote route source, you must **materialize a new filter** and follow a refresh/rollback procedure rather than mutating the active instance.

## 12. Filter Order, Retry, and Security Considerations

### 12.1. Route Order vs. Filter Order

A route's `order` determines which route wins when multiple predicates match. `GatewayFilter` and `GlobalFilter` instances are combined and sorted by order in a single filter chain. When explicit ordering is needed, consider `OrderedGatewayFilter`, while understanding Gateway's pre/post phases.

Do not set an arbitrary order and assume a custom filter replaces **Spring Security WebFilter**: that is a separate security layer requiring its own policy.

### 12.2. Retry Can Cause a Filter to Run Multiple Times

Under Retry mechanics, filters **within the retried portion of the chain** may execute again when the backend fails. If a custom filter writes audit logs, deducts quota, or emits a message on every attempt, a single client request can trigger repeated side effects.

With `AuditLabel`, `overwrite=true` uses `headers.set`, keeping the marker single-valued and less prone to duplication. `overwrite=false` uses `headers.add`, which can produce repeated headers if multiple filters/attempts append values. Always test behavior alongside Retry, circuit breakers, and request-mutating filters.

### 12.3. Custom Headers Are Not Proof of Identity

Never accept a client-sent `X-Authenticated-User` header and forward it downstream as an authentication credential. If Gateway needs to propagate identity, it must **verify the JWT/session first**, strip forged client headers, and use a proper trust boundary/secure channel to the backend. The `X-Lab-Tag` header in this lesson is **strictly for observability**.

## 13. Troubleshooting Filter Configuration

| Symptom | Common cause | How to inspect |
| --- | --- | --- |
| Factory `AuditLabel` not found | Missing `@Component`, wrong package scan, wrong class name | Check beans and filter name |
| Shortcut fails, full args work | Wrong order in `shortcutFieldOrder()` | Compare positional mapping |
| Invalid boolean, route inactive | Binding/conversion error | Route materialization logs |
| `ConstraintViolationException` | NotBlank/Pattern/NotNull/Min/Max violation | Fix config at source |
| `IllegalArgumentException` max length | Cross-property constraint | Compare label and maxLabelLength |
| Backend does not receive header | Route mismatch, filter not loaded, proxy strips header | Check route ID, downstream request |
| Backend sees multiple values | `overwrite=false` or another filter adds the same header | Test set/append, Retry order |
| Unintended routes affected | Using GlobalFilter/default-filters | Check filter scope |
| Error only appears on refresh | New config unvalidated or lazy route loading | Validate in CI and check after refresh |
| Startup shows no errors, no routes | Wrong YAML namespace or route source | Check runtime routes and version config |

If using Spring Boot Actuator to inspect runtime routes/filters, **never expose management endpoints publicly on the Internet**. Logs should include route ID, factory name, and configuration error type; never log raw args containing secrets.

### Controlling Configuration Rollouts

A deployment workflow might look like:

1. Validate YAML syntax and args schema/key names.
2. Unit test `Config`, Bean Validation, and cross-field rules.
3. Integration test the binder with both full and shortcut forms.
4. Materialize route definitions in staging.
5. Smoke test HTTP requests through the live filter.
6. Publish/roll out only after passing; if remote config supports refresh, prepare rollback.

Never silently drop a security filter when a route definition is malformed. In some versions, a route can disappear or throw at lookup time while the JVM process remains alive; operations must detect this via readiness checks and route audits rather than relying solely on JVM liveness.

## 14. Production Checklist

- [ ] Factory class has the `GatewayFilterFactory` suffix and is a Spring bean in component scan.
- [ ] Extends `AbstractGatewayFilterFactory<Config>` with `super(Config.class)`.
- [ ] Typed Config with public getters/setters; no untyped Map unless genuinely required.
- [ ] Required fields have no dangerous defaults; required booleans can use `Boolean + @NotNull`.
- [ ] Empty strings, lengths, valid characters, and numeric min/max bounds are validated.
- [ ] `Validator.validate(config)` is called **explicitly**, plus cross-field checks.
- [ ] Full args are clear; shortcuts have accurate `shortcutFieldOrder()` and are tested.
- [ ] Verified that fields do not accept wrong types/typos across binder version changes.
- [ ] Unit tests and integration tests actually materialize routes.
- [ ] Arbitrary config cannot overwrite auth/cookie/host/forwarded headers.
- [ ] No secrets in route args/logs/Actuator.
- [ ] Config is immutable on the request path; custom filter never blocks the reactive event loop.
- [ ] Filter order, Retry, concurrent requests, and final responses are tested.
- [ ] Refresh/rollback, route auditing, and protected management endpoints are in place.
- [ ] Gateway Server WebFlux 4.x/5.x namespaces are not mixed up with Server MVC.

## 15. Self-Check Questions

**1. Why use `Boolean overwrite` instead of `boolean overwrite`?**

So `null` represents a missing value, allowing `@NotNull` to catch the error; a primitive boolean defaulting to `false` could hide a typo.

**2. When using `AuditLabel=X-Lab-Tag,v1,true`, how does Gateway know which field `v1` maps to?**

From the second position in `shortcutFieldOrder()`, which corresponds to `label`.

**3. Does simply adding `@Validated` to Config guarantee validation runs across every binding path?**

You should not assume so. The example calls `validator.validate(config)` inside `apply(config)` to validate when building the filter.

**4. Why can `label` match its pattern and `maxLabelLength` be within range yet still be rejected?**

Because of the **cross-property** rule: label length must not exceed `maxLabelLength`.

**5. Why is successful application startup not enough to prove every route Config is valid?**

Route definition conversion can happen lazily or on refresh. You must materialize routes and run smoke tests.

**6. Why should Config never store a per-user request ID?**

Because a filter can handle multiple concurrent requests using the same Config; mutating it creates race conditions and state leaks.

## 16. References

1. [Spring Cloud Gateway Server WebFlux — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/developer-guide.html): custom `GatewayFilterFactory`, `AbstractGatewayFilterFactory`, and naming convention.
2. [Gateway WebFlux 4.3 — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/developer-guide.html): reference for the 4.3 release line.
3. [Gateway WebFlux — Configuring Route Predicate and Filter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): shortcut and fully expanded args.
4. [Gateway WebFlux 4.3 — Filter Factory Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): 4.3 route syntax.
5. [Spring Blog — Creating a Custom Spring Cloud Gateway Filter](https://spring.io/blog/2022/08/26/creating-a-custom-spring-cloud-gateway-filter/): `shortcutFieldOrder()` and request mutation.
6. [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Validator and Spring integration.
7. [Spring Cloud Gateway — Global Filters and Ordering](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): filter ordering and pre/post phases.

**Takeaway:** In a WebFlux custom GatewayFilterFactory, **`Config` is the contract between YAML routes and Java**, `shortcutFieldOrder()` is the positional contract for shortcuts, and `apply(config)` is the right place to **validate config before building the filter**. Use clear data types, intentional defaults, explicit validation, and tests for both valid and invalid YAML. A high-quality custom filter does not just work with good configs—it also **refuses to run silently with dangerous configs**.
