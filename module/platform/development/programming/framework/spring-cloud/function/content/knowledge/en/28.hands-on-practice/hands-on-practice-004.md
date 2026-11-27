# Header-Based Routing with an Allowlist of Permitted Functions

## 1. Practice Problem

In **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), business logic is registered as `Supplier`, `Function`, or `Consumer` beans and managed by `FunctionCatalog`. Thanks to adapters, the same function can be invoked over HTTP, event-driven systems, or serverless environments. When an application offers multiple capabilities but wants to expose **a single entry point**, you can use **RoutingFunction** to select the target function on a per-message basis.

Suppose a platform receives multiple text types from partner systems. The same endpoint/message input must support three operations:

| Route Key | Target Function | Operation |
| --- | --- | --- |
| `normalize` | `normalizeText` | Collapse whitespace and convert to uppercase |
| `reverse` | `reverseText` | Reverse the string |
| `mask` | `maskDigits` | Replace digits with `*` |

The producer sends a payload and an application-defined header:

~~~text
route-key: normalize
~~~

Payload:

~~~text
  Spring   Cloud Function 101
~~~

Result:

~~~text
SPRING CLOUD FUNCTION 101
~~~

**Security requirement:** producers may choose only one of the three published route keys. Producers must not be allowed to send arbitrary bean names, arbitrary composition strings, or SpEL expressions for the application to execute.

We will build an **allowlist** mapping route keys to fixed function names:

~~~text
route-key from message
        |
        v
Allowlisted MessageRoutingCallback
        |
        +-- normalize --> normalizeText
        |
        +-- reverse ---> reverseText
        |
        +-- mask ------> maskDigits
        |
        +-- any other value --> reject
~~~

Key highlights of this lesson:

1. Use the built-in `functionRouter` registered in `FunctionCatalog`.
2. Read the `route-key` header via `MessageRoutingCallback`.
3. Return only function definitions present in the server-side allowlist.
4. Test valid routing, missing headers, unknown headers, and attempts to override with standard routing headers.
5. Understand the difference between per-message routing and whole-stream reactive routing.
6. Recognize the allowlist's boundary: it constrains **which targets the router may pick**, and does not replace authentication/authorization or adapter configuration that exposes only the router.

## 2. RoutingFunction and Routing Mechanisms

Spring Cloud Function registers a router named `functionRouter` in `FunctionCatalog`. This router can be looked up like a function and accepts messages to decide the target function.

~~~java
Function<Object, Object> router =
        functionCatalog.lookup("functionRouter");
~~~

When the router receives a `Message<?>`, the routing destination can be determined by:

- `spring.cloud.function.definition`: a function name or a composition such as `foo|bar`.
- `spring.cloud.function.routing-expression`: a SpEL expression returning a function definition.
- `MessageRoutingCallback`: a strategy bean that programmatically resolves the function definition.

### 2.1. Precedence When Multiple Mechanisms Are Present

For imperative functions, the Spring Cloud Function documentation specifies the precedence order:

| Priority | Mechanism | Meaning |
| ---: | --- | --- |
| 1 | `MessageRoutingCallback` | Application-registered strategy callback |
| 2 | Message headers | `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` |
| 3 | Application properties | Application-level routing configuration |

**When a `MessageRoutingCallback` is present, it takes precedence over routing headers and application properties** for per-message routing. This is crucial for enforcing an allowlist: the callback returns only bean names mapped in server code.

### 2.2. Why Not Use a Function Name Directly from the Header?

A concise but dangerous approach is:

~~~java
// Do not use this approach for headers controlled by external producers.
return (String) message.getHeaders()
        .get("function-name");
~~~

If a producer sends `reverseText`, `internalMaintenance`, or `normalizeText|someOtherFunction`, the router receives that string as a function definition. As long as the catalog contains a matching function, the producer can invoke functions the application never intended to expose through this entry point.

Similarly, `spring.cloud.function.routing-expression` accepts a SpEL expression. Spring Cloud Function restricts the evaluation context for expressions arriving via message headers using `SimpleEvaluationContext`, yet **that is no reason to let clients supply expressions**. Accept a simple route key instead and map it against a fixed list.

### 2.3. Route Keys Differ from Bean Names

In this lab:

~~~text
Header: route-key = normalize
Server map: normalize -> normalizeText
Router returns: normalizeText
~~~

The producer only knows the business key `normalize`. The bean name `normalizeText` is a server-side implementation detail. You can change the implementation or bean name without requiring producers to send a new Java name.

## 3. Scope of Per-Message Routing

Header-based routing only fits when the unit of work is **a single message**. With an imperative signature such as:

~~~java
Function<String, String>
~~~

the framework can accept a `Message<?>`, read its headers, and select a function for that specific message.

With a reactive function such as:

~~~java
Function<Flux<String>, Flux<String>>
~~~

Spring Cloud Function invokes the function to wire up the pipeline for **the entire publisher**. At that point, per-item headers cannot route individual elements independently as with imperative functions. For reactive functions, routing instructions must come from application properties and apply to the stream as a single unit of work.

**This lab uses imperative functions** `Function<String,String>` so we can verify that individual messages can route to different targets.

## 4. Preparing the Maven Project

The lab uses **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0**, and **Spring Cloud 2025.0.0**. This is a compatible reference pair; for new projects, choose supported patches within the same release train and verify the version matrix rather than mixing independent versions.

Create the directory `header-routing-lab`:

~~~text
header-routing-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingLabApplication.java
    │   │   ├── TextFunctions.java
    │   │   └── AllowlistedRoutingConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/routing/
            ├── TextFunctionsTest.java
            └── FunctionRouterAllowlistTest.java
~~~

All classes use package `com.example.routing`. We do not need Kafka, RabbitMQ, an HTTP server, or cloud services for the core tests—only the Spring context and `FunctionCatalog`.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>header-routing-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>header-routing-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
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

Core dependencies:

| Artifact | Role |
| --- | --- |
| `spring-boot-starter` | Spring application context and auto-configuration |
| `spring-cloud-function-context` | `FunctionCatalog`, `RoutingFunction`, and routing callback |
| `spring-boot-starter-test` | JUnit 5, Spring Boot Test, and assertions |

You do not need `spring-cloud-function-web` or Spring Cloud Stream for the catalog tests. We will discuss adding adapters in the extension sections later.

## 5. Declaring the Three Target Functions

Create `TextFunctions.java`:

~~~java
package com.example.routing;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeText() {
        return input -> input.strip()
                .replaceAll("\\s+", " ")
                .toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> reverseText() {
        return input -> new StringBuilder(input)
                .reverse()
                .toString();
    }

    @Bean
    public Function<String, String> maskDigits() {
        return input -> input.replaceAll("\\d", "*");
    }
}
~~~

All three beans share the `Function<String,String>` signature. That keeps the routing demo focused on **target selection** rather than handling multiple different input schemas.

| Function Bean | Input | Output |
| --- | --- | --- |
| `normalizeText` | `"  Spring   Cloud "` | `"SPRING CLOUD"` |
| `reverseText` | `"abc 123"` | `"321 cba"` |
| `maskDigits` | `"order 123"` | `"order ***"` |

In real applications, each function can have different input/output types if converters and adapters are configured properly. However, every route must guarantee that the payload can be converted into the type expected by the target function.

## 6. Creating an Allowlist from the route-key Header

Create `AllowlistedRoutingConfiguration.java`:

~~~java
package com.example.routing;

import java.util.Locale;
import java.util.Map;

import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration(proxyBeanMethods = false)
public class AllowlistedRoutingConfiguration {

    private static final String ROUTE_HEADER = "route-key";

    private static final Map<String, String> ALLOWED_ROUTES = Map.of(
            "normalize", "normalizeText",
            "reverse", "reverseText",
            "mask", "maskDigits");

    @Bean
    public MessageRoutingCallback allowlistedMessageRoutingCallback() {
        return new MessageRoutingCallback() {

            @Override
            public String routingResult(Message<?> message) {
                Object rawValue =
                        message.getHeaders().get(ROUTE_HEADER);

                if (!(rawValue instanceof String routeKey)) {
                    throw new IllegalArgumentException(
                            "Missing or invalid route-key header");
                }

                String normalizedKey = routeKey
                        .trim()
                        .toLowerCase(Locale.ROOT);

                String functionDefinition =
                        ALLOWED_ROUTES.get(normalizedKey);

                if (functionDefinition == null) {
                    throw new IllegalArgumentException(
                            "Route is not allowed");
                }

                return functionDefinition;
            }
        };
    }
}
~~~

### 6.1. Analyzing the Callback

**Step 1 — read the application-defined header**

~~~java
Object rawValue = message.getHeaders().get("route-key");
~~~

`route-key` is a custom header defined for this lab, not a standard Spring Cloud Function routing header. It carries only the business key that producers are permitted to send.

**Step 2 — validate the data type**

~~~java
if (!(rawValue instanceof String routeKey)) {
    throw new IllegalArgumentException(...);
}
~~~

If the header is missing or not a string, the callback rejects the message. Do not blindly convert an arbitrary object into a function name.

**Step 3 — normalize the alias**

~~~java
String normalizedKey = routeKey.trim().toLowerCase(Locale.ROOT);
~~~

Normalization lets `" NORMALIZE "` resolve to `"normalize"`. It does not alter the allowlist or turn an arbitrary string into a valid function.

**Step 4 — map only through a fixed Map**

~~~java
String functionDefinition = ALLOWED_ROUTES.get(normalizedKey);
~~~

The returned value is always one of the three server-defined function names. Headers cannot inject `|` characters to construct compositions or specify arbitrary bean names.

**Step 5 — reject any alias outside the list**

~~~java
if (functionDefinition == null) {
    throw new IllegalArgumentException("Route is not allowed");
}
~~~

The callback does not return `null` to silently fall back to a default function. An invalid route must be surfaced as an explicit error for the adapter/binder to handle according to application policy.

### 6.2. Why Use MessageRoutingCallback?

Spring Cloud Function automatically detects a `MessageRoutingCallback` bean, and `RoutingFunction` uses it to resolve the function definition. The callback has **higher priority** than routing headers and application properties for imperative routing.

Therefore, even if a message contains:

~~~text
spring.cloud.function.definition: reverseText
spring.cloud.function.routing-expression: 'reverseText'
route-key: normalize
~~~

the callback still selects `normalizeText` based on `route-key`. Standard routing headers cannot override the allowlist decision.

### 6.3. Keep SpEL Out of the Allowlist

Do not write:

~~~java
// Do not use producer-supplied expressions to pick functions.
return (String) message.getHeaders()
        .get("spring.cloud.function.routing-expression");
~~~

And do not write:

~~~java
// Do not allow arbitrary function names from headers.
return (String) message.getHeaders()
        .get("spring.cloud.function.definition");
~~~

Both approaches hand function selection directly to the producer. If the application needs dynamic routing, parse a **finite route key** and map it to fixed bean names as shown in the example.

## 7. Application Startup and Configuration

Create `RoutingLabApplication.java`:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RoutingLabApplication.class, args);
    }
}
~~~

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: header-routing-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Do not set `spring.cloud.function.definition` to a fixed target function, because the goal is to route each message through `functionRouter`. Also do not configure `spring.cloud.function.routing-expression` as a default expression; the callback resolves the target via the allowlist.

`single-function-fallback-enabled: false` disables fallback lookup of an arbitrary name when the catalog contains only one function. Even in a multi-bean lab, this setting keeps lookup behavior transparent.

### 7.1. functionRouter Is Not a Bean We Write Ourselves

Spring Cloud Function pre-registers `RoutingFunction` in `FunctionCatalog` under the name `functionRouter`. We do not need to write a new `@Bean Function<Object,Object> functionRouter()` method to perform routing.

The beans we write consist solely of:

- `normalizeText`
- `reverseText`
- `maskDigits`
- `allowlistedMessageRoutingCallback`

When executing, look up `functionRouter` from the catalog.

## 8. Unit Testing the Target Functions

Create `TextFunctionsTest.java`:

~~~java
package com.example.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.function.Function;

import org.junit.jupiter.api.Test;

class TextFunctionsTest {

    private final TextFunctions functions = new TextFunctions();

    @Test
    void normalizesText() {
        Function<String, String> normalize =
                functions.normalizeText();

        assertEquals(
                "SPRING CLOUD FUNCTION",
                normalize.apply("  Spring   Cloud Function  "));
    }

    @Test
    void reversesText() {
        Function<String, String> reverse =
                functions.reverseText();

        assertEquals("321 cba", reverse.apply("abc 123"));
    }

    @Test
    void masksDigits() {
        Function<String, String> mask =
                functions.maskDigits();

        assertEquals("order ***", mask.apply("order 123"));
    }
}
~~~

This unit test only verifies each target function individually. It does not start Spring, build `FunctionCatalog`, or prove header routing works.

## 9. Testing Routing Through FunctionCatalog

Create `FunctionRouterAllowlistTest.java`:

~~~java
package com.example.routing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.function.context.MessageRoutingCallback;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(
        classes = RoutingLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FunctionRouterAllowlistTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private MessageRoutingCallback routingCallback;

    private Message<String> message(String routeKey, String payload) {
        return MessageBuilder
                .withPayload(payload)
                .setHeader("route-key", routeKey)
                .build();
    }

    private Function<Object, Object> router() {
        Function<Object, Object> router =
                catalog.lookup("functionRouter");
        assertNotNull(router);
        return router;
    }

    @Test
    void routesToNormalizeFunction() {
        Object result = router().apply(
                message("normalize", "  Spring   Cloud Function  "));

        assertEquals("SPRING CLOUD FUNCTION", result);
    }

    @Test
    void routesToReverseFunction() {
        Object result = router().apply(
                message("reverse", "abc 123"));

        assertEquals("321 cba", result);
    }

    @Test
    void routesToMaskFunction() {
        Object result = router().apply(
                message("mask", "order 123"));

        assertEquals("order ***", result);
    }

    @Test
    void normalizesRouteAlias() {
        Object result = router().apply(
                message(" NORMALIZE ", "  spring cloud "));

        assertEquals("SPRING CLOUD", result);
    }

    @Test
    void rejectsUnknownRouteKey() {
        Message<String> input =
                message("deleteAll", "some payload");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsFunctionNameAsRouteKey() {
        Message<String> input =
                message("reverseText", "abc");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsCompositionInRouteKey() {
        Message<String> input =
                message("normalizeText|reverseText", "abc");

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsMissingRouteHeader() {
        Message<String> input = MessageBuilder
                .withPayload("Spring Cloud")
                .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void rejectsNonStringRouteHeader() {
        Message<Integer> input = MessageBuilder
                .withPayload(42)
                .setHeader("route-key", 123)
                .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> routingCallback.routingResult(input));
    }

    @Test
    void callbackOverridesStandardRoutingHeaders() {
        Message<String> input = MessageBuilder
                .withPayload("  Spring   Cloud ")
                .setHeader("route-key", "normalize")
                .setHeader(
                        "spring.cloud.function.definition",
                        "reverseText")
                .setHeader(
                        "spring.cloud.function.routing-expression",
                        "'reverseText'")
                .build();

        Object result = router().apply(input);

        assertEquals("SPRING CLOUD", result);
    }
}
~~~

### 9.1. Interpreting the Test Results

| Test | What Is Proven |
| --- | --- |
| `routesToNormalizeFunction` | Alias `normalize` invokes the `normalizeText` bean |
| `routesToReverseFunction` | Alias `reverse` invokes the `reverseText` bean |
| `routesToMaskFunction` | Alias `mask` invokes the `maskDigits` bean |
| `normalizesRouteAlias` | Alias is trimmed/lowercased before map lookup |
| `rejectsUnknownRouteKey` | Headers outside the allowlist are rejected |
| `rejectsFunctionNameAsRouteKey` | Producers cannot pass raw bean names |
| `rejectsCompositionInRouteKey` | Producers cannot inject arbitrary compositions |
| `rejectsMissingRouteHeader` | Missing route key does not fall back to a default function |
| `rejectsNonStringRouteHeader` | Invalid header types are rejected |
| `callbackOverridesStandardRoutingHeaders` | Callback takes precedence over standard routing headers |

The two test layers serve different purposes:

- Calling `routingCallback.routingResult(message)` verifies the **allowlist policy** in isolation.
- Calling `router.apply(message)` verifies that **RoutingFunction + FunctionCatalog + callback + target function** work together.

Testing only the callback without testing the router does not prove that the framework discovered the callback bean and uses it during routing.

### 9.2. Why Do the Tests Pass Message Instead of Just String?

Routing metadata lives in the **header**. If you call:

~~~java
router.apply("Spring Cloud");
~~~

the router has no `Message<?>` from which to read `route-key`. For per-message routing, pass `MessageBuilder.withPayload(...).setHeader(...).build()`.

### 9.3. Why Does the Callback Return the Target Function Name?

`MessageRoutingCallback.routingResult` returns a **function definition** (the name of a `Function`/`Consumer`, or a composition if the application intentionally permits one). In this lesson, the callback returns exactly one of three names:

~~~text
normalizeText
reverseText
maskDigits
~~~

It does not return the processed payload. `RoutingFunction` uses that definition to look up the target function in the catalog and then invokes it with the incoming message.

## 10. Testing Rejection Behavior Through the Router

In `FunctionRouterAllowlistTest`, testing rejection directly on the callback clarifies the policy. You can add a router test to verify that errors do not turn into valid function output:

~~~java
@Test
void routerDoesNotInvokeAFunctionForUnknownAlias() {
    Message<String> input = message("admin", "payload");

    assertThrows(
            RuntimeException.class,
            () -> router().apply(input));
}
~~~

The actual exception may be wrapped by the framework, wrapper, or adapter. Therefore:

- Callback unit tests assert the exact `IllegalArgumentException` from the policy.
- Router tests verify that invocation fails on an invalid route.
- Broker/HTTP integration tests verify how exceptions map to responses, retries, or dead-letter queues per configuration.

Do not write HTTP/broker tests expecting a specific status code or retry behavior before defining the adapter's error contract.

## 11. Understanding Standard Routing Headers vs. Application Headers

Spring Cloud Function has two commonly used routing headers:

| Header | Meaning |
| --- | --- |
| `spring.cloud.function.definition` | Function name or composition definition |
| `spring.cloud.function.routing-expression` | SpEL expression producing a function definition |
| `route-key` (this lab) | Application-defined business route key |

In this lesson, only `route-key` is inspected to determine the route. The two standard headers are ignored because the callback is registered and has higher precedence.

### 11.1. What Happens Without a Callback?

When no `MessageRoutingCallback` is present, `RoutingFunction` can read `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` from message headers. The definition header can carry a function name or a composition string. This is convenient for internal systems with trusted producers, but unsuitable when external clients can pick arbitrary functions.

### 11.2. Header SpEL Is Restricted, Yet Still Needs Control

Spring Cloud Function evaluates SpEL coming from message headers with `SimpleEvaluationContext`, which is more restricted than `StandardEvaluationContext`. Expressions coming from application properties or system properties have a broader evaluation context.

This reduces the risk of dangerous expression execution from headers, but **does not replace an allowlist**. Even a simple expression like `headers['route-key']` can select unintended function definitions if producers control the entire target name.

### 11.3. ineligible-definitions Is Not a Routing Allowlist

Spring Cloud Function provides the property:

~~~yaml
spring:
  cloud:
    function:
      ineligible-definitions: internalHelper,debugFunction
~~~

It excludes the named beans from registration candidates in `FunctionCatalog`. It can be used to prevent helper functions from appearing in the catalog.

However, this property differs from a per-message allowlist:

- `ineligible-definitions` filters functions **globally** out of the catalog.
- `MessageRoutingCallback` maps each `route-key` to an allowed function.

If a function is excluded from the catalog, the callback cannot invoke it. If a function remains in the catalog without an alias in the allowlist, the router in this lesson cannot select it.

## 12. Extending to Spring Cloud Stream Event Routing

Header-based routing is especially useful when a single input destination receives multiple event types. Spring Cloud Stream can bind `RoutingFunction` to a single input binding.

To enable event routing, configure:

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
      bindings:
        functionRouter-in-0:
          destination: text.events.in
          group: text-router
          content-type: text/plain
        functionRouter-out-0:
          destination: text.events.out
          content-type: text/plain
~~~

The input binding name is `functionRouter-in-0`. Producers send messages to destination `text.events.in` with:

~~~text
route-key: normalize
contentType: text/plain
payload: "  Spring   Cloud Function "
~~~

`MessageRoutingCallback` selects `normalizeText`, the function returns the normalized string, and the routing function's output is forwarded to the output binding when the routed target is a `Function`.

**This configuration is an extension:** the current Maven project does not include Spring Cloud Stream or a binder. To run with RabbitMQ, add the appropriate BOM-managed binder dependency, configure the broker, and test with real messages.

### 12.1. Bindings When the Router Calls a Function or Consumer

`RoutingFunction` is bound as a special function:

- If it routes to a `Function` producing output, the framework can create an output binding for the router to emit results.
- If it routes to a `Consumer`, there is no business output payload, so the router behaves as a consumer without needing an output binding.

The lab currently has three targets that are all `Function<String,String>`, so both input and output binding configurations make sense. If you add an `audit` route pointing to a `Consumer<String>`, re-evaluate output behavior and design the message flow for that consumer.

### 12.2. Headers Must Be Preserved Across the Broker

`route-key` is a custom message header. Producers, binders, and brokers must preserve this header so the callback can read it. When using Kafka or RabbitMQ, verify:

- The binder's header mapping rules.
- The header's data type after deserialization.
- Broker header naming rules and size/count limits.
- Content type and payload type required by the target function.

Never assume a header attached by the producer will automatically arrive unmodified at the consumer across every binder or bridge.

### 12.3. Routing and Reactive Functions

With an imperative `Function<String,String>`, one message corresponds to one invocation and can be routed by `route-key`.

With a reactive `Function<Flux<String>,Flux<String>>`, the unit of work is the publisher/stream. You cannot read each event's route key as in this lab to swap target functions per element. When you need to dispatch events within a reactive stream, use `filter`/`groupBy`/`flatMap` inside a pipeline or use application properties to select the function for the entire stream.

## 13. Extending to the HTTP Adapter

If you want to send headers over HTTP, add the dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-web</artifactId>
</dependency>
~~~

The Spring Cloud Function web adapter can translate HTTP headers into message headers. When calling the router endpoint, the client sends:

~~~bash
curl -i -X POST "http://localhost:8080/functionRouter" \
  -H "Content-Type: text/plain" \
  -H "route-key: normalize" \
  --data-binary "  Spring   Cloud Function "
~~~

The callback reads `route-key` from the message created by the adapter and selects `normalizeText`.

**Note on public surface area:** The allowlist inside the callback only restricts which functions **functionRouter** is allowed to invoke. If the web adapter also exposes `/normalizeText`, `/reverseText`, or `/maskDigits` directly, clients can call those URLs straight away without passing through the allowlist. In deployment, configure the adapter/gateway to expose only the router entry point or enforce authorization per endpoint, and test that direct paths cannot bypass the policy.

### 13.1. HTTP Tests Do Not Replace Catalog Tests

Catalog tests verify that the router and callback cooperate properly inside the application context. HTTP integration tests must additionally verify:

- The router URL is exported.
- The `route-key` header is propagated as a message header.
- `Content-Type` and payload are converted properly.
- Response status, body, and content type match the contract.
- Target functions cannot be called directly if they are not part of the public API surface.

Do not conclude from a passing `FunctionCatalog.lookup("functionRouter")` test that the HTTP endpoint is already securely configured.

## 14. An Allowlist Does Not Replace Authentication and Authorization

An allowlist answers the question:

> "Which functions is the router allowed to select?"

Authentication and authorization answer a different question:

> "Who is allowed to send messages, and which routes is that caller permitted to invoke?"

In this lab, anyone able to send a message with `route-key=normalize` can ask the router to call `normalizeText`. If `maskDigits` is meant only for a specific client group, a shared allowlist is not enough. You can extend the callback to check an upstream-authenticated principal/tenant/permission:

~~~text
HTTP / broker authentication
          |
          v
Authorization / tenant context
          |
          v
MessageRoutingCallback
          |
          v
route-key -> function allowlist
~~~

Production rules:

1. Never trust client-supplied headers like `X-Role: ADMIN` as proof of authorization.
2. Obtain identity from the security context or verified credentials.
3. Verify that the identity is authorized for the requested route alias.
4. Return the function definition only after authorization checks succeed.
5. Log the route key, correlation ID, and routing decision; avoid logging sensitive payloads.
6. Never include destructive or administrative side-effect functions in a public allowlist.
7. Test direct endpoints and other bindings to ensure there is no router bypass.

## 15. Handling Invalid Routes

In this lab, the callback throws `IllegalArgumentException` if the header is missing or not in the allowlist. That is a **fail-closed** choice: never guess a default route.

There are three distinct scenarios:

| Scenario | Where Detected | Illustrative Policy |
| --- | --- | --- |
| Missing `route-key` | Callback | Reject |
| `route-key` absent from map | Callback | Reject |
| Callback returns a function name not present in catalog | RoutingFunction/catalog | Unroutable error |

Spring Cloud Function provides `DefaultMessageRoutingHandler` for cases where a message cannot be routed to a function in the catalog. The default handler may log and allow the message flow to continue as documented; you can provide a custom implementation to handle unroutable messages.

However, that handler **does not replace allowlist validation in the callback**. The callback must still reject disallowed aliases before returning any function definition.

### 15.1. Do Not Route to Arbitrary Defaults

Some applications want ambiguous routes sent to a `defaultHandler`. Only do this when the default handler has a safe contract, such as recording failed messages into quarantine. Never automatically route invalid messages to a higher-privilege function or one with side effects.

If a fallback is needed:

- Define an explicit server-side route alias, such as `unsupported`.
- Return that alias only when business policy permits.
- Use a consumer that records only required metadata or an error DTO.
- Test that the fallback never accidentally invokes sensitive business functions.

## 16. Running the Tests

In `header-routing-lab`, run:

~~~bash
java -version
mvn -version
mvn test
~~~

Tests expected to pass:

| Group | Expected Outcome |
| --- | --- |
| `TextFunctionsTest` | All three target functions transform strings accurately |
| `FunctionRouterAllowlistTest` | `functionRouter` routes valid aliases accurately |
| Negative routing tests | Unknown aliases, bean names, compositions, missing headers, and wrong types are rejected |
| Precedence test | `route-key` handled by callback overrides standard routing headers |

You do not need a running broker or serverless platform to prove the allowlist works at the catalog layer. If you add an adapter, add dedicated integration tests.

## 17. Extension Exercises

### Exercise A — Adding a Route for JSON Text Output

Add a `summarizeText` function that takes a `String` and returns a JSON string describing character length/word count. Add alias `summary` to the map.

**Requirements:**

- Only route alias `summary` invokes `summarizeText`.
- Header `route-key=summarizeText` must be rejected.
- Write a catalog test verifying the result.

### Exercise B — Routing by Event Type

Create three aliases:

~~~text
customer-created
customer-updated
customer-deleted
~~~

Map each alias to its corresponding function. Use the same `Message<CustomerEvent>` or a unified event schema to verify payload types. If functions take distinct DTOs, configure suitable converters and content types.

**Requirement:** never use raw header values directly as bean names; always map through a fixed map.

### Exercise C — Per-Tenant Authorization

Extend the callback to receive an authenticated identity (from a security context or an injected service). Only tenants holding the `mask` permission may route to `maskDigits`.

**Requirements:** test:

- A tenant authorized for route `mask`.
- A tenant unauthorized for route `mask`.
- Missing authentication context.
- A spoofed `tenant-id` header cannot override the authenticated identity.

### Exercise D — Quarantining Invalid Messages

Instead of only throwing an exception, design a `quarantineMessage` consumer accepting error messages with a safe schema.

**Requirement:** clearly define which cases go to quarantine; do not store raw payloads containing sensitive data without a retention policy. Write tests proving valid routes do not enter quarantine.

### Exercise E — Adding an Allowed Composition

If the business genuinely needs the pipeline `normalizeText|maskDigits`, add a single dedicated alias:

~~~text
normalize-and-mask -> normalizeText|maskDigits
~~~

**Requirement:** the map returns only the fixed composition. Header `route-key=normalizeText|maskDigits` must be rejected. Write tests for the expected output and for rejecting producer-supplied compositions.

### Exercise F — Comparing Routing Callback and SpEL

Write a comparison table:

| Criterion | `routing-expression` | `MessageRoutingCallback` |
| --- | --- | --- |
| Declaration | SpEL | Java strategy bean |
| Flexibility | High for expressions | Arbitrary custom Java logic |
| Allowlist | Must craft controlling expressions manually | Can map aliases via a fixed allowlist |
| Precedence | After callback | Before message headers and properties |
| Testing | Test expression + context | Callback unit tests + catalog tests |

**Requirement:** explain why a short expression does not equal a complete authorization policy.

## 18. Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `catalog.lookup("functionRouter")` returns null | Spring Cloud Function not loaded or wrong lookup name | Check dependencies/context and router name |
| Callback does not execute | Callback bean not scanned or registered | Check `@Configuration` and packages |
| Route header is not read | Passing raw payload instead of `Message<?>` | Use `MessageBuilder` and set the header |
| Header causes cast exception | Producer sent a non-String value | Check `instanceof String` and reject |
| Producer invokes unintended function | Callback returns raw header or is not registered | Use allowlist map and test precedence |
| Routing expression overrides callback | Callback was not actually picked up by Spring | Test callback bean and route via `functionRouter` |
| Valid alias but function missing | Map points to wrong bean name | Check `@Bean` names and catalog |
| Message routes right but converter fails | Target function input type differs from payload | Check generic signatures, content type, and `MessageConverter` |
| Catalog test passes but Kafka does not route | Event routing disabled or binder misconfigured | Enable `spring.cloud.stream.function.routing.enabled` and check input binding |
| Custom header lost across broker | Binder/header mapping drops the header | Check binder-specific header mapping |
| Reactive stream fails to route per message | Reactive function unit of work is the stream | Use application properties or design an in-stream dispatch pipeline |
| Direct endpoint bypasses allowlist | Adapter still exports target functions individually | Expose only the router or secure every endpoint |
| Unknown route dropped without logs | Default handler handles unroutable messages or adapter swallows errors | Define an explicit error policy and test the adapter |
| User can route without business permission | Allowlist mistaken for authorization | Check identity/permissions before returning function definition |

### 18.1. Debugging Sequence

1. Verify JDK/Maven and run `mvn test`.
2. Confirm target functions are Spring beans.
3. Confirm `MessageRoutingCallback` is present in the application context.
4. Invoke the callback directly with one valid message and one invalid message.
5. Look up `functionRouter` through `FunctionCatalog`.
6. Pass a `Message<String>` with `route-key` and verify the result.
7. Send standard routing headers alongside it to verify callback precedence.
8. Only then integrate HTTP or a binder and verify header propagation.
9. Check other endpoints/bindings to ensure there is no bypass path.

## 19. Completion Criteria

| Criterion | Evidence |
| --- | --- |
| Router exists | `FunctionCatalog.lookup("functionRouter")` succeeds |
| Three target functions exist | `normalizeText`, `reverseText`, `maskDigits` |
| Allowlist exists | Maps aliases to fixed function names |
| Header-based routing | `route-key` selects the right function per message |
| Rejects unknown routes | Headers outside the allowlist fail |
| Disallows raw bean names | `route-key=reverseText` is rejected |
| Disallows arbitrary composition | Producer strings containing `|` are rejected |
| Callback takes precedence | Standard routing headers do not override `route-key` |
| Imperative/reactive understood | Distinguishes per-message vs. per-stream routing |
| Security boundaries understood | Allowlist does not replace authz or block direct endpoints if still exposed |

**Summary:** `RoutingFunction` provides a single entry point for per-message function selection. `MessageRoutingCallback` lets the application control that decision in Java code. When headers carry only an alias and the callback maps aliases through an allowlist, producers cannot freely pick bean names or arbitrary compositions. For safe deployment, you must also secure ingress, authorize callers, and ensure adapters expose only permitted entry points.

## 20. Self-Check Questions

**Question 1.** What is the default name of `RoutingFunction` in `FunctionCatalog`?

**Answer:** `functionRouter`.

**Question 2.** Why should `MessageRoutingCallback` not directly return the value of a `function-name` header?

**Answer:** Producers could supply arbitrary bean names or compositions. The callback should map a finite set of route aliases to server-controlled function definitions.

**Question 3.** When a `MessageRoutingCallback` is present, can the `spring.cloud.function.definition` header override the callback's decision?

**Answer:** No, not for imperative per-message routing; the callback has the highest precedence among the documented routing mechanisms.

**Question 4.** What is the role of `spring.cloud.function.routing-expression`?

**Answer:** It is a SpEL expression that computes a function definition. When supplied in a message header, it is evaluated in a restricted context; arbitrary expressions from producers should still not be accepted.

**Question 5.** Why does this lesson use `Function<String,String>` instead of `Function<Flux<String>,Flux<String>>`?

**Answer:** The lesson requires per-message routing. With reactive functions, the unit of work is the entire stream, and per-message routing instructions are not supported in the same way.

**Question 6.** Does an allowlist guarantee the caller is authorized to invoke a function under business rules?

**Answer:** No. It only restricts which targets the router can pick. Authentication and authorization are required to verify which caller may use which aliases.

**Question 7.** If the web adapter still exposes `/reverseText` directly, will `functionRouter`'s allowlist stop clients from calling that URL?

**Answer:** No. You must restrict the adapter/gateway to expose only the router or protect individual endpoints separately.

**Question 8.** Which input binding name does Spring Cloud Stream use for the routing function?

**Answer:** `functionRouter-in-0`. Event routing requires enabling `spring.cloud.stream.function.routing.enabled=true`.

**Question 9.** How does `spring.cloud.function.ineligible-definitions` differ from a routing allowlist?

**Answer:** It excludes beans from the catalog globally; a routing callback allowlist picks a target function per message from among the eligible functions.

## References

- [Spring Cloud Function — Programming Model: RoutingFunction, MessageRoutingCallback, routing precedence](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Event Routing: routing headers and MessageRoutingCallback](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Function — FunctionCatalog and Filtering Ineligible Functions](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud — Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Framework — Message and MessageHeaders](https://docs.spring.io/spring-framework/reference/integration/spring-integration.html)
- [Java 17 — Map and Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
