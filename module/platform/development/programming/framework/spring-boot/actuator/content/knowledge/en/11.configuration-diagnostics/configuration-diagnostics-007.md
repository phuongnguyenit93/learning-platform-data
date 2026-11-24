# Inspecting Servlet and Reactive Request Mappings with the mappings Endpoint

## 1. What questions do request mappings answer?

Having an `OrderController` class in source code does not guarantee that the path a user calls was registered properly. The controller might lie outside the component-scan scope; the path might differ from expectations; or the request might match the URL but have the wrong HTTP method or miss a header condition.

A **request mapping** is a rule connecting an HTTP request to an application handler. A **handler** can be a controller method, a handler function, a static resource handler, or an Actuator endpoint.

The `mappings` endpoint reports the mappings described by the running application. We use it to trace the chain:

~~~text
Application context
    → dispatcher
    → request matching conditions
    → handler method or function
~~~

Three practical questions in this lesson:

1. Is the target route registered in the right application/context?
2. Which path, HTTP method, parameters, headers, and media types does that route require?
3. Does the result reside in the Servlet/MVC branch or the Reactive/WebFlux branch, and what are the limits of our conclusions?

The mappings list is evidence of routing configuration. It does not replace sending real requests to verify access permissions, input payloads, and business behavior.

## 2. Servlet and Reactive: same goal, different data branches

With **Spring MVC**, the central dispatcher is `DispatcherServlet`. With **Spring WebFlux**, dispatching is handled by `DispatcherHandler`. Both support annotation-based controllers; WebFlux also supports the `RouterFunction` functional routing model.

The response from `GET /actuator/mappings` is grouped by context, then by mapping kind. Locations to recognize:

| Location within a `contexts.<id>.mappings` entry | Practical meaning |
| --- | --- |
| `dispatcherServlets.<beanName>[]` | Mappings routed through the Spring MVC dispatcher. |
| `dispatcherHandlers.<beanName>[]` | Mappings routed through the Spring WebFlux dispatcher. |
| `servlets[]` | Registered Servlets and their URL patterns. |
| `servletFilters[]` | Servlet Filters and their registration scope by URL/Servlet name. |

`contexts` is keyed by context ID; a context may carry `parentId`. Dispatcher names are also data, not fixed keys across every project. Common examples are `dispatcherServlet` in MVC and `webHandler` in WebFlux.

See [Spring Boot 3.3 mappings response contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/mappings.html). Reading only `contexts.application.mappings.dispatcherServlets.dispatcherServlet` will miss applications with different context names, multiple dispatchers, or WebFlux.

Do not infer WebFlux solely because a method returns `Mono`. Spring MVC also supports several asynchronous/reactive return types; verify the actual application type and data branch.

## 3. Servlet hands-on lab with a multi-condition controller

The example uses **Java 21, Gradle 8.5, and Spring Boot 3.3.0** to pin the lab environment. The configuration below is for Boot 3.3; do not directly substitute properties from newer Boot lines into this example.

Create a standalone project:

~~~text
mappings-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/
    │   ├── MappingsLabApplication.java
    │   └── OrderController.java
    └── resources/application.properties
~~~

### 3.1. Project configuration files

Contents of `settings.gradle`:

~~~groovy
rootProject.name = 'mappings-lab'
~~~

Contents of `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'lab'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

The `spring-boot-dependencies` BOM manages library versions used in the example. The Web starter creates an MVC application; Actuator adds management endpoints.

Contents of `src/main/resources/application.properties`:

~~~properties
spring.application.name=mappings-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,mappings
management.endpoint.mappings.enabled=true
~~~

In Boot 3.3, an endpoint being enabled and being exposed over HTTP are two separate states. By default only `health` is exposed over HTTP; include `mappings` in `include` to read it. If `exclude` also contains `mappings`, the exclusion rule takes precedence. See [Enabling and exposing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#exposing-endpoints).

The example listens only on loopback and adds no Spring Security. In secured applications, appropriate read permissions for the endpoint must still be granted. This data can expose internal routes and handler class names.

### 3.2. Main application class

Contents of `src/main/java/lab/MappingsLabApplication.java`:

~~~java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(proxyBeanMethods = false)
public class MappingsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingsLabApplication.class, args);
    }
}
~~~

The main class sits in package `lab`, in the same package tree as the controller so component scanning discovers the controller.

### 3.3. Controller to observe

Contents of `src/main/java/lab/OrderController.java`:

~~~java
package lab;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping(value = "/{id}", produces = "application/json")
    public Map<String, Object> find(@PathVariable("id") long id) {
        return Map.of("id", id, "state", "READY");
    }

    @PostMapping(
            consumes = "application/json",
            produces = "application/json",
            params = "mode=check",
            headers = "X-Lab=on")
    public Map<String, Object> check(@RequestBody Map<String, Object> body) {
        return Map.of("checked", true, "input", body);
    }
}
~~~

There are two rules:

- `find`: accepts `GET /api/orders/{id}` and produces a JSON response.
- `check`: accepts `POST /api/orders`, requiring parameter `mode=check`, header `X-Lab=on`, a JSON request body, and the ability to return JSON to the caller.

Class-level and method-level paths combine into the operation's path. Here `@PathVariable("id")` specifies the variable name explicitly, so it does not rely on Java parameter name inference.

### 3.4. Running and fetching the mappings document

With Gradle 8.5 installed, generate the wrapper once in the project directory:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Run on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

On Linux/macOS, use `./gradlew bootRun`. The first run needs to download Gradle and dependencies. This is a Spring application with library dependencies; do not compile a single controller file with bare `javac` and expect the full system to start.

Once the application starts, open another PowerShell window:

~~~powershell
$document = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/mappings'
$document.contexts.PSObject.Properties.Name
~~~

Or save the raw response on Windows:

~~~powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/mappings' --output mappings.json
~~~

Portions of the example's MVC document look like this. This excerpt keeps only the POST mapping to focus on conditions; the real application also includes GET, Actuator routes, and possibly other default routes:

~~~json
{
  "contexts": {
    "mappings-lab": {
      "mappings": {
        "dispatcherServlets": {
          "dispatcherServlet": [
            {
              "handler": "lab.OrderController#check(Map)",
              "predicate": "{POST [/api/orders], params [mode=check], headers [X-Lab=on], consumes [application/json], produces [application/json]}",
              "details": {
                "handlerMethod": {
                  "className": "lab.OrderController",
                  "name": "check",
                  "descriptor": "(Ljava/util/Map;)Ljava/util/Map;"
                },
                "requestMappingConditions": {
                  "consumes": [
                    {
                      "mediaType": "application/json",
                      "negated": false
                    }
                  ],
                  "headers": [
                    {
                      "name": "X-Lab",
                      "value": "on",
                      "negated": false
                    }
                  ],
                  "methods": [
                    "POST"
                  ],
                  "params": [
                    {
                      "name": "mode",
                      "value": "check",
                      "negated": false
                    }
                  ],
                  "patterns": [
                    "/api/orders"
                  ],
                  "produces": [
                    {
                      "mediaType": "application/json",
                      "negated": false
                    }
                  ]
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

The fields of the POST entry were verified against Boot 3.3.0's mappings data provider. Entry ordering, JSON key ordering, and `predicate` string formatting are not routing precedence order for our tools to rely on.

## 4. Reading an entry by matching conditions

An entry typically contains:

- `handler`: short description of the handler.
- `predicate`: human-readable condition string.
- `details.handlerMethod`: class, method name, and descriptor info, if available.
- `details.requestMappingConditions`: structured conditions for controller mappings, if available.

For the POST mapping just examined, read each group:

| Condition field | Example value | Question to verify on the request |
| --- | --- | --- |
| `patterns` | `/api/orders` | Does the path received by the dispatcher match? |
| `methods` | `POST` | Is the right HTTP method being sent? |
| `params` | `mode=check` | Is the parameter present with the right value? |
| `headers` | `X-Lab=on` | Is the header present matching the condition? |
| `consumes` | `application/json` | Does the request body's `Content-Type` match? |
| `produces` | `application/json` | Does the caller accept this response format, usually via `Accept`? |

`consumes` refers to **incoming** content, whereas `produces` refers to **outgoing** content. Changing the `Accept` header cannot fix an error caused by an incorrect `Content-Type`.

In media type groups, `negated=true` indicates a negated condition. For example, `!application/xml` does not mean only JSON is accepted. For params/headers, read `name`, `value`, and `negated` together; a condition can check presence, absence, or a specific value.

Constraint groups in the example must all be satisfied simultaneously. Do not interpret every array as logical AND: for instance, an HTTP methods list may allow any one of the listed methods. An empty `methods` array on a method-unrestricted mapping does not mean "no HTTP method is allowed".

See [Spring Framework 6.1.8 RequestMapping](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html) to cross-check attribute semantics.

A `descriptor` such as `(J)Ljava/util/Map;` describes the method signature in JVM descriptor format; it is not a JSON schema for requests or responses. Likewise, do not split the `predicate` string by commas to build a long-term parser: use the structured fields whenever present.

A `GET` mapping can also be used by the framework for `HEAD` requests; do not judge `HEAD` support merely by searching for the string `HEAD` in the array.

## 5. Switching to Reactive and also inspecting functional routes

### 5.1. Swapping the starter while keeping the sample controller

In `build.gradle`, **replace**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

with:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

Keep Actuator, the BOM, and the example Java files. A controller returning `Map` is still supported by WebFlux for small, non-blocking work like this example; you do not have to change the return type to `Mono` just to observe the Reactive branch.

Do not keep both starters in this comparison experiment. When MVC and WebFlux are both present, Boot normally auto-configures MVC according to its default selection rule. That is why merely adding the WebFlux library does not prove the application switched to Reactive. See [Boot 3.3 Reactive web applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html#web.reactive.webflux).

Stop the old process, restart the application, and fetch a **fresh response**. Re-filtering the stale `$document` variable does not refresh the data.

The branch to observe becomes `dispatcherHandlers`. Excerpt keeping only GET and selected fields:

~~~json
{
  "contexts": {
    "mappings-lab": {
      "mappings": {
        "dispatcherHandlers": {
          "webHandler": [
            {
              "handler": "lab.OrderController#find(long)",
              "predicate": "{GET /api/orders/{id}, produces [application/json]}",
              "details": {
                "handlerMethod": {
                  "className": "lab.OrderController",
                  "name": "find",
                  "descriptor": "(J)Ljava/util/Map;"
                },
                "requestMappingConditions": {
                  "methods": [
                    "GET"
                  ],
                  "patterns": [
                    "/api/orders/{id}"
                  ]
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Controller condition structures still help inspect paths, methods, and media types. What differs and needs recognition is where the data is grouped and the dispatcher type.

### 5.2. Adding a WebFlux functional route

In the Reactive variant only, add `src/main/java/lab/ReactiveRoutes.java`:

~~~java
package lab;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class ReactiveRoutes {
    @Bean
    RouterFunction<ServerResponse> statusRoute() {
        return RouterFunctions.route()
                .GET("/api/status", request -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of("state", "READY")))
                .build();
    }
}
~~~

After restarting, `GET /api/status` returns a JSON object with `state` equal to `READY`.

This route is declared functionally, not as a `@GetMapping` controller method. In the experiment's Boot 3.3.0 data:

- `predicate` describes `(GET && /api/status)`.
- `details.handlerFunction.className` describes the handler function's class.
- `details.handlerMethod` and `details.requestMappingConditions` have no data for this functional route entry.

If the function is created via a lambda, the generated class name can change across runs. Do not use the full lambda class name as a stable route identifier.

A tool that keeps only entries with `handlerMethod` will miss functional routes. A tool that searches only inside `requestMappingConditions.patterns` will likewise miss `/api/status`. Retain `predicate` and `handlerFunction` information to inspect this group. See [WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).

## 6. Filtering both branches with PowerShell

The snippets below use PowerShell 5.1+ or 7 without StrictMode enabled. They operate on the JSON document just fetched and do not modify server configuration.

### 6.1. Transforming data into easily filterable records

After each application restart, re-fetch:

~~~powershell
$document = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/mappings'
~~~

Then run:

~~~powershell
$rows = @(
    foreach ($context in $document.contexts.PSObject.Properties) {
        foreach ($kind in @('dispatcherServlets', 'dispatcherHandlers')) {
            $dispatchers = $context.Value.mappings.$kind
            if ($null -eq $dispatchers) { continue }

            foreach ($dispatcher in $dispatchers.PSObject.Properties) {
                foreach ($mapping in @($dispatcher.Value)) {
                    if ($null -eq $mapping) { continue }
                    $conditions = $mapping.details.requestMappingConditions

                    [pscustomobject]@{
                        Context       = $context.Name
                        Kind          = $kind
                        Dispatcher    = $dispatcher.Name
                        Methods       = @($conditions.methods)
                        Patterns      = @($conditions.patterns)
                        Params        = @($conditions.params)
                        Headers       = @($conditions.headers)
                        Consumes      = @($conditions.consumes)
                        Produces      = @($conditions.produces)
                        Handler       = $mapping.handler
                        Predicate     = $mapping.predicate
                        HandlerClass  = $mapping.details.handlerMethod.className
                        HandlerMethod = $mapping.details.handlerMethod.name
                        FunctionClass = $mapping.details.handlerFunction.className
                    }
                }
            }
        }
    }
)
~~~

This snippet preserves the context ID, branch kind, and dispatcher name. Entries without method details are still kept. It aggregates only the two dispatcher branches, without merging `servlets`/`servletFilters` entries as controller routes.

### 6.2. Finding a controller's path pattern

~~~powershell
$rows |
    Where-Object { $_.Patterns -ccontains '/api/orders/{id}' } |
    Select-Object Context, Kind, Dispatcher,
        @{Name='Methods'; Expression={ $_.Methods -join ',' }},
        Handler
~~~

In the Servlet example there is one GET entry under `dispatcherServlets`; in the Reactive variant, the GET entry sits under `dispatcherHandlers`.

`-ccontains` performs a case-sensitive array element match. This searches for a **registered pattern**, not executing a URL matching algorithm. The string `/api/orders/42` does not equal the pattern `/api/orders/{id}`; failing to find a concrete URL string in the filter does not prove the route is missing.

### 6.3. Viewing all conditions of the POST operation

~~~powershell
$postMappings = @(
    $rows | Where-Object {
        $_.Patterns -ccontains '/api/orders' -and
        $_.Methods -ccontains 'POST'
    }
)

$postMappings |
    Select-Object Context, Params, Headers, Consumes, Produces |
    ConvertTo-Json -Depth 6
~~~

Verify four facts: `mode=check`, `X-Lab=on`, accepts JSON, and produces JSON. Keep `-Depth 6` so nested structures render clearly instead of printing PowerShell object type names.

If multiple contexts or dispatchers register the same pattern, filter further by `Context`/`Dispatcher` using actual data before concluding.

### 6.4. Searching by controller class

~~~powershell
$rows |
    Where-Object { $_.HandlerClass -ceq 'lab.OrderController' } |
    Select-Object Context, Kind, HandlerMethod, Predicate
~~~

The example has two operations, `find` and `check`. Do not assume the order in which they appear is Spring's selection order.

### 6.5. Preserving and inspecting functional routes

~~~powershell
$rows |
    Where-Object {
        $_.FunctionClass -and $_.Predicate -clike '*/api/status*'
    } |
    Select-Object Context, Kind, Dispatcher, Predicate, FunctionClass
~~~

In the Reactive variant with `ReactiveRoutes` added, this query finds the functional route. String matching in `predicate` here is a human inspection aid, not an HTTP condition evaluator equivalent to Spring's.

### 6.6. Inspecting Servlets and Filters as another registration layer

In the Servlet variant:

~~~powershell
foreach ($context in $document.contexts.PSObject.Properties) {
    Write-Output ('Context: ' + $context.Name)
    $context.Value.mappings.servlets | ConvertTo-Json -Depth 5
    $context.Value.mappings.servletFilters | ConvertTo-Json -Depth 5
}
~~~

A `DispatcherServlet` registered for `/` does not mean every URL has a corresponding controller method. Similarly, a Filter registered for `/*` only describes the Filter's scope; it is not a business API.

The Servlet Filter list also does not expose the internal filters inside each `SecurityFilterChain`. WebFlux applications use a different filtering mechanism; the absence of `servletFilters` does not prove the system lacks security.

## 7. Sending requests and comparing results

### 7.1. Successful requests

GET with PowerShell:

~~~powershell
$getRequest = @{
    Uri = 'http://127.0.0.1:8080/api/orders/42'
    Headers = @{ Accept = 'application/json' }
}
Invoke-RestMethod @getRequest | ConvertTo-Json
~~~

The response contains two values: `id=42` and `state=READY`. Do not rely on `Map` JSON key order.

POST:

~~~powershell
$postRequest = @{
    Method = 'Post'
    Uri = 'http://127.0.0.1:8080/api/orders?mode=check'
    Headers = @{ 'X-Lab' = 'on'; Accept = 'application/json' }
    ContentType = 'application/json'
    Body = '{"name":"book"}'
}
Invoke-RestMethod @postRequest | ConvertTo-Json -Depth 5
~~~

Resulting JSON representation:

~~~json
{
  "checked": true,
  "input": {
    "name": "book"
  }
}
~~~

The example method has neither `@ResponseStatus(CREATED)` nor a `ResponseEntity` with another status code, so this valid POST request returns **200**, rather than automatically becoming 201 just because POST was used.

### 7.2. Changing one condition at a time

The cases below were verified using simulated MVC and WebFlux requests against the lesson's controller:

| Request or change | Example result | How to trace back in mappings data |
| --- | --- | --- |
| `GET /api/orders/42`, accepting JSON | 200 | GET, pattern `/{id}`, produces JSON. |
| `PUT /api/orders/42` | 405 | Path pattern exists, but operation is declared as GET. |
| `GET /api/orders/42`, `Accept: text/plain` | 406 | Accepted response format does not match `produces`. |
| POST with right URL, `mode`, header, but `Content-Type: text/plain` and body `hello` | 415 | `consumes` requires JSON. |

Example command showing 405 on Windows:

~~~powershell
curl.exe -i -X PUT 'http://127.0.0.1:8080/api/orders/42'
~~~

Example showing 406:

~~~powershell
curl.exe -i 'http://127.0.0.1:8080/api/orders/42' -H 'Accept: text/plain'
~~~

Example showing 415, keeping the right parameter and header so only content type changes:

~~~powershell
curl.exe -i -X POST 'http://127.0.0.1:8080/api/orders?mode=check' -H 'X-Lab: on' -H 'Content-Type: text/plain' --data-raw 'hello'
~~~

The status codes above describe the sample application without security or custom error handlers. In real systems, proxies, Filters/WebFilters, security configuration, or exception handlers can intervene before or after routing.

Do not attribute every error to 404. For example, a missing parameter condition can produce a bad-request error; failures converting `id` to a number, malformed JSON, or validation errors also belong to stages separate from whether a URL pattern exists. Match the actual request against the returned error.

## 8. Diagnostic workflow when a route behaves unexpectedly

### Unable to retrieve the mappings document

Check that the application has started, the management URL, `mappings` enablement/exposure, and then authentication and read permissions. `401`/`403` is not proof that the controller is unregistered.

The built-in endpoint in this lesson returns the document at `GET /actuator/mappings`. Do not assume `/actuator/mappings/orders` or a standard `?path=/api/orders` filter exists; filter client-side as shown in Section 6.

### JSON retrieved, but the route is missing

1. Inspect all context IDs and both dispatcher branches.
2. Verify whether the application is actually running MVC or WebFlux.
3. Check component-scan scope, whether the controller is registered, and whether configuration conditions allow creating that component.
4. For functional routes, look for `handlerFunction`/`predicate` instead of only `handlerMethod`.
5. Confirm you are reading the right process, port, and fresh data after restarting.

A `/**` route serving static resources does not substitute for evidence of the target controller. Having many entries in the document likewise does not imply having many business APIs.

### Path pattern exists, yet external calls still fail

Distinguish the URL seen by the caller from the path the application/dispatcher matches against. Common settings to cross-check:

| Component | What to confirm |
| --- | --- |
| Reverse proxy or gateway | Does it strip/add a prefix or forward to another service? |
| `server.servlet.context-path` | Which context prefix does the Servlet app have? |
| `spring.mvc.servlet.path` | Does DispatcherServlet have a custom registration path? |
| `spring.webflux.base-path` | Which base path does the WebFlux variant have? |
| `management.endpoints.web.base-path` | Is the Actuator prefix still `/actuator`? |
| `management.server.port` | Does the management API use a separate port? |

Do not assume `patterns` is always a full public URL ready to append directly to a domain name. Inspect configuration at each layer and the actual request reaching the application. See [Management paths and ports in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Seeing two nearly identical entries or application fails to start

Sharing a URL pattern is not enough to conclude duplicate mappings: two operations can differ in method, params, or media types. Compare all conditions and handler classes.

Conversely, if conflicting declarations prevent Spring from creating the context, that application's endpoint is not ready to read. In that case use startup errors to locate the two conflicting declarations; do not wait for `mappings` from an application that is not running.

### Having a mapping is not sufficient operational evidence

This document does not tell you:

- Whether a specific user is authorized to call the route.
- How many requests the route received or how long they took.
- Which business fields a JSON body requires or whether they are valid.
- Which processing chain a specific request went through or where it failed.
- That every rule of a custom router has a detailed description.

Combine mappings data with test requests, logs, performance observability, or API contract docs according to the actual question. Reading `mappings` never adds, deletes, or modifies routes.

## 9. Self-verification exercises

**Exercise 1 — Identify the dispatcher.** Run both variants in turn. Record `Context`, `Kind`, and `Dispatcher` for the `find` operation.

Check: MVC has `dispatcherServlets`; WebFlux has `dispatcherHandlers`. Take context/dispatcher names from actual data rather than hardcoding them in answers.

**Exercise 2 — From conditions to a request.** Find the POST entry and write a successful request from the six condition groups.

Check: POST to the right path; `mode=check`; `X-Lab=on`; JSON body and JSON Accept. Then change only `Content-Type` to verify the cause of 415.

**Exercise 3 — Do not miss functional routes.** In the WebFlux variant, locate `/api/status` using both the controller-pattern query and the functional-route query.

Check: a query checking only `requestMappingConditions.patterns` fails to find the example's functional route; a query retaining `predicate` and `FunctionClass` finds it.

**Exercise 4 — Controlled path change.** Change `@RequestMapping("/api/orders")` to `@RequestMapping("/api/purchases")`, restart, fetch fresh JSON, and resend the GET request.

Check: the controller pattern changes to `/api/purchases/{id}`; `/api/status` of the functional route stays independent. Both the test request and the query's pattern string must be updated.

**Exercise 5 — Limits of conclusions.** An entry exists yet the caller receives 403; another application returns `Mono` yet data sits in `dispatcherServlets`. Explain both cases.

Check: route registration and access control are two separate layers; a single method's return type does not by itself determine the MVC/WebFlux choice for the entire application.

The completion goal for this lesson is to locate routes in the right context and dispatcher, construct requests from complete conditions, verify responses, and keep conclusions within the scope of evidence that `mappings` actually provides.
