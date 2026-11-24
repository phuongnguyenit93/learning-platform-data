# Declaring @ReadOperation, @WriteOperation, and @DeleteOperation

A management endpoint may need three capabilities: reading current state, changing a value, and deleting a configured entry. Spring Boot Actuator uses `@ReadOperation`, `@WriteOperation`, and `@DeleteOperation` to describe these operations on a custom endpoint.

These annotations help Actuator discover methods, accept inputs, and expose operations over configured technologies such as HTTP or JMX. The method body remains where you write the actual behavior.

This lesson uses Spring Boot 3.3.x and Java 21. The example manages in-memory feature flags, small enough to clearly observe all three operation types.

## 1. Roles of the Three Annotations

| Annotation | Operation Meaning | When Exposed Over HTTP | Suitable Example |
| --- | --- | --- | --- |
| `@ReadOperation` | Reads information/state | `GET` | Reading the currently set flags |
| `@WriteOperation` | Modifies state or performs a write action | `POST` | Setting the value of a flag |
| `@DeleteOperation` | Deletes data or state managed by the endpoint | `DELETE` | Deleting a set flag |

All three live in the `org.springframework.boot.actuate.endpoint.annotation` package and are placed on endpoint methods. The API describes them as markers identifying operation types: [ReadOperation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/ReadOperation.html) and [WriteOperation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/WriteOperation.html).

The Java method name does not determine the HTTP method. A method named `update` annotated with `@ReadOperation` is still exposed as a read operation; the name does not turn it into `POST`. Therefore, name methods and write behavior consistently with the annotation.

The annotations do not automatically perform business logic either:

- `@ReadOperation` does not automatically forbid all state changes inside the method body.
- `@WriteOperation` does not automatically save to a database or open a transaction.
- `@DeleteOperation` does not automatically know which item to delete.
- The operation type does not automatically grant permissions to callers.

Keep read operations free of business side effects, especially because monitoring tools may invoke them repeatedly.

## 2. How Do Endpoint, Bean, and Operations Relate?

```text
Spring bean with @Endpoint(id = "featureflags")
  ├── @ReadOperation   → read information
  ├── @WriteOperation  → write/modify
  └── @DeleteOperation → delete
            ↓
    Actuator discovers operations
            ↓
    Exposed over HTTP/JMX per configuration
```

There are three distinct conditions:

1. **Bean exists:** the endpoint class must be created by Spring, such as via `@Component` or a `@Bean` method.
2. **Endpoint is enabled:** enablement configuration allows the endpoint to be active.
3. **Exposed over the required technology:** exposure configuration includes that endpoint on HTTP or JMX.

Merely writing `@Endpoint` on a class that is not registered as a bean is not enough. Similarly, having a bean does not mean the HTTP path is already exposed.

With `@Endpoint`, operations are described independently of Spring MVC. When exposed over JMX, they are MBean operations; JMX does not use the HTTP methods GET/POST/DELETE. If you need a web-only endpoint, Actuator also has `@WebEndpoint`, though there is no need to switch to it for this example.

The exposure and execution mechanism for custom endpoints is described in the [Spring Boot 3.3 endpoints documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

## 3. Complete Example: Managing In-Memory Flags

### 3.1. Preparing the Practice Project

Use a standalone Gradle project with a compatible Gradle Wrapper, such as Gradle 8.5, and JDK 21. The files below belong to that practice project.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-operations-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'demo'
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
```

Version `3.3.0` is a baseline to reproduce the example; when placing it in an existing project, follow the 3.3.x version and dependency set managed by that project. This example uses the BOM via Gradle's `platform` mechanism.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    featureflags:
      enabled: true
  endpoints:
    web:
      exposure:
        include: featureflags
```

The configuration exposes only the `featureflags` endpoint over the web in the local practice application. It does not automatically grant access permissions if the project already has Spring Security. The minimal dependency set above does not add Spring Security.

### 3.2. Startup Class

Create `src/main/java/demo/EndpointApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointApplication.class, args);
    }
}
```

### 3.3. Endpoint Class

Create `src/main/java/demo/FeatureFlagsEndpoint.java`:

```java
package demo;

import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "featureflags")
public class FeatureFlagsEndpoint {
    private final ConcurrentMap<String, Boolean> flags = new ConcurrentHashMap<>();

    @ReadOperation
    public Map<String, Boolean> readAll() {
        return new TreeMap<>(flags);
    }

    @ReadOperation
    public Boolean readOne(@Selector String name) {
        return flags.get(name);
    }

    @WriteOperation
    public Map<String, Boolean> write(@Selector String name, boolean enabled) {
        flags.put(name, enabled);
        return Map.of(name, enabled);
    }

    @DeleteOperation
    public void delete(@Selector String name) {
        flags.remove(name);
    }
}
```

The methods have specific responsibilities:

- `readAll()` returns a copy of the existing flags. Callers must not be handed the internal storage structure directly for mutation.
- `readOne(name)` reads one flag; `null` means no value has been set for that name yet.
- `write(name, enabled)` adds a new flag or updates the value of an existing flag.
- `delete(name)` removes the flag if it exists. Calling it again when the flag is already gone still produces no state change.

`ConcurrentHashMap` makes per-key reads/writes safe under concurrency. It does not turn a sequence of multiple operations into a transaction. The example stores state in the RAM of a single instance, so data is lost on restart and not automatically synchronized across instances.

In a real system, business code must read the flag from the appropriate source to use that value. The annotations do not automatically bind this map to every feature in the application.

## 4. From Annotations to HTTP Paths

Keeping the default base path `/actuator` and endpoint ID `featureflags`, we have:

| Java Method | Annotation | HTTP Method | Path |
| --- | --- | --- | --- |
| `readAll()` | `@ReadOperation` | `GET` | `/actuator/featureflags` |
| `readOne(name)` | `@ReadOperation` | `GET` | `/actuator/featureflags/{name}` |
| `write(name, enabled)` | `@WriteOperation` | `POST` | `/actuator/featureflags/{name}` |
| `delete(name)` | `@DeleteOperation` | `DELETE` | `/actuator/featureflags/{name}` |

`@Selector String name` makes `name` a path segment. When calling `/actuator/featureflags/checkout`, Actuator passes the string `checkout` into that parameter.

The method name `readOne` is not automatically appended to the URL. `@WriteOperation` uses `POST`, even if the behavior in the example might be expressed with PUT in another business API.

Here there are two read operations, but their paths differ: one has no selector and one has a selector. The three read/write/delete operations on the selector path are also distinguished by HTTP method.

If you add another read operation with the same existing path, merely changing the Java method name will not make the web mapping unique. Avoid operations with duplicate mapping predicates; check both the HTTP method and the path.

## 5. Binding Inputs to Parameters

With the write method:

```java
@WriteOperation
public Map<String, Boolean> write(@Selector String name, boolean enabled) {
    flags.put(name, enabled);
    return Map.of(name, enabled);
}
```

This is an excerpt from the complete endpoint class above. A corresponding request is:

```http
POST /actuator/featureflags/checkout
Content-Type: application/json
Accept: application/json

{"enabled": true}
```

The two input sources are:

- `name` is taken from the path segment defined by `@Selector`.
- `enabled` is taken from the top-level `enabled` property of the JSON body.

Operation inputs can also be supplied via query parameters according to Actuator's mechanism. When writing examples and usage contracts, pick one clear approach rather than sending the same parameter in multiple places and relying on override precedence.

### Parameter Names Must Be Preserved During Compilation

Actuator needs to know the name `enabled` to bind the input to the Java parameter. Endpoint code must be compiled with `-parameters`. The Spring Boot Gradle plugin in the example already configures this.

If using another build tool, ensure the equivalent flag is enabled; do not rely solely on the IDE showing the variable name. Missing parameter name metadata can prevent operation discovery or invocation from working as expected.

### Input Types and Optional Parameters

Endpoint parameters use simple types such as `String`, `boolean`, and `int`. Actuator converts inputs to the required types before invoking the method body.

Parameters are required by default. If you need an optional parameter, you can use `org.springframework.lang.Nullable` with an appropriate reference type, then specify how missing values are handled. For example, if `null` must be accepted, use `Boolean` instead of primitive `boolean`.

Do not apply MVC controller conventions mechanically:

- `@RequestBody` is not needed for Actuator to read top-level JSON properties in the example.
- Use `@Selector` for path segments of an operation.
- Do not turn all inputs into a complex DTO and assume it is supported like a controller's `@RequestBody` parameter.

Input type constraints do not mean the output can only be a single value: the example returns a `Map` to emit JSON. If a more specialized HTTP contract is needed, consider a web-specific endpoint or an appropriate extension.

## 6. Understanding Return Values and Response Status Codes

The table below applies to default operation responses when exposed over HTTP, not a custom status-code wrapper:

| Operation Type | Return Value | Default HTTP |
| --- | --- | --- |
| Read | Has value | `200 OK` |
| Read | No value, e.g. `null` | `404 Not Found` |
| Write | Has value | `200 OK` |
| Write | No value, e.g. `void` or `null` | `204 No Content` |
| Delete | Has value | `200 OK` |
| Delete | No value, e.g. `void` or `null` | `204 No Content` |

Therefore, choosing the return type is part of the operation contract:

- `readAll()` returning an empty map still **has a value**, so the response is `200` with `{}`.
- `readOne()` returning `Boolean.FALSE` still **has a value**, so the response is `200` with `false`.
- `readOne()` returns `null` when the name is absent, so it receives `404`.
- `write()` returns a non-null map so it receives `200`; it does not automatically become `201` just because a flag was added.
- `delete()` returns `void` so it receives `204`, even when the flag already did not exist under the example's implementation.

Missing a required parameter or failing to convert a parameter to the required type causes the request to receive `400 Bad Request` before the operation body is called. This differs from a business exception thrown inside the method; do not assume every `IllegalArgumentException` automatically becomes `400`.

When a specific HTTP code outside the default rules is required, `WebEndpointResponse` is a tool for web extension operations. It represents an HTTP-dependent choice; see the [WebEndpointResponse API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html). For this lesson, keep return values simple to observe the default behavior accurately.


## 7. Running and Invoking the Endpoint

### 7.1. Starting the Application

From the practice project directory, on Linux/macOS:

```bash
./gradlew bootRun
```

On PowerShell/Windows:

```powershell
.\gradlew.bat bootRun
```

You can stop the `bootRun` process, then package and run the JAR:

```bash
./gradlew bootJar
java -jar build/libs/actuator-operations-demo-1.0.0.jar
```

On Windows, replace the Wrapper invocation with `.\gradlew.bat bootJar`. The `java -jar` command is the same. Startup logs include timestamps and environment info that vary; the values below describe the endpoint's response contract, not the full stdout of the application.

### 7.2. Trying the Read → Write → Read → Delete Flow

The `curl` commands in this section use Bash syntax. Start with a fresh application process so the map contains no flags yet.

Read all:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags
```

Result: `200 OK`, body `{}`.

Set the `checkout` flag:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"enabled":true}' http://localhost:8080/actuator/featureflags/checkout
```

Result: `200 OK`, body `{"checkout":true}`.

Read that specific flag:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

Result: `200 OK`, body `true`.

Set it back to `false` and read:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"enabled":false}' http://localhost:8080/actuator/featureflags/checkout
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

POST returns `200` with `{"checkout":false}`; GET returns `200` with `false`. A disabled state is not mistaken for “non-existent”.

Delete and check again:

```bash
curl -i -X DELETE http://localhost:8080/actuator/featureflags/checkout
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

DELETE returns `204 No Content` with an empty body. The subsequent GET returns `404 Not Found` because `readOne()` returns `null`. Calling DELETE again still receives `204` as the method is written.

### 7.3. Calling from PowerShell

To avoid confusion about passing JSON quotes across shells, you can directly use:

```powershell
$demoEndpointUri = 'http://localhost:8080/actuator/featureflags'
$demoRequestBody = @{ enabled = $true } | ConvertTo-Json

Invoke-RestMethod -Uri "$demoEndpointUri/checkout" -Method Post -ContentType 'application/json' -Body $demoRequestBody
Invoke-RestMethod -Uri "$demoEndpointUri/checkout" -Method Get

$demoDeleteResponse = Invoke-WebRequest -UseBasicParsing -Uri "$demoEndpointUri/checkout" -Method Delete
$demoDeleteResponse.StatusCode
```

The last command returns status `204`. `Invoke-RestMethod` converts JSON into PowerShell objects, so its display format differs from curl's raw JSON string. When testing error cases such as GET after delete, PowerShell commands may throw errors for HTTP 4xx; that does not mean the application stopped running.

## 8. Testing Invalid Inputs and HTTP Methods

### Missing Required Parameter

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{}' http://localhost:8080/actuator/featureflags/checkout
```

The request does not supply `enabled`, so it receives `400`. No default value of `false` is automatically passed into the method just because the Java parameter is `boolean`.

### Wrong Parameter Type

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{"enabled":"not-a-boolean"}' http://localhost:8080/actuator/featureflags/checkout
```

This string cannot be converted to `boolean`, so it receives `400`. You can create a valid flag first, send the invalid request, and then GET again to confirm the old state was not overwritten.

### Using PUT for WriteOperation

```bash
curl -i -X PUT -H "Content-Type: application/json" -d '{"enabled":true}' http://localhost:8080/actuator/featureflags/checkout
```

In this minimal application, the path exists but has no PUT operation, so it receives `405 Method Not Allowed`. If you need an API with a specific PUT/PATCH contract, do not infer that naming the method `write` will alter Actuator's fixed mapping.

Cases to distinguish in the example:

| Case | Response Code | Meaning |
| --- | --- | --- |
| GET map with no elements yet | `200` | An empty map is a valid result |
| GET a flag whose value is `false` | `200` | Flag exists; current value is off |
| GET a non-existent flag | `404` | Operation returned `null` |
| Valid POST | `200` | Operation writes and returns a map |
| POST missing/invalid type `enabled` | `400` | Operation body was not invoked |
| DELETE with method returning `void` | `204` | No response body |
| PUT to a path with only GET/POST/DELETE | `405` | No mapping for that method |

Calling `new FeatureFlagsEndpoint().write(...)` directly only tests Java logic; it bypasses endpoint discovery, exposure, input binding, and web responses. When testing an operation contract, also test at the request-handling layer, such as MockMvc with an Actuator-enabled application context, or by calling a running application.

## 9. Common Errors When Declaring Operations

| Symptom | What to Check |
| --- | --- |
| Endpoint not visible over HTTP | Is the class a bean, is the endpoint enabled, does web exposure include the right ID? |
| Calling `/actuator/featureflags/readAll` gives unexpected result | Method names do not automatically become a URL segment; `readAll` may be treated as a selector value |
| POST does not reach write method | Are HTTP method, path, content type, parameter name, and JSON body all right? |
| Parameter name errors | `-parameters` compiler flag and metadata of the exact class being run |
| Startup reports duplicate mapping | Are there two operations with the same HTTP method and same path shape? |
| GET returns 404 even though endpoint is exposed | Is the operation returning `null`? Distinguish this from a missing endpoint/path |
| POST/DELETE returns 401 or 403 | Authentication, authorization, and CSRF in the active Spring Security configuration |
| Write succeeds but data is lost after restart | The example stores in RAM and has no persistent storage |
| One instance sees different values from another | Each instance holds its own map |

In projects with Spring Security, it is especially important to distinguish mapping errors from requests blocked before reaching the operation. A `403` on POST/DELETE may involve CSRF, even when the caller is authenticated. Apply an appropriate protection policy for management endpoints; operation annotations and exposure do not substitute for that policy.

When changing state via an endpoint in a real system, clearly define write/delete permissions, change scope, and action auditing. This is part of management operation design, not a built-in effect of `@WriteOperation` or `@DeleteOperation`.

## 10. Practice to Understand the Contract Properly

### Exercise 1: Change the Write Operation's Return Type

In a copy of the practice project, change `write()` to return `void` while keeping the map update. Send POST and then GET again.

What to notice: POST changes from `200` with a body to `204` with no body, while the value is still written. The default status code depends on both the operation type and the return result.

### Exercise 2: Read an Off Value vs. a Missing Value

Set flag `checkout=false`, GET once, delete it, then GET again.

Explain the difference between `200 false` and `404`: the value `false` is existing data; `null` represents not found in this design.

### Exercise 3: Change the Java Method Name

Rename `write()` to `setFlag()`, keeping `@WriteOperation` and the parameters. Call the same POST path again.

The HTTP mapping still relies on operation type, endpoint ID, and selector. Changing the Java name does not create a `/setFlag` URL. When using JMX, re-check the exposed operation name because that is a different access contract.

### Exercise 4: Check Required Parameter Boundaries

Create a valid flag, send a POST missing `enabled` or with a wrong-type value, then read it back.

Expected result: the error request receives `400`, and the old value stays intact because the write method body was not invoked. If business rules beyond type conversion are needed, write and test those rules separately.
